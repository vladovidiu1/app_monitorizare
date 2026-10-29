"""Stable IDs shared by navigation and saved profile state; never display labels."""
from ..i18n import tr

TAB_IDS = {'Detalii':'details','Subtaskuri':'subtasks','Subtask-uri':'subtasks',
           'Activitate':'journal','Jurnal':'journal','Fișiere':'files',
           'Planificare':'planning','Versiuni':'versions','Pași':'steps'}
TAB_KEYS = {key:f'nav.tab.{key}' for key in TAB_IDS.values()}


def tab_id(value):
    return TAB_IDS.get(value, value)


def tab_label(value):
    return tr(TAB_KEYS[tab_id(value)])


class TabMap(dict):
    """Read legacy names for extensions; enumerate only stable IDs."""
    def __getitem__(self,key):return super().__getitem__(tab_id(key))
    def __setitem__(self,key,value):return super().__setitem__(tab_id(key),value)
    def get(self,key,default=None):return super().get(tab_id(key),default)
