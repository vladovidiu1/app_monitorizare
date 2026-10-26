"""Audit an allowlisted onedir, build ZIP64 archives, and write SHA256 checksums."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ALLOWED_ROOT={'FocusDesk.exe','_internal','models','licenses','build-info.json','CITESTE-MA.txt'}


def audit(bundle, manifest, include_model):
    actual={p.name for p in bundle.iterdir()}
    if not actual<=ALLOWED_ROOT or 'FocusDesk.exe' not in actual:
        raise ValueError(f'Unexpected distribution entries: {actual-ALLOWED_ROOT}')
    forbidden={'workspace.json','app.json','state.json','.env','credentials.json'}
    for path in bundle.rglob('*'):
        if path.is_file() and path.name.lower() in forbidden:
            raise ValueError('Personal/workspace data found in distribution: '+str(path))
    models=list((bundle/'models').glob('*'))
    if include_model:
        target=bundle/'models'/manifest['filename']
        if set(models)!={target} or target.stat().st_size!=manifest['size']:
            raise ValueError('Unexpected or missing model')
        if sha256(target)!=manifest['sha256']:
            raise ValueError('GGUF SHA256 mismatch before packaging')
    elif models:
        raise ValueError('No-model archive must contain no GGUF')


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(8*1024*1024):digest.update(block)
    return digest.hexdigest()


def archive(bundle, destination, *, include_model):
    # ZIP64 and forced ZIP64 file headers: GGUF exceeds the classic 4 GiB boundary.
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as output:
        for path in sorted(bundle.rglob('*')):
            if not path.is_file() or (not include_model and path.is_relative_to(bundle/'models')):
                continue
            info=zipfile.ZipInfo.from_file(path,arcname='FocusDesk/'+path.relative_to(bundle).as_posix())
            if path.name=='build-info.json' and path.parent==bundle:
                data=json.loads(path.read_text(encoding='utf-8-sig'))
                data['model_included']=include_model
                with output.open(info,'w',force_zip64=True) as target:
                    target.write(json.dumps(data,indent=2).encode('utf-8'))
            else:
                with path.open('rb') as source, output.open(info,'w',force_zip64=True) as target:
                    shutil.copyfileobj(source,target,8*1024*1024)
    with zipfile.ZipFile(destination) as check:
        bad=check.testzip()
        if bad:raise ValueError('Archive CRC mismatch: '+bad)
    checksum=destination.with_suffix('.zip.sha256')
    checksum.write_text(sha256(destination)+'  '+destination.name+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,default=Path('src/focusdesk/resources/ai-model.json'))
    parser.add_argument('--with-update',action='store_true')
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    audit(args.bundle,manifest,True)
    args.output.mkdir(parents=True,exist_ok=True)
    expected=manifest['size']+sum(p.stat().st_size for p in args.bundle.rglob('*') if p.is_file() and not p.is_relative_to(args.bundle/'models'))
    if shutil.disk_usage(args.output).free<expected+512*1024*1024:
        raise RuntimeError('Insufficient disk for ZIP64 archive')
    archive(args.bundle,args.output/'FocusDesk-Windows-x64-cu-model.zip',include_model=True)
    if args.with_update:
        archive(args.bundle,args.output/'FocusDesk-Windows-x64-fara-model.zip',include_model=False)
    return 0


if __name__=='__main__':raise SystemExit(main())
