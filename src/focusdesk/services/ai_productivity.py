"""Fluxuri AI read-only; cifrele sunt calculate în cod, programarea aparține Planner."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re

from ..domain.models import CLOSED_STATUSES, Kind, Status
from ..errors import ValidationError
from .assistant_context import ContextBundle, Source, node_guard
from .assistant_proposals import ProposalBatch
from .queries import Queries

MAIL_MODES = ("Actualizare progres", "Solicitare clarificări", "Follow-up", "Anunț de finalizare")


def mail_instruction(ws, node_id, mode):
    if mode not in MAIL_MODES:
        raise ValidationError("Tip de ciornă necunoscut.")
    node = ws.get(node_id)
    if mode == MAIL_MODES[3] and node.status != Status.DONE:
        raise ValidationError("Taskul nu este finalizat în date. Actualizează corect starea sau alege alt tip de mesaj.")
    return (f"Redactează un mesaj nou: {mode}. Folosește taskul, jurnalul și sesiunile citate. "
        "Nu inventa rezultate, promisiuni sau date viitoare. Nu afirma finalizare dacă statusul nu este done. "
        "Nu afirma că ai răspuns într-o conversație: acesta este un mesaj NOU, fără Reply/ReplyAll. "
        "Dacă lipsesc date, formulează întrebări sau spune explicit că lipsesc. Completează email, fără destinatari și fără trimitere.")


def day_context(ws, question, token=None):
    q = Queries(ws)
    candidates = [n for n in q.assistant_candidates(question, None) if n.kind == Kind.TASK and n.status not in CLOSED_STATUSES]
    candidates.sort(key=lambda n: (q.due_day(n) or date.max, bool(ws.unfinished_dependencies(n.id)), n.title.casefold()))
    bundle = ContextBundle(ws.id, "workspace", None, matched=len(candidates), truncated=len(candidates) > 12)
    for node in candidates[:12]:
        if token:
            token.check()
        guard = node_guard(ws, node.id)
        data = {"today": q.today().isoformat(), "timezone": ws.settings.timezone, "title": node.title, "status": node.status.value, "due_date": str(q.due_day(node)) if q.due_day(node) else None,
            "remaining_minutes": node.remaining_minutes if node.remaining_minutes is not None else node.estimated_minutes,
            "blocker_titles": [d.title for d in ws.unfinished_dependencies(node.id)], "next_action": node.next_action}
        key = "task:" + node.id
        bundle.sources[key] = Source(key, "task", node.id, node.id, guard.fingerprint, data)
        bundle.guards[node.id] = guard
    return bundle


DAY_INSTRUCTION = ("Pregătește-mi ziua. Interpretează cererea și alege maximum TREI priorități dintre candidați. "
    "Un paragraf answer pentru fiecare task, cu exact sursa task:ID respectivă. Justifică prin termen, blocaje și timp rămas. "
    "Nu calcula ore sau intervale: Planner face asta. Neestimat înseamnă cere estimare, nu inventa minute. "
    "Dependențele blocate nu sunt rezolvate prin selectare. Fără actions și fără email. Cererea mea: ")


def day_selection(ws, bundle, reply, included):
    ProposalBatch.prepare(ws, bundle, reply, included, "chat")
    if not 1 <= len(reply.answer) <= 3:
        raise ValidationError("Sunt permise maximum trei priorități.")
    selected = []
    for part in reply.answer:
        if len(part.sources) != 1 or not part.sources[0].startswith("task:"):
            raise ValidationError("Fiecare prioritate necesită exact un task sursă.")
        source = bundle.sources[part.sources[0]]
        if source.node_id in selected or ws.get(source.node_id).status in CLOSED_STATUSES:
            raise ValidationError("Prioritate duplicată sau task închis; recalculează.")
        selected.append(source.node_id)
    return selected


def activity_report(ws, first: date, last: date, token=None):
    """Aceeași atribuire pe zi ca Queries.worked_by_day: întreaga sesiune la startul real.

    Fără rollup părinte/copil și fără timp live nesalvat sau durate planificate.
    """
    q = Queries(ws)
    if last < first or (last-first).days > 6:
        raise ValidationError("Raportul acoperă cel mult șapte zile.")
    totals = {}
    for values in q.worked_by_day(first, last).values():
        for node_id, seconds in values.items():
            totals[node_id] = totals.get(node_id, 0) + seconds
    sessions = ws.repo.sessions.list_all()
    rows = []
    for node in sorted(q.tasks(include_archived=True), key=lambda n: (n.title.casefold(), n.id)):
        if token:
            token.check()
        completed = bool(node.status == Status.DONE and node.completed_at and first <= node.completed_at.astimezone(q.tz()).date() <= last)
        seconds = totals.get(node.id, 0)
        blockers = [d.title for d in ws.unfinished_dependencies(node.id)]
        if not (seconds or completed or (node.status not in CLOSED_STATUSES and (blockers or node.waiting_reason))):
            continue
        records = [s.id for s in sessions if s.node_id == node.id and s.actual_seconds > 0 and
            first <= (s.started_actual_at or s.start_at).astimezone(q.tz()).date() <= last]
        rows.append({"task_id": node.id, "title": node.title, "actual_seconds": seconds,
            "completed_in_period": completed, "completed_at": node.completed_at.isoformat() if completed else None,
            "status": node.status.value, "blockers": blockers, "waiting_reason": node.waiting_reason,
            "next_action": node.next_action, "session_ids": records})
    return {"first": first.isoformat(), "last": last.isoformat(), "timezone": ws.settings.timezone,
        "actual_seconds": sum(totals.values()), "worked_tasks": sum(v > 0 for v in totals.values()),
        "completed_tasks": sum(r["completed_in_period"] for r in rows), "tasks": rows,
        "rule": "actual_seconds salvate, atribuite zilei started_actual_at sau start_at; fără timp planificat sau live"}


def report_fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def report_context(ws, first, last, token=None):
    data = activity_report(ws, first, last, token)
    bundle = ContextBundle(ws.id, "workspace", None, matched=len(data["tasks"]), truncated=len(data["tasks"]) > 6)
    # Rezumatul calculat rămâne primul în buget. Detaliile complete se afișează separat în UI.
    summary = {k: v for k, v in data.items() if k != "tasks"}
    key = "report:" + ws.id
    bundle.sources[key] = Source(key, "report", ws.id, ws.id, report_fingerprint(data), summary)
    for row in data["tasks"][:6]:
        node_id = row["task_id"]
        guard = node_guard(ws, node_id)
        key = "task:" + node_id
        # period_actual_seconds avoids confusing this with lifetime actual_seconds validation.
        detail = {**row, "period_actual_seconds": row["actual_seconds"]}
        del detail["actual_seconds"]
        bundle.sources[key] = Source(key, "task", node_id, node_id, guard.fingerprint, detail)
        bundle.guards[node_id] = guard
    return bundle, data


REPORT_INSTRUCTION = ("Redactează explicația raportului calculat în cod. Copiază exact cifrele din report; "
    "nu recalcula și nu confunda planificat cu lucrat. Include activitate, finalizări, blocaje și pași următori "
    "numai dacă sursele le susțin. Contextul de detalii poate fi parțial. Fără promisiuni, acțiuni sau email. "
    "Citează report pentru totaluri și task pentru detalii. Când lipsesc date spune acest lucru.")


def report_text(data):
    lines = [f"Raport {data['first']} — {data['last']} ({data['timezone']})",
        f"Lucrat: {data['actual_seconds']} secunde; taskuri lucrate: {data['worked_tasks']}; finalizate în perioadă: {data['completed_tasks']}.",
        data["rule"]]
    for row in data["tasks"]:
        lines.append(f"\n{row['title']} [task:{row['task_id']}] — {row['actual_seconds']} secunde; finalizat în perioadă: {row['completed_in_period']}")
        lines.extend("[session:" + sid + "]" for sid in row["session_ids"])
        lines.append("Blocaje: " + (", ".join(row["blockers"]) or row["waiting_reason"] or "niciunul înregistrat"))
        lines.append("Următor pas: " + (row["next_action"] or "nesalvat"))
    if not data["tasks"]:
        lines.append("Nu există activitate sau blocaje înregistrate pentru perioada aleasă.")
    return "\n".join(lines)


def validate_mail_reply(ws, bundle, reply, included, node_id):
    batch = ProposalBatch.prepare(ws, bundle, reply, included, "email")
    if not reply.email or reply.email.node_id != node_id:
        raise ValidationError("Ciorna nu aparține taskului ales.")
    text = (reply.email.subject + " " + reply.email.body).casefold()
    if ws.get(node_id).status != Status.DONE and re.search(r"finalizat|finalizată|încheiat|terminat|completed|finished", text):
        raise ValidationError("Ciorna afirmă sau sugerează finalizare pentru un task deschis; reformulează.")
    if re.search(r"\b(?:voi|vom|promit|promitem|garantez|garantăm)\b|mă angajez", text):
        raise ValidationError("Ciorna introduce o promisiune; reformulează fără angajamente generate.")
    if re.search(r"am răspuns|am raspuns|replyall|în conversația originală", text):
        raise ValidationError("Se pregătește un mesaj nou, nu un răspuns în conversația originală.")
    return batch
