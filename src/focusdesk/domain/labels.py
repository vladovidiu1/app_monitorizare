"""Etichete in limba romana pentru valorile interne."""

from __future__ import annotations

from .models import Kind, Priority, Status

STATUS_LABELS: dict[Status, str] = {
    Status.INBOX: "Inbox",
    Status.TODO: "De făcut",
    Status.IN_PROGRESS: "În lucru",
    Status.WAITING: "În așteptare",
    Status.TESTING: "În testare",
    Status.DONE: "Finalizat",
    Status.CANCELLED: "Anulat",
}

PRIORITY_LABELS: dict[Priority, str] = {
    Priority.URGENT: "Urgentă",
    Priority.HIGH: "Ridicată",
    Priority.NORMAL: "Normală",
    Priority.LOW: "Redusă",
}

KIND_LABELS: dict[Kind, str] = {
    Kind.FOLDER: "Folder",
    Kind.PROJECT: "Proiect",
    Kind.TASK: "Task",
}

SESSION_STATUS_LABELS = {
    "planned": "Planificată",
    "active": "Activă",
    "done": "Realizată",
    "cancelled": "Anulată",
    "missed": "Ratată",
}

STATUS_FROM_LABEL = {v: k for k, v in STATUS_LABELS.items()}
PRIORITY_FROM_LABEL = {v: k for k, v in PRIORITY_LABELS.items()}


def status_label(status: Status | None) -> str:
    return STATUS_LABELS.get(status, "") if status else ""


def priority_label(priority: Priority | None) -> str:
    return PRIORITY_LABELS.get(priority, "") if priority else ""


def format_minutes(minutes: int | None) -> str:
    """Formateaza durata; `None` inseamna neestimat, nu zero."""
    if minutes is None:
        return "Neestimat"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} h {m:02d} min"
    if h:
        return f"{h} h"
    return f"{m} min"


def format_seconds(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def format_worked(seconds: float) -> str:
    """Timp lucrat in ore si minute; gol pentru zero."""
    if seconds <= 0:
        return ""
    if seconds < 60:
        return "< 1 min"
    return format_minutes(round(seconds / 60))
