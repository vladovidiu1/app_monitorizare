"""Bara de stare de jos."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .common import error_color, muted_color, ok_color


class StatusBar(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=(8, 4))
        self._labels: dict[str, ttk.Label] = {}
        for key in ("workspace", "save", "timer", "calendar"):
            lbl = ttk.Label(self, text="", style="Muted.TLabel")
            lbl.pack(side="left", padx=(8, 12))
            self._labels[key] = lbl
        self.message = ttk.Label(self, text="", style="Muted.TLabel")
        self.message.pack(side="right", padx=10)
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=90)
        self._busy_text = ""

    def _set(self, key: str, text: str, color: str | None = None) -> None:
        lbl = self._labels[key]
        lbl.configure(text=text, foreground=color or muted_color(self))

    def set_workspace(self, name: str, path: str, read_only: bool) -> None:
        text = f"Workspace: {name} — {path}"
        if read_only:
            text += "  [DOAR CITIRE]"
        self._set("workspace", text, error_color(self) if read_only else None)

    def set_saved(self) -> None:
        self._set("save", f"Salvat {datetime.now():%H:%M:%S}", ok_color(self))

    def set_save_error(self, text: str = "Eroare la salvare") -> None:
        self._set("save", text, error_color(self))

    def set_save_idle(self, text: str = "") -> None:
        self._set("save", text)

    def set_timer(self, text: str, active: bool = False) -> None:
        self._set("timer", text, ok_color(self) if active else None)

    def set_calendar(self, text: str, state: str = "muted") -> None:
        colors = {"ok": ok_color(self), "error": error_color(self), "muted": None}
        self._set("calendar", text, colors[state])

    def set_message(self, text: str) -> None:
        self.message.configure(text=text)

    def set_busy(self, text: str) -> None:
        self.message.configure(text=text)
        if not self.progress.winfo_ismapped():
            self.progress.pack(side="right", padx=(0, 6), pady=3)
            self.progress.start(12)

    def clear_busy(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.message.configure(text="")
