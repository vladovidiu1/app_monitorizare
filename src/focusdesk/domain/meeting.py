"""Local meetings are calendar context, never work sessions or task nodes."""

from ..i18n import tr
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .common import UtcDateTime, new_id, utcnow, is_uuid

class MeetingSource(BaseModel):
    model_config=ConfigDict(extra='allow')
    id: str=Field(default_factory=new_id)
    provider: Literal['manual','outlook']='manual'
    source_key: str=''
    store_id: str=''
    folder_id: str=''
    event_uid: str=''
    occurrence_key: str=''
    entry_id: str=''
    title: str
    start_at: UtcDateTime
    end_at: UtcDateTime
    timezone: str='Europe/Bucharest'
    source_timezone: str=''
    location: str=''
    organizer: str=''
    join_url: str=''
    all_day: bool=False
    all_day_start: date|None=None
    all_day_end: date|None=None
    state: Literal['present','cancelled','not_seen']='present'
    last_seen_at: UtcDateTime=Field(default_factory=utcnow)

    @field_validator('id')
    @classmethod
    def uuid(cls,value):
        if not is_uuid(value):raise ValueError(tr('extra.domain.meeting.uuid_intalnire_invalid'))
        return value

    @field_validator('title')
    @classmethod
    def title_valid(cls,value):
        if not value.strip() or len(value)>1000:raise ValueError(tr('extra.domain.meeting.titlu_obligatoriu_maximum_1000_caractere'))
        return value.strip()

    @model_validator(mode='after')
    def interval(self):
        if self.end_at<=self.start_at:raise ValueError(tr('extra.domain.meeting.sfarsitul_trebuie_sa_fie_dupa_inceput'))
        if self.all_day_start and self.all_day_end and self.all_day_end<=self.all_day_start:
            raise ValueError(tr('extra.domain.meeting.interval_all_day_invalid_sfarsitul_este_exclusiv'))
        return self

class MeetingAction(BaseModel):
    model_config=ConfigDict(extra='allow')
    id: str=Field(default_factory=new_id)
    text: str
    responsible: str=''
    due_date: date|None=None
    state: Literal['clarify','todo','converted','closed']='clarify'
    node_id: str|None=None

    @field_validator('id','node_id')
    @classmethod
    def uuid(cls,value):
        if value is not None and not is_uuid(value):raise ValueError(tr('extra.domain.meeting.uuid_actiune_invalid'))
        return value

    @field_validator('text')
    @classmethod
    def text_valid(cls,value):
        if not value.strip():raise ValueError(tr('extra.domain.meeting.textul_actiunii_este_obligatoriu'))
        return value.strip()

class MeetingLocal(BaseModel):
    model_config=ConfigDict(extra='allow')
    actions: list[MeetingAction]=Field(default_factory=list)
    linked_node_ids: list[str]=Field(default_factory=list)

    @model_validator(mode='after')
    def unique_actions(self):
        if len({a.id for a in self.actions})!=len(self.actions):raise ValueError(tr('extra.domain.meeting.identificatori_de_actiuni_duplicati'))
        return self

    @field_validator('linked_node_ids')
    @classmethod
    def ids(cls,value):
        if any(not is_uuid(v) for v in value):raise ValueError(tr('extra.domain.meeting.referinta_la_nod_invalida'))
        return list(dict.fromkeys(value))
