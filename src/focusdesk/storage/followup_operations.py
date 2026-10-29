"""Forward recovery of one requirement plus typed relation and deterministic events."""

from ..i18n import tr
from pathlib import Path
from ..domain.models import Node, HistoryEvent
from ..domain.common import utcnow
from ..errors import StorageError, ExternalModificationError, NotFoundError
from .atomic import atomic_write_json, atomic_write_text, read_json
from .paths import physical_dirname, is_reparse_point
from .repository import NODE_SUBDIRS


def apply_followup(repo,op):
    repo._require_writable()
    if op.state=='done':return op.data['new_node_id']
    node=Node.model_validate(op.data['node'])
    current=node.continuation_of;seen={node.id}
    while current is not None:
        if current in seen:raise StorageError(tr('storage.followup_operations.ciclu_in_relatia_cerintelor_recuperarea_necesita_corectarea_relatiei'))
        if current not in repo.nodes:break
        seen.add(current);current=repo.nodes[current].continuation_of
    target=repo.nodes_dir/physical_dirname(node.title,node.id)
    if node.creation_operation_id!=op.id:raise StorageError(tr('storage.followup_operations.identificator_de_operatie_neconcordant'))
    repo.mark_index_dirty()
    if not target.exists():
        current=node.parent_id;seen=set()
        while current is not None:
            if current not in repo.nodes:raise StorageError(tr('storage.followup_operations.destinatia_cerintei_nu_mai_este_disponibila_restaureaza_containerul_sa'))
            if current in seen or repo.nodes[current].archived_at is not None:raise StorageError(tr('storage.followup_operations.destinatia_este_arhivata_sau_invalida_recuperarea_asteapta_o_destinati'))
            seen.add(current);current=repo.nodes[current].parent_id
        repo.create_node(node,op.data['description'])
    else:
        if is_reparse_point(target) or is_reparse_point(repo.nodes_dir):raise StorageError(tr('extra.storage.followup_operations.director_de_recuperare_nesigur'))
        path=target/'node.json'
        if path.exists():
            stored=Node.model_validate(read_json(path,allow_backup=False)[0])
            if stored.id!=node.id or stored.creation_operation_id!=op.id or stored.continuation_of!=node.continuation_of:
                raise ExternalModificationError(tr('storage.followup_operations.identitatea_sau_relatia_taskului_in_curs_de_creare_s_a_schimbat_nu_se'))
        else:
            if 'node' in op.steps_done:raise ExternalModificationError(tr('storage.followup_operations.taskul_creat_a_fost_sters_extern_nu_se_recreeaza_automat'))
            # A reserved, interrupted create may contain only empty setup directories.
            if any(p.name not in NODE_SUBDIRS or not p.is_dir() or any(p.iterdir()) for p in target.iterdir()):
                raise StorageError(tr('storage.followup_operations.directorul_rezervat_contine_date_neasteptate_nu_se_suprascrie'))
            atomic_write_json(path,node.model_dump(mode='json'))
        description=target/'description.md'
        if description.exists():
            if description.read_text(encoding='utf-8-sig')!=op.data['description']:
                raise ExternalModificationError(tr('storage.followup_operations.descrierea_cerintei_a_fost_modificata_extern_ciorna_nu_se_suprascrie'))
        elif 'node' in op.steps_done:
            raise ExternalModificationError(tr('storage.followup_operations.descrierea_cerintei_a_fost_stearsa_extern'))
        else:atomic_write_text(description,op.data['description'])
        for name in NODE_SUBDIRS:(target/name).mkdir(exist_ok=True)
        if node.id not in repo.nodes:repo.load_node_dir(target)
        else:repo.reload_node(node.id)
    if 'node' not in op.steps_done:
        op.steps_done.append('node');op.updated_at=utcnow();repo.operations.save(op)
    for event_data in op.data['events']:
        event=HistoryEvent.model_validate(event_data)
        try:existing=repo.history.get(event.id)
        except NotFoundError:repo.history.save(event)
        else:
            if existing.model_dump(mode='json')!=event.model_dump(mode='json'):
                raise ExternalModificationError(tr('storage.followup_operations.evenimentul_operatiei_a_fost_modificat_nu_se_suprascrie'))
    # Durable compact receipt: no second permanent copy of description/checklist.
    op.data={'fingerprint':op.data['fingerprint'],'new_node_id':node.id,'source_id':node.continuation_of}
    op.state='done';op.updated_at=utcnow();repo.operations.save(op)
    return node.id


def recover_followups(repo):
    if repo.read_only:return []
    messages=[]
    for op in repo.operations.select(predicate=lambda row:row.get('type')=='followup_create' and row.get('state')=='pending'):
        try:
            apply_followup(repo,op)
            messages.append(tr('storage.followup_operations.cerinta_noua_intrerupta_a_fost_recuperata_fara_duplicate'))
        except Exception as exc:
            messages.append(tr('storage.followup_operations.cerinta_noua_in_asteptarea_recuperarii', exc=exc))
    return messages
