"""Run the packaged application with empty PATH and disposable personal data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def validate_runtime_paths(value, bundle):
    # PyInstaller's pywin32 hook may add its own private DLL directory.
    for entry in value.split(os.pathsep):
        if entry and not Path(entry).resolve().is_relative_to(bundle.resolve()):
            raise AssertionError('Frozen runtime introduced an external PATH directory: ' + entry)


def validate_mail_runtime(report):
    assert report.get('gmail_modules_loaded') and report.get('gmail_fake_smtp'), 'Missing Gmail runtime verification'
    assert report.get('gmail_network_used') is False, 'SMTP smoke must not use the network'
    assert report.get('credential_api_loaded'), 'Windows Credential Manager API unavailable in executable'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args()
    args.reports.mkdir(parents=True, exist_ok=True)
    output = (args.reports / 'application.json').resolve()
    output.unlink(missing_ok=True)  # stale successes must never validate this run
    with tempfile.TemporaryDirectory(prefix='focusdesk-packaged-test-') as folder:
        base = Path(folder)
        env = {**os.environ, 'PATH': '', 'APPDATA': str(base / 'profile'), 'LOCALAPPDATA': str(base / 'local')}
        for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
            env.pop(key, None)
        result = subprocess.run([str(args.exe.resolve()), '--smoke-test', '--smoke-report', str(output)],
                                cwd=base, env=env, timeout=args.timeout)
        report = json.loads(output.read_text(encoding='utf-8'))
        if result.returncode != 0 or report.get('status') != 'ok' or not report.get('frozen'):
            raise RuntimeError(f'Packaged application smoke failed: {report}')
        validate_runtime_paths(report['python_path'], args.exe.resolve().parent)
        validate_mail_runtime(report)
        report.update(launcher_path_empty=True, runtime_path_internal_only=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
