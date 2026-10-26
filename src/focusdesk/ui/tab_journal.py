"""Tabul „Jurnal”: notite datate, progres, sesiuni si schimbari de status."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.labels import STATUS_LABELS, format_seconds
from ..domain.models import Node, Status
from .common import muted_color
from .inspector import InspectorTab

if TYPE_CHECKING:
    from .app import FocusDeskApp

KIND_CHOICES = {"Notiță": "note", "Progres": "progress", "Acțiune": "action"}
KIND_NAMES = {"note": "Notiță", "progress": "Progres", "action": "Acțiune", "session": "Sesiune"}


class JournalTab(InspectorTab):
    title = "Jurnal"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 2))
        self.kind_var = tk.StringVar(value="Notiță")
        ttk.Combobox(top, textvariable=self.kind_var, values=list(KIND_CHOICES), state="readonly",
                     width=10).pack(side="left")
        self.total_lbl = ttk.Label(top, text="", style="Muted.TLabel")
        self.total_lbl.pack(side="right")
        self.entry = tk.Text(self, height=4, wrap="word", font="TkTextFont", borderwidth=1, relief="solid",
                             highlightthickness=0)
        self.entry.pack(fill="x", padx=8, pady=4)
        self.entry.bind("<Control-Return>", lambda _e: (self._add(), "break")[1])
        self.add_btn = ttk.Button(self, text="Adaugă în jurnal (Ctrl+Enter)", command=self._add)
        self.add_btn.pack(anchor="e", padx=8)
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.text = tk.Text(wrap, wrap="word", state="disabled", font="TkTextFont", borderwidth=0,
                            highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.text.tag_configure("when", font=("Segoe UI", 9, "bold"))
        self.text.tag_configure("muted", foreground=muted_color(self), font=("Segoe UI", 9))

    def load(self, node: Node) -> None:
        super().load(node)
        ws, q = self.app.ws, self.app.q
        tz = q.tz()
        entries: list[tuple] = []
        for n in ws.list_notes(node.id):
            entries.append((n.at, KIND_NAMES.get(n.kind, n.kind), n.text, n.minutes))
        total = 0
        for s in ws.repo.sessions.list_all():
            if s.node_id != node.id:
                continue
            if s.status == "done" and s.actual_seconds:
                total += s.actual_seconds
                txt = f"Sesiune de lucru: {format_seconds(s.actual_seconds)}"
                if s.summary:
                    txt += f"\n{s.summary}"
                entries.append((s.stopped_actual_at or s.end_at, "Sesiune", txt, None))
        for e in ws.list_history(node.id):
            if e.type == "status_changed":
                new = Status(e.data.get("to")) if e.data.get("to") else None
                entries.append((e.at, "Status", f"Status schimbat în {STATUS_LABELS.get(new, '?')}", None))
        entries.sort(key=lambda x: x[0], reverse=True)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if not entries:
            self.text.insert("end", "Nicio înregistrare încă.", "muted")
        for at, kind, body, _m in entries:
            self.text.insert("end", f"{at.astimezone(tz):%d.%m.%Y %H:%M}  ·  {kind}\n", "when")
            self.text.insert("end", body + "\n\n")
        self.text.configure(state="disabled")
        self.total_lbl.configure(text=f"Timp lucrat: {format_seconds(total)}" if total else "Timp lucrat: 0:00:00")
        state = "disabled" if ws.read_only else "normal"
        self.add_btn.configure(state=state)
        self.entry.configure(state=state)

    def _add(self) -> None:
        text = self.entry.get("1.0", "end").strip()
        if not text or not self.node_id:
            return
        kind = KIND_CHOICES[self.kind_var.get()]
        if self.app.run_write(lambda: self.app.ws.add_note(self.node_id, text, kind), success_text="Notiță salvată"):
            self.entry.delete("1.0", "end")
            self.load(self.app.ws.get(self.node_id))
