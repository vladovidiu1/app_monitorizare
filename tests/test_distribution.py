import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package_windows',ROOT/'scripts/package_windows.py')
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)


def bundle(tmp_path):
    root=tmp_path/'FocusDesk';root.mkdir()
    (root/'FocusDesk.exe').write_bytes(b'not-an-executable-test-fixture')
    (root/'build-info.json').write_text('{"model_included":true}')
    (root/'_internal').mkdir()
    (root/'_internal'/'runtime.dll').write_bytes(b'fixture')
    (root/'models').mkdir()
    data=b'GGUF-test-fixture'
    (root/'models'/'model.gguf').write_bytes(data)
    return root,{'filename':'model.gguf','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def test_distribution_audit_rejects_user_data_and_changed_model(tmp_path):
    root,manifest=bundle(tmp_path)
    package.audit(root,manifest,True)
    (root/'workspace.json').write_text('{}')
    with pytest.raises(ValueError):package.audit(root,manifest,True)
    (root/'workspace.json').unlink()
    (root/'models'/'model.gguf').write_bytes(b'X'*manifest['size'])
    with pytest.raises(ValueError,match='SHA256'):package.audit(root,manifest,True)


def test_distribution_zip64_round_trip_and_model_free_update(tmp_path):
    root,manifest=bundle(tmp_path)
    full=tmp_path/'full.zip';update=tmp_path/'update.zip'
    package.archive(root,full,include_model=True)
    package.archive(root,update,include_model=False)
    with zipfile.ZipFile(full) as archive:
        assert archive.read('FocusDesk/models/model.gguf')==b'GGUF-test-fixture'
        assert archive.getinfo('FocusDesk/models/model.gguf').extract_version>=45
    with zipfile.ZipFile(update) as archive:
        assert not any('.gguf' in name for name in archive.namelist())
        assert 'FocusDesk/FocusDesk.exe' in archive.namelist()
        assert json.loads(archive.read('FocusDesk/build-info.json'))['model_included'] is False
    assert package.sha256(full) in full.with_suffix('.zip.sha256').read_text()


def test_distribution_audit_rejects_unexpected_model_or_nested_profile(tmp_path):
    root,manifest=bundle(tmp_path)
    (root/'_internal'/'app.json').write_text('{}')
    with pytest.raises(ValueError,match='Personal'):package.audit(root,manifest,True)
    (root/'_internal'/'app.json').unlink()
    (root/'models'/'other.gguf').write_bytes(b'other')
    with pytest.raises(ValueError):package.audit(root,manifest,True)


def test_distribution_diagnostics_always_isolate_profile(tmp_path,monkeypatch):
    import os,socket
    from focusdesk.ai import distribution_smoke as smoke
    parent=tmp_path/'personal';parent.mkdir()
    (parent/'app.json').write_text('{"private":"keep"}')
    monkeypatch.setenv('APPDATA',str(parent))
    connect=socket.socket.connect
    def fake(model,**kwargs):
        assert os.environ['APPDATA']!=str(parent)
        Path(os.environ['APPDATA']).mkdir(parents=True)
        Path(os.environ['APPDATA'],'app.json').write_text('{}')
        return {'status':'ok'}
    monkeypatch.setattr(smoke,'_run_distribution_smoke',fake)
    assert smoke.run_distribution_smoke(tmp_path/'test.gguf')['status']=='ok'
    assert os.environ['APPDATA']==str(parent)
    assert json.loads((parent/'app.json').read_text())=={'private':'keep'}
    assert socket.socket.connect is connect


def test_frozen_path_allows_only_pyinstaller_private_dll_directory(tmp_path):
    spec=importlib.util.spec_from_file_location('verify_distribution',ROOT/'scripts/verify_distribution.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.validate_runtime_paths('',tmp_path)
    verifier.validate_runtime_paths(str(tmp_path/'_internal'/'pywin32_system32'),tmp_path)
    with pytest.raises(AssertionError,match='external PATH'):
        verifier.validate_runtime_paths(str(tmp_path.parent/'external-python'),tmp_path)
