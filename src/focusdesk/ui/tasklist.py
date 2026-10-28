"""Lista de task-uri din zona centrala: arbore ierarhic (proiect > task > subtask > ...) sau lista plata, cu filtre."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

import ttkbootstrap as tb

from ..domain.labels import (
    PRIORITY_FROM_LABEL, PRIORITY_LABELS, STATUS_FROM_LABEL, STATUS_LABELS, VISIBLE_STATUSES, format_minutes, format_worked,
)
from ..domain.models import CLOSED_STATUSES, PRIORITY_ORDER, Kind, Node, Priority, Status
from ..services.queries import Progress
from .common import BASE_SIZE, FONT_FAMILY, SessionButton, error_color, muted_color
from .formats import format_date
from .status_visuals import node_icon
from .tree_rows import sync_rows

if TYPE_CHECKING:
    from .app import FocusDeskApp

ALL = "Toate"
DUE_FILTERS = {"Orice termen": None, "Restante": "overdue", "Azi": "today", "Următoarele 7 zile": "week",
               "Fără termen": "none"}
COLUMNS = [("status", "Status", 120), ("priority", "Prioritate", 76), ("due", "Termen", 84),
           ("progress", "Progres", 68), ("remaining", "Timp rămas", 150), ("worked", "Lucrat salvat", 100),
           ("loc", "Locație", 150)]
TREE_COLUMNS = ("status", "priority", "due", "progress", "remaining", "worked")


class TaskList(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent)
        self.app = app
        self._source: Callable[[], list[Node]] = lambda: []
        self._sort_key = "default"
        self._sort_rev = False
        self._shown: list[Node] = []
        self._suppress = False
        self.show_closed_default = False
        self.scope_id: str | None = None  # setat in vizualizarea de arbore: afiseaza ierarhia, nu lista plata
        self._source_key: object = None
        self._expand_all = True
        self._force_open: set[str] = set()
        self._cmap: dict[str | None, list[Node]] = {}
        self._prog: dict[str, Progress] = {}
        self._worked: dict[str, int] = {}
        self.empty_hint = ""

        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(14, 0))
        self.title_lbl = ttk.Label(top, text="", style="Title.TLabel")
        self.title_lbl.pack(side="left")
        self.count_lbl = ttk.Label(top, text="", style="Muted.TLabel")
        self.count_lbl.pack(side="left", padx=10, pady=(8, 0))
        self.crumb = ttk.Label(self, text="", style="Crumb.TLabel")
        self.crumb.pack(fill="x", padx=16, pady=(0, 6))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=16, pady=(0, 6))
        self.status_var = tk.StringVar(value="Orice status")
        self.prio_var = tk.StringVar(value="Orice prioritate")
        self.due_var = tk.StringVar(value="Orice termen")
        self.proj_var = tk.StringVar(value="Toate proiectele")
        self.text_var = tk.StringVar()
        self.requester_var = tk.StringVar()
        self.closed_var = tk.BooleanVar(value=False)
        self.status_box = self._combo(bar, self.status_var, ["Orice status"] + [STATUS_LABELS[s] for s in VISIBLE_STATUSES], 14)
        self.prio_box = self._combo(bar, self.prio_var, ["Orice prioritate"] + [PRIORITY_LABELS[p] for p in Priority], 14)
        self.due_box = self._combo(bar, self.due_var, list(DUE_FILTERS), 15)
        project_row = ttk.Frame(self)
        project_row.pack(fill="x", padx=16, pady=(0,6))
        self.proj_box = self._combo(project_row, self.proj_var, ["Toate proiectele"], 18)
        people_row = ttk.Frame(self)
        people_row.pack(fill="x", padx=16, pady=(0, 6))
        ttk.Label(people_row, text="De la").pack(side="left", padx=(0, 6))
        self.requester_entry = ttk.Entry(people_row, textvariable=self.requester_var, width=10)
        self.requester_entry.pack(side="left", fill="x", expand=True)
        self.requester_var.trace_add('write', lambda *_: self._debounced_refresh())
        bar2 = ttk.Frame(self)

        ent = ttk.Entry(project_row, textvariable=self.text_var,width=12)
        ent.pack(side="left",fill="x",expand=True)
        bar2.columnconfigure(0,weight=1)
        tb.Checkbutton(people_row, text="Închise", variable=self.closed_var, command=self._toggle_closed,
                       bootstyle="round-toggle").pack(side="left",padx=6)
        tb.Button(people_row, text="Reset", command=self.reset_filters, bootstyle="secondary-outline"
                  ).pack(side="left")
        self.text_var.trace_add("write", lambda *_: self._debounced_refresh())
        self._after_id = None
        for box in (self.status_box,self.prio_box,self.due_box,self.proj_box):
            box.bind('<<ComboboxSelected>>',self._filter_changed)
        from .common import Tooltip
        Tooltip(ent,"Caută în lista curentă")
        Tooltip(self.requester_entry,"Solicitant: nume, cod sau adresă")

        act_bar = ttk.Frame(self)
        act_bar.pack(fill="x", padx=16, pady=(0, 8))
        self.session_btn = SessionButton(act_bar, app, self.selected_id)
        self.session_btn.pack(side="left")
        self.act_bar = act_bar
        self.move_btn = ttk.Button(act_bar, text="Mută / proiect…", command=app.move_selected)
        self.move_btn.pack(side="left", padx=6)
        quick = ttk.Frame(self)
        quick.pack(fill="x", padx=16, pady=(0,6))
        for label, code in (("Toate", "all"), ("În așteptare", "waiting"), ("Restante", "overdue"), ("Finalizate", "done")):
            ttk.Button(quick, text=label, command=lambda c=code: app.quick_tasks(c)).pack(side="left", padx=(0,4))

        self.add_bar = ttk.Frame(self)  # vizibila doar in vizualizarea de arbore, deasupra listei
        self._build_add_bar(self.add_bar)

        self.list_wrap = ttk.Frame(self)
        self.list_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.tv = ttk.Treeview(self.list_wrap, style="Dense.Treeview", columns=[c[0] for c in COLUMNS], show="tree headings",
                               selectmode="browse")
        self.tv.heading("#0", text="Titlu", anchor="w", command=lambda: self._sort_by("title"))
        self.tv.column("#0", width=260, minwidth=240, anchor="w", stretch=True)
        for cid, text, width in COLUMNS:
            self.tv.heading(cid, text=text, anchor="w", command=lambda c=cid: self._sort_by(c))
            self.tv.column(cid, width=width, minwidth=50, anchor="w", stretch=False)
        vbar = ttk.Scrollbar(self.list_wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=vbar.set)
        self.hbar = ttk.Scrollbar(self.list_wrap, orient="horizontal", command=self.tv.xview)
        self.tv.configure(xscrollcommand=self.hbar.set)
        self.list_wrap.columnconfigure(0,weight=1)
        self.list_wrap.rowconfigure(0,weight=1)
        self.tv.grid(row=0,column=0,sticky="nsew")
        vbar.grid(row=0,column=1,sticky="ns")
        self.hbar.grid(row=1,column=0,sticky="ew")
        self.configure_tags()
        self.tv.bind("<<TreeviewSelect>>", self._on_select)
        self.tv.bind("<Double-1>", self._on_double)
        self.tv.bind("<Button-3>", self._on_context)
        self.tv.bind("<Return>", lambda _e: self.app.focus_inspector())
        self.tv.bind("<Insert>", lambda _e: self._focus_add())
        self.empty_lbl = ttk.Label(self, text="", style="Muted.TLabel")

    # ---- construction helpers ---------------------------------------
    @staticmethod
    def _combo(parent: tk.Misc, var: tk.StringVar, values: list[str], width: int) -> ttk.Combobox:
        box = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=width)
        box.pack(side="left", padx=(0, 8))
        return box

    def _build_add_bar(self, bar: ttk.Frame) -> None:
        self.target_lbl = ttk.Label(bar, text="", style="Muted.TLabel")
        self.target_lbl.pack(anchor="w", pady=(0, 3))
        row = ttk.Frame(bar)
        row.pack(fill="x")
        self.add_var = tk.StringVar()
        self.add_entry = ttk.Entry(row, textvariable=self.add_var)
        self.add_entry.pack(side="left", fill="x", expand=True)
        self.add_entry.bind("<Return>", lambda _e: self._quick_add(under_selection=True))
        self.add_btn = tb.Button(row, text="+ Adaugă", bootstyle="primary",
                                  command=lambda: self._quick_add(under_selection=True))
        self.add_btn.pack(side="left", padx=(8, 0))
        self.add_top_btn = tb.Button(row, text="Aici", bootstyle="secondary-outline",
                                      command=lambda: self._quick_add(under_selection=False))
        self.add_top_btn.pack(side="left", padx=(6, 0))

    def configure_tags(self) -> None:
        self.tv.tag_configure("overdue", foreground=error_color(self))
        self.tv.tag_configure("closed", foreground=muted_color(self))
        self.tv.tag_configure("context", foreground=muted_color(self))
        self.tv.tag_configure("group", font=(self._root()._focusdesk_family, BASE_SIZE, "bold"))

    # ---- configuration ----------------------------------------------
    def set_source(self, title: str, loader: Callable[[], list[Node]], crumb: str = "",
                   show_closed: bool = False, empty_hint: str = "Nu există task-uri aici.",
                   scope_id: str | None = None) -> None:
        self._source = loader
        key = (title, scope_id)
        self._expand_all = key != self._source_key
        changed_source = key != self._source_key
        self._source_key = key
        self.scope_id = scope_id
        self.title_lbl.configure(text=title)
        self.crumb.configure(text=crumb)
        self.show_closed_default = show_closed
        if changed_source:
            self.closed_var.set(show_closed)
        self.empty_hint = empty_hint
        if scope_id is not None:
            self.tv.configure(displaycolumns=TREE_COLUMNS)
            self.add_bar.pack(fill="x", padx=16, pady=(0, 8), before=self.list_wrap)
        else:
            self.tv.configure(displaycolumns=[c[0] for c in COLUMNS])
            self.add_bar.pack(fill="x", padx=16, pady=(0,8), before=self.list_wrap)
        self.refresh()

    def _filter_changed(self,event=None):
        if STATUS_FROM_LABEL.get(self.status_var.get()) in CLOSED_STATUSES:
            self.closed_var.set(True)
        self.refresh()

    def _toggle_closed(self):
        if not self.closed_var.get() and STATUS_FROM_LABEL.get(self.status_var.get()) in CLOSED_STATUSES:
            self.status_var.set('Orice status')
        self.refresh()

    def reset_filters(self) -> None:
        self.status_var.set("Orice status")
        self.prio_var.set("Orice prioritate")
        self.due_var.set("Orice termen")
        self.proj_var.set("Toate proiectele")
        self.requester_var.set("")
        self.text_var.set("")
        self.closed_var.set(self.show_closed_default)
        self.refresh()

    def _debounced_refresh(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(200, self.refresh)

    # ---- data -------------------------------------------------------
    def _project_options(self) -> dict[str, str]:
        ws = self.app.ws
        projects = [ws.nodes[nid] for nid in ws.repo.project_ids]
        from collections import Counter
        counts = Counter(n.title for n in projects)
        return {(n.title if counts[n.title] == 1 else n.title + ' · ' + n.id[:6]): n.id
                for n in sorted(projects,key=lambda n:n.title.casefold())}

    def refresh(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        q, ws = self.app.q, self.app.ws
        projects = self._project_options()
        self.proj_box.configure(values=["Toate proiectele", "Fără proiect", *projects])
        if self.proj_var.get() not in ("Toate proiectele", "Fără proiect", *projects):
            self.proj_var.set("Toate proiectele")
        scope = self.scope_id if self.scope_id in ws.nodes else None
        self._cmap = ws.children_map()
        self._prog = q.progress_map()
        self._worked = q.worked_map()
        nodes = self._source()
        status = None if self.status_var.get() in (ALL,"Orice status") else STATUS_FROM_LABEL[self.status_var.get()]
        prio = None if self.prio_var.get() in (ALL,"Orice prioritate") else PRIORITY_FROM_LABEL[self.prio_var.get()]
        proj = projects.get(self.proj_var.get())
        if not self.closed_var.get() and status is None:
            nodes = [n for n in nodes if n.status not in CLOSED_STATUSES]
        nodes = q.filter(nodes, status=status, priority=prio, due=DUE_FILTERS[self.due_var.get()],
                         project_id=proj, text=self.text_var.get(), requester=self.requester_var.get().strip(),
                         no_project=self.proj_var.get() == "Fără proiect")
        self._shown = self._sorted(nodes)
        rows = self._tree_rows(scope, nodes) if scope else [("", n) for n in self._shown]
        matched_ids = {n.id for n in nodes}
        scroll = 0 if self._expand_all else self.tv.yview()[0]
        horizontal = 0 if self._expand_all else self.tv.xview()[0]
        open_ids = {i for i in self._all_items() if self.tv.item(i, "open")}
        selected = self.tv.selection()
        self._suppress = True
        try:
            rendered = []
            for parent_iid, n in rows:
                is_open = self._expand_all or n.id in open_ids or n.id in self._force_open
                rendered.append((parent_iid,n.id,dict(tags=self._tags_for(n,n.id in matched_ids),
                    text=self._title_text(n),image=(str(node_icon(self,n)),),open=is_open,
                    values=self._values(n,scope is not None))))
            sync_rows(self.tv,rendered)
        finally:
            self._suppress = False
        self.tv.yview_moveto(scroll)
        self.tv.xview_moveto(horizontal)
        self._force_open.clear()
        self._expand_all = False
        self.count_lbl.configure(text=f"{len(self._shown)} task-uri")
        if not rows:
            self.empty_lbl.configure(text=self.empty_hint)
            self.empty_lbl.place(relx=0.5, rely=0.65, anchor="center")
        else:
            self.empty_lbl.place_forget()
        self._update_target()

    def _tree_rows(self, scope: str, matched: list[Node]) -> list[tuple[str, Node]]:
        """Randurile arborelui (parinte, nod). Stramosii unui task potrivit raman vizibili ca structura."""
        ws = self.app.ws
        in_scope = set(ws.subtree_ids(scope, include_self=False))
        keep = {n.id for n in matched} & in_scope
        done: set[str] = set()
        for n in matched:
            cur = n.parent_id
            while cur in in_scope and cur not in done:
                done.add(cur)
                keep.add(cur)
                cur = ws.nodes[cur].parent_id
        rows: list[tuple[str, Node]] = []

        def walk(pid: str, parent_iid: str) -> None:
            for c in self._order([c for c in self._cmap.get(pid, []) if c.id in keep]):
                rows.append((parent_iid, c))
                walk(c.id, c.id)

        walk(scope, "")
        # Task-uri legate din afara subarborelui: la final, fara ierarhie.
        outside = [n for n in matched if n.id not in in_scope and n.id != scope]
        rows.extend(("", n) for n in self._order(outside))
        return rows

    def _tags_for(self, n: Node, matched: bool) -> list[str]:
        tags: list[str] = []
        if n.kind != Kind.TASK:
            tags.append("group")
        if not matched:
            tags.append("context")
        elif n.status in CLOSED_STATUSES:
            tags.append("closed")
        elif self.app.q.is_overdue(n):
            tags.append("overdue")
        return tags

    def _title_text(self, n: Node) -> str:
        text = n.title
        if n.kind == Kind.TASK and n.status not in CLOSED_STATUSES and self.app.q.is_blocked(n):
            text += "  [blocat]"
        return text

    def _values(self, n: Node, in_tree: bool) -> tuple[str, ...]:
        loc = "" if in_tree else " › ".join(a.title for a in self.app.ws.ancestors(n.id))
        is_task = n.kind == Kind.TASK
        return (
            STATUS_LABELS.get(n.status, "") if n.status and is_task else "",
            PRIORITY_LABELS.get(n.priority, "") if n.priority and is_task else "",
            self._due_text(n) if is_task else "", self._progress_text(n),
            self.remaining_text(n) if is_task else "", format_worked(self._worked.get(n.id, 0)), loc)

    def _progress_text(self, n: Node) -> str:
        p = self._prog.get(n.id)
        if p is None or p.leaf_total == 0 or not self._cmap.get(n.id):
            return ""
        return f"{p.done}/{p.leaf_total}"

    def _due_text(self, n: Node) -> str:
        q = self.app.q
        d = q.due_day(n)
        if d is None:
            return ""
        text = format_date(d)
        if n.due_at is not None:
            text += n.due_at.astimezone(q.tz()).strftime(" %H:%M")
        return text

    def remaining_text(self, n: Node) -> str:
        if n.status in CLOSED_STATUSES:
            return "—"
        if any(c.kind == Kind.TASK for c in self._cmap.get(n.id, [])):
            p = self._prog.get(n.id) or self.app.q.progress(n.id)
            if p.open == 0:
                return "—"
            text = format_minutes(p.remaining_minutes) if p.remaining_minutes else "Neestimat"
            return f"Σ {text}" + (f" (+{p.unestimated} neest.)" if p.unestimated and p.remaining_minutes else "")
        rem = n.remaining_minutes if n.remaining_minutes is not None else n.estimated_minutes
        return format_minutes(rem)

    def _getters(self) -> dict[str, Callable[[Node], object]]:
        far = date.max
        q = self.app.q

        def progress_ratio(n: Node) -> float:
            p = self._prog.get(n.id)
            return (p.done / p.leaf_total) if p and p.leaf_total else -1.0

        return {
            "title": lambda n: n.title.lower(),
            "status": lambda n: STATUS_LABELS.get(n.status, "") if n.status else "",
            "priority": lambda n: PRIORITY_ORDER.get(n.priority or Priority.NORMAL, 2),
            "due": lambda n: q.due_day(n) or far,
            "progress": progress_ratio,
            "worked": lambda n: self._worked.get(n.id, 0),
            "remaining": lambda n: (n.remaining_minutes if n.remaining_minutes is not None
                                    else (n.estimated_minutes if n.estimated_minutes is not None else 10 ** 9)),
            "loc": lambda n: self.app.ws.breadcrumb(n.id).lower(),
        }

    def _sorted(self, nodes: list[Node]) -> list[Node]:
        if self._sort_key == "default":
            return self.app.q._sorted(nodes)
        return sorted(nodes, key=self._getters()[self._sort_key], reverse=self._sort_rev)

    def _order(self, siblings: list[Node]) -> list[Node]:
        """Ordinea fratilor in arbore: ordinea manuala (sort_order) pana alegi o coloana de sortare."""
        if self._sort_key == "default":
            return siblings
        return sorted(siblings, key=self._getters()[self._sort_key], reverse=self._sort_rev)

    def _sort_by(self, col: str) -> None:
        if self._sort_key == col:
            if self._sort_rev:
                self._sort_key, self._sort_rev = "default", False
            else:
                self._sort_rev = True
        else:
            self._sort_key, self._sort_rev = col, False
        self.refresh()

    def _all_items(self, parent: str = "") -> list[str]:
        out: list[str] = []
        for c in self.tv.get_children(parent):
            out.append(c)
            out.extend(self._all_items(c))
        return out

    # ---- selection --------------------------------------------------
    def select(self, node_id: str) -> None:
        if not self.tv.exists(node_id):
            self.clear_selection()  # nodul nu e un rand (ex. containerul listei): nu lasam un rand vechi selectat
            return
        self._suppress = True
        p = self.tv.parent(node_id)
        while p:
            self.tv.item(p, open=True)
            p = self.tv.parent(p)
        self.tv.selection_set(node_id)
        self.tv.see(node_id)
        self._suppress = False
        self._update_target()

    def clear_selection(self) -> None:
        self._suppress = True
        self.tv.selection_remove(self.tv.selection())
        self._suppress = False
        self._update_target()

    def selected_id(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def _on_select(self, _e=None) -> None:
        view=self.app.current_view
        if self._suppress or not (view in ('tasks','archive') or view.startswith(('tree:','search:'))):
            return
        nid = self.selected_id()
        if nid:
            self.app.select_node(nid, source="list")
        self._update_target()

    def _on_double(self, event: tk.Event) -> None:
        if self.tv.identify_region(event.x, event.y) == "tree":
            return  # dublu-clic pe sageata de expandare: comportamentul implicit
        self.app.focus_inspector()

    def _on_context(self, event: tk.Event) -> None:
        iid = self.tv.identify_row(event.y)
        if iid:
            self.tv.selection_set(iid)
        self.app.popup_context_menu(event.x_root, event.y_root, iid or None)

    # ---- quick add --------------------------------------------------
    def _selected_task_id(self) -> str | None:
        nid = self.selected_id()
        node = self.app.ws.nodes.get(nid) if nid else None
        return nid if node is not None and node.kind == Kind.TASK else None

    def _update_target(self) -> None:
        ws = self.app.ws
        self.session_btn.update_state()
        self.move_btn.state(["!disabled"] if ws and self.app.selected_id and not ws.read_only else ["disabled"])
        # The same action is already visible in the selected task's inspector.
        if self.app.config.show_inspector and self.app.selected_id:
            self.session_btn.pack_forget()
        elif not self.session_btn.winfo_manager():
            self.session_btn.pack(side="left")
        if ws is None:
            return
        if self.scope_id is None or self.scope_id not in ws.nodes:
            self.target_lbl.configure(text="Task independent" if not self._selected_task_id() else "Subtask în selecția curentă")
            self.add_top_btn.configure(text="Task independent")
            if self._selected_task_id(): self.add_top_btn.pack(side="left",padx=(6,0))
            else: self.add_top_btn.pack_forget()
            return
        sel = self._selected_task_id()
        if sel:
            self.target_lbl.configure(text=f"Se adaugă ca subtask în: {ws.breadcrumb(sel)}")
            self.add_top_btn.configure(text="La nivelul listei")
            self.add_top_btn.pack(side="left",padx=(6,0))
        else:
            self.target_lbl.configure(text=f"Se adaugă task în: {ws.breadcrumb(self.scope_id)}")
            self.add_top_btn.configure(text="Aici")
            self.add_top_btn.pack_forget()

    def _focus_add(self) -> None:
        if self.app.ws is not None:
            self.add_entry.focus_set()

    def _quick_add(self, under_selection: bool) -> None:
        title = self.add_var.get().strip()
        if not title:
            return
        parent = (self._selected_task_id() if under_selection else None) or self.scope_id
        if parent:
            self._force_open.add(parent)  # refresh-ul declansat de creare trebuie sa lase parintele deschis
        if self.app.quick_add_task(parent, title):
            self.add_var.set("")
            self.add_entry.focus_set()
