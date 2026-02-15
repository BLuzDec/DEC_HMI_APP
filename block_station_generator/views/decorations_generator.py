"""
Decorations Generation: {CHILD_INSTANCES}, {MULTI_INSTANCES}.
User configures child FBs and multi-instance arrays.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QGroupBox, QAbstractItemView
)
from PySide6.QtCore import Qt


class DecorationsGeneratorView(QWidget):
    """View for CHILD_INSTANCES and MULTI_INSTANCES generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Child instances
        child_grp = QGroupBox("Child Instances ({CHILD_INSTANCES})")
        child_layout = QVBoxLayout(child_grp)
        self._child_table = QTableWidget()
        self._child_table.setColumnCount(3)
        self._child_table.setHorizontalHeaderLabels(["Instance Name", "FB Type", "Comment"])
        self._child_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        child_layout.addWidget(self._child_table)
        child_btn = QPushButton("Add Child")
        child_btn.clicked.connect(self._add_child)
        child_layout.addWidget(child_btn)
        layout.addWidget(child_grp)

        # Multi instances
        multi_grp = QGroupBox("Multi Instances ({MULTI_INSTANCES})")
        multi_layout = QVBoxLayout(multi_grp)
        self._multi_table = QTableWidget()
        self._multi_table.setColumnCount(4)
        self._multi_table.setHorizontalHeaderLabels(["Array Name", "FB Type", "Size", "Comment"])
        self._multi_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        multi_layout.addWidget(self._multi_table)
        multi_btn = QPushButton("Add Multi-Instance")
        multi_btn.clicked.connect(self._add_multi)
        multi_layout.addWidget(multi_btn)
        layout.addWidget(multi_grp)

        layout.addStretch()
        self._apply_styles()

    def _apply_styles(self):
        self.setStyleSheet("""
            QGroupBox { color: #cccccc; font-weight: bold; }
            QTableWidget { background: #252526; color: #d4d4d4; }
            QHeaderView::section { background: #2d2d30; color: #cccccc; }
            QPushButton { background: #0e639c; color: white; padding: 6px 12px; }
            QPushButton:hover { background: #1177bb; }
        """)

    def _add_child(self):
        r = self._child_table.rowCount()
        self._child_table.insertRow(r)
        self._child_table.setItem(r, 0, QTableWidgetItem("fbChild"))
        self._child_table.setItem(r, 1, QTableWidgetItem("FB_Child"))
        self._child_table.setItem(r, 2, QTableWidgetItem(""))

    def _add_multi(self):
        r = self._multi_table.rowCount()
        self._multi_table.insertRow(r)
        self._multi_table.setItem(r, 0, QTableWidgetItem("arrChildren"))
        self._multi_table.setItem(r, 1, QTableWidgetItem("FB_Child"))
        self._multi_table.setItem(r, 2, QTableWidgetItem("10"))
        self._multi_table.setItem(r, 3, QTableWidgetItem(""))

    def get_child_instances_scl(self) -> str:
        """Generate SCL for {CHILD_INSTANCES}."""
        lines = []
        for r in range(self._child_table.rowCount()):
            name = self._child_table.item(r, 0)
            fb_type = self._child_table.item(r, 1)
            if name and name.text() and fb_type and fb_type.text():
                lines.append(f"\t#_{name.text()}(...);")
        return "\n".join(lines) if lines else ""

    def get_multi_instances_scl(self) -> str:
        """Generate SCL for {MULTI_INSTANCES}."""
        lines = []
        for r in range(self._multi_table.rowCount()):
            name = self._multi_table.item(r, 0)
            fb_type = self._multi_table.item(r, 1)
            size = self._multi_table.item(r, 2)
            if name and name.text() and fb_type and fb_type.text():
                sz = size.text() if size else "1"
                lines.append(f"\tFOR i := 0 TO {sz} DO\n\t\t#_{name.text()}[i](...);\n\tEND_FOR;")
        return "\n".join(lines) if lines else ""
