from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .expression_presets import ExpressionPresetPanel
from .settings_panel import SettingsPanel
from .ordering import ReorderButtons, moved_list, moved_mapping, restored_mapping
from .voices import VoiceController, VoicePanel
from .disk_cache import CacheRegistry, MAX_SIDE, state_digest
from . import performance_log as perf
from .region_renderer import RegionRenderer
from .cache_plan import effective_visibility, animation_states, generate_plan
from .cache_dialogs import confirm_generation, PrecacheProgressDialog, CacheDeleteDialog
from queue import Queue, Empty
from .reaction_preview import ReactionPreview as Preview
from .reactions import ReactionPanel, find_reaction, sanitize_reactions
from .idle import IdlePanel, IdleScheduler, IdleActivityFilter, sanitize_idle
from .branding import APP_NAME, WINDOW_TITLE, app_icon, configure_application, settings_directory, set_windows_app_id
from uuid import uuid4

from PIL import Image
from psd_tools import PSDImage
from PySide6.QtCore import QStandardPaths, Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QAction, QFont, QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def runtime_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _key(parts: tuple[int, ...]) -> str:
    return "/".join(map(str, parts))


def _label(layer: Any) -> str:
    name = getattr(layer, "name", None) or "(名称なし)"
    return str(name)


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


class MascotWindow(QWidget):
    tapped = Signal(float, float)
    voice_requested = Signal(str)
    outfit_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.image = QLabel(self)
        self.image.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        close_action = QAction("閉じる", self)
        close_action.triggered.connect(self.hide)
        self.voice_menu = QMenu("ボイス", self)
        self.voice_menu.setEnabled(False)
        self.addAction(self.voice_menu.menuAction())
        self.outfit_menu = QMenu("着替え", self)
        self.outfit_menu.setEnabled(False)
        self.addAction(self.outfit_menu.menuAction())
        self.addAction(close_action)
        self._drag_offset = None
        self._press_global = None
        self._dragging = False
        self.reactions = []
        self.pixmap: QPixmap | None = None
        self.scale_percent = 100

    def set_voice_presets(self, presets):
        self.voice_menu.clear()
        for preset in presets:
            if preset["voice"] is True:
                action = self.voice_menu.addAction(preset["name"])
                action.setData(preset["id"])
                action.triggered.connect(
                    lambda _checked=False, identifier=preset["id"]: self.voice_requested.emit(identifier)
                )
        self.voice_menu.setEnabled(bool(self.voice_menu.actions()))

    def set_outfit_presets(self, names):
        self.outfit_menu.clear()
        for name in names:
            action = self.outfit_menu.addAction(name)
            action.setData(name)
            action.triggered.connect(
                lambda _checked=False, selected=name: self.outfit_requested.emit(selected))
        self.outfit_menu.setEnabled(bool(self.outfit_menu.actions()))

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self._update_image()

    def set_scale_percent(self, percent: int) -> None:
        percent = max(10, min(300, int(percent)))
        if self.scale_percent != percent:
            self.scale_percent = percent
            self._update_image()

    def _update_image(self) -> None:
        if self.pixmap is None or self.pixmap.isNull():
            return
        # Always scale from the original frame to avoid accumulating blur.
        width = max(1, round(self.pixmap.width() * self.scale_percent / 100))
        height = max(1, round(self.pixmap.height() * self.scale_percent / 100))
        scaled = self.pixmap if self.scale_percent == 100 else self.pixmap.scaled(
            width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.resize(width, height)
        self.image.setGeometry(0, 0, width, height)
        self.image.setPixmap(scaled)

    def set_reactions(self, regions):
        self.reactions = regions
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # A virtually transparent fill keeps alpha-zero portions of a hit box
        # clickable on Windows layered windows. No outline is drawn here.
        painter = QPainter(self)
        for region in self.reactions:
            x, y, width, height = region["rect"]
            painter.fillRect(QRectF(x*self.width(), y*self.height(),
                                   width*self.width(), height*self.height()), QColor(0, 0, 0, 1))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            self._dragging = self._dragging or distance >= QApplication.startDragDistance()
            if self._dragging:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            distance = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
            if not self._dragging and distance < QApplication.startDragDistance():
                self.tapped.emit(event.position().x()/max(1, self.width()),
                                 event.position().y()/max(1, self.height()))
            self._press_global = None
            self._drag_offset = None
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class MascotApp(QMainWindow):
    ROLE_NONE = "(未設定)"
    EYE_CLOSED_WORDS = ("閉じ目", "目閉", "まばたき", "瞬き", "eye_close", "eyes_closed", "blink")
    EYE_OPEN_WORDS = ("開き目", "目開", "通常目", "eye_open", "eyes_open")
    MOUTH_OPEN_WORDS = ("口開", "開口", "口パク", "mouth_open", "mouthopen")
    MOUTH_CLOSED_WORDS = ("口閉", "閉口", "mouth_closed", "mouthclose")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1040, 700)
        app = QApplication.instance()
        base_font = app.property("psdMascotBaseFont")
        if not isinstance(base_font, QFont):
            base_font = QFont(app.font())
            app.setProperty("psdMascotBaseFont", base_font)
        self._base_ui_font = QFont(base_font)
        self._last_font_scale = None
        self._last_blink_interval = None
        self._last_voice_mouth_mode = None
        perf.configure(runtime_directory() / "logs")
        perf.set_enabled(False)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.job = None
        self.pending_render = None
        self.region_renderer = None
        self.frame_cache = OrderedDict()
        self.cache_bytes = 0
        self.cache_registry = CacheRegistry(runtime_directory() / "cache")
        self.document_cache = None
        self.bulk_active = False
        self.bulk_dialog = None
        self._bulk_pending = None
        self._bulk_progress = None
        self.cache_manager_active = False
        self.cache_manager = None
        self._cache_manager_pending = False
        self._manager_render_pending = False
        self._cache_root_error = ""
        try:
            self.cache_registry.ensure()
        except OSError as exc:
            self._cache_root_error = str(exc)
        self._loading = False
        self.warm_queue = []
        self.warm_total = 0
        self.warm_done = 0
        self.psd: PSDImage | None = None
        self.psd_path: Path | None = None
        self.layers: dict[str, Any] = {}
        self.labels: dict[str, str] = {}
        self.base_visibility: dict[str, bool] = {}
        self.presets: dict[str, dict[str, bool]] = {}
        self.outfit_menu_names: set[str] = set()
        self.expression_presets: dict[str, dict[str, Any]] = {}
        self.expression_layers: set[str] = set()
        self._restoring_settings = False
        self.reactions = []
        self.idle_settings = sanitize_idle({})
        self.idle_scheduler = IdleScheduler()
        self._action_source = None
        self._idle_active_id = None
        self._idle_hold_until = None
        self._idle_voice_id = None
        self._closing = False
        self._reaction_return_motion = None
        self._reaction_pending_voice = None
        self._reaction_wait_state = None
        self._reaction_expires_at = None
        self._reaction_duration = 0.0
        self.blink_active = False
        self.mouth_open = False
        self._voice_playing = False
        self._voice_mouth_open = True
        self._voice_frozen_open = False
        self._voice_mouth_deadline = 0.0
        self.blink_deadline = 0.0
        self.blink_end = 0.0
        self.mouth_deadline = 0.0
        self._updating_tree = False
        self._pixmap: QPixmap | None = None
        self.mascot_window = MascotWindow()

        self.preview = Preview()
        self.tabs = QTabWidget()
        self.layer_tree = QTreeWidget()
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.itemChanged.connect(self._on_layer_changed)
        layer_page = QWidget()
        layer_layout = QVBoxLayout(layer_page)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.addWidget(self.layer_tree, 1)
        self.all_cache_button = QPushButton("すべての事前キャッシュを生成")
        self.all_cache_button.clicked.connect(lambda: self._request_bulk_cache("all"))
        layer_layout.addWidget(self.all_cache_button)
        self.tabs.addTab(layer_page, "レイヤー")
        self.tabs.addTab(self._build_preset_tab(), "服装")
        self.expression_panel = ExpressionPresetPanel()
        self.expression_panel.save_requested.connect(self.save_expression)
        self.expression_panel.apply_requested.connect(self.apply_expression)
        self.expression_panel.delete_requested.connect(self.delete_expression)
        self.expression_panel.move_requested.connect(self._move_expression)
        self.expression_panel.cache_requested.connect(lambda: self._request_bulk_cache("expressions"))
        self.tabs.addTab(self.expression_panel, "表情")
        self.tabs.addTab(self._build_motion_tab(), "動き")
        self.reaction_panel = ReactionPanel()
        self.tabs.addTab(self.reaction_panel, "リアクション")
        self.idle_panel = IdlePanel()
        self.tabs.addTab(self.idle_panel, "放置")
        self.voice_controller = VoiceController(runtime_directory() / "voice", self)
        self.voice_panel = VoicePanel(self.voice_controller)
        self.tabs.addTab(self.voice_panel, "セリフ")
        self.settings_panel = SettingsPanel()
        self.topmost_check = self.settings_panel.topmost_check
        self.tabs.addTab(self.settings_panel, "設定")

        splitter = QSplitter()
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("PSDを開いて開始してください")

        self.progress_label = QLabel("待機中")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.statusBar().addPermanentWidget(self.progress_label)
        self.statusBar().addPermanentWidget(self.progress)

        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(30)
        self.job_timer.timeout.connect(self._poll_job)
        self.job_timer.start()
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.setInterval(300)
        self.settings_save_timer.timeout.connect(self._save_app_settings)
        self.settings_panel.changed.connect(self._on_app_settings_changed)
        self.settings_panel.cache_delete_requested.connect(self._request_cache_delete)
        self._load_app_settings()
        self.reaction_panel.add_requested.connect(self._add_reaction)
        self.reaction_panel.delete_requested.connect(self._delete_reaction)
        self.reaction_panel.selection_changed.connect(self.preview.select_region)
        self.reaction_panel.edited.connect(self._edit_reaction)
        self.reaction_panel.test_requested.connect(self._trigger_reaction)
        self.reaction_panel.move_requested.connect(self._move_reaction)
        self.preview.box_selected.connect(self.reaction_panel.select_region)
        self.preview.box_changed.connect(self._edit_reaction_geometry)
        self.mascot_window.tapped.connect(self._tap_reaction)
        self.tabs.currentChanged.connect(self._reaction_tab_changed)
        self.reaction_save_timer = QTimer(self)
        self.reaction_save_timer.setSingleShot(True)
        self.reaction_save_timer.setInterval(300)
        self.reaction_save_timer.timeout.connect(self._save_data)
        self.reaction_timer = QTimer(self)
        self.reaction_timer.setInterval(20)
        self.reaction_timer.timeout.connect(self._advance_reaction)
        self.reaction_timer.start()
        self.voice_controller.presets_changed.connect(self._sync_voice_menu)
        self.voice_controller.playback_active_changed.connect(self._on_voice_playback_changed)
        self.voice_controller.message_changed.connect(self.statusBar().showMessage)
        self.mascot_window.voice_requested.connect(self.voice_controller.play)
        self.mascot_window.outfit_requested.connect(self._apply_menu_outfit)
        self._sync_voice_menu()
        self.idle_panel.add_requested.connect(self._add_idle)
        self.idle_panel.delete_requested.connect(self._delete_idle)
        self.idle_panel.edited.connect(self._edit_idle)
        self.idle_panel.options_changed.connect(self._edit_idle_options)
        self.idle_panel.move_requested.connect(self._move_idle)
        self.idle_panel.test_requested.connect(self._trigger_idle_action)
        self._refresh_idle()
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(200)
        self.idle_timer.timeout.connect(self._advance_idle)
        self.idle_timer.start()
        self.idle_activity_filter = IdleActivityFilter(self, self.mascot_window)
        self.idle_activity_filter.activity.connect(self._on_user_activity)
        QApplication.instance().installEventFilter(self.idle_activity_filter)
        self.tray_icon = QSystemTrayIcon(app_icon(), self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("開く", self._show_from_tray)
        self.tray_menu.addAction("終了", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        if self._cache_root_error:
            self.statusBar().showMessage(f"キャッシュフォルダを作成できませんでした: {self._cache_root_error}")

    def _show_from_tray(self):
        self._on_user_activity()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        self.open_button = QPushButton("PSDを開く")
        self.open_button.clicked.connect(self.open_psd_dialog)
        self.stage_button = QPushButton("デスクトップに表示")
        self.stage_button.clicked.connect(self.toggle_stage)
        layout.addWidget(self.open_button)
        layout.addWidget(self.stage_button)
        layout.addStretch(1)
        self.file_label = QLabel("PSD未読込")
        self.file_label.setStyleSheet("color: #666")
        layout.addWidget(self.file_label, 1)
        return bar

    def _build_preset_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("現在のレイヤー表示状態に名前を付けて保存します。"))
        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(lambda *_: self._show_outfit_menu_check())
        self.preset_list.itemDoubleClicked.connect(lambda _item: self.apply_selected_preset())
        layout.addWidget(self.preset_list, 1)
        self.outfit_reorder = ReorderButtons(self.preset_list)
        self.outfit_reorder.move_requested.connect(self._move_outfit)
        layout.addWidget(self.outfit_reorder)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("服装名（例：制服）")
        layout.addWidget(self.preset_name)
        self.outfit_menu_check = QCheckBox("着替え")
        self.outfit_menu_check.setToolTip("選択した服装を、立ち絵の右クリック「着替え」メニューに表示します。")
        self.outfit_menu_check.setEnabled(False)
        self.outfit_menu_check.toggled.connect(self._set_outfit_menu_check)
        layout.addWidget(self.outfit_menu_check)
        row = QHBoxLayout()
        save = QPushButton("現在の状態を保存")
        save.clicked.connect(self.save_preset)
        apply = QPushButton("呼び出す")
        apply.clicked.connect(self.apply_selected_preset)
        delete = QPushButton("削除")
        delete.clicked.connect(self.delete_selected_preset)
        row.addWidget(save)
        row.addWidget(apply)
        row.addWidget(delete)
        layout.addLayout(row)
        self.outfit_cache_button = QPushButton("服装の事前キャッシュを生成")
        self.outfit_cache_button.clicked.connect(lambda: self._request_bulk_cache("outfits"))
        layout.addWidget(self.outfit_cache_button)
        return page

    def _build_motion_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("PSD内の開閉レイヤーを割り当てると、表示状態を保ったまま動きを重ねます。"))
        form = QFormLayout()
        self.brow_combo = QComboBox()
        self.eye_open_combo = QComboBox()
        self.eye_closed_combo = QComboBox()
        self.mouth_closed_combo = QComboBox()
        self.mouth_open_combo = QComboBox()
        self.accessory_combo = QComboBox()
        for combo in (self.brow_combo, self.eye_open_combo, self.eye_closed_combo, self.mouth_closed_combo, self.mouth_open_combo, self.accessory_combo):
            combo.currentIndexChanged.connect(self._on_role_changed)
        form.addRow("眉", self.brow_combo)
        form.addRow("開眼レイヤー", self.eye_open_combo)
        form.addRow("閉眼レイヤー", self.eye_closed_combo)
        form.addRow("閉じ口レイヤー", self.mouth_closed_combo)
        form.addRow("開き口レイヤー", self.mouth_open_combo)
        form.addRow("アクセサリ", self.accessory_combo)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.blink_button = QPushButton("今すぐまばたき")
        self.blink_button.clicked.connect(self.trigger_blink)
        self.lipsync_check = QCheckBox("簡易口パク")
        self.lipsync_check.toggled.connect(self._on_lipsync_toggled)
        row.addWidget(self.blink_button)
        row.addWidget(self.lipsync_check)
        layout.addLayout(row)
        prepare = QPushButton("現在の表情を事前キャッシュ")
        prepare.clicked.connect(self._prepare_current_cache)
        layout.addWidget(prepare)
        layout.addStretch(1)
        return page

    def open_psd_dialog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "PSDを開く", "", "Photoshop files (*.psd *.psb)")
        if filename:
            self.load_psd(Path(filename))

    def load_psd(self, path: Path) -> None:
        if self.bulk_active or self.cache_manager_active:
            return
        if self.job is not None:
            self.statusBar().showMessage("処理中です。完了後にPSDを開いてください")
            return
        self._stop_idle_action()
        self.idle_scheduler.reset()
        self._cancel_reaction(restore=True)
        self._save_data()
        self._loading = True
        self.warm_queue.clear()
        self._set_progress("PSD読み込み中…")
        self.pending_render = None
        self.open_button.setEnabled(False)
        self.tabs.setEnabled(False)
        self.statusBar().showMessage("PSDを読み込み中…")
        self.job = ("load", path, self.executor.submit(self.cache_registry.load_document, path))

    def _finish_load(self, path: Path, psd: PSDImage, document_cache) -> None:
        if self.region_renderer is not None:
            self.region_renderer.clear()
        self.region_renderer = None
        self.document_cache = document_cache
        self.frame_cache.clear()
        self.cache_bytes = 0
        self._restoring_settings = True
        self.psd = psd
        self.psd_path = path.resolve()
        self.blink_active = False
        self.mouth_open = False
        self.lipsync_check.setChecked(False)
        self.layers.clear()
        self.labels.clear()
        self.base_visibility.clear()
        self.presets = {}
        self.outfit_menu_names.clear()
        self.expression_presets = {}
        self.expression_layers.clear()
        self.reactions = []
        self.idle_settings = sanitize_idle({})
        self.idle_scheduler.reset()
        self.expression_panel.set_names([])
        self._populate_layers()
        self._populate_role_combos()
        self._load_data()
        self._restoring_settings = False
        self._track_motion_layers()
        self._refresh_reactions()
        self._refresh_idle()
        self.file_label.setText(path.name)
        self.statusBar().showMessage(f"{path.name}  ({psd.width} × {psd.height})")
        self.last_psd_path = str(self.psd_path)
        self._save_app_settings()
        self._start_warmup()

    def _populate_layers(self) -> None:
        assert self.psd is not None
        self._updating_tree = True
        self.layer_tree.clear()

        def add_children(parent: QTreeWidgetItem | None, children: Any, prefix: tuple[int, ...]) -> None:
            for index, layer in enumerate(children):
                path = prefix + (index,)
                key = _key(path)
                label = _label(layer)
                self.layers[key] = layer
                self.labels[key] = label
                self.base_visibility[key] = bool(layer.visible)
                item = QTreeWidgetItem([label])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                item.setToolTip(0, self._layer_path(key))
                if parent is None:
                    self.layer_tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                if getattr(layer, "is_group", lambda: False)():
                    add_children(item, layer, path)

        add_children(None, self.psd, ())
        self.layer_tree.expandAll()
        self._updating_tree = False

    def _layer_path(self, key: str) -> str:
        indices = tuple(int(part) for part in key.split("/"))
        names: list[str] = []
        container: Any = self.psd
        for index in indices:
            layer = container[index]
            names.append(_label(layer))
            container = layer
        return " / ".join(names)

    def _populate_role_combos(self) -> None:
        combos = (self.brow_combo, self.eye_open_combo, self.eye_closed_combo, self.mouth_closed_combo, self.mouth_open_combo, self.accessory_combo)
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(self.ROLE_NONE, "")
            for key, label in self.labels.items():
                combo.addItem(self._layer_path(key), key)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._auto_select(self.eye_open_combo, self.EYE_OPEN_WORDS)
        self._auto_select(self.eye_closed_combo, self.EYE_CLOSED_WORDS)
        self._auto_select(self.mouth_closed_combo, self.MOUTH_CLOSED_WORDS)
        self._auto_select(self.mouth_open_combo, self.MOUTH_OPEN_WORDS)

    def _auto_select(self, combo: QComboBox, words: tuple[str, ...]) -> None:
        for index in range(1, combo.count()):
            text = combo.itemText(index).casefold()
            if any(word.casefold() in text for word in words):
                combo.setCurrentIndex(index)
                return

    def _on_layer_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating_tree:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        state = item.checkState(0) == Qt.CheckState.Checked
        if key in self.base_visibility:
            self.base_visibility[key] = state
        self._updating_tree = True
        for index in range(item.childCount()):
            self._set_subtree(item.child(index), state)
        self._updating_tree = False
        self._apply_visibility()

    def _set_subtree(self, item: QTreeWidgetItem, visible: bool) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key in self.base_visibility:
            self.base_visibility[key] = visible
        item.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
        for index in range(item.childCount()):
            self._set_subtree(item.child(index), visible)

    def _sync_tree(self) -> None:
        self._updating_tree = True

        def visit(item: QTreeWidgetItem) -> None:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key in self.base_visibility:
                item.setCheckState(0, Qt.CheckState.Checked if self.base_visibility[key] else Qt.CheckState.Unchecked)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.layer_tree.topLevelItemCount()):
            visit(self.layer_tree.topLevelItem(index))
        self._updating_tree = False

    def _selected_key(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        return str(value) if value else None

    def _effective_visibility(self) -> dict[str, bool]:
        roles = {key: self._selected_key(combo) for key, combo in self._role_combos().items()}
        mouth, lipsync = self._mouth_state_for_render()
        return effective_visibility(self.base_visibility, roles, self.expression_layers,
                                    self.blink_active, mouth, lipsync)

    def _voice_open_for_mode(self, mode):
        if mode == "open":
            return True
        if mode == "flap":
            return self._voice_mouth_open
        return self._voice_frozen_open

    def _mouth_state_for_render(self):
        if self._voice_playing:
            mode = self.settings_panel.voice_mouth_mode.currentData()
            return self._voice_open_for_mode(mode), True
        return self.mouth_open, self.lipsync_check.isChecked()

    def _on_voice_playback_changed(self, playing):
        playing = bool(playing)
        if not playing:
            self._idle_voice_id = None
        if playing == self._voice_playing:
            return
        if playing:
            mouth, lipsync = self._mouth_state_for_render()
            self._voice_frozen_open = bool(mouth and lipsync and self._selected_key(self.mouth_open_combo))
            self._voice_mouth_open = True
            self._voice_mouth_deadline = time.monotonic() + .12
        else:
            self.mouth_deadline = time.monotonic() + (.12 if self.mouth_open else .16)
        self._voice_playing = playing
        self._render()

    def _apply_visibility(self) -> None:
        self._render()

    def _render(self) -> None:
        if self.psd is None or self._loading or self.bulk_active:
            return
        if self.cache_manager_active:
            self._manager_render_pending = True
            return
        state = tuple(sorted(self._effective_visibility().items()))
        if self._reaction_wait_state is not None:
            # Audio may end or change the mouth phase while a reaction frame
            # is being rendered. Wait for the latest valid frame in that case.
            self._reaction_wait_state = state
        self.pending_render = state

    def _remember_frame(self, state, image):
        cost = image.width * image.height * 4
        while self.frame_cache and self.cache_bytes + cost > 128 * 1024 * 1024:
            _, old = self.frame_cache.popitem(last=False)
            self.cache_bytes -= old.width * old.height * 4
        self.frame_cache[state] = image
        self.cache_bytes += cost

    def _persist_frame(self, state, image, strict):
        if self.document_cache is None:
            if strict:
                raise OSError("PSDのキャッシュ保存先がありません")
            return
        try:
            self.document_cache.write(state, image)
        except (OSError, ValueError) as exc:
            self.document_cache.last_error = str(exc)
            if strict:
                raise

    def _compose_frame(self, state, strict_disk=False, controlled=None):
        with perf.session("frame", self.psd_path):
            with perf.frame(state_digest(state)) as record:
                snapshot = frozenset(self.expression_layers) if controlled is None else frozenset(controlled)
                return self._compose_frame_measured(state, strict_disk, record, snapshot)

    def _compose_frame_measured(self, state, strict_disk, record, controlled):
        cached = self.frame_cache.get(state)
        if cached is not None:
            record["source"] = "memory_cache"
            perf.count("frame_memory_cache")
            self.frame_cache.move_to_end(state)
            if strict_disk or (self.document_cache is not None and not self.document_cache.frame_path(state).is_file()):
                self._persist_frame(state, cached, strict_disk)
            return cached, 0.0
        if self.document_cache is not None:
            cached = self.document_cache.read(state)
            if cached is not None:
                record["source"] = "disk_cache"
                perf.count("frame_disk_cache")
                self._remember_frame(state, cached)
                return cached, 0.0
        started = time.monotonic()
        if self.region_renderer is None or self.region_renderer.psd is not self.psd:
            if self.region_renderer is not None:
                self.region_renderer.clear()
            self.region_renderer = RegionRenderer(self.psd, self.layers)
        image, rendering = self.region_renderer.render(state, controlled)
        record.update(rendering)
        with perf.measure("resize"):
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        self._remember_frame(state, image)
        self._persist_frame(state, image, strict_disk)
        record["source"] = "new_composite"
        perf.count("frame_new_composite")
        return image, time.monotonic() - started

    def _cache_spec(self, mode):
        base = dict(self.base_visibility)
        outfits = [base]
        if mode in ("all", "outfits"):
            for saved in self.presets.values():
                outfit = dict(base)
                outfit.update(saved)
                outfits.append(outfit)
        motions = [self._reaction_return_motion or self._motion_snapshot()]
        if mode in ("all", "expressions"):
            motions.extend(self.expression_presets.values())
        motions = [{"roles": dict(motion.get("roles", {})), "lipsync": bool(motion.get("lipsync"))}
                   for motion in motions]
        controlled = set(self.expression_layers)
        for motion in motions:
            controlled.update(key for key in motion["roles"].values() if key)
        return {"outfits": outfits, "motions": motions, "controlled": controlled}

    def _request_bulk_cache(self, mode):
        if self.psd is None or self._loading:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        if self.bulk_active or self.cache_manager_active:
            return
        descriptions = {
            "all": "登録済みの服装×表情と、目・口の開閉差分を生成します（現在の状態も含む）。",
            "outfits": "登録済みの服装と現在の表情について、目・口の開閉差分を生成します（現在の服装も含む）。",
            "expressions": "現在の服装と登録済みの表情について、目・口の開閉差分を生成します（現在の表情も含む）。",
        }
        if not confirm_generation(self, descriptions[mode]):
            return
        self._cancel_reaction(restore=True)
        self.bulk_active = True
        self.pending_render = None
        self.warm_queue.clear()
        self._bulk_progress = Queue()
        self._bulk_pending = self._cache_spec(mode)
        self.bulk_dialog = PrecacheProgressDialog(self)
        self.bulk_dialog.finished.connect(self._bulk_dialog_finished)
        self.bulk_dialog.open_centered()

    def _drain_bulk_progress(self):
        if self._bulk_progress is None or self.bulk_dialog is None:
            return
        latest = None
        while True:
            try:
                latest = self._bulk_progress.get_nowait()
            except Empty:
                break
        if latest is not None:
            self.bulk_dialog.report(latest)

    def _bulk_dialog_finished(self, _result):
        dialog = self.bulk_dialog
        self.bulk_dialog = None
        self.bulk_active = False
        self._bulk_pending = None
        self._bulk_progress = None
        if dialog is not None:
            dialog.deleteLater()
        self.blink_deadline = time.monotonic() + self._blink_interval()
        self.mouth_deadline = time.monotonic() + .16
        self._render()

    def _request_cache_delete(self):
        if self.bulk_active or self._loading or self.cache_manager_active:
            return
        self._manager_render_pending = self.pending_render is not None
        self.cache_manager_active = True
        self._cache_manager_pending = True
        self.pending_render = None
        self.warm_queue.clear()

    def _open_cache_manager(self):
        self.cache_manager = CacheDeleteDialog(self.cache_registry, self)
        self.cache_manager.deleted.connect(self._on_caches_deleted)
        self.cache_manager.finished.connect(self._cache_manager_finished)
        self.cache_manager.open()

    def _on_caches_deleted(self, identifiers):
        if self.document_cache is not None and self.document_cache.document_id in identifiers:
            self.frame_cache.clear()
            self.cache_bytes = 0
            if self.region_renderer is not None:
                self.region_renderer.clear()

    def _cache_manager_finished(self, _result):
        dialog = self.cache_manager
        self.cache_manager = None
        self.cache_manager_active = False
        if dialog is not None:
            dialog.deleteLater()
        self.blink_deadline = time.monotonic() + self._blink_interval()
        self.mouth_deadline = time.monotonic() + .16
        if self._manager_render_pending:
            self._manager_render_pending = False
            self._render()

    def _set_progress(self, text, done=None, total=None):
        self.progress_label.setText(text)
        if total is None:
            # psd-tools has no per-layer progress callback for one composite.
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(done)

    def _prepare_current_cache(self):
        if self.bulk_active or self.cache_manager_active:
            return
        if self.job is not None or self.warm_queue:
            self.statusBar().showMessage("現在の処理が完了してからキャッシュを準備してください")
            return
        if self.psd is not None and not self._loading:
            self._start_warmup()

    def _start_warmup(self):
        current = tuple(sorted(self._effective_visibility().items()))
        states = [current]
        for state in animation_states(self.base_visibility, self._motion_snapshot(), self.expression_layers):
            if state not in states:
                states.append(state)
        self.pending_render = None
        self.warm_queue = states
        self.warm_total = len(states)
        self.warm_done = 0
        self._set_progress(f"キャッシュ準備 0/{self.warm_total}", 0, self.warm_total)

    def _poll_job(self) -> None:
        self._drain_bulk_progress()
        if self.job is not None:
            kind, context, future = self.job
            if not future.done():
                return
            self.job = None
            try:
                result = future.result()
                if kind == "load":
                    self._loading = False
                    self.open_button.setEnabled(True)
                    self.tabs.setEnabled(True)
                    self._finish_load(context, *result)
                elif kind == "bulk":
                    self._drain_bulk_progress()
                    self.bulk_dialog.complete(result)
                    self._set_progress("事前キャッシュ生成完了", 1, 1)
                else:
                    image, elapsed = result
                    current = tuple(sorted(self._effective_visibility().items()))
                    if context == current:
                        self._pixmap = _pil_to_pixmap(image)
                        self.preview.set_pixmap(self._pixmap)
                        self.mascot_window.set_pixmap(self._pixmap)
                        self._reaction_frame_shown(context)
                    if kind == "warm":
                        self.warm_done += 1
                        self._set_progress(
                            f"キャッシュ準備 {self.warm_done}/{self.warm_total}",
                            self.warm_done, self.warm_total)
                        if not self.warm_queue:
                            self._set_progress("キャッシュ準備完了", 1, 1)
                    else:
                        self._set_progress(f"更新完了 {elapsed:.2f}秒", 1, 1)
                    if self.document_cache is not None and self.document_cache.last_error:
                        self.statusBar().showMessage(f"キャッシュを保存できませんでした: {self.document_cache.last_error}")
            except Exception as exc:
                if self.bulk_active and self.bulk_dialog is not None:
                    self._bulk_pending = None
                    self.bulk_dialog.fail(exc)
                self._loading = False
                self._restoring_settings = False
                self._cancel_reaction(restore=True)
                self.warm_queue.clear()
                self.open_button.setEnabled(True)
                self.tabs.setEnabled(True)
                self._set_progress("処理失敗", 0, 1)
                self.statusBar().showMessage(f"処理に失敗しました: {exc}")
        if self.job is None:
            if self._bulk_pending is not None:
                spec = self._bulk_pending
                self._bulk_pending = None
                self.job = ("bulk", None, self.executor.submit(
                    generate_plan, spec, self.document_cache,
                    lambda state: self._compose_frame(state, strict_disk=True, controlled=spec["controlled"]), self._bulk_progress.put))
                return
            if self._cache_manager_pending:
                self._cache_manager_pending = False
                self._open_cache_manager()
                return
            if self.bulk_active or self.cache_manager_active:
                return
            if self.pending_render is not None:
                state = self.pending_render
                self.pending_render = None
                self._set_progress("表示を更新中…")
                self.job = ("render", state, self.executor.submit(self._compose_frame, state, False, frozenset(self.expression_layers)))
            elif self.warm_queue:
                state = self.warm_queue.pop(0)
                self._set_progress(
                    f"キャッシュ準備 {self.warm_done}/{self.warm_total}",
                    self.warm_done, self.warm_total)
                self.job = ("warm", state, self.executor.submit(self._compose_frame, state, False, frozenset(self.expression_layers)))

    def save_preset(self) -> None:
        if self.psd is None:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        name = self.preset_name.text().strip()
        if not name:
            QMessageBox.information(self, "服装名", "保存する服装名を入力してください。")
            return
        self.presets[name] = dict(self.base_visibility)
        self._refresh_preset_list(select=name)
        self._save_data()

    def apply_selected_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is not None:
            self._apply_outfit(item.text())

    def _apply_outfit(self, name):
        if self.psd is None or self._loading or self.bulk_active or self.cache_manager_active:
            return
        state = self.presets.get(name)
        if state is None:
            return
        self._on_user_activity()
        self.base_visibility.update(state)
        self._sync_tree()
        self._apply_visibility()
        self.preset_name.setText(name)
        matches = self.preset_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.preset_list.setCurrentItem(matches[0])
        self._save_data()

    def _apply_menu_outfit(self, name):
        if name in self.outfit_menu_names:
            self._apply_outfit(name)

    def _show_outfit_menu_check(self):
        item = self.preset_list.currentItem()
        name = item.text() if item is not None else ""
        blocked = self.outfit_menu_check.blockSignals(True)
        self.outfit_menu_check.setEnabled(name in self.presets)
        self.outfit_menu_check.setChecked(name in self.outfit_menu_names)
        self.outfit_menu_check.blockSignals(blocked)

    def _set_outfit_menu_check(self, enabled):
        item = self.preset_list.currentItem()
        if item is None or item.text() not in self.presets:
            return
        if enabled:
            self.outfit_menu_names.add(item.text())
        else:
            self.outfit_menu_names.discard(item.text())
        self._sync_outfit_menu()
        self._save_data()

    def _sync_outfit_menu(self):
        self.mascot_window.set_outfit_presets(
            [name for name in self.presets if name in self.outfit_menu_names])

    def delete_selected_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        self.presets.pop(item.text(), None)
        self.outfit_menu_names.discard(item.text())
        self._refresh_preset_list()
        self._save_data()

    def _refresh_preset_list(self, select: str | None = None) -> None:
        self.preset_list.clear()
        self.preset_list.addItems(list(self.presets))
        if select:
            matches = self.preset_list.findItems(select, Qt.MatchFlag.MatchExactly)
            if matches:
                self.preset_list.setCurrentItem(matches[0])
        self._show_outfit_menu_check()
        self._sync_outfit_menu()

    def _on_role_changed(self, _index: int) -> None:
        if self._restoring_settings:
            return
        if self.psd is not None:
            self._cancel_reaction(restore=False)
            self._on_user_activity()
            self._track_motion_layers()
            self.blink_active = False
            self.blink_deadline = time.monotonic() + self._blink_interval()
            self._apply_visibility()
            self._save_data()

    def _on_lipsync_toggled(self, enabled: bool) -> None:
        if self._restoring_settings:
            return
        self._cancel_reaction(restore=False)
        self._on_user_activity()
        self.mouth_open = False
        self.mouth_deadline = time.monotonic() + 0.1
        self._apply_visibility()
        if enabled and not self._selected_key(self.mouth_open_combo):
            self.statusBar().showMessage("口パク用の開き口レイヤーを割り当ててください")
        self._save_data()

    def trigger_blink(self) -> None:
        if not self._selected_key(self.eye_closed_combo):
            self.statusBar().showMessage("動きタブで閉眼レイヤーを割り当ててください")
            return
        self.blink_active = True
        self.blink_end = time.monotonic() + 0.13
        self._apply_visibility()

    def _tick(self) -> None:
        if self.bulk_active or self.cache_manager_active or self._loading or self.job is not None or self.pending_render is not None or self.warm_queue:
            return
        now = time.monotonic()
        changed = False
        if self._selected_key(self.eye_closed_combo):
            if not self.blink_active and now >= self.blink_deadline:
                self.blink_active = True
                self.blink_end = now + 0.13
                changed = True
            elif self.blink_active and now >= self.blink_end:
                self.blink_active = False
                self.blink_deadline = now + self._blink_interval()
                changed = True
        if self._voice_playing:
            if (self.settings_panel.voice_mouth_mode.currentData() == "flap"
                    and self._selected_key(self.mouth_open_combo)
                    and now >= self._voice_mouth_deadline):
                self._voice_mouth_open = not self._voice_mouth_open
                self._voice_mouth_deadline = now + (.12 if self._voice_mouth_open else .16)
                changed = True
        elif self.lipsync_check.isChecked() and self._selected_key(self.mouth_open_combo) and now >= self.mouth_deadline:
            self.mouth_open = not self.mouth_open
            self.mouth_deadline = now + (0.12 if self.mouth_open else 0.16)
            changed = True
        if changed:
            self._apply_visibility()

    def toggle_stage(self) -> None:
        self._on_user_activity()
        if self.psd is None:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        if self.mascot_window.isVisible():
            self.mascot_window.hide()
            self.stage_button.setText("デスクトップに表示")
        else:
            if self._pixmap is not None:
                self.mascot_window.set_pixmap(self._pixmap)
            self.mascot_window.show()
            self.stage_button.setText("表示を閉じる")

    def _set_topmost(self, enabled: bool) -> None:
        if bool(self.mascot_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) == enabled:
            return
        visible = self.mascot_window.isVisible()
        self.mascot_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if visible:
            self.mascot_window.show()

    def _blink_interval(self) -> float:
        return self.settings_panel.blink_interval.value()

    def _on_app_settings_changed(self) -> None:
        self._apply_app_settings()
        self.settings_save_timer.start()

    def _apply_app_settings(self) -> None:
        values = self.settings_panel.values()
        perf.set_enabled(values["log_enabled"])
        mode = values["voice_mouth_mode"]
        if mode != self._last_voice_mouth_mode:
            if self._voice_playing:
                if mode == "none":
                    self._voice_frozen_open = bool(self._voice_open_for_mode(self._last_voice_mouth_mode)
                                                   and self._selected_key(self.mouth_open_combo))
                elif mode == "flap":
                    self._voice_mouth_open = True
                    self._voice_mouth_deadline = time.monotonic() + .12
            self._last_voice_mouth_mode = mode
            if self._voice_playing:
                self._render()
        self.mascot_window.set_scale_percent(values["desktop_scale"])
        self._set_topmost(values["topmost"])
        if self._last_blink_interval != values["blink_interval"]:
            self._last_blink_interval = values["blink_interval"]
            if not self.blink_active:
                self.blink_deadline = time.monotonic() + self._blink_interval()
        if self._last_font_scale != values["font_scale"]:
            self._last_font_scale = values["font_scale"]
            font = QFont(self._base_ui_font)
            points = font.pointSizeF()
            if points <= 0:
                points = 9.0
            font.setPointSizeF(points * values["font_scale"] / 100)
            QApplication.instance().setFont(font)

    def _app_settings_path(self) -> Path:
        base = settings_directory()
        return base / "app-settings.json"

    def _load_app_settings(self) -> None:
        path = self._read_settings_path(self._app_settings_path())
        try:
            if path.exists():
                values = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(values, dict):
                    self.settings_panel.restore(values)
                    last = values.get("last_psd_path")
                    self.last_psd_path = last if isinstance(last, str) else None
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage(f"アプリ設定を読み込めませんでした: {exc}")
        self._apply_app_settings()

    def _save_app_settings(self) -> None:
        path = self._app_settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({**self.settings_panel.values(), "last_psd_path": getattr(self, "last_psd_path", None)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            self.statusBar().showMessage(f"アプリ設定を保存できませんでした: {exc}")

    def _data_path(self) -> Path | None:
        if self.psd_path is None:
            return None
        base = settings_directory()
        import hashlib

        digest = hashlib.sha256(str(self.psd_path).casefold().encode("utf-8")).hexdigest()[:20]
        return base / f"{digest}.json"

    @staticmethod
    def _read_settings_path(path):
        # Prefer the unversioned file. Copy legacy data, never move or delete it.
        if path.exists():
            return path
        versions = ("v0.4.1", "v0.4.0", "v0.3.9", "v0.3.8", "v0.3.6", "v0.3.5", "v0.3.4", "v0.3.3", "v0.3.2", "v0.3.1", "v0.3.0", "v0.2.2")
        root = path.parent.parent if path.parent.name == "v0.4.1" else path.parent
        for version in versions:
            legacy = root / version / path.name
            if legacy != path and legacy.is_file():
                try:
                    # Validate before migration; keep the original on any error.
                    raw = legacy.read_bytes()
                    if not isinstance(json.loads(raw.decode("utf-8")), dict):
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".migration.tmp")
                    temporary.write_bytes(raw)
                    temporary.replace(path)
                    return path
                except (OSError, ValueError, TypeError):
                    return legacy
        return path

    def restore_last_psd(self):
        last = getattr(self, "last_psd_path", None)
        if not last or self.psd is not None or self.job is not None or self._closing:
            return
        path = Path(last)
        if not path.is_file():
            QMessageBox.warning(self, "前回のPSDが見つかりません",
                                f"前回使用したPSDが見つかりません。\n{path}\n\n「PSDを開く」からファイルを選び直してください。")
            return
        self.load_psd(path)

    def _reaction_tab_changed(self, _index):
        self.preview.set_editing(self.tabs.currentWidget() is self.reaction_panel)

    def _refresh_reactions(self, selected=None):
        self.reaction_panel.set_expressions(self.expression_presets)
        self.idle_panel.set_expressions(self.expression_presets)
        self.reaction_panel.set_voices(self.voice_controller.presets)
        self.reaction_panel.set_regions(self.reactions, selected)
        self.preview.set_reactions(self.reactions, self.reaction_panel.selected_id())
        self.mascot_window.set_reactions(self.reactions)
        self._reaction_tab_changed(0)

    def _add_reaction(self):
        if self.psd is None:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        region = {
            "id": uuid4().hex, "name": f"当たり判定{len(self.reactions)+1}",
            "rect": [.25, .25, .5, .5],
            "expression": next(iter(self.expression_presets), ""), "voice": "", "duration": 2.0,
        }
        self.reactions.append(region)
        self._refresh_reactions(region["id"])
        self._save_data()

    def _delete_reaction(self, identifier):
        self.reactions = [r for r in self.reactions if r["id"] != identifier]
        self._refresh_reactions("")
        self._save_data()

    def _edit_reaction(self, identifier, updates):
        region = next((r for r in self.reactions if r["id"] == identifier), None)
        if region is not None:
            region.update(updates)
            self._refresh_reactions(identifier)
            self._save_data()

    def _edit_reaction_geometry(self, identifier, rect):
        region = next((r for r in self.reactions if r["id"] == identifier), None)
        if region is not None:
            region["rect"] = list(rect)
            self.reaction_panel.show_geometry(rect)
            self.mascot_window.update()
            self.reaction_save_timer.start()

    def _refresh_idle(self, selected=None):
        self.idle_panel.set_expressions(self.expression_presets)
        self.idle_panel.set_voices(self.voice_controller.presets)
        self.idle_panel.set_state(self.idle_settings, selected)

    def _add_idle(self):
        if self.psd is None:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        action = {"id": uuid4().hex, "name": f"放置アクション{len(self.idle_settings['actions'])+1}",
                  "enabled": True, "expression": next(iter(self.expression_presets), ""),
                  "voice": "", "duration": 2.0}
        self.idle_settings["actions"].append(action)
        self._refresh_idle(action["id"])
        self.idle_scheduler.reset()
        self._save_data()

    def _delete_idle(self, identifier):
        if self._idle_active_id == identifier:
            self._stop_idle_action()
        self.idle_settings["actions"] = [a for a in self.idle_settings["actions"] if a["id"] != identifier]
        self._refresh_idle("")
        self.idle_scheduler.reset()
        self._save_data()

    def _edit_idle(self, identifier, updates):
        action = next((a for a in self.idle_settings["actions"] if a["id"] == identifier), None)
        if action is not None:
            if self._idle_active_id == identifier:
                self._stop_idle_action()
            action.update(updates)
            self.idle_settings = sanitize_idle(self.idle_settings)
            self._refresh_idle(identifier)
            self.idle_scheduler.reset()
            self._save_data()

    def _edit_idle_options(self, options):
        self.idle_settings.update(options)
        self.idle_settings = sanitize_idle(self.idle_settings)
        if not self.idle_settings["enabled"]:
            self._stop_idle_action()
        self.idle_scheduler.reset()
        self._save_data()

    def _move_idle(self, identifier, step):
        actions = self.idle_settings["actions"]
        index = next((i for i, a in enumerate(actions) if a["id"] == identifier), -1)
        moved = moved_list(actions, index, step)
        if moved is not None:
            self.idle_settings["actions"] = moved
            self._refresh_idle(identifier)
            self._save_data()

    def _idle_action_valid(self, action):
        voice = next((p for p in self.voice_controller.presets if p["id"] == action["voice"]), None)
        return (action["expression"] in self.expression_presets or
                (voice is not None and (self.voice_controller.library.directory / voice["file"]).is_file()))

    def _on_user_activity(self):
        if self._closing:
            return
        self._stop_idle_action()
        self.idle_scheduler.arm(self.idle_settings["min_seconds"], self.idle_settings["max_seconds"])

    def _stop_idle_action(self):
        voice_id = self._idle_voice_id
        self._idle_voice_id = None
        if self._action_source == "idle":
            self._cancel_reaction(restore=True)
        if voice_id and self.voice_controller._playing_id == voice_id:
            self.voice_controller.stop()

    def _advance_idle(self):
        if self._closing:
            return
        actions = [a for a in self.idle_settings["actions"] if a["enabled"] and self._idle_action_valid(a)]
        reason = ""
        if not self.idle_settings["enabled"]:
            reason = "放置アクションは無効です"
        elif self.psd is None:
            reason = "PSDを開いてください"
        elif not actions:
            reason = "有効な表情またはセリフを設定したアクションを追加してください"
        elif self._idle_active_id is not None:
            reason = "放置アクション実行中"
        elif not self.mascot_window.isVisible() or self.mascot_window.isMinimized():
            reason = "デスクトップ表示中に自動実行します"
        elif self._loading or self.bulk_active or self.cache_manager_active or self.voice_panel._busy or QApplication.activeModalWidget() is not None:
            reason = "処理・ダイアログ表示中は待機します"
        elif self._reaction_return_motion is not None or self._reaction_wait_state is not None:
            reason = "手動リアクションの終了を待っています"
        elif self._voice_playing or self.voice_controller._playing_id is not None:
            reason = "音声再生の終了を待っています"
        ready = self.job is None and self.pending_render is None and not self.warm_queue
        due = self.idle_scheduler.poll(self.idle_settings["min_seconds"], self.idle_settings["max_seconds"],
                                       paused=bool(reason), ready=ready)
        if reason:
            self.idle_panel.status_label.setText(reason)
        elif due:
            self._trigger_idle_action(self.idle_scheduler.choose(actions)["id"], automatic=True)
        elif self.idle_scheduler.deadline is not None:
            left = max(0, self.idle_scheduler.deadline - self.idle_scheduler.clock())
            self.idle_panel.status_label.setText(f"次の放置アクションまで {left:.1f} 秒")

    def _trigger_idle_action(self, identifier, automatic=False):
        action = next((a for a in self.idle_settings["actions"] if a["id"] == identifier), None)
        if action is None or self.psd is None or self._loading or self.bulk_active or self.cache_manager_active:
            return
        if not self._idle_action_valid(action):
            self.statusBar().showMessage("放置アクションに有効な表情またはセリフを指定してください")
            return
        if automatic and (not self.idle_settings["enabled"] or not action["enabled"]
                          or self._reaction_return_motion is not None or self._voice_playing
                          or self.voice_controller._playing_id is not None):
            return
        self._stop_idle_action()
        self._cancel_reaction(restore=True)
        self.idle_scheduler.reset()
        self._begin_temporary_action(action, "idle")

    def _tap_reaction(self, x, y):
        self._on_user_activity()
        if self._loading:
            return
        region = find_reaction(self.reactions, x, y)
        if region is not None:
            self._trigger_reaction(region["id"])

    def _play_reaction_voice(self, identifier):
        if not identifier:
            return
        if any(preset["id"] == identifier for preset in self.voice_controller.presets):
            self.voice_controller.play(identifier)
            if self._action_source == "idle" and self.voice_controller._playing_id == identifier:
                self._idle_voice_id = identifier
        else:
            label = "放置" if self._action_source == "idle" else "リアクション"
            self.statusBar().showMessage(f"指定されたセリフが見つかりません。{label}設定を確認してください")

    def _trigger_reaction(self, identifier):
        region = next((r for r in self.reactions if r["id"] == identifier), None)
        if region is None or self.psd is None or self._loading or self.bulk_active or self.cache_manager_active:
            return
        self._stop_idle_action()
        self.idle_scheduler.reset()
        self._begin_temporary_action(region, "reaction")

    def _begin_temporary_action(self, region, source):
        voice_id = region.get("voice", "")
        snapshot = self.expression_presets.get(region["expression"])
        if source == "idle":
            self._action_source = "idle"
            self._idle_active_id = region["id"]
        if snapshot is None:
            if source == "idle":
                self._idle_hold_until = time.monotonic() + region["duration"]
            if voice_id:
                self._reaction_pending_voice = None
                self._play_reaction_voice(voice_id)
            else:
                self.statusBar().showMessage("リアクションに有効な表情またはセリフを指定してください")
            return
        self._action_source = source
        if self._reaction_return_motion is None:
            self._reaction_return_motion = self._motion_snapshot()
        self._track_motion_layers()
        self._restore_motion(snapshot)
        self._reaction_duration = region["duration"]
        self._reaction_pending_voice = voice_id or None
        self._reaction_expires_at = None
        self._reaction_wait_state = tuple(sorted(self._effective_visibility().items()))
        self._render()
        label = "放置アクション" if source == "idle" else "リアクション"
        self.statusBar().showMessage(f"{label}「{region['name']}」を準備中…")

    def _reaction_frame_shown(self, state):
        if self._reaction_wait_state is not None and state == self._reaction_wait_state:
            self._reaction_wait_state = None
            self._reaction_expires_at = time.monotonic() + self._reaction_duration
            label = "放置アクション" if self._action_source == "idle" else "リアクション"
            self.statusBar().showMessage(f"{label}表示中（{self._reaction_duration:.1f}秒）")
            voice_id = self._reaction_pending_voice
            self._reaction_pending_voice = None
            self._play_reaction_voice(voice_id)

    def _advance_reaction(self):
        now = time.monotonic()
        if ((self._reaction_expires_at is not None and now >= self._reaction_expires_at)
                or (self._idle_hold_until is not None and now >= self._idle_hold_until)):
            label = "放置アクション" if self._action_source == "idle" else "リアクション"
            self._cancel_reaction(restore=True)
            self.statusBar().showMessage(f"{label}終了：元の表情に戻しました")

    def _cancel_reaction(self, restore=False):
        if self._action_source == "idle":
            self._idle_active_id = None
            self._idle_hold_until = None
            self.idle_scheduler.reset()
        self._action_source = None
        snapshot = self._reaction_return_motion
        self._reaction_return_motion = None
        self._reaction_pending_voice = None
        self._reaction_wait_state = None
        self._reaction_expires_at = None
        if restore and snapshot is not None:
            self._restore_motion(snapshot)
            self._render()

    def _sync_voice_menu(self, _selected=""):
        self.mascot_window.set_voice_presets(self.voice_controller.presets)
        self.reaction_panel.set_voices(self.voice_controller.presets)
        self.idle_panel.set_voices(self.voice_controller.presets)

    def _move_outfit(self, step):
        item = self.preset_list.currentItem()
        if item is None:
            return
        name = item.text()
        values = moved_mapping(self.presets, name, step)
        if values is not None:
            self.presets = values
            self._refresh_preset_list(select=name)
            self._save_data()
    def _move_expression(self, name, step):
        values = moved_mapping(self.expression_presets, name, step)
        if values is not None:
            self.expression_presets = values
            self.expression_panel.set_names(self.expression_presets, name)
            self.reaction_panel.set_expressions(self.expression_presets)
            self.idle_panel.set_expressions(self.expression_presets)
            self._save_data()
    def _move_reaction(self, identifier, step):
        index = next((i for i, region in enumerate(self.reactions) if region["id"] == identifier), -1)
        values = moved_list(self.reactions, index, step)
        if values is not None:
            self.reactions = values
            self._refresh_reactions(identifier)
            self._save_data()
    def _role_combos(self):
        return {
            "brow": self.brow_combo,
            "eye_open": self.eye_open_combo,
            "eye_closed": self.eye_closed_combo,
            "mouth_closed": self.mouth_closed_combo,
            "mouth_open": self.mouth_open_combo,
            "accessory": self.accessory_combo,
        }

    def _motion_snapshot(self) -> dict[str, Any]:
        return {
            "roles": {key: self._selected_key(combo) for key, combo in self._role_combos().items()},
            "lipsync": self.lipsync_check.isChecked(),
        }

    def _track_motion_layers(self) -> None:
        self.expression_layers.update(
            key for combo in self._role_combos().values()
            if (key := self._selected_key(combo))
        )

    def _restore_motion(self, snapshot: dict[str, Any]) -> None:
        roles = snapshot.get("roles", {})
        for key, combo in self._role_combos().items():
            combo.blockSignals(True)
            index = combo.findData(roles.get(key) or "")
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.lipsync_check.blockSignals(True)
        self.lipsync_check.setChecked(bool(snapshot.get("lipsync", False)))
        self.lipsync_check.blockSignals(False)
        self._track_motion_layers()
        self.blink_active = False
        self.mouth_open = False
        self.blink_deadline = time.monotonic() + self._blink_interval()
        self.mouth_deadline = time.monotonic() + 0.1

    def save_expression(self, name: str) -> None:
        if self.psd is None:
            QMessageBox.information(self, "PSD未読込", "先にPSDを開いてください。")
            return
        if not name:
            QMessageBox.information(self, "表情名", "保存する表情名を入力してください。")
            return
        self.expression_presets[name] = self._motion_snapshot()
        self.expression_panel.set_names(self.expression_presets, name)
        self.reaction_panel.set_expressions(self.expression_presets)
        self.idle_panel.set_expressions(self.expression_presets)
        self._save_data()
        self.statusBar().showMessage(f"表情「{name}」を保存しました")

    def apply_expression(self, name: str) -> None:
        snapshot = self.expression_presets.get(name)
        if snapshot is None:
            return
        self._on_user_activity()
        self._cancel_reaction(restore=False)
        self._track_motion_layers()
        self._restore_motion(snapshot)
        self._apply_visibility()
        self._save_data()
        self.statusBar().showMessage(f"表情「{name}」を呼び出しました")

    def delete_expression(self, name: str) -> None:
        self.expression_presets.pop(name, None)
        self.expression_panel.set_names(self.expression_presets)
        self.reaction_panel.set_expressions(self.expression_presets)
        self.idle_panel.set_expressions(self.expression_presets)
        self._save_data()

    def _load_data(self) -> None:
        data_path = self._data_path()
        if data_path is not None:
            data_path = self._read_settings_path(data_path)
        if data_path is not None and data_path.exists():
            try:
                payload = json.loads(data_path.read_text(encoding="utf-8"))
                self.presets = {
                    str(name): {str(k): bool(v) for k, v in values.items() if k in self.layers}
                    for name, values in payload.get("presets", {}).items()
                }
                self.presets = restored_mapping(self.presets, payload.get("preset_order"))
                names = payload.get("outfit_menu", [])
                self.outfit_menu_names = {
                    name for name in names if isinstance(name, str) and name in self.presets
                } if isinstance(names, list) else set()
                for key, value in payload.get("visibility", {}).items():
                    if key in self.base_visibility:
                        self.base_visibility[key] = bool(value)
                self.expression_layers = {
                    key for key in payload.get("expression_layers", []) if key in self.layers
                }
                self.expression_presets = {}
                for name, state in payload.get("expression_presets", {}).items():
                    self.expression_presets[str(name)] = {
                        "roles": {
                            key: value if value in self.layers else None
                            for key, value in state.get("roles", {}).items()
                            if key in self._role_combos()
                        },
                        "lipsync": bool(state.get("lipsync", False)),
                    }
                self.expression_presets = restored_mapping(
                    self.expression_presets, payload.get("expression_order"))
                for state in self.expression_presets.values():
                    self.expression_layers.update(value for value in state["roles"].values() if value)
                self._restore_motion(payload.get("motion", {"roles": payload.get("roles", {})}))
                self._sync_tree()
                self.reactions = sanitize_reactions(payload.get("reactions", []))
                self.idle_settings = sanitize_idle(payload.get("idle", {}))
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self.statusBar().showMessage(f"設定を読み込めませんでした: {exc}")
        self._refresh_preset_list()
        self.expression_panel.set_names(self.expression_presets)
        self.blink_deadline = time.monotonic() + self._blink_interval()
        self._apply_visibility()

    def _save_data(self) -> None:
        if self._restoring_settings:
            return
        data_path = self._data_path()
        if data_path is None:
            return
        payload = {
            "schema_version": 7,
            "presets": self.presets,
            "preset_order": list(self.presets),
            "outfit_menu": [name for name in self.presets if name in self.outfit_menu_names],
            "visibility": self.base_visibility,
            "expression_presets": self.expression_presets,
            "expression_order": list(self.expression_presets),
            "expression_layers": sorted(self.expression_layers),
            "motion": self._reaction_return_motion or self._motion_snapshot(),
            "reactions": self.reactions,
            "idle": self.idle_settings,
        }
        try:
            data_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = data_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(data_path)
        except OSError as exc:
            self.statusBar().showMessage(f"設定を保存できませんでした: {exc}")

    def closeEvent(self, event: Any) -> None:
        if self.bulk_active or self.cache_manager_active:
            event.ignore()
            return
        self._closing = True
        self.tray_icon.hide()
        self.idle_timer.stop()
        QApplication.instance().removeEventFilter(self.idle_activity_filter)
        self.voice_controller.close()
        self.timer.stop()
        self.job_timer.stop()
        self.reaction_timer.stop()
        self.reaction_save_timer.stop()
        self.settings_save_timer.stop()
        self._save_app_settings()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self._save_data()
        self.mascot_window.close()
        super().closeEvent(event)


def main() -> None:
    set_windows_app_id()
    app = QApplication(sys.argv)
    configure_application(app)
    window = MascotApp()
    window.show()
    QTimer.singleShot(0, window.restore_last_psd)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
