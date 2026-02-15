"""
Block component: system block with inputs/outputs/in_out for HMI simulation.
Supports Request (user sends to PLC) vs Status (received from PLC).
Bool request: On/Off buttons. Real request: spinbox. Status: read-only.
"""
from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QDoubleSpinBox, QSpinBox, QComboBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from block_definitions import BLOCK_REGISTRY, MPTS_MODE_LABELS


class BlockWidget(QFrame):
    """Widget showing a system block with I/O. Request = control, Status = display."""

    value_changed = Signal(str, object)  # name, value

    def __init__(self, block_config, parent=None):
        super().__init__(parent)
        self.block_config = block_config
        self._value_widgets = {}  # name -> widget for get/set
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setObjectName("BlockWidget")
        self.setStyleSheet("""
            QFrame#BlockWidget {
                background-color: #2d2d30;
                border: 2px solid #3e3e42;
                border-radius: 6px;
            }
        """)
        self.setMinimumSize(360, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel(block_config.get("title", block_config.get("name", "Block")))
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #007ACC;")
        layout.addWidget(title)

        # Inputs (can be request or status)
        layout.addWidget(QLabel("INPUTS"))
        self.inputs_layout = QVBoxLayout()
        layout.addLayout(self.inputs_layout)
        self._build_io_section(block_config.get("inputs", []), self.inputs_layout, "request", read_only=False)

        # In/Out
        in_out = block_config.get("in_out", [])
        if in_out:
            layout.addWidget(QLabel("IN_OUT"))
            self.inout_layout = QVBoxLayout()
            layout.addLayout(self.inout_layout)
            self._build_io_section(in_out, self.inout_layout, "status", read_only=False)

        # Outputs (always status)
        layout.addWidget(QLabel("OUTPUTS"))
        self.outputs_layout = QVBoxLayout()
        layout.addLayout(self.outputs_layout)
        self._build_io_section(block_config.get("outputs", []), self.outputs_layout, "status", read_only=True)

    def _build_io_section(self, rows, section_layout, default_direction, read_only=False):
        """Build rows: Name | Control or Display."""
        for row in rows:
            if isinstance(row, (list, tuple)):
                name = row[0] if row else ""
                dtype = row[1] if len(row) > 1 else "Bool"
                desc = row[2] if len(row) > 2 else ""
                direction = default_direction
            else:
                name = row.get("name", "")
                dtype = row.get("type", "Bool")
                desc = row.get("desc", "")
                direction = row.get("direction", default_direction)
            if not name:
                continue
            h = QHBoxLayout()
            h.addWidget(QLabel(name))
            if direction == "request" and not read_only:
                if dtype == "Bool":
                    w = QWidget()
                    btn_layout = QHBoxLayout(w)
                    btn_on = QPushButton("On")
                    btn_off = QPushButton("Off")
                    btn_on.setFixedWidth(40)
                    btn_off.setFixedWidth(40)
                    btn_on.clicked.connect(lambda checked, n=name: self._emit_value(n, True))
                    btn_off.clicked.connect(lambda checked, n=name: self._emit_value(n, False))
                    btn_layout.addWidget(btn_on)
                    btn_layout.addWidget(btn_off)
                    self._value_widgets[name] = ("bool", (btn_on, btn_off))
                elif dtype == "Real":
                    sp = QDoubleSpinBox()
                    sp.setRange(-1e9, 1e9)
                    sp.setDecimals(3)
                    sp.valueChanged.connect(lambda v, n=name: self.value_changed.emit(n, v))
                    self._value_widgets[name] = ("real", sp)
                elif dtype == "Int":
                    sp = QSpinBox()
                    sp.setRange(-2147483648, 2147483647)
                    sp.valueChanged.connect(lambda v, n=name: self.value_changed.emit(n, v))
                    self._value_widgets[name] = ("int", sp)
                else:
                    lbl = QLabel("--")
                    self._value_widgets[name] = ("readonly", lbl)
            else:
                lbl = QLabel("--")
                lbl.setStyleSheet("color: #888;")
                self._value_widgets[name] = ("readonly", lbl)
            h.addWidget(self._get_control_widget(name), 1)
            if desc:
                h.addWidget(QLabel(desc))
            section_layout.addLayout(h)

    def _get_control_widget(self, name):
        entry = self._value_widgets.get(name)
        if not entry:
            return QLabel("--")
        t, w = entry
        if t == "bool":
            return w[0].parent()
        return w

    def _emit_value(self, name, value):
        self.value_changed.emit(name, value)

    def set_value(self, name, value):
        """Set value (for outputs/status from PLC)."""
        entry = self._value_widgets.get(name)
        if not entry:
            return
        t, w = entry
        if t == "readonly":
            if name == "St.Mode" and isinstance(value, int):
                w.setText(MPTS_MODE_LABELS.get(value, str(value)))
            else:
                w.setText(str(value))
            w.setStyleSheet("color: #4CAF50;")
        elif t == "real":
            w.setValue(float(value))
        elif t == "int":
            w.setValue(int(value))

    def get_value(self, name):
        """Get value (for request inputs to send to PLC)."""
        entry = self._value_widgets.get(name)
        if not entry:
            return None
        t, w = entry
        if t == "bool":
            return None  # Bool is pulse/edge, not state
        if t == "real":
            return w.value()
        if t == "int":
            return w.value()
        return None


class BlockItem(QGraphicsProxyWidget):
    """Graphics item wrapping BlockWidget for placement on canvas."""

    def __init__(self, block_key, x=0, y=0, parent=None):
        super().__init__(parent)
        config = BLOCK_REGISTRY.get(block_key, BLOCK_REGISTRY.get("mpts", {}))
        self.widget = BlockWidget(config)
        self.setWidget(self.widget)
        self.setPos(x, y)
        self.setFlag(QGraphicsProxyWidget.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsProxyWidget.GraphicsItemFlag.ItemIsSelectable)
