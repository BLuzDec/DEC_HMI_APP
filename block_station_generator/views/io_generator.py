"""
Inputs/Outputs Generation: {INPUTS}, {OUTPUTS}.
User fills a table of variables (name, type, default, comment).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt


COMMON_TYPES = ["Bool", "Int", "DInt", "Real", "Time", "String"]


class IOGeneratorView(QWidget):
    """View for block inputs and outputs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Inputs
        in_grp = QGroupBox("Inputs ({INPUTS})")
        in_layout = QVBoxLayout(in_grp)
        self._in_table = QTableWidget()
        self._in_table.setColumnCount(4)
        self._in_table.setHorizontalHeaderLabels(["Name", "Type", "Default", "Comment"])
        self._in_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        in_layout.addWidget(self._in_table)
        in_btn = QPushButton("Add Input")
        in_btn.clicked.connect(self._add_input)
        in_layout.addWidget(in_btn)
        layout.addWidget(in_grp)

        # Outputs
        out_grp = QGroupBox("Outputs ({OUTPUTS})")
        out_layout = QVBoxLayout(out_grp)
        self._out_table = QTableWidget()
        self._out_table.setColumnCount(4)
        self._out_table.setHorizontalHeaderLabels(["Name", "Type", "Default", "Comment"])
        self._out_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        out_layout.addWidget(self._out_table)
        out_btn = QPushButton("Add Output")
        out_btn.clicked.connect(self._add_output)
        out_layout.addWidget(out_btn)
        layout.addWidget(out_grp)

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

    def _add_input(self):
        r = self._in_table.rowCount()
        self._in_table.insertRow(r)
        self._in_table.setItem(r, 0, QTableWidgetItem("iSignal"))
        cb = QComboBox()
        cb.addItems(COMMON_TYPES)
        self._in_table.setCellWidget(r, 1, cb)
        self._in_table.setItem(r, 2, QTableWidgetItem("FALSE"))
        self._in_table.setItem(r, 3, QTableWidgetItem(""))

    def _add_output(self):
        r = self._out_table.rowCount()
        self._out_table.insertRow(r)
        self._out_table.setItem(r, 0, QTableWidgetItem("oSignal"))
        cb = QComboBox()
        cb.addItems(COMMON_TYPES)
        self._out_table.setCellWidget(r, 1, cb)
        self._out_table.setItem(r, 2, QTableWidgetItem("FALSE"))
        self._out_table.setItem(r, 3, QTableWidgetItem(""))

    def _get_type_from_row(self, table, row, col=1):
        w = table.cellWidget(row, col)
        if isinstance(w, QComboBox):
            return w.currentText()
        it = table.item(row, col)
        return it.text() if it else "Bool"

    def get_inputs_scl(self) -> str:
        """Generate SCL for {INPUTS}."""
        lines = []
        for r in range(self._in_table.rowCount()):
            name = self._in_table.item(r, 0)
            typ = self._get_type_from_row(self._in_table, r)
            default = self._in_table.item(r, 2)
            if name and name.text():
                def_str = f" := {default.text()}" if default and default.text() else ""
                lines.append(f"      {name.text()} : {typ}{def_str};")
        return "\n".join(lines) if lines else ""

    def get_outputs_scl(self) -> str:
        """Generate SCL for {OUTPUTS}."""
        lines = []
        for r in range(self._out_table.rowCount()):
            name = self._out_table.item(r, 0)
            typ = self._get_type_from_row(self._out_table, r)
            default = self._out_table.item(r, 2)
            if name and name.text():
                def_str = f" := {default.text()}" if default and default.text() else ""
                lines.append(f"      {name.text()} : {typ}{def_str};")
        return "\n".join(lines) if lines else ""
