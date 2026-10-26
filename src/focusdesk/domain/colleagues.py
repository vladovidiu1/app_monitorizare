"""Identitatea unui coleg importat din Excel."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator


class Colleague(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    code: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Numele colegului este obligatoriu.")
        return value

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", value):
            raise ValueError("Codul trebuie sa fie un identificator, fara @ sau spatii.")
        return value

    @property
    def email(self) -> str:
        return f"{self.code}@eon.com"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.code})"