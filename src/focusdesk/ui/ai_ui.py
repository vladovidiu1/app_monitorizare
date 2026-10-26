"""UI AI: Tk doar pe firul principal; generare, previzualizare, confirmare explicită."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, ttk
from uuid import uuid4

from ..ai.models import default_model_path, validate_location
from ..ai.process import EngineProcess
from ..ai.protocol import EngineSettings, Request
from ..config import AiConfig
from ..errors import ValidationError
from ..services.ai_actions import ActionContext, apply_proposal, validate_proposal
from .common import confirm, show_error

OPERATIONS = {
    "Propune un subtask": "create_subtask",
    "Propune o notiță": "add_note",
    "Propune următorul pas": "set_next_action",
}


class AiController:
    def __init__(self, app) -> None:
        self.app = app
        self.engine = None
        self.request_id = None
        self.views = set()
        self.epoch = 0

    def selection_changed(self) -> None:
        for view in tuple(self.views):
            view.on_selection()

    def invalidate_workspace(self) -> None:
        self.epoch += 1
        for view in tuple(self.views):
            view.workspace_changed()
        self.cancel()

    def request(self, config: AiConfig, action, instruction, context, callback, *, intent="chat") -> str:
        settings = EngineSettings.model_validate(config.model_dump(exclude={"enabled"}))
        if not settings.model_path:
            settings.model_path = str(default_model_path())
        request = Request(request_id=str(uuid4()), action=action, intent=intent, instruction=instruction, context=context)
        if self.engine and self.engine.settings != settings:
            if self.engine.busy:
                raise RuntimeError("Anulează cererea AI activă înainte de a schimba setările.")
            self.engine.close()
            self.engine = None
        if self.engine is None:
            self.engine = EngineProcess(settings, self.app.bridge.post)
        self.engine.submit(request, callback)
        self.request_id = request.request_id
        return request.request_id

    def cancel(self, request_id=None) -> None:
        if self.engine and (request_id is None or request_id == self.request_id):
            self.engine.cancel()

    def close(self) -> None:
        for view in tuple(self.views):
            view.cancel()
        window = getattr(self.app, "ai_window", None)
        if window and not window._closed:
            window.cancel()
        if self.engine:
            self.engine.close()
            self.engine = None


class AiSettingsPanel(ttk.Frame):
    def __init__(self, parent, app) -> None:
        super().__init__(parent, padding=12)
        self.app = app
        self._closed = False
        self._request_id = None
        config = app.config.ai
        self.enabled = tk.BooleanVar(value=config.enabled)
        self.path = tk.StringVar(value=config.model_path or str(default_model_path()))
        self.context = tk.StringVar(value=str(config.context))
        self.threads = tk.StringVar(value=str(config.threads))
        self.timeout = tk.StringVar(value=str(config.timeout))
        self.status = tk.StringVar(value="Model neîncărcat. Testul verifică SHA256 și pornește inferența CPU.")
        self.columnconfigure(1, weight=1)
        ttk.Checkbutton(self, text="Activează AI local", variable=self.enabled).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Label(self, text="Model GGUF").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.path).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="Alege…", command=self.pick).grid(row=1, column=2)
        for row, (label, var) in enumerate((("Context (tokeni)", self.context),
                                            ("Fire CPU", self.threads), ("Timeout (secunde)", self.timeout)), 2):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(self, textvariable=var, width=10).grid(row=row, column=1, sticky="w", padx=6)
        controls = ttk.Frame(self)
        controls.grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        self.test_button = ttk.Button(controls, text="Testează modelul", command=self.test)
        self.test_button.pack(side="left")
        ttk.Button(controls, text="Anulează testul", command=self.cancel).pack(side="left", padx=8)
        ttk.Button(controls, text="Oprește motorul", command=self.stop).pack(side="left")
        ttk.Label(self, textvariable=self.status, wraplength=580).grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(self, wraplength=580, text=(
            "Procesare locală pe CPU, fără server sau GPU. Modelul (~5 GB) este furnizat separat împreună "
            "cu aplicația. Selectează fișierul GGUF și păstrează-l în models/ lângă executabil, în afara workspace-ului. "
            "Aplicația funcționează și fără AI. Pentru 8B se recomandă cel puțin 12–16 GB RAM liberă.")
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=14)

    def pick(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Model GGUF", filetypes=[("GGUF", "*.gguf")])
        if path:
            self.path.set(path)

    def collect(self) -> AiConfig:
        path = self.path.get().strip()
        if path:
            from pathlib import Path

            path = str(validate_location(Path(path)))
        return AiConfig(enabled=self.enabled.get(), model_path=path, context=int(self.context.get()),
                        threads=int(self.threads.get()), timeout=int(self.timeout.get()))

    def test(self) -> None:
        try:
            config = self.collect()
            self._request_id = self.app.ai.request(config, "add_note", "Scrie o notiță foarte scurtă: Model local OK.",
                                                  "Test de conectivitate locală, fără scriere în workspace.", self.on_message)
        except Exception as exc:
            self.status.set(str(exc))
            return
        self.test_button.state(["disabled"])
        self.status.set("Pornire proces AI…")

    def on_message(self, message) -> None:
        if self._closed or message.request_id != self._request_id:
            return
        if message.kind == "loading":
            self.status.set("Verificare SHA256, încărcare model și inferență CPU…")
        else:
            self.test_button.state(["!disabled"])
            self._request_id = None
            self.status.set("Model verificat, răspuns: " + message.proposal.text if message.kind == "result" else message.error)

    def cancel(self) -> None:
        if self._request_id:
            self.app.ai.cancel(self._request_id)
            self._request_id = None
            self.status.set("Test anulat; procesul AI se oprește.")
            self.test_button.state(["!disabled"])

    def stop(self) -> None:
        self.cancel()
        self.app.ai.close()
        self.status.set("Motor oprit; memoria modelului este eliberată.")

    def destroy(self) -> None:
        self.cancel()
        self._closed = True
        super().destroy()


class AiWindow(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app.root)
        self.app = app
        self.title("AI local — propuneri")
        self.geometry("720x640")
        self.transient(app.root)
        self._closed = False
        self._request_id = None
        self._context = None
        self._proposal = None
        self._applied = False
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        self.target = tk.StringVar()
        ttk.Label(body, textvariable=self.target, wraplength=660).pack(anchor="w")
        self.operation = tk.StringVar(value=next(iter(OPERATIONS)))
        ttk.Combobox(body, textvariable=self.operation, values=list(OPERATIONS), state="readonly").pack(fill="x", pady=10)
        ttk.Label(body, text="Cerere (se transmite doar contextul nodului selectat):").pack(anchor="w")
        self.instruction = tk.Text(body, height=5, wrap="word")
        self.instruction.pack(fill="x", pady=6)
        self.instruction.insert("1.0", "Propune un pas concret pe baza descrierii task-ului.")
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=8)
        self.generate_button = ttk.Button(controls, text="Generează propunerea", command=self.generate)
        self.generate_button.pack(side="left")
        ttk.Button(controls, text="Anulează", command=self.cancel).pack(side="left", padx=8)
        self.apply_button = ttk.Button(controls, text="Aplică propunerea…", command=self.apply, state="disabled")
        self.apply_button.pack(side="right")
        self.status = tk.StringVar(value="Nicio modificare nu se aplică automat.")
        ttk.Label(body, textvariable=self.status, wraplength=660).pack(anchor="w")
        self.preview = tk.Text(body, height=14, wrap="word", state="disabled")
        self.preview.pack(fill="both", expand=True, pady=8)
        self.target.set("Țintă la generare: " + (app.ws.get(app.selected_id).title if app.ws and app.selected_id else "selectează un nod"))

    def generate(self) -> None:
        try:
            if not self.app.config.ai.enabled:
                raise ValidationError("Activează AI local din Setări → AI.")
            if not self.app.ws or not self.app.selected_id:
                raise ValidationError("Selectează mai întâi un task sau un proiect.")
            if not self.app.confirm_leave():
                return
            action = OPERATIONS[self.operation.get()]
            ws = self.app.ws
            context = ActionContext.capture(ws, self.app.selected_id, action)
            node = ws.get(context.node_id)
            description = ws.repo.read_description(node.id)
            # Bounded context from the selected node only. No file contents, mail, or workspace scan.
            text = json.dumps({"titlu": node.title, "descriere": description[:4500],
                               "următorul_pas": (node.next_action or "")[:1000]}, ensure_ascii=False)
            self._context = context
            self._proposal = None
            self._applied = False
            self.apply_button.state(["disabled"])
            self._request_id = self.app.ai.request(self.app.config.ai, action,
                self.instruction.get("1.0", "end").strip(), text, self.on_message)
            self.target.set("Țintă fixată: " + node.title)
            self.generate_button.state(["disabled"])
            self.status.set("Pornire AI…")
        except Exception as exc:
            self.status.set(str(exc))

    def on_message(self, message) -> None:
        if self._closed or message.request_id != self._request_id:
            return
        if message.kind == "loading":
            self.status.set("Verificare și încărcare model, apoi generare pe CPU…")
            return
        self._request_id = None
        self.generate_button.state(["!disabled"])
        if message.kind == "error":
            self.status.set(message.error)
            return
        try:
            validate_proposal(self.app.ws, self._context, message.proposal)
        except Exception as exc:
            self.status.set(f"Propunere respinsă: {exc}")
            return
        self._proposal = message.proposal
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", f"Operație: {self._proposal.action}\nTitlu: {self._proposal.title}\n\n{self._proposal.text}")
        self.preview.configure(state="disabled")
        self.apply_button.state(["!disabled"])
        self.status.set("Verifică sensul propunerii. JSON valid nu garantează că informația este corectă.")

    def apply(self) -> None:
        if self._proposal is None or self._applied:
            return
        try:
            validate_proposal(self.app.ws, self._context, self._proposal)
        except Exception as exc:
            show_error(self, str(exc))
            return
        if not self.app.confirm_leave():
            return
        if not confirm(self, "Aplici operația afișată asupra nodului indicat? Verifică textul înainte de confirmare.", "Aplică propunerea AI"):
            return
        if self.app.run_write(lambda: apply_proposal(self.app.ws, self._context, self._proposal), refresh=True):
            self._applied = True
            self.apply_button.state(["disabled"])
            self.status.set("Propunere aplicată prin Workspace.")

    def cancel(self) -> None:
        if self._request_id:
            self.app.ai.cancel(self._request_id)
            self._request_id = None
            self.status.set("Cerere anulată; procesul se oprește.")
            self.generate_button.state(["!disabled"])
        self._proposal = None
        self.apply_button.state(["disabled"])

    def destroy(self) -> None:
        if not self._closed:
            self.cancel()
            self._closed = True
            self.app.ai_window = None
        super().destroy()
