"""PSDキャンバスに対する正規化座標でリアクションを保存する。"""

import math
from uuid import uuid4
from .ordering import ReorderButtons

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


def sanitize_reactions(values):
    result = []
    used = set()
    if not isinstance(values, list):
        return result
    for value in values:
        try:
            x, y, width, height = map(float, value["rect"])
            duration = float(value.get("duration", 2.0))
            if not all(math.isfinite(n) for n in (x, y, width, height, duration)):
                continue
            x, y = max(0, min(.99, x)), max(0, min(.99, y))
            width, height = max(.01, min(1-x, width)), max(.01, min(1-y, height))
            identifier = str(value.get("id") or uuid4().hex)
            if identifier in used:
                identifier = uuid4().hex
            used.add(identifier)
            result.append({
                "id": identifier,
                "name": str(value.get("name") or "当たり判定"),
                "rect": [x, y, width, height],
                "expression": str(value.get("expression") or ""),
                "voice": str(value.get("voice") or ""),
                "duration": round(max(.1, min(600, duration)), 1),
            })
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    return result


def find_reaction(regions, x, y):
    # Overlapping boxes use the last (frontmost) entry.
    for region in reversed(regions):
        left, top, width, height = region["rect"]
        if left <= x <= left+width and top <= y <= top+height:
            return region
    return None


class ReactionPanel(QScrollArea):
    add_requested = Signal()
    delete_requested = Signal(str)
    selection_changed = Signal(str)
    edited = Signal(str, object)
    test_requested = Signal(str)
    move_requested = Signal(str, int)

    def __init__(self):
        super().__init__()
        self._updating = False
        self._regions = []
        self._expression_names = []
        self._voice_presets = []
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        hint = QLabel(
            "当たり判定を追加し、右側のプレビューでドラッグ移動・"
            "辺や角のハンドルでサイズ変更してください。"
            "ボックスはこのタブでのみ表示します。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.region_list = QListWidget()
        self.region_list.setMinimumHeight(100)
        self.region_list.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.region_list, 1)
        self.reorder_buttons = ReorderButtons(self.region_list)
        self.reorder_buttons.move_requested.connect(
            lambda step: self.move_requested.emit(self.selected_id(), step))
        layout.addWidget(self.reorder_buttons)
        row = QHBoxLayout()
        add = QPushButton("当たり判定を追加")
        add.clicked.connect(lambda: self.add_requested.emit())
        delete = QPushButton("削除")
        delete.clicked.connect(lambda: self.delete_requested.emit(self.selected_id()))
        row.addWidget(add)
        row.addWidget(delete)
        layout.addLayout(row)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("判定名（例：頭）")
        self.expression_combo = QComboBox()
        self.voice_combo = QComboBox()
        self.duration = QDoubleSpinBox()
        self.duration.setDecimals(1)
        self.duration.setRange(.1, 600)
        self.duration.setSingleStep(.1)
        self.duration.setSuffix(" 秒")
        self.duration.setValue(2)
        self.duration.setKeyboardTracking(False)
        form.addRow("判定名", self.name_edit)
        form.addRow("呼び出す表情", self.expression_combo)
        form.addRow("呼び出すセリフ", self.voice_combo)
        form.addRow("持続時間", self.duration)
        layout.addLayout(form)
        self.geometry_label = QLabel("ボックスを選択してください")
        self.geometry_label.setWordWrap(True)
        layout.addWidget(self.geometry_label)
        test = QPushButton("選択したリアクションを試す")
        test.clicked.connect(lambda: self.test_requested.emit(self.selected_id()))
        layout.addWidget(test)
        explanation = QLabel(
            "デスクトップの判定内をタップすると表情が一時的に変わり、"
            "指定時間後に戻ります。セリフも指定できます。ドラッグ移動では反応しません。"
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.name_edit.editingFinished.connect(self._commit)
        self.expression_combo.currentIndexChanged.connect(lambda _: self._commit())
        self.voice_combo.currentIndexChanged.connect(lambda _: self._commit())
        self.duration.valueChanged.connect(lambda _: self._commit())
        self._show_region()

    def selected_id(self):
        item = self.region_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else ""

    def set_regions(self, regions, selected=None):
        selected = self.selected_id() if selected is None else selected
        self._updating = True
        self._regions = regions
        self.region_list.clear()
        for region in regions:
            item = QListWidgetItem(region["name"])
            item.setData(Qt.ItemDataRole.UserRole, region["id"])
            self.region_list.addItem(item)
            if region["id"] == selected:
                self.region_list.setCurrentItem(item)
        self._updating = False
        self._show_region()

    def set_expressions(self, names):
        self._expression_names = list(names)
        self._show_region()

    def set_voices(self, presets):
        self._voice_presets = list(presets)
        self._show_region()

    def select_region(self, identifier):
        for i in range(self.region_list.count()):
            item = self.region_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == identifier:
                self.region_list.setCurrentItem(item)
                return
        self.region_list.setCurrentItem(None)

    def _selection_changed(self, _current, _previous):
        if not self._updating:
            self._show_region()
            self.selection_changed.emit(self.selected_id())

    def _show_region(self):
        region = next((r for r in self._regions if r["id"] == self.selected_id()), None)
        self._updating = True
        for control in (self.name_edit, self.expression_combo, self.voice_combo, self.duration):
            control.setEnabled(region is not None)
        self.expression_combo.clear()
        self.expression_combo.addItem("(未設定)", "")
        for name in self._expression_names:
            self.expression_combo.addItem(name, name)
        self.voice_combo.clear()
        self.voice_combo.addItem("(未設定)", "")
        for preset in self._voice_presets:
            self.voice_combo.addItem(preset["name"], preset["id"])
        if region is not None:
            voice_id = region.get("voice", "")
            if voice_id and self.voice_combo.findData(voice_id) < 0:
                self.voice_combo.addItem("(見つからないセリフ)", voice_id)
            self.voice_combo.setCurrentIndex(max(0, self.voice_combo.findData(voice_id)))
            name = region["expression"]
            if name and name not in self._expression_names:
                self.expression_combo.addItem(f"(見つからない表情: {name})", name)
            self.name_edit.setText(region["name"])
            self.expression_combo.setCurrentIndex(max(0, self.expression_combo.findData(name)))
            self.duration.setValue(region["duration"])
            self.show_geometry(region["rect"])
        else:
            self.name_edit.clear()
            self.geometry_label.setText("ボックスを選択してください")
        self._updating = False

    def show_geometry(self, rect):
        x, y, width, height = rect
        self.geometry_label.setText(
            f"位置 X {x*100:.1f}% / Y {y*100:.1f}%　"
            f"大きさ {width*100:.1f}% × {height*100:.1f}%"
        )

    def _commit(self):
        identifier = self.selected_id()
        if not self._updating and identifier:
            self.edited.emit(identifier, {
                "name": self.name_edit.text().strip() or "当たり判定",
                "expression": self.expression_combo.currentData() or "",
                "voice": self.voice_combo.currentData() or "",
                "duration": self.duration.value(),
            })
