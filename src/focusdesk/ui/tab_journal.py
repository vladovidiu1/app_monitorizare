"""Tabul „Jurnal”: notite datate, progres, sesiuni si schimbari de status."""

from __future__ import annotations

from ..i18n import tr

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.labels import STATUS_LABELS, format_seconds, SESSION_STATUS_LABELS, session_status_text
from ..domain.models import Node, Status
from .common import muted_color
from .inspector import InspectorTab
from .markdown_editor import PeerText

if TYPE_CHECKING:
    from .app import FocusDeskApp

KIND_CHOICES = {tr('ui.tab_journal.notita'): "note", tr('ui.tab_subtasks.progres'): "progress", tr('ui.tab_journal.actiune'): "action"}
KIND_NAMES = {"note": tr('ui.tab_journal.notita'), "progress": tr('ui.tab_subtasks.progres'), "action": tr('ui.tab_journal.actiune'), "session": tr('ui.tab_journal.sesiune')}


class JournalTab(InspectorTab):
    title = "Activitate"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", *, source_entry=None, source_kind=None) -> None:
        super().__init__(parent, app)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 2))
        self.kind_var = source_kind if source_kind is not None else tk.StringVar(value=tr('ui.tab_journal.notita'))
        ttk.Combobox(top, textvariable=self.kind_var, values=list(KIND_CHOICES), state="readonly",
                     width=10).pack(side="left")
        self.total_lbl = ttk.Label(top, text="", style="Muted.TLabel")
        self.total_lbl.pack(side="right")
        self.entry = PeerText(self, source_entry) if source_entry is not None else tk.Text(self)
        self.entry.configure(height=4, wrap="word", font="TkTextFont", borderwidth=1, relief="solid", highlightthickness=0)
        self.entry.pack(fill="x", padx=8, pady=4)
        self.entry.bind("<<Modified>>", self._draft_changed)
        self.entry.bind("<Control-Return>", lambda _e: (self._add(), "break")[1])
        self.add_btn = ttk.Button(self, text=tr('ui.tab_journal.adauga_in_jurnal_ctrl_enter'), command=self._add)
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

    def _draft_changed(self,event=None):
        if self.entry.edit_modified(): self.entry.edit_modified(False)

    def load(self, node: Node) -> None:
        same = self.node_id == node.id
        scroll = self.text.yview()[0] if same else 0
        super().load(node)
        ws, q = self.app.ws, self.app.q
        tz = q.tz()
        entries: list[tuple] = []
        for n in ws.list_notes(node.id):
            entries.append((n.at, KIND_NAMES.get(n.kind, n.kind), n.text, n.minutes))
        total = 0
        for s in ws.repo.sessions.select(node_ids={node.id}):
            if s.node_id != node.id:
                continue
            total += s.actual_seconds
            txt = tr('ui.tab_journal.lucrat_durata_programata_min', session_status_text_s_self_app_timer=session_status_text(s, self.app.timer), format_seconds_s_actual_seconds=format_seconds(s.actual_seconds), s_planned_minutes=s.planned_minutes)
            for correction in s.corrections:
                entries.append((datetime.fromisoformat(correction['at']), tr('ui.tab_journal.corectie_timp'),
                    tr('ui.tab_journal.s_s', correction_before_seconds=correction['before']['seconds'], correction_after_seconds=correction['after']['seconds']) + correction.get('reason',''), None))
            if s.summary:
                txt += f"\n{s.summary}"
            entries.append((s.stopped_actual_at or s.start_at, tr('ui.tab_journal.sesiune'), txt, None))
        for e in ws.list_history(node.id):
            if e.type == "status_changed":
                new = Status(e.data.get("to")) if e.data.get("to") else None
                entries.append((e.at, tr('ui.tab_details.status'), tr('ui.tab_journal.status_schimbat_in', status_labels_get_new=STATUS_LABELS.get(new, '?')), None))
            elif e.type=='reopened':
                entries.append((e.at,tr('ui.tab_journal.redeschidere'),tr('ui.tab_journal.continuarea_cerintei_initiale')+('\n'+tr('ui.tab_journal.reopening_reason',reason=e.data['reason']) if e.data.get('reason') else ''),None))
            elif e.type in ('followup_created','followup_linked'):
                text=(tr('ui.tab_journal.cerinta_ulterioara_creata') if e.type=='followup_created' else tr('ui.tab_journal.continuare_a'))+e.data.get('title',tr('ui.meetings.task_indisponibil'))
                entries.append((e.at,tr('ui.tab_journal.cerinta_noua'),text,None))
        entries.sort(key=lambda x: x[0], reverse=True)
        if getattr(self,'_render_job',None):
            self.after_cancel(self._render_job)
            self._render_job = None
        generation = getattr(self,'_render_generation',0)+1
        self._render_generation = generation
        self.text.configure(state='normal');self.text.delete('1.0','end')
        if not entries: self.text.insert('end',tr('ui.tab_journal.nicio_inregistrare_inca'),'muted')
        self.text.configure(state='disabled')
        def append(offset=0):
            if generation != self._render_generation: return
            self._render_job = None
            self.text.configure(state='normal')
            for at,kind,body,_m in entries[offset:offset+100]:
                self.text.insert('end',tr('ui.tab_journal.entry_heading', at_astimezone_tz=at.astimezone(tz), kind=kind),'when')
                self.text.insert('end',body+'\n\n')
            self.text.configure(state='disabled')
            if offset == 0: self.text.yview_moveto(scroll)
            if offset+100 < len(entries):
                self._render_job = self.after(1,lambda:append(offset+100))
        append()
        self.total_lbl.configure(text=tr('ui.tab_journal.timp_lucrat', format_seconds_total=format_seconds(total)) if total else tr('ui.tab_journal.timp_lucrat_0_00_00'))
        state = "disabled" if ws.read_only else "normal"
        self.add_btn.configure(state=state)
        self.entry.configure(state=state)

    def is_dirty(self):
        return bool(self.entry.get('1.0','end-1c').strip())

    def save(self):
        return self._add()

    def revert(self):
        self.entry.delete('1.0','end')
        super().revert()

    def _add(self):
        text = self.entry.get("1.0", "end").strip()
        if not text or not self.node_id:
            return True
        kind = KIND_CHOICES[self.kind_var.get()]
        if self.app.run_write(lambda: self.app.ws.add_note(self.node_id, text, kind), success_text=tr('ui.tab_journal.notita_salvata')):
            self.entry.delete("1.0", "end")
            self.load(self.app.ws.get(self.node_id))
            return True
        return False
