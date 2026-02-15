"""
UI for configuring simulation type and parameters per i* variable.
Dropdown to choose type, dynamic parameter fields per type.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QDoubleSpinBox, QLineEdit, QFrame,
)
from PySide6.QtCore import Signal

from simulation import (
    SIMULATION_TYPES,
    get_simulation_types_for_var,
    get_params_for_type,
)


class SimulationConfigRow(QWidget):
    """One row: variable name, type dropdown, parameter fields."""

    config_changed = Signal(str, str, dict)  # var_name, type_id, params

    def __init__(self, var_name: str, var_type: str, initial_type_id: str = "first_order", initial_params: dict = None, parent=None):
        super().__init__(parent)
        self.var_name = var_name
        self.var_type = var_type
        self.param_widgets = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        layout.addWidget(QLabel(var_name))
        self.type_combo = QComboBox()
        types = get_simulation_types_for_var(var_type)
        for tid, label in types:
            self.type_combo.addItem(label, tid)
        idx = self.type_combo.findData(initial_type_id)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        self.params_container = QWidget()
        self.params_layout = QFormLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_container, 1)
        self._build_params(initial_type_id, initial_params or {})

    def _build_params(self, type_id: str, values: dict):
        for w in self.param_widgets.values():
            w.deleteLater()
        self.param_widgets.clear()
        for name, ptype, default, label in get_params_for_type(type_id):
            if ptype == "float":
                w = QDoubleSpinBox()
                w.setRange(0.0001, 3600)
                w.setDecimals(3)
                w.setSingleStep(0.1)
                w.setValue(values.get(name, default))
                w.valueChanged.connect(self._emit_config)
            elif ptype == "str":
                w = QLineEdit()
                w.setPlaceholderText("e.g. oValveCommand")
                w.setText(values.get(name, default) or "")
                w.textChanged.connect(self._emit_config)
            else:
                w = QLineEdit()
                w.setText(str(values.get(name, default)))
                w.textChanged.connect(self._emit_config)
            self.param_widgets[name] = w
            self.params_layout.addRow(label, w)

    def _on_type_changed(self):
        type_id = self.type_combo.currentData()
        self._build_params(type_id, {})
        self._emit_config()

    def _emit_config(self):
        type_id = self.type_combo.currentData()
        params = {}
        for name, ptype, default, _ in get_params_for_type(type_id):
            w = self.param_widgets.get(name)
            if w is None:
                continue
            if ptype == "float":
                params[name] = w.value()
            else:
                params[name] = w.text().strip() or default
        self.config_changed.emit(self.var_name, type_id, params)

    def get_config(self) -> tuple:
        """Return (type_id, params)."""
        type_id = self.type_combo.currentData()
        params = {}
        for name, ptype, default, _ in get_params_for_type(type_id):
            w = self.param_widgets.get(name)
            if w:
                params[name] = w.value() if ptype == "float" else (w.text().strip() or default)
        return type_id, params


class SimulationConfigPanel(QFrame):
    """Panel to configure simulation for all i* variables."""

    config_changed = Signal(dict)  # {var_name: (setpoint_var, type_id, params)}

    def __init__(self, variables: list, parent=None):
        """
        variables: list of {name, type, setpoint_var} for i* vars to simulate
        """
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setStyleSheet("QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 4px; }")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Simulation config (i* feedbacks)"))
        self.rows = {}
        for v in variables:
            name = v.get("name", "")
            vtype = v.get("type", "Real")
            setpoint = v.get("setpoint_var", "")
            row = SimulationConfigRow(
                name, vtype,
                initial_type_id="first_order" if vtype == "Real" else "bool_delay" if vtype == "Bool" else "instant",
                initial_params={"tau_seconds": 0.7} if vtype == "Real" else {"delay_seconds": 0.1, "trigger_variable": setpoint},
            )
            row.config_changed.connect(lambda tid, p, n=name, sp=setpoint: self._on_row_changed(n, sp, tid, p))
            self.rows[name] = (row, setpoint)
            layout.addWidget(row)
        layout.addStretch()

    def _on_row_changed(self, var_name: str, setpoint_var: str, type_id: str, params: dict):
        self.config_changed.emit(self.get_config())

    def get_config(self) -> dict:
        """Return {var_name: (setpoint_var, type_id, params)}."""
        result = {}
        for name, (row, setpoint) in self.rows.items():
            type_id, params = row.get_config()
            result[name] = (setpoint, type_id, params)
        return result
