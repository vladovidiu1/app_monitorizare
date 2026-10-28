"""Panoul din stanga: vizualizari inteligente si arborele de noduri."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.models import CLOSED_STATUSES, Kind, Node
from .common import KIND_GLYPH, STATUS_GLYPH, muted_color
from .design import C, icon, button
from .status_visuals import node_icon, node_label

if TYPE_CHECKING:
    from .app import FocusDeskApp

SMART_VIEWS = [
    ("today", "Astăzi"), ("tasks", "Proiecte și taskuri"),
    ("calendar", "Calendar"), ("activity", "Activitate"),
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

        ttk.Label(self, text="NAVIGARE", style="Sidebar.TLabel").pack(anchor="w", padx=14, pady=(14, 4))
        self.views = ttk.Treeview(self, show="tree", selectmode="browse", height=len(SMART_VIEWS), style="Nav.Treeview")
        self.views.pack(fill="x", padx=8)
        for key, label in SMART_VIEWS:
            self.views.insert("", "end", iid=key, text="  " + label, image=icon(self,{"tasks":"project","activity":"chart"}.get(key,key)))
        self.views.bind("<<TreeviewSelect>>", self._on_view_select)
        head = ttk.Frame(self, style="Sidebar.TFrame")
        head.pack(fill="x", padx=14, pady=(16, 4))
        ttk.Label(head, text="PROIECTE ȘI CATEGORII", style="Sidebar.TLabel").pack(side="left")
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.hierarchy_head = head
        self.hierarchy_wrap = wrap
        secondary = ttk.Frame(self)
        secondary.pack(side="bottom",fill="x",padx=10,pady=8)
        ttk.Button(secondary,text="Arhivă",image=icon(self,"archive"),compound="left",command=lambda:app.show_view("archive")).pack(fill="x")
        ttk.Button(secondary,text="Setări",image=icon(self,"settings"),compound="left",command=app.open_settings).pack(fill="x",pady=2)
        data_button = ttk.Menubutton(secondary,text="Date și backup")
        data_button.pack(fill="x",pady=2)
        data_menu = tk.Menu(data_button,tearoff=False)
        for label,command in (("Coș…",app.open_trash),("Backup metadate",lambda:app.backup_now(False)),
                              ("Backup complet",lambda:app.backup_now(True)),("Restaurează backup…",app.restore_backup),
                              ("Verifică integritatea…",app.show_issues)):
            data_menu.add_command(label=label,command=command)
        data_button.configure(menu=data_menu)
        self.tree = ttk.Treeview(wrap, show="tree", selectmode="browse", style="Dense.Treeview")
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
        self.views.tag_configure("section",background=C.selected,foreground=C.accent)
        self._first_fill = True

    # ---- population -------------------------------------------------
    def refresh(self) -> None:
        from .tree_rows import sync_rows
        ws, q = self.app.ws, self.app.q
        self.show_hierarchy(self.app.current_view.startswith(("tasks", "tree:", "search:")) or self.app.current_view == "archive")
        self._suppress = True
        try:
            scroll = self.tree.yview()[0]
            horizontal = self.tree.xview()[0]
            open_ids = {i for i in self._all_items() if self.tree.item(i, "open")}
            selected = self.tree.selection()
            rows = []
            visible = ws.active_context_ids() if not self.app.config.show_completed else None
            cmap = ws.active_children_map() if visible is not None else ws.children_map()
            show_archived = self.app.config.show_archived

            def add(parent_iid: str, n: Node) -> None:
                archived = q.is_archived(n)
                if archived and not show_archived:
                    return
                if visible is not None and n.id not in visible:
                    return
                tags = []
                if n.status in CLOSED_STATUSES:
                    tags.append("closed")
                if archived:
                    tags.append("archived")
                kids = cmap.get(n.id, [])
                is_open = n.id in open_ids or (self._first_fill and parent_iid == "")
                rows.append((parent_iid,n.id,dict(text="  " + n.title + " · " + node_label(n), image=(str(node_icon(self,n)),),
                                 open=is_open,tags=tags)))
                for c in kids:
                    add(n.id, c)

            for n in cmap.get(None, []):
                add("", n)
            sync_rows(self.tree,rows)
            self.tree.yview_moveto(scroll)
            self.tree.xview_moveto(horizontal)
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

    def show_hierarchy(self, visible):
        self.views.item("tasks", tags=("section",) if visible else ())
        if visible:
            self.hierarchy_head.pack(fill="x",padx=14,pady=(16,4))
            self.hierarchy_wrap.pack(fill="both",expand=True,padx=8,pady=(0,8))
        else:
            self.hierarchy_head.pack_forget()
            self.hierarchy_wrap.pack_forget()

    def _update_counts(self):
        for key,label in SMART_VIEWS:
            self.views.item(key,text="  "+label)

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
            if self.views.exists(key):
                self.views.selection_set(key)
            else:
                self.views.selection_remove(self.views.selection())
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
        if not self.tree.winfo_ismapped():
            return
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
