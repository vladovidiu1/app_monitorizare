"""Analiză locală: estimări, citate, date calculate determinist și proiecție revizuibilă."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
import re
from uuid import uuid4, uuid5, UUID
from zoneinfo import ZoneInfo

from ..ai.assistant_protocol import AssistantReply
from ..ai.mail_protocol import MailAnalysis
from ..domain.models import Kind
from ..errors import ValidationError
from .assistant_context import ContextBundle, Guard, Source, node_guard
from .assistant_proposals import ProposalBatch
from .mail_monitor import MailMonitorService, mail_fingerprint
from .queries import Queries


def normalized(text):
    return " ".join(text.casefold().split())


def quote_exists(message, quote, body_chars=None):
    body = message.body if body_chars is None else message.body[:body_chars]
    return bool(quote and normalized(quote) in normalized(message.header.subject + "\n" + body))


def resolve_deadline(quote, sent_at, timezone):
    if not quote:
        return None, None
    base = sent_at.astimezone(ZoneInfo(timezone)).date()
    text = normalized(quote)
    if any(word in text for word in ("probabil", "poate", "sau", "cândva", "candva")):
        return None, "Termen ambiguu; confirmă o dată calendaristică."
    candidates = []
    for match in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text):
        try:
            candidates.append(date.fromisoformat(match))
        except ValueError:
            return None, "Data explicită este invalidă."
    for day, month, year in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", text):
        try:
            candidates.append(date(int(year), int(month), int(day)))
        except ValueError:
            return None, "Data explicită este invalidă."
    explicit = set(candidates)
    if "viitoare" in text and not explicit:
        return None, "«Săptămâna viitoare» necesită confirmarea unei date exacte."
    if re.search(r"\b(?:mâine|maine)\b", text):
        candidates.append(base + timedelta(days=1))
    if re.search(r"\b(?:poimâine|poimaine)\b", text):
        candidates.append(base + timedelta(days=2))
    weekdays = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
    for weekday, word in enumerate(weekdays):
        aliases = {word, word.replace("ț", "t").replace("â", "a").replace("ă", "a").replace("î", "i")}
        if any(re.search(rf"\b{alias}\b", text) for alias in aliases):
            if explicit:
                if any(value.weekday() != weekday for value in explicit):
                    return None, "Ziua săptămânii nu corespunde datei explicite."
                continue
            offset = (weekday - base.weekday()) % 7
            if offset == 0:
                return None, "Ziua menționată coincide cu data mesajului; astăzi sau săptămâna următoare?"
            candidates.append(base + timedelta(days=offset))
    unique = set(candidates)
    if len(unique) != 1:
        return None, "Termenul necesită clarificare: nu există o singură dată explicită."
    return unique.pop(), None


def build_mail_context(ws, message_id, token=None):
    if token:
        token.check()
    message = ws.mail_get(message_id)
    if message is None or not message.body_loaded:
        raise ValidationError("Încarcă textul mailului înainte de analiză.")
    if message.state == "ignored" or message.header.conversation_key in ws.mail_state().ignored_conversations:
        raise ValidationError("Reia explicit conversația înainte de analiză.")
    bundle = ContextBundle(ws.id, "workspace", None)
    key = "mail:" + message.id
    bundle.sources[key] = Source(key, "mail", message.id, message.id, mail_fingerprint(message), {
        "subject": message.header.subject, "sender": message.header.sender_smtp,
        "sent_at": message.header.sent_at.isoformat(), "body_excerpt": message.body[:6000]})
    monitor = MailMonitorService(ws)
    confirmed = monitor.confirmed_candidates(message)
    candidates = confirmed + [n.id for n in Queries(ws).assistant_candidates(message.header.subject + " " + message.body[:400], None)]
    candidates = [node_id for node_id in dict.fromkeys(candidates) if node_id in ws.nodes and ws.get(node_id).kind == Kind.TASK][:5]
    candidate_data = []
    q = Queries(ws)
    for node_id in candidates:
        if token:
            token.check()
        node = ws.get(node_id)
        guard = node_guard(ws, node_id)
        data = {"id": node.id, "title": node.title, "description": q.description_text(node.id)[:600],
                "status": node.status.value, "next_action": node.next_action, "confirmed_conversation_hint": node.id in confirmed}
        bundle.sources["task:" + node.id] = Source("task:" + node.id, "task", node.id, node.id, guard.fingerprint, data)
        bundle.guards[node.id] = guard
        candidate_data.append(data)
    conversation = sorted((record for record in ws.mail_records() if record.id != message.id and
        record.header.conversation_key == message.header.conversation_key), key=lambda record: record.header.sent_at, reverse=True)[:2]
    payload = {"mail": {"id": message.id, "subject": message.header.subject, "body": message.body,
        "sender_name": message.header.sender_name, "sender_smtp": message.header.sender_smtp,
        "sent_at": message.header.sent_at.isoformat(), "workspace_timezone": ws.settings.timezone,
        "body_truncated": message.body_truncated,
        "attachments_metadata_only": [a.model_dump() for a in message.attachments]}, "candidates": candidate_data,
        "conversation": [{"subject": old.header.subject, "text_excerpt": old.body[:800],
                          "confirmed_task_ids": old.confirmed_task_ids} for old in conversation]}
    return bundle, payload


def project_analysis(ws, message_id, analysis, bundle, candidate_ids=None, body_chars=None):
    analysis = MailAnalysis.model_validate(analysis.model_dump())
    message = ws.mail_get(message_id)
    key = "mail:" + message_id
    if candidate_ids is not None:
        bundle.sources = {key: source for key, source in bundle.sources.items() if source.kind == "mail" or source.node_id in candidate_ids}
    if body_chars is not None:
        bundle.sources[key].data["body_excerpt"] = message.body[:min(6000, body_chars)]
    if not quote_exists(message, analysis.evidence_quote, body_chars):
        raise ValidationError("Fragmentul justificativ nu există în mail. Analiza nu este acceptată.")
    clarifications = []
    due = None
    if analysis.deadline_quote:
        if not quote_exists(message, analysis.deadline_quote, body_chars):
            raise ValidationError("Fragment de termen inventat.")
        due, issue = resolve_deadline(analysis.deadline_quote, message.header.sent_at, ws.settings.timezone)
        marker = re.search(r"(?im)^(?:from:|de la:|[- ]*original message|[- ]*mesaj original)", message.body)
        if marker and normalized(analysis.deadline_quote) in normalized(message.body[marker.start():]):
            due, issue = None, "Termen din text citat/forwarded; confirmă data mesajului la care se referă."
        if issue:
            clarifications.append(issue)
            bundle.sources[key].data["deadline_ambiguous"] = True
    if analysis.clarification:
        clarifications.append(analysis.clarification)
    if message.body_truncated or (body_chars is not None and body_chars < len(message.body)):
        clarifications.append("Text trunchiat: analiza nu acoperă întregul mesaj. Verifică originalul înainte de confirmare.")
    data = bundle.sources[key].data
    data["evidence_quote"] = analysis.evidence_quote
    data["deadline_resolved"] = due.isoformat() if due else None
    common = {"reason": analysis.evidence_quote, "sources": [key]}
    operations = []
    if analysis.classification == "request" and message.confirmed_task_ids:
        clarifications.append("Acest mail are deja o asociere confirmată; nu se propune încă un task automat.")
    elif analysis.classification == "request":
        if any((receipt := ws.ai_receipt(item_id)) and receipt.data.get("state") in ("started", "uncertain") for item_id in message.proposal_ids):
            raise ValidationError("Există o creare cu rezultat incert; verifică istoricul înainte de alte propuneri.")
        requester = None
        if analysis.requester_is_sender and message.header.sender_smtp:
            requester = {"name": message.header.sender_name or message.header.sender_smtp, "email_address": message.header.sender_smtp}
        else:
            data["requester_unresolved"] = True
            clarifications.append("Confirmă solicitantul și o adresă SMTP reală; numele afișat nu este o adresă.")
        if not analysis.task_title.strip():
            raise ValidationError("Lipsește titlul taskului propus.")
        operations.append({**common, "kind": "create_task", "parent_id": None, "title": analysis.task_title,
            "description": analysis.description or analysis.summary, "due_date": due.isoformat() if due else None,
            "requested_by": requester})
    elif analysis.classification == "update":
        target = analysis.target_task_id
        if target is None:
            clarifications.append("Alege/confirmă taskul; ConversationID nu dovedește asocierea.")
        elif "task:" + target not in bundle.sources:
            raise ValidationError("Taskul propus nu a fost consultat.")
        else:
            refs = [key, "task:" + target]
            common = {"reason": analysis.evidence_quote, "sources": refs}
            operations.append({**common, "kind": "associate_mail", "node_id": target, "mail_id": message_id})
            if analysis.journal_update:
                operations.append({**common, "kind": "add_note", "node_id": target, "text": analysis.journal_update})
            patch = {}
            if analysis.status:
                supported = {"done": ("finalizat", "rezolvat", "terminat"), "cancelled": ("anulat", "renunț", "renunt"),
                    "waiting": ("aștept", "astept", "blocat"), "in_progress": ("lucrez", "în lucru", "in lucru"),
                    "todo": ("te rog", "solicit", "de făcut", "de facut")}
                quote = normalized(analysis.status_quote or "")
                ambiguous_status = re.search(r"\b(?:nu|n-am|nefinalizat|neterminat|poate|dacă|daca|sper)\b|va fi|ar fi|\?", quote)
                if quote_exists(message, analysis.status_quote, body_chars) and not ambiguous_status and any(word in quote for word in supported[analysis.status]):
                    patch["status"] = analysis.status
                else:
                    clarifications.append("Statusul nu este susținut explicit de un fragment; confirmă-l manual.")
            for field in ("waiting_reason", "next_action"):
                value = getattr(analysis, field)
                if value:
                    patch[field] = value
            if due:
                patch["due_date"] = due.isoformat()
            elif data.get("deadline_ambiguous"):
                patch["due_date"] = None
            if patch:
                operations.append({**common, "kind": "update_task", "node_id": target, "patch": patch})
    elif analysis.classification == "clarify":
        clarifications.append(analysis.clarification or "Cererea este ambiguă; cere detalii expeditorului.")
    reply = AssistantReply.model_validate({"answer": [{"text": analysis.summary, "sources": [key]}], "actions": operations})
    batch = ProposalBatch.prepare(ws, bundle, reply, list(bundle.sources))
    generation = str(uuid4())
    for index, item in enumerate(batch.items):
        item.id = str(uuid5(UUID(message_id), generation + ":" + str(index)))
    message.analysis = analysis.model_dump()
    message.projection = reply.model_dump(exclude_unset=True)
    message.context_snapshot = asdict(bundle)
    message.included_keys = list(bundle.sources)
    message.proposal_ids = [item.id for item in batch.items]
    message.edited_items = [False] * len(batch.items)
    message.analysis_generation = generation
    message.clarification = clarifications
    message.state = "proposed" if batch.items else "informational" if analysis.classification == "informational" and not clarifications else "clarify"
    ws.save_mail_record(message)
    return batch


def restore_batch(ws, message_id):
    message = ws.mail_get(message_id)
    if not message or not message.projection or not message.context_snapshot:
        return None
    raw = message.context_snapshot
    bundle = ContextBundle(raw["workspace_id"], raw["scope"], raw["anchor"],
        sources={key: Source(**value) for key, value in raw["sources"].items()},
        guards={key: Guard(**value) for key, value in raw["guards"].items()}, matched=raw["matched"], truncated=raw["truncated"])
    # Advance guards only from persisted successful receipts, never from current edited task state.
    for item_id in message.proposal_ids:
        receipt = ws.ai_receipt(item_id)
        if receipt and receipt.data.get("state") == "applied":
            for node_id, guard in receipt.data.get("after_guards", {}).items():
                bundle.guards[node_id] = Guard(**guard)
    batch = ProposalBatch.prepare(ws, bundle, AssistantReply.model_validate(message.projection), message.included_keys)
    for index, item in enumerate(batch.items):
        item.id = message.proposal_ids[index]
        item.edited = message.edited_items[index] if index < len(message.edited_items) else False
        receipt = ws.ai_receipt(item.id)
        if receipt:
            item.state = receipt.data.get("state", "started")
    return batch


def save_batch(ws, message_id, batch):
    message = ws.mail_get(message_id)
    message.projection["actions"] = [item.operation.model_dump(exclude_unset=True) for item in batch.items]
    message.edited_items = [item.edited for item in batch.items]
    message.context_snapshot["guards"] = {key: asdict(value) for key, value in batch.guards.items()}
    states = [ws.ai_receipt(item.id).data.get("state") if ws.ai_receipt(item.id) else "pending" for item in batch.items]
    if states and all(state in ("applied", "rejected", "conflict", "uncertain", "started") for state in states):
        message.state = "error" if any(state in ("started", "uncertain") for state in states) else "handled" if "applied" in states else "rejected"
    ws.save_mail_record(message)


def reconcile(ws):
    for message in ws.mail_records():
        if message.state not in ("proposed", "clarify") or not message.proposal_ids:
            continue
        try:
            receipts = [ws.ai_receipt(item_id) for item_id in message.proposal_ids]
        except Exception:
            message.state = "error"
            ws.save_mail_record(message)
            continue
        if all(receipts):
            states = [receipt.data.get("state") for receipt in receipts]
            if all(state != "pending" for state in states):
                message.state = "error" if any(state in ("started", "uncertain") for state in states) else "handled" if "applied" in states else "rejected"
                ws.save_mail_record(message)
