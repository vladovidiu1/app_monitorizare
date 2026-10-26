"""Inspectorul nodului selectat (taburi)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.labels import KIND_LABELS
from ..domain.models import Node
from .sidebar import node_glyph

if TYPE_CHECKING:
    from .app import FocusDeskApp


class InspectorTab(ttk.Frame):
    title = "Tab"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent)
        self.app = app
        self.node_id: str | None = None

    def applies_to(self, node: Node) -> bool:
        return True

    def load(self, node: Node) -> None:
        self.node_id = node.id

    def is_dirty(self) -> bool:
        return False

    def save(self) -> bool:
        return True

    def revert(self) -> None:
        if self.node_id and self.node_id in self.app.ws.nodes:
            self.load(self.app.ws.nodes[self.node_id])


class Inspector(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent)
        self.app = app
        self.node_id: str | None = None
        head = ttk.Frame(self)
        head.pack(fill="x", padx=14, pady=(14, 2))
        self.head_lbl = ttk.Label(head, text="Nimic selectat", style="Section.TLabel", wraplength=520, justify="left")
        self.head_lbl.pack(side="left")
        self.path_lbl = ttk.Label(self, text="", style="Crumb.TLabel", wraplength=520, justify="left")
        self.path_lbl.pack(fill="x", padx=14)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tabs: list[InspectorTab] = []
        self.empty = ttk.Label(self, text="Selectează un folder, proiect sau task\npentru a vedea detaliile.",
                               style="Muted.TLabel", justify="center")

    def add_tab(self, tab: InspectorTab) -> None:
        self.tabs.append(tab)
        self.nb.add(tab, text=tab.title)

    def tab_by_title(self, title: str) -> InspectorTab | None:
        return next((t for t in self.tabs if t.title == title), None)

    def show_tab(self, title: str) -> None:
        tab = self.tab_by_title(title)
        if tab is not None and str(tab) in self.nb.tabs():
            self.nb.select(tab)

    def load(self, node_id: str | None, keep_dirty: bool = False) -> None:
        same = node_id == self.node_id
        self.node_id = node_id
        if node_id is None or node_id not in self.app.ws.nodes:
            self.node_id = None
            self.head_lbl.configure(text="Nimic selectat")
            self.path_lbl.configure(text="")
            self.nb.pack_forget()
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
            return
        self.empty.place_forget()
        if not self.nb.winfo_ismapped():
            self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        node = self.app.ws.get(node_id)
        self.head_lbl.configure(text=f"{node_glyph(node)}  {node.title}")
        anc = " › ".join(a.title for a in self.app.ws.ancestors(node_id))
        self.path_lbl.configure(text=f"{KIND_LABELS[node.kind]}  ·  {anc or 'Rădăcina workspace-ului'}")
        current = self.nb.select()
        for tab in self.tabs:
            state = "normal" if tab.applies_to(node) else "hidden"
            self.nb.tab(tab, state=state)
            if state == "normal" and not (keep_dirty and same and tab.is_dirty()):
                tab.load(node)
        if current and self.nb.tab(current, "state") == "hidden":
            self.nb.select(self.tabs[0])

    def is_dirty(self) -> bool:
        return any(t.is_dirty() for t in self.tabs if self.node_id and t.node_id == self.node_id)

    def save(self) -> bool:
        ok = True
        for t in self.tabs:
            if t.node_id == self.node_id and t.is_dirty():
                ok = t.save() and ok
        return ok

    def revert(self) -> None:
        for t in self.tabs:
            if t.node_id == self.node_id:
                t.revert()

    def refresh_current(self) -> None:
        if self.node_id:
            self.load(self.node_id, keep_dirty=True)
