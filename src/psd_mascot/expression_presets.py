"""表情（動き設定）のプリセット一覧と操作UI。"""

from PySide6.QtCore import Qt, Signal
from .ordering import ReorderButtons
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QVBoxLayout, QWidget,
)


class ExpressionPresetPanel(QWidget):
    save_requested = Signal(str)
    apply_requested = Signal(str)
    delete_requested = Signal(str)
    move_requested = Signal(str, int)
    cache_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        description = QLabel(
            "「動き」タブの眉・開眼・閉眼・閉じ口・開き口・アクセサリの割り当てと、"
            "簡易口パクのON/OFFを表情として保存します。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.preset_list = QListWidget()
        self.preset_list.currentTextChanged.connect(self._select_name)
        self.preset_list.itemDoubleClicked.connect(lambda _: self._apply())
        layout.addWidget(self.preset_list, 1)
        self.reorder_buttons = ReorderButtons(self.preset_list)
        self.reorder_buttons.move_requested.connect(self._move)
        layout.addWidget(self.reorder_buttons)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("表情名（例：通常・笑顔）")
        layout.addWidget(self.name_edit)
        row = QHBoxLayout()
        save = QPushButton("動き設定を保存")
        save.clicked.connect(lambda: self.save_requested.emit(self.name_edit.text().strip()))
        apply = QPushButton("呼び出す")
        apply.clicked.connect(self._apply)
        delete = QPushButton("削除")
        delete.clicked.connect(self._delete)
        for button in (save, apply, delete):
            row.addWidget(button)
        layout.addLayout(row)
        self.cache_button = QPushButton("表情の事前キャッシュを生成")
        self.cache_button.clicked.connect(lambda: self.cache_requested.emit())
        layout.addWidget(self.cache_button)

    def _move(self, step):
        item = self.preset_list.currentItem()
        if item is not None:
            self.move_requested.emit(item.text(), step)
    def _select_name(self, name: str) -> None:
        if name:
            self.name_edit.setText(name)

    def _apply(self) -> None:
        item = self.preset_list.currentItem()
        if item is not None:
            self.apply_requested.emit(item.text())

    def _delete(self) -> None:
        item = self.preset_list.currentItem()
        if item is not None:
            self.delete_requested.emit(item.text())

    def set_names(self, names, selected: str | None = None) -> None:
        self.preset_list.clear()
        self.preset_list.addItems(list(names))
        if selected:
            matches = self.preset_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if matches:
                self.preset_list.setCurrentItem(matches[0])
