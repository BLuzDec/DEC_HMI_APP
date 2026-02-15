"""
HMI Generation: {HMI_INPUT_FIELDS}, {HMI_OUTPUT_FIELDS}, {HMI_TRANSFER}.
User fills HMI input/output fields and transfer assignments.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QGroupBox, QComboBox, QPlainTextEdit
)
from PySide6.QtCore import Qt


COMMON_TYPES = ["Bool", "Int", "Real", "Time", "String"]


class HMIGeneratorView(QWidget):
    """View for HMI UDT and transfer generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # HMI Input fields (from operator)
        in_grp = QGroupBox("HMI Input Fields ({HMI_INPUT_FIELDS})")
        in_layout = QVBoxLayout(in_grp)
        self._in_table = QTableWidget()
        self._in_table.setColumnCount(4)
        self._in_table.setHorizontalHeaderLabels(["Name", "Type", "Default", "Comment"])
        self._in_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        in_layout.addWidget(self._in_table)
        in_btn = QPushButton("Add HMI Input")
        in_btn.clicked.connect(self._add_hmi_input)
        in_layout.addWidget(in_btn)
        layout.addWidget(in_grp)

        # HMI Output fields (to display)
        out_grp = QGroupBox("HMI Output Fields ({HMI_OUTPUT_FIELDS})")
        out_layout = QVBoxLayout(out_grp)
        self._out_table = QTableWidget()
        self._out_table.setColumnCount(4)
        self._out_table.setHorizontalHeaderLabels(["Name", "Type", "Default", "Comment"])
        self._out_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        out_layout.addWidget(self._out_table)
        out_btn = QPushButton("Add HMI Output")
        out_btn.clicked.connect(self._add_hmi_output)
        out_layout.addWidget(out_btn)
        layout.addWidget(out_grp)

        # HMI Transfer (assignments in BEGIN)
        transfer_grp = QGroupBox("HMI Transfer ({HMI_TRANSFER})")
        transfer_layout = QVBoxLayout(transfer_grp)
        self._transfer_edit = QPlainTextEdit()
        self._transfer_edit.setPlaceholderText(
            "#HMI_Data.iCurrentStep := #_Step;\n#HMI_Data.iStatus := #_Mode;\n..."
        )
        self._transfer_edit.setMinimumHeight(120)
        transfer_layout.addWidget(self._transfer_edit)
        layout.addWidget(transfer_grp)

        layout.addStretch()
        self._apply_styles()

    def _apply_styles(self):
        self.setStyleSheet("""
            QGroupBox { color: #cccccc; font-weight: bold; }
            QTableWidget { background: #252526; color: #d4d4d4; }
            QHeaderView::section { background: #2d2d30; color: #cccccc; }
            QPlainTextEdit { background: #252526; color: #d4d4d4; }
            QPushButton { background: #0e639c; color: white; padding: 6px 12px; }
            QPushButton:hover { background: #1177bb; }
        """)

    def _add_hmi_input(self):
        r = self._in_table.rowCount()
        self._in_table.insertRow(r)
        self._in_table.setItem(r, 0, QTableWidgetItem("oManualRun"))
        cb = QComboBox()
        cb.addItems(COMMON_TYPES)
        self._in_table.setCellWidget(r, 1, cb)
        self._in_table.setItem(r, 2, QTableWidgetItem("FALSE"))
        self._in_table.setItem(r, 3, QTableWidgetItem(""))

    def _add_hmi_output(self):
        r = self._out_table.rowCount()
        self._out_table.insertRow(r)
        self._out_table.setItem(r, 0, QTableWidgetItem("iStatus"))
        cb = QComboBox()
        cb.addItems(COMMON_TYPES)
        self._out_table.setCellWidget(r, 1, cb)
        self._out_table.setItem(r, 2, QTableWidgetItem("0"))
        self._out_table.setItem(r, 3, QTableWidgetItem(""))

    def _get_type_from_row(self, table, row, col=1):
        w = table.cellWidget(row, col)
        if isinstance(w, QComboBox):
            return w.currentText()
        it = table.item(row, col)
        return it.text() if it else "Bool"

    def get_hmi_input_fields_scl(self) -> str:
        lines = []
        for r in range(self._in_table.rowCount()):
            name = self._in_table.item(r, 0)
            typ = self._get_type_from_row(self._in_table, r)
            default = self._in_table.item(r, 2)
            if name and name.text():
                def_str = f" := {default.text()}" if default and default.text() else ""
                lines.append(f"      {name.text()} : {typ}{def_str};")
        return "\n".join(lines) if lines else ""

    def get_hmi_output_fields_scl(self) -> str:
        lines = []
        for r in range(self._out_table.rowCount()):
            name = self._out_table.item(r, 0)
            typ = self._get_type_from_row(self._out_table, r)
            default = self._out_table.item(r, 2)
            if name and name.text():
                def_str = f" := {default.text()}" if default and default.text() else ""
                lines.append(f"      {name.text()} : {typ}{def_str};")
        return "\n".join(lines) if lines else ""

    def get_hmi_transfer_scl(self) -> str:
        return self._transfer_edit.toPlainText().strip()
