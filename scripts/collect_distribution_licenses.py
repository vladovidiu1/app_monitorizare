"""Copy installed distributions' license files; never copy user configuration."""
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

from packaging.requirements import Requirement

# Collect the declared runtime closure, plus the bundler's license. Unrelated
# packages installed on a developer machine must not contaminate the package.
def distributions():
    pending = ['focusdesk', 'pyinstaller']
    seen = set()
    while pending:
        name = pending.pop()
        normalized = name.lower().replace('_', '-')
        if normalized in seen:
            continue
        seen.add(normalized)
        dist = metadata.distribution(name)
        for dependency in dist.requires or []:
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
        yield dist

output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
summary=[]
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():
    (output/'PYTHON-LICENSE.txt').write_bytes(python_license.read_bytes())
for dist in distributions():
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
            # Preserve subdirectories: several wheels ship distinct LICENSE files
            # with the same basename (including case-insensitive Windows names).
            safe=Path(*[part for part in entry.parts if part not in ('.','..','/','\\')])
            target=output/name/safe
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source.read_bytes())
(output/'THIRD-PARTY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
