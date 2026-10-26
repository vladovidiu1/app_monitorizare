"""Chat nemodal, inspector și revizuire comună; numai firul Tk aplică propuneri."""

from __future__ import annotations

import json
import re
import tkinter as tk
from tkinter import ttk

from ..ai.assistant_protocol import AssistantReply
from ..domain.labels import PRIORITY_LABELS, STATUS_LABELS, format_seconds
from ..domain.models import Kind
from ..errors import ValidationError
from ..services.assistant_context import build_context
from ..services.assistant_proposals import ProposalBatch, validate_reply
from .common import ModalDialog, ScrollFrame, confirm, show_error
from .inspector import InspectorTab

SCOPES = {"Task selectat": "task", "Proiect": "project", "Întreg workspace": "workspace"}
QUICK = {
    "Unde am rămas?": "Unde am rămas? Rezumă ultimele sesiuni și notițe, următorul pas salvat și blocajele. Nu propune modificări.",
    "Propune pași": "Transformă descrierea în maximum 3 subtaskuri concrete și o actualizare de checklist. Prezintă propuneri, nu le aplica.",
    "Rezumă proiectul": "Rezumă proiectul: starea taskurilor, progresul înregistrat și blocajele. Nu propune modificări.",
    "Pregătește e-mail": "Pregătește un e-mail scurt despre taskul selectat, bazat exclusiv pe surse. Întoarce o propunere email, fără trimitere și fără alte acțiuni.",
}
QUICK_INTENTS = dict(zip(QUICK, ("resume", "steps", "project_summary", "email")))
KINDS = {"create_task": "Creare task", "update_task": "Actualizare câmpuri", "add_note": "Adăugare notiță", "link_tasks": "Legătură între taskuri", "associate_mail": "Asociere mail–task"}
STATES = {"pending": "În așteptare", "started": "Rezervat — rezultat incert după întrerupere", "applied": "Aplicat",
          "needs_clarification": "Necesită clarificare / modificare",
          "rejected": "Respins", "conflict": "Conflict — recalculează", "uncertain": "Incert — verifică manual",
          "failed": "Neexecutat", "not_run": "Neexecutat", "already_recorded": "Deja înregistrat, fără repetare"}
FIELDS = {"title": "Titlu", "description": "Descriere", "parent_id": "Părinte", "note": "Notiță", "node_id": "Task",
    "reason": "Motiv", "text": "Text", "patch": "Modificări", "relation": "Tip legătură",
    "status": "Status", "priority": "Prioritate", "next_action": "Următorul pas", "waiting_reason": "Motiv blocaj",
    "due_date": "Termen (AAAA-LL-ZZ)", "due_at": "Termen cu oră", "estimated_minutes": "Estimare (minute)",
    "remaining_minutes": "Rămas (minute)", "tags": "Etichete", "checklist": "Checklist", "depends_on_ids": "Dependențe",
    "related_node_ids": "Legături"}
FIELDS.update(requested_by="Solicitant (propunere)", email_address="Adresă SMTP", name="Nume", confirmed_task_ids="Taskuri confirmate")


def human_values(values):
    if values is None:
        return "Nu există / înregistrare nouă"
    lines = []
    for key, value in values.items():
        if key == "status":
            value = STATUS_LABELS.get(value, value)
        elif key == "priority":
            value = PRIORITY_LABELS.get(value, value)
        elif key == "checklist" and isinstance(value, list):
            value = "\n" + "\n".join(("☑ " if item.get("done") else "☐ ") + item["text"] for item in value)
        elif isinstance(value, list):
            value = ", ".join(map(str, value)) or "—"
        elif isinstance(value, dict):
            value = "\n" + human_values(value)
        lines.append(f"{FIELDS.get(key, key)}: {'—' if value is None else value}")
    return "\n".join(lines)


def read_only_text(parent, text: str, height=10):
    field = tk.Text(parent, wrap="word", height=height)
    field.insert("1.0", text)
    field.configure(state="disabled")
    field.pack(fill="both", expand=True, padx=8, pady=8)
    return field


def open_source(app, workspace_id, source) -> None:
    try:
        if not app.ws or app.ws.id != workspace_id:
            raise ValidationError("Sursa aparține altui workspace.")
        if source.kind == "report":
            from datetime import date
            from ..services.ai_productivity import activity_report, report_text
            from ..services.assistant_context import validate_source
            validate_source(app.ws, source, {})
            window = tk.Toplevel(app.root)
            window.title("Sursă — raport calculat")
            window.geometry("750x550")
            read_only_text(window, report_text(activity_report(app.ws, date.fromisoformat(source.data["first"]), date.fromisoformat(source.data["last"]))))
            return
        if source.kind == "mail":
            app.show_view("mail_review")
            app.mail_page.select_message(source.record_id)
            return
        node = app.ws.get(source.node_id)
        if source.kind == "task":
            app.select_node(node.id, reveal=True)
            return
        store = {"note": app.ws.repo.notes_store(node.id), "session": app.ws.repo.sessions,
                 "history": app.ws.repo.history}[source.kind]
        record = store.get(source.record_id)
        if record.node_id != node.id:
            raise ValidationError("Înregistrarea nu aparține taskului citat.")
        app.select_node(node.id, reveal=True)
        app.inspector.show_tab("Jurnal")
        detail = tk.Toplevel(app.root)
        detail.title(f"Sursă — {node.title}")
        detail.geometry("650x450")
        ttk.Label(detail, text=f"{source.kind}: {record.id}\nTask: {node.title} [{node.id}]", wraplength=620).pack(anchor="w", padx=10, pady=10)
        data = record.model_dump(mode="json")
        read_only_text(detail, "\n".join(f"{FIELDS.get(key, key)}: {value}" for key, value in data.items() if value is not None))
    except Exception as exc:
        show_error(app.root, str(exc))


class AssistantPanel(ttk.Frame):
    def __init__(self, parent, app, node_getter=None) -> None:
        super().__init__(parent, padding=6)
        self.app, self.node_getter = app, node_getter or (lambda: app.selected_id)
        self._closed = False
        self._signature = None
        self._serial = 0
        self._request_id = None
        self._retrieval = None
        self._bundle = None
        self._reply = None
        self._batch = None
        self.history = []
        self.scope = tk.StringVar(value="Task selectat")
        scope_line = ttk.Frame(self)
        scope_line.pack(fill="x")
        ttk.Label(scope_line, text="Context:").pack(side="left")
        self.scope_box = ttk.Combobox(scope_line, textvariable=self.scope, values=list(SCOPES), state="readonly", width=18)
        self.scope_box.pack(side="left", padx=6)
        self.scope_box.bind("<<ComboboxSelected>>", lambda _e: self.on_selection())
        self.context_label = tk.StringVar()
        self.context_widget = ttk.Label(self, textvariable=self.context_label, wraplength=360)
        self.context_widget.pack(fill="x", pady=4)
        quick = ttk.Frame(self)
        quick.pack(fill="x")
        for index, title in enumerate(QUICK):
            ttk.Button(quick, text=title, command=lambda t=title: self.quick(t)).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2)
        quick.columnconfigure((0, 1), weight=1)
        transcript_frame = ttk.Frame(self)
        transcript_frame.pack(fill="both", expand=True, pady=5)
        self.transcript = tk.Text(transcript_frame, wrap="word", height=10, state="disabled")
        scroll = ttk.Scrollbar(transcript_frame, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        self.transcript.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.entry = tk.Text(self, height=3, wrap="word", undo=True)
        self.entry.pack(fill="x")
        self.entry.bind("<Control-Return>", lambda _e: (self.send(), "break")[1])
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=4)
        self.send_button = ttk.Button(buttons, text="Trimite", command=self.send)
        self.send_button.pack(side="left")
        ttk.Button(buttons, text="Anulează", command=self.cancel).pack(side="left", padx=4)
        self.review_button = ttk.Button(buttons, text="Propuneri…", command=self.review, state="disabled")
        self.review_button.pack(side="left", padx=4)
        self.email_button = ttk.Button(buttons, text="E-mail…", command=self.email, state="disabled")
        self.email_button.pack(side="left")
        ttk.Button(self, text="Istoric propuneri…", command=self.show_history).pack(anchor="w")
        self.status = tk.StringVar(value="Nicio modificare fără confirmare.")
        self.status_widget = ttk.Label(self, textvariable=self.status, wraplength=360)
        self.status_widget.pack(fill="x")
        self.bind("<Configure>", self.resize_labels, add="+")
        app.ai.views.add(self)
        self.on_selection()

    def resize_labels(self, event):
        width = max(180, event.width - 12)
        for widget in (self.context_widget, self.status_widget):
            if int(widget.cget("wraplength")) != width:
                widget.configure(wraplength=width)

    def signature(self):
        ws = self.app.ws
        scope = SCOPES[self.scope.get()]
        node_id = self.node_getter()
        if scope == "workspace":
            node_id = None
        elif scope == "project" and ws and node_id in ws.nodes:
            project = ws.nearest_project(node_id)
            node_id = project.id if project else None
        return (ws.id if ws else None, scope, node_id)

    def on_selection(self) -> None:
        if self._closed:
            return
        signature = self.signature()
        if signature != self._signature:
            self.cancel()
            self.history.clear()
            self._batch = self._reply = None
            self.review_button.state(["disabled"])
            self.email_button.state(["disabled"])
            self._signature = signature
        wsid, scope, node_id = signature
        ws = self.app.ws
        label = ws.get(node_id).title + f" [{node_id}]" if ws and node_id in ws.nodes else "niciun nod selectat"
        if scope == "workspace":
            label = (ws.name if ws else "niciun workspace") + " — înregistrări relevante, nu întregul conținut"
        self.context_label.set(f"{self.scope.get()}: {label}")

    def quick(self, title: str) -> None:
        if title == "Rezumă proiectul":
            self.scope.set("Proiect")
        elif title in ("Unde am rămas?", "Propune pași", "Pregătește e-mail"):
            self.scope.set("Task selectat")
        self.on_selection()
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", QUICK[title])
        self.send(intent=QUICK_INTENTS[title])

    def append(self, text: str, sources=None, bundle=None) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text + "\n")
        for key in sources or []:
            source = bundle.sources[key]
            tag = f"source-{self._serial}-{self.transcript.index('end')}"
            label = f"↗ {source.kind} {source.record_id} — task {source.node_id}\n"
            self.transcript.tag_configure(tag, foreground="#2878bf", underline=True)
            self.transcript.tag_bind(tag, "<Button-1>", lambda _e, s=source, w=bundle.workspace_id: open_source(self.app, w, s))
            self.transcript.insert("end", label, tag)
            # Deterministic facts remain visible beside generated interpretations.
            if source.kind == "task":
                facts = []
                data = source.data
                if data.get("status"):
                    facts.append("Status: " + STATUS_LABELS.get(data["status"], data["status"]))
                if data.get("due_date") or data.get("due_at"):
                    facts.append("Termen: " + (data.get("due_date") or data["due_at"]))
                if "actual_seconds" in data:
                    facts.append("Timp înregistrat: " + format_seconds(data["actual_seconds"]))
                if data.get("progress"):
                    p = data["progress"]
                    facts.append(f"Taskuri frunză finalizate: {p['done_leaves']} din {p['done_leaves'] + p['open_leaves']}")
                if data.get("next_action"):
                    facts.append("Următorul pas salvat: " + data["next_action"])
                if data.get("waiting_reason") or data.get("blocker_titles"):
                    facts.append("Blocaje: " + "; ".join(filter(None, [data.get("waiting_reason"), *data.get("blocker_titles", [])])))
                self.transcript.insert("end", "Date din sursă: " + "; ".join(facts) + "\n")
            elif source.kind == "note":
                self.transcript.insert("end", f"Notiță {source.data['at']}: {source.data['text']}\n")
            elif source.kind == "session":
                self.transcript.insert("end", f"Sesiune {source.data['start_at']} — {source.data['status']}; timp înregistrat: " +
                    format_seconds(source.data["actual_seconds"]) + "\n" + (source.data.get("summary") or source.data.get("note") or "") + "\n")
        self.transcript.insert("end", "\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def active(self, serial, ws, epoch) -> bool:
        return not self._closed and serial == self._serial and self.app.ws is ws and epoch == self.app.ai.epoch

    def send(self, intent=None) -> None:
        if self._request_id or self._retrieval:
            self.status.set("Anulează cererea curentă înainte de a trimite alta.")
            return
        question = self.entry.get("1.0", "end").strip()
        if not question:
            return
        if not self.app.ws or not self.app.config.ai.enabled:
            self.status.set("Deschide un workspace și activează AI din Setări → AI.")
            return
        if not self.app.confirm_leave():
            return
        self.on_selection()
        ws, epoch = self.app.ws, self.app.ai.epoch
        if intent is None:
            intent = ("resume" if re.search(r"unde am r[ăa]mas", question, re.IGNORECASE) else
                      "email" if re.search(r"^pregătește.*e-?mail", question, re.IGNORECASE) else
                      "actions" if re.search(r"^(?:te rog[, ]+)?(?:propune|creează|adaugă|actualizează|modifică|leagă|transformă)\b", question, re.IGNORECASE) else "chat")
        self._intent = intent
        scope, node_id = SCOPES[self.scope.get()], self.node_getter()
        self._serial += 1
        serial = self._serial
        self._batch = self._reply = None
        self.review_button.state(["disabled"])
        self.email_button.state(["disabled"])
        self.append("Tu: " + question)
        self.send_button.state(["disabled"])
        self.status.set("Selectez sursele relevante…")

        def ready(bundle):
            if not self.active(serial, ws, epoch):
                return
            self._retrieval = None
            self._bundle = bundle
            payload = json.loads(bundle.wire())
            payload["history"] = self.history[-4:]
            while len(json.dumps(payload, ensure_ascii=False)) > 30000 and payload["history"]:
                payload["history"].pop(0)
            try:
                if not bundle.sources:
                    from ..ai.protocol import Response
                    reply = AssistantReply(answer=[{"text": "Nu am găsit surse relevante în contextul ales. Schimbă contextul sau numele căutat.", "sources": []}])
                    self.receive(Response(request_id="00000000-0000-0000-0000-000000000000", kind="result", assistant=reply),
                                 serial, ws, epoch, question)
                    return
                self._request_id = self.app.ai.request(self.app.config.ai, "assistant", question,
                    json.dumps(payload, ensure_ascii=False),
                    lambda message: self.receive(message, serial, ws, epoch, question), intent=intent)
                self.status.set(f"AI local: {len(bundle.sources)} surse selectate; rezerva de răspuns este inclusă în buget.")
            except Exception as exc:
                failed(exc)

        def failed(exc):
            if self.active(serial, ws, epoch):
                self._request_id = self._retrieval = None
                self.send_button.state(["!disabled"])
                self.status.set(str(exc))
        self._retrieval = self.app.bridge.submit(lambda token: build_context(ws, scope, node_id, question, token),
            on_done=ready, on_error=failed, name="assistant-context")

    def receive(self, message, serial, ws, epoch, question) -> None:
        if not self.active(serial, ws, epoch):
            return
        if self._request_id and message.request_id != self._request_id:
            return
        if message.kind == "loading":
            self.status.set("Încarc modelul local…")
            return
        self._request_id = None
        self.send_button.state(["!disabled"])
        if message.kind == "error":
            self.status.set(message.error)
            return
        try:
            batch = ProposalBatch.prepare(ws, self._bundle, message.assistant, message.context_keys, self._intent)
        except Exception as exc:
            self.status.set(f"Răspuns respins; recalculează: {exc}")
            return
        self._reply, self._batch = message.assistant, batch
        for part in self._reply.answer:
            self.append("Asistent: " + part.text, part.sources, self._bundle)
        if self._intent == "resume":
            cited = {key for part in self._reply.answer for key in part.sources}
            recent = [key for key in message.context_keys if key not in cited and self._bundle.sources[key].kind in ("note", "session")]
            if recent:
                self.append("Ultimele înregistrări consultate (date salvate):", recent[:6], self._bundle)
        self.history.extend([{"role": "user", "text": question[:1500]},
                             {"role": "assistant", "text": " ".join(p.text for p in self._reply.answer)[:1500]}])
        self.history = self.history[-6:]
        if batch.items:
            self.review_button.state(["!disabled"])
        if self._reply.email:
            self.email_button.state(["!disabled"])
            self.append("Ciornă propusă (netrimisă): " + self._reply.email.subject + "\n" + self._reply.email.body,
                        self._reply.email.sources, self._bundle)
        omitted = len(message.context_keys) < len(self._bundle.sources) or self._bundle.truncated
        self.status.set(f"{len(message.context_keys)} surse folosite. " + ("Context parțial. " if omitted else "") +
                        f"{len(batch.items)} propuneri; verifică și confirmă înainte de aplicare.")

    def review(self) -> None:
        if self._batch and self._batch.items:
            ProposalReview(self.app, self._batch)

    def email(self) -> None:
        if not self._reply or not self._reply.email:
            return
        try:
            self._batch.check(self.app.ws)
            draft = self._reply.email
            if confirm(self, "Deschizi ciorna propusă în editorul de e-mail? Nimic nu se trimite automat."):
                self.app.compose_mail(draft.node_id, ai_draft=draft)
        except Exception as exc:
            show_error(self, str(exc))

    def show_history(self) -> None:
        ws, epoch = self.app.ws, self.app.ai.epoch
        if ws is None:
            return
        def show(events):
            if self._closed or self.app.ws is not ws or epoch != self.app.ai.epoch:
                return
            window = tk.Toplevel(self)
            window.title("Istoric propuneri AI")
            window.geometry("750x500")
            read_only_text(window, "\n\n".join(
                f"{e.at.isoformat()} — {e.id}\nStare: {STATES.get(e.data.get('state'), e.data.get('state'))}\n{e.data.get('detail', 'Rezultat incert; nu se repetă automat.')}\n"
                + KINDS.get(e.data.get("operation", {}).get("kind"), "Propunere") + "\n"
                + human_values({k: v for k, v in e.data.get("operation", {}).items() if k not in ("kind", "sources")})
                for e in events) or "Nicio propunere înregistrată.")
        self.app.bridge.submit(lambda token: [e for e in ws.list_history() if e.type == "ai_proposal"][:100],
                               on_done=show, on_error=lambda e: self.status.set(str(e)) if not self._closed and self.app.ws is ws and epoch == self.app.ai.epoch else None,
                               name="assistant-history")

    def cancel(self) -> None:
        was_busy = self._retrieval is not None or self._request_id is not None
        self._serial += 1
        if self._retrieval:
            self._retrieval.cancel()
            self._retrieval = None
        if self._request_id:
            self.app.ai.cancel(self._request_id)
            self._request_id = None
        self.send_button.state(["!disabled"])
        if was_busy:
            self.status.set("Cerere anulată. Nicio propunere nu a fost aplicată.")

    def workspace_changed(self) -> None:
        self.cancel()
        self._batch = self._reply = self._bundle = None
        self.history.clear()
        self.review_button.state(["disabled"])
        self.email_button.state(["disabled"])
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._signature = None
        self.context_label.set("Context invalidat; selectează un task sau un workspace.")
        self.status.set("Workspace schimbat; contextul și rezultatele anterioare au fost invalidate.")

    def destroy(self) -> None:
        if not self._closed:
            self.cancel()
            self._closed = True
            self.app.ai.views.discard(self)
        super().destroy()


class AssistantWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Asistent FocusDesk — AI local")
        self.geometry("850x780")
        self.transient(app.root)
        self.panel = AssistantPanel(self, app)
        self.panel.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # Deliberately no grab_set or wait_window: chat remains nonmodal.

    def destroy(self):
        self.app.assistant_window = None
        super().destroy()


class AssistantTab(InspectorTab):
    title = "Asistent"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.panel = AssistantPanel(self, app, lambda: self.node_id)
        self.panel.pack(fill="both", expand=True)

    def load(self, node):
        super().load(node)
        self.panel.on_selection()

    def applies_to(self, node):
        return node.kind in (Kind.TASK, Kind.PROJECT)


class EditOperationDialog(ModalDialog):
    def __init__(self, parent, app, batch, index):
        super().__init__(parent, "Modifică propunerea", resizable=True, ok_text="Păstrează modificările")
        self.app, self.batch, self.index = app, batch, index
        self.payload = batch.items[index].operation.model_dump(exclude_unset=True)
        self.geometry("680x650")
        sf = ScrollFrame(self.body)
        sf.pack(fill="both", expand=True)
        self.form = sf.inner
        self.editors = {}
        kind = self.payload["kind"]
        fields = {"create_task": ["title", "description", "checklist", "due_date", "requested_by"], "add_note": ["text"],
                  "link_tasks": ["relation"], "associate_mail": []}.get(kind, list(self.payload.get("patch", {})))
        values = self.payload.get("patch", self.payload)
        for key in fields:
            value = values.get(key, [] if key == "checklist" else "")
            ttk.Label(self.form, text=FIELDS.get(key, {"text": "Text", "relation": "Tip legătură"}.get(key, key))).pack(anchor="w", pady=(8, 2))
            include = tk.BooleanVar(value=True)
            if kind == "update_task":
                ttk.Checkbutton(self.form, text="Modifică acest câmp", variable=include).pack(anchor="w")
            mapping = None
            if key in ("status", "priority", "relation"):
                mapping = ({v: k.value for k, v in STATUS_LABELS.items()} if key == "status" else
                           {v: k.value for k, v in PRIORITY_LABELS.items()} if key == "priority" else
                           {"Legătură": "related", "Dependență": "depends_on"})
                var = tk.StringVar(value=next((label for label, raw in mapping.items() if raw == value), ""))
                widget = ttk.Combobox(self.form, textvariable=var, values=list(mapping), state="readonly")
                widget.pack(fill="x")
                getter = var.get
            else:
                widget = tk.Text(self.form, height=4 if key in ("text", "description", "checklist") else 2, wrap="word")
                if key == "checklist":
                    text = "\n".join(("[x] " if item.get("done") else "[ ] ") + item["text"] for item in value or [])
                elif key == "tags":
                    text = ", ".join(value or [])
                elif key == "requested_by":
                    text = f"{value['name']} <{value['email_address']}>" if value else ""
                else:
                    text = "" if value is None else str(value)
                widget.insert("1.0", text)
                widget.pack(fill="x")
                getter = lambda w=widget: w.get("1.0", "end").strip()
            self.editors[key] = (include, getter, mapping)

    def validate(self):
        try:
            payload = dict(self.payload)
            values = {}
            for key, (include, getter, mapping) in self.editors.items():
                if not include.get():
                    continue
                value = getter()
                if mapping:
                    value = mapping.get(value)
                elif key in ("estimated_minutes", "remaining_minutes"):
                    value = int(value) if value else None
                elif key == "tags":
                    value = [part.strip() for part in value.split(",") if part.strip()]
                elif key == "checklist":
                    value = [{"text": line.removeprefix("[x]").removeprefix("[ ]").strip(), "done": line.startswith("[x]")}
                             for line in value.splitlines() if line.strip()]
                elif key == "due_date":
                    value = value or None
                elif key == "requested_by":
                    from email.utils import parseaddr
                    name, address = parseaddr(value)
                    value = {"name": name or address, "email_address": address} if value else None
                values[key] = value
            if payload["kind"] == "update_task":
                payload["patch"] = values
            else:
                payload.update(values)
            self.batch.edit(self.app.ws, self.index, payload)
            return True
        except Exception as exc:
            show_error(self, str(exc))
            return False

    def collect(self):
        return True


class ProposalReview(tk.Toplevel):
    def __init__(self, app, batch, on_change=None):
        super().__init__(app.root)
        self.app, self.batch = app, batch
        self.on_change = on_change
        self.title("Revizuire propuneri AI — fără aplicare automată")
        self.geometry("850x680")
        self.transient(app.root)
        self.tree = ttk.Treeview(self, columns=("action", "state"), show="headings", height=5)
        self.tree.heading("action", text="Acțiune / țintă")
        self.tree.heading("state", text="Stare")
        self.tree.pack(fill="x", padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_item())
        self.content = tk.Text(self, wrap="word", state="disabled", height=15)
        self.content.pack(fill="both", expand=True, padx=10)
        self.sources = ttk.Frame(self)
        self.sources.pack(fill="x", padx=10, pady=5)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=10)
        self.accept_button = ttk.Button(buttons, text="Acceptă selecția…", command=lambda: self.accept([self.index()]))
        self.accept_button.pack(side="left")
        self.edit_button = ttk.Button(buttons, text="Modifică…", command=self.edit)
        self.edit_button.pack(side="left", padx=6)
        self.reject_button = ttk.Button(buttons, text="Respinge", command=self.reject)
        self.reject_button.pack(side="left")
        ttk.Button(buttons, text="Acceptă toate în așteptare…", command=self.accept).pack(side="right")
        self.status = tk.StringVar(value="Verifică înainte/după, motivul și sursele fiecărei acțiuni.")
        ttk.Label(self, textvariable=self.status, wraplength=800).pack(fill="x", padx=10, pady=8)
        self.refresh()

    def index(self):
        selected = self.tree.selection()
        return int(selected[0]) if selected else 0

    def refresh(self):
        selected = self.index()
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, item in enumerate(self.batch.items):
            target = getattr(item.operation, "node_id", getattr(item.operation, "parent_id", None))
            label = self.app.ws.nodes[target].title if self.app.ws and self.app.ws.id == self.batch.bundle.workspace_id and target in self.app.ws.nodes else target or "Rădăcină"
            self.tree.insert("", "end", iid=str(i), values=(f"{KINDS[item.operation.kind]} — {label}", STATES.get(item.state, item.state)))
        if self.batch.items:
            self.tree.selection_set(str(selected))
        self.show_item()

    def show_item(self):
        if not self.batch.items:
            return
        item = self.batch.items[self.index()]
        try:
            preview = self.batch.preview(self.app.ws, [item])[0] if item.state == "pending" else None
            text = f"Motiv: {item.operation.reason}\nStare: {STATES.get(item.state, item.state)}\n{item.detail}\n"
            if preview:
                for title, values in (("ÎNAINTE", preview["before"]), ("DUPĂ ACCEPTARE", preview["after"])):
                    text += f"\n{title}\n" + human_values(values) + "\n"
            enabled = item.state == "pending"
        except Exception as exc:
            text, enabled = f"Recalculare necesară: {exc}", False
        self.content.configure(state="normal")
        self.content.delete("1.0", "end")
        self.content.insert("1.0", text)
        self.content.configure(state="disabled")
        for button in (self.accept_button, self.edit_button):
            button.state(["!disabled" if enabled else "disabled"])
        self.reject_button.state(["!disabled" if item.state == "pending" and self.app.ws and self.app.ws.id == self.batch.bundle.workspace_id else "disabled"])
        for child in self.sources.winfo_children():
            child.destroy()
        for key in item.operation.sources:
            source = self.batch.bundle.sources[key]
            ttk.Button(self.sources, text=f"Sursă: {source.kind} {source.record_id}", command=lambda s=source:
                open_source(self.app, self.batch.bundle.workspace_id, s)).pack(anchor="w")

    def accept(self, indices=None):
        indices = indices if indices is not None else [i for i, item in enumerate(self.batch.items) if item.state == "pending"]
        indices = [i for i in indices if self.batch.items[i].state == "pending"]
        if not indices:
            return
        results = None
        try:
            if not self.app.confirm_leave():
                return
            self.batch.preview(self.app.ws, [self.batch.items[i] for i in indices])
            ws, epoch = self.app.ws, self.app.ai.epoch
            if not confirm(self, f"Aplici {len(indices)} propuneri afișate? Operațiile pot reuși parțial; rezultatul fiecăreia va fi raportat."):
                return
            if self.app.ws is not ws or self.app.ai.epoch != epoch:
                raise ValidationError("Workspace-ul s-a schimbat înainte de confirmare; recalculează.")
            results = self.batch.apply(self.app.ws, indices)
            if self.on_change:
                self.on_change(self.batch)
            self.status.set("; ".join(f"{STATES.get(row['state'], row['state'])}: {row['detail']}" for row in results))
            self.app.refresh_all()
            self.refresh()
        except Exception as exc:
            if results is None:
                self.status.set(f"Nu s-a aplicat lotul: {exc}")
            else:
                self.status.set("; ".join(f"{STATES.get(row['state'], row['state'])}: {row['detail']}" for row in results) +
                                f"; reîmprospătarea interfeței a eșuat: {exc}")

    def edit(self):
        if EditOperationDialog(self, self.app, self.batch, self.index()).run():
            if self.on_change:
                self.on_change(self.batch)
            self.refresh()

    def reject(self):
        try:
            self.batch.reject(self.app.ws, self.index())
            if self.on_change:
                self.on_change(self.batch)
            self.refresh()
        except Exception as exc:
            self.status.set(str(exc))
