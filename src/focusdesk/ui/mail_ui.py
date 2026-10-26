"""Dialogul „E-mail din task”: compune un mesaj (cu contextul task-ului) si il trimite prin Outlook sau il deschide ca ciorna."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.models import Node
from ..errors import FocusDeskError, ValidationError
from ..services.colleagues import requester
from ..services.mail import MailDraft, build_draft, default_body, default_subject
from .common import ModalDialog, Tooltip, confirm, show_error
from .colleagues_ui import ColleaguePickerDialog

if TYPE_CHECKING:
    from .app import FocusDeskApp


class MailDialog(ModalDialog):
    # Enter nu trebuie sa trimita mesajul din greseala (ex. din campul „Către”).
    enter_confirms = False

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp", node: Node) -> None:
        super().__init__(parent, "E-mail din task", resizable=True, ok_text="Trimite", cancel_text="Anulează")
        self.app = app
        self.action = "send"
        self.node_id = node.id
        self.geometry("720x620")
        self.minsize(560, 480)
        self.draft_btn = ttk.Button(self.buttons, text="Deschide ciorna în Outlook", command=self._open_draft)
        self.draft_btn.pack(side="left")
        # Butoanele primele, jos: la redimensionare corpul cedeaza spatiu, nu butoanele.
        self.body.pack_forget()
        self.buttons.pack_forget()
        self.buttons.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        b = self.body
        b.columnconfigure(1, weight=1)
        b.rowconfigure(4, weight=1)
        ttk.Label(b, text=f"Task: {node.title}", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.to_var, self.cc_var = tk.StringVar(), tk.StringVar()
        person = node.requested_by
        try:
            person = requester(app.ws, node)
        except FocusDeskError as exc:
            show_error(self, str(exc))
        if person:
            self.to_var.set(person.email)
        self.subject_var = tk.StringVar(value=default_subject(node))
        for r, (label, var) in enumerate((("Către", self.to_var), ("CC", self.cc_var), ("Subiect", self.subject_var)), 1):
            ttk.Label(b, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            line = ttk.Frame(b)
            line.grid(row=r, column=1, sticky="ew", pady=4)
            entry = ttk.Entry(line, textvariable=var)
            entry.pack(side="left", fill="x", expand=True)
            if r in (1, 2):
                pick = ttk.Button(line, text="…", width=3, command=lambda target=var: self._add_colleague(target))
                pick.pack(side="left", padx=(4, 0))
                Tooltip(pick, "Adaugă un coleg")
            if r == 1:
                self.to_entry = entry
        ttk.Label(b, text="Mesaj").grid(row=4, column=0, sticky="nw", pady=4, padx=(0, 10))
        wrap = ttk.Frame(b)
        wrap.grid(row=4, column=1, sticky="nsew", pady=4)
        self.text = tk.Text(wrap, wrap="word", height=12, font="TkTextFont", borderwidth=1, relief="solid",
                            highlightthickness=0, undo=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.text.insert("1.0", default_body(app.ws, node))
        ttk.Label(b, style="Muted.TLabel", wraplength=640, justify="left", text=(
            "Adrese separate prin „;” sau „,”. Se trimite din contul implicit din Outlook Classic. Nimic nu pleacă "
            "până nu apeși „Trimite”; „Deschide ciorna” îl lasă în Outlook pentru ultimele ajustări.")).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(b, text="Mesaj nou, nu Reply/ReplyAll în conversația originală.", style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        self.to_entry.focus_set()

    def _add_colleague(self, target: tk.StringVar) -> None:
        person = ColleaguePickerDialog(self, self.app.ws).run()
        if person is not None:
            current = target.get().strip().rstrip(";,")
            target.set(f"{current}; {person.email}" if current else person.email)

    def _open_draft(self) -> None:
        self.action = "draft"
        self._on_ok()
        if self.result is None:
            self.action = "send"  # validarea a esuat: ramanem in dialog, butonul principal ramane „Trimite”

    def _build(self) -> MailDraft:
        return build_draft(self.to_var.get(), self.cc_var.get(), self.subject_var.get(),
                           self.text.get("1.0", "end"), for_send=self.action == "send")

    def validate(self) -> bool:
        try:
            draft = self._build()
        except ValidationError as exc:
            show_error(self, str(exc), "E-mail")
            return False
        if self.action == "send" and not confirm(
                self, f"Trimit acum e-mailul către:\n{', '.join(draft.to)}\n\nSubiect: {draft.subject}", "Trimite e-mail"):
            return False
        return True

    def collect(self) -> dict:
        return {"action": self.action, "draft": self._build()}
