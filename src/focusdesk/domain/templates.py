"""Strict, portable templates. Local keys are never workspace UUIDs or file paths."""
from __future__ import annotations

from ..i18n import tr

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .common import new_id, is_uuid
from .models import Kind, Priority, Node, Status

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
EXCLUDED = (tr('extra.domain.templates.id_uri_originale_istoric_notite_sesiuni_si_timp_lucrat_sincroniza'))

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
        if type(value) is not int or value != 1:raise ValueError(tr('extra.domain.templates.versiune_de_schema_incompatibila'))
        return value

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():raise ValueError(tr('extra.domain.templates.numele_sablonului_nu_poate_fi_gol'))
        return value.strip()

    @field_validator('id')
    @classmethod
    def valid_id(cls, value):
        if not is_uuid(value): raise ValueError(tr('services.templates.id_sablon_invalid'))
        return value

    @field_validator('variables')
    @classmethod
    def variable_names(cls, values):
        if len(set(values)) != len(values) or any(not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,63}', v) for v in values):
            raise ValueError(tr('extra.domain.templates.variabilele_trebuie_sa_aiba_nume_distincte_litere_cifre_si_unders'))
        return values

    @model_validator(mode='after')
    def graph(self):
        by = {i.key:i for i in self.items}
        if len(by) != len(self.items): raise ValueError(tr('extra.domain.templates.chei_de_element_duplicate'))
        roots = [i for i in self.items if i.parent is None]
        if len(roots) != 1 or roots[0].kind not in (Kind.PROJECT, Kind.TASK):
            raise ValueError(tr('extra.domain.templates.este_necesara_o_singura_radacina_proiect_task'))
        for item in self.items:
            if item.parent is not None:
                if item.parent not in by: raise ValueError(tr('extra.domain.templates.parinte_inexistent'))
                parent = by[item.parent]
                if parent.kind == Kind.TASK and item.kind != Kind.TASK: raise ValueError(tr('extra.domain.templates.un_task_contine_doar_taskuri'))
                if item.kind == Kind.PROJECT and parent.kind != Kind.FOLDER: raise ValueError(tr('extra.domain.templates.proiectul_necesita_parinte_folder'))
            for ref in item.depends_on + item.related:
                if ref not in by or ref == item.key: raise ValueError(tr('extra.domain.templates.referinta_interna_invalida'))
            # Reuse Node's kind/title/estimate rules without preserving any UUID.
            Node(kind=item.kind, title=item.title, status=Status.TODO if item.kind != Kind.FOLDER else None,
                 estimated_minutes=item.estimated_minutes)
            if item.kind == Kind.FOLDER and item.depends_on: raise ValueError(tr('extra.domain.templates.folderul_nu_are_dependente'))
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
            if len(visited)!=len(by):raise ValueError(tr('extra.domain.templates.ciclu_in_ierarhie_sau_dependente'))
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
        if size>limit:raise ValueError(tr('extra.domain.templates.textul_rezultat_depaseste_limita_permisa'))
        parts.extend((prefix,replacement));end=match.end()
    if size+len(text)-end>limit:raise ValueError(tr('extra.domain.templates.textul_rezultat_depaseste_limita_permisa'))
    parts.append(text[end:]);return ''.join(parts)
