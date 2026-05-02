from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .sources import SearchSource, SourceError, load_bundled_defaults, load_sources, save_sources


class SetupDialog:
    def __init__(self, root: tk.Tk, sources_path: Path, existing: list[SearchSource]) -> None:
        self.root = root
        self.sources_path = sources_path
        self.sources: list[SearchSource] = list(existing)
        self.proceed = False

        root.title("anidb-launcher — first-time setup")
        root.geometry("680x640")

        wrap = ttk.Frame(root, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            wrap,
            text="Welcome — let's add your first search source.",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            wrap,
            text=(
                "anidb-launcher ships with no sources. You decide which sites it "
                "searches when you click an anime."
            ),
            foreground="#555",
            justify=tk.LEFT,
            wraplength=640,
        ).pack(anchor=tk.W, pady=(4, 8))

        tutorial = ttk.LabelFrame(wrap, text=" How to add a source ", padding=10)
        tutorial.pack(fill=tk.X, pady=(0, 10))
        steps = (
            "1. Open the site you want to search in your browser.\n"
            "2. Run a search there for any anime title — e.g. \"naruto\".\n"
            "3. Copy the URL from your browser's address bar.\n"
            "4. Replace the search term with the literal placeholder {query}.\n"
            "5. Click \"Add source...\" below, paste the template, and give it a name."
        )
        ttk.Label(tutorial, text=steps, justify=tk.LEFT, foreground="#333").pack(anchor=tk.W)
        ttk.Label(
            tutorial,
            text=(
                "Example: searching DuckDuckGo for \"naruto\" gives\n"
                "    https://duckduckgo.com/?q=naruto\n"
                "Replace \"naruto\" with {query} →\n"
                "    https://duckduckgo.com/?q={query}"
            ),
            justify=tk.LEFT,
            foreground="#666",
            font=("Consolas", 9),
        ).pack(anchor=tk.W, pady=(8, 0))

        list_frame = ttk.Frame(wrap)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(list_frame, height=10)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scroll.set)
        self._refresh_listbox()

        btn_row = ttk.Frame(wrap)
        btn_row.pack(fill=tk.X, pady=8)
        ttk.Button(btn_row, text="Add source...", command=self._add).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Remove selected", command=self._remove).pack(side=tk.LEFT, padx=2)

        bottom = ttk.Frame(wrap)
        bottom.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(bottom, text="Continue", command=self._continue).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bottom, text="Quit", command=self._quit).pack(side=tk.RIGHT, padx=2)

        self.status = ttk.Label(wrap, text="", foreground="#888")
        self.status.pack(anchor=tk.W, pady=(8, 0))
        self._update_status()

        root.protocol("WM_DELETE_WINDOW", self._quit)

    def _refresh_listbox(self) -> None:
        self.listbox.delete(0, tk.END)
        for s in self.sources:
            tag = " [pattern]" if s.match_pattern else ""
            self.listbox.insert(tk.END, f"{s.name}  -  {s.search_url_template}{tag}")

    def _update_status(self) -> None:
        n = len(self.sources)
        self.status.config(text=f"{n} source(s). Add at least one to continue.")

    def _add(self) -> None:
        AddSourceDialog(self.root, on_save=self._on_added)

    def _on_added(self, source: SearchSource) -> None:
        if any(s.name == source.name for s in self.sources):
            messagebox.showerror("Duplicate name", f"A source named {source.name!r} already exists.")
            return
        self.sources.append(source)
        self._refresh_listbox()
        self._update_status()

    def _remove(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        del self.sources[sel[0]]
        self._refresh_listbox()
        self._update_status()

    def _continue(self) -> None:
        if not self.sources:
            messagebox.showinfo("Add a source", "Add at least one search source before continuing.")
            return
        save_sources(self.sources_path, self.sources)
        self.proceed = True
        self.root.destroy()

    def _quit(self) -> None:
        self.proceed = False
        self.root.destroy()


class AddSourceDialog:
    def __init__(self, parent: tk.Misc, on_save) -> None:
        self.on_save = on_save
        win = tk.Toplevel(parent)
        self.win = win
        win.title("Add search source")
        win.geometry("520x320")
        win.transient(parent)
        win.grab_set()

        wrap = ttk.Frame(win, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)

        ttk.Label(wrap, text="Name").pack(anchor=tk.W)
        self.name_var = tk.StringVar()
        ttk.Entry(wrap, textvariable=self.name_var, width=50).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(wrap, text="Search URL template (must contain {query})").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(wrap, textvariable=self.url_var, width=64).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(
            wrap,
            text="example: https://duckduckgo.com/?q={query}",
            foreground="#888",
        ).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(wrap, text="Match pattern (optional regex)").pack(anchor=tk.W)
        self.pat_var = tk.StringVar()
        ttk.Entry(wrap, textvariable=self.pat_var, width=64).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(
            wrap,
            text='if blank, the app checks whether the anime title appears in the response',
            foreground="#888",
        ).pack(anchor=tk.W, pady=(0, 8))

        btn_row = ttk.Frame(wrap)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="Save", command=self._save).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=2)

    def _save(self) -> None:
        name = self.name_var.get().strip()
        url = self.url_var.get().strip()
        pat = self.pat_var.get().strip() or None
        try:
            source = SearchSource(name=name, search_url_template=url, match_pattern=pat)
        except SourceError as e:
            messagebox.showerror("Invalid source", str(e))
            return
        self.on_save(source)
        self.win.destroy()


def run_setup_if_needed(sources_path: Path) -> bool:
    """Return True if user pressed Continue (sources saved). False if quit."""
    existing = load_sources(sources_path) if sources_path.exists() else []
    if existing:
        return True
    # Auto-seed from bundled defaults when user has no sources file yet.
    # This is what lets a fresh install ship with pre-configured sources
    # while still allowing the user to edit/remove them after.
    bundled = load_bundled_defaults()
    if bundled:
        save_sources(sources_path, bundled)
        return True
    root = tk.Tk()
    dialog = SetupDialog(root, sources_path=sources_path, existing=existing)
    root.mainloop()
    return dialog.proceed
