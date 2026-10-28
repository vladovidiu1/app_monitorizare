"""JSON records with disposable metadata indexes and bounded, copy-on-read payloads."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar
import logging
import json
import hashlib
from bisect import bisect_left
from datetime import datetime

from pydantic import BaseModel, ValidationError as PydanticValidationError
from ..errors import CorruptFileError, NotFoundError, ExternalModificationError, ReadOnlyError
from .atomic import atomic_write_json, atomic_write_bytes, read_json, sha256_file

log = logging.getLogger(__name__)
M = TypeVar('M', bound=BaseModel)
# Payloads (notes, summaries, event data, sync details) stay in authoritative files.
def write_cache(path, data):
    return atomic_write_bytes(path, json.dumps(data, ensure_ascii=False, separators=(',',':')).encode())


def checksum(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


SUMMARY_FIELDS = {'id','node_id','start_at','end_at','status','actual_seconds',
                  'started_actual_at','stopped_actual_at','origin','at','type','state','created_at'}


def signature(path):
    s = path.stat()
    return [s.st_mtime_ns, s.st_size, s.st_ctime_ns]


class RecordStore(Generic[M]):
    def __init__(self, directory: Path, model: type[M], *, keep_backup=False,
                 writable=lambda: True, before_write=lambda: None):
        self.directory = Path(directory)
        self.model, self.keep_backup = model, keep_backup
        self.cache_version = 2 if model.__name__ == "HistoryEvent" else (3 if model.__name__ == "SessionRecord" else 1)
        self.summary_fields = SUMMARY_FIELDS & set(model.model_fields)
        if self.cache_version == 2: self.summary_fields = self.summary_fields | {"transition_to"}
        self.writable, self.before_write = writable, before_write
        self.errors = []
        self._observed = {}
        self._entries = {} if not self.directory.exists() else None
        self._by_node = {}
        self._by_status = {}
        self._payloads = OrderedDict()
        self._mutex = RLock()
        self.revision = 0
        self._dirty = False
        self._derived_revision = -1
        self._dates = {}
        self._totals = {}
        self.cache_path = self.directory / '.cache' / 'index.json'
        self.marker = self.directory / '.cache' / 'dirty.json'

    def _path(self, record_id):
        # No caller-controlled path traversal, including malformed cache contents.
        if Path(record_id).name != record_id or record_id in ('.','..'):
            raise NotFoundError('Identificator de înregistrare invalid.')
        return self.directory / f'{record_id}.json'

    def invalidate(self):
        with self._mutex:
            self._entries = None
            self._payloads.clear()
            self._by_node.clear()
            self._observed.clear()
            self.revision += 1

    def _index(self, *, check=None):
        if self._entries is not None:
            return
        entries = {}
        try:
            cache, _, _ = read_json(self.cache_path, allow_backup=False)
            if cache['version'] == self.cache_version and cache['model'] == self.model.__name__ and cache['checksum'] == checksum(cache['entries']) and not self.marker.exists():
                entries = cache['entries']
                if not isinstance(entries, dict): entries = {}
        except (CorruptFileError, KeyError, TypeError):
            pass
        self.errors = []
        valid = {}
        for path in sorted(self.directory.glob('*.json')):
            if check: check()
            try:
                stamp = signature(path)
                entry = entries.get(path.stem)
                if not isinstance(entry, dict) or entry.get('stamp') != stamp or not isinstance(entry.get('summary'), dict) or entry['summary'].get('id') != path.stem or set(entry['summary']) != self.summary_fields or not isinstance(entry.get('digest'),str) or len(entry['digest']) != 64:
                    data, digest, _ = read_json(path)
                    record = self.model.model_validate(data)
                    if record.id != path.stem:
                        raise ValueError('UUID diferit de numele fișierului')
                    entry = self._entry(record, stamp, digest)
                valid[path.stem] = entry
            except (CorruptFileError, PydanticValidationError, OSError, ValueError) as exc:
                self.errors.append((path, str(exc)))
                log.warning('Înregistrare invalidă %s: %s', path, exc)
        self._entries = valid
        self._observed.clear()
        self._rebuild_nodes()
        self._dirty = True
        self.flush()

    def _rebuild_nodes(self):
        self._by_node = {}
        self._by_status = {}
        for rid, entry in self._entries.items():
            self._by_node.setdefault(entry['summary'].get('node_id'), set()).add(rid)
            self._by_status.setdefault(entry['summary'].get('status'),set()).add(rid)

    def _entry(self, record, stamp, digest):
        data = record.model_dump(mode='json')
        summary = {k:v for k,v in data.items() if k in SUMMARY_FIELDS and k in self.model.model_fields}
        if self.cache_version == 2: summary['transition_to'] = data.get('data',{}).get('to') if data.get('type') == 'status_changed' else None
        return {'stamp':stamp,'digest':digest,'summary':summary}

    def _mark(self):
        if not self.writable(): raise ReadOnlyError("Workspace-ul este deschis doar pentru citire.")
        self.before_write()
        if self.writable() and not self.marker.exists():
            atomic_write_json(self.marker, {'dirty': True}, keep_backup=False)

    def save(self, record: M):
        with self._mutex:
            rid = record.id
            path = self._path(rid)
            old = self._entries.get(rid) if self._entries is not None else self._observed.get(rid)
            if old is None and path.exists():
                raise ExternalModificationError('Înregistrare existentă necitită. Reîncarcă înainte de scriere.')
            if old and (not path.exists() or sha256_file(path) != old['digest']):
                raise ExternalModificationError('Înregistrarea a fost modificată extern. Reîncarcă workspace-ul.')
            self._mark()
            digest = atomic_write_json(path, record.model_dump(mode='json'), keep_backup=self.keep_backup)
            entry = self._entry(record, signature(path), digest)
            if old:
                self._by_node.get(old['summary'].get('node_id'), set()).discard(rid)
                self._by_status.get(old['summary'].get('status'),set()).discard(rid)
            if self._entries is not None:
                self._entries[rid] = entry
                self._by_status.setdefault(entry['summary'].get('status'),set()).add(rid)
                self._by_node.setdefault(entry['summary'].get('node_id'), set()).add(rid)
            self._observed[rid] = entry
            self._remember(rid, record)
            self._dirty = True
            self.revision += 1

    def _remember(self, rid, record):
        self._payloads[rid] = record.model_copy(deep=True)
        self._payloads.move_to_end(rid)
        while len(self._payloads) > 128: self._payloads.popitem(last=False)

    def get(self, record_id: str) -> M:
        with self._mutex:
            path = self._path(record_id)
            if not path.exists(): raise NotFoundError(f'Înregistrarea {record_id} nu există.')
            stamp = signature(path)
            entry = self._entries.get(record_id) if self._entries is not None else None
            if record_id in self._payloads and entry and entry['stamp'] == stamp:
                return self._payloads[record_id].model_copy(deep=True)
            data, digest, _ = read_json(path)
            record = self.model.model_validate(data)
            if self._entries is None: self._observed[record_id] = self._entry(record, stamp, digest)
            # A fresh read may observe an external edit; it becomes the conflict baseline.
            if self._entries is not None and (entry is None or entry['stamp'] != stamp):
                if entry: self._by_node.get(entry['summary'].get('node_id'), set()).discard(record_id)
                self._entries[record_id] = self._entry(record, stamp, digest)
                self._by_node.setdefault(getattr(record,'node_id',None), set()).add(record_id)
                self._rebuild_nodes()
                self.revision += 1
                self._dirty = True
            self._remember(record_id, record)
            return record.model_copy(deep=True)

    def delete(self, record_id):
        with self._mutex:
            self._index()
            path = self._path(record_id)
            old = self._entries.get(record_id)
            if old and path.exists() and sha256_file(path) != old['digest']:
                raise ExternalModificationError('Înregistrarea a fost modificată extern. Reîncarcă înainte de ștergere.')
            self._mark()
            path.unlink(missing_ok=True)
            old = self._entries.pop(record_id, None)
            if old: self._by_node.get(old['summary'].get('node_id'),set()).discard(record_id)
            if old: self._by_status.get(old['summary'].get('status'),set()).discard(record_id)
            self._payloads.pop(record_id,None)
            self._dirty = True
            self.revision += 1

    def summaries(self):
        with self._mutex:
            self._index()
            return [dict(e['summary']) for e in self._entries.values()]

    def select(self, *, node_ids=None, statuses=None, predicate=None, check=None):
        with self._mutex:
            self._index(check=check)
            ids = self._entries.keys() if node_ids is None else set().union(*(self._by_node.get(n,set()) for n in node_ids))
            if statuses is not None:
                ids = set(ids) & set().union(*(self._by_status.get(status,set()) for status in statuses))
            out = []
            for rid in sorted(ids):
                if check: check()
                if predicate is None or predicate(self._entries[rid]['summary']):
                    try: out.append(self.get(rid))
                    except (CorruptFileError, PydanticValidationError, NotFoundError) as exc:
                        self.errors.append((self._path(rid),str(exc)))
            return out

    def _derive(self):
        self._index()
        if self._derived_revision == self.revision: return
        self._dates = {'start_at':[], 'worked_at':[]}
        self._max_duration = 0
        self._totals = {}
        for rid, entry in self._entries.items():
            row = entry['summary']
            if 'start_at' not in row: continue
            duration = (datetime.fromisoformat(row['end_at'])-datetime.fromisoformat(row['start_at'])).total_seconds()
            self._max_duration = max(self._max_duration,duration)
            for field, value in [('start_at',row['start_at']), ('worked_at',row.get('started_actual_at') or row['start_at'])]:
                self._dates[field].append((datetime.fromisoformat(value),rid))
            seconds = max(0,row.get('actual_seconds',0))
            self._totals[row['node_id']] = self._totals.get(row['node_id'],0) + seconds
        for values in self._dates.values(): values.sort()
        self._derived_revision = self.revision

    def ids(self):
        with self._mutex:
            self._index()
            return self._entries.keys()

    def overlapping(self, start, end, statuses):
        from datetime import timedelta
        with self._mutex:
            self._derive()
            # No interval ending after start can begin before start-max_duration.
            values = self._dates['start_at']
            lo = bisect_left(values,(start-timedelta(seconds=self._max_duration),''))
            hi = bisect_left(values,(end,''))
            return self.select_ids((rid for _,rid in values[lo:hi]),predicate=lambda r:
                r['status'] in statuses and datetime.fromisoformat(r['end_at']) > start)

    def worked_for_node(self,node_id):
        with self._mutex:
            self._derive()
            return self._totals.get(node_id,0)

    def worked_totals(self):
        with self._mutex:
            self._derive()
            return dict(self._totals)

    def in_period(self, start, end, *, worked=False, statuses=None):
        """Union actual/planned dates for reports; all filtering precedes UI paging."""
        with self._mutex:
            self._derive()
            ids = set()
            for field in (('start_at','worked_at') if worked else ('start_at',)):
                values = self._dates[field]
                lo = bisect_left(values,(start,'')); hi = bisect_left(values,(end,''))
                ids.update(rid for _,rid in values[lo:hi])
            return self.select_ids(ids, predicate=lambda r: statuses is None or r.get('status') in statuses)

    def select_ids(self, ids, predicate=None):
        out = []
        for rid in sorted(ids):
            if predicate is None or predicate(self._entries[rid]['summary']):
                try: out.append(self.get(rid))
                except (CorruptFileError, PydanticValidationError, NotFoundError) as exc:
                    self.errors.append((self._path(rid),str(exc)))
        return out

    def list_all(self, *, check=None):
        return self.select(check=check)

    def flush(self):
        with self._mutex:
            if self._entries is None or not self._dirty or not self.writable(): return
            try:
                write_cache(self.cache_path, {'version':self.cache_version,'model':self.model.__name__,'entries':self._entries,'checksum':checksum(self._entries)})
                self.marker.unlink(missing_ok=True)
                self._dirty = False
            except Exception:
                log.warning('Index de înregistrări nescris: %s',self.cache_path,exc_info=True)
