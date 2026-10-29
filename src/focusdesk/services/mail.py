"""E-mail dintr-un task: validarea adreselor si textul implicit. Trimiterea propriu-zisa se face prin Outlook (COM)."""

from __future__ import annotations

from ..i18n import tr, date_text, datetime_text

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain.labels import PRIORITY_LABELS, STATUS_LABELS
from ..domain.models import Kind, Node
from ..errors import ValidationError
from .files import LocalFile, format_size, inspect_local_file, normalized_file_key
from .workspace import Workspace

_EMAIL_RE = re.compile(r"^[^@\s<>;,\"']+@[^@\s<>;,\"']+\.[^@\s<>;,\"']+$")
_NAME_ADDR_RE = re.compile(r"<([^<>]+)>\s*$")


@dataclass
class MailDraft:
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    attachments: list[LocalFile] = field(default_factory=list)


def attachment_selection(paths: Iterable[str | Path | LocalFile]) -> list[LocalFile]:
    """Deduplicate by Windows path, retain unavailable selections so they can be corrected."""
    selected = {}
    for item in paths:
        path = item.path if isinstance(item, LocalFile) else item
        key = normalized_file_key(path)
        if key not in selected:
            selected[key] = inspect_local_file(path)
    return list(selected.values())


def validate_attachments(paths: Iterable[str | Path | LocalFile]) -> list[LocalFile]:
    selected = attachment_selection(paths)
    bad = [item for item in selected if item.state != "ready"]
    if bad:
        raise ValidationError(tr('services.mail.corecteaza_atasamentele_inainte_de_a_continua') + "\n".join(
            f"{item.path}: {item.detail}" for item in bad))
    return selected


def attachment_summary(attachments: list[LocalFile]) -> str:
    size = format_size(sum(item.size_bytes or 0 for item in attachments))
    unknown = sum(item.size_bytes is None for item in attachments)
    suffix = tr('services.mail.cunoscuti_dimensiuni_indisponibile', unknown=unknown) if unknown else ""
    return tr('services.mail.atasamente', count=len(attachments), len_attachments=len(attachments), size=size, suffix=suffix)


def confirmation_text(draft: MailDraft) -> str:
    return (tr('services.mail.predau_outlook_pentru_trimitere_catre_cc_subiect_livrarea_efectiva_nu', join_draft_to=', '.join(draft.to), join_draft_cc_or=', '.join(draft.cc) or '—', draft_subject=draft.subject, attachment_summary_draft_attachments=attachment_summary(draft.attachments)))


def parse_addresses(text: str) -> list[str]:
    """Adrese separate prin `;`, `,` sau rand nou; accepta si forma `Nume <adresa@domeniu.ro>`."""
    out: list[str] = []
    for part in (p.strip() for p in re.split(r"[;,\n]+", text)):
        if not part:
            continue
        m = _NAME_ADDR_RE.search(part)
        addr = m.group(1).strip() if m else part
        if not _EMAIL_RE.match(addr):
            raise ValidationError(tr('services.mail.adresa_de_e_mail_invalida', part=part))
        if addr.lower() not in {a.lower() for a in out}:
            out.append(addr)
    return out


def clean_subject(subject: str) -> str:
    """Subiectul este o singura linie (fara CR/LF)."""
    return " ".join(subject.split())


def build_draft(to: str, cc: str, subject: str, body: str, *, for_send: bool = True,
                attachments: Iterable[str | Path | LocalFile] = (), allow_cc_only: bool = False) -> MailDraft:
    """La trimitere sunt obligatorii destinatarul, subiectul si mesajul; pentru ciorna se accepta si goluri."""
    recipients = parse_addresses(to)
    copies = parse_addresses(cc)
    subject = clean_subject(subject)
    if for_send:
        if not recipients and not (allow_cc_only and copies):
            raise ValidationError(tr('services.mail.adauga_cel_putin_un_destinatar'))
        if not subject:
            raise ValidationError(tr('extra.services.mail.subiectul_este_obligatoriu'))
        if not body.strip():
            raise ValidationError(tr('extra.services.mail.mesajul_este_gol'))
    return MailDraft(to=recipients, cc=copies, subject=subject, body=body,
                     attachments=validate_attachments(attachments))


def default_subject(node: Node) -> str:
    return tr('services.mail.nelamuriri', node_title=node.title)


def default_body(ws: Workspace, node: Node, *, description: str | None = None) -> str:
    """Text de pornire: loc pentru intrebare + contextul task-ului (editabil inainte de trimitere)."""
    lines = [tr('services.mail.buna_ziua'), "", tr('services.mail.am_o_nelamurire_legata_de', node_title=node.title), "", "", "", tr('services.mail.multumesc'), "",
             tr('extra.services.mail.context'), tr('ui.mail_ui.task', node_title=node.title)]
    path = ws.breadcrumb(node.id)
    if path != node.title:
        lines.append(tr('services.mail.locatie', path=path))
    if node.kind != Kind.FOLDER:
        if node.status:
            lines.append(tr('mail.status',status=STATUS_LABELS[node.status]))
        if node.priority:
            lines.append(tr('mail.priority',priority=PRIORITY_LABELS[node.priority]))
    if node.due_date:
        lines.append(tr('mail.deadline',date=date_text(node.due_date)))
    elif node.due_at:
        lines.append(tr('mail.deadline',date=datetime_text(node.due_at.astimezone(ZoneInfo(ws.settings.timezone)))))
    if node.next_action:
        lines.append(tr('services.mail.urmatorul_pas', node_next_action=node.next_action))
    desc = ws.get_description(node.id, observe=False) if description is None else description
    if desc.strip():
        lines += ["", desc]
    return "\n".join(lines)


def journal_text(draft: MailDraft, result: str = "submitted") -> str:
    if not isinstance(result,str):
        from .gmail import journal_text as gmail_journal
        return gmail_journal(draft,result)
    cc = tr('mail.cc',addresses=', '.join(draft.cc)) if draft.cc else ""
    outcome = {"submitted": tr('services.mail.e_mail_predat_outlook_pentru_trimitere_livrare_neconfirmata'),
               "displayed": tr('services.mail.ciorna_e_mail_deschisa_in_outlook_fara_trimitere'),
               "uncertain": tr('services.mail.rezultat_e_mail_incert_verifica_in_outlook_inainte_de_reincercare')}[result]
    names = "; ".join(item.name for item in draft.attachments) or tr('services.mail.fara_atasamente')
    return tr('services.mail.catre_subiect_atasamente', outcome=outcome, join_draft_to=', '.join(draft.to), cc=cc, draft_subject=draft.subject, names=names)
