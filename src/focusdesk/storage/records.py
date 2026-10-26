"""Stocare generica de inregistrari JSON identificate prin UUID (sesiuni, istoric, note...)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ..errors import CorruptFileError, NotFoundError
from .atomic import atomic_write_json, read_json

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)


class RecordStore(Generic[M]):
    def __init__(self, directory: Path, model: type[M], *, keep_backup: bool = False) -> None:
        self.directory = Path(directory)
        self.model = model
        self.keep_backup = keep_backup
        self.errors: list[tuple[Path, str]] = []

    def _path(self, record_id: str) -> Path:
        return self.directory / f"{record_id}.json"

    def save(self, record: M) -> None:
        atomic_write_json(self._path(record.id), record.model_dump(mode="json"), keep_backup=self.keep_backup)  # type: ignore[attr-defined]

    def get(self, record_id: str) -> M:
        p = self._path(record_id)
        if not p.exists():
            raise NotFoundError(f"Înregistrarea {record_id} nu există.")
        data, _, _ = read_json(p)
        return self.model.model_validate(data)

    def delete(self, record_id: str) -> None:
        self._path(record_id).unlink(missing_ok=True)

    def list_all(self, *, check=None) -> list[M]:
        """Citeste toate inregistrarile; cele corupte sunt raportate in `errors`, nu ridica exceptii."""
        self.errors = []
        out: list[M] = []
        if not self.directory.exists():
            return out
        for p in sorted(self.directory.glob("*.json")):
            if check:
                check()
            try:
                data, _, _ = read_json(p)
                out.append(self.model.model_validate(data))
            except (CorruptFileError, PydanticValidationError) as exc:
                self.errors.append((p, str(exc)))
                log.warning("Înregistrare invalidă %s: %s", p, exc)
        return out
