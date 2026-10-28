"""Tabul „Detalii” din inspector."""

from __future__ import annotations

import tkinter as tk
from datetime import time
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ..domain.labels import (
    PRIORITY_FROM_LABEL, PRIORITY_LABELS, STATUS_FROM_LABEL, STATUS_LABELS, VISIBLE_STATUSES, format_minutes,
)
from ..domain.models import CLOSED_STATUSES, Kind, Node, Priority, Status
from ..domain.timeutil import local_to_utc, utc_to_local
from ..errors import FocusDeskError
from .common import ScrollFrame, error_color, muted_color, show_error
from .colleagues_ui import ColleagueField
from .dialogs import NodePickerDialog
from .formats import (
    duration_to_text, format_date, parse_date, parse_duration, parse_tags, parse_time,
)
from .inspector import InspectorTab
from .markdown_editor import MarkdownEditor, ExpandedDescription

if TYPE_CHECKING:
    from .app import FocusDeskApp

REVIEW_TIME = time(8, 0)


class DetailsTab(InspectorTab):
    title = "Detalii"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        self._loading = False
        self._dirty = False
        self._orig_desc = ""
        self._loaded_node = None
        self.expanded = None
        self.panes = ttk.PanedWindow(self, orient="vertical")
        self.panes.pack(fill="both", expand=True)
        self.sf = ScrollFrame(self.panes, height=240)
        self.panes.add(self.sf, weight=1)
        f = self.sf.inner
        f.columnconfigure(1, weight=1)
        pad = {"padx": (12, 12), "pady": 5}
        self.vars: dict[str, tk.StringVar] = {k: tk.StringVar() for k in (
            "title", "status", "priority", "due", "due_time", "est", "rem", "tags", "next", "waiting", "review", "completed")}
        self.pin_var = tk.BooleanVar()
        for v in (*self.vars.values(), self.pin_var):
            v.trace_add("write", lambda *_: self._mark_dirty())
        r = 0
        self.rows: dict[str, list[tk.Misc]] = {}

        def row(key: str, label: str, widget_factory, *, sticky="ew") -> ttk.Frame:
            nonlocal r
            lbl = ttk.Label(f, text=label)
            lbl.grid(row=r, column=0, sticky="nw", **pad)
            w = widget_factory(f)
            w.grid(row=r, column=1, sticky=sticky, **pad)
            self.rows[key] = [lbl, w]
            r += 1
            return w

        row("title", "Titlu", lambda p: ttk.Entry(p, textvariable=self.vars["title"]))
        self.title_entry = self.rows["title"][1]
        self.requester_field = row("requester", "Cine a solicitat", lambda p: ColleagueField(
            p, lambda: self.app.ws, self._mark_dirty))
        self.status_box = row("status", "Status", lambda p: ttk.Combobox(
            p, textvariable=self.vars["status"], state="readonly", values=[STATUS_LABELS[s] for s in VISIBLE_STATUSES]))
        self.prio_box = row("priority", "Prioritate", lambda p: ttk.Combobox(
            p, textvariable=self.vars["priority"], state="readonly", values=[PRIORITY_LABELS[x] for x in Priority]))

        def due_frame(p):
            fr = ttk.Frame(p)
            fields=ttk.Frame(fr)
            fields.pack(anchor="w",fill="x")
            ttk.Entry(fields, textvariable=self.vars["due"], width=12).pack(side="left")
            ttk.Label(fields, text="ora").pack(side="left", padx=(8,2))
            ttk.Entry(fields, textvariable=self.vars["due_time"], width=6).pack(side="left")
            actions=ttk.Frame(fr)
            actions.pack(anchor="w",pady=(4,0))
            ttk.Button(actions,text="Azi",command=lambda:self._set_due("azi")).pack(side="left")
            ttk.Button(actions,text="Mâine",command=lambda:self._set_due("mâine")).pack(side="left",padx=4)
            from .design import button
            button(actions,"",lambda:self._set_due(""),glyph="clear",tooltip="Elimină termenul",width=2).pack(side="left")
            return fr

        row("due", "Termen", due_frame)

        def est_frame(p):
            fr = ttk.Frame(p)
            ttk.Entry(fr, textvariable=self.vars["est"], width=9).pack(side="left")
            ttk.Label(fr, text="rămas").pack(side="left", padx=(10, 2))
            ttk.Entry(fr, textvariable=self.vars["rem"], width=9).pack(side="left")
            return fr

        row("est", "Estimare", est_frame)
        self.agg_lbl = ttk.Label(f, text="", style="Muted.TLabel", wraplength=340, justify="left")
        self.agg_lbl.grid(row=r, column=0, columnspan=2, sticky="w", padx=8)
        r += 1
        row("tags", "Etichete", lambda p: ttk.Entry(p, textvariable=self.vars["tags"]))
        row("next", "Următorul pas", lambda p: ttk.Entry(p, textvariable=self.vars["next"]))
        row("waiting", "Blocaj / motiv", lambda p: ttk.Entry(p, textvariable=self.vars["waiting"]))
        row("review", "Dată de revenire", lambda p: ttk.Entry(p, textvariable=self.vars["review"], width=14),
            sticky="w")
        row("completed", "Dată finalizare", lambda p: ttk.Entry(p, textvariable=self.vars["completed"], width=14),
            sticky="w")
        pin = ttk.Checkbutton(f, text="Prioritate pentru azi (max. 3)", variable=self.pin_var)
        pin.grid(row=r, column=1, sticky="w", **pad)
        self.rows["pin"] = [pin]
        r += 1

        # Dependente si legaturi (se aplica imediat, nu fac parte din formular)
        self.dep_frame = ttk.LabelFrame(f, text="Depinde de (dependențe)")
        self.dep_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=(10, 3))
        self.dep_list = tk.Listbox(self.dep_frame, height=3, activestyle="none", exportselection=False)
        self.dep_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        dbtn = ttk.Frame(self.dep_frame)
        dbtn.pack(side="right", padx=6)
        ttk.Button(dbtn, text="Adaugă…", command=self._add_dep).pack(fill="x", pady=2)
        ttk.Button(dbtn, text="Elimină", command=self._remove_dep).pack(fill="x", pady=2)
        r += 1
        self.link_frame = ttk.LabelFrame(f, text="Legături către alte proiecte / task-uri (referințe, fără copii)")
        self.link_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=3)
        self.link_list = tk.Listbox(self.link_frame, height=3, activestyle="none", exportselection=False)
        self.link_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        lbtn = ttk.Frame(self.link_frame)
        lbtn.pack(side="right", padx=6)
        ttk.Button(lbtn, text="Adaugă…", command=self._add_link).pack(fill="x", pady=2)
        ttk.Button(lbtn, text="Elimină", command=self._remove_link).pack(fill="x", pady=2)
        r += 1
        self._dep_ids: list[str] = []
        self._link_ids: list[str] = []

        self.editor = MarkdownEditor(self.panes, on_change=self._desc_changed,
                                     on_save=self.save, expand=self.expand_description, guide_context=self.description_context, on_guide_applied=self._mark_dirty)
        self.desc = self.editor.text
        self.panes.add(self.editor, weight=2)
        self._split_initialized = False
        self.panes.bind("<Configure>", self._layout_split)
        bar = ttk.Frame(self, padding=(10,8))
        self.panes.pack_forget()
        bar.pack(side="bottom", fill="x")
        self.panes.pack(fill="both", expand=True)
        self.save_btn = tb.Button(bar, text="Salvează (Ctrl+S)", command=self.save, bootstyle="primary")
        self.save_btn.pack(side="left")
        ttk.Button(bar, text="Renunță la modificări", command=self.revert).pack(side="left", padx=8)
        self.state_lbl = ttk.Label(bar, text="", style="Muted.TLabel")
        self.state_lbl.pack(side="bottom", fill="x", pady=(6,0))

    # ---- applicability ----------------------------------------------
    def applies_to(self, node: Node) -> bool:
        return True

    # ---- load -------------------------------------------------------
    def load(self, node: Node) -> None:
        same = self.node_id == node.id
        super().load(node)
        self.editor.clear_guide_notice()
        self._loaded_node = node.model_copy(deep=True)
        ws, q = self.app.ws, self.app.q
        self._loading = True
        try:
            v = self.vars
            v["title"].set(node.title)
            self.requester_field.set(node.requested_by)
            v["status"].set(STATUS_LABELS[node.status] if node.status else "")
            v["priority"].set(PRIORITY_LABELS[node.priority] if node.priority else "")
            d = q.due_day(node)
            v["due"].set(format_date(d))
            v["due_time"].set(node.due_at.astimezone(q.tz()).strftime("%H:%M") if node.due_at else "")
            v["est"].set(duration_to_text(node.estimated_minutes))
            v["rem"].set(duration_to_text(node.remaining_minutes))
            v["tags"].set(", ".join(node.tags))
            v["next"].set(node.next_action or "")
            v["waiting"].set(node.waiting_reason or "")
            v["review"].set(format_date(node.review_at.astimezone(q.tz()).date()) if node.review_at else "")
            self.pin_var.set(node.pinned_today == q.today())
            v["completed"].set(format_date(node.completed_at.astimezone(q.tz()).date()) if node.completed_at else "")
            try:
                self._orig_desc = ws.get_description(node.id)
            except FocusDeskError as exc:
                self._orig_desc = ""
                show_error(self, str(exc))
            self.desc.configure(state="normal")
            if not same or self.desc.get("1.0", "end-1c") != self._orig_desc:
                self.desc.delete("1.0", "end")
                self.desc.insert("1.0", self._orig_desc)
                self.desc.edit_reset()
            self.desc.edit_modified(False)
        finally:
            self._loading = False
        self._apply_visibility(node)
        self._load_links(node)
        self._update_aggregate(node)
        self._dirty = False
        self._update_state()
        ro = ws.read_only
        self.editor.set_read_only(ro)
        for child in self.sf.inner.winfo_children():
            self._set_state_recursive(child, "disabled" if ro else None)

    def _layout_split(self, event):
        if event.height < 180:
            return
        if not self._split_initialized:
            self._split_initialized = True
            self.panes.sashpos(0, min(220, int(event.height * .4)))
        elif self.panes.sashpos(0) > max(100, event.height - 240):
            self.panes.sashpos(0, max(100, event.height - 240))

    def description_context(self):
        ws = self.app.ws
        if ws is None or ws.read_only or self.node_id not in ws.nodes or self.app.inspector.node_id != self.node_id:
            return None
        try:
            if not (ws.node_dir(self.node_id) / 'node.json').is_file():
                return None
        except (OSError, KeyError):
            return None
        return ws, self.node_id

    def expand_description(self):
        if self.app.ws.read_only or not self.node_id:
            return
        if self.expanded and self.expanded.winfo_exists():
            self.expanded.lift()
        else:
            self.expanded = ExpandedDescription(self)

    def _set_state_recursive(self, widget: tk.Misc, state: str | None) -> None:
        try:
            if state is not None:
                if not hasattr(widget, '_writable_state'):
                    widget._writable_state = widget.cget('state')
                widget.configure(state=state)
            elif hasattr(widget, '_writable_state'):
                widget.configure(state=widget._writable_state)
                del widget._writable_state
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_state_recursive(child,state)

    def _apply_visibility(self, node: Node) -> None:
        is_task = node.kind == Kind.TASK
        show = {
            "requester": is_task,
            "status": node.kind != Kind.FOLDER, "priority": node.kind != Kind.FOLDER,
            "due": is_task, "est": is_task, "waiting": is_task, "review": is_task, "completed": is_task, "pin": is_task,
        }
        for key, visible in show.items():
            for w in self.rows[key]:
                if visible:
                    w.grid()
                else:
                    w.grid_remove()
        if is_task:
            self.dep_frame.grid()
        else:
            self.dep_frame.grid_remove()

    def _load_links(self, node: Node) -> None:
        ws = self.app.ws
        self.dep_list.delete(0, "end")
        self._dep_ids = []
        for dep_id in node.depends_on_ids:
            dep = ws.nodes.get(dep_id)
            if dep is None:
                label = f"(inexistent) {dep_id[:8]}"
            else:
                done = " ✓" if dep.status in (Status.DONE, Status.CANCELLED) else ""
                label = f"{dep.title}{done}"
            self.dep_list.insert("end", label)
            self._dep_ids.append(dep_id)
        self.link_list.delete(0, "end")
        self._link_ids = []
        seen: set[str] = set()
        for rid in [*node.related_node_ids, *[n.id for n in ws.referrers(node.id) if node.id in n.related_node_ids]]:
            if rid in seen:
                continue
            seen.add(rid)
            other = ws.nodes.get(rid)
            direction = "→" if rid in node.related_node_ids else "←"
            self.link_list.insert("end", f"{direction} {other.title if other else '(inexistent) ' + rid[:8]}")
            self._link_ids.append(rid)

    def _update_aggregate(self, node: Node) -> None:
        q = self.app.q
        has_task_children = any(c.kind == Kind.TASK for c in self.app.ws.children(node.id))
        if node.kind == Kind.FOLDER or not (node.kind == Kind.PROJECT or has_task_children):
            self.agg_lbl.configure(text="")
            return
        p = q.progress(node.id)
        if p.leaf_total == 0:
            self.agg_lbl.configure(text="Fără task-uri frunză încă.")
            return
        pct = f"{round(100 * p.ratio)}%" if p.ratio is not None else "—"
        parts = [f"Progres agregat (task-uri frunză): {p.done}/{p.done + p.open} finalizate ({pct})."]
        parts.append(f"Timp rămas estimat: {format_minutes(p.remaining_minutes) if p.remaining_minutes else 'Neestimat'}.")
        if p.unestimated:
            parts.append(f"{p.unestimated} task-uri deschise sunt neestimate.")
        self.agg_lbl.configure(text=" ".join(parts))

    # ---- dirty tracking ---------------------------------------------
    def _mark_dirty(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._update_state()

    def _desc_changed(self) -> None:
        if self._loading:
            return
        if self.desc.get("1.0", "end-1c") != self._orig_desc:
            self._mark_dirty()

    def is_dirty(self) -> bool:
        return self._dirty or self.desc.get("1.0", "end-1c") != self._orig_desc

    def _update_state(self, text: str | None = None, error: bool = False) -> None:
        if text is None:
            text = "Modificări nesalvate" if self._dirty else ""
        color = error_color(self) if error or self._dirty else muted_color(self)
        self.state_lbl.configure(text=text, foreground=color)

    # ---- actions ----------------------------------------------------
    def _set_due(self, word: str) -> None:
        self.vars["due"].set(format_date(parse_date(word, self.app.q.today())) if word else "")
        if not word:
            self.vars["due_time"].set("")

    def _collect(self, node: Node) -> dict:
        q = self.app.q
        v = self.vars
        changes: dict = {}
        title = v["title"].get().strip()
        if not title:
            raise ValueError("Titlul nu poate fi gol.")
        if title != node.title:
            changes["title"] = title
        if node.kind != Kind.FOLDER:
            status = STATUS_FROM_LABEL[v["status"].get()]
            if STATUS_LABELS[status] != STATUS_LABELS.get(node.status):
                changes["status"] = status
            prio = PRIORITY_FROM_LABEL[v["priority"].get()]
            if prio != node.priority:
                changes["priority"] = prio
        tags = parse_tags(v["tags"].get())
        if tags != node.tags:
            changes["tags"] = tags
        if node.kind != Kind.TASK:
            return changes
        if self.requester_field.person != node.requested_by:
            changes["requested_by"] = self.requester_field.person
        today = q.today()
        d = parse_date(v["due"].get(), today)
        t = parse_time(v["due_time"].get())
        if d is None and t is not None:
            raise ValueError("Ora termenului necesită și o dată.")
        if d is None:
            new_due = (None, None)
        elif t is None:
            new_due = (d, None)
        else:
            new_due = (None, local_to_utc(d, t, self.app.ws.settings.timezone))
        if new_due != (node.due_date, node.due_at):
            changes["due_date"], changes["due_at"] = new_due
        est, rem = parse_duration(v["est"].get()), parse_duration(v["rem"].get())
        if est != node.estimated_minutes:
            changes["estimated_minutes"] = est
            if rem is None and node.remaining_minutes is None:
                changes["remaining_minutes"] = est
        if rem != node.remaining_minutes:
            changes["remaining_minutes"] = rem
        nxt = v["next"].get().strip() or None
        if nxt != node.next_action:
            changes["next_action"] = nxt
        wr = v["waiting"].get().strip() or None
        if wr != node.waiting_reason:
            changes["waiting_reason"] = wr
        rv = parse_date(v["review"].get(), today)
        new_review = local_to_utc(rv, REVIEW_TIME, self.app.ws.settings.timezone) if rv else None
        old_review_day = node.review_at.astimezone(q.tz()).date() if node.review_at else None
        if rv != old_review_day:
            changes["review_at"] = new_review
        done_day = parse_date(v["completed"].get(), today)
        old_done_day = node.completed_at.astimezone(q.tz()).date() if node.completed_at else None
        if done_day != old_done_day:
            if changes.get("status", node.status) in CLOSED_STATUSES:
                old_time = node.completed_at.astimezone(q.tz()).time() if node.completed_at else REVIEW_TIME
                changes["completed_at"] = (local_to_utc(done_day, old_time, self.app.ws.settings.timezone)
                                           if done_day else None)
            elif done_day is not None:
                raise ValueError("Data finalizării se poate seta doar pentru task-uri finalizate sau anulate.")
        pinned = today if self.pin_var.get() else None
        current_pin = node.pinned_today if node.pinned_today == today else None
        if pinned != current_pin:
            changes["pinned_today"] = pinned
        return changes

    def save(self) -> bool:
        if not self.node_id:
            return True
        ws = self.app.ws
        node = ws.get(self.node_id)
        try:
            changes = self._collect(self._loaded_node or node)
        except ValueError as exc:
            show_error(self, str(exc))
            return False
        desc = self.desc.get("1.0", "end-1c")
        desc_changed = desc != self._orig_desc

        def write() -> None:
            if changes:
                ws.update_node(node.id, **changes)
            if desc_changed:
                ws.set_description(node.id, desc)

        if not self.app.run_write(write, success_text="Salvat"):
            self._update_state("Salvarea a eșuat", error=True)
            return False
        self._orig_desc = desc
        self._dirty = False
        self.app.after_inspector_save(node.id)
        self.load(ws.get(node.id))
        self._update_state("Salvat")
        return True

    def revert(self) -> None:
        if self.node_id and self.node_id in self.app.ws.nodes:
            self.load(self.app.ws.nodes[self.node_id])

    def _commit_first(self) -> bool:
        return not self._dirty or self.save()

    def _add_dep(self) -> None:
        if not self.node_id or not self._commit_first():
            return
        node = self.app.ws.get(self.node_id)
        exclude = {node.id, *node.depends_on_ids}
        picked = NodePickerDialog(self, self.app.ws, "Depinde de…", exclude=exclude, only_tasks=True).run()
        if picked:
            self.app.run_write(lambda: self.app.ws.add_dependency(node.id, picked), refresh=True)

    def _remove_dep(self) -> None:
        sel = self.dep_list.curselection()
        if sel and self.node_id and self._commit_first():
            dep = self._dep_ids[sel[0]]
            self.app.run_write(lambda: self.app.ws.remove_dependency(self.node_id, dep), refresh=True)

    def _add_link(self) -> None:
        if not self.node_id or not self._commit_first():
            return
        node = self.app.ws.get(self.node_id)
        exclude = {node.id, *node.related_node_ids}
        picked = NodePickerDialog(self, self.app.ws, "Legătură către…", exclude=exclude).run()
        if picked:
            self.app.run_write(lambda: self.app.ws.add_related(node.id, picked), refresh=True)

    def _remove_link(self) -> None:
        sel = self.link_list.curselection()
        if not sel or not self.node_id or not self._commit_first():
            return
        other = self._link_ids[sel[0]]
        node = self.app.ws.get(self.node_id)
        if other in node.related_node_ids:
            self.app.run_write(lambda: self.app.ws.remove_related(node.id, other), refresh=True)
        else:
            self.app.run_write(lambda: self.app.ws.remove_related(other, node.id), refresh=True)
