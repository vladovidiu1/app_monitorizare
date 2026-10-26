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
from .design import C, icon

if TYPE_CHECKING:
    from .app import FocusDeskApp


class SubtasksTab(InspectorTab):
    title = "Subtaskuri"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", *, drafts_from=None, on_open=None, checklist_first=False) -> None:
        super().__init__(parent, app)
        add = ttk.Frame(self)
        add.pack(fill="x", padx=8, pady=(8, 4))
        self.on_open = on_open
        self.add_var = drafts_from.add_var if drafts_from else tk.StringVar()
        self.add_entry = ttk.Entry(add, textvariable=self.add_var)
        self.add_entry.pack(side="left", fill="x", expand=True)
        self.add_entry.bind("<Return>", lambda _e: self._quick_add())
        self.add_btn = ttk.Button(add, text="Adaugă subtask", command=self._quick_add)
        self.add_btn.pack(side="left", padx=(6, 0))
        self.tv, frame = make_tree(self, [("title", "Titlu", 220), ("status", "Status", 90), ("progress", "Progres", 75), ("due", "Termen", 90)],
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
        self.check_tv.tag_configure("checked",foreground=C.muted)
        self.check_tv.pack(fill="x", padx=6, pady=(6, 2))
        self.check_tv.bind("<Double-1>", lambda _e: self._toggle_check())
        self.check_tv.bind("<space>", lambda _e: self._toggle_check())
        crow = ttk.Frame(self.check_frame)
        crow.pack(fill="x", padx=6, pady=(0, 6))
        self.check_var = drafts_from.check_var if drafts_from else tk.StringVar()
        ce = ttk.Entry(crow, textvariable=self.check_var)
        ce.pack(side="left", fill="x", expand=True)
        ce.bind("<Return>", lambda _e: self._add_check())
        ttk.Button(crow, text="Adaugă", command=self._add_check).pack(side="left", padx=4)
        ttk.Button(crow, text="Elimină", command=self._remove_check).pack(side="left")

        if checklist_first:
            self.check_frame.pack(before=add, fill="x", padx=8, pady=(6,8))
            self.tv.configure(height=3,style="Dense.Treeview")

    def is_dirty(self):
        return bool(self.add_var.get().strip() or self.check_var.get().strip())

    def save(self):
        if self.add_var.get().strip(): self._quick_add()
        if self.check_var.get().strip(): self._add_check()
        return not self.is_dirty()

    def revert(self):
        self.add_var.set('')
        self.check_var.set('')
        super().revert()

    def load(self, node: Node) -> None:
        same = self.node_id == node.id
        selected, scroll = self.tv.selection(), self.tv.yview()[0]
        checks_selected, check_scroll = self.check_tv.selection(), self.check_tv.yview()[0]
        super().load(node)
        ws = self.app.ws
        self.tv.delete(*self.tv.get_children())
        progress = self.app.q.progress_map()
        for c in ws.children(node.id):
            self.tv.insert("", "end", iid=c.id, image=node_icon(self,c), tags=("closed",) if c.status in CLOSED_STATUSES else (), values=(
                c.title, STATUS_LABELS.get(c.status, "") if c.status else "",
                f"{progress[c.id].done}/{progress[c.id].leaf_total}" if progress[c.id].leaf_total else "—",
                format_date(self.app.q.due_day(c))))
        if same:
            self.tv.selection_set([i for i in selected if self.tv.exists(i)])
            self.tv.yview_moveto(scroll)
        if node.kind == Kind.TASK:
            self.check_frame.pack(fill="x", padx=8, pady=(6, 8))
            self.check_tv.delete(*self.check_tv.get_children())
            for i, item in enumerate(node.checklist):
                self.check_tv.insert("", "end", iid=str(i), text=item.text, image=icon(self,"status-done" if item.done else "status-todo"), tags=("checked",) if item.done else ())
        else:
            self.check_frame.pack_forget()
        if same:
            self.check_tv.selection_set([i for i in checks_selected if self.check_tv.exists(i)])
            self.check_tv.yview_moveto(check_scroll)
        state = "disabled" if ws.read_only else "normal"
        self.add_entry.configure(state=state)
        self.add_btn.configure(state=state)

    def _selected(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def _quick_add(self) -> None:
        if self.app.ws.read_only: return
        title = self.add_var.get().strip()
        if not title or not self.node_id:
            return
        if self.app.run_write(lambda: self.app.ws.create_node(Kind.TASK, title, self.node_id), refresh=True):
            self.add_var.set("")
            self.load(self.app.ws.get(self.node_id))
            self.add_entry.focus_set()

    def _reorder(self, direction: int) -> None:
        if self.app.ws.read_only: return
        sel = self._selected()
        if sel:
            self.app.run_write(lambda: self.app.ws.reorder(sel, direction), refresh=True)
            if self.tv.exists(sel):
                self.tv.selection_set(sel)

    def _toggle_done(self) -> None:
        if self.app.ws.read_only: return
        sel = self._selected()
        if not sel:
            return
        node = self.app.ws.get(sel)
        new = Status.TODO if node.status in CLOSED_STATUSES else Status.DONE
        self.app.run_write(lambda: self.app.ws.update_node(sel, status=new), refresh=True)

    def _open(self, _e=None) -> None:
        sel = self._selected()
        if sel:
            if self.on_open: self.on_open(sel)
            else: self.app.select_node(sel, reveal=True)

    def _trash(self) -> None:
        if self.app.ws.read_only: return
        sel = self._selected()
        if sel and confirm(self, "Muți elementul selectat (și subtask-urile lui) în coș?"):
            self.app.run_write(lambda: self.app.ws.trash(sel), refresh=True)

    # ---- checklist --------------------------------------------------
    def _checklist_items(self) -> list[tuple[str, bool]]:
        node = self.app.ws.get(self.node_id)  # type: ignore[arg-type]
        return [(c.text, c.done) for c in node.checklist]

    def _toggle_check(self) -> None:
        if self.app.ws.read_only: return
        sel = self.check_tv.selection()
        if not sel or not self.node_id:
            return
        items = self._checklist_items()
        i = int(sel[0])
        items[i] = (items[i][0], not items[i][1])
        self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True)

    def _add_check(self) -> None:
        if self.app.ws.read_only: return
        text = self.check_var.get().strip()
        if not text or not self.node_id:
            return
        items = [*self._checklist_items(), (text, False)]
        if self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True):
            self.check_var.set("")
            self.load(self.app.ws.get(self.node_id))

    def _remove_check(self) -> None:
        if self.app.ws.read_only: return
        sel = self.check_tv.selection()
        if not sel or not self.node_id:
            return
        items = self._checklist_items()
        del items[int(sel[0])]
        self.app.run_write(lambda: self.app.ws.toggle_checklist(self.node_id, items), refresh=True)
