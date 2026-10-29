"""Import validat si pastrare atomica a registrului Excel in workspace."""

from __future__ import annotations

from ..i18n import tr

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile

from openpyxl import load_workbook

from ..domain.colleagues import Colleague
from ..domain.models import Node
from ..errors import ValidationError
from ..storage.atomic import atomic_write_bytes

if TYPE_CHECKING:
    from .workspace import Workspace


def _parse(data: bytes) -> list[Colleague]:
    try:
        book = load_workbook(BytesIO(data), read_only=True, data_only=False)
        try:
            sheet = book.worksheets[0]
            colleagues = []
            codes: set[str] = set()
            first = True
            for number, cells in enumerate(sheet.iter_rows(min_col=1, max_col=2), 1):
                name, code = [str(cell.value).strip() if cell.value is not None else "" for cell in cells]
                if not name and not code:
                    continue
                if first and name.casefold() in {"nume", "nume complet", "numele complet", "name"} and code.casefold() in {
                    "cod", "code", "cod coleg", "identificator",
                }:
                    first = False
                    continue
                first = False
                try:
                    if any(cell.data_type in {"f", "e"} for cell in cells):
                        raise ValueError(tr('extra.services.colleagues.formulele_si_erorile_excel_nu_sunt_acceptate'))
                    person = Colleague(name=name, code=code)
                    if person.code in codes:
                        raise ValueError(tr('extra.services.colleagues.cod_duplicat', person_code=person.code))
                except ValueError as exc:
                    raise ValidationError(tr('extra.services.colleagues.randul', number=number, exc=exc)) from exc
                codes.add(person.code)
                colleagues.append(person)
        finally:
            book.close()
    except ValidationError:
        raise
    except (BadZipFile, OSError, ValueError, KeyError, IndexError, SyntaxError) as exc:
        raise ValidationError(tr('extra.services.colleagues.fisier_excel_invalid', exc=exc)) from exc
    if not colleagues:
        raise ValidationError(tr('extra.services.colleagues.fisierul_nu_contine_colegi'))
    return sorted(colleagues, key=lambda person: (person.name.casefold(), person.code))


def _path(ws: Workspace) -> Path:
    return ws.root / "_system" / "colleagues.xlsx"


def load_colleagues(ws: Workspace) -> list[Colleague]:
    path = _path(ws)
    if not path.exists():
        return []
    return _parse(_read(path))


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValidationError(tr('extra.services.colleagues.nu_se_poate_citi_lista_de_colegi', exc=exc)) from exc


def import_colleagues(ws: Workspace, source: Path) -> list[Colleague]:
    ws._check_writable()
    if source.suffix.lower() != ".xlsx":
        raise ValidationError(tr('extra.services.colleagues.alege_un_fisier_excel_xlsx'))
    data = _read(source)
    people = _parse(data)
    atomic_write_bytes(_path(ws), data)
    ws.emit("colleagues_updated", count=len(people))
    return people


def requester(ws: Workspace, node: Node) -> Colleague | None:
    saved = node.requested_by
    if saved is None:
        return None
    if saved.email_address:
        return saved  # A real external SMTP address must never be rebuilt from a display name/code.
    return next((person for person in load_colleagues(ws) if person.code == saved.code), saved)
