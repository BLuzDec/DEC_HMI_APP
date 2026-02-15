"""
HMI Canvas widget: QGraphicsView that accepts drag-and-drop from the palette.
"""
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QWidget, QVBoxLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QBrush

from hmi_components import (
    ValveItem, TankItem, PumpItem, MIME_TYPE_HMI,
)
from block_component import BlockItem


class DropGraphicsView(QGraphicsView):
    """Graphics view that accepts HMI component drops."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE_HMI):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE_HMI):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_TYPE_HMI):
            return
        comp_type = event.mimeData().data(MIME_TYPE_HMI).data().decode("utf-8")
        pos = self.mapToScene(event.position().toPoint())
        self._create_item(comp_type, pos.x(), pos.y())
        event.acceptProposedAction()

    def _create_item(self, comp_type, x, y):
        if comp_type == "valve":
            item = ValveItem(x, y, 50, is_open=True)
        elif comp_type == "valve_closed":
            item = ValveItem(x, y, 50, is_open=False)
        elif comp_type == "tank":
            item = TankItem(x, y, 60, 100, fill_level=0.5)
        elif comp_type == "pump":
            item = PumpItem(x, y, 50)
        elif comp_type in ("block_mpts", "block"):
            item = BlockItem("mpts", x, y)
        else:
            return
        self.scene().addItem(item)


class HmiCanvasWidget(QWidget):
    """Canvas with QGraphicsView that accepts drops from the component palette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(0, 0, 800, 600)
        self.scene.setBackgroundBrush(QBrush(QColor(30, 35, 45)))
        self.view = DropGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def load_from_project(self, widgets_data):
        """Create items on canvas from project widgets list."""
        for w in widgets_data or []:
            wtype = w.get("type", "")
            x = w.get("x", 20)
            y = w.get("y", 20)
            if wtype == "block_mpts" or wtype == "block":
                item = BlockItem("mpts", x, y)
            elif wtype == "valve":
                is_open = w.get("is_open", True)
                item = ValveItem(x, y, 50, is_open=is_open)
            elif wtype == "valve_closed":
                item = ValveItem(x, y, 50, is_open=False)
            elif wtype == "tank":
                fill = w.get("fill_level", 0.5)
                item = TankItem(x, y, 60, 100, fill_level=fill)
            elif wtype == "pump":
                item = PumpItem(x, y, 50)
            else:
                continue
            self.scene.addItem(item)
