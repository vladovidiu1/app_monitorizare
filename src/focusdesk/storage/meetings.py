"""Meeting JSON and Markdown, separate CAS baselines and disposable compact index."""

from ..i18n import tr
from pathlib import Path
from threading import RLock
from ..domain.common import is_uuid
from ..domain.meeting import MeetingSource, MeetingLocal
from ..errors import NotFoundError, ExternalModificationError, UnsafePathError
from .atomic import read_json, atomic_write_json, atomic_write_text, sha256_file
from .records import checksum, signature, write_cache
from .paths import is_reparse_point, ensure_path_fits

class MeetingStore:
    def __init__(self,repo):
        self.repo=repo;self.root=repo.system_dir/'meetings';self.cache=self.root/'.cache'/'index.json'
        self._entries=None;self._baselines={};self._mutex=RLock();self.issues=[];self.revision=0

    def path(self,mid,name):
        if not is_uuid(mid) or name not in ('source.json','local.json','notes.md'):raise NotFoundError(tr('storage.meetings.identificator_de_intalnire_invalid'))
        path=self.root/mid/name
        if any(is_reparse_point(p) for p in (self.root,path.parent,path)):raise UnsafePathError(tr('storage.meetings.cale_intalnire_nesigura'))
        ensure_path_fits(path);return path

    def invalidate(self):
        with self._mutex:self._entries=None;self.revision+=1

    def _read(self,mid,name,model):
        path=self.path(mid,name)
        if not path.exists():
            if name=='local.json':self._baselines[(mid,name)]=None;return MeetingLocal()
            raise NotFoundError(tr('storage.meetings.intalnirea_nu_mai_este_disponibila'))
        data,digest,_=read_json(path,allow_backup=False);value=model.model_validate(data)
        if name=='source.json' and value.id!=mid:raise ValueError(tr('storage.meetings.uuid_diferit_de_directorul_intalnirii'))
        self._baselines[(mid,name)]=digest;return value

    def source(self,mid):
        with self._mutex:return self._read(mid,'source.json',MeetingSource)

    def local(self,mid):
        with self._mutex:return self._read(mid,'local.json',MeetingLocal)

    def notes(self,mid,*,observe=True):
        with self._mutex:
            self.source(mid);path=self.path(mid,'notes.md')
            if not path.exists():
                if observe:self._baselines[(mid,'notes.md')]=None
                return ''
            raw=path.read_bytes();from .atomic import sha256_bytes
            text=raw.decode('utf-8-sig')
            if observe:self._baselines[(mid,'notes.md')]=sha256_bytes(raw)
            return text

    def _write(self,mid,name,value):
        self.repo._require_writable();path=self.path(mid,name);key=(mid,name)
        expected=self._baselines.get(key)
        if path.exists():
            if key not in self._baselines or sha256_file(path)!=expected:
                raise ExternalModificationError(tr('storage.meetings.intalnirea_sau_notitele_au_fost_modificate_extern_ciorna_ramane_in_edi'))
        elif expected is not None:raise ExternalModificationError(tr('storage.meetings.fisierul_intalnirii_a_fost_sters_extern'))
        digest=atomic_write_text(path,value) if name=='notes.md' else atomic_write_json(path,value.model_dump(mode='json'))
        self._baselines[key]=digest
        if self._entries is not None:
            try:self._entries[mid]=self._entry(mid)
            except Exception:self._entries=None
        self.revision+=1
        # Cache checkpoint is batched; authoritative JSON/Markdown is already atomic.

    def flush(self):
        with self._mutex:self._save_index()

    def save_source(self,record):
        with self._mutex:self._write(record.id,'source.json',record)

    def save_local(self,mid,record):
        with self._mutex:self.source(mid);self._write(mid,'local.json',record)

    def save_notes(self,mid,text):
        with self._mutex:self.source(mid);self._write(mid,'notes.md',text)

    def _stamp(self,mid):
        return {name:signature(self.path(mid,name)) if self.path(mid,name).exists() else None for name in ('source.json','local.json','notes.md')}

    def _entry(self,mid):
        source=self._read(mid,'source.json',MeetingSource);local=self._read(mid,'local.json',MeetingLocal)
        path=self.path(mid,'notes.md')
        return dict(stamp=self._stamp(mid),id=mid,title=source.title,start_at=source.start_at.isoformat(),end_at=source.end_at.isoformat(),
            state=source.state,provider=source.provider,source_key=source.source_key,store_id=source.store_id,folder_id=source.folder_id,
            has_notes=path.exists() and path.stat().st_size>0,unconverted=sum(a.state in ('clarify','todo') for a in local.actions),
            links=local.linked_node_ids,all_day=source.all_day,all_day_start=source.all_day_start.isoformat() if source.all_day_start else None,all_day_end=source.all_day_end.isoformat() if source.all_day_end else None)

    def summaries(self):
        with self._mutex:
            if self._entries is None:
                cached={}
                if is_reparse_point(self.root):raise UnsafePathError(tr('storage.meetings.directorul_intalnirilor_este_o_legatura_nesigura'))
                try:
                    if is_reparse_point(self.cache.parent) or is_reparse_point(self.cache):raise UnsafePathError(tr('storage.meetings.cache_intalniri_nesigur'))
                    data,_,_=read_json(self.cache,allow_backup=False)
                    if data.get('version')==2 and checksum(data['entries'])==data['checksum']:cached=data['entries']
                except Exception:pass
                entries={};self.issues=[]
                if is_reparse_point(self.root):raise UnsafePathError(tr('storage.meetings.directorul_intalnirilor_este_o_legatura_nesigura'))
                for folder in sorted(self.root.iterdir()) if self.root.exists() else []:
                    if not is_uuid(folder.name):continue
                    mid=folder.name
                    try:
                        old=cached.get(mid)
                        fields={'stamp','id','title','start_at','end_at','state','provider','source_key','store_id','folder_id','has_notes','unconverted','links','all_day','all_day_start','all_day_end'}
                        if old and set(old)==fields and old['id']==mid and old['stamp']==self._stamp(mid):entries[mid]=old
                        else:entries[mid]=self._entry(mid)
                    except Exception as exc:self.issues.append((str(folder),str(exc)))
                self._entries=entries;self._save_index()
            return [dict(item,links=list(item['links'])) for item in self._entries.values()]

    def summary(self,mid):
        with self._mutex:
            if self._entries is None:self.summaries()
            row=self._entries.get(mid)
            return dict(row,links=list(row['links'])) if row else None

    def _save_index(self):
        if self.repo.read_only or self._entries is None:return
        if any(is_reparse_point(p) for p in (self.root,self.cache.parent,self.cache)):return
        try:write_cache(self.cache,dict(version=2,entries=self._entries,checksum=checksum(self._entries)))
        except Exception:pass # disposable, signatures force reconciliation after a crash
