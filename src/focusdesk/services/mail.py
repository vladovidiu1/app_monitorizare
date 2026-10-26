"""E-mail dintr-un task: validarea adreselor si textul implicit. Trimiterea propriu-zisa se face prin Outlook (COM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from ..domain.labels import PRIORITY_LABELS, STATUS_LABELS
from ..domain.models import Kind, Node
from ..errors import ValidationError
from .workspace import Workspace

_EMAIL_RE = re.compile(r"^[^@\s<>;,\"']+@[^@\s<>;,\"']+\.[^@\s<>;,\"']+$")
_NAME_ADDR_RE = re.compile(r"<([^<>]+)>\s*$")
DESCRIPTION_LIMIT = 600


@dataclass
class MailDraft:
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)


def parse_addresses(text: str) -> list[str]:
    """Adrese separate prin `;`, `,` sau rand nou; accepta si forma `Nume <adresa@domeniu.ro>`."""
    out: list[str] = []
    for part in (p.strip() for p in re.split(r"[;,\n]+", text)):
        if not part:
            continue
        m = _NAME_ADDR_RE.search(part)
        addr = m.group(1).strip() if m else part
        if not _EMAIL_RE.match(addr):
            raise ValidationError(f"Adresă de e-mail invalidă: {part}")
        if addr.lower() not in {a.lower() for a in out}:
            out.append(addr)
    return out


def clean_subject(subject: str) -> str:
    """Subiectul este o singura linie (fara CR/LF)."""
    return " ".join(subject.split())


def build_draft(to: str, cc: str, subject: str, body: str, *, for_send: bool = True) -> MailDraft:
    """La trimitere sunt obligatorii destinatarul, subiectul si mesajul; pentru ciorna se accepta si goluri."""
    recipients = parse_addresses(to)
    subject = clean_subject(subject)
    if for_send:
        if not recipients:
            raise ValidationError("Adaugă cel puțin un destinatar.")
        if not subject:
            raise ValidationError("Subiectul este obligatoriu.")
        if not body.strip():
            raise ValidationError("Mesajul este gol.")
    return MailDraft(to=recipients, cc=parse_addresses(cc), subject=subject, body=body.strip())


def default_subject(node: Node) -> str:
    return f"Nelămuriri: {node.title}"


def default_body(ws: Workspace, node: Node) -> str:
    """Text de pornire: loc pentru intrebare + contextul task-ului (editabil inainte de trimitere)."""
    lines = ["Bună ziua,", "", f"Am o nelămurire legată de „{node.title}”:", "", "", "", "Mulțumesc!", "",
             "— Context —", f"Task: {node.title}"]
    path = ws.breadcrumb(node.id)
    if path != node.title:
        lines.append(f"Locație: {path}")
    if node.kind != Kind.FOLDER:
        if node.status:
            lines.append(f"Status: {STATUS_LABELS[node.status]}")
        if node.priority:
            lines.append(f"Prioritate: {PRIORITY_LABELS[node.priority]}")
    if node.due_date:
        lines.append(f"Termen: {node.due_date:%d.%m.%Y}")
    elif node.due_at:
        lines.append(f"Termen: {node.due_at.astimezone(ZoneInfo(ws.settings.timezone)):%d.%m.%Y %H:%M}")
    if node.next_action:
        lines.append(f"Următorul pas: {node.next_action}")
    desc = ws.get_description(node.id).strip()
    if desc:
        if len(desc) > DESCRIPTION_LIMIT:
            desc = desc[:DESCRIPTION_LIMIT].rstrip() + "…"
        lines += ["", desc]
    return "\n".join(lines)


def journal_text(draft: MailDraft) -> str:
    cc = f"\nCC: {', '.join(draft.cc)}" if draft.cc else ""
    return f"E-mail trimis către {', '.join(draft.to)}{cc}\nSubiect: {draft.subject}"
