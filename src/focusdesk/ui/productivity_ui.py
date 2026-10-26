"""Previzualizări read-only. Nicio trimitere sau sesiune creată la primirea AI."""
from __future__ import annotations

from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk

from ..services.ai_productivity import (DAY_INSTRUCTION, REPORT_INSTRUCTION, day_context, day_selection,
    mail_instruction, report_context, report_text, report_fingerprint, activity_report, validate_mail_reply)
from ..services.assistant_context import build_context
from ..services.assistant_proposals import ProposalBatch
from .assistant_ui import open_source
from .common import confirm, show_error


class ProductivityWindow(tk.Toplevel):
    def __init__(self, app, mode, *, parent=None, node_id=None, mail_mode=None, use_draft=None):
        super().__init__(parent or app.root)
        self.app, self.mode, self.node_id = app, mode, node_id
        self.mail_mode, self.use_draft = mail_mode, use_draft
        self.ws, self.epoch = app.ws, app.ai.epoch
        self.closed = False
        self.request_id = self.job = None
        self.serial = 0
        self.bundle = self.reply = self.batch = self.report = None
        self.selected = []
        self.title({"day": "Pregătește-mi ziua", "report": "Raport de activitate", "mail": "Ciornă AI — mesaj nou"}[mode])
        self.geometry("820x680")
        self.period = tk.StringVar(value="Zilnic")
        if mode == "report":
            ttk.Combobox(self, textvariable=self.period, values=("Zilnic", "Săptămânal"), state="readonly").pack(anchor="w", padx=8, pady=4)
            ttk.Label(self, text="Zilnic: azi. Săptămânal: ultimele 7 zile inclusiv azi; numai timp înregistrat.").pack(anchor="w", padx=8)
        self.question = tk.StringVar(value="Alege prioritățile de azi după termene și blocaje.")
        if mode == "day":
            ttk.Entry(self, textvariable=self.question).pack(fill="x", padx=8, pady=6)
            ttk.Label(self, text="AI alege maximum 3 taskuri. Planner calculează; estimările lipsă se completează explicit.").pack(anchor="w", padx=8)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=6)
        ttk.Button(buttons, text="Generează cu AI", command=self.generate).pack(side="left")
        ttk.Button(buttons, text="Anulează", command=self.cancel).pack(side="left", padx=4)
        ttk.Button(buttons, text="Copiază", command=self.copy).pack(side="left", padx=4)
        self.use_button = ttk.Button(buttons, text={"mail": "Folosește ciorna…", "day": "Previzualizează în Planner…", "report": "Pregătește e-mail…"}[mode], command=self.use, state="disabled")
        self.use_button.pack(side="left", padx=4)
        self.text = tk.Text(self, wrap="word", undo=True)
        self.text.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(self, text="Text editabil. Sursele validate sunt în lista de mai jos. Nimic nu se trimite automat.").pack(anchor="w", padx=8)
        self.sources = tk.Listbox(self, height=4)
        self.sources.pack(fill="x", padx=8)
        self.sources.bind("<Double-1>", self.source)
        self.status = tk.StringVar(value="Nicio modificare automată.")
        ttk.Label(self, textvariable=self.status, wraplength=780).pack(fill="x", padx=8, pady=6)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        app.ai.views.add(self)
        if mode == "report":
            # Even without AI, make deterministic figures available on explicit request.
            ttk.Button(buttons, text="Calculează fără AI", command=lambda: self.generate(only_data=True)).pack(side="left")

    def on_selection(self):
        pass  # Contextul este explicit și rămâne taskul selectat la deschidere.

    def workspace_changed(self):
        self.destroy()

    def cancel(self):
        self.serial += 1
        if self.job:
            self.job.cancel()
            self.job = None
        if self.request_id:
            self.app.ai.cancel(self.request_id)
            self.request_id = None
        if not self.closed:
            self.status.set("Generare anulată. Previzualizarea nu a fost aplicată.")

    def active(self, serial):
        return not self.closed and self.app.ws is self.ws and self.epoch == self.app.ai.epoch and self.serial == serial

    def generate(self, only_data=False):
        self.cancel()
        self.bundle = self.reply = self.batch = self.report = None
        self.use_button.state(["disabled"])
        self.sources.delete(0, "end")
        self.replace("")
        if not only_data and not self.app.config.ai.enabled:
            self.status.set("Activează AI în Setări. Raportul numeric poate fi calculat fără AI.")
            return
        serial = self.serial
        today = self.app.q.today()
        first = today - timedelta(days=6) if self.period.get() == "Săptămânal" else today
        question = self.question.get().strip()[:2000]
        try:
            instruction = mail_instruction(self.ws, self.node_id, self.mail_mode) if self.mode == "mail" else DAY_INSTRUCTION + question if self.mode == "day" else REPORT_INSTRUCTION
        except Exception as exc:
            self.status.set(str(exc))
            return
        def retrieve(token):
            if self.mode == "mail":
                return build_context(self.ws, "task", self.node_id, instruction, token), None
            if self.mode == "day":
                return day_context(self.ws, question, token), None
            return report_context(self.ws, first, today, token)
        def failed(exc):
            if self.active(serial):
                self.job = self.request_id = None
                self.status.set("Generarea nu poate continua: " + str(exc))
        def ready(value):
            if not self.active(serial):
                return
            self.job = None
            self.bundle, self.report = value
            if self.report is not None:
                for key in self.bundle.sources:
                    self.sources.insert("end", key)
                self.replace(report_text(self.report))
                self.use_button.state(["!disabled"])
            if only_data or not self.bundle.sources:
                self.status.set("Cifre calculate în cod; fără inferență." if only_data else "Nu există taskuri candidate.")
                return
            try:
                self.request_id = self.app.ai.request(self.app.config.ai, "assistant", instruction, self.bundle.wire(),
                    lambda message: received(message), intent="email" if self.mode == "mail" else "chat")
                self.status.set("Generez local; nicio aplicare sau trimitere…")
            except Exception as exc:
                failed(exc)
        def received(message):
            if not self.active(serial) or (self.request_id and message.request_id != self.request_id):
                return
            if message.kind == "loading":
                self.status.set("Încarc modelul local…")
                return
            self.request_id = None
            if message.kind == "error":
                failed(RuntimeError(message.error))
                return
            try:
                reply = message.assistant
                if self.mode == "mail":
                    self.batch = validate_mail_reply(self.ws, self.bundle, reply, message.context_keys, self.node_id)
                else:
                    self.batch = ProposalBatch.prepare(self.ws, self.bundle, reply, message.context_keys, "chat")
                if self.mode == "day":
                    self.selected = day_selection(self.ws, self.bundle, reply, message.context_keys)
                self.reply = reply
                prose = "\n\n".join(part.text + "\n[" + ", ".join(part.sources) + "]" for part in reply.answer)
                if self.mode == "mail":
                    prose = reply.email.subject + "\n\n" + reply.email.body
                if self.report is not None:
                    prose = report_text(self.report) + "\n\nExplicație AI (de verificat):\n" + prose
                self.replace(prose)
                self.source_keys = list(dict.fromkeys(key for part in [*reply.answer, *([reply.email] if reply.email else [])] for key in part.sources))
                self.sources.delete(0, "end")
                for key in dict.fromkeys([*self.source_keys, *([] if self.report is None else self.bundle.sources)]):
                    self.sources.insert("end", key)
                self.use_button.state(["!disabled"])
                self.status.set("Previzualizare; verifică sursele și modifică textul. Nimic aplicat.")
            except Exception as exc:
                failed(exc)
        self.status.set("Recuperez datele relevante…")
        self.job = self.app.bridge.submit(retrieve, on_done=ready, on_error=failed, name="ai-productivity-context")

    def replace(self, text):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def source(self, _event=None):
        if self.bundle and self.sources.curselection():
            key = self.sources.get(self.sources.curselection()[0])
            open_source(self.app, self.ws.id, self.bundle.sources[key])

    def use(self):
        if self.app.ws is not self.ws or self.closed:
            return
        try:
            if self.batch:
                self.batch.check(self.ws)
            if self.mode == "day":
                from .planning import PlannerDialog
                dialog = PlannerDialog(self, self.app, preselected=self.selected)
                dialog.to_var.set(dialog.from_var.get())
                dialog.title("Previzualizare Planner — rezervări personale de timp")
                dialog.run()
            elif self.mode == "mail":
                if self.reply and confirm(self, "Înlocuiești subiectul și textul din editor? Destinatarii rămân cei verificați de tine; nu se trimite nimic."):
                    subject, _, body = self.text.get("1.0", "end-1c").partition("\n")
                    self.use_draft(subject, body.lstrip("\n"))
                    self.destroy()
            else:
                if not self.report:
                    return
                current = activity_report(self.ws, date.fromisoformat(self.report['first']), date.fromisoformat(self.report['last']))
                if report_fingerprint(current) != report_fingerprint(self.report):
                    raise ValueError("Datele raportului s-au schimbat; recalculează.")
                # MailDialog handles recipient validation and confirmation; route result through existing sender.
                from ..services.mail import MailDraft
                draft = MailDraft(to=[], subject=f"Raport {self.report['first']} — {self.report['last']}", body=self.text.get('1.0', 'end-1c'))
                self.app.compose_mail(ai_draft=draft, standalone=True)
        except Exception as exc:
            show_error(self, str(exc))

    def destroy(self):
        if self.closed:
            return
        self.cancel()
        self.closed = True
        self.app.ai.views.discard(self)
        super().destroy()
