"""事前生成の確認・進捗とPSD別キャッシュ削除の画面。"""

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)


def confirm_generation(parent, description):
    box = QMessageBox(parent)
    box.setWindowTitle("事前キャッシュの生成")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(description + "\n\nPSDの大きさや組み合わせの数によって、長時間かかる場合があります。"
                "保存先の空き容量も使用します。\n生成済みの有効なキャッシュはスキップします。\n実行しますか？")
    yes = box.addButton("はい", QMessageBox.ButtonRole.YesRole)
    no = box.addButton("いいえ", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() == yes


class PrecacheProgressDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("事前キャッシュを生成中")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.completed = False
        self.summary = None
        layout = QVBoxLayout(self)
        self.message = QLabel("処理の開始を待っています…")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.ok_button = QPushButton("ＯＫ")
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        layout.addWidget(self.ok_button)
        self.resize(460, 190)

    def open_centered(self):
        self.open()
        QTimer.singleShot(0, self._center)

    def _center(self):
        rectangle = self.frameGeometry()
        rectangle.moveCenter(self.parentWidget().frameGeometry().center())
        self.move(rectangle.topLeft())

    def report(self, values):
        phase = values["phase"]
        done, total = values["done"], values["total"]
        self.message.setText("生成済みのキャッシュを確認中…" if phase == "scan" else "キャッシュを生成中…")
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done if total else 1)
        self.details.setText(f"{done} / {total}　生成済み {values.get('cached', 0)} 件")

    def complete(self, result):
        self.summary = dict(result)
        self.completed = True
        self.setWindowTitle("事前キャッシュの生成")
        self.message.setText("ロードが完了しました")
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.details.setText(f"新規生成 {result['generated']} 件 / 生成済みをスキップ {result['skipped']} 件")
        self.ok_button.setEnabled(True)
        self.ok_button.setDefault(True)
        self.ok_button.setFocus()

    def fail(self, error):
        self.completed = True
        self.setWindowTitle("事前キャッシュの生成")
        self.message.setText("キャッシュの生成に失敗しました")
        self.details.setText(str(error))
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.ok_button.setEnabled(True)

    def accept(self):
        if self.completed:
            super().accept()

    def reject(self):
        # Completion is acknowledged explicitly using the requested OK button.
        pass

    def closeEvent(self, event):
        event.ignore()


class CacheDeleteDialog(QDialog):
    deleted = Signal(object)

    def __init__(self, registry, parent):
        super().__init__(parent)
        self.registry = registry
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.job = None
        self._operation_message = ""
        self.setWindowTitle("キャッシュの削除")
        self.resize(640, 440)
        layout = QVBoxLayout(self)
        hint = QLabel("削除するPSDのキャッシュにチェックを付けてください。"
                      "表示中のPSDは、次回の表示更新からキャッシュが再作成されます。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.entries = QListWidget()
        self.entries.itemChanged.connect(self._update_buttons)
        layout.addWidget(self.entries, 1)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.delete_button = QPushButton("選択したキャッシュを削除")
        self.delete_button.clicked.connect(self._request_delete)
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.delete_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._refresh()

    def _refresh(self):
        self.message.setText("PSDごとのキャッシュを読み込み中…")
        self.job = ("list", self.executor.submit(self.registry.list_documents))
        self._update_buttons()

    def _update_buttons(self, *_args):
        checked = any(self.entries.item(i).checkState() == Qt.CheckState.Checked
                      for i in range(self.entries.count()))
        busy = self.job is not None
        self.delete_button.setEnabled(checked and not busy)
        self.close_button.setEnabled(not busy)
        self.entries.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _request_delete(self):
        identifiers = [self.entries.item(i).data(Qt.ItemDataRole.UserRole)
                       for i in range(self.entries.count())
                       if self.entries.item(i).checkState() == Qt.CheckState.Checked]
        if not identifiers or self.job is not None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("キャッシュの削除")
        box.setText(f"選択した {len(identifiers)} 件のPSDキャッシュを削除しますか？")
        yes = box.addButton("はい", QMessageBox.ButtonRole.YesRole)
        no = box.addButton("いいえ", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() == yes:
            self.message.setText("キャッシュを削除中…")
            self.job = ("delete", self.executor.submit(self.registry.delete_documents, identifiers))
            self._update_buttons()

    def _poll(self):
        if self.job is None or not self.job[1].done():
            return
        kind, future = self.job
        self.job = None
        try:
            result = future.result()
            if kind == "list":
                self.entries.clear()
                for value in result:
                    label = (f"{value['psd_name']}　{value['frames']} 枚 / {value['bytes']/1024**2:.1f} MiB\n"
                             f"{value['psd_path']}")
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, value["document_id"])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setToolTip(value["psd_path"])
                    self.entries.addItem(item)
                self.message.setText(self._operation_message or (
                    "削除するキャッシュを選択してください" if result else "保存されたキャッシュはありません"))
                self._operation_message = ""
            else:
                self.deleted.emit(result["deleted"])
                self._operation_message = f"{len(result['deleted'])} 件のPSDキャッシュを削除しました"
                if result["errors"]:
                    self._operation_message += "。削除できなかった項目：" + " / ".join(result["errors"])
                self._refresh()
        except Exception as exc:
            self.message.setText(f"処理に失敗しました: {exc}")
        self._update_buttons()

    def done(self, result):
        if self.job is not None:
            return
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().done(result)

    def closeEvent(self, event):
        if self.job is not None:
            event.ignore()
        else:
            super().closeEvent(event)
