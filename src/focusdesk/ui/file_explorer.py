"""Lazy disk tree. Workers return metadata; all Tk access stays on the UI thread."""
from __future__ import annotations

from ..i18n import datetime_text

from ..i18n import tr

from collections import OrderedDict
from datetime import datetime
import hashlib
import tkinter as tk
from tkinter import ttk

from ..services.files import DirectoryEntry, FileService, format_size, normalized_file_key
from .common import error_color, make_tree
from .design import px


class FileExplorer(ttk.Frame):
    PAGE = 200
    POLL_MS = 2500
    POLL_DIRECTORIES = 4
    MAX_SCANS = 2

    def __init__(self, parent, app, *, on_open=lambda: None, on_select=lambda: None):
        super().__init__(parent)
        self.app = app
        self.on_open, self.on_select = on_open, on_select
        self.ws = None
        self.node_id = None
        self.sources = ()
        self.references = ()
        self.rows = {}
        self.contents = {}
        self.limits = {}
        self.requests = {}
        self._queue = OrderedDict()
        self._cache = OrderedDict()
        self._restore = None
        self._generation = 0
        self._active = False
        self._poll_job = self._refresh_job = None
        self._poll_offset = 0
        self.tv, frame = make_tree(self, [("type", tr('ui.dialogs.tip'), px(self,65)), ("size", tr('ui.file_picker.dimensiune'), px(self,80)),
                                          ("modified", tr('ui.tab_versions.modificat'), px(self,135)), ("state", tr('ui.meetings.stare'), px(self,110))],
                                   show_tree=True, height=9, selectmode="extended")
        self.tv.heading("#0", text=tr('ui.file_picker.nume'), anchor="w")
        self.tv.column("#0", width=px(self,200), minwidth=px(self,120), stretch=True)
        self.tv.column("type", stretch=False)
        frame.pack(fill="both", expand=True)
        self.tv.tag_configure("bad", foreground=error_color(self))
        self.status = ttk.Label(self, style="Muted.TLabel", text=tr('ui.file_explorer.extinde_un_folder_pentru_a_l_explora'), wraplength=500)
        self.status.pack(fill="x", pady=(4, 0))
        self.tv.bind("<<TreeviewOpen>>", self._opened)
        self.tv.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tv.bind("<Double-1>", self._double_click)
        self.tv.bind("<Return>", lambda _e: self.activate_selected())
        self.tv.bind("<F5>", lambda _e: self.refresh() or "break")
        self.bind("<Map>", lambda _e: self.after_idle(self._mapped))
        self.bind("<Unmap>", lambda _e: self.stop())
        self.bind("<Configure>", lambda e: self.status.configure(wraplength=max(160, e.width - 8)))
        self.bind("<Destroy>", self._destroyed)
        self._focus_binding = app.root.bind("<FocusIn>", self._focus_in, add="+")

    @staticmethod
    def _id(root_id, path):
        return root_id + ":" + hashlib.sha256(normalized_file_key(path).encode()).hexdigest()[:24]

    def _visible(self):
        return (self.winfo_exists() and self.winfo_viewable() and self.app.ws is self.ws
                and self.node_id in self.ws.nodes and self.app.selected_id == self.node_id)

    def _remember(self):
        if self.ws and self.node_id:
            key = (self.ws, self.node_id)
            self._cache[key] = dict(expanded={iid for iid in self.rows if self.tv.exists(iid) and self.tv.item(iid, "open")},
                                    selected=self.tv.selection(), y=self.tv.yview()[0], x=self.tv.xview()[0],
                                    limits=dict(self.limits))
            self._cache.move_to_end(key)
            while len(self._cache) > 10:
                self._cache.popitem(last=False)

    def load(self, ws, node_id, sources, references=()):
        same = self.ws is ws and self.node_id == node_id
        self.references = tuple(references)
        if same and self.sources == tuple(sources):
            if self._active:
                self.schedule_refresh()
            else:
                self._mapped()
            return
        self._remember()
        self.stop()
        if self.ws is not ws:
            self._cache.clear()
        self.ws, self.node_id, self.sources = ws, node_id, tuple(sources)
        self._restore = self._cache.get((ws, node_id))
        self.tv.delete(*self.tv.get_children())
        self.rows.clear()
        self.contents.clear()
        self.limits = dict(self._restore["limits"]) if self._restore else {}
        expanded = self._restore["expanded"] if self._restore else set()
        links = None
        for source in sources:
            if source.key.startswith("link-"):
                if links is None:
                    links = "links"
                    self.tv.insert("", "end", iid=links, text=tr('ui.file_explorer.legaturi_externe_alte_referinte'), open=True)
                parent = links
            else:
                parent = ""
            iid = self._id(source.key, source.path) if source.path else source.key + ":error"
            entry = DirectoryEntry(source.path, source.is_dir, None) if source.path else None
            self.rows[iid] = dict(root=source.path, entry=entry, source=source)
            opened = iid in expanded if self._restore else source.is_dir
            self.tv.insert(parent, "end", iid=iid, text=source.label, open=opened,
                           values=(tr('ui.file_picker.folder') if source.is_dir else tr('ui.tab_versions.fisier'), "—", "—", source.error or tr('ui.file_explorer.neincarcat')),
                           tags=("bad",) if source.error else ())
            if source.path and source.is_dir:
                self._hint(iid)
        self._mapped()

    def _hint(self, iid):
        key = iid + ":hint"
        if not self.tv.get_children(iid):
            self.tv.insert(iid, "end", iid=key, text=tr('ui.file_explorer.extinde_pentru_incarcare'))

    def _mapped(self):
        if not self.ws or not self._visible():
            return
        if not self._active:
            self._active = True
            self.refresh()
        if self._poll_job is None:
            self._poll_job = self.after(self.POLL_MS, self._poll)

    def _focus_in(self, _event):
        if self.ws and self._visible():
            if not self._active:
                self._mapped()
            else:
                self.schedule_refresh()

    def schedule_refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(300, self.refresh)

    def stop(self):
        self._active = False
        self._generation += 1
        for name in ("_poll_job", "_refresh_job"):
            job = getattr(self, name)
            if job:
                self.after_cancel(job)
                setattr(self, name, None)
        for job in self.requests.values():
            job.cancel()
        self.requests.clear()
        self._queue.clear()

    def detach_workspace(self):
        """Release cached paths and the old workspace even if this tab is never opened again."""
        self.stop()
        self.ws = self.node_id = None
        self.sources = self.references = ()
        self._restore = None
        self._cache.clear()
        self.rows.clear()
        self.contents.clear()
        self.limits.clear()
        self.tv.delete(*self.tv.get_children())

    def _destroyed(self, event):
        if event.widget is self:
            self.stop()
            self.app.root.unbind("<FocusIn>", self._focus_binding)

    def _expanded(self, iid):
        if not self.tv.exists(iid):
            return False
        parent = self.tv.parent(iid)
        while parent:
            if not self.tv.item(parent, "open"):
                return False
            parent = self.tv.parent(parent)
        entry = self.rows[iid]["entry"]
        return not entry.is_dir or bool(self.tv.item(iid, "open"))

    def _watched(self):
        return [iid for iid, row in self.rows.items() if row["entry"] is not None and not row["entry"].is_link
                and self._expanded(iid) and (row.get("source") or row["entry"].is_dir)]

    def refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        if not self._active or not self._visible():
            return
        # Root probes also recover missing files/folders without recreating associations.
        for iid in self._watched():
            self._request(iid)

    def _poll(self):
        self._poll_job = None
        if not self._visible():
            self.stop()
            return
        watched = self._watched()
        if watched:
            for index in range(min(len(watched), self.POLL_DIRECTORIES)):
                self._request(watched[(self._poll_offset + index) % len(watched)])
            self._poll_offset = (self._poll_offset + self.POLL_DIRECTORIES) % len(watched)
        self._poll_job = self.after(self.POLL_MS, self._poll)

    def _opened(self, _event=None):
        iid = self.tv.focus()
        generation = self._generation
        self.after_idle(lambda: self.open_directory(iid) if generation == self._generation else None)

    def open_directory(self, iid):
        if iid not in self.rows or self.rows[iid]["entry"] is None:
            return
        entry = self.rows[iid]["entry"]
        if not entry.is_dir or entry.is_link or entry.state != "ready":
            return
        self.tv.item(iid, open=True)
        self._request(iid)

    def _request(self, iid):
        if iid in self.requests or iid in self._queue or not self._active or not self._visible():
            return
        row = self.rows.get(iid)
        if row is None or row["entry"] is None or row["entry"].is_link:
            return
        self._queue[iid] = None
        self._drain()

    def _drain(self):
        while self._queue and len(self.requests) < self.MAX_SCANS and self._active:
            iid, _ = self._queue.popitem(last=False)
            if iid not in self.rows or not self._expanded(iid):
                continue
            row = self.rows[iid]
            root, path = row["root"], row["entry"].path
            generation = self._generation
            self.status.configure(text=tr('ui.file_explorer.se_citesc_directoarele_deschise'))

            def work(token, root=root, path=path):
                token.check()
                entry = FileService.describe_entry(root, path)
                children = FileService.browse_directory(path, root=root, include_links=True, cancel=token) if entry.is_dir else None
                return entry, children

            def accept(result, iid=iid, generation=generation):
                if not self._valid(generation, iid):
                    return
                self.requests.pop(iid, None)
                if self._expanded(iid):
                    entry, children = result
                    self.rows[iid]["entry"] = entry
                    self.rows[iid].pop("error", None)
                    self._update_row(iid)
                    if children is not None:
                        # Legacy references remain manageable if a file disappeared from a listed directory.
                        present = {normalized_file_key(child.path) for child in children}
                        children = [*children, *(DirectoryEntry(path, is_dir, None, state="missing",
                                                               detail=tr('ui.file_explorer.referinta_existenta_fisierul_lipseste_de_pe_disc'))
                                                for path, is_dir in self.references
                                                if normalized_file_key(path.parent) == normalized_file_key(entry.path)
                                                and normalized_file_key(path) not in present)]
                        children.sort(key=lambda item: (not item.is_dir, item.path.name.casefold()))
                        self._render(iid, children)
                    else:
                        for child in self.tv.get_children(iid):
                            self._remove_row(child)
                        self.contents.pop(iid, None)
                    self._restore_position()
                self._drain()
                if not self.requests and not self._queue:
                    self.status.configure(text=tr('ui.file_explorer.unele_directoare_sunt_indisponibile_selecteaza_randul_pentru_detalii') if
                                          any(row.get("error") for row in self.rows.values()) else
                                          tr('ui.file_explorer.actualizat_de_pe_disc_f5_pentru_directoarele_deschise'))

            def failed(error, iid=iid, generation=generation):
                if not self._valid(generation, iid):
                    return
                self.requests.pop(iid, None)
                self.rows[iid]["error"] = str(error)
                self.tv.set(iid, "state", str(error))
                self.tv.item(iid, tags=("bad",))
                # Keep old visible children on transient errors; never present them as fresh.
                self.status.configure(text=tr('ui.file_explorer.folder_indisponibil_celelalte_surse_raman_accesibile', error=error))
                self._drain()

            self.requests[iid] = self.app.bridge.submit(work, accept, failed, name="files-list")

    def _valid(self, generation, iid):
        return generation == self._generation and self._active and self._visible() and iid in self.rows and self.tv.exists(iid)

    def _update_row(self, iid):
        row = self.rows[iid]
        entry = row["entry"]
        try:
            modified = datetime_text(datetime.fromtimestamp(entry.modified_ns / 1e9)) if entry.modified_ns is not None else "—"
        except (ValueError, OverflowError, OSError):
            modified = tr('ui.file_explorer.data_indisponibila')
        values = (tr('ui.meetings.legatura') if entry.is_link else tr('ui.file_picker.folder') if entry.is_dir else entry.path.suffix or tr('ui.tab_versions.fisier'),
                  format_size(entry.size_bytes) if entry.size_bytes is not None else "—",
                  modified,
                  entry.detail or tr('ui.file_explorer.pe_disc'))
        options = dict(values=values, tags=("bad",) if entry.state != "ready" else ())
        if tuple(self.tv.item(iid, "values")) != values or self.tv.item(iid, "tags"):
            self.tv.item(iid, **options)

    def _remove_row(self, iid):
        for child in self.tv.get_children(iid):
            self._remove_row(child)
        self.rows.pop(iid, None)
        self.contents.pop(iid, None)
        self._queue.pop(iid, None)
        job = self.requests.pop(iid, None)
        if job:
            job.cancel()
        self.tv.delete(iid)

    def _render(self, parent, entries):
        if self.contents.get(parent) == entries:
            return
        self.contents[parent] = entries
        self._render_page(parent)

    def _render_page(self, parent):
        entries = self.contents[parent]
        limit = self.limits.get(parent, self.PAGE)
        self.limits[parent] = limit
        wanted = entries[:limit]
        ids = [self._id(parent, entry.path) for entry in wanted]
        more = parent + ":more"
        desired = set(ids + ([more] if len(entries) > limit else []))
        selected, x, y = self.tv.selection(), self.tv.xview()[0], self.tv.yview()[0]
        for iid in self.tv.get_children(parent):
            if iid not in desired:
                self._remove_row(iid)
        expanded = self._restore["expanded"] if self._restore else set()
        for index, (iid, entry) in enumerate(zip(ids, wanted)):
            previous = self.rows.get(iid)
            self.rows[iid] = dict(root=self.rows[parent]["root"], entry=entry, source=None)
            if not self.tv.exists(iid):
                self.tv.insert(parent, index, iid=iid, text=entry.path.name, open=iid in expanded)
            elif self.tv.index(iid) != index:
                self.tv.move(iid, parent, index)
            self._update_row(iid)
            expandable = entry.is_dir and not entry.is_link and entry.state == "ready"
            if not expandable:
                for child in self.tv.get_children(iid):
                    self._remove_row(child)
                self.contents.pop(iid, None)
            elif iid not in self.contents:
                self._hint(iid)
            if expandable and self.tv.item(iid, "open") and (previous is None or iid not in self.contents):
                self._request(iid)
        if len(entries) > limit:
            text = tr('ui.file_explorer.incarca_urmatoarele_din', self_page=self.PAGE, min_limit_len_entries=min(limit,len(entries)), len_entries=len(entries))
            if self.tv.exists(more):
                self.tv.item(more, text=text)
            else:
                self.tv.insert(parent, "end", iid=more, text=text)
            self.tv.move(more, parent, "end")
        self.tv.selection_set([iid for iid in selected if self.tv.exists(iid)])
        self.tv.xview_moveto(x)
        self.tv.yview_moveto(y)

    def _restore_position(self):
        if not self._restore:
            return
        selected = [iid for iid in self._restore["selected"] if self.tv.exists(iid)]
        if selected:
            self.tv.selection_set(selected)
        self.tv.yview_moveto(self._restore["y"])
        self.tv.xview_moveto(self._restore["x"])
        if not self.requests and not self._queue:
            self._restore = None

    def selected(self):
        return [(iid, self.rows[iid]) for iid in self.tv.selection() if iid in self.rows and self.rows[iid]["entry"] is not None]

    def _double_click(self, event):
        iid = self.tv.identify_row(event.y)
        if iid:
            self.tv.selection_set(iid)
            self.tv.focus(iid)
            self.activate_selected()
        return "break"  # Own the toggle, avoiding a second default Treeview toggle.

    def activate_selected(self):
        iid = self.tv.focus()
        if iid.endswith(":more") and self.tv.exists(iid):
            parent = self.tv.parent(iid)
            self.limits[parent] = self.limits.get(parent, self.PAGE) + self.PAGE
            self._render_page(parent)
        elif iid in self.rows and self.rows[iid]["entry"] is not None:
            entry = self.rows[iid]["entry"]
            if entry.is_dir and not entry.is_link:
                opened = bool(self.tv.item(iid, "open"))
                self.tv.item(iid, open=not opened)
                if not opened:
                    self._request(iid)
            else:
                self.on_open()
        return "break"
