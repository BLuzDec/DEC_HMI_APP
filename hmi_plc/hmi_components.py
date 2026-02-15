"""
HMI components: Valve, Tank, Pump, etc. for drag-and-drop onto the canvas.
"""
from PySide6.QtWidgets import (
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPixmapItem,
    QWidget, QVBoxLayout, QLabel, QFrame, QPushButton, QScrollArea,
)
from PySide6.QtCore import Qt, QRectF, QPointF, QMimeData
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPolygonF, QPixmap, QDrag,
)


class ValveItem(QGraphicsRectItem):
    """Valve symbol: circle with triangle (open/closed indicator)."""
    def __init__(self, x=0, y=0, size=40, is_open=True, parent=None):
        super().__init__(0, 0, size, size, parent)
        self.setPos(x, y)
        self._is_open = is_open
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.PenStyle.NoPen))

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        rad = min(r.width(), r.height()) * 0.4
        painter.setPen(QPen(QColor(80, 120, 180), 2))
        painter.setBrush(QBrush(QColor(60, 100, 160)))
        painter.drawEllipse(QPointF(cx, cy), rad, rad)
        color = QColor(100, 200, 100) if self._is_open else QColor(200, 100, 100)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 1))
        tri = QPolygonF()
        if self._is_open:
            tri << QPointF(cx, cy - rad * 0.6) << QPointF(cx - rad * 0.5, cy + rad * 0.4) << QPointF(cx + rad * 0.5, cy + rad * 0.4)
        else:
            tri << QPointF(cx, cy + rad * 0.6) << QPointF(cx - rad * 0.5, cy - rad * 0.4) << QPointF(cx + rad * 0.5, cy - rad * 0.4)
        painter.drawPolygon(tri)


class TankItem(QGraphicsRectItem):
    """Tank symbol: rectangle with fill level (0..1)."""
    def __init__(self, x=0, y=0, w=60, h=100, fill_level=0.5, parent=None):
        super().__init__(0, 0, w, h, parent)
        self.setPos(x, y)
        self._fill_level = max(0, min(1, fill_level))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.PenStyle.NoPen))

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.setPen(QPen(QColor(100, 140, 200), 2))
        painter.setBrush(QBrush(QColor(30, 50, 80)))
        painter.drawRoundedRect(r, 4, 4)
        fill_h = r.height() * self._fill_level
        if fill_h > 2:
            fill_rect = QRectF(r.x() + 2, r.bottom() - fill_h - 2, r.width() - 4, fill_h)
            painter.setBrush(QBrush(QColor(50, 150, 220, 180)))
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.drawRoundedRect(fill_rect, 2, 2)

    def set_fill_level(self, level):
        self._fill_level = max(0, min(1, level))
        self.update()


class PumpItem(QGraphicsEllipseItem):
    """Pump symbol: circle."""
    def __init__(self, x=0, y=0, size=50, parent=None):
        super().__init__(0, 0, size, size, parent)
        self.setPos(x, y)
        self.setBrush(QBrush(QColor(80, 180, 120, 200)))
        self.setPen(QPen(QColor(60, 140, 90), 2))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable)


MIME_TYPE_HMI = "application/x-hmi-component"


class PaletteButton(QPushButton):
    """Button that starts a drag when pressed and dragged."""
    def __init__(self, label, component_type, parent=None):
        super().__init__(label, parent)
        self._component_type = component_type
        self._drag_start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start:
            dist = (event.position().toPoint() - self._drag_start).manhattanLength()
            if dist > 10:  # Start drag after small movement
                mime = QMimeData()
                mime.setData(MIME_TYPE_HMI, self._component_type.encode("utf-8"))
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.CopyAction)
                self._drag_start = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)
