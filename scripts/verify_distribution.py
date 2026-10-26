"""Run the FROZEN application with empty PATH and isolated personal data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def validate_runtime_paths(value, bundle):
    # The launcher supplies PATH="". PyInstaller's pywin32 hook legitimately adds
    # its OWN DLL folder before our entry point. Permit only bundled directories.
    for entry in value.split(os.pathsep):
        if entry and not Path(entry).resolve().is_relative_to(bundle.resolve()):
            raise AssertionError('Frozen runtime introduced an external PATH directory: '+entry)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--reports',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=600)
    args=parser.parse_args()
    args.reports.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='focusdesk-packaged-test-') as folder:
        base=Path(folder)
        env={**os.environ,'PATH':'','APPDATA':str(base/'appdata'),'LOCALAPPDATA':str(base/'localappdata')}
        for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):
            env.pop(key,None)
        for case in ('real','missing'):
            output=args.reports/(case+'.json')
            command=[str(args.exe.resolve()),'--distribution-smoke',case,'--ai-smoke-report',str(output.resolve()),'--ai-timeout',str(args.timeout)]
            if case=='missing':
                command += ['--ai-smoke',str(base/'absent.gguf')]
            result=subprocess.run(command,cwd=base,env=env,timeout=args.timeout+45)
            report=json.loads(output.read_text(encoding='utf-8'))
            # Also expose small, non-personal reports as check annotations, so
            # verification remains inspectable when artifact/log downloads are restricted.
            data=json.dumps(report,ensure_ascii=True).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            level='notice' if result.returncode==0 and report.get('status')=='ok' else 'error'
            print(f'::{level} title=Frozen {case} smoke::{data}',flush=True)
            if result.returncode!=0 or report.get('status')!='ok':
                raise RuntimeError(f'Packaged {case} smoke failed: {report}')
            validate_runtime_paths(report['python_path'],args.exe.resolve().parent)
            assert report['ai_child_stopped']
            report.update(launcher_path_empty=True,runtime_path_internal_only=True)
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'case':case,'status':'ok','report':str(output)}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
