"""Identitatea unui coleg importat din Excel."""

from __future__ import annotations

from ..i18n import tr

import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Colleague(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    code: str = ""
    email_address: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError(tr('extra.domain.colleagues.numele_colegului_este_obligatoriu'))
        return value

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            return value
        if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", value):
            raise ValueError(tr('extra.domain.colleagues.codul_trebuie_sa_fie_un_identificator_fara_sau_spatii'))
        return value

    @field_validator("email_address")
    @classmethod
    def _smtp(cls, value):
        if value is not None and not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", value):
            raise ValueError(tr('domain.colleagues.adresa_smtp_invalida'))
        return value

    @model_validator(mode="after")
    def _identity(self):
        if not self.code and not self.email_address:
            raise ValueError(tr('domain.colleagues.codul_colegului_sau_adresa_smtp_explicita_este_obligatorie'))
        return self

    @property
    def email(self) -> str:
        return self.email_address or f"{self.code}@eon.com"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.code or self.email_address})"
