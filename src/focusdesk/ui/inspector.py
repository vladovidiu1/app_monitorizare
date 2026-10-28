"""Inspectorul nodului selectat (taburi)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.labels import KIND_LABELS, PRIORITY_LABELS
from .formats import format_date
from ..domain.models import CLOSED_STATUSES, Kind
from .status_visuals import node_icon, node_label
from .design import C
from .common import SessionButton
from ..domain.models import Node

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
        self.status_lbl = ttk.Label(self, text="", compound="left", style="Muted.TLabel")
        self.status_lbl.pack(fill="x", padx=14, pady=(4, 2))
        self.next_lbl = ttk.Label(self, text="", style="Muted.TLabel", wraplength=380)
        self.next_lbl.pack(fill="x",padx=14,pady=2)
        self.actions = ttk.Frame(self)
        self.actions.pack(fill="x",padx=10,pady=4)
        self.start_btn = SessionButton(self.actions,app,lambda:self.node_id)
        self.start_btn.pack(side="left")
        self.reopen_btn = ttk.Button(self.actions, text="Finalizează", command=app.toggle_done_selected)
        self.reopen_btn.pack(side="left",padx=4)
        more = ttk.Menubutton(self.actions,text="Mai multe")
        more.pack(side="left")
        menu = tk.Menu(more,tearoff=False)
        for label,command in (("Compune e-mail…",app.compose_mail),("Mută / asociază proiect…",app.move_selected),
                              ("Arhivează / restaurează",app.toggle_archive_selected),("Deschide folderul",lambda:app.open_node_folder(self.node_id))):
            menu.add_command(label=label,command=command)
        self.more_menu=menu
        menu.add_command(label="Adaugă cerință nouă…",command=lambda:app.add_followup(self.node_id))
        menu.add_command(label="Redeschide cu motiv…",command=lambda:app.reopen_with_reason(self.node_id))
        more.configure(menu=menu)
        self.space_btn = ttk.Button(self,text="Deschide spațiul de lucru",command=lambda:app.open_task_space(self.node_id))
        self.nb = ttk.Notebook(self, style="Inspector.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        from .meetings import MeetingLinks
        self.meeting_links=MeetingLinks(self,app)
        from .followups import FollowupContext
        self.followup_context=FollowupContext(self,app)
        self.bind("<Configure>", lambda e: (self.head_lbl.configure(wraplength=max(160,e.width-32)), self.path_lbl.configure(wraplength=max(160,e.width-32))))
        self._pending_tabs = {}
        self.tabs: list[InspectorTab] = []
        self.nb.bind('<<NotebookTabChanged>>', self._remember_tab)
        self.empty = ttk.Label(self, text="Selectează un folder, proiect sau task\npentru a vedea detaliile.",
                               style="Muted.TLabel", justify="center")

    def add_tab(self, tab: InspectorTab) -> None:
        self.tabs.append(tab)
        self.nb.add(tab, text=tab.title)

    def _remember_tab(self,event=None):
        current = self.nb.select()
        for tab in self.tabs:
            if str(tab) == current: self._load_pending(tab)
        if current and self.node_id is not None:
            self.app.config.inspector_tab = self.nb.tab(current,'text')

    def tab_by_title(self, title: str) -> InspectorTab | None:
        title = {'Jurnal':'Activitate','Subtask-uri':'Subtaskuri'}.get(title,title)
        tab = next((t for t in self.tabs if t.title == title), None)
        if tab is not None: self._load_pending(tab)
        return tab

    def _load_pending(self, tab):
        nid = self._pending_tabs.pop(tab,None)
        if nid is not None and self.app.ws and nid in self.app.ws.nodes:
            if tab.node_id == nid and (tab.is_dirty() or getattr(tab,'expanded',None) is not None): return
            tab.load(self.app.ws.get(nid))

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
            self.status_lbl.configure(text="", image="")
            self.actions.pack_forget()
            self.space_btn.pack_forget()
            self.next_lbl.configure(text="")
            self.meeting_links.pack_forget()
            self.followup_context.pack_forget()
            self.nb.pack_forget()
            self.empty.place(relx=0.5, rely=0.4, anchor="center")
            return
        self.empty.place_forget()
        if not self.nb.winfo_ismapped():
            self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        node = self.app.ws.get(node_id)
        self.meeting_links.load(node,self.nb)
        self.head_lbl.configure(text=node.title, foreground=C.muted if node.status in CLOSED_STATUSES else C.text)
        summary = node_label(node)
        if node.kind == Kind.TASK:
            summary += " · " + PRIORITY_LABELS.get(node.priority, "")
            day = self.app.q.due_day(node)
            summary += " · " + (format_date(day) if day else "Fără termen")
        self.status_lbl.configure(text=summary, image=node_icon(self,node))
        self.reopen_btn.state(["disabled"] if self.app.ws.read_only else ["!disabled"])
        self.more_menu.entryconfigure('Adaugă cerință nouă…',state='normal' if node.kind==Kind.TASK and not self.app.ws.read_only else 'disabled')
        self.more_menu.entryconfigure('Redeschide cu motiv…',state='normal' if node.kind==Kind.TASK and node.status in CLOSED_STATUSES and not self.app.ws.read_only else 'disabled')
        if node.kind == Kind.TASK:
            self.followup_context.pack(fill='x',padx=6,before=self.nb)
            self.followup_context.load(node)
            self.space_btn.pack(fill="x",padx=10,pady=(0,4),before=self.nb)
            self.actions.pack(fill="x",padx=10,pady=4,before=self.nb)
            self.reopen_btn.configure(text="Redeschide taskul" if node.status in CLOSED_STATUSES else "Finalizează")
            self.next_lbl.configure(text="Următorul pas: " + (node.next_action or "Completează în Detalii"))
            self.start_btn.update_state()
        else:
            self.followup_context.pack_forget()
            self.space_btn.pack_forget()
            self.actions.pack_forget()
            self.next_lbl.configure(text="")
        anc = " › ".join(a.title for a in self.app.ws.ancestors(node_id))
        self.path_lbl.configure(text=f"{KIND_LABELS[node.kind]}  ·  {anc or 'Rădăcina workspace-ului'}")
        current = self.nb.select()
        for tab in self.tabs:
            state = "normal" if tab.applies_to(node) else "hidden"
            self.nb.tab(tab, state=state)
            if state == "normal" and not (keep_dirty and same and (tab.is_dirty() or getattr(tab, "expanded", None) is not None)):
                self._pending_tabs[tab] = node.id
                if tab.title in ('Subtaskuri','Activitate'):
                    tab.node_id = node.id  # Bind shared draft ownership without reading ledger/files.
                if tab.title == 'Detalii' or str(tab) == current:
                    self._load_pending(tab)
        if current and self.nb.tab(current, "state") == "hidden":
            self.nb.select(self.tabs[0])
        if not same:
            preferred = self.tab_by_title(self.app.config.inspector_tab)
            if preferred is not None and self.nb.tab(preferred, "state") != "hidden":
                self.nb.select(preferred)

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
