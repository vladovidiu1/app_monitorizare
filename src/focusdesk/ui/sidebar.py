"""Panoul din stanga: vizualizari inteligente si arborele de noduri."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.models import CLOSED_STATUSES, Kind, Node
from .common import KIND_GLYPH, STATUS_GLYPH, muted_color
from .design import icon, button
from .status_visuals import node_icon, node_label

if TYPE_CHECKING:
    from .app import FocusDeskApp

SMART_VIEWS = [
    ("today", "Astăzi"),
    ("inbox", "Inbox"),
    ("waiting", "În așteptare"),
    ("overdue", "Restante"),
    ("calendar", "Calendar"),
    ("archive", "Arhivă"),
]


def node_glyph(node: Node) -> str:
    if node.kind == Kind.TASK:
        return STATUS_GLYPH.get(node.status.value if node.status else "todo", "○")
    return KIND_GLYPH[node.kind.value]


class Sidebar(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, style="Sidebar.TFrame")
        self.app = app
        self._suppress = False
        button(self, "Timp lucrat", app.open_dashboard, glyph="chart").pack(fill="x", padx=10, pady=(12, 0))
        ttk.Label(self, text="WORKSPACE", style="Sidebar.TLabel").pack(anchor="w", padx=14, pady=(14, 4))
        self.views = ttk.Treeview(self, show="tree", selectmode="browse", height=len(SMART_VIEWS), style="Nav.Treeview")
        self.views.pack(fill="x", padx=8)
        for key, label in SMART_VIEWS:
            self.views.insert("", "end", iid=key, text="  " + label, image=icon(self,key))
        self.views.bind("<<TreeviewSelect>>", self._on_view_select)
        head = ttk.Frame(self, style="Sidebar.TFrame")
        head.pack(fill="x", padx=14, pady=(16, 4))
        ttk.Label(head, text="PROIECTE ȘI TASKURI", style="Sidebar.TLabel").pack(side="left")
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(wrap, show="tree", selectmode="browse")
        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vbar.set)
        hbar=ttk.Scrollbar(wrap,orient="horizontal",command=self.tree.xview)
        self.tree.configure(xscrollcommand=hbar.set)
        self.tree.column("#0",width=300,minwidth=180,stretch=True)
        wrap.columnconfigure(0,weight=1)
        wrap.rowconfigure(0,weight=1)
        self.tree.grid(row=0,column=0,sticky="nsew")
        vbar.grid(row=0,column=1,sticky="ns")
        hbar.grid(row=1,column=0,sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._on_context)
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.tag_configure("closed", foreground=muted_color(self))
        self.tree.tag_configure("archived", foreground=muted_color(self))
        self._first_fill = True

    # ---- population -------------------------------------------------
    def refresh(self) -> None:
        ws, q = self.app.ws, self.app.q
        self._suppress = True
        try:
            open_ids = {i for i in self._all_items() if self.tree.item(i, "open")}
            selected = self.tree.selection()
            self.tree.delete(*self.tree.get_children())
            cmap = ws.children_map()
            show_archived = self.app.config.show_archived

            def add(parent_iid: str, n: Node) -> None:
                archived = q.is_archived(n)
                if archived and not show_archived:
                    return
                if not self.app.config.show_completed and n.status in CLOSED_STATUSES:
                    # Keep a closed ancestor as structure if it has visible open descendants.
                    if not any(ws.nodes[k].status not in CLOSED_STATUSES for k in ws.subtree_ids(n.id, include_self=False)):
                        return
                tags = []
                if n.status in CLOSED_STATUSES:
                    tags.append("closed")
                if archived:
                    tags.append("archived")
                kids = cmap.get(n.id, [])
                is_open = n.id in open_ids or (self._first_fill and parent_iid == "")
                self.tree.insert(parent_iid, "end", iid=n.id, text="  " + n.title + " · " + node_label(n), image=node_icon(self,n),
                                 open=is_open, tags=tags)
                for c in kids:
                    add(n.id, c)

            for n in cmap.get(None, []):
                add("", n)
            self._first_fill = False
            keep = [s for s in selected if self.tree.exists(s)]
            if keep:
                self.tree.selection_set(keep)
        finally:
            self._suppress = False
        self._update_counts()

    def _all_items(self, parent: str = "") -> list[str]:
        out: list[str] = []
        for c in self.tree.get_children(parent):
            out.append(c)
            out.extend(self._all_items(c))
        return out

    def _update_counts(self) -> None:
        q = self.app.q
        counts = {
            "today": len(q.view_today()), "inbox": len(q.view_inbox()), "waiting": len(q.view_waiting()),
            "overdue": len(q.view_overdue()), "calendar": None, "archive": len(q.view_archive()),
        }
        for key, label in SMART_VIEWS:
            n = counts[key]
            self.views.item(key, text="  " + (f"{label}  ({n})" if n else label))

    # ---- selection --------------------------------------------------
    def select_node(self, node_id: str) -> None:
        if not self.tree.exists(node_id):
            return
        self._suppress = True
        try:
            self.views.selection_remove(self.views.selection())
            p = self.tree.parent(node_id)
            while p:
                self.tree.item(p, open=True)
                p = self.tree.parent(p)
            self.tree.selection_set(node_id)
            self.tree.see(node_id)
        finally:
            self._suppress = False

    def select_view(self, key: str) -> None:
        self._suppress = True
        try:
            self.tree.selection_remove(self.tree.selection())
            self.views.selection_set(key)
        finally:
            self._suppress = False

    def clear_selection(self) -> None:
        self._suppress = True
        try:
            self.tree.selection_remove(self.tree.selection())
            self.views.selection_remove(self.views.selection())
        finally:
            self._suppress = False

    def selected_tree_id(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _on_view_select(self, _e=None) -> None:
        if self._suppress:
            return
        sel = self.views.selection()
        if sel and sel[0] != self.app.current_view:
            self.app.show_view(sel[0])

    def _on_tree_select(self, _e=None) -> None:
        if self._suppress:
            return
        sel = self.tree.selection()
        if sel and sel[0] != self.app.current_scope:
            self.views.selection_remove(self.views.selection())
            self.app.show_node_scope(sel[0])

    def _on_double(self, _e=None) -> None:
        self.app.focus_inspector()

    def _on_context(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self._suppress = True
            self.tree.selection_set(iid)
            self._suppress = False
            self.app.show_node_scope(iid)
        self.app.popup_context_menu(event.x_root, event.y_root, iid or None)
