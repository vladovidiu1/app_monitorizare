"""Monitorizare prin ComWorker existent și pagină separată de Inbox-ul taskurilor."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
import time
import tkinter as tk
from tkinter import ttk

from ..domain.settings import MailMonitorSettings
from ..services.mail_monitor import MailMonitorService
from ..services.mail_analysis import build_mail_context, project_analysis, restore_batch, save_batch, reconcile
from .assistant_ui import ProposalReview
from .common import confirm, show_error

LABELS = {"pending": "De analizat", "proposed": "Propuneri neconfirmate", "clarify": "Necesită clarificare",
    "informational": "Informativ (estimare AI)", "handled": "Tratat", "rejected": "Respins", "ignored": "Ignorat", "error": "Eroare / verificare manuală"}


class MailWatchController:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.serial = 0
        self.next_due = 0
        self.status = "Monitorizare dezactivată."

    def invalidate(self, clear_selection=False):
        self.serial += 1
        self.active = False
        self.next_due = 0
        self.app.mail_page.cancel_analysis()
        if clear_selection:
            page = self.app.mail_page
            page.message_id = None
            page.tree.delete(*page.tree.get_children())
            page.text.configure(state="normal")
            page.text.delete("1.0", "end")
            page.text.configure(state="disabled")

    def tick(self):
        ws = self.app.ws
        if ws and ws.settings.mail_monitor.enabled and not ws.read_only and not self.active and time.monotonic() >= self.next_due:
            self.scan()

    def scan(self):
        ws = self.app.ws
        worker = self.app.outlook.worker
        if not ws or not ws.settings.mail_monitor.enabled or ws.read_only:
            self.status = "Activează monitorizarea și alege contul/folderele în Setări."
            return
        if self.active or worker.busy or worker.blocked:
            self.status = "Outlook COM este ocupat/blocat; nu pornesc o scanare suprapusă."
            self.next_due = time.monotonic() + 5
            return
        self.active = True
        self.serial += 1
        serial = self.serial
        epoch = self.app.ai.epoch
        budget = [ws.settings.mail_monitor.max_per_check]
        finished = set()
        service = MailMonitorService(ws)

        def valid():
            return self.app.ws is ws and self.serial == serial and self.app.ai.epoch == epoch and ws.settings.mail_monitor.enabled

        def finish(status):
            if valid():
                self.active = False
                self.status = status
                self.next_due = time.monotonic() + ws.settings.mail_monitor.interval_seconds
                self.app.mail_page.refresh()

        def failed(exc):
            if valid():
                state = ws.mail_state()
                state.next_folder += 1
                ws.save_mail_state(state)
                finish(f"Outlook Classic indisponibil ({type(exc).__name__}). Checkpoint păstrat; fără modificări în mailbox.")

        def next_page():
            if not valid():
                return
            if budget[0] <= 0:
                finish("Lot verificat; următoarea verificare respectă intervalul configurat.")
                return
            try:
                plan = service.plan(budget=budget[0])
                if plan["key"] in finished:
                    state = ws.mail_state()
                    state.next_folder += 1
                    ws.save_mail_state(state)
                    self.app.root.after(0, next_page)
                    return
                self.status = "Citesc metadatele unui lot Outlook…"
                def headers_ready(page):
                    if not valid():
                        return
                    try:
                        locators = service.details_needed(plan, page)
                        def commit(details):
                            if not valid():
                                return
                            try:
                                service.commit(plan, page, details)
                                budget[0] -= max(1, page.get("consumed", len(page["headers"])))
                                if page["done"]:
                                    finished.add(plan["key"])
                                if len(finished) >= len(ws.settings.mail_monitor.folders) or budget[0] <= 0:
                                    finish("Scanare încheiată; stările și deduplicarea sunt salvate local.")
                                else:
                                    self.app.root.after(0, next_page)
                            except Exception as exc:
                                failed(exc)
                        if locators:
                            worker.submit(lambda backend: backend.read_mail_details(locators), commit, failed,
                                          timeout_s=30, name="mail-read-details")
                        else:
                            commit([])
                    except Exception as exc:
                        failed(exc)
                worker.submit(lambda backend: backend.scan_mail_page(plan), headers_ready, failed,
                              timeout_s=30, name="mail-read-page")
            except Exception as exc:
                failed(exc)
        next_page()


class MailSettingsPanel(ttk.Frame):
    def __init__(self, parent, dialog):
        super().__init__(parent, padding=10)
        self.dialog = dialog
        self.app = dialog.app
        self.closed = False
        self.config_value = dialog.s.mail_monitor.model_copy(deep=True)
        self.enabled = tk.BooleanVar(value=self.config_value.enabled)
        self.values = {}
        ttk.Checkbutton(self, text="Activează explicit monitorizarea Outlook Classic", variable=self.enabled).pack(anchor="w")
        self.selection_label = tk.StringVar(value=self._label())
        ttk.Label(self, textvariable=self.selection_label, wraplength=620).pack(fill="x", pady=5)
        ttk.Button(self, text="Alege contul și folderele…", command=self.choose).pack(anchor="w")
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=8)
        fields = [("interval_seconds", "Interval verificare (secunde)"), ("first_days", "Inițial: ultimele zile (dacă De la este gol)"),
            ("first_since", "Inițial: De la (AAAA-LL-ZZ, opțional)"), ("first_until", "Inițial: Până la (AAAA-LL-ZZ, opțional)"),
            ("first_max", "Maxim inițial / folder"), ("page_size", "Mailuri / pagină"), ("max_per_check", "Maxim / verificare")]
        for row, (key, label) in enumerate(fields):
            value = getattr(self.config_value, key)
            var = tk.StringVar(value=str(value) if value is not None else "")
            self.values[key] = var
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(grid, textvariable=var, width=16).grid(row=row, column=1, padx=5)
        ttk.Label(self, wraplength=620, text="Nu se marchează citit, mută sau șterge nimic. Analiza AI se pornește explicit din Mailuri de analizat. "
            "Intervalul inițial se aplică folderelor încă nescanate; pentru reluare explicită folosește Resetează intervalul din pagină.").pack(fill="x", pady=6)

    def _label(self):
        c = self.config_value
        return (c.mailbox + ": " + "; ".join(f.path for f in c.folders)) if c.folders else "Niciun cont/folder ales; nu se importă nimic implicit."

    def choose(self):
        worker = self.app.outlook.worker
        if worker.busy or worker.blocked:
            self.selection_label.set("COM ocupat/blocat; reîncearcă după încheierea apelului curent.")
            return
        def done(rows):
            if self.closed:
                return
            window = tk.Toplevel(self)
            window.title("Selectează folderele unui singur cont")
            window.geometry("650x450")
            tree = ttk.Treeview(window, columns=("folder",), show="headings", selectmode="extended")
            tree.heading("folder", text="Cont / cale folder (maximum 10)")
            tree.pack(fill="both", expand=True)
            for index, row in enumerate(rows):
                tree.insert("", "end", iid=str(index), values=(row["mailbox"] + " / " + row["path"],))
            def select():
                try:
                    chosen = [rows[int(index)] for index in tree.selection()]
                    if not chosen or len(chosen) > 10 or len({f["store_id"] for f in chosen}) != 1:
                        raise ValueError("Alege 1–10 foldere din același cont.")
                    from ..domain.mail_monitor import FolderChoice
                    self.config_value = MailMonitorSettings.model_validate({**self.config_value.model_dump(),
                        "store_id": chosen[0]["store_id"], "mailbox": chosen[0]["mailbox"], "folders": chosen})
                    self.selection_label.set(self._label())
                    window.destroy()
                except Exception as exc:
                    show_error(window, str(exc))
            ttk.Button(window, text="Folosește selecția", command=select).pack(pady=6)
        worker.submit(lambda backend: backend.list_mail_folders(), done,
            lambda _exc: self.selection_label.set("Deschide Outlook Classic conectat. New Outlook nu suportă COM.") if not self.closed else None,
            timeout_s=30, name="mail-folders")

    def collect(self, settings):
        data = self.config_value.model_dump()
        data["enabled"] = self.enabled.get()
        for key, var in self.values.items():
            text = var.get().strip()
            data[key] = date.fromisoformat(text) if text and key in ("first_since", "first_until") else None if key in ("first_since", "first_until") else int(text)
        settings.mail_monitor = MailMonitorSettings.model_validate(data)

    def destroy(self):
        self.closed = True
        super().destroy()


class MailReviewPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.message_id = None
        self.request_id = None
        self.job = None
        self.serial = 0
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Mailuri de analizat — Outlook Classic", style="Section.TLabel").pack(side="left")
        ttk.Button(top, text="Verifică acum", command=lambda: app.mail_watch.scan()).pack(side="right")
        self.include_ignored = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Arată și conversațiile ignorate", variable=self.include_ignored, command=self.refresh).pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("subject", "sender", "state"), show="headings", height=7)
        for key, label in (("subject", "Subiect"), ("sender", "SMTP expeditor"), ("state", "Stare locală")):
            self.tree.heading(key, text=label)
        self.tree.pack(fill="x", pady=5)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.select_message(self.tree.selection()[0]) if self.tree.selection() else None)
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        for index, (label, command) in enumerate((("Analizează local…", self.analyze), ("Propuneri…", self.review), ("Respinge mailul", self.reject),
                ("Ignoră conversația…", self.ignore), ("Reia conversația…", self.unignore), ("Anulează analiza", self.cancel_analysis),
                ("Resetează intervalul…", self.reset_cursor))):
            ttk.Button(controls, text=label, command=command).grid(row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2)
        controls.columnconfigure((0, 1), weight=1)
        self.text = tk.Text(self, wrap="word", state="disabled", height=16)
        self.text.pack(fill="both", expand=True, pady=5)
        self.status = tk.StringVar(value="Monitorizare dezactivată; configurează Setări → Mailuri.")
        ttk.Label(self, textvariable=self.status, wraplength=1000).pack(fill="x")

    def refresh(self):
        if not self.app.ws:
            return
        selected = self.message_id
        rows = sorted(self.app.ws.mail_records(), key=lambda r: r.header.received_at, reverse=True)
        self.tree.delete(*self.tree.get_children())
        ignored = set(self.app.ws.mail_state().ignored_conversations)
        for record in rows[:500]:
            if (record.state == "ignored" or record.header.conversation_key in ignored) and not self.include_ignored.get():
                continue
            self.tree.insert("", "end", iid=record.id, values=(record.header.subject, record.header.sender_smtp or "SMTP nerezolvat", LABELS[record.state]))
        self.status.set(self.app.mail_watch.status)
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)

    def select_message(self, message_id):
        if not self.app.ws:
            return
        message = self.app.ws.mail_get(message_id)
        if message is None:
            return
        if self.message_id != message_id:
            self.cancel_analysis()
        self.message_id = message_id
        body = (f"Mail sursă: {message.id}\n{message.header.subject}\nDe la: {message.header.sender_name} <{message.header.sender_smtp or 'SMTP necunoscut'}>\n"
            f"Data mesajului: {message.header.sent_at.isoformat()}\nStare locală: {LABELS[message.state]}\n"
            f"Taskuri confirmate pentru ACEST mail: {', '.join(message.confirmed_task_ids) or 'niciunul'}\n\n{message.body}\n\n"
            "Atașamente (numai metadate):\n" + "\n".join(f"{a.filename} — {a.size} octeți" for a in message.attachments))
        if message.analysis:
            body += "\n\nESTIMARE AI — neconfirmată:\n" + message.analysis["summary"]
            body += "\nFragment justificativ: «" + message.analysis["evidence_quote"] + "»"
            if message.analysis.get("deadline_quote"):
                from ..services.mail_analysis import resolve_deadline
                due, issue = resolve_deadline(message.analysis["deadline_quote"], message.header.sent_at, self.app.ws.settings.timezone)
                body += f"\nTermen din «{message.analysis['deadline_quote']}»: {due or issue}; fus {self.app.ws.settings.timezone}."
            body += "\nResponsabil/prioritate: neextrase; prioritatea Normală a unui task nou este implicită aplicației, nu o afirmație din mail."
        if message.body_truncated:
            body += "\nText trunchiat la limita locală; verifică originalul pentru restul conținutului."
        if not message.header.internet_id and not message.header.search_key:
            body += "\nIdentitate slabă (EntryID): mutarea poate schimba identificatorul și necesita verificare manuală."
        if message.clarification:
            body += "\n\nCLARIFICĂRI:\n" + "\n".join(message.clarification)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", body)
        self.text.configure(state="disabled")

    def analyze(self):
        ws = self.app.ws
        if not ws or not self.message_id or self.request_id or self.job:
            return
        if ws.read_only or not self.app.config.ai.enabled:
            self.status.set("Necesită workspace editabil și AI activat în Setări.")
            return
        message = ws.mail_get(self.message_id)
        if message is None:
            return
        if message.state == "ignored" or message.header.conversation_key in ws.mail_state().ignored_conversations:
            self.status.set("Reia explicit conversația înainte de analiză.")
            return
        if message.analysis and not confirm(self, "Reanalizezi explicit? Verifică istoricul înainte de a genera propuneri noi; scanarea nu resetează deciziile."):
            return
        if message.state in ("rejected", "handled", "informational", "error"):
            message.state = "pending"
            ws.save_mail_record(message)
        self.serial += 1
        serial, epoch, message_id = self.serial, self.app.ai.epoch, message.id
        def valid():
            return self.app.ws is ws and epoch == self.app.ai.epoch and serial == self.serial
        def fail(_exc):
            if valid():
                self.job = self.request_id = None
                self.status.set("Analiza a eșuat; niciun task modificat. Verifică motorul/modelul sau încarcă mailul din nou.")
        def ready(result):
            if not valid():
                return
            self.job = None
            bundle, payload = result
            try:
                def received(response):
                    if not valid():
                        return
                    if response.kind == "loading":
                        self.status.set("Încarc motorul local…")
                        return
                    self.request_id = None
                    if response.kind == "error":
                        fail(None)
                        return
                    try:
                        project_analysis(ws, message_id, response.mail_analysis, bundle, response.mail_candidate_ids, response.mail_body_chars)
                        self.refresh()
                        self.select_message(message_id)
                        self.status.set("Analiză locală salvată ca estimare. Revizuiește Propuneri înainte de acceptare.")
                    except Exception:
                        self.status.set("Analiză respinsă: fragment/ID invalid sau sursă schimbată. Cere clarificare/reanalizează.")
                self.request_id = self.app.ai.request(self.app.config.ai, "analyze_mail", "Analizează mailul cu dovezi literale.",
                    json.dumps(payload, ensure_ascii=False), received)
            except Exception:
                fail(None)
        def prepare():
            if valid():
                self.job = self.app.bridge.submit(lambda token: build_mail_context(ws, message_id, token), on_done=ready, on_error=fail, name="mail-context")
        if not message.body_loaded:
            worker = self.app.outlook.worker
            if worker.busy or worker.blocked:
                self.status.set("COM ocupat; încarcă mailul mai târziu.")
                return
            def loaded(details):
                if valid() and details:
                    from ..domain.mail_monitor import AttachmentMeta
                    from ..services.mail_monitor import content_hash
                    record = ws.mail_get(message_id)
                    record.body = details[0]["body"][:12000]
                    record.body_loaded = True
                    record.attachments = [AttachmentMeta.model_validate(a) for a in details[0].get("attachments", [])]
                    record.content_hash = content_hash(record)
                    record.content_version += 1
                    ws.save_mail_record(record)
                    prepare()
            worker.submit(lambda backend: backend.read_mail_details([{"store_id": message.header.store_id, "entry_id": message.header.entry_id}]), loaded, fail,
                          timeout_s=30, name="mail-explicit-load")
        else:
            prepare()

    def review(self):
        if not self.message_id:
            return
        try:
            message_id, ws = self.message_id, self.app.ws
            batch = restore_batch(ws, message_id)
            if batch is None or not batch.items:
                self.status.set("Nu există propuneri; analizează mailul sau cere clarificări.")
                return
            ProposalReview(self.app, batch, on_change=lambda value: (save_batch(ws, message_id, value), self.refresh(), self.select_message(message_id)))
        except Exception:
            self.status.set("Propunere învechită sau deja tratată; verifică istoricul și reanalizează explicit.")

    def reject(self):
        if not self.message_id:
            return
        self.cancel_analysis()
        try:
            ws, message_id = self.app.ws, self.message_id
            batch = restore_batch(ws, message_id)
            if batch:
                for index, item in enumerate(batch.items):
                    if item.state == "pending":
                        batch.reject(ws, index)
            record = ws.mail_get(message_id)
            record.state = "rejected"
            ws.save_mail_record(record)
            self.refresh()
            self.select_message(message_id)
        except Exception:
            self.status.set("Nu pot respinge; verifică istoricul. Nu s-a retrimis nicio acțiune.")

    def ignore(self):
        if self.message_id and confirm(self, "Ignori explicit conversația din acest mailbox? ConversationID poate grupa și mesaje despre taskuri diferite. Mailurile Outlook nu se modifică."):
            MailMonitorService(self.app.ws).ignore_conversation(self.message_id)
            self.cancel_analysis()
            self.refresh()

    def unignore(self):
        if self.message_id and confirm(self, "Reiei explicit conversația? Deciziile anterioare rămân în istoric."):
            MailMonitorService(self.app.ws).ignore_conversation(self.message_id, False)
            self.refresh()

    def reset_cursor(self):
        if self.app.ws and confirm(self, "Resetezi numai intervalele/cursorii pentru o scanare inițială nouă? Mailurile și deciziile salvate rămân deduplicate."):
            state = self.app.ws.mail_state()
            self.app.mail_watch.invalidate()
            state.cursors.clear()
            self.app.ws.save_mail_state(state)
            self.app.mail_watch.next_due = 0

    def cancel_analysis(self):
        self.serial += 1
        if self.job:
            self.job.cancel()
        if self.request_id:
            self.app.ai.cancel(self.request_id)
        self.job = self.request_id = None
