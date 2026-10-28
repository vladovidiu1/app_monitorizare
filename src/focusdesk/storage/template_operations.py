"""Rollback of template batches, including interruption before repository memory was updated."""
import shutil
from ..domain.models import Node
from ..domain.common import utcnow
from ..errors import StorageError
from .atomic import read_json
from .paths import physical_dirname, is_reparse_point


def rollback_template(repo, op):
    repo._require_writable()
    nodes=[Node.model_validate(value) for value in op.data['nodes']]
    for node in reversed(nodes):
        path=repo.nodes_dir/physical_dirname(node.title,node.id)
        if path.exists():
            if is_reparse_point(path):raise StorageError('Director de recuperare nesigur')
            if (path/'node.json').exists():
                data,_,_=read_json(path/'node.json',allow_backup=False)
                if data.get('id')!=node.id:raise StorageError('Identitate schimbată; recuperare manuală necesară')
            shutil.rmtree(path)
        repo.forget_subtree([node.id])
    op.state='rolled_back';op.updated_at=utcnow();repo.operations.save(op)


def recover_templates(repo):
    if repo.read_only:return []
    messages=[]
    for op in repo.operations.select(predicate=lambda row:row.get('state')=='pending' and row.get('type')=='template_create'):
        if op.type!='template_create' or op.state!='pending':continue
        try:
            rollback_template(repo,op)
            messages.append('Crearea întreruptă din șablon a fost anulată; datele existente sunt păstrate.')
        except Exception as exc:
            # Keep pending so recovery can be retried; never call the batch successful.
            messages.append(f'Crearea din șablon necesită recuperare: {exc}')
    return messages
