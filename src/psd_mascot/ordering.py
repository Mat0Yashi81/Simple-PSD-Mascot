"""選択を保った一覧の上下移動と、順序の保存・復元。"""
from PySide6.QtCore import Signal
from shiboken6 import isValid
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

def moved_list(values, index, step):
    """無効な移動はNoneを返し、元の一覧は変更しない。"""
    destination = index + step
    if step not in (-1, 1) or not 0 <= index < len(values) or not 0 <= destination < len(values):
        return None
    result = list(values)
    result.insert(destination, result.pop(index))
    return result

def moved_mapping(values, key, step):
    keys = list(values)
    if key not in values:
        return None
    moved = moved_list(keys, keys.index(key), step)
    return {name: values[name] for name in moved} if moved is not None else None

def restored_mapping(values, order):
    # Legacy tabs displayed alphabetically before manual ordering was added.
    if not isinstance(order, list):
        return {name: values[name] for name in sorted(values)}
    result = {}
    for name in order:
        if isinstance(name, str) and name in values:
            result[name] = values[name]
    for name, value in values.items():
        result.setdefault(name, value)
    return result

class ReorderButtons(QWidget):
    move_requested = Signal(int)
    def __init__(self, list_widget):
        super().__init__()
        self.list_widget = list_widget
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.up_button = QPushButton("上へ")
        self.down_button = QPushButton("下へ")
        layout.addWidget(self.up_button)
        layout.addWidget(self.down_button)
        self.up_button.clicked.connect(lambda: self.move_requested.emit(-1))
        self.down_button.clicked.connect(lambda: self.move_requested.emit(1))
        list_widget.currentRowChanged.connect(self._update_enabled)
        list_widget.model().rowsInserted.connect(self._update_enabled)
        list_widget.model().rowsRemoved.connect(self._update_enabled)
        list_widget.model().modelReset.connect(self._update_enabled)
        self._update_enabled()
    def _update_enabled(self, *_args):
        if not all(isValid(widget) for widget in (self.list_widget, self.up_button, self.down_button)):
            return
        index, count = self.list_widget.currentRow(), self.list_widget.count()
        self.up_button.setEnabled(index > 0)
        self.down_button.setEnabled(0 <= index < count-1)
