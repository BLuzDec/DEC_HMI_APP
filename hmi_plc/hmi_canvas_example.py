"""
HMI Canvas Example - PySide6 QGraphicsScene for industrial HMI placement.

Demonstrates:
- QGraphicsScene / QGraphicsView: practical placement of objects in screen coordinates
- Valves (custom painted items)
- Tanks (custom painted items with fill level)
- Transparent PNG images (pumps, icons)
- Drag-and-drop or fixed positioning

Run: python hmi_canvas_example.py
"""
import sys
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsPolygonItem,
    QVBoxLayout, QWidget, QLabel,
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPolygonF, QPixmap, QTransform,
)

# Add project root
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


class ValveItem(QGraphicsRectItem):
    """Valve symbol: circle with triangle (open/closed indicator)."""
    def __init__(self, x, y, size=40, is_open=True, parent=None):
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
        # Body circle
        painter.setPen(QPen(QColor(80, 120, 180), 2))
        painter.setBrush(QBrush(QColor(60, 100, 160)))
        painter.drawEllipse(QPointF(cx, cy), rad, rad)
        # Triangle (valve state)
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
    def __init__(self, x, y, w=60, h=100, fill_level=0.5, parent=None):
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
        # Tank outline
        painter.setPen(QPen(QColor(100, 140, 200), 2))
        painter.setBrush(QBrush(QColor(30, 50, 80)))
        painter.drawRoundedRect(r, 4, 4)
        # Fill level
        fill_h = r.height() * self._fill_level
        if fill_h > 2:
            fill_rect = QRectF(r.x() + 2, r.bottom() - fill_h - 2, r.width() - 4, fill_h)
            painter.setBrush(QBrush(QColor(50, 150, 220, 180)))
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.drawRoundedRect(fill_rect, 2, 2)

    def set_fill_level(self, level):
        self._fill_level = max(0, min(1, level))
        self.update()


class HmiCanvasExample(QMainWindow):
    """Example window with QGraphicsScene showing valves, tanks, and images."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HMI Canvas Example - Valves, Tanks, Images")
        self.resize(700, 500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Drag items to reposition. Uses QGraphicsScene for practical screen mapping."))

        scene = QGraphicsScene(0, 0, 600, 400)
        scene.setBackgroundBrush(QBrush(QColor(30, 35, 45)))

        # Valves
        v1 = ValveItem(80, 150, 50, is_open=True)
        v2 = ValveItem(250, 150, 50, is_open=False)
        v3 = ValveItem(420, 150, 50, is_open=True)
        scene.addItem(v1)
        scene.addItem(v2)
        scene.addItem(v3)

        # Tanks
        t1 = TankItem(100, 220, 70, 120, fill_level=0.7)
        t2 = TankItem(270, 220, 70, 120, fill_level=0.35)
        t3 = TankItem(440, 220, 70, 120, fill_level=0.9)
        scene.addItem(t1)
        scene.addItem(t2)
        scene.addItem(t3)

        # Transparent image (if available)
        img_path = os.path.join(_root, "Images", "dec_background_endToEnd_bottomRight.png")
        if os.path.isfile(img_path):
            pix = QPixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(120, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                img_item = QGraphicsPixmapItem(pix)
                img_item.setPos(480, 20)
                img_item.setOpacity(0.6)  # Semi-transparent
                img_item.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
                scene.addItem(img_item)

        # Simple pump icon (ellipse) - no external image needed
        pump = QGraphicsEllipseItem(0, 0, 50, 50)
        pump.setPos(320, 50)
        pump.setBrush(QBrush(QColor(80, 180, 120, 200)))
        pump.setPen(QPen(QColor(60, 140, 90), 2))
        pump.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable)
        scene.addItem(pump)

        view = QGraphicsView(scene)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        layout.addWidget(view)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = HmiCanvasExample()
    win.show()
    sys.exit(app.exec())
