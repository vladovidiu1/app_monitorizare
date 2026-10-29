"""Rollback of template batches, including interruption before repository memory was updated."""

from ..i18n import tr
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
            if is_reparse_point(path):raise StorageError(tr('extra.storage.followup_operations.director_de_recuperare_nesigur'))
            if (path/'node.json').exists():
                data,_,_=read_json(path/'node.json',allow_backup=False)
                if data.get('id')!=node.id:raise StorageError(tr('storage.template_operations.identitate_schimbata_recuperare_manuala_necesara'))
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
            messages.append(tr('storage.template_operations.crearea_intrerupta_din_sablon_a_fost_anulata_datele_existente_sunt_pas'))
        except Exception as exc:
            # Keep pending so recovery can be retried; never call the batch successful.
            messages.append(tr('storage.template_operations.crearea_din_sablon_necesita_recuperare', exc=exc))
    return messages
