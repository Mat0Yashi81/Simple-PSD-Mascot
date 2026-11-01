"""プレビュー画像の座標系で当たり判定を編集する。"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget,
)

class BoxItem(QGraphicsRectItem):
    def __init__(self, region, canvas_width, canvas_height, changed):
        x, y, width, height = region["rect"]
        super().__init__(0, 0, width * canvas_width, height * canvas_height)
        self.setPos(x * canvas_width, y * canvas_height)
        self.identifier = region["id"]
        self.name = region["name"]
        self.canvas_width, self.canvas_height = canvas_width, canvas_height
        self.changed = changed
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._drag_start = None
        self._original = None
        self._edges = ""
        self.setPen(QPen(QColor("#00b8d4"), 2))
    def _scale(self):
        views = self.scene().views() if self.scene() else []
        return max(.001, views[0].transform().m11()) if views else 1
    def _handle_rects(self):
        r = self.rect()
        size = min(8 / self._scale(), r.width()/3, r.height()/3)
        left, right, top, bottom = 0, r.width()-size, 0, r.height()-size
        cx, cy = (r.width()-size)/2, (r.height()-size)/2
        return [QRectF(x, y, size, size) for x, y in (
            (left, top), (cx, top), (right, top), (left, cy),
            (right, cy), (left, bottom), (cx, bottom), (right, bottom),
        )]
    def paint(self, painter, option, widget=None):
        painter.save()
        color = QColor("#ffb300" if self.isSelected() else "#00a8c6")
        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 35))
        painter.drawRect(self.rect())
        scale = self._scale()
        font = painter.font()
        font.setPixelSize(max(1, round(12/scale)))
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(5/scale, 5/scale, -5/scale, -5/scale),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.name)
        if self.isSelected():
            painter.setBrush(color)
            for handle in self._handle_rects():
                painter.drawRect(handle)
        painter.restore()
    def _edges_at(self, point):
        r = self.rect()
        dx = min(10/self._scale(), r.width()/3)
        dy = min(10/self._scale(), r.height()/3)
        horizontal = "l" if point.x() <= dx else "r" if point.x() >= r.width()-dx else ""
        vertical = "t" if point.y() <= dy else "b" if point.y() >= r.height()-dy else ""
        return horizontal + vertical
    def hoverMoveEvent(self, event):
        edges = self._edges_at(event.pos())
        cursor = Qt.CursorShape.SizeAllCursor
        if edges in ("lt", "rb"):
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif edges in ("rt", "lb"):
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif edges in ("l", "r"):
            cursor = Qt.CursorShape.SizeHorCursor
        elif edges in ("t", "b"):
            cursor = Qt.CursorShape.SizeVerCursor
        self.setCursor(cursor)
        super().hoverMoveEvent(event)
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.scene().clearSelection()
        self.setSelected(True)
        self._drag_start = QPointF(event.scenePos())
        self._original = QRectF(self.pos(), self.rect().size())
        self._edges = self._edges_at(event.pos())
        event.accept()
    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        delta = event.scenePos() - self._drag_start
        r = QRectF(self._original)
        cw, ch = self.canvas_width, self.canvas_height
        if not self._edges:
            r.moveLeft(max(0, min(cw-r.width(), r.x()+delta.x())))
            r.moveTop(max(0, min(ch-r.height(), r.y()+delta.y())))
        else:
            minw, minh = cw*.01, ch*.01
            if "l" in self._edges:
                r.setLeft(max(0, min(r.right()-minw, r.left()+delta.x())))
            if "r" in self._edges:
                r.setRight(min(cw, max(r.left()+minw, r.right()+delta.x())))
            if "t" in self._edges:
                r.setTop(max(0, min(r.bottom()-minh, r.top()+delta.y())))
            if "b" in self._edges:
                r.setBottom(min(ch, max(r.top()+minh, r.bottom()+delta.y())))
        self.setRect(0, 0, r.width(), r.height())
        self.setPos(r.topLeft())
        self.changed(self.identifier, [r.x()/cw, r.y()/ch, r.width()/cw, r.height()/ch])
        event.accept()
    def mouseReleaseEvent(self, event):
        self._drag_start = None
        event.accept()

class PreviewView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_image()
    def fit_image(self):
        r = self.sceneRect()
        if r.width() > 0 and r.height() > 0:
            self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)

class ReactionPreview(QWidget):
    box_selected = Signal(str)
    box_changed = Signal(str, object)
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.view = PreviewView(self.scene)
        self.view.setMinimumSize(280, 280)
        self.view.setBackgroundBrush(QColor("#e7e7e7"))
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)
        self.placeholder = self.scene.addText("PSDを開いてください")
        self.scene.setSceneRect(0, 0, 280, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.pixmap = None
        self.regions = []
        self.boxes = {}
        self.selected_id = ""
        self.editing = False
        self._selecting = False
        self.scene.selectionChanged.connect(self._selection_changed)
    def set_pixmap(self, pixmap: QPixmap | None):
        old_size = self.pixmap.size() if self.pixmap is not None else None
        self.pixmap = pixmap
        self.image_item.setPixmap(pixmap or QPixmap())
        self.placeholder.setVisible(pixmap is None or pixmap.isNull())
        if pixmap is not None and not pixmap.isNull():
            self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
            if old_size != pixmap.size():
                self._rebuild_boxes()
                self.view.fit_image()
    def set_reactions(self, regions, selected=""):
        self.regions = regions
        self.selected_id = selected
        self._rebuild_boxes()
    def set_editing(self, enabled):
        self.editing = enabled
        for box in self.boxes.values():
            box.setVisible(enabled)
    def select_region(self, identifier):
        self._selecting = True
        self.selected_id = identifier
        for key, box in self.boxes.items():
            box.setSelected(key == identifier)
            box.setZValue(10000 if key == identifier else box.layer_index)
            box.update()
        self._selecting = False
    def _rebuild_boxes(self):
        self._selecting = True
        for box in self.boxes.values():
            self.scene.removeItem(box)
        self.boxes.clear()
        if self.pixmap is not None and not self.pixmap.isNull():
            for index, region in enumerate(self.regions):
                box = BoxItem(region, self.pixmap.width(), self.pixmap.height(), self.box_changed.emit)
                box.layer_index = index+1
                box.setZValue(10000 if region["id"] == self.selected_id else box.layer_index)
                self.scene.addItem(box)
                box.setVisible(self.editing)
                box.setSelected(region["id"] == self.selected_id)
                self.boxes[region["id"]] = box
        self._selecting = False
    def _selection_changed(self):
        if not self._selecting:
            items = [item for item in self.scene.selectedItems() if isinstance(item, BoxItem)]
            self.selected_id = items[0].identifier if items else ""
            self.box_selected.emit(self.selected_id)
