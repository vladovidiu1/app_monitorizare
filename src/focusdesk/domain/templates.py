"""Strict, portable templates. Local keys are never workspace UUIDs or file paths."""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .common import new_id, is_uuid
from .models import Kind, Priority, Node, Status

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
EXCLUDED = ('ID-uri originale; istoric, notițe, sesiuni și timp lucrat; sincronizări Outlook; '
            'checkpointuri și Git; solicitant și adrese de colegi; fișiere și căi locale; '
            'referințe externe structurii; termene calendaristice și prioritate azi; '
            'statusuri și bife de checklist. Textul liber este păstrat: verifică manual datele personale din descrieri.')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

class TemplateItem(Strict):
    key: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,63}$')
    parent: str | None = None
    kind: Kind = Kind.TASK
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default='', max_length=500_000)
    checklist: list[str] = Field(default_factory=list, max_length=500)
    priority: Priority | None = None
    tags: list[str] = Field(default_factory=list, max_length=100)
    estimated_minutes: int | None = Field(default=None, ge=0)
    next_action: str | None = None
    depends_on: list[str] = Field(default_factory=list, max_length=500)
    related: list[str] = Field(default_factory=list, max_length=500)

class StructureTemplate(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(default_factory=new_id)
    revision: int = Field(default=1, ge=1)
    name: str = Field(min_length=1, max_length=200)
    variables: list[str] = Field(default_factory=list, max_length=40)
    items: list[TemplateItem] = Field(min_length=1, max_length=500)

    @field_validator('schema_version', mode='before')
    @classmethod
    def version(cls, value):
        if type(value) is not int or value != 1:raise ValueError('Versiune de schemă incompatibilă')
        return value

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():raise ValueError('Numele șablonului nu poate fi gol')
        return value.strip()

    @field_validator('id')
    @classmethod
    def valid_id(cls, value):
        if not is_uuid(value): raise ValueError('ID șablon invalid')
        return value

    @field_validator('variables')
    @classmethod
    def variable_names(cls, values):
        if len(set(values)) != len(values) or any(not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,63}', v) for v in values):
            raise ValueError('Variabilele trebuie să aibă nume distincte: litere, cifre și underscore.')
        return values

    @model_validator(mode='after')
    def graph(self):
        by = {i.key:i for i in self.items}
        if len(by) != len(self.items): raise ValueError('Chei de element duplicate')
        roots = [i for i in self.items if i.parent is None]
        if len(roots) != 1 or roots[0].kind not in (Kind.PROJECT, Kind.TASK):
            raise ValueError('Este necesară o singură rădăcină proiect/task')
        for item in self.items:
            if item.parent is not None:
                if item.parent not in by: raise ValueError('Părinte inexistent')
                parent = by[item.parent]
                if parent.kind == Kind.TASK and item.kind != Kind.TASK: raise ValueError('Un task conține doar taskuri')
                if item.kind == Kind.PROJECT and parent.kind != Kind.FOLDER: raise ValueError('Proiectul necesită părinte folder')
            for ref in item.depends_on + item.related:
                if ref not in by or ref == item.key: raise ValueError('Referință internă invalidă')
            # Reuse Node's kind/title/estimate rules without preserving any UUID.
            Node(kind=item.kind, title=item.title, status=Status.TODO if item.kind != Kind.FOLDER else None,
                 estimated_minutes=item.estimated_minutes)
            if item.kind == Kind.FOLDER and item.depends_on: raise ValueError('Folderul nu are dependențe')
        for edges in ({i.key:[i.parent] if i.parent else [] for i in self.items}, {i.key:i.depends_on for i in self.items}):
            # Iterative Kahn traversal: imported deep structures cannot overflow Python recursion.
            pending={key:set(values) for key,values in edges.items()}
            ready=[key for key,values in pending.items() if not values]
            visited=set()
            reverse={key:[] for key in by}
            for key,values in pending.items():
                for ref in values: reverse[ref].append(key)
            while ready:
                key=ready.pop();visited.add(key)
                for child in reverse[key]:
                    pending[child].discard(key)
                    if not pending[child] and child not in visited:ready.append(child)
            if len(visited)!=len(by):raise ValueError('Ciclu în ierarhie sau dependențe')
        return self

    def ordered(self):
        children={None:[]}
        for item in self.items:children.setdefault(item.parent,[]).append(item)
        stack=list(reversed(children[None]));out=[]
        while stack:
            item=stack.pop();out.append(item);stack.extend(reversed(children.get(item.key,[])))
        return out

    @property
    def root(self):return next(i for i in self.items if i.parent is None)


def substitute(text: str, values: dict[str,str], *, limit=500_000) -> str:
    """Only declared placeholders, one pass; cap expansion before allocating a huge string."""
    parts=[];end=0;size=0
    for match in re.finditer(r'\{\{([a-zA-Z][a-zA-Z0-9_]*)\}\}',text):
        prefix=text[end:match.start()];replacement=values.get(match[1],match[0])
        size+=len(prefix)+len(replacement)
        if size>limit:raise ValueError('Textul rezultat depășește limita permisă.')
        parts.extend((prefix,replacement));end=match.end()
    if size+len(text)-end>limit:raise ValueError('Textul rezultat depășește limita permisă.')
    parts.append(text[end:]);return ''.join(parts)
