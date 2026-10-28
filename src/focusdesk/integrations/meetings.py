"""Primitive calendar import DTOs. No COM object or message body crosses threads."""
from dataclasses import dataclass,field
from datetime import datetime,date

@dataclass(frozen=True)
class CalendarMeeting:
    uid: str
    start: datetime
    end: datetime
    title: str=''
    entry_id: str=''
    occurrence_key: str=''
    timezone: str=''
    location: str=''
    organizer: str=''
    join_url: str=''
    all_day: bool=False
    all_day_start: date|None=None
    all_day_end: date|None=None
    cancelled: bool=False
    session_id: str|None=None

@dataclass
class MeetingBatch:
    events: list[CalendarMeeting]=field(default_factory=list)
    complete: bool=True
    warnings: list[str]=field(default_factory=list)

# MS-OXOCAL named properties. Clean GOID identifies a series independently of occurrence dates.
PSET_MEETING='{6ED8DA90-450B-101B-98DA-00AA003F1305}'
PSET_APPOINTMENT='{00062002-0000-0000-C000-000000000046}'

def named_property(item,namespace,ident,kind):
    return item.PropertyAccessor.GetProperty(f'http://schemas.microsoft.com/mapi/id/{namespace}/{ident:04X}{kind}')


def clean_uid(item):
    try:
        raw=named_property(item,PSET_MEETING,0x23,'0102')
        return bytes(raw).hex() if not isinstance(raw,str) else raw
    except Exception:
        uid=str(getattr(item,'GlobalAppointmentID','') or '')
        # GlobalObjectId encodes the occurrence date at byte offsets 16..19.
        try:
            raw=bytearray.fromhex(uid)
            if len(raw)>=40:raw[16:20]=b'\0'*4;return raw.hex()
        except ValueError:pass
        return uid


def read_outlook_meetings(backend,store_id,folder_id,start,end):
    """Bounded Restrict; never falls back to traversing the whole Outlook calendar."""
    from datetime import timezone
    from urllib.parse import urlparse
    from .outlook import MAX_EVENTS
    from .outlook_com import outlook_filter_datetime, PROP_SESSION, to_utc
    folder=backend._folder(store_id,folder_id)
    items=folder.Items;items.Sort('[Start]');items.IncludeRecurrences=True
    collection=items.Restrict(f"[Start] < '{outlook_filter_datetime(end)}' AND [End] > '{outlook_filter_datetime(start)}'")
    out=MeetingBatch();item=collection.GetFirst();count=0
    def stamp(value):return value.replace(tzinfo=timezone.utc)
    while item is not None and count<MAX_EVENTS:
        count+=1
        try:
            # StartUTC/EndUTC bypass the ambiguous local Windows wall time at DST.
            a=stamp(item.StartUTC);b=stamp(item.EndUTC)
            if b<=start or a>=end:item=collection.GetNext();continue
            recurrence=int(getattr(item,'RecurrenceState',0))
            uid=clean_uid(item)
            if not uid and recurrence:raise ValueError('Recurență fără identificator de serie stabil; element omis')
            uid=uid or str(item.EntryID)
            slot=''
            if recurrence in (2,3):
                if recurrence==3:
                    # PidLidExceptionReplaceTime = original UTC slot, not the moved start.
                    original=named_property(item,PSET_APPOINTMENT,0x8228,'0040')
                    slot=stamp(original).isoformat()
                else:slot=a.isoformat()
            elif recurrence==1:
                raise ValueError('Outlook a returnat masterul recurent în loc de apariție; nu se importă ca întâlnire separată')
            link=''
            try:link=str(named_property(item,PSET_APPOINTMENT,0x8245,'001F') or '')
            except Exception:pass
            if urlparse(link).scheme not in ('https','http'):link=''
            try:tz=str(item.StartTimeZone.ID)
            except Exception:tz=''
            out.events.append(CalendarMeeting(uid=uid,entry_id=str(item.EntryID),occurrence_key=slot,start=a,end=b,
                title=str(item.Subject or ''),timezone=tz,location=str(getattr(item,'Location','') or ''),
                organizer=str(getattr(item,'Organizer','') or ''),join_url=link,all_day=bool(getattr(item,'AllDayEvent',False)),
                all_day_start=item.Start.date() if bool(getattr(item,'AllDayEvent',False)) else None,
                all_day_end=item.End.date() if bool(getattr(item,'AllDayEvent',False)) else None,
                cancelled=int(getattr(item,'MeetingStatus',0)) in (5,7),session_id=backend._prop(item,PROP_SESSION)))
        except Exception as exc:
            out.complete=False;out.warnings.append('Element omis: '+str(exc))
        item=collection.GetNext()
    if item is not None:
        out.complete=False;out.warnings.append(f'Limită de {MAX_EVENTS} evenimente atinsă; rezultatul este parțial.')
    return out
