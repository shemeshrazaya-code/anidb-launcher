from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

POLL_INTERVAL_MS = 50
TICK_INTERVAL_MS = 500


def _fmt_eta(secs: int) -> str:
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


class CancelledByUser(RuntimeError):
    pass


class LoadingDialog:
    def __init__(self, root: tk.Tk, title: str = "Loading...",
                 on_cancel: Callable[[], None] | None = None) -> None:
        win = tk.Toplevel(root)
        self.win = win
        win.title(title)
        win.geometry("480x230")
        win.transient(root)
        win.resizable(False, False)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        self._on_cancel = on_cancel
        win.protocol("WM_DELETE_WINDOW", self._handle_cancel)

        wrap = ttk.Frame(win, padding=16)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Starting...")
        ttk.Label(wrap, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        self.detail_var = tk.StringVar(value="")
        ttk.Label(wrap, textvariable=self.detail_var, foreground="#9aa0a6").pack(anchor=tk.W, pady=(2, 8))

        self.progress = ttk.Progressbar(wrap, mode="indeterminate", length=440)
        self.progress.pack(fill=tk.X)
        self.progress.start(12)

        # Live ETA indicator. set_progress() updates this from the
        # current/total/elapsed-time triplet so the user can estimate finish.
        self.eta_var = tk.StringVar(value="")
        ttk.Label(
            wrap, textvariable=self.eta_var,
            font=("Segoe UI", 10, "bold"), foreground="#7fb4ff",
        ).pack(anchor=tk.W, pady=(8, 0))

        # Always-running elapsed-time indicator. Independent of progress events,
        # so the dialog visibly stays alive even during long waits (e.g. when a
        # rate-limited HTTP retry blocks the worker for tens of seconds).
        self._start_time = time.time()
        self.elapsed_var = tk.StringVar(value="elapsed: 0s")
        ttk.Label(wrap, textvariable=self.elapsed_var, foreground="#888").pack(anchor=tk.W)
        self._tick_elapsed()

        # Cancel button gives users a way to abort a multi-minute fetch.
        self.cancel_btn = ttk.Button(wrap, text="Cancel", command=self._handle_cancel)
        self.cancel_btn.pack(anchor=tk.E, pady=(10, 0))

    def _handle_cancel(self) -> None:
        if self._on_cancel is None:
            return
        self.cancel_btn.config(text="Cancelling...", state=tk.DISABLED)
        self.status_var.set("Cancelling — finishing current request...")
        self._on_cancel()

    def _tick_elapsed(self) -> None:
        if not self.win.winfo_exists():
            return
        secs = int(time.time() - self._start_time)
        m, s = divmod(secs, 60)
        self.elapsed_var.set(f"elapsed: {m}m {s:02d}s" if m else f"elapsed: {s}s")
        try:
            self.win.after(TICK_INTERVAL_MS, self._tick_elapsed)
        except tk.TclError:
            pass

    def set_status(self, status: str, detail: str = "") -> None:
        self.status_var.set(status)
        self.detail_var.set(detail)

    def set_progress(self, current: int, total: int, label: str = "") -> None:
        if total <= 0:
            return
        if str(self.progress["mode"]) != "determinate":
            self.progress.stop()
            self.progress.config(mode="determinate", maximum=total)
        self.progress["value"] = current
        if label:
            self.detail_var.set(label)

        # ETA from observed page-rate; recalibrates each tick so it absorbs
        # rate-limit pauses gracefully.
        elapsed = max(time.time() - self._start_time, 0.001)
        pct = int((current / total) * 100) if total else 0
        if 0 < current < total:
            rate = current / elapsed  # pages per second
            remaining = (total - current) / rate if rate > 0 else 0
            self.eta_var.set(f"{pct}% — about {_fmt_eta(int(remaining))} remaining")
        elif current >= total:
            self.eta_var.set(f"{pct}% — wrapping up...")
        else:
            self.eta_var.set(f"{pct}% — calculating...")

    def close(self) -> None:
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass


def run_with_progress(
    root: tk.Tk,
    work: Callable[[Callable[..., None]], Any],
    title: str = "Loading...",
    initial_status: str = "Starting...",
) -> Any:
    """Show a modal Toplevel progress dialog, run `work(progress_cb)` in a daemon thread.

    Worker pushes progress events to a thread-safe Queue; the main thread polls
    via tk.after — this is the canonical Tkinter+threads pattern that works
    regardless of Tcl's threading mode.

    `progress_cb` accepts kwargs: status (str), detail (str), current (int), total (int).
    Returns work's return value, or re-raises any exception it threw. If the
    user clicks Cancel, the next progress_cb call inside `work` raises
    CancelledByUser; the worker should let that propagate out of work().
    """
    cancel_event = threading.Event()
    dialog = LoadingDialog(root, title=title, on_cancel=cancel_event.set)
    dialog.set_status(initial_status)

    msg_queue: queue.Queue = queue.Queue()
    holder: dict[str, Any] = {"value": None, "error": None}

    def progress_cb(**kwargs: Any) -> None:
        if cancel_event.is_set():
            raise CancelledByUser("user cancelled")
        msg_queue.put(("progress", kwargs))

    def worker() -> None:
        try:
            holder["value"] = work(progress_cb)
        except BaseException as e:
            holder["error"] = e
        finally:
            msg_queue.put(("done", None))

    def drain_queue() -> None:
        try:
            while True:
                kind, payload = msg_queue.get_nowait()
                if kind == "progress":
                    _apply_progress(dialog, payload)
                elif kind == "done":
                    dialog.close()
                    return
        except queue.Empty:
            pass
        root.after(POLL_INTERVAL_MS, drain_queue)

    threading.Thread(target=worker, daemon=True).start()
    root.after(POLL_INTERVAL_MS, drain_queue)
    root.wait_window(dialog.win)

    if holder["error"] is not None:
        raise holder["error"]
    return holder["value"]


def _apply_progress(dialog: LoadingDialog, kwargs: dict) -> None:
    status = kwargs.get("status")
    detail = kwargs.get("detail", "")
    current = kwargs.get("current")
    total = kwargs.get("total")
    if status is not None:
        dialog.set_status(status, detail)
    elif detail:
        dialog.detail_var.set(detail)
    if current is not None and total is not None:
        dialog.set_progress(current, total, detail)
