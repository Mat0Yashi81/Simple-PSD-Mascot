"""デスクトップ表示とアプリ全体の設定。"""
import math
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget, QPushButton, QComboBox, QGroupBox,
)

class SettingsPanel(QScrollArea):
    changed = Signal()
    cache_delete_requested = Signal()
    DEFAULTS = {
        "desktop_scale": 100, "blink_interval": 3.5,
        "voice_mouth_mode": "flap", "font_scale": 100,
        "topmost": True, "log_enabled": False,
    }
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        description = QLabel("設定は操作後に自動保存され、次回の起動時にも反映されます。")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.behavior_group = QGroupBox("マスコットの挙動")
        form = QFormLayout(self.behavior_group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.topmost_check = QCheckBox("マスコットを最前面に表示")
        self.topmost_check.setChecked(True)
        form.addRow(self.topmost_check)
        self.desktop_scale = QSpinBox()
        self.desktop_scale.setRange(10, 300)
        self.desktop_scale.setSuffix(" %")
        self.desktop_scale.setValue(100)
        self.desktop_scale.setKeyboardTracking(False)
        self.desktop_scale.setToolTip("100%は現在の描画画像の大きさです。プレビューの大きさは変更しません。")
        form.addRow("デスクトップ表示倍率", self.desktop_scale)
        self.blink_interval = QDoubleSpinBox()
        self.blink_interval.setDecimals(1)
        self.blink_interval.setRange(0.1, 60.0)
        self.blink_interval.setSingleStep(0.1)
        self.blink_interval.setSuffix(" 秒")
        self.blink_interval.setValue(3.5)
        self.blink_interval.setKeyboardTracking(False)
        self.blink_interval.setToolTip("目が開いてから、次に閉じるまでの待ち時間です。")
        form.addRow("まばたきの感覚", self.blink_interval)
        self.voice_mouth_mode = QComboBox()
        self.voice_mouth_mode.addItem("開けっ放し", "open")
        self.voice_mouth_mode.addItem("口パク", "flap")
        self.voice_mouth_mode.addItem("動かさない", "none")
        self.voice_mouth_mode.setCurrentIndex(1)
        self.voice_mouth_mode.setToolTip("音声再生中の口の動きです。終了・停止すると通常の口制御へ戻ります。")
        form.addRow("口パクの種類", self.voice_mouth_mode)
        self.font_scale = QSpinBox()
        self.font_scale.setRange(50, 200)
        self.font_scale.setSingleStep(5)
        self.font_scale.setSuffix(" %")
        self.font_scale.setValue(100)
        self.font_scale.setKeyboardTracking(False)
        layout.addWidget(self.behavior_group)
        hint = QLabel("「動き」タブで、まばたき用の閉眼レイヤーと、音声用の開き口・閉じ口レイヤーを割り当ててください。")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.application_group = QGroupBox("アプリの設定")
        application_form = QFormLayout(self.application_group)
        application_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        application_form.addRow("アプリのフォント倍率", self.font_scale)
        self.cache_delete_button = QPushButton("キャッシュの削除")
        self.cache_delete_button.clicked.connect(lambda: self.cache_delete_requested.emit())
        application_form.addRow(self.cache_delete_button)
        layout.addWidget(self.application_group)
        self.debug_group = QGroupBox("デバッグ")
        debug_layout = QVBoxLayout(self.debug_group)
        self.log_enabled_check = QCheckBox("Log機能のオンオフ")
        self.log_enabled_check.setChecked(False)
        self.log_enabled_check.setToolTip("オンの場合にキャッシュ生成・描画の計測ログを保存します。初期値はオフです。")
        debug_layout.addWidget(self.log_enabled_check)
        self.reset_button = QPushButton("設定タブのリセット")
        self.reset_button.setToolTip("このタブの全設定を初期値に戻します。プリセット・音声・キャッシュは削除しません。")
        self.reset_button.clicked.connect(self.reset_defaults)
        debug_layout.addWidget(self.reset_button)
        layout.addWidget(self.debug_group)
        layout.addStretch(1)
        for control in (self.desktop_scale, self.blink_interval, self.font_scale):
            control.valueChanged.connect(lambda _value: self.changed.emit())
        self.topmost_check.toggled.connect(lambda _value: self.changed.emit())
        self.log_enabled_check.toggled.connect(lambda _value: self.changed.emit())
        self.voice_mouth_mode.currentIndexChanged.connect(lambda _value: self.changed.emit())
    def reset_defaults(self) -> None:
        self.restore(self.DEFAULTS)
        self.changed.emit()
    def values(self) -> dict:
        return {
            "desktop_scale": self.desktop_scale.value(),
            "blink_interval": self.blink_interval.value(),
            "voice_mouth_mode": self.voice_mouth_mode.currentData(),
            "font_scale": self.font_scale.value(),
            "topmost": self.topmost_check.isChecked(),
            "log_enabled": self.log_enabled_check.isChecked(),
        }
    def restore(self, values: dict) -> None:
        was_blocked = self.blockSignals(True)
        try:
            for name, control in (
                ("desktop_scale", self.desktop_scale),
                ("blink_interval", self.blink_interval),
                ("font_scale", self.font_scale),
            ):
                try:
                    value = float(values.get(name, control.value()))
                    if math.isfinite(value):
                        value = max(control.minimum(), min(control.maximum(), value))
                        control.setValue(value if name == "blink_interval" else round(value))
                except (TypeError, ValueError, OverflowError):
                    pass
            if isinstance(values.get("topmost"), bool):
                self.topmost_check.setChecked(values["topmost"])
            index = self.voice_mouth_mode.findData(values.get("voice_mouth_mode", "flap"))
            self.voice_mouth_mode.setCurrentIndex(index if index >= 0 else 1)
            log_enabled = values.get("log_enabled", False)
            self.log_enabled_check.setChecked(log_enabled if isinstance(log_enabled, bool) else False)
        finally:
            self.blockSignals(was_blocked)
