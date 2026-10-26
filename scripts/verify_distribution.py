"""Run the FROZEN application with empty PATH and isolated personal data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


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
            if result.returncode!=0 or report.get('status')!='ok':
                raise RuntimeError(f'Packaged {case} smoke failed: {report}')
            assert report['python_path']=='' and report['ai_child_stopped']
            print(json.dumps({'case':case,'status':'ok','report':str(output)}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
