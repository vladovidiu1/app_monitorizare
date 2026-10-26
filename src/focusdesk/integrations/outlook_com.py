"""Backend Outlook Classic prin COM (pywin32). Ruleaza EXCLUSIV in thread-ul COM dedicat.

Neverificat in acest repository pe un Outlook real: vezi docs/diagnostic-integrari.md pentru testul pe calculatorul tinta.
Calendarul: nu foloseste Send(); creeaza programari personale fara participanti, doar cu Save().
E-mailul: `send_mail` trimite doar la cererea explicita a utilizatorului (dialogul de e-mail din task).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .outlook import (
    BUSY_STATUS_NAMES, MAX_EVENTS, AppointmentFields, AppointmentInfo, CalendarInfo, RawEvent,
)

log = logging.getLogger(__name__)
UTC = timezone.utc

OL_APPOINTMENT_ITEM = 1
OL_MAIL_ITEM = 0
OL_FOLDER_CALENDAR = 9
OL_TEXT = 1
OL_NON_MEETING = 0
PROP_SESSION = "FocusDeskSessionId"
PROP_WORKSPACE = "FocusDeskWorkspaceId"
NEW_OUTLOOK_HINT = ("Outlook.Application nu este disponibil. New Outlook nu suportă COM/Outlook Object Model; "
                    "folosește Outlook Classic sau exportul .ics.")


def to_utc(dt: datetime) -> datetime:
    """Outlook intoarce ora de perete in fusul Windows al sistemului, dar pywin32 o eticheteaza cu un fus gresit: o ignoram."""
    return dt.replace(tzinfo=None).astimezone(UTC)


def to_local_naive(dt_utc: datetime) -> datetime:
    """Ora de perete locala (fusul Windows al sistemului, ca in Outlook), nu fusul din setarile workspace-ului."""
    return dt_utc.astimezone().replace(tzinfo=None)


def to_com_date(dt_utc: datetime) -> datetime:
    """pywin32 converteste un datetime naiv local in UTC inainte de a-l da lui Outlook (ora ajunge cu 3h mai devreme).

    Un datetime cu fus UTC este trecut neschimbat, deci ii dam ora de perete locala etichetata UTC.
    """
    return to_local_naive(dt_utc).replace(tzinfo=UTC)


def outlook_filter_datetime(dt_utc: datetime) -> str:
    """Data/ora pentru Items.Restrict in formatul regional Windows (dd.MM.yyyy HH:mm in RO, MM/dd/yyyy in US...)."""
    local = to_local_naive(dt_utc)
    try:
        import win32api  # type: ignore

        d = win32api.GetDateFormat(0x0400, 1, local)  # LOCALE_USER_DEFAULT, DATE_SHORTDATE
        t = win32api.GetTimeFormat(0x0400, 2, local)  # TIME_NOSECONDS
        return f"{d} {t}"
    except Exception:  # pragma: no cover - fallback US
        return local.strftime("%m/%d/%Y %I:%M %p")


class OutlookComBackend:
    def __init__(self) -> None:
        self._app = None
        self._ns = None

    # ---- connection -------------------------------------------------
    def _connect(self):
        if self._app is None:
            import win32com.client  # type: ignore

            self._app = win32com.client.Dispatch("Outlook.Application")
            self._ns = self._app.GetNamespace("MAPI")
        return self._app, self._ns

    def diagnose(self) -> dict:
        info: dict = {"pywin32": False, "outlook": False, "version": None, "profile": None, "stores": [],
                      "error": None, "hint": None}
        try:
            import win32com.client  # type: ignore  # noqa: F401

            info["pywin32"] = True
        except ImportError as exc:
            info["error"] = f"pywin32 lipsește: {exc}"
            return info
        try:
            app, ns = self._connect()
            info["outlook"] = True
            info["version"] = str(getattr(app, "Version", ""))
            try:
                info["profile"] = str(ns.CurrentProfileName)
            except Exception:
                pass
            for store in ns.Stores:
                try:
                    info["stores"].append(str(store.DisplayName))
                except Exception:
                    continue
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
            info["hint"] = NEW_OUTLOOK_HINT
        return info

    # ---- calendars --------------------------------------------------
    def list_calendars(self) -> list[CalendarInfo]:
        _, ns = self._connect()
        out: list[CalendarInfo] = []
        for store in ns.Stores:
            try:
                cal = store.GetDefaultFolder(OL_FOLDER_CALENDAR)
            except Exception:
                continue  # magazin fara calendar (ex. arhive)
            try:
                et = int(store.ExchangeStoreType)
            except Exception:
                et = 3
            kind = {0: "exchange_primary", 1: "exchange_additional", 2: "exchange_public"}.get(et, "other")
            name = str(store.DisplayName)
            out.append(CalendarInfo(str(store.StoreID), name, kind, str(cal.EntryID), str(cal.Name), True))
            try:
                for sub in cal.Folders:
                    if int(getattr(sub, "DefaultItemType", 1)) == OL_APPOINTMENT_ITEM:
                        out.append(CalendarInfo(str(store.StoreID), name, kind, str(sub.EntryID), str(sub.Name), False))
            except Exception:
                pass
        return out

    def _folder(self, store_id: str, folder_id: str):
        _, ns = self._connect()
        return ns.GetFolderFromID(folder_id, store_id)

    # ---- reading ----------------------------------------------------
    def _iter_range(self, folder, start_utc: datetime, end_utc: datetime):
        """Itereaza evenimentele (cu recurente expandate) dintr-un interval LIMITAT."""
        items = folder.Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")
        flt = f"[Start] < '{outlook_filter_datetime(end_utc)}' AND [End] > '{outlook_filter_datetime(start_utc)}'"
        try:
            coll = items.Restrict(flt)
            restricted = True
        except Exception:
            log.warning("Restrict a esuat (format regional?); folosesc iterare marginita")
            coll, restricted = items, False
        count = 0
        item = coll.GetFirst()
        while item is not None and count < MAX_EVENTS:
            count += 1
            try:
                s, e = to_utc(item.Start), to_utc(item.End)
            except Exception:
                item = coll.GetNext()
                continue
            if not restricted:
                if s >= end_utc:
                    break  # sortat dupa Start: restul sunt dupa interval
                if e <= start_utc:
                    item = coll.GetNext()
                    continue
            yield item, s, e
            item = coll.GetNext()

    def read_events(self, store_id: str, folder_id: str, start_utc: datetime, end_utc: datetime) -> list[RawEvent]:
        folder = self._folder(store_id, folder_id)
        out: list[RawEvent] = []
        for item, s, e in self._iter_range(folder, start_utc, end_utc):
            try:
                status = BUSY_STATUS_NAMES.get(int(item.BusyStatus), "busy")
                all_day = bool(item.AllDayEvent)
            except Exception:
                status, all_day = "busy", False
            out.append(RawEvent(s, e, status, all_day, ""))  # titlul nu se pastreaza (confidentialitate)
        return out

    def read_calendar_events(self, store_id: str, folder_id: str, start_utc: datetime,
                             end_utc: datetime) -> list[RawEvent]:
        folder = self._folder(store_id, folder_id)
        out: list[RawEvent] = []
        for item, s, e in self._iter_range(folder, start_utc, end_utc):
            try:
                status = BUSY_STATUS_NAMES.get(int(item.BusyStatus), "busy")
                all_day = bool(item.AllDayEvent)
                subject = str(item.Subject)
            except Exception:
                status, all_day, subject = "busy", False, ""
            out.append(RawEvent(s, e, status, all_day, subject, self._prop(item, PROP_SESSION)))
        return out

    @staticmethod
    def _prop(item, name: str) -> str | None:
        try:
            p = item.UserProperties.Find(name, True)
            return str(p.Value) if p is not None else None
        except Exception:
            return None

    def _info(self, item) -> AppointmentInfo:
        parent = item.Parent
        return AppointmentInfo(
            entry_id=str(item.EntryID), store_id=str(parent.StoreID), folder_id=str(parent.EntryID),
            subject=str(item.Subject), start_utc=to_utc(item.Start), end_utc=to_utc(item.End),
            busy_status=int(item.BusyStatus), session_id=self._prop(item, PROP_SESSION),
            workspace_id=self._prop(item, PROP_WORKSPACE))

    def find_by_session(self, store_id: str, folder_id: str, session_id: str, workspace_id: str,
                        around_start: datetime, around_end: datetime) -> AppointmentInfo | None:
        folder = self._folder(store_id, folder_id)
        for item, _s, _e in self._iter_range(folder, around_start, around_end):
            if self._prop(item, PROP_SESSION) == session_id and self._prop(item, PROP_WORKSPACE) == workspace_id:
                return self._info(item)
        return None

    def get(self, entry_id: str, store_id: str) -> AppointmentInfo | None:
        _, ns = self._connect()
        try:
            item = ns.GetItemFromID(entry_id, store_id)
        except Exception:
            return None
        try:
            # Elementele sterse raman accesibile prin EntryID, dar in Elemente sterse (alt tip de folder).
            if int(item.Parent.DefaultItemType) != OL_APPOINTMENT_ITEM:
                return None
            return self._info(item)
        except Exception:
            return None

    # ---- mail -------------------------------------------------------
    def send_mail(self, to: list[str], cc: list[str], subject: str, body: str, *, send: bool) -> str:
        """`send=True` trimite din contul implicit Outlook; `send=False` doar deschide ciorna pentru revizuire."""
        try:
            app, _ = self._connect()
        except Exception as exc:
            raise RuntimeError(f"{NEW_OUTLOOK_HINT} ({type(exc).__name__}: {exc})") from exc
        mail = app.CreateItem(OL_MAIL_ITEM)
        mail.To = "; ".join(to)
        if cc:
            mail.CC = "; ".join(cc)
        mail.Subject = subject
        mail.Body = body
        if not send:
            mail.Display(False)
            return "displayed"
        if not mail.Recipients.ResolveAll():
            bad = [str(r.Name) for r in mail.Recipients if not r.Resolved]
            raise ValueError("Outlook nu a putut rezolva destinatarii: " + ", ".join(bad) + ". Nimic nu a fost trimis.")
        mail.Send()
        return "sent"

    # ---- writing ----------------------------------------------------
    @staticmethod
    def _apply(appt, f: AppointmentFields, *, new: bool) -> None:
        appt.Subject = f.subject
        appt.Start = to_com_date(f.start_utc)
        appt.End = to_com_date(f.end_utc)
        appt.Body = f.body
        appt.AllDayEvent = False
        appt.BusyStatus = f.busy_status
        appt.MeetingStatus = OL_NON_MEETING  # personal, fara participanti, fara Teams
        if f.reminder_minutes > 0:
            appt.ReminderSet = True
            appt.ReminderMinutesBeforeStart = f.reminder_minutes
        else:
            appt.ReminderSet = False
        if f.category:
            appt.Categories = f.category
        if new:
            for name, value in ((PROP_SESSION, f.session_id), (PROP_WORKSPACE, f.workspace_id)):
                prop = appt.UserProperties.Add(name, OL_TEXT, True)
                prop.Value = value

    def create(self, store_id: str, folder_id: str, fields: AppointmentFields) -> AppointmentInfo:
        folder = self._folder(store_id, folder_id)
        appt = folder.Items.Add(OL_APPOINTMENT_ITEM)  # in calendarul ales, nu in cel implicit
        self._apply(appt, fields, new=True)
        appt.Save()  # NU Send()
        return self._info(appt)

    def update(self, entry_id: str, store_id: str, fields: AppointmentFields) -> AppointmentInfo:
        _, ns = self._connect()
        appt = ns.GetItemFromID(entry_id, store_id)
        self._apply(appt, fields, new=False)
        appt.Save()
        return self._info(appt)

    def delete(self, entry_id: str, store_id: str) -> None:
        _, ns = self._connect()
        ns.GetItemFromID(entry_id, store_id).Delete()  # ajunge in Elemente sterse (recuperabil)
