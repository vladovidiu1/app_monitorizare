"""Dialoguri pentru crearea, mutarea si legarea nodurilor, coș si diagnostic."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..domain.labels import (
    KIND_LABELS, PRIORITY_FROM_LABEL, PRIORITY_LABELS, STATUS_FROM_LABEL, STATUS_LABELS, VISIBLE_STATUSES,
)
from ..domain.models import Kind, Node, Priority, Status
from ..errors import FocusDeskError, ValidationError
from ..services.queries import Queries
from ..services.workspace import Workspace
from .common import ModalDialog, make_tree, show_error
from .colleagues_ui import ColleagueField
from .formats import parse_date, parse_duration, parse_tags

ROOT_LABEL = "(Rădăcina workspace-ului)"


def location_choices(ws: Workspace, kind: Kind, *, exclude_subtree_of: str | None = None) -> list[tuple[str, str | None]]:
    """Parinti valizi pentru `kind`, in ordinea arborelui, cu breadcrumb ca eticheta."""
    excluded = set(ws.subtree_ids(exclude_subtree_of)) if exclude_subtree_of else set()
    out: list[tuple[str, str | None]] = [(ROOT_LABEL, None)]
    cmap = ws.children_map()

    def walk(parent_id: str | None, prefix: str) -> None:
        for n in cmap.get(parent_id, []):
            if n.id in excluded:
                continue
            label = f"{prefix}{n.title}"
            try:
                ws.check_parent(kind, n.id)
                out.append((label, n.id))
            except ValidationError:
                pass
            walk(n.id, f"{label} › ")

    walk(None, "")
    return out


class NewNodeDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, ws: Workspace, *, kind: Kind = Kind.TASK, parent_id: str | None = None,
                 title: str = "") -> None:
        titles = {Kind.TASK: "Task nou", Kind.FOLDER: "Folder nou", Kind.PROJECT: "Proiect nou"}
        super().__init__(parent, titles[kind], ok_text="Creează")
        self.ws, self.kind = ws, kind
        self.q = Queries(ws)
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text="Titlu").grid(row=0, column=0, sticky="w", pady=4)
        self.title_var = tk.StringVar(value=title)
        self.title_entry = ttk.Entry(b, textvariable=self.title_var, width=52)
        self.title_entry.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(b, text="Locație").grid(row=1, column=0, sticky="w", pady=4)
        self._choices = location_choices(ws, kind)
        self.loc_var = tk.StringVar()
        self.loc_box = ttk.Combobox(b, textvariable=self.loc_var, state="readonly",
                                    values=[c[0] for c in self._choices], width=50)
        self.loc_box.grid(row=1, column=1, sticky="ew", pady=4)
        idx = next((i for i, c in enumerate(self._choices) if c[1] == parent_id), 0)
        self.loc_box.current(idx)
        self.more_open = tk.BooleanVar(value=False)
        self.more_btn = ttk.Checkbutton(b, text="Mai multe detalii", variable=self.more_open,
                                        command=self._toggle_more, style="Toolbutton")
        self.more_btn.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.more = ttk.Frame(b)
        self.more.columnconfigure(1, weight=1)
        self._build_more()
        self.title_entry.focus_set()

    def _build_more(self) -> None:
        m = self.more
        r = 0
        self.status_var = tk.StringVar(value=STATUS_LABELS[Status.TODO])
        self.prio_var = tk.StringVar(value=PRIORITY_LABELS[Priority.NORMAL])
        self.due_var = tk.StringVar()
        self.est_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.next_var = tk.StringVar()
        if self.kind != Kind.FOLDER:
            ttk.Label(m, text="Status").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Combobox(m, textvariable=self.status_var, state="readonly",
                         values=[STATUS_LABELS[s] for s in VISIBLE_STATUSES]).grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
            ttk.Label(m, text="Prioritate").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Combobox(m, textvariable=self.prio_var, state="readonly",
                         values=[PRIORITY_LABELS[p] for p in Priority]).grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
        if self.kind == Kind.TASK:
            ttk.Label(m, text="Cine a solicitat").grid(row=r, column=0, sticky="w", pady=3)
            self.requester_field = ColleagueField(m, lambda: self.ws)
            self.requester_field.grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
            ttk.Label(m, text="Termen").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(m, textvariable=self.due_var).grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
            ttk.Label(m, text="Estimare").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(m, textvariable=self.est_var).grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
            ttk.Label(m, text="Următorul pas").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(m, textvariable=self.next_var).grid(row=r, column=1, sticky="ew", pady=3)
            r += 1
        ttk.Label(m, text="Etichete").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(m, textvariable=self.tags_var).grid(row=r, column=1, sticky="ew", pady=3)
        r += 1
        ttk.Label(m, text="Descriere").grid(row=r, column=0, sticky="nw", pady=3)
        self.desc = tk.Text(m, height=5, width=40, wrap="word", font="TkTextFont")
        self.desc.grid(row=r, column=1, sticky="ew", pady=3)
        if self.kind == Kind.TASK:
            hint = "Termen: ZZ.LL.AAAA, azi, mâine, +3. Estimare: 90, 1h30."
            ttk.Label(m, text=hint, style="Muted.TLabel").grid(row=r + 1, column=1, sticky="w")

    def _toggle_more(self) -> None:
        if self.more_open.get():
            self.more.grid(row=3, column=0, columnspan=2, sticky="ew")
        else:
            self.more.grid_forget()

    def validate(self) -> bool:
        if not self.title_var.get().strip():
            show_error(self, "Titlul este obligatoriu.")
            return False
        try:
            if self.kind == Kind.TASK:
                parse_date(self.due_var.get())
                parse_duration(self.est_var.get())
        except ValueError as exc:
            show_error(self, str(exc))
            return False
        return True

    def collect(self) -> dict[str, Any]:
        parent_id = self._choices[self.loc_box.current()][1]
        fields: dict[str, Any] = {}
        if self.more_open.get():
            if self.kind != Kind.FOLDER:
                fields["status"] = STATUS_FROM_LABEL[self.status_var.get()]
                fields["priority"] = PRIORITY_FROM_LABEL[self.prio_var.get()]
            if self.kind == Kind.TASK:
                fields["requested_by"] = self.requester_field.person
                fields["due_date"] = parse_date(self.due_var.get(), self.q.today())
                fields["estimated_minutes"] = parse_duration(self.est_var.get())
                fields["remaining_minutes"] = fields["estimated_minutes"]
                fields["next_action"] = self.next_var.get().strip() or None
            fields["tags"] = parse_tags(self.tags_var.get())
        return {"kind": self.kind, "title": self.title_var.get(), "parent_id": parent_id, "fields": fields,
                "description": self.desc.get("1.0", "end").strip() if self.more_open.get() else ""}


class MoveDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, ws: Workspace, node: Node) -> None:
        super().__init__(parent, f"Mută „{node.title}”", ok_text="Mută")
        self.choices = location_choices(ws, node.kind, exclude_subtree_of=node.id)
        ttk.Label(self.body, text="Destinație nouă").pack(anchor="w")
        self.var = tk.StringVar()
        self.box = ttk.Combobox(self.body, textvariable=self.var, state="readonly",
                                values=[c[0] for c in self.choices], width=56)
        self.box.pack(fill="x", pady=6)
        idx = next((i for i, c in enumerate(self.choices) if c[1] == node.parent_id), 0)
        self.box.current(idx)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=420,
                  text="UUID-urile, fișierele, sesiunile și legăturile rămân neschimbate.").pack(anchor="w")

    def collect(self) -> tuple[str | None]:
        return (self.choices[self.box.current()][1],)


class NodePickerDialog(ModalDialog):
    """Alege un nod existent (pentru legaturi/dependente)."""

    def __init__(self, parent: tk.Misc, ws: Workspace, title: str, *, exclude: set[str] | None = None,
                 only_tasks: bool = False, ok_text: str = "Alege") -> None:
        super().__init__(parent, title, resizable=True, ok_text=ok_text)
        self.ws = ws
        self.q = Queries(ws)
        self.exclude = exclude or set()
        self.only_tasks = only_tasks
        self.var = tk.StringVar()
        entry = ttk.Entry(self.body, textvariable=self.var, width=60)
        entry.pack(fill="x")
        entry.focus_set()
        self.tv, frame = make_tree(self.body, [("title", "Titlu", 260), ("kind", "Tip", 70), ("loc", "Locație", 220)],
                                   height=12)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        self.tv.bind("<Double-1>", lambda _e: self._on_ok())
        self.var.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _refresh(self) -> None:
        self.tv.delete(*self.tv.get_children())
        text = self.var.get().strip()
        nodes = self.q.search(text, include_archived=False) if text else sorted(
            self.ws.nodes.values(), key=lambda n: n.title.lower())
        for n in nodes[:300]:
            if n.id in self.exclude or (self.only_tasks and n.kind != Kind.TASK):
                continue
            loc = " › ".join(a.title for a in self.ws.ancestors(n.id))
            self.tv.insert("", "end", iid=n.id, values=(n.title, KIND_LABELS[n.kind], loc))

    def validate(self) -> bool:
        if not self.tv.selection():
            show_error(self, "Selectează un element din listă.")
            return False
        return True

    def collect(self) -> str:
        return self.tv.selection()[0]


class TrashDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, ws: Workspace, on_change) -> None:
        super().__init__(parent, "Coș", resizable=True, ok_text="Închide", cancel_text="Închide")
        self.ok_btn.pack_forget()
        self.ws, self.on_change = ws, on_change
        self.tv, frame = make_tree(self.body, [("title", "Element", 280), ("kind", "Tip", 80),
                                               ("count", "Noduri", 60), ("when", "Șters la", 140)], height=10)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Restaurează", command=self._restore).pack(side="left")
        ttk.Button(row, text="Șterge definitiv", command=self._purge).pack(side="left", padx=8)
        ttk.Label(self.body, style="Muted.TLabel", wraplength=480,
                  text="Restaurarea readuce nodul și descendenții lui cu aceleași UUID-uri, la locul inițial dacă mai există.").pack(anchor="w", pady=(8, 0))
        self._load()

    def _load(self) -> None:
        self.tv.delete(*self.tv.get_children())
        for e in self.ws.list_trash():
            self.tv.insert("", "end", iid=e["node_id"], values=(
                e["title"], KIND_LABELS.get(Kind(e["kind"]), e["kind"]), len(e["node_ids"]),
                e["trashed_at"].replace("T", " ").replace("Z", " UTC")))

    def _selected(self) -> str | None:
        sel = self.tv.selection()
        return sel[0] if sel else None

    def _restore(self) -> None:
        nid = self._selected()
        if not nid:
            return
        try:
            self.ws.restore(nid)
        except FocusDeskError as exc:
            show_error(self, str(exc))
            return
        self._load()
        self.on_change()

    def _purge(self) -> None:
        from .common import confirm

        nid = self._selected()
        if nid and confirm(self, "Ștergerea definitivă nu poate fi anulată. Continui?"):
            try:
                self.ws.purge_trash(nid)
            except FocusDeskError as exc:
                show_error(self, str(exc))
            self._load()


class IssuesDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, ws: Workspace) -> None:
        super().__init__(parent, "Verificare integritate workspace", resizable=True, ok_text="Închide",
                         cancel_text="Închide")
        self.ok_btn.pack_forget()
        issues = ws.issues
        ttk.Label(self.body, text=(f"{len(issues)} probleme detectate; nimic nu a fost șters automat."
                                   if issues else "Nu au fost detectate probleme."),
                  style="Section.TLabel").pack(anchor="w")
        if issues:
            tv, frame = make_tree(self.body, [("sev", "Nivel", 70), ("code", "Cod", 150), ("msg", "Detalii", 560)],
                                  height=12)
            frame.pack(fill="both", expand=True, pady=8)
            for i in issues:
                tv.insert("", "end", values=("Eroare" if i.severity == "error" else "Avertisment", i.code, i.message))
        for m in ws.recovery_messages:
            ttk.Label(self.body, text="• " + m, wraplength=640).pack(anchor="w")
