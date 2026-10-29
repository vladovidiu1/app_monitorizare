"""Offline messages and display formats. No workspace data enters the catalogs.

Language is fixed for a process: saving a preference never rebuilds live editors.
Catalog values are Unicode strings or CLDR-style one/few/other plural mappings.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from string import Formatter

LANGUAGES = {'ro': 'Română', 'en': 'English', 'de': 'Deutsch', 'fr': 'Français', 'es': 'Español'}
log = logging.getLogger(__name__)


def resource_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'focusdesk' / 'resources'
    return Path(__file__).parent / 'resources'


def profile_language() -> str:
    try:
        path = Path(os.environ.get('APPDATA') or Path.home()) / 'FocusDesk' / 'app.json'
        code = json.loads(path.read_text('utf-8')).get('language', 'ro')
        return code if code in LANGUAGES else 'ro'
    except (OSError, ValueError, TypeError, AttributeError):
        return 'ro'


_language = profile_language()
_catalogs: dict[str, dict] = {}
_missing: set[tuple[str, str]] = set()


def language() -> str:
    return _language


def _catalog(code: str) -> dict:
    if code not in _catalogs:
        try:
            data = json.loads((resource_dir() / 'locales' / f'{code}.json').read_text('utf-8'))
            if not isinstance(data, dict): raise ValueError('catalog must be an object')
            _catalogs[code] = data
        except (OSError, ValueError):
            log.exception('Cannot load FocusDesk language catalog: %s', code)
            _catalogs[code] = {}
    return _catalogs[code]


def plural_category(count: int | float, code: str | None = None) -> str:
    code = code or _language
    if code == 'ro':
        if count == 1: return 'one'
        if count != int(count) or count == 0 or 1 <= count % 100 <= 19: return 'few'
        return 'other'
    if code == 'fr': return 'one' if 0 <= count < 2 else 'other'
    return 'one' if count == 1 else 'other'


def tr(key: str, *, count: int | float | None = None, **params) -> str:
    """Named interpolation only; log a missing key once and use Romanian fallback.

    A key missing even from the source catalog is visible as [key], never blank.
    Missing arguments are programmer errors, not silently discarded user context.
    """
    code = _language
    entry = _catalog(code).get(key)
    entry_code = code
    if entry is None:
        if (code, key) not in _missing:
            _missing.add((code, key)); log.warning('Missing translation: %s:%s', code, key)
        entry = _catalog('ro').get(key, f'[{key}]')
        entry_code = 'ro'
    if isinstance(entry, dict):
        if count is None: raise ValueError(f'count required: {key}')
        entry = entry.get(plural_category(count, entry_code), entry['other'])
    if count is not None: params.setdefault('count', count)
    return entry.format_map({name: _DateValue(value) if isinstance(value, date) else value for name,value in params.items()})


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


def validate_catalogs(directory: Path | None = None) -> list[str]:
    directory = directory or resource_dir() / 'locales'
    errors = []
    data = {code: json.loads((directory / f'{code}.json').read_text('utf-8')) for code in LANGUAGES}
    source = data['ro']
    for code, catalog in data.items():
        for key in source.keys() ^ catalog.keys(): errors.append(f'{code}: inconsistent key {key}')
        for key in source.keys() & catalog.keys():
            expected, actual = source[key], catalog[key]
            variants = actual.values() if isinstance(actual, dict) else [actual]
            bases = expected.values() if isinstance(expected, dict) else [expected]
            wanted = set.union(*(fields(v) for v in bases))
            if isinstance(expected, dict) != isinstance(actual, dict): errors.append(f'{code}:{key}: plural type')
            if isinstance(actual, dict) and not ({'one', 'other'} <= actual.keys()): errors.append(f'{code}:{key}: plural forms')
            for text in variants:
                if not text.strip() or fields(text) != wanted: errors.append(f'{code}:{key}: parameters/content')
    return errors


# Input uses the explicitly advertised ISO or day-first format in every language.
# Display formats never call process-global locale.setlocale (workers are concurrent).
def date_text(value: date | None, *, iso: bool = False) -> str:
    if value is None: return ''
    if iso: return value.isoformat()
    return value.strftime('%d/%m/%Y' if _language in ('en', 'fr', 'es') else '%d.%m.%Y')


def datetime_text(value: datetime) -> str:
    return f'{date_text(value)} {value:%H:%M}'


def number(value: int | float, digits: int = 0) -> str:
    text = f'{value:,.{digits}f}'
    group, decimal = {'ro': ('.', ','), 'en': (',', '.'), 'de': ('.', ','), 'fr': ('\u202f', ','), 'es': ('.', ',')}[_language]
    return text.replace(',', '\0').replace('.', decimal).replace('\0', group)


def percent(value: float, digits: int = 0) -> str:
    return tr('format.percent', value=number(value, digits))


def month_name(month: int) -> str:
    return tr(f'calendar.month.{month}')


def weekday_name(day: int) -> str:
    return tr(f'calendar.weekday.{day}')


def long_date(value: date) -> str:
    return tr('format.long_date', day=value.day, month=month_name(value.month), year=value.year, weekday=weekday_name(value.weekday()))


class _DateValue:
    def __init__(self,value):self.value=value
    def __format__(self,spec):
        if '%d.%m.%Y' in spec and language() in ('en','fr','es'):
            spec=spec.replace('%d.%m.%Y','%d/%m/%Y')
        return format(self.value,spec)
    def __str__(self):return str(self.value)
    def __repr__(self):return repr(self.value)


def datetime_seconds_text(value: datetime) -> str:
    return f'{date_text(value)} {value:%H:%M:%S}'


def short_date_text(value: date) -> str:
    return tr('format.short_date',date=value)


def short_datetime_text(value: datetime) -> str:
    return f'{short_date_text(value)} {value:%H:%M}'


def month_year_text(value: date) -> str:
    return value.strftime('%m/%Y' if language() in ('en','fr','es') else '%m.%Y')


def hours_text(value: float) -> str:
    return tr('format.hours',hours=number(value,1))
