"""Capture the real Tk file explorer on disposable data; no external programs or mail are launched."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    from PIL import ImageGrab
    from focusdesk.domain.models import Kind
    from focusdesk.ui.app import FocusDeskApp
    from focusdesk.ui.common import apply_theme
    from focusdesk.ui.design import MIN_WINDOW, px

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/files'))
    parser.add_argument('--scale', type=float, default=1.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(platform=sys.platform, simulated_scale=args.scale, windows_dpi_verified=False,
                  external_apps_opened=False, captures=[], checks=[])
    with tempfile.TemporaryDirectory(prefix='focusdesk-files-demo-') as temp:
        base = Path(temp)
        os.environ['APPDATA'] = str(base / 'config')
        app = FocusDeskApp()
        app.root.tk.call('tk', 'scaling', args.scale * 96 / 72)
        apply_theme(app.root)
        app.root.minsize(*(px(app.root, value) for value in MIN_WINDOW))
        app.root.geometry(f'{px(app.root,1100)}x{px(app.root,700)}+0+0')
        assert app.open_workspace(base / 'workspace', create=True)
        errors = []
        app.root.report_callback_exception = lambda cls, error, tb: errors.append(f'{cls.__name__}: {error}')
        project = app.ws.create_node(Kind.PROJECT, 'Raportări · folder asociat')
        task = app.ws.create_node(Kind.TASK, 'Verifică documentele primite', project.id,
                                  description='Scop\nVerifică datele și discută rezultatul.\n\nPasul 1\n    Deschide documentele din folderul proiectului.')
        root = base / 'Folder proiect'
        root.mkdir()
        docs = root / 'Documente'; docs.mkdir()
        sources = root / 'Surse'; sources.mkdir()
        (docs / 'Raport.csv').write_text('Nume;Valoare\nExemplu;42\n', encoding='utf-8')
        (sources / 'prelucrare.py').write_text('# Exemplu afișat, niciodată executat.\n', encoding='utf-8')
        (root / '.configurare').write_text('Fișier afișat, fără filtrare ascunsă.', encoding='utf-8')
        (app.files.files_dir(task.id) / 'Notiță locală.txt').write_text('Document pus manual în files/.', encoding='utf-8')
        ext = base / 'Referință externă.txt'; ext.write_text('Document extern.', encoding='utf-8')
        app.files.set_code_folder(project.id, root)
        app.files.add_external(task.id, ext)
        app.refresh_all(); app.select_node(task.id, reveal=True)
        app.inspector.show_tab('Fișiere')

        def pump(condition=lambda: True):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                app.root.update()
                if condition():
                    for _ in range(4): app.root.update(); time.sleep(.02)
                    return
                time.sleep(.01)
            raise AssertionError('Explorer did not settle')

        def ready(tab):
            return tab.explorer._active and not tab.explorer.requests and not tab.explorer._queue and tab.explorer._refresh_job is None

        def row(tab, path):
            return next(iid for iid, value in tab.explorer.rows.items() if value['entry'] and value['entry'].path == path)

        def open_docs(tab):
            pump(lambda: ready(tab))
            tab.explorer.open_directory(row(tab, docs))
            pump(lambda: ready(tab))
            iid = row(tab, docs / 'Raport.csv')
            tab.tv.selection_set(iid); tab.tv.focus(iid)
            return iid

        def check(name, widget, *, min_height=1):
            app.root.update_idletasks()
            x, y = widget.winfo_rootx() - app.root.winfo_rootx(), widget.winfo_rooty() - app.root.winfo_rooty()
            ok = (widget.winfo_viewable() and x >= 0 and y >= 0 and widget.winfo_height() >= min_height
                  and x+widget.winfo_width() <= app.root.winfo_width() and y+widget.winfo_height() <= app.root.winfo_height())
            report['checks'].append(dict(name=name, ok=bool(ok), height=widget.winfo_height()))
            assert ok, name

        def capture(name):
            pump()
            ImageGrab.grab(bbox=(app.root.winfo_rootx(), app.root.winfo_rooty(),
                                app.root.winfo_rootx()+app.root.winfo_width(), app.root.winfo_rooty()+app.root.winfo_height())).save(args.output / (name+'.png'))
            report['captures'].append(name+'.png')

        try:
            tab = app.inspector.tab_by_title('Fișiere')
            selected = open_docs(tab)
            check('inspector-refresh', tab.refresh_btn)
            check('inspector-tree', tab.tv, min_height=px(tab,90))
            assert 'Moștenit de la' in tab.code_note.cget('text')
            capture('fisiere-inspector')
            fresh = docs / 'Adăugat manual.csv'; fresh.write_text('Coloană\nValoare\n', encoding='utf-8')
            tab.refresh(); pump(lambda: ready(tab))
            assert row(tab, fresh) and tab.tv.selection() == (selected,)
            assert len(app.ws.get(task.id).attachments) == 1
            assert app.open_task_space(task.id)
            space = app.task_space
            space.nb.select(space.scrolls['Fișiere']); pump(); space.widen_files()
            pump()
            tab = space.sections['Fișiere']; open_docs(tab)
            check('spatiu-refresh', tab.refresh_btn)
            check('spatiu-tree', tab.tv, min_height=px(tab,100))
            capture('fisiere-spatiu-lucru')
            assert not errors, errors
        finally:
            app.inspector.revert()
            deadline = time.monotonic()+5
            while app._pending_workspace_jobs() and time.monotonic()<deadline: app.root.update(); time.sleep(.01)
            app.on_close()
    (args.output/'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
