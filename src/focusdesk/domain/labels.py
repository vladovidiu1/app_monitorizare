"""Etichete in limba romana pentru valorile interne."""

from __future__ import annotations

from ..i18n import tr

from .models import Kind, Priority, Status

STATUS_LABELS: dict[Status, str] = {
    Status.INBOX: tr('ui.meetings.de_facut'),
    Status.TODO: tr('ui.meetings.de_facut'),
    Status.IN_PROGRESS: tr('ui.session_ui.in_lucru'),
    Status.WAITING: tr('ui.tasklist.in_asteptare'),
    Status.TESTING: tr('domain.labels.in_testare'),
    Status.DONE: tr('extra.domain.labels.finalizat'),
    Status.CANCELLED: tr('ui.planning.anulat'),
}

PRIORITY_LABELS: dict[Priority, str] = {
    Priority.URGENT: tr('domain.labels.urgenta'),
    Priority.HIGH: tr('domain.labels.ridicata'),
    Priority.NORMAL: tr('domain.labels.normala'),
    Priority.LOW: tr('domain.labels.redusa'),
}

KIND_LABELS: dict[Kind, str] = {
    Kind.FOLDER: tr('ui.file_picker.folder'),
    Kind.PROJECT: tr('ui.app.proiect'),
    Kind.TASK: tr('ui.outlook_ui.task'),
}

SESSION_STATUS_LABELS = {
    "planned": tr('domain.labels.programata'),
    "active": tr('ui.session_ui.in_lucru'),
    "done": tr('domain.labels.incheiata'),
    "cancelled": tr('domain.labels.anulata'),
    "missed": tr('domain.labels.ratata'),
}

STATUS_FROM_LABEL = {v: k for k, v in STATUS_LABELS.items()}
VISIBLE_STATUSES = tuple(s for s in Status if s != Status.INBOX)


def display_status(status):
    return Status.TODO if status == Status.INBOX else status


PRIORITY_FROM_LABEL = {v: k for k, v in PRIORITY_LABELS.items()}


def status_label(status: Status | None) -> str:
    return STATUS_LABELS.get(status, "") if status else ""


def priority_label(priority: Priority | None) -> str:
    return PRIORITY_LABELS.get(priority, "") if priority else ""


def format_minutes(minutes: int | None) -> str:
    """Formateaza durata; `None` inseamna neestimat, nu zero."""
    if minutes is None:
        return tr('ui.planning.neestimat')
    h, m = divmod(int(minutes), 60)
    if h and m:
        return tr('format.hours_minutes',hours=h,minutes=m)
    if h:
        return tr('format.hours',hours=h)
    return tr('format.minutes',minutes=m)


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
        return tr('format.less_minute')
    return format_minutes(round(seconds / 60))


def session_status_text(session, timer=None):
    """The persisted active flag is qualified by the unique current timer."""
    if session.status == 'active':
        if timer and timer.state and timer.state.session_id == session.id:
            if timer.recovered: return tr('status.recovered',state=tr('ui.session_ui.in_pauza') if timer.state.state == 'paused' else tr('ui.session_ui.in_lucru'))
            return tr('domain.labels.in_lucru') if timer.running else tr('domain.labels.ii_in_pauza')
        return tr('domain.labels.de_verificat_fara_timer_curent')
    label = SESSION_STATUS_LABELS[session.status]
    return tr('status.booking',status=label) if session.status == 'planned' else label
