"""Packaged offline manual. This module never opens a workspace or personal documents."""
from __future__ import annotations

from ..i18n import tr, language

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

from ..config import resource_path
from ..errors import FocusDeskError


class GuideError(FocusDeskError):
    pass


def normalize(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize(text)).strip('-') or 'sectiune'


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    anchor: str = ''
    level: int = 0


def blocks(markdown: str) -> tuple[Block, ...]:
    result, paragraph, code, anchors = [], [], None, {}
    def flush():
        if paragraph:
            result.append(Block('paragraph', ' '.join(paragraph)))
            paragraph.clear()
    for line in markdown.splitlines():
        if line.startswith('```'):
            flush()
            if code is None: code = []
            else:
                result.append(Block('code', '\n'.join(code)))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        heading = re.match(r'^(#{1,3})\s+(.+?)\s*$', line)
        if heading:
            flush()
            explicit = re.match(r'^(.*?)\s+\{#([a-z0-9-]+)\}$', heading[2])
            title = explicit[1] if explicit else heading[2]
            key = explicit[2] if explicit else slug(title)
            anchors[key] = anchors.get(key, 0) + 1
            anchor = key + (f'-{anchors[key]}' if anchors[key] > 1 else '')
            result.append(Block('heading', title, anchor, len(heading[1])))
        elif not line.strip(): flush()
        elif re.match(r'^\d+[.)]\s', line):
            flush(); result.append(Block('list', line))
        elif line.startswith('- '):
            flush(); result.append(Block('list', '• ' + line[2:]))
        elif line.startswith('> '):
            flush(); result.append(Block('note', line[2:]))
        else: paragraph.append(line)
    flush()
    if code is not None: result.append(Block('code', '\n'.join(code)))
    return tuple(result)


LINK = re.compile(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)')


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    content: str
    blocks: tuple[Block, ...]

    @property
    def anchors(self):
        return {block.anchor for block in self.blocks if block.anchor}


@dataclass(frozen=True)
class SearchHit:
    chapter_id: str
    title: str
    fragment: str
    anchor: str


class GuideLibrary:
    def __init__(self, directory: Path | None = None):
        directory = directory if directory is not None else (resource_path('guide') / language() if language() != 'ro' else resource_path('guide'))
        try:
            manifest = json.loads((directory / 'index.json').read_text('utf-8-sig'))
            if not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(manifest.get('chapters'), list):
                raise ValueError(tr('services.user_guide.schema_ghidului_nu_este_acceptata'))
            self.chapters = {}
            for entry in manifest['chapters']:
                chapter_id, filename = entry['id'], entry['file']
                if not re.fullmatch(r'[a-z0-9-]+', chapter_id) or not re.fullmatch(r'[a-z0-9-]+\.md', filename):
                    raise ValueError(tr('services.user_guide.identificator_sau_cale_invalida_in_ghid'))
                if chapter_id in self.chapters:
                    raise ValueError(tr('extra.services.user_guide.identificator_de_capitol_duplicat'))
                content = (directory / filename).read_text('utf-8-sig')
                parsed = blocks(content)
                if not parsed or parsed[0].kind != 'heading' or parsed[0].level != 1:
                    raise ValueError(tr('services.user_guide.capitol_fara_titlu'))
                self.chapters[chapter_id] = Chapter(chapter_id, parsed[0].text, content, parsed)
            if not self.chapters or 'introducere' not in self.chapters:
                raise ValueError(tr('services.user_guide.lipseste_introducerea_ghidului'))
            self.validate_links()
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise GuideError(tr('services.user_guide.ghidul_local_nu_poate_fi_incarcat_reinstaleaza_distributia_completa_fo', exc=exc)) from exc
        # Only the bundled documentation is indexed, once per library instance.
        self._index = {key: normalize(chapter.title + '\n' + chapter.content) for key, chapter in self.chapters.items()}

    def target(self, url: str, current: str = 'introducere') -> tuple[str, str]:
        if url.startswith('#'):
            chapter_id, anchor = current, url[1:]
        else:
            value = url.removeprefix('guide:')
            chapter_id, _, anchor = value.partition('#')
        if chapter_id not in self.chapters or (anchor and anchor not in self.chapters[chapter_id].anchors):
            raise GuideError(tr('services.user_guide.legatura_interna_indisponibila', url=url))
        return chapter_id, anchor

    def validate_links(self):
        for chapter in self.chapters.values():
            for _label, url in LINK.findall(chapter.content):
                if not url.startswith(('guide:', '#')):
                    raise ValueError(tr('services.user_guide.ghidul_accepta_doar_legaturi_interne', url=url))
                self.target(url, chapter.id)

    def search(self, query: str) -> list[SearchHit]:
        tokens = normalize(query).split()
        if not tokens: return []
        results = []
        for key, chapter in self.chapters.items():
            text = self._index[key]
            if not all(token in text for token in tokens): continue
            score = sum(5 if token in normalize(chapter.title) else 1 for token in tokens)
            anchor, fragment, best = '', '', (-1, -1)
            current_anchor = ''
            for block in chapter.blocks:
                if block.anchor: current_anchor = block.anchor
                matched = sum(token in normalize(block.text) for token in tokens)
                rank = (matched, int(block.kind != 'heading'))
                if rank > best:
                    best, anchor, fragment = rank, current_anchor, block.text
            fragment = LINK.sub(r'\1', fragment).replace('**', '').replace('`', '')
            results.append((score, SearchHit(key, chapter.title, fragment[:210] + ('…' if len(fragment)>210 else ''), anchor)))
        return [hit for _, hit in sorted(results, key=lambda item: -item[0])]


@dataclass
class ReadingLocation:
    chapter_id: str
    anchor: str = ''
    scroll: float | None = None


class GuideHistory:
    def __init__(self):
        self.entries = [ReadingLocation('introducere')]
        self.index = 0

    @property
    def current(self): return self.entries[self.index]

    def visit(self, chapter_id: str, anchor: str = '') -> bool:
        current = self.current
        if chapter_id == current.chapter_id and (not anchor or anchor == current.anchor):
            return False
        del self.entries[self.index+1:]
        self.entries.append(ReadingLocation(chapter_id, anchor))
        self.entries = self.entries[-100:]
        self.index = len(self.entries)-1
        return True

    def move(self, delta: int) -> bool:
        target = self.index + delta
        if not 0 <= target < len(self.entries): return False
        self.index = target
        return True
