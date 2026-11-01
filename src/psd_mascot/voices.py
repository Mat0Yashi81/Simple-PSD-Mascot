"""音声ライブラリ、非同期取り込み、音声だけの再生と設定画面。"""

import hashlib
import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from .ordering import ReorderButtons, moved_list

# Use the bundled FFmpeg backend for consistent mp3/wav/ogg decoding.
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget, QSizePolicy,
)

SUPPORTED_AUDIO = {".mp3", ".wav", ".ogg"}


class VoiceLibrary:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.manifest = self.directory / "presets.json"

    def load(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.manifest.exists():
            return []
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        values = payload.get("presets", [])
        if not isinstance(values, list):
            raise ValueError("音声プリセットの保存形式が正しくありません")
        result, used = [], set()
        for value in values:
            if not isinstance(value, dict):
                continue
            filename = str(value.get("file", ""))
            if not filename or Path(filename).name != filename or "\\" in filename or "/" in filename:
                continue
            if Path(filename).suffix.lower() not in SUPPORTED_AUDIO:
                continue
            identifier = str(value.get("id") or uuid4().hex)
            if identifier in used:
                identifier = uuid4().hex
            used.add(identifier)
            result.append({
                "id": identifier,
                "name": str(value.get("name") or Path(filename).stem),
                "file": filename,
                "voice": value.get("voice") is True,
            })
        return result

    def save(self, presets):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest.with_suffix(".tmp")
        temporary.write_text(json.dumps({"schema_version": 1, "presets": presets},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.manifest)

    def import_file(self, source: Path):
        source = Path(source).resolve()
        if source.suffix.lower() not in SUPPORTED_AUDIO or not source.is_file():
            raise ValueError("mp3・wav・oggの音声ファイルを選択してください")
        self.directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source.stem)[:40].strip(" .") or "audio"
        filename = f"{digest.hexdigest()}-{stem}{source.suffix.lower()}"
        target = self.directory / filename
        if not target.exists():
            temporary = self.directory / f"{uuid4().hex}.tmp"
            try:
                shutil.copyfile(source, temporary)
                temporary.replace(target)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return filename, source.stem


class VoiceController(QObject):
    presets_changed = Signal(str)
    message_changed = Signal(str)
    busy_changed = Signal(bool)
    playback_active_changed = Signal(bool)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.library = VoiceLibrary(directory)
        self.message = "音声ファイルを追加してください"
        try:
            self.presets = self.library.load()
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.presets = []
            self.message = f"音声設定を読み込めませんでした: {exc}"
        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.is_playing = False
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(self._play_error)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self._playing_id = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.import_job = None
        self.import_timer = QTimer(self)
        self.import_timer.setInterval(50)
        self.import_timer.timeout.connect(self._poll_import)

    def _message(self, message):
        self.message = message
        self.message_changed.emit(message)

    def _commit(self, values, selected=""):
        try:
            self.library.save(values)
        except OSError as exc:
            self._message(f"音声設定を保存できませんでした: {exc}")
            self.presets_changed.emit(selected)
            return False
        self.presets = values
        self.presets_changed.emit(selected)
        return True

    def import_audio(self, source, replace_id=None):
        if self.import_job is not None:
            return
        self.import_job = (replace_id, self.executor.submit(self.library.import_file, Path(source)))
        self._message("音声ファイルを取り込み中…")
        self.busy_changed.emit(True)
        self.import_timer.start()

    def _poll_import(self):
        if self.import_job is None:
            return
        replace_id, future = self.import_job
        if not future.done():
            return
        self.import_job = None
        self.import_timer.stop()
        try:
            filename, default_name = future.result()
            values = [dict(preset) for preset in self.presets]
            existing = next((p for p in values if p["id"] == replace_id), None)
            if existing is None:
                existing = {"id": uuid4().hex, "name": default_name, "file": filename, "voice": False}
                values.append(existing)
            else:
                if self._playing_id == replace_id:
                    self.stop()
                existing["file"] = filename
            if self._commit(values, existing["id"]):
                self._message("音声ファイルを取り込みました")
        except (OSError, ValueError) as exc:
            self._message(f"音声を取り込めませんでした: {exc}")
        finally:
            self.busy_changed.emit(False)

    def update_preset(self, identifier, name, voice):
        values = [dict(p) for p in self.presets]
        preset = next((p for p in values if p["id"] == identifier), None)
        if preset is not None:
            preset.update(name=name.strip() or "音声", voice=bool(voice))
            self._commit(values, identifier)

    def delete_preset(self, identifier):
        if self._playing_id == identifier:
            self.stop()
        self._commit([dict(p) for p in self.presets if p["id"] != identifier])

    def move_preset(self, identifier, step):
        index = next((i for i, preset in enumerate(self.presets) if preset["id"] == identifier), -1)
        values = moved_list(self.presets, index, step)
        if values is not None:
            self._commit(values, identifier)
    def play(self, identifier):
        preset = next((p for p in self.presets if p["id"] == identifier), None)
        if preset is None:
            return
        path = self.library.directory / preset["file"]
        if not path.is_file():
            self._message(f"音声ファイルが見つかりません: {preset['file']}")
            return
        source = QUrl.fromLocalFile(str(path.resolve()))
        # Reset the source instead of seeking during rapid retriggers.
        if not self.player.source().isEmpty():
            self.player.setSource(QUrl())
        self.player.setSource(source)
        self._playing_id = identifier
        self._message(f"再生中：{preset['name']}")
        self.player.play()

    def stop(self):
        self.player.stop()
        self._set_playback_active(False)
        self._playing_id = None
        self._message("停止しました")

    def _play_error(self, _error, description):
        self._set_playback_active(False)
        self._playing_id = None
        self._message(f"音声を再生できませんでした: {description}")

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._set_playback_active(False)
            self._playing_id = None
            self._message("再生が完了しました")

    def _set_playback_active(self, active):
        active = bool(active)
        if active != self.is_playing:
            self.is_playing = active
            self.playback_active_changed.emit(active)

    def _playback_state_changed(self, state):
        self._set_playback_active(state == QMediaPlayer.PlaybackState.PlayingState)

    def close(self):
        self.import_timer.stop()
        self._set_playback_active(False)
        self.player.stop()
        self.player.setSource(QUrl())
        self.executor.shutdown(wait=False, cancel_futures=True)


class VoicePanel(QScrollArea):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._updating = False
        self._busy = False
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        hint = QLabel("音声プリセットを登録して再生できます。「ボイス」にチェックした項目だけを、立ち絵の右クリックメニューに表示します。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.preset_list = QListWidget()
        self.preset_list.setMinimumHeight(100)
        self.preset_list.currentItemChanged.connect(lambda *_: self._show_preset())
        self.preset_list.itemDoubleClicked.connect(lambda _: self.controller.play(self.selected_id()))
        layout.addWidget(self.preset_list, 1)
        self.reorder_buttons = ReorderButtons(self.preset_list)
        self.reorder_buttons.move_requested.connect(
            lambda step: self.controller.move_preset(self.selected_id(), step))
        layout.addWidget(self.reorder_buttons)
        row = QHBoxLayout()
        self.add_button = QPushButton("音声を追加")
        self.add_button.clicked.connect(lambda: self._choose_file(False))
        self.delete_button = QPushButton("削除")
        self.delete_button.clicked.connect(lambda: self.controller.delete_preset(self.selected_id()))
        row.addWidget(self.add_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("音声プリセット名")
        self.name_edit.editingFinished.connect(self._commit)
        form.addRow("プリセット名", self.name_edit)
        self.file_label = QLabel("未選択")
        self.file_label.setWordWrap(True)
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form.addRow("音声ファイル", self.file_label)
        self.voice_check = QCheckBox("ボイス")
        self.voice_check.setToolTip("チェックすると右クリックの「ボイス」メニューに表示します")
        self.voice_check.toggled.connect(lambda _: self._commit())
        form.addRow(self.voice_check)
        layout.addLayout(form)
        self.replace_button = QPushButton("ファイルを変更")
        self.replace_button.clicked.connect(lambda: self._choose_file(True))
        layout.addWidget(self.replace_button)
        row = QHBoxLayout()
        self.play_button = QPushButton("再生")
        self.play_button.clicked.connect(lambda: self.controller.play(self.selected_id()))
        stop = QPushButton("停止")
        stop.clicked.connect(self.controller.stop)
        row.addWidget(self.play_button)
        row.addWidget(stop)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message_label = QLabel(controller.message)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        folder = QLabel("保存先：exeと同じ階層の voice フォルダ")
        folder.setToolTip(str(controller.library.directory.resolve()))
        folder.setWordWrap(True)
        layout.addWidget(folder)
        controller.presets_changed.connect(self.refresh)
        controller.message_changed.connect(self.message_label.setText)
        controller.busy_changed.connect(self._set_busy)
        self.refresh()

    def selected_id(self):
        item = self.preset_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else ""

    def refresh(self, selected=""):
        selected = selected or self.selected_id()
        self._updating = True
        self.preset_list.clear()
        for preset in self.controller.presets:
            item = QListWidgetItem(preset["name"])
            item.setData(Qt.ItemDataRole.UserRole, preset["id"])
            self.preset_list.addItem(item)
            if preset["id"] == selected:
                self.preset_list.setCurrentItem(item)
        self._updating = False
        self._show_preset()

    def _show_preset(self):
        if self._updating:
            return
        self._updating = True
        preset = next((p for p in self.controller.presets if p["id"] == self.selected_id()), None)
        self.name_edit.setText(preset["name"] if preset else "")
        filename = preset["file"] if preset else ""
        display_name = filename[65:] if re.match(r"^[a-f0-9]{64}-", filename) else filename
        self.file_label.setText(display_name or "未選択")
        self.file_label.setToolTip(str(self.controller.library.directory / filename) if preset else "")
        self.voice_check.setChecked(preset["voice"] if preset else False)
        enabled = preset is not None and not self._busy
        for control in (self.name_edit, self.voice_check, self.replace_button, self.play_button, self.delete_button):
            control.setEnabled(enabled)
        self._updating = False

    def _commit(self):
        if not self._updating and self.selected_id():
            self.controller.update_preset(self.selected_id(), self.name_edit.text(), self.voice_check.isChecked())

    def _choose_file(self, replace):
        path, _ = QFileDialog.getOpenFileName(self, "音声ファイルを選択", "", "音声 (*.mp3 *.wav *.ogg)")
        if path:
            self.controller.import_audio(path, self.selected_id() if replace else None)

    def _set_busy(self, busy):
        self._busy = busy
        self.progress.setVisible(busy)
        self.add_button.setEnabled(not busy)
        self.reorder_buttons.setEnabled(not busy)
        self.preset_list.setEnabled(not busy)
        self._show_preset()
