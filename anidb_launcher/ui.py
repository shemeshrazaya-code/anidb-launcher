from __future__ import annotations

import io
import queue
import sys
import threading
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

from PIL import Image, ImageTk

from .models import AnimeDetail
from .favorites import save_favorites, toggle_favorite
from .launcher import launch
from .loading_dialog import CancelledByUser, run_with_progress
from .preferences import load_prefs, save_prefs
from .reminders import (
    add_reminder,
    has_reminder,
    is_released,
    remove_reminder,
    save_reminders,
)
from .setup_dialog import AddSourceDialog
from .sources import AvailabilityResult, SearchSource, check_availability, load_bundled_defaults, load_sources, save_sources

if TYPE_CHECKING:
    from .__main__ import AnimeListItem

THUMBNAIL_MAX_W = 220
THUMBNAIL_MAX_H = 310

FetchDetail = Callable[[int], AnimeDetail | None]


def apply_modern_theme(root: tk.Tk, theme: str = "dark") -> None:
    """Apply sv-ttk theme + mica/acrylic glass effect when available. No-op on missing deps."""
    try:
        import sv_ttk
        sv_ttk.set_theme(theme if theme in ("dark", "light") else "dark")
    except ImportError:
        try:
            ttk.Style(root).theme_use("vista")
        except tk.TclError:
            pass

    if sys.platform == "win32":
        try:
            import pywinstyles
            # mica = subtle dark glass texture; acrylic = light frosted glass.
            pywinstyles.apply_style(root, "mica" if theme == "dark" else "acrylic")
        except Exception:
            pass


def _bind_recursive(widget: tk.Misc, sequence: str, handler) -> None:
    widget.bind(sequence, handler)
    for child in widget.winfo_children():
        _bind_recursive(child, sequence, handler)


def _all_descendants(widget: tk.Misc) -> list[tk.Misc]:
    out: list[tk.Misc] = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(_all_descendants(child))
    return out


def _theme_text_colors(root: tk.Tk) -> tuple[str, str]:
    """Return (background, foreground) hex colors that match the active theme.

    `tk.Text` is a classic Tk widget and does not auto-inherit sv-ttk styling,
    so we query sv-ttk directly when present and pick a sensible pair.
    """
    try:
        import sv_ttk
        if sv_ttk.get_theme() == "dark":
            return "#1c1c1c", "#fafafa"
        return "#fafafa", "#1c1c1c"
    except Exception:
        pass
    style = ttk.Style(root)
    bg = style.lookup("TFrame", "background") or root.cget("background") or "#ffffff"
    fg = style.lookup("TLabel", "foreground") or "#000000"
    return bg, fg


class App:
    def __init__(
        self,
        root: tk.Tk,
        items: list["AnimeListItem"],
        fetch_detail: FetchDetail | None,
        sources_path: Path,
        mode_label: str,
        favorites: set[int] | None = None,
        favorites_path: Path | None = None,
        refresh_fn: Callable[[Callable[..., None]], tuple[list, str]] | None = None,
        prefs_path: Path | None = None,
        initial_theme: str = "dark",
        reminders: list[dict] | None = None,
        reminders_path: Path | None = None,
    ) -> None:
        self.root = root
        self.all_items = items
        self.fetch_detail = fetch_detail
        self.sources_path = sources_path
        self.mode_label = mode_label
        self.refresh_fn = refresh_fn

        self.sources: list[SearchSource] = load_sources(sources_path)
        self.current = None
        self._thumbnail_image: ImageTk.PhotoImage | None = None
        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._source_rows: list[dict] = []
        self._check_seq = 0
        self.favorites: set[int] = favorites if favorites is not None else set()
        self.favorites_path: Path | None = favorites_path
        self.prefs_path: Path | None = prefs_path
        self.theme_name: str = initial_theme if initial_theme in ("dark", "light") else "dark"
        self.reminders: list[dict] = reminders if reminders is not None else []
        self.reminders_path: Path | None = reminders_path

        # All worker → main-thread UI updates flow through this queue. Calling
        # root.after() directly from a worker thread fails on some Python/Tcl
        # builds with "main thread is not in main loop"; queue + poll is safe.
        self._ui_queue: queue.Queue = queue.Queue()

        self._cards_widgets: list[tk.Widget] = []
        self._card_thumb_refs: dict[int, "ImageTk.PhotoImage"] = {}
        self._selected_card: tk.Widget | None = None
        # Debounce handle for typed-search rebuilds. Without this, every keystroke
        # rebuilds ~200 cards which causes visible lag on faster typing.
        self._populate_pending: str | None = None

        root.title("anidb-launcher")
        root.geometry("1320x800")

        self._build_layout()
        self._populate_list()
        self._render_source_rows()
        self._update_status()
        self.root.after(50, self._drain_ui_queue)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception as e:
                    print(f"ui-queue handler error: {type(e).__name__}: {e}", file=sys.stderr)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def _build_layout(self) -> None:
        muted = self.theme["muted"]

        # ── App Bar (always visible, above tabs) ──────────────────────────────
        appbar = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        appbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(appbar, text="anidb-launcher", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(appbar, text=self.mode_label, foreground=muted, padding=(10, 0, 0, 0)).pack(side=tk.LEFT, padx=(10, 0))
        self.refresh_btn = ttk.Button(appbar, text="↻ Refresh", command=self._do_refresh)
        self.refresh_btn.pack(side=tk.RIGHT)
        if self.refresh_fn is None:
            self.refresh_btn.state(["disabled"])
        self.theme_btn = ttk.Button(
            appbar, text=("☀" if self.theme_name == "dark" else "🌙"),
            width=3, command=self._toggle_theme,
        )
        self.theme_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # Status bar pinned to the very bottom (still common across tabs).
        self.status = ttk.Label(self.root, anchor=tk.W, padding=(12, 6), relief=tk.FLAT, foreground=muted)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # ── Tab container ─────────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        library_tab = ttk.Frame(self.notebook)
        self.notebook.add(library_tab, text="Library")

        upcoming_tab = ttk.Frame(self.notebook)
        self.notebook.add(upcoming_tab, text=" 📅 Upcoming ")

        reminders_tab = ttk.Frame(self.notebook)
        self.notebook.add(reminders_tab, text=" 🔔 Reminders ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_library_tab(library_tab)
        self._build_upcoming_tab(upcoming_tab)
        self._build_reminders_tab(reminders_tab)

    def _build_library_tab(self, parent: tk.Widget) -> None:
        muted = self.theme["muted"]
        accent = self.theme["accent"]
        text_bg, text_fg = _theme_text_colors(self.root)

        # ── Search bar (full width, prominent) ────────────────────────────────
        searchbar = ttk.Frame(parent, padding=(16, 4, 16, 4))
        searchbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(searchbar, text="Search", foreground=muted).pack(side=tk.LEFT, padx=(0, 8))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._debounced_populate())
        ttk.Entry(searchbar, textvariable=self.filter_var, font=("Segoe UI", 11)).pack(
            side=tk.LEFT, fill=tk.X, expand=True,
        )

        # ── Filter row ────────────────────────────────────────────────────────
        filters = ttk.Frame(parent, padding=(16, 6, 16, 12))
        filters.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filters, text="Genre", foreground=muted).pack(side=tk.LEFT)
        self.genre_var = tk.StringVar(value="All")
        self._all_genres_choices: list[str] = ["All"] + self._available_genres()
        self.genre_combo = ttk.Combobox(
            filters, textvariable=self.genre_var, values=self._all_genres_choices,
            width=18, state="normal", height=25,
        )
        self.genre_combo.pack(side=tk.LEFT, padx=(6, 14))
        self.genre_combo.bind("<<ComboboxSelected>>", lambda _e: self._populate_list())
        self.genre_combo.bind("<Return>", lambda _e: self._populate_list())
        self.genre_combo.bind("<KeyRelease>", self._on_genre_typed)

        ttk.Label(filters, text="Year", foreground=muted).pack(side=tk.LEFT)
        self.year_var = tk.StringVar(value="All")
        self.year_combo = ttk.Combobox(
            filters, textvariable=self.year_var, values=self._available_years(),
            width=14, state="readonly", height=20,
        )
        self.year_combo.pack(side=tk.LEFT, padx=(6, 14))
        self.year_combo.bind("<<ComboboxSelected>>", lambda _e: self._populate_list())

        ttk.Label(filters, text="Format", foreground=muted).pack(side=tk.LEFT)
        self.format_var = tk.StringVar(value="All")
        self.format_combo = ttk.Combobox(
            filters, textvariable=self.format_var, values=["All"] + self._available_formats(),
            width=10, state="readonly",
        )
        self.format_combo.pack(side=tk.LEFT, padx=(6, 14))
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._populate_list())

        ttk.Label(filters, text="★", foreground="#ffc83d", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.rating_var = tk.DoubleVar(value=0.0)
        ttk.Scale(
            filters, from_=0.0, to=10.0, variable=self.rating_var,
            orient=tk.HORIZONTAL, length=140, command=lambda _v: self._populate_list(),
        ).pack(side=tk.LEFT, padx=(4, 4))
        self.rating_value_label = ttk.Label(filters, text="0.0", width=4)
        self.rating_value_label.pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(filters, text="Sort", foreground=muted).pack(side=tk.LEFT)
        self.sort_var = tk.StringVar(value="Rating")
        sort_combo = ttk.Combobox(
            filters, textvariable=self.sort_var,
            values=["Rating", "Newest", "Oldest", "Title A→Z"],
            width=12, state="readonly",
        )
        sort_combo.pack(side=tk.LEFT, padx=(6, 14))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._populate_list())

        self.favs_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filters, text="♥ Favorites only", variable=self.favs_only_var,
            command=self._populate_list,
        ).pack(side=tk.LEFT)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X)

        # ── Body: cards grid (left, 60%) + detail panel (right, 40%) ─────────
        body = ttk.Frame(parent)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Card grid — left
        left = ttk.Frame(body, padding=(12, 8, 4, 8))
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas_bg, _ = text_bg, text_fg
        self.cards_canvas = tk.Canvas(
            left, highlightthickness=0, background=canvas_bg, borderwidth=0,
        )
        self.cards_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cards_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.cards_canvas.yview)
        cards_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cards_canvas.config(yscrollcommand=cards_scroll.set)

        self.cards_inner = ttk.Frame(self.cards_canvas)
        self._cards_window_id = self.cards_canvas.create_window(
            (0, 0), window=self.cards_inner, anchor="nw"
        )
        self.cards_inner.bind(
            "<Configure>",
            lambda _e: self.cards_canvas.config(scrollregion=self.cards_canvas.bbox("all")),
        )
        self.cards_canvas.bind(
            "<Configure>",
            lambda e: self.cards_canvas.itemconfig(self._cards_window_id, width=e.width),
        )
        self.cards_canvas.bind("<Enter>", self._bind_mousewheel)
        self.cards_canvas.bind("<Leave>", self._unbind_mousewheel)

        # Detail panel — right (scrollable)
        right_outer = ttk.Frame(body, padding=(4, 8, 8, 8), width=520)
        right_outer.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_outer.pack_propagate(False)

        self.detail_canvas = tk.Canvas(
            right_outer, highlightthickness=0, background=canvas_bg, borderwidth=0,
        )
        self.detail_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll = ttk.Scrollbar(right_outer, orient=tk.VERTICAL, command=self.detail_canvas.yview)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail_canvas.config(yscrollcommand=detail_scroll.set)

        detail = ttk.Frame(self.detail_canvas, padding=(16, 12, 16, 16))
        self._detail_window_id = self.detail_canvas.create_window(
            (0, 0), window=detail, anchor="nw"
        )
        detail.bind(
            "<Configure>",
            lambda _e: self.detail_canvas.config(scrollregion=self.detail_canvas.bbox("all")),
        )
        self.detail_canvas.bind(
            "<Configure>",
            lambda e: self.detail_canvas.itemconfig(self._detail_window_id, width=e.width),
        )
        self.detail_canvas.bind("<Enter>", self._bind_detail_mousewheel)
        self.detail_canvas.bind("<Leave>", self._unbind_detail_mousewheel)

        # Hero thumbnail (centered, large)
        hero = ttk.Frame(detail)
        hero.pack(fill=tk.X, pady=(0, 14))
        self.thumb_label = ttk.Label(hero, text="(select an anime)", anchor=tk.CENTER, foreground=muted)
        self.thumb_label.pack(anchor=tk.CENTER)

        # Title
        self.title_label = ttk.Label(
            detail, text="", font=("Segoe UI", 18, "bold"),
            wraplength=460, justify=tk.LEFT,
        )
        self.title_label.pack(anchor=tk.W, pady=(0, 6))

        # Rating + heart toggle
        rating_row = ttk.Frame(detail)
        rating_row.pack(fill=tk.X, pady=(0, 8))
        self.rating_chip = ttk.Label(
            rating_row, text="", font=("Segoe UI", 18, "bold"), foreground="#ffc83d",
        )
        self.rating_chip.pack(side=tk.LEFT)
        self.rating_count_label = ttk.Label(rating_row, text="", foreground=muted)
        self.rating_count_label.pack(side=tk.LEFT, padx=(10, 0))
        self.heart_btn = ttk.Button(rating_row, text="♡", width=4, command=self._toggle_favorite)
        self.heart_btn.pack(side=tk.RIGHT)

        # Stat chips: format · episodes · year
        self.meta_label = ttk.Label(detail, text="", foreground=muted, font=("Segoe UI", 10))
        self.meta_label.pack(anchor=tk.W, pady=(0, 12))

        # Genre pills container
        self.genres_frame = ttk.Frame(detail)
        self.genres_frame.pack(fill=tk.X, pady=(0, 14))
        self.genres_label = ttk.Label(detail, text="", foreground=accent, wraplength=460)
        # legacy reference kept for compat; pills go in genres_frame, fallback to label

        # Synopsis section
        ttk.Label(detail, text="Synopsis", font=("Segoe UI", 11, "bold"), foreground=muted).pack(anchor=tk.W, pady=(0, 4))
        self.synopsis = tk.Text(
            detail, wrap=tk.WORD, height=10, relief=tk.FLAT,
            background=text_bg, foreground=text_fg,
            insertbackground=text_fg,
            selectbackground="#3a5a8a", selectforeground="#ffffff",
            borderwidth=0, padx=0, pady=2,
            font=("Segoe UI", 10),
        )
        self.synopsis.pack(fill=tk.X, pady=(0, 16))
        self.synopsis.config(state=tk.DISABLED)

        # Sources section header
        sources_header = ttk.Frame(detail)
        sources_header.pack(fill=tk.X, pady=(8, 4))
        self.sources_title = ttk.Label(
            sources_header, text="Search sources",
            font=("Segoe UI", 11, "bold"), foreground=muted,
        )
        self.sources_title.pack(side=tk.LEFT)
        try:
            style = ttk.Style()
            style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 4))
            ttk.Button(sources_header, text="+ Add", command=self._add_source, style="Accent.TButton").pack(side=tk.RIGHT)
        except tk.TclError:
            ttk.Button(sources_header, text="+ Add", command=self._add_source).pack(side=tk.RIGHT)

        self.sources_frame = ttk.Frame(detail)
        self.sources_frame.pack(fill=tk.X, pady=(2, 8))

        actions = ttk.Frame(detail)
        actions.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(actions, text="Check all", command=self._check_all_sources).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(actions, text="Reload", command=self._reload_sources).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Edit file", command=self._open_sources_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(actions, text="Restore defaults", command=self._restore_defaults).pack(side=tk.LEFT, padx=4)

    # ── Upcoming tab ──────────────────────────────────────────────────────────
    def _build_upcoming_tab(self, parent: tk.Widget) -> None:
        muted = self.theme["muted"]
        wrap = ttk.Frame(parent, padding=(16, 12, 16, 12))
        wrap.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(wrap)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            header, text="Upcoming releases",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="(items in your cache with a future air date — refresh to expand coverage)",
            foreground=muted,
        ).pack(side=tk.LEFT, padx=(10, 0))

        canvas_bg, _ = _theme_text_colors(self.root)
        self.upcoming_canvas = tk.Canvas(
            wrap, highlightthickness=0, background=canvas_bg, borderwidth=0,
        )
        self.upcoming_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.upcoming_canvas.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.upcoming_canvas.config(yscrollcommand=scroll.set)

        self.upcoming_inner = ttk.Frame(self.upcoming_canvas)
        self._upcoming_window_id = self.upcoming_canvas.create_window(
            (0, 0), window=self.upcoming_inner, anchor="nw",
        )
        self.upcoming_inner.bind(
            "<Configure>",
            lambda _e: self.upcoming_canvas.config(scrollregion=self.upcoming_canvas.bbox("all")),
        )
        self.upcoming_canvas.bind(
            "<Configure>",
            lambda e: self.upcoming_canvas.itemconfig(self._upcoming_window_id, width=e.width),
        )
        self.upcoming_canvas.bind(
            "<Enter>",
            lambda _e: self.upcoming_canvas.bind_all(
                "<MouseWheel>",
                lambda ev: self.upcoming_canvas.yview_scroll(int(-ev.delta / 120), "units"),
            ),
        )
        self.upcoming_canvas.bind(
            "<Leave>",
            lambda _e: self.upcoming_canvas.unbind_all("<MouseWheel>"),
        )

    def _populate_upcoming(self) -> None:
        for w in self.upcoming_inner.winfo_children():
            w.destroy()
        from datetime import date
        today_iso = date.today().isoformat()
        # Pull items with a future or current start_date (sorted ascending).
        upcoming = []
        for it in self.all_items:
            if not it.detail or not it.detail.start_date:
                continue
            sd = it.detail.start_date
            # Pad to YYYY-MM-DD for stable comparison.
            full = sd if len(sd) >= 10 else (sd + "-99-99")[:10]
            if full >= today_iso:
                upcoming.append((sd, it))
        upcoming.sort(key=lambda p: p[0])

        if not upcoming:
            ttk.Label(
                self.upcoming_inner,
                text="No upcoming items in cache. Hit ↻ Refresh to fetch trending/airing releases.",
                foreground=self.theme["muted"], padding=(8, 12),
            ).pack(anchor=tk.W)
            return

        for date_str, it in upcoming[:300]:
            self._build_upcoming_row(date_str, it)

    def _build_upcoming_row(self, date_str: str, item) -> None:
        canvas_bg, _ = _theme_text_colors(self.root)
        t = self.theme
        row = tk.Frame(
            self.upcoming_inner, background=canvas_bg, padx=10, pady=8,
            highlightthickness=1, highlightbackground=t["badge_neutral_bg"],
        )
        row.pack(fill=tk.X, pady=2)

        date_lbl = tk.Label(
            row, text=date_str, font=("Segoe UI", 10, "bold"),
            background=canvas_bg, foreground=t["accent"], width=12, anchor=tk.W,
        )
        date_lbl.pack(side=tk.LEFT, padx=(0, 8))

        title_lbl = tk.Label(
            row, text=item.title, font=("Segoe UI", 10, "bold"),
            background=canvas_bg, foreground=t["card_title_fg"], anchor=tk.W,
        )
        title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        if item.detail and item.detail.type:
            tk.Label(
                row, text=item.detail.type, foreground=t["card_meta_fg"],
                background=canvas_bg, font=("Segoe UI", 9),
            ).pack(side=tk.LEFT, padx=(8, 0))

        already = has_reminder(self.reminders, item.aid)
        bell_btn = ttk.Button(
            row, text=("🔔 Reminded" if already else "🔔 Remind"),
            width=12,
            command=lambda it=item, b=None: self._toggle_reminder(it),
        )
        bell_btn.pack(side=tk.RIGHT, padx=(8, 0))

    # ── Reminders tab ─────────────────────────────────────────────────────────
    def _build_reminders_tab(self, parent: tk.Widget) -> None:
        muted = self.theme["muted"]
        wrap = ttk.Frame(parent, padding=(16, 12, 16, 12))
        wrap.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(wrap)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            header, text="Your reminders",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="(Released items show a 🆕 badge when their air date passes — checked each app launch.)",
            foreground=muted,
        ).pack(side=tk.LEFT, padx=(10, 0))

        canvas_bg, _ = _theme_text_colors(self.root)
        self.reminders_canvas = tk.Canvas(
            wrap, highlightthickness=0, background=canvas_bg, borderwidth=0,
        )
        self.reminders_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.reminders_canvas.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.reminders_canvas.config(yscrollcommand=scroll.set)

        self.reminders_inner = ttk.Frame(self.reminders_canvas)
        self._reminders_window_id = self.reminders_canvas.create_window(
            (0, 0), window=self.reminders_inner, anchor="nw",
        )
        self.reminders_inner.bind(
            "<Configure>",
            lambda _e: self.reminders_canvas.config(scrollregion=self.reminders_canvas.bbox("all")),
        )
        self.reminders_canvas.bind(
            "<Configure>",
            lambda e: self.reminders_canvas.itemconfig(self._reminders_window_id, width=e.width),
        )

    def _populate_reminders(self) -> None:
        for w in self.reminders_inner.winfo_children():
            w.destroy()
        if not self.reminders:
            ttk.Label(
                self.reminders_inner,
                text="No reminders yet. Open the Upcoming tab and tap 🔔 Remind on an item.",
                foreground=self.theme["muted"], padding=(8, 12),
            ).pack(anchor=tk.W)
            return

        # Sort: released-but-recent first, then waiting by date.
        def sort_key(r: dict) -> tuple:
            return (0 if is_released(r) else 1, r.get("target_date") or "9999-99-99")

        for r in sorted(self.reminders, key=sort_key):
            self._build_reminder_row(r)

    def _build_reminder_row(self, reminder: dict) -> None:
        canvas_bg, _ = _theme_text_colors(self.root)
        t = self.theme
        released = is_released(reminder)
        border = "#4ade80" if released else t["badge_neutral_bg"]

        row = tk.Frame(
            self.reminders_inner, background=canvas_bg, padx=10, pady=8,
            highlightthickness=1, highlightbackground=border,
        )
        row.pack(fill=tk.X, pady=2)

        if released:
            tk.Label(
                row, text="🆕 RELEASED", background=canvas_bg, foreground="#4ade80",
                font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.LEFT, padx=(0, 8))
        else:
            tk.Label(
                row, text="⏳ Waiting", background=canvas_bg, foreground=t["muted"],
                font=("Segoe UI", 9),
            ).pack(side=tk.LEFT, padx=(0, 8))

        date_str = reminder.get("target_date") or "TBA"
        tk.Label(
            row, text=date_str, font=("Segoe UI", 10, "bold"),
            background=canvas_bg, foreground=t["accent"], width=12, anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(0, 8))

        title = reminder.get("title") or f"#{reminder.get('aid')}"
        tk.Label(
            row, text=title, font=("Segoe UI", 10, "bold"),
            background=canvas_bg, foreground=t["card_title_fg"], anchor=tk.W,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(
            row, text="✕ Remove", width=10,
            command=lambda aid=int(reminder.get("aid", -1)): self._remove_reminder(aid),
        ).pack(side=tk.RIGHT)

    def _on_tab_changed(self, _event) -> None:
        try:
            tab_text = self.notebook.tab(self.notebook.select(), "text").strip()
        except tk.TclError:
            return
        if "Upcoming" in tab_text:
            self._populate_upcoming()
        elif "Reminders" in tab_text:
            self._populate_reminders()

    def _toggle_reminder(self, item) -> None:
        title = item.title
        target = (item.detail.start_date if item.detail else None) or ""
        if has_reminder(self.reminders, item.aid):
            remove_reminder(self.reminders, item.aid)
        else:
            add_reminder(self.reminders, item.aid, title, target)
        if self.reminders_path is not None:
            try:
                save_reminders(self.reminders_path, self.reminders)
            except OSError as e:
                messagebox.showerror("Save failed", f"Could not save reminders: {e}")
        # Refresh whichever view is visible.
        try:
            tab_text = self.notebook.tab(self.notebook.select(), "text").strip()
        except tk.TclError:
            tab_text = ""
        if "Upcoming" in tab_text:
            self._populate_upcoming()
        elif "Reminders" in tab_text:
            self._populate_reminders()

    def _remove_reminder(self, aid: int) -> None:
        remove_reminder(self.reminders, aid)
        if self.reminders_path is not None:
            try:
                save_reminders(self.reminders_path, self.reminders)
            except OSError:
                pass
        self._populate_reminders()

    def _bind_detail_mousewheel(self, _event=None) -> None:
        self.detail_canvas.bind_all("<MouseWheel>", self._on_detail_mousewheel)

    def _unbind_detail_mousewheel(self, _event=None) -> None:
        self.detail_canvas.unbind_all("<MouseWheel>")

    def _on_detail_mousewheel(self, event) -> None:
        try:
            self.detail_canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass


    def _available_formats(self) -> list[str]:
        seen: dict[str, str] = {}
        for it in self.all_items:
            t = it.detail.type if it.detail else None
            if t:
                seen.setdefault(t.upper(), t)
        return sorted(seen.values(), key=str.lower)

    def _available_genres(self) -> list[str]:
        seen: set[str] = set()
        for it in self.all_items:
            if it.detail is None:
                continue
            for g in (it.detail.genres or ()):
                if g:
                    seen.add(g)
        return sorted(seen, key=str.lower)

    def _available_years(self) -> list[str]:
        years: set[int] = set()
        for it in self.all_items:
            if it.detail is None or not it.detail.start_date:
                continue
            head = it.detail.start_date[:4]
            if head.isdigit():
                years.add(int(head))
        return ["All"] + ["Last 12 months"] + [str(y) for y in sorted(years, reverse=True)]

    def _on_genre_typed(self, event) -> None:
        # Navigation/edit keys shouldn't trigger filtering or list rebuilds.
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Tab", "Escape"):
            return
        typed = self.genre_var.get().strip().lower()
        if not typed:
            self.genre_combo.config(values=self._all_genres_choices)
        else:
            filtered = [g for g in self._all_genres_choices if typed in g.lower()]
            self.genre_combo.config(values=filtered or ["(no match)"])

    def _debounced_populate(self) -> None:
        """Coalesce rapid filter-var updates into a single _populate_list call."""
        if self._populate_pending is not None:
            try:
                self.root.after_cancel(self._populate_pending)
            except (tk.TclError, ValueError):
                pass
        self._populate_pending = self.root.after(200, self._populate_now)

    def _populate_now(self) -> None:
        self._populate_pending = None
        self._populate_list()

    def _filtered_items(self) -> list:
        import datetime
        min_rating = float(self.rating_var.get())
        needle = self.filter_var.get().strip().lower()
        fmt = self.format_var.get() if hasattr(self, "format_var") else "All"
        fmt_norm = fmt.upper() if fmt and fmt != "All" else None
        genre = self.genre_var.get() if hasattr(self, "genre_var") else "All"
        genre_norm = genre.lower() if genre and genre != "All" else None
        favs_only = bool(self.favs_only_var.get()) if hasattr(self, "favs_only_var") else False
        year = self.year_var.get() if hasattr(self, "year_var") else "All"
        year_target: int | None = None
        recent_cutoff: str | None = None
        if year == "Last 12 months":
            cutoff_dt = datetime.date.today() - datetime.timedelta(days=365)
            recent_cutoff = cutoff_dt.isoformat()
        elif year and year != "All" and year.isdigit():
            year_target = int(year)
        out = []
        for it in self.all_items:
            if favs_only and it.aid not in self.favorites:
                continue
            if year_target is not None or recent_cutoff is not None:
                sd = (it.detail.start_date if it.detail else None) or ""
                if year_target is not None:
                    if not sd[:4].isdigit() or int(sd[:4]) != year_target:
                        continue
                else:  # Last 12 months
                    if len(sd) < 4 or sd < recent_cutoff:
                        continue
            rating = it.detail.rating if it.detail else None
            if min_rating > 0.0 and (rating is None or rating < min_rating):
                continue
            if fmt_norm:
                t = (it.detail.type if it.detail else None) or ""
                if t.upper() != fmt_norm:
                    continue
            if genre_norm:
                item_genres = [g.lower() for g in (it.detail.genres or ())] if it.detail else []
                if genre_norm not in item_genres:
                    continue
            if needle:
                hay = it.title.lower()
                alt = (it.detail.alt_titles if it.detail else None) or ()
                if needle not in hay and not any(needle in (a or "").lower() for a in alt):
                    continue
            out.append(it)

        sort_mode = self.sort_var.get() if hasattr(self, "sort_var") else "Rating"
        if sort_mode == "Newest":
            # Pad missing dates so they sort to the end. ISO strings sort lexicographically.
            out.sort(key=lambda i: ((i.detail.start_date or "0000") if i.detail else "0000", i.title.lower()), reverse=True)
        elif sort_mode == "Oldest":
            out.sort(key=lambda i: ((i.detail.start_date or "9999") if i.detail else "9999", i.title.lower()))
        elif sort_mode == "Title A→Z":
            out.sort(key=lambda i: i.title.lower())
        else:  # Rating (default)
            out.sort(key=lambda i: (-(i.detail.rating if (i.detail and i.detail.rating) else 0.0), i.title.lower()))
        return out

    CARD_THUMB_W = 200
    CARD_THUMB_H = 285
    CARD_COLS = 3
    CARD_CAP = 200

    _THEMES = {
        "dark": {
            "card_hover_bg": "#2c2c30",
            "card_selected_bg": "#3a4a6c",
            "card_selected_border": "#7fb4ff",
            "card_title_fg": "#fafafa",
            "card_meta_fg": "#9aa0a6",
            "card_subtle_fg": "#7a7a82",
            "thumb_placeholder_bg": "#2a2a2a",
            "thumb_placeholder_fg": "#888888",
            "muted": "#8a8a92",
            "accent": "#7fb4ff",
            "badge_neutral_bg": "#3a3a3a",
            "badge_neutral_fg": "#cccccc",
            "pywinstyle": "mica",
            "pill_palette": [
                ("#2a4a6c", "#a8c8ff"),
                ("#4a2a6c", "#d0a8ff"),
                ("#6c2a4a", "#ffa8c8"),
                ("#2a6c4a", "#a8ffc8"),
                ("#6c4a2a", "#ffd0a8"),
                ("#4a6c2a", "#c8ffa8"),
            ],
        },
        "light": {
            "card_hover_bg": "#e8e8ec",
            "card_selected_bg": "#cfdcf7",
            "card_selected_border": "#1f6fff",
            "card_title_fg": "#1a1a1a",
            "card_meta_fg": "#5a5a62",
            "card_subtle_fg": "#7a7a82",
            "thumb_placeholder_bg": "#dcdce0",
            "thumb_placeholder_fg": "#5a5a62",
            "muted": "#5a5a62",
            "accent": "#1f6fff",
            "badge_neutral_bg": "#d8d8dc",
            "badge_neutral_fg": "#3a3a3a",
            "pywinstyle": "acrylic",
            "pill_palette": [
                ("#cce5ff", "#003a7a"),
                ("#e5ccff", "#3a007a"),
                ("#ffccdd", "#7a003a"),
                ("#ccffd9", "#007a3a"),
                ("#ffe0cc", "#7a3a00"),
                ("#ddffcc", "#3a7a00"),
            ],
        },
    }

    @property
    def theme(self) -> dict:
        return self._THEMES[self.theme_name]

    @property
    def CARD_HOVER_BG(self) -> str:
        return self.theme["card_hover_bg"]

    @property
    def CARD_SELECTED_BG(self) -> str:
        return self.theme["card_selected_bg"]

    def _bind_mousewheel(self, _event=None) -> None:
        self.cards_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.cards_canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        try:
            self.cards_canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def _populate_list(self) -> None:
        self.rating_value_label.config(text=f"{self.rating_var.get():.1f}")
        self._filtered = self._filtered_items()

        for w in self._cards_widgets:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._cards_widgets = []
        self._selected_card = None

        for col in range(self.CARD_COLS):
            self.cards_inner.columnconfigure(col, weight=1, uniform="cards")

        for i, item in enumerate(self._filtered[: self.CARD_CAP]):
            card = self._build_card(item)
            r, c = divmod(i, self.CARD_COLS)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            self._cards_widgets.append(card)

        self.cards_canvas.yview_moveto(0)
        self._update_status()

    def _build_card(self, item) -> tk.Frame:
        # Use classic tk.Frame so we can set a background that responds to
        # hover/select. ttk.Frame can't change bg without theme overrides.
        canvas_bg, _ = _theme_text_colors(self.root)
        t = self.theme
        card = tk.Frame(
            self.cards_inner,
            background=canvas_bg, padx=8, pady=8,
            highlightthickness=2, highlightbackground=canvas_bg,
            cursor="hand2",
        )
        card._aid = item.aid  # type: ignore[attr-defined]
        card._base_bg = canvas_bg  # type: ignore[attr-defined]

        thumb = tk.Label(
            card, text="loading…",
            width=int(self.CARD_THUMB_W / 8), height=int(self.CARD_THUMB_H / 16),
            background=t["thumb_placeholder_bg"], foreground=t["thumb_placeholder_fg"],
            relief=tk.FLAT, borderwidth=0,
        )
        thumb.pack(pady=(0, 6))

        title_lbl = tk.Label(
            card, text=item.title, font=("Segoe UI", 10, "bold"),
            wraplength=self.CARD_THUMB_W, justify=tk.CENTER, anchor=tk.CENTER,
            background=canvas_bg, foreground=t["card_title_fg"],
        )
        title_lbl.pack(fill=tk.X)

        info = tk.Frame(card, background=canvas_bg)
        info.pack(fill=tk.X, pady=(4, 0))
        rating_text = (
            f"★ {item.detail.rating:.2f}"
            if item.detail and item.detail.rating is not None else "★ —"
        )
        tk.Label(
            info, text=rating_text, foreground="#ffc83d",
            background=canvas_bg, font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)
        if item.aid in self.favorites:
            tk.Label(
                info, text="♥", foreground="#ff5b8a",
                background=canvas_bg, font=("Segoe UI", 12, "bold"),
            ).pack(side=tk.RIGHT)
        if item.detail and item.detail.type:
            tk.Label(
                info, text=item.detail.type, foreground=t["card_meta_fg"],
                background=canvas_bg, font=("Segoe UI", 9),
            ).pack(side=tk.RIGHT, padx=(0, 6))
        if item.detail and item.detail.season:
            tk.Label(
                info, text=item.detail.season, foreground=t["card_subtle_fg"],
                background=canvas_bg, font=("Segoe UI", 8),
            ).pack(side=tk.LEFT, padx=(8, 0))

        def on_click(_event=None, it=item, c=card):
            self._on_card_click(it, c)
        def on_enter(_event=None, c=card):
            if c is not self._selected_card:
                try:
                    c.config(background=self.CARD_HOVER_BG, highlightbackground=self.CARD_HOVER_BG)
                    for child in _all_descendants(c):
                        if isinstance(child, (tk.Frame, tk.Label)):
                            child.config(background=self.CARD_HOVER_BG)
                except tk.TclError:
                    pass
        def on_leave(_event=None, c=card):
            if c is not self._selected_card:
                try:
                    c.config(background=c._base_bg, highlightbackground=c._base_bg)
                    for child in _all_descendants(c):
                        if isinstance(child, (tk.Frame, tk.Label)):
                            child.config(background=c._base_bg)
                except tk.TclError:
                    pass
        _bind_recursive(card, "<Button-1>", on_click)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        if item.detail and item.detail.picture_url:
            threading.Thread(
                target=self._fetch_card_thumb_worker,
                args=(thumb, item.detail.picture_url),
                daemon=True,
            ).start()

        return card

    def _on_card_click(self, item, card: tk.Widget) -> None:
        # Clear previously selected card's accent border + background.
        prev = self._selected_card
        if prev is not None and prev.winfo_exists():
            try:
                base = getattr(prev, "_base_bg", "#1c1c1c")
                prev.config(background=base, highlightbackground=base)
                for child in _all_descendants(prev):
                    if isinstance(child, (tk.Frame, tk.Label)):
                        child.config(background=base)
            except tk.TclError:
                pass
        # Apply selected-state coloring to the newly clicked card.
        try:
            card.config(
                background=self.CARD_SELECTED_BG,
                highlightbackground=self.theme["card_selected_border"],
            )
            for child in _all_descendants(card):
                if isinstance(child, (tk.Frame, tk.Label)):
                    child.config(background=self.CARD_SELECTED_BG)
        except tk.TclError:
            pass
        self._selected_card = card

        self.current = item
        self.title_label.config(text=item.title)
        self._render_source_rows()

        if item.detail is not None:
            self._show_detail(item.detail)
        else:
            self.rating_chip.config(text="")
            self.rating_count_label.config(text="")
            self.heart_btn.config(text=("♥" if item.aid in self.favorites else "♡"))
            self.meta_label.config(text="")
            self._render_genre_pills([])
            self.sources_title.config(text="Search sources")
            self._set_synopsis_text("(loading details...)" if self.fetch_detail else
                                     "(no detail available — try --refresh)")
            self.thumb_label.config(image="", text="(no image)")
            self._thumbnail_image = None
            if self.fetch_detail is not None:
                self._fetch_detail_async(item)

    def _fetch_card_thumb_worker(self, label: tk.Label, url: str) -> None:
        try:
            cached = self._thumb_cache.get(url)
            if cached is not None:
                self._ui_queue.put((self._apply_card_thumb_cached, (label, cached)))
                return
            req = urllib.request.Request(url, headers={"User-Agent": "anidb-launcher/0.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data))
            img.thumbnail((self.CARD_THUMB_W, self.CARD_THUMB_H))
            self._ui_queue.put((self._apply_card_thumb_image, (label, img, url)))
        except Exception:
            pass

    def _apply_card_thumb_cached(self, label: tk.Label, photo: "ImageTk.PhotoImage") -> None:
        if not label.winfo_exists():
            return
        # tk.Label width/height are CHARACTERS in text mode but PIXELS once an
        # image is set. The placeholder used char units (18×13); reset to 0/0
        # so the label sizes to the image's natural pixels.
        # Don't pass background="" — Tk rejects empty as "unknown color name".
        label.config(image=photo, text="", width=0, height=0)
        self._card_thumb_refs[id(label)] = photo

    def _apply_card_thumb_image(self, label: tk.Label, img: "Image.Image", url: str) -> None:
        if not label.winfo_exists():
            return
        photo = ImageTk.PhotoImage(img)
        self._thumb_cache[url] = photo
        label.config(image=photo, text="", width=0, height=0)
        self._card_thumb_refs[id(label)] = photo

    def _fetch_detail_async(self, item) -> None:
        aid = item.aid

        def run() -> None:
            try:
                detail = self.fetch_detail(aid) if self.fetch_detail else None
            except Exception as e:
                print(f"fetch_detail error: {type(e).__name__}: {e}", file=sys.stderr)
                detail = None
            self._ui_queue.put((self._apply_fetched_detail, (item, aid, detail)))

        threading.Thread(target=run, daemon=True).start()

    def _apply_fetched_detail(self, item, aid: int, detail) -> None:
        if self.current is None or self.current.aid != aid:
            return
        if detail is None:
            self._set_synopsis_text("(failed to fetch detail — see terminal)")
            return
        item.detail = detail
        self._show_detail(detail)
        self._populate_list()

    def _show_detail(self, detail: AnimeDetail) -> None:
        if detail.rating is not None:
            self.rating_chip.config(text=f"★ {detail.rating:.2f}")
            count = f"{detail.rating_count:,} votes" if detail.rating_count else ""
            self.rating_count_label.config(text=count)
        else:
            self.rating_chip.config(text="☆ —")
            self.rating_count_label.config(text="(unrated)")

        is_fav = detail.aid in self.favorites
        self.heart_btn.config(text=("♥" if is_fav else "♡"))

        meta_bits = []
        if detail.type:
            meta_bits.append(detail.type)
        if detail.episode_count:
            meta_bits.append(f"{detail.episode_count} ep")
        if detail.season:
            meta_bits.append(detail.season)
        elif detail.start_date:
            meta_bits.append(detail.start_date)
        if detail.start_date and detail.season:
            meta_bits.append(f"aired {detail.start_date}")
        self.meta_label.config(text="   ·   ".join(meta_bits))

        # Render genres as colored pills (not a comma-joined label).
        self._render_genre_pills(detail.genres or [])

        # Update sources section header with the selected title.
        self.sources_title.config(text=f"Search “{detail.title}” on")

        self._set_synopsis_text(detail.description or "(no synopsis)")
        self._load_thumbnail(detail.picture_url)
        # Reset detail-panel scroll when a new item is shown.
        try:
            self.detail_canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _render_genre_pills(self, genres: list[str]) -> None:
        for w in self.genres_frame.winfo_children():
            w.destroy()
        if not genres:
            return
        palette = self.theme["pill_palette"]
        col, row = 0, 0
        max_cols = 6
        for i, g in enumerate(genres[:18]):
            bg, fg = palette[i % len(palette)]
            pill = tk.Label(
                self.genres_frame, text=g,
                background=bg, foreground=fg,
                font=("Segoe UI", 9, "bold"),
                padx=10, pady=3, borderwidth=0, relief=tk.FLAT,
            )
            pill.grid(row=row, column=col, padx=(0, 4), pady=(0, 4), sticky="w")
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _after_refresh_dialog_closed(self) -> None:
        """Re-enable the refresh button and yank the main window back to the
        front. After a long modal blocks for minutes, the main window can end
        up buried behind other apps."""
        try:
            self.refresh_btn.state(["!disabled"])
        except tk.TclError:
            pass
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except tk.TclError:
            pass

    def _do_refresh(self) -> None:
        if self.refresh_fn is None:
            return
        try:
            self.refresh_btn.state(["disabled"])
        except tk.TclError:
            pass
        try:
            new_items, source_name = run_with_progress(
                self.root,
                self.refresh_fn,
                title="Refreshing anime data",
                initial_status="Refreshing — fetch can take 3–5 min for full coverage",
            )
        except CancelledByUser:
            self._after_refresh_dialog_closed()
            return
        except Exception as e:
            self._after_refresh_dialog_closed()
            messagebox.showerror("Refresh failed", f"{type(e).__name__}: {e}")
            return

        self._after_refresh_dialog_closed()
        self.all_items = new_items
        self.mode_label = f"live · {source_name}"
        # Repopulate filter dropdowns from the new data.
        self.format_combo.config(values=["All"] + self._available_formats())
        self._all_genres_choices = ["All"] + self._available_genres()
        self.genre_combo.config(values=self._all_genres_choices)
        if self.format_var.get() not in ("All", *self._available_formats()):
            self.format_var.set("All")
        if self.genre_var.get() not in self._all_genres_choices:
            self.genre_var.set("All")
        self.current = None
        self._populate_list()
        try:
            self.refresh_btn.state(["!disabled"])
        except tk.TclError:
            pass

    def _toggle_theme(self) -> None:
        new = "light" if self.theme_name == "dark" else "dark"
        self.theme_name = new
        try:
            import sv_ttk
            sv_ttk.set_theme(new)
        except ImportError:
            pass

        # Re-apply the glass effect for the new theme — mica (subtle dark
        # texture) for dark, acrylic (frosted translucent) for light.
        if sys.platform == "win32":
            try:
                import pywinstyles
                pywinstyles.apply_style(self.root, self.theme["pywinstyle"])
            except Exception:
                pass

        # Persist preference (load existing prefs first to preserve other keys).
        if self.prefs_path is not None:
            try:
                existing = load_prefs(self.prefs_path) if self.prefs_path.exists() else {}
                existing["theme"] = new
                save_prefs(self.prefs_path, existing)
            except OSError:
                pass

        # Repaint classic-tk widgets (ttk widgets follow sv-ttk automatically).
        text_bg, text_fg = _theme_text_colors(self.root)
        try:
            self.synopsis.config(background=text_bg, foreground=text_fg, insertbackground=text_fg)
            self.cards_canvas.config(background=text_bg)
            self.detail_canvas.config(background=text_bg)
        except tk.TclError:
            pass

        # Source-row badges keep stale dark colors after a theme swap unless
        # we re-render. Same for cards & pills which bake colors at build time.
        self._render_source_rows()
        self._populate_list()
        if self.current and self.current.detail:
            self._show_detail(self.current.detail)

        # Update the toggle button icon to reflect the *next* state.
        self.theme_btn.config(text=("☀" if new == "dark" else "🌙"))

    def _toggle_favorite(self) -> None:
        if self.current is None:
            return
        is_fav = toggle_favorite(self.favorites, self.current.aid)
        self.heart_btn.config(text=("♥" if is_fav else "♡"))
        if self.favorites_path is not None:
            try:
                save_favorites(self.favorites_path, self.favorites)
            except OSError as e:
                messagebox.showerror("Save failed", f"Could not save favorites: {e}")
        # Refresh list so the ♥ prefix updates and "Favorites only" filter reacts.
        self._populate_list()

    def _set_synopsis_text(self, text: str) -> None:
        self.synopsis.config(state=tk.NORMAL)
        self.synopsis.delete("1.0", tk.END)
        self.synopsis.insert("1.0", text)
        self.synopsis.config(state=tk.DISABLED)

    def _load_thumbnail(self, url: str | None) -> None:
        self.thumb_label.config(image="", text="(loading...)")
        self._thumbnail_image = None
        if not url:
            self.thumb_label.config(text="(no image)")
            return
        cached = self._thumb_cache.get(url)
        if cached is not None:
            self._thumbnail_image = cached
            self.thumb_label.config(image=cached, text="")
            return

        def fetch() -> None:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "anidb-launcher/0.1"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data))
                img.thumbnail((THUMBNAIL_MAX_W, THUMBNAIL_MAX_H))
                self._ui_queue.put((self._set_thumbnail, (url, img)))
            except Exception as e:
                err_text = f"(image failed)\n{type(e).__name__}"
                self._ui_queue.put((self._set_thumbnail_error, (err_text,)))

        threading.Thread(target=fetch, daemon=True).start()

    def _set_thumbnail_error(self, text: str) -> None:
        self.thumb_label.config(image="", text=text)

    def _set_thumbnail(self, url: str, img: Image.Image) -> None:
        photo = ImageTk.PhotoImage(img)
        self._thumb_cache[url] = photo
        if self.current and self.current.detail and self.current.detail.picture_url == url:
            self._thumbnail_image = photo
            self.thumb_label.config(image=photo, text="")

    def _render_source_rows(self) -> None:
        for w in self.sources_frame.winfo_children():
            w.destroy()
        self._source_rows = []
        if not self.sources:
            ttk.Label(
                self.sources_frame,
                text="No sources yet — click + Add to configure one.",
                foreground="#888",
            ).pack(anchor=tk.W, pady=(4, 4))
            return
        for source in self.sources:
            row = ttk.Frame(self.sources_frame, padding=(6, 4))
            row.pack(fill=tk.X, pady=1)

            status_var = tk.StringVar(value="•")
            status_badge = tk.Label(
                row, textvariable=status_var, width=2, anchor=tk.CENTER,
                font=("Segoe UI", 11, "bold"),
                background=self.theme["badge_neutral_bg"],
                foreground=self.theme["badge_neutral_fg"],
                padx=4, pady=1,
            )
            status_badge.pack(side=tk.LEFT, padx=(0, 8))

            name_lbl = ttk.Label(row, text=source.name, font=("Segoe UI", 10, "bold"), anchor=tk.W)
            name_lbl.pack(side=tk.LEFT)

            ttk.Button(row, text="Open ↗", width=8,
                       command=lambda s=source: self._open_one(s)).pack(side=tk.RIGHT, padx=(2, 0))
            ttk.Button(row, text="Check", width=7,
                       command=lambda s=source, v=status_var: self._check_one(s, v)).pack(side=tk.RIGHT, padx=(2, 0))

            note_var = tk.StringVar(value="ready")
            ttk.Label(row, textvariable=note_var, foreground="#888", font=("Segoe UI", 9)).pack(
                side=tk.RIGHT, padx=(0, 8),
            )

            self._source_rows.append({
                "source": source, "status": status_var, "note": note_var,
                "badge": status_badge,
            })

    def _check_one(self, source: SearchSource, status_var: tk.StringVar) -> None:
        if self.current is None:
            messagebox.showinfo("Pick an anime", "Select an anime from the list first.")
            return
        title = self.current.title
        status_var.set("…")
        seq = self._check_seq
        row = next((r for r in self._source_rows if r["source"].name == source.name), None)
        if row:
            row["note"].set("checking…")
            badge = row.get("badge")
            if badge is not None:
                try:
                    badge.config(
                        background=self.theme["badge_neutral_bg"],
                        foreground=self.theme["badge_neutral_fg"],
                    )
                except tk.TclError:
                    pass

        def run() -> None:
            try:
                res = check_availability(source, title)
            except Exception as e:
                res = AvailabilityResult(
                    url=source.build_url(title), found=None, status=None,
                    error=f"{type(e).__name__}: {e}",
                )
            self._ui_queue.put((self._apply_check_result, (seq, source, status_var, res)))

        threading.Thread(target=run, daemon=True).start()

    def _check_all_sources(self) -> None:
        if self.current is None:
            messagebox.showinfo("Pick an anime", "Select an anime from the list first.")
            return
        self._check_seq += 1
        for row in self._source_rows:
            self._check_one(row["source"], row["status"])

    _BADGE_STYLE = {
        True:  ("✓", "#1f6f3d", "#d4f5dc"),   # found: green
        False: ("✗", "#7a1d1d", "#ffd6d6"),   # not found: red
        None:  ("!", "#7a4d00", "#ffe1a8"),   # error: amber
    }

    def _apply_check_result(self, seq: int, source: SearchSource, status_var: tk.StringVar, res: AvailabilityResult) -> None:
        if seq != self._check_seq:
            return  # newer "Check all" round has started; drop stale result
        symbol, bg, fg = self._BADGE_STYLE[res.found]
        status_var.set(symbol)
        row = next((r for r in self._source_rows if r["source"].name == source.name), None)
        if row:
            badge = row.get("badge")
            if badge is not None:
                try:
                    badge.config(background=bg, foreground=fg)
                except tk.TclError:
                    pass
            if res.error:
                note = res.error[:40]
            elif res.found is True:
                note = f"found · HTTP {res.status}" if res.status is not None else "found"
            elif res.found is False:
                note = f"no match · HTTP {res.status}" if res.status is not None else "no match"
            else:
                note = f"HTTP {res.status}" if res.status is not None else "error"
            row["note"].set(note)

    def _open_one(self, source: SearchSource) -> None:
        if self.current is None:
            messagebox.showinfo("Pick an anime", "Select an anime from the list first.")
            return
        try:
            launch(source, self.current.title)
        except Exception as e:
            messagebox.showerror("Launch failed", str(e))

    def _reload_sources(self) -> None:
        self.sources = load_sources(self.sources_path)
        self._render_source_rows()
        self._update_status()

    def _restore_defaults(self) -> None:
        defaults = load_bundled_defaults()
        if not defaults:
            messagebox.showinfo(
                "No bundled defaults",
                "No default_sources.json shipped with this build, or the file is empty.",
            )
            return
        names = ", ".join(s.name for s in defaults)
        if not messagebox.askyesno(
            "Restore defaults",
            f"Replace your {len(self.sources)} source(s) with the {len(defaults)} bundled "
            f"default(s)?\n\n{names}\n\nYour current list will be overwritten.",
        ):
            return
        save_sources(self.sources_path, defaults)
        self._reload_sources()

    def _open_sources_file(self) -> None:
        if not self.sources_path.exists():
            self.sources_path.parent.mkdir(parents=True, exist_ok=True)
            self.sources_path.write_text('{"sources": []}\n', encoding="utf-8")
            self._reload_sources()
        try:
            import os
            os.startfile(str(self.sources_path))  # Windows
        except Exception as e:
            messagebox.showerror("Open failed", f"Could not open {self.sources_path}: {e}")

    def _add_source(self) -> None:
        AddSourceDialog(self.root, on_save=self._on_added_source)

    def _on_added_source(self, source: SearchSource) -> None:
        if any(s.name == source.name for s in self.sources):
            messagebox.showerror("Duplicate name", f"A source named {source.name!r} already exists.")
            return
        self.sources.append(source)
        save_sources(self.sources_path, self.sources)
        self._render_source_rows()
        self._update_status()

    def _update_status(self) -> None:
        n_shown = len(getattr(self, "_filtered", self.all_items))
        n_total = len(self.all_items)
        self.status.config(
            text=f"{n_shown}/{n_total} anime · {len(self.sources)} source(s) · {self.sources_path}"
        )


def run_app(
    items: list,
    fetch_detail: FetchDetail | None,
    sources_path: Path,
    mode_label: str = "live",
    root: tk.Tk | None = None,
    favorites: set[int] | None = None,
    favorites_path: Path | None = None,
    refresh_fn: Callable[[Callable[..., None]], tuple[list, str]] | None = None,
    prefs_path: Path | None = None,
    initial_theme: str = "dark",
    reminders: list[dict] | None = None,
    reminders_path: Path | None = None,
) -> None:
    owns_root = root is None
    if owns_root:
        root = tk.Tk()
        apply_modern_theme(root, theme=initial_theme)
    App(
        root, items=items, fetch_detail=fetch_detail, sources_path=sources_path,
        mode_label=mode_label, favorites=favorites, favorites_path=favorites_path,
        refresh_fn=refresh_fn, prefs_path=prefs_path, initial_theme=initial_theme,
        reminders=reminders, reminders_path=reminders_path,
    )

    root.deiconify()
    root.update_idletasks()
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()

    root.mainloop()
