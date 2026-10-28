"""Small validated navigation metadata; attachments/checklists hydrate only on demand."""
from pydantic import PrivateAttr
from ..domain.models import Node

HEAVY = {'attachments', 'checklist'}


class NavigationNode(Node):
    _loader: object = PrivateAttr(default=None)
    _full: Node | None = PrivateAttr(default=None)

    def hydrate(self):
        if self._full is None:
            self._full = self._loader()
        return self._full

    def __getattribute__(self, name):
        if name in HEAVY:
            private = object.__getattribute__(self, '__pydantic_private__')
            if private and private.get('_loader'):
                return self.hydrate().__getattribute__(name)
        return super().__getattribute__(name)

    def model_dump(self, *args, **kwargs):
        return self.hydrate().model_dump(*args, **kwargs)

    def model_copy(self, *args, **kwargs):
        return self.hydrate().model_copy(*args, **kwargs)


def navigation_data(node):
    if isinstance(node, NavigationNode):
        return Node.model_dump(node, mode='json', exclude=HEAVY | set(node.model_extra or {}))
    return node.model_dump(mode='json', exclude=HEAVY | set(node.model_extra or {}))
