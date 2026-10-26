"""Copy installed distributions' license files; never copy user configuration."""
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
summary=[]
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():
    (output/'PYTHON-LICENSE.txt').write_bytes(python_license.read_bytes())
for dist in metadata.distributions():
    name=dist.metadata['Name'] or 'unknown'
    if name.lower() in ('focusdesk','pip'):
        continue
    summary.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                    'homepage':dist.metadata.get('Home-page')})
    for entry in dist.files or []:
        if not any(marker in entry.name.lower() for marker in ('license','licence','copying','notice')):
            continue
        source=Path(dist.locate_file(entry))
        if source.is_file():
            target=output/name/entry.name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source.read_bytes())
(output/'THIRD-PARTY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
