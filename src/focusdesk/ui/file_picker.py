"""Read-only, one-directory-at-a-time picker shared with task file services."""
from __future__ import annotations

from pathlib import Path
from tkinter import ttk

from ..errors import FocusDeskError
from ..services.files import format_size
from .common import ModalDialog, make_tree, show_error


class TaskFilePicker(ModalDialog):
    enter_confirms = False

    def __init__(self, parent, files, node_id):
        super().__init__(parent, "Din fișierele taskului/proiectului", resizable=True,
                         ok_text="Adaugă fișierele selectate")
        self.geometry("800x480")
        self.minsize(580, 360)
        self.files = files
        self.locations = files.browse_locations(node_id)
        self.directory = None
        self.entries = {}
        self.body.pack_forget()
        self.buttons.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        self.location = ttk.Combobox(self.body, state="readonly", values=[item.label for item in self.locations])
        self.location.pack(fill="x")
        self.location.bind("<<ComboboxSelected>>", lambda _e: self._select_location())
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        self.up = ttk.Button(row, text="↑ Folder părinte", command=self._up)
        self.up.pack(side="left")
        self.path = ttk.Label(row, style="Muted.TLabel", wraplength=540)
        self.path.pack(side="left", fill="x", expand=True, padx=8)
        self.notice = ttk.Label(self.body, style="Muted.TLabel", wraplength=720,
                                text="Selectează documente cu Ctrl/Shift. Enter sau dublu-click deschide un folder.")
        self.notice.pack(side="bottom", fill="x", pady=6)
        self.more = ttk.Button(self.body, text="Încarcă următoarele 200", command=self._append)
        self.more.pack(side="bottom", anchor="w")
        self.tree, frame = make_tree(self.body, [("name", "Nume", 380), ("size", "Dimensiune", 110)], height=10)
        self.tree.configure(selectmode="extended")
        frame.pack(fill="both", expand=True)
        self.tree.bind("<Return>", self._activate)
        self.tree.bind("<Double-1>", self._activate)
        self.tree.bind("<Alt-Up>", lambda _e: self._up())
        self.bind("<Configure>", self._resize)
        if self.locations:
            self.location.current(0)
            self._select_location()

    def _resize(self, event):
        if event.widget is self:
            self.path.configure(wraplength=max(200, event.width - 220))
            self.notice.configure(wraplength=max(300, event.width - 40))

    def _select_location(self):
        self._load(self.locations[self.location.current()].path)

    def _load(self, path: Path):
        self.directory = path
        self.path.configure(text=str(path))
        self.up.state(["disabled"] if path == self.locations[self.location.current()].path else ["!disabled"])
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        self._remaining = []
        self.more.state(["disabled"])
        try:
            entries = self.files.browse_directory(path)
        except FocusDeskError as exc:
            self.notice.configure(text=str(exc))
            return
        self.notice.configure(text="Selectează documente cu Ctrl/Shift. Enter sau dublu-click deschide un folder."
                              if entries else "Folder gol. Poți alege altă locație.")
        self._remaining = entries
        self._append()

    def _append(self):
        # Sort the entire directory before paging; preserve existing selection while appending.
        batch, self._remaining = self._remaining[:200], self._remaining[200:]
        for entry in batch:
            key = str(len(self.entries))
            self.entries[key] = entry
            self.tree.insert("", "end", iid=key, values=(
                ("▣ " if entry.is_dir else "") + entry.path.name,
                "Folder" if entry.is_dir else format_size(entry.size_bytes or 0)))
        self.more.state(["!disabled"] if self._remaining else ["disabled"])

    def _up(self):
        if self.directory and self.directory != self.locations[self.location.current()].path:
            self._load(self.directory.parent)
        return "break"

    def _activate(self, _event=None):
        selected = self.tree.selection()
        if selected:
            entry = self.entries[selected[0]]
            if entry.is_dir:
                self._load(entry.path)
            else:
                self._on_ok()
        return "break"

    def validate(self):
        selected = [self.entries[key] for key in self.tree.selection()]
        if not selected or any(item.is_dir for item in selected):
            show_error(self, "Selectează fișiere. Deschide folderele pentru a alege documentele din interior.")
            return False
        return True

    def collect(self):
        return [str(self.entries[key].path) for key in self.tree.selection()]

    def run(self):
        previous = self.grab_current()
        focus = self.focus_get()
        try:
            return super().run()
        finally:
            if previous is not None and previous.winfo_exists():
                previous.grab_set()
            if focus is not None and focus.winfo_exists():
                focus.focus_set()
