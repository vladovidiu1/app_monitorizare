"""Shared local node/status images and explicit labels; original MIT resources."""
from ..domain.models import Kind, Status
from ..domain.labels import STATUS_LABELS, KIND_LABELS
from .design import icon


def node_icon(widget, node, size=20):
    name = node.kind.value
    if node.kind == Kind.TASK:
        name = 'status-' + (Status.TODO if node.status == Status.INBOX else node.status or Status.TODO).value
    return icon(widget, name, size)


def node_label(node):
    return STATUS_LABELS.get(node.status, '') if node.kind == Kind.TASK else KIND_LABELS[node.kind]
