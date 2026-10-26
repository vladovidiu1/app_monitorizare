"""Selectia cu cautare a colegilor din registrul workspace-ului."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..domain.colleagues import Colleague
from ..errors import FocusDeskError
from ..services.colleagues import load_colleagues
from ..services.workspace import Workspace
from .common import ModalDialog, Tooltip, make_tree, show_error


class ColleaguePickerDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, ws: Workspace) -> None:
        super().__init__(parent, "Alege colegul", resizable=True, ok_text="Alege")
        self.people: dict[str, Colleague] = {}
        try:
            self.people = {person.code: person for person in load_colleagues(ws)}
        except FocusDeskError as exc:
            show_error(self, str(exc))
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self.body, textvariable=self.var, width=60)
        self.entry.pack(fill="x")
        self.tv, frame = make_tree(self.body, [("name", "Nume complet", 300), ("code", "Cod", 140)], height=12)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        if not self.people:
            ttk.Label(self.body, text="Lista de colegi este goală.", style="Muted.TLabel").pack(anchor="w", pady=6)
        self.var.trace_add("write", lambda *_: self._refresh())
        self.tv.bind("<Double-1>", lambda _event: self._on_ok())
        self._refresh()
        self.entry.focus_set()

    def _refresh(self) -> None:
        self.tv.delete(*self.tv.get_children())
        words = self.var.get().casefold().split()
        for person in self.people.values():
            if all(word in person.label.casefold() for word in words):
                self.tv.insert("", "end", iid=person.code, values=(person.name, person.code))

    def validate(self) -> bool:
        if not self.tv.selection():
            show_error(self, "Selectează un coleg din listă.")
            return False
        return True

    def collect(self) -> Colleague:
        return self.people[self.tv.selection()[0]]


class ColleagueField(ttk.Frame):
    def __init__(self, parent: tk.Misc, ws_getter: Callable[[], Workspace],
                 on_change: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.ws_getter, self.on_change = ws_getter, on_change
        self.person: Colleague | None = None
        self.var = tk.StringVar()
        ttk.Entry(self, textvariable=self.var, state="readonly", width=20).pack(side="left", fill="x", expand=True)
        self.pick_btn = ttk.Button(self, text="…", width=3, command=self._pick)
        self.pick_btn.pack(side="left", padx=(4, 0))
        Tooltip(self.pick_btn, "Alege colegul")
        self.clear_btn = ttk.Button(self, text="✕", width=3, command=self._clear)
        self.clear_btn.pack(side="left", padx=(4, 0))
        Tooltip(self.clear_btn, "Elimină solicitantul")

    def set(self, person: Colleague | None) -> None:
        self.person = person
        self.var.set(person.label if person else "")

    def _pick(self) -> None:
        if self.ws_getter().read_only:
            return
        person = ColleaguePickerDialog(self, self.ws_getter()).run()
        if person is not None:
            self.set(person)
            if self.on_change:
                self.on_change()

    def _clear(self) -> None:
        if self.ws_getter().read_only:
            return
        self.set(None)
        if self.on_change:
            self.on_change()