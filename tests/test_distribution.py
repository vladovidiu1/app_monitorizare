import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


package = module('package_windows')


def bundle(tmp_path):
    root = tmp_path / 'FocusDesk'
    root.mkdir()
    (root / 'FocusDesk.exe').write_bytes(b'not-an-executable-test-fixture')
    (root / 'build-info.json').write_text('{"platform":"Windows-x64"}')
    (root / '_internal').mkdir()
    (root / '_internal' / 'runtime.dll').write_bytes(b'fixture')
    return root


def test_distribution_audit_rejects_user_data(tmp_path):
    root = bundle(tmp_path)
    package.audit(root)
    (root / '_internal' / 'app.json').write_text('{}')
    with pytest.raises(ValueError, match='Personal'):
        package.audit(root)


def test_distribution_round_trip_and_checksum(tmp_path):
    root = bundle(tmp_path)
    target = tmp_path / 'FocusDesk-Windows-x64.zip'
    package.archive(root, target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read('FocusDesk/_internal/runtime.dll') == b'fixture'
        assert json.loads(archive.read('FocusDesk/build-info.json'))['platform'] == 'Windows-x64'
        assert not any('.gguf' in name or '/models/' in name for name in archive.namelist())
    assert package.sha256(target) in target.with_suffix('.zip.sha256').read_text()


def test_distribution_rejects_leftover_model_and_unexpected_directories(tmp_path):
    root = bundle(tmp_path)
    path = root / '_internal' / 'old.gguf'
    path.write_bytes(b'obsolete')
    with pytest.raises(ValueError, match='Unexpected'):
        package.audit(root)
    path.unlink()
    (root / 'models').mkdir()
    with pytest.raises(ValueError, match='Unexpected'):
        package.audit(root)


def test_frozen_path_allows_only_private_dll_directory(tmp_path):
    verifier = module('verify_distribution')
    verifier.validate_runtime_paths('', tmp_path)
    verifier.validate_runtime_paths(str(tmp_path / '_internal' / 'pywin32_system32'), tmp_path)
    with pytest.raises(AssertionError, match='external PATH'):
        verifier.validate_runtime_paths(str(tmp_path.parent / 'external-python'), tmp_path)


def test_packaged_verifier_requires_gmail_and_native_credential_api():
    verifier=module('verify_distribution')
    report={'gmail_modules_loaded':True,'gmail_fake_smtp':True,'gmail_network_used':False,'credential_api_loaded':True}
    verifier.validate_mail_runtime(report)
    for name,value in [('gmail_modules_loaded',False),('gmail_fake_smtp',False),('gmail_network_used',True),('credential_api_loaded',False)]:
        with pytest.raises(AssertionError):verifier.validate_mail_runtime({**report,name:value})


def test_smoke_always_isolates_profile_even_on_failure(tmp_path, monkeypatch):
    import os
    from focusdesk import smoke
    parent = tmp_path / 'personal'
    parent.mkdir()
    (parent / 'app.json').write_text('{"private":"keep"}')
    monkeypatch.setenv('APPDATA', str(parent))
    def fake(base):
        assert os.environ['APPDATA'] != str(parent)
        assert base.is_dir()
        raise RuntimeError('Controlled failure')
    monkeypatch.setattr(smoke, '_run', fake)
    assert smoke.run_smoke()['status'] == 'error'
    assert os.environ['APPDATA'] == str(parent)
    assert json.loads((parent / 'app.json').read_text()) == {'private': 'keep'}
