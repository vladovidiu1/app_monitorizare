"""Tabul „Subtask-uri”: copii directi si checklist."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.labels import STATUS_LABELS
from ..domain.models import CLOSED_STATUSES, Kind, Node, Status
from .common import confirm, make_tree
from .formats import format_date
from .inspector import InspectorTab
from .status_visuals import node_icon
from .design import C

if TYPE_CHECKING:
    from .app import FocusDeskApp


class SubtasksTab(InspectorTab):
    title = "Subtaskuri"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        add = ttk.Frame(self)
        add.pack(fill="x", padx=8, pady=(8, 4))
        self.add_var = tk.StringVar()
        self.add_entry = ttk.Entry(add, textvariable=self.add_var)
        self.add_entry.pack(side="left", fill="x", expand=True)
        self.add_entry.bind("<Return>", lambda _e: self._quick_add())
        self.add_btn = ttk.Button(add, text="Adaugă subtask", command=self._quick_add)
        self.add_btn.pack(side="left", padx=(6, 0))
        self.tv, frame = make_tree(self, [("title", "Titlu", 220), ("status", "Status", 90), ("due", "Termen", 90)],
                                   height=7)
        frame.pack(fill="both", expand=True, padx=8)
        self.tv.configure(show="tree headings")
        self.tv.column("#0", width=32, minwidth=32, stretch=False)
        self.tv.tag_configure("closed", foreground=C.muted)
        self.tv.bind("<Double-1>", self._open)
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=4)
        for text, cmd in (("▲", lambda: self._reorder(-1)), ("▼", lambda: self._reorder(1)),
                          ("Finalizează / redeschide", self._toggle_done), ("Deschide", self._open),
                          ("În coș", self._trash)):
            ttk.Button(btns, text=text, command=cmd, width=3 if len(text) == 1 else None).pack(side="left", padx=2)

        self.check_frame = ttk.LabelFrame(self, text="Checklist funcțional al taskului (separat de căsuțele Markdown)")
        self.check_frame.pack(fill="x", padx=8, pady=(6, 8))
        self.check_tv = ttk.Treeview(self.check_frame, show="tree", height=4, selectmode="browse")
        self.check_tv.pack(fill="x", padx=6, pady=(6, 2))
        self.check_tv.bind("<Double-1>", lambda _e: self._toggle_check())
        self.check_tv.bind("<space>", lambda _e: self._toggle_check())
        crow = ttk.Frame(self.check_frame)
        crow.pack(fill="x", padx=6, pady=(0, 6))
        self.check_var = tk.StringVar()
        ce = ttk.Entry(crow, textvariable=self.check_var)
        ce.pack(side="left", fill="x", expand=True)
        ce.bind("<Return>", lambda _e: self._add_check())
        ttk.Button(crow, text="Adaugă", command=self._add_check).pack(side="left", padx=4)
        ttk.Button(crow, text="Elimină", command=self._remove_check).pack(side="left")

    def load(self, node: Node) -> None:
        super().load(node)
        ws = self.app.ws
        self.tv.delete(*self.tv.get_children())
        for c in ws.children(node.id):
            self.tv.insert("", "end", iid=c.id, image=node_icon(self,c), tags=("closed",) if c.status in CLOSED_STATUSES else (), values=(
                c.title, STATUS_LABELS.get(c.status, "") if c.status else "",
                format_date(self.app.q.due_day(c))))
        if node.kind == Kind.TASK:
            self.check_frame.pack(fill="x", padx=8, pady=(6, 8))
            self.check_tv.delete(*self.check_tv.get_children())
            for i, item in enumerate(node.checklist):
                self.check_tv.insert("", "end", iid=str(i), text=f"{'☑' if item.done else '☐'}  {item.text}")
        else:
            self.check_frame.pack_forget()
        state = "disabled" if ws.read_only else "normal"
        self.add_entry.configure(state=state)
        self.add_btn.configure(state=state)

    def _selected(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def _quick_add(self) -> None:
        title = self.add_var.get().strip()
        if not title or not self.node_id:
            return
        if self.app.run_write(lambda: self.app.ws.create_node(Kind.TASK, title, self.node_id), refresh=True):
            self.add_var.set("")
            self.add_entry.focus_set()

    def _reorder(self, direction: int) -> None:
        sel = self._selected()
        if sel:
            self.app.run_write(lambda: self.app.ws.reorder(sel, direction), refresh=True)
            if self.tv.exists(sel):
                self.tv.selection_set(sel)

    def _toggle_done(self) -> None:
        sel = self._selected()
        if not sel:
            return
        node = self.app.ws.get(sel)
        new = Status.TODO if node.status in CLOSED_STATUSES else Status.DONE
        self.app.run_write(lambda: self.app.ws.update_node(sel, status=new), refresh=True)

    def _open(self, _e=None) -> None:
        sel = self._selected()
        if sel:
            self.app.select_node(sel, reveal=True)

    def _trash(self) -> None:
        sel = self._selected()
        if sel and confirm(self, "Muți elementul selectat (și subtask-urile lui) în coș?"):
            self.app.run_write(lambda: self.app.ws.trash(sel), refresh=True)

    # ---- checklist --------------------------------------------------
    def _checklist_items(self) -> list[tuple[str, bool]]:
        node = self.app.ws.get(self.node_id)  # type: ignore[arg-type]
        return [(c.text, c.done) for c in node.checklist]

    def _toggle_check(self) -> None:
        sel = self.check_tv.selection()
        if not sel or not self.node_id:
            return
        items = self._checklist_items()
        i = int(sel[0])
        items[i] = (items[i][0], not items[i][1])
        self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True)

    def _add_check(self) -> None:
        text = self.check_var.get().strip()
        if not text or not self.node_id:
            return
        items = [*self._checklist_items(), (text, False)]
        if self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True):
            self.check_var.set("")

    def _remove_check(self) -> None:
        sel = self.check_tv.selection()
        if not sel or not self.node_id:
            return
        items = self._checklist_items()
        del items[int(sel[0])]
        self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True)
