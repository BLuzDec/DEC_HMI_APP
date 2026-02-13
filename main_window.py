import sys
import json
import os
import logging

import duckdb
from datetime import datetime, timedelta
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                               QListWidget, QPushButton, QSplitter, QScrollArea,
                               QAbstractItemView, QLabel, QApplication, QFrame,
                               QDialog, QComboBox, QDialogButtonBox, QFormLayout,
                               QCheckBox, QLineEdit, QMessageBox, QFileDialog,
                               QTableWidget, QTableWidgetItem, QGroupBox, QHeaderView,
                               QDoubleSpinBox, QSpinBox, QDateTimeEdit, QRadioButton,
                               QInputDialog, QMenuBar, QSizeGrip, QSizePolicy)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSettings, QDateTime, QPoint
from PySide6.QtGui import QPalette, QColor, QIcon, QPixmap, QPainter, QAction, QActionGroup
import pyqtgraph as pg
from collections import deque
import numpy as np
from external.plc_thread import PLCThread
from external.plc_ads_thread import PLCADSThread
from external.plc_simulator import PLCSimulator
from external.variable_loader import load_exchange_and_recipes
from external.analytics_window import AnalyticsWindow


# Color palette for limit lines (user can choose from these)
LIMIT_LINE_COLORS = [
    ("#FF5252", "Red"),
    ("#FF9800", "Orange"),
    ("#FFEB3B", "Yellow"),
    ("#4CAF50", "Green"),
    ("#00BCD4", "Cyan"),
    ("#2196F3", "Blue"),
    ("#9C27B0", "Purple"),
    ("#E91E63", "Pink"),
    ("#795548", "Brown"),
    ("#FFFFFF", "White"),
    ("#9E9E9E", "Gray"),
]


def _app_icon():
    """Load application icon: prefer DEC Group logo with taskbar sizes, then other Images/assets."""
    base = os.path.dirname(os.path.abspath(__file__))
    # DEC Group logo: build multi-size icon so it fits entirely in Windows taskbar (16/24/32)
    dec_group = os.path.join(base, "Images", "Dec Group_bleu_noir_transparent.png")
    if os.path.isfile(dec_group):
        pix = QPixmap(dec_group)
        if not pix.isNull():
            icon = QIcon()
            for size in (16, 24, 32, 48, 256):
                scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon.addPixmap(scaled)
            return icon
    # Fallback: Dec True end-to-end logo
    dec_logo = os.path.join(base, "Images", "Dec True end-to-end final white_small.png")
    if os.path.isfile(dec_logo):
        icon = QIcon(dec_logo)
        if not icon.isNull():
            return icon
    for name in ("app_icon.ico", "app_icon.png", "icon.ico"):
        for folder in (base, os.path.join(base, "assets")):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                icon = QIcon(path)
                if not icon.isNull():
                    return icon
    return QIcon()


class ConnectionPopup(QDialog):
    """Popup window for Connection configuration (Client, IP, Variable files, Recording, PLC Trigger)."""
    def __init__(self, content_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection")
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content_widget)
        self.setStyleSheet("""
            QDialog { background-color: #2d2d30; }
        """)
        self.resize(420, 520)


class LoadPopup(QDialog):
    """Popup window for Offline Data (Load CSV, Load Recording DB, Recording History)."""
    def __init__(self, content_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Offline Data")
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content_widget)
        self.setStyleSheet("""
            QDialog { background-color: #2d2d30; }
        """)
        self.resize(380, 420)


class GraphConfigDialog(QDialog):
    """Dialog to configure graph parameters before creation."""
    def __init__(self, variable_list, parent=None, selected_vars=None):
        super().__init__(parent)
        self._selected_vars = selected_vars or []
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.setWindowTitle("Graph Configuration")
        
        self.resize(480, 560)  # Larger to fit limit lines section
        self.setStyleSheet("""
            QDialog { background-color: #333; color: white; }
            QLabel { color: white; font-size: 14px; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #444; color: white; border: 1px solid #555; padding: 5px;
            }
            QPushButton {
                background-color: #007ACC; color: white; padding: 8px 15px; border: none;
            }
            QPushButton:hover { background-color: #0098FF; }
            QGroupBox { color: white; border: 1px solid #555; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.combo_x_axis = QComboBox()
        self.combo_x_axis.setMaxVisibleItems(12)
        self.combo_x_axis.addItem("Time (Index)")
        self.combo_x_axis.addItem("Discrete index (1, 2, 3…)")
        for var in variable_list:
            self.combo_x_axis.addItem(var)
        self.combo_x_axis.setToolTip(
            "Time (Index): 0-based index, shown as time. "
            "Discrete index: row count 1, 2, 3… up to total rows (e.g. 3 runs × 10 doses = 1..30); no fold-back on X."
        )
        self.combo_x_axis.currentTextChanged.connect(self._update_title_placeholder)
        self.combo_x_axis.currentTextChanged.connect(self._on_x_axis_changed)
        form_layout.addRow("X-Axis Source:", self.combo_x_axis)

        # Linked variable for discrete index (shown only when X-Axis = Discrete index)
        self.linked_var_label = QLabel("Linked variable (resets define new run):")
        self.combo_linked_var = QComboBox()
        self.combo_linked_var.setMaxVisibleItems(12)
        self.combo_linked_var.addItem("(none – count every row)", "")
        for var in variable_list:
            self.combo_linked_var.addItem(var, var)
        # Default to variable that looks like dose/cartridge counter if present
        for i in range(self.combo_linked_var.count()):
            v = self.combo_linked_var.itemData(i)
            if v and ("BatchTotalPiece" in str(v) or "Number of cartridge" in str(v) or "Number of doses" in str(v)):
                self.combo_linked_var.setCurrentIndex(i)
                break
        self.combo_linked_var.setToolTip(
            "Variable whose value changes define each 'row' (e.g. Number of cartridge). "
            "When it resets (e.g. 52→1), the index keeps counting: 1,2,…,52,53,…,102,…"
        )
        self._linked_var_row = form_layout.rowCount()
        form_layout.addRow(self.linked_var_label, self.combo_linked_var)
        self._on_x_axis_changed(self.combo_x_axis.currentText())

        # Buffer size (per graph)
        self.buffer_size_edit = QLineEdit("100000")
        self.buffer_size_edit.setPlaceholderText("100000")
        self.buffer_size_edit.setToolTip("Number of data points to keep for this graph. Array variables may scale this automatically.")
        form_layout.addRow("Buffer size:", self.buffer_size_edit)

        # Custom title (optional); default shown as placeholder
        default_title = self._default_title()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(default_title)
        self.title_edit.setToolTip("Leave empty to use default: variable names and X-axis source.")
        form_layout.addRow("Graph title (optional):", self.title_edit)

        # Y-Axis mode: 2 vars = dropdown; 3+ vars = per-variable Y1/Y2 assignment
        nvars = len(self._selected_vars)
        x_src = self.combo_x_axis.currentText()
        is_index_based = x_src in ("Time (Index)", "Discrete index (1, 2, 3…)")
        if nvars == 2 and is_index_based:
            self.y_axis_mode_combo = QComboBox()
            self.y_axis_mode_combo.addItem("Auto (by variable type)", "auto")
            self.y_axis_mode_combo.addItem("Force same axis", "same")
            self.y_axis_mode_combo.addItem("Force dual axis (Y1 / Y2)", "dual")
            self.y_axis_mode_combo.setToolTip("Auto: same axis if same type/range, else dual. Force same/dual overrides.")
            form_layout.addRow("Y-Axis mode (2 vars):", self.y_axis_mode_combo)
            self.y_axis_assignments = None
        elif nvars >= 3 and is_index_based:
            self.y_axis_mode_combo = None
            assign_group = QWidget()
            assign_layout = QFormLayout(assign_group)
            self.y_axis_assignments = {}
            for v in self._selected_vars:
                combo = QComboBox()
                combo.addItem("Y1 (left)", "y1")
                combo.addItem("Y2 (right)", "y2")
                self.y_axis_assignments[v] = combo
                assign_layout.addRow(v + ":", combo)
            form_layout.addRow("Assign to axis:", assign_group)
        else:
            self.y_axis_mode_combo = None
            self.y_axis_assignments = None
        if not hasattr(self, "y_axis_assignments"):
            self.y_axis_assignments = None

        # Display deadband (0 = off)
        self.deadband_spin = QDoubleSpinBox()
        self.deadband_spin.setRange(0.0, 1e9)
        self.deadband_spin.setDecimals(4)
        self.deadband_spin.setValue(0.0)
        self.deadband_spin.setSpecialValueText("Off")
        self.deadband_spin.setToolTip("Quantize displayed values (e.g. 0.1 bar: 1.2xxx → 1.2, 1.3xxx → 1.3). 0 = off.")
        form_layout.addRow("Display deadband (0 = off):", self.deadband_spin)

        layout.addLayout(form_layout)

        # --- Limit Lines Section ---
        limits_group = QGroupBox("Limit Lines (dashed horizontal lines)")
        limits_group.setStyleSheet("""
            QGroupBox { color: white; border: 1px solid #555; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        limits_layout = QFormLayout(limits_group)
        
        # Helper to create limit row (type selector, value/variable, color)
        def create_limit_row(label, default_color_idx=0):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            # Type: None / Fixed / Variable
            type_combo = QComboBox()
            type_combo.addItem("None", "none")
            type_combo.addItem("Fixed value", "fixed")
            type_combo.addItem("Variable", "variable")
            type_combo.setFixedWidth(100)
            row_layout.addWidget(type_combo)
            
            # Fixed value input
            value_spin = QDoubleSpinBox()
            value_spin.setRange(-1e9, 1e9)
            value_spin.setDecimals(4)
            value_spin.setValue(0.0)
            value_spin.setFixedWidth(100)
            value_spin.setVisible(False)
            row_layout.addWidget(value_spin)
            
            # Variable selector
            var_combo = QComboBox()
            var_combo.setMaxVisibleItems(12)
            for var in variable_list:
                var_combo.addItem(var)
            var_combo.setFixedWidth(180)
            var_combo.setVisible(False)
            row_layout.addWidget(var_combo)
            
            # Color selector
            color_combo = QComboBox()
            for hex_color, name in LIMIT_LINE_COLORS:
                color_combo.addItem(name, hex_color)
            color_combo.setCurrentIndex(default_color_idx)
            color_combo.setFixedWidth(80)
            color_combo.setVisible(False)
            row_layout.addWidget(color_combo)
            
            row_layout.addStretch()
            
            # Connect type change to show/hide widgets
            def on_type_changed(text):
                is_fixed = type_combo.currentData() == "fixed"
                is_var = type_combo.currentData() == "variable"
                value_spin.setVisible(is_fixed)
                var_combo.setVisible(is_var)
                color_combo.setVisible(is_fixed or is_var)
            
            type_combo.currentTextChanged.connect(on_type_changed)
            
            return row_widget, type_combo, value_spin, var_combo, color_combo
        
        # Limit High
        self.limit_high_widget, self.limit_high_type, self.limit_high_value, self.limit_high_var, self.limit_high_color = create_limit_row("Limit High", 0)  # Red
        limits_layout.addRow("Limit High:", self.limit_high_widget)
        
        # Limit Low
        self.limit_low_widget, self.limit_low_type, self.limit_low_value, self.limit_low_var, self.limit_low_color = create_limit_row("Limit Low", 6)  # Purple
        limits_layout.addRow("Limit Low:", self.limit_low_widget)
        
        layout.addWidget(limits_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _default_title(self):
        x = self.combo_x_axis.currentText() if hasattr(self, "combo_x_axis") else "Time (Index)"
        vars_str = " • ".join(self._selected_vars) if self._selected_vars else "Variables"
        return f"{vars_str}  [vs {x}]"

    def _update_title_placeholder(self):
        if hasattr(self, "title_edit"):
            self.title_edit.setPlaceholderText(self._default_title())

    def _on_x_axis_changed(self, x_src):
        discrete = x_src == "Discrete index (1, 2, 3…)"
        self.linked_var_label.setVisible(discrete)
        self.combo_linked_var.setVisible(discrete)

    def get_settings(self):
        out = {
            "x_axis": self.combo_x_axis.currentText(),
            "buffer_size": 100000,
            "graph_title": self.title_edit.text().strip() if hasattr(self, "title_edit") else "",
            "display_deadband": self.deadband_spin.value() if hasattr(self, "deadband_spin") else 0.0,
        }
        try:
            out["buffer_size"] = max(100, min(500000, int(self.buffer_size_edit.text().strip() or "100000")))
        except ValueError:
            pass
        if hasattr(self, "y_axis_mode_combo") and self.y_axis_mode_combo is not None:
            out["y_axis_mode"] = self.y_axis_mode_combo.currentData()
            out["y_axis_assignments"] = None
        elif hasattr(self, "y_axis_assignments") and self.y_axis_assignments:
            out["y_axis_mode"] = None
            out["y_axis_assignments"] = {v: combo.currentData() for v, combo in self.y_axis_assignments.items()}
        else:
            out["y_axis_mode"] = "auto"
            out["y_axis_assignments"] = None
        out["discrete_index_linked_variable"] = None
        if self.combo_x_axis.currentText() == "Discrete index (1, 2, 3…)":
            linked = self.combo_linked_var.currentData()
            if linked:
                out["discrete_index_linked_variable"] = linked
        
        # Limit lines settings
        def get_limit_settings(type_combo, value_spin, var_combo, color_combo):
            limit_type = type_combo.currentData()
            if limit_type == "none":
                return {"enabled": False}
            return {
                "enabled": True,
                "type": limit_type,
                "value": value_spin.value() if limit_type == "fixed" else None,
                "variable": var_combo.currentText() if limit_type == "variable" else None,
                "color": color_combo.currentData(),
            }
        
        out["limit_high"] = get_limit_settings(self.limit_high_type, self.limit_high_value, self.limit_high_var, self.limit_high_color)
        out["limit_low"] = get_limit_settings(self.limit_low_type, self.limit_low_value, self.limit_low_var, self.limit_low_color)
        
        return out

class RangeAxisSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that shows full numbers (no exponent) unless value has more than 5 digits."""

    def textFromValue(self, value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return str(value)
        dec = self.decimals()
        if -99999 <= v <= 99999:
            s = f"{v:.{dec}f}".rstrip("0").rstrip(".")
            return s if s else "0"
        return f"{v:.2e}"

    def valueFromText(self, text):
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return self.minimum()


class RangeConfigDialog(QDialog):
    """Dialog to configure Min/Max ranges for axes, plus buffer size, title, deadband, and limit lines."""
    def __init__(self, current_settings, has_dual_y=False, show_recipes=True, has_two_variables=False, show_delta=False, parent=None,
                 buffer_size=100000, graph_title="", graph_default_title="", display_deadband=0.0,
                 limit_high=None, limit_low=None, variable_list=None):
        super().__init__(parent)
        self._variable_list = variable_list or []
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.setWindowTitle("Axis Range Settings")
        self.setModal(True)
        self.resize(480, 480)  # Larger to fit limit lines
        self.setStyleSheet("""
            QDialog { background-color: #333; color: white; }
            QLabel { color: white; }
            QDoubleSpinBox {
                background-color: #444; color: white; border: 1px solid #555; padding: 2px;
            }
            QCheckBox { color: white; }
            QPushButton {
                background-color: #007ACC; color: white; padding: 6px 12px; border: none;
            }
            QPushButton:hover { background-color: #0098FF; }
            QComboBox {
                background-color: #444; color: white; border: 1px solid #555; padding: 2px;
            }
            QGroupBox { color: white; border: 1px solid #555; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        self.current_settings = current_settings
        layout = QVBoxLayout(self)

        def create_axis_row(axis_id, label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(80)
            # Get settings with defaults, ensuring all required keys exist
            default_vals = {"auto": True, "min": 0.0, "max": 10.0}
            vals = self.current_settings.get(axis_id, default_vals)
            # Ensure all required keys exist (merge with defaults)
            vals = {**default_vals, **vals}
            chk_auto = QCheckBox("Auto")
            chk_auto.setChecked(vals.get("auto", True))
            spin_min = RangeAxisSpinBox()
            spin_min.setRange(-1e9, 1e9)
            spin_min.setDecimals(2)
            spin_min.setValue(vals.get("min", 0.0))
            spin_min.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            spin_min.setEnabled(not vals.get("auto", True))
            spin_max = RangeAxisSpinBox()
            spin_max.setRange(-1e9, 1e9)
            spin_max.setDecimals(2)
            spin_max.setValue(vals.get("max", 10.0))
            spin_max.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            spin_max.setEnabled(not vals.get("auto", True))
            chk_auto.toggled.connect(spin_min.setDisabled)
            chk_auto.toggled.connect(spin_max.setDisabled)
            row.addWidget(lbl)
            row.addWidget(chk_auto)
            row.addWidget(QLabel("Min:"))
            row.addWidget(spin_min)
            row.addWidget(QLabel("Max:"))
            row.addWidget(spin_max)
            return row, chk_auto, spin_min, spin_max

        self.x_row, self.chk_x_auto, self.spin_x_min, self.spin_x_max = create_axis_row("x", "X Axis")
        layout.addLayout(self.x_row)
        self.y1_row, self.chk_y1_auto, self.spin_y1_min, self.spin_y1_max = create_axis_row("y1", "Y Axis (Left)")
        layout.addLayout(self.y1_row)
        self.has_dual_y = has_dual_y
        if has_dual_y:
            self.y2_row, self.chk_y2_auto, self.spin_y2_min, self.spin_y2_max = create_axis_row("y2", "Y Axis (Right)")
            layout.addLayout(self.y2_row)
            # When Y1 and Y2 have same min/max, both axes align; padding % (0 = exact alignment)
            pad_val = self.current_settings.get("aligned_y_padding_percent", 5.0)
            pad_row = QHBoxLayout()
            pad_row.addWidget(QLabel("Aligned Y padding %:"))
            self.spin_aligned_padding = RangeAxisSpinBox()
            self.spin_aligned_padding.setRange(0, 50)
            self.spin_aligned_padding.setDecimals(1)
            self.spin_aligned_padding.setValue(pad_val)
            self.spin_aligned_padding.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            self.spin_aligned_padding.setToolTip("When Y1 and Y2 have same min/max, padding added to aligned range. 0 = exact alignment.")
            pad_row.addWidget(self.spin_aligned_padding)
            pad_row.addStretch()
            layout.addLayout(pad_row)
        else:
            self.spin_aligned_padding = None
        
        # Recipe display toggle
        recipe_layout = QHBoxLayout()
        self.chk_show_recipes = QCheckBox("Show Recipe Parameters in Tooltip")
        self.chk_show_recipes.setChecked(show_recipes)
        self.chk_show_recipes.setStyleSheet("color: white; padding: 5px;")
        recipe_layout.addWidget(self.chk_show_recipes)
        recipe_layout.addStretch()
        layout.addLayout(recipe_layout)
        
        # Delta on graph: only when exactly 2 variables
        self.has_two_variables = has_two_variables
        if has_two_variables:
            delta_layout = QHBoxLayout()
            self.chk_show_delta = QCheckBox("Show delta (var2 − var1) on graph")
            self.chk_show_delta.setChecked(show_delta)
            self.chk_show_delta.setStyleSheet("color: white; padding: 5px;")
            delta_layout.addWidget(self.chk_show_delta)
            delta_layout.addStretch()
            layout.addLayout(delta_layout)
        else:
            self.chk_show_delta = None

        # Buffer size (per graph)
        buf_row = QHBoxLayout()
        buf_row.addWidget(QLabel("Buffer size:"))
        self.buffer_size_edit = QLineEdit(str(buffer_size))
        self.buffer_size_edit.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.buffer_size_edit.setToolTip("Number of data points to keep for this graph.")
        buf_row.addWidget(self.buffer_size_edit)
        buf_row.addStretch()
        layout.addLayout(buf_row)

        # Graph title (optional); show default if empty
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Graph title (optional):"))
        self.title_edit = QLineEdit(graph_title)
        self.title_edit.setPlaceholderText(graph_default_title or "Default: Var1 • Var2 [vs X]")
        self.title_edit.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.title_edit.setToolTip("Leave empty to use default.")
        title_row.addWidget(self.title_edit)
        layout.addLayout(title_row)

        # Display deadband (0 = off)
        deadband_row = QHBoxLayout()
        deadband_row.addWidget(QLabel("Display deadband (0 = off):"))
        self.deadband_spin = RangeAxisSpinBox()
        self.deadband_spin.setRange(0, 1e9)
        self.deadband_spin.setDecimals(4)
        self.deadband_spin.setValue(display_deadband)
        self.deadband_spin.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
        self.deadband_spin.setToolTip("Quantize displayed values. 0 = off.")
        deadband_row.addWidget(self.deadband_spin)
        deadband_row.addStretch()
        layout.addLayout(deadband_row)

        # --- Limit Lines Section ---
        limits_group = QGroupBox("Limit Lines (dashed horizontal lines)")
        limits_layout = QFormLayout(limits_group)
        
        # Helper to create limit row (type selector, value/variable, color)
        def create_limit_row(label, existing_settings, default_color_idx=0):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            # Type: None / Fixed / Variable
            type_combo = QComboBox()
            type_combo.addItem("None", "none")
            type_combo.addItem("Fixed value", "fixed")
            type_combo.addItem("Variable", "variable")
            type_combo.setFixedWidth(100)
            
            # Set current type from existing settings
            if existing_settings and existing_settings.get("enabled"):
                limit_type = existing_settings.get("type", "none")
                idx = {"none": 0, "fixed": 1, "variable": 2}.get(limit_type, 0)
                type_combo.setCurrentIndex(idx)
            
            row_layout.addWidget(type_combo)
            
            # Fixed value input
            value_spin = RangeAxisSpinBox()
            value_spin.setRange(-1e9, 1e9)
            value_spin.setDecimals(4)
            if existing_settings and existing_settings.get("type") == "fixed":
                value_spin.setValue(existing_settings.get("value", 0.0))
            else:
                value_spin.setValue(0.0)
            value_spin.setFixedWidth(100)
            value_spin.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            row_layout.addWidget(value_spin)
            
            # Variable selector
            var_combo = QComboBox()
            var_combo.setMaxVisibleItems(12)
            for var in self._variable_list:
                var_combo.addItem(var)
            var_combo.setFixedWidth(180)
            # Set current variable from existing settings
            if existing_settings and existing_settings.get("type") == "variable":
                var_name = existing_settings.get("variable", "")
                idx = var_combo.findText(var_name)
                if idx >= 0:
                    var_combo.setCurrentIndex(idx)
            row_layout.addWidget(var_combo)
            
            # Color selector
            color_combo = QComboBox()
            for hex_color, name in LIMIT_LINE_COLORS:
                color_combo.addItem(name, hex_color)
            # Set current color from existing settings
            if existing_settings and existing_settings.get("enabled"):
                current_color = existing_settings.get("color", "")
                for i, (hex_color, _) in enumerate(LIMIT_LINE_COLORS):
                    if hex_color == current_color:
                        color_combo.setCurrentIndex(i)
                        break
            else:
                color_combo.setCurrentIndex(default_color_idx)
            color_combo.setFixedWidth(80)
            row_layout.addWidget(color_combo)
            
            row_layout.addStretch()
            
            # Connect type change to show/hide widgets
            def on_type_changed():
                is_fixed = type_combo.currentData() == "fixed"
                is_var = type_combo.currentData() == "variable"
                value_spin.setVisible(is_fixed)
                var_combo.setVisible(is_var)
                color_combo.setVisible(is_fixed or is_var)
            
            type_combo.currentTextChanged.connect(on_type_changed)
            on_type_changed()  # Initialize visibility
            
            return row_widget, type_combo, value_spin, var_combo, color_combo
        
        # Limit High
        self.limit_high_widget, self.limit_high_type, self.limit_high_value, self.limit_high_var, self.limit_high_color = create_limit_row("Limit High", limit_high, 0)  # Red
        limits_layout.addRow("Limit High:", self.limit_high_widget)
        
        # Limit Low
        self.limit_low_widget, self.limit_low_type, self.limit_low_value, self.limit_low_var, self.limit_low_color = create_limit_row("Limit Low", limit_low, 6)  # Purple
        limits_layout.addRow("Limit Low:", self.limit_low_widget)
        
        layout.addWidget(limits_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        settings = {
            "x": {"auto": self.chk_x_auto.isChecked(), "min": self.spin_x_min.value(), "max": self.spin_x_max.value()},
            "y1": {"auto": self.chk_y1_auto.isChecked(), "min": self.spin_y1_min.value(), "max": self.spin_y1_max.value()},
            "show_recipes": self.chk_show_recipes.isChecked(),
            "show_delta": self.chk_show_delta.isChecked() if self.chk_show_delta is not None else False
        }
        if self.has_dual_y:
             settings["y2"] = {"auto": self.chk_y2_auto.isChecked(), "min": self.spin_y2_min.value(), "max": self.spin_y2_max.value()}
             settings["aligned_y_padding_percent"] = self.spin_aligned_padding.value() if self.spin_aligned_padding else 5.0
        try:
            settings["buffer_size"] = max(100, min(500000, int(self.buffer_size_edit.text().strip() or "100000")))
        except ValueError:
            settings["buffer_size"] = 100000
        settings["graph_title"] = self.title_edit.text().strip() if hasattr(self, "title_edit") else ""
        settings["display_deadband"] = self.deadband_spin.value() if hasattr(self, "deadband_spin") else 0.0
        
        # Limit lines settings
        def get_limit_settings(type_combo, value_spin, var_combo, color_combo):
            limit_type = type_combo.currentData()
            if limit_type == "none":
                return {"enabled": False}
            return {
                "enabled": True,
                "type": limit_type,
                "value": value_spin.value() if limit_type == "fixed" else None,
                "variable": var_combo.currentText() if limit_type == "variable" else None,
                "color": color_combo.currentData(),
            }
        
        settings["limit_high"] = get_limit_settings(self.limit_high_type, self.limit_high_value, self.limit_high_var, self.limit_high_color)
        settings["limit_low"] = get_limit_settings(self.limit_low_type, self.limit_low_value, self.limit_low_var, self.limit_low_color)
        
        return settings


class ExportRecordingDialog(QDialog):
    """Dialog to export recorded session data to CSV with time range and sampling interval."""
    INTERVALS_MS = [50, 500, 1000]  # 50 ms, 500 ms, 1 s

    def __init__(self, db_path, time_min, time_max, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.time_min = time_min
        self.time_max = time_max
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.setWindowTitle("Export recording to CSV")
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background-color: #333; color: white; }
            QLabel { color: white; }
            QDateTimeEdit, QComboBox {
                background-color: #444; color: white; border: 1px solid #555; padding: 5px;
            }
            QPushButton { background-color: #007ACC; color: white; padding: 8px 15px; border: none; }
            QPushButton:hover { background-color: #0098FF; }
        """)
        layout = QFormLayout(self)
        self.from_edit = QDateTimeEdit()
        self.from_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.from_edit.setCalendarPopup(True)
        if time_min:
            self.from_edit.setDateTime(QDateTime(time_min))
        layout.addRow("From:", self.from_edit)
        self.to_edit = QDateTimeEdit()
        self.to_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.to_edit.setCalendarPopup(True)
        if time_max:
            self.to_edit.setDateTime(QDateTime(time_max))
        layout.addRow("To:", self.to_edit)
        self.interval_combo = QComboBox()
        for ms in self.INTERVALS_MS:
            if ms >= 1000:
                self.interval_combo.addItem(f"{ms // 1000} s", ms / 1000.0)
            else:
                self.interval_combo.addItem(f"{ms} ms", ms / 1000.0)
        self.interval_combo.setCurrentIndex(1)  # 500 ms default
        self.interval_combo.setToolTip("Sample interval for exported rows (50 ms, 500 ms, or 1 s).")
        layout.addRow("Interval:", self.interval_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_from_to_interval(self):
        """Return (from_datetime, to_datetime, interval_seconds)."""
        from_qt = self.from_edit.dateTime().toPython()
        to_qt = self.to_edit.dateTime().toPython()
        interval_sec = self.interval_combo.currentData()
        return from_qt, to_qt, interval_sec


def export_recording_to_csv(db_path, from_dt, to_dt, interval_sec, csv_path):
    """
    Export exchange_variables from DuckDB to CSV with resampling by interval_sec.
    Columns: timestamp;var1;var2;... (semicolon-separated). Uses first value in each time bucket.
    """
    conn = duckdb.connect(database=db_path, read_only=True)
    try:
        # Resample: bucket by interval, first value per variable per bucket
        interval_placeholder = interval_sec
        result = conn.execute("""
            SELECT
                (floor(epoch(timestamp)::DOUBLE / ?) * ?) AS ts_bucket,
                variable_name,
                first(value) AS value
            FROM exchange_variables
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY ts_bucket, variable_name
            ORDER BY ts_bucket, variable_name
        """, (interval_placeholder, interval_placeholder, from_dt, to_dt)).fetchall()
        if not result:
            return 0
        # Build pivot: buckets -> { variable_name: value }
        from collections import defaultdict
        buckets = defaultdict(dict)
        for ts_bucket, var_name, value in result:
            buckets[ts_bucket][var_name] = value
        all_vars = sorted(set(v for row in result for v in [row[1]]))
        buckets_sorted = sorted(buckets.keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            header = "timestamp;" + ";".join(all_vars)
            f.write(header + "\n")
            for ts_bucket in buckets_sorted:
                row_vals = [datetime.fromtimestamp(ts_bucket).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]]
                for v in all_vars:
                    row_vals.append(str(buckets[ts_bucket].get(v, "")))
                f.write(";".join(row_vals) + "\n")
        return len(buckets_sorted)
    finally:
        conn.close()


def get_recording_time_range(db_path):
    """Return (min_timestamp, max_timestamp) from exchange_variables, or (None, None) if empty."""
    if not db_path or not os.path.isfile(db_path):
        return None, None
    try:
        conn = duckdb.connect(database=db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT min(timestamp), max(timestamp) FROM exchange_variables"
            ).fetchone()
            if row and row[0] is not None and row[1] is not None:
                return row[0], row[1]
            return None, None
        finally:
            conn.close()
    except Exception:
        return None, None


def recording_has_data(db_path):
    """Return True if exchange_variables has at least one row."""
    if not db_path or not os.path.isfile(db_path):
        return False
    try:
        conn = duckdb.connect(database=db_path, read_only=True)
        try:
            n = conn.execute("SELECT count(*) FROM exchange_variables").fetchone()[0]
            return n > 0
        finally:
            conn.close()
    except Exception:
        return False


def _format_size(size_bytes):
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_process_ram_mb():
    """Return current process RSS (resident set size) in MB, or None if psutil unavailable."""
    if _HAS_PSUTIL:
        try:
            proc = psutil.Process(os.getpid())
            return proc.memory_info().rss / (1024 * 1024)
        except Exception:
            return None
    return None


def list_recording_db_files(external_dir):
    """
    List all Data_DDMMYYYY.duckdb (and legacy recording_YYYY-MM-DD.duckdb) files in external_dir.
    Returns list of dicts: [{ 'path': str, 'date_str': str, 'date': date, 'size_bytes': int, 'size_label': str }]
    sorted by date descending (newest first).
    """
    import re, datetime as _dt
    results = []
    if not external_dir or not os.path.isdir(external_dir):
        return results
    # New format: Data_DDMMYYYY.duckdb  (e.g. Data_09022026.duckdb)
    pat_new = re.compile(r'^Data_(\d{2})(\d{2})(\d{4})\.duckdb$')
    # Old format: recording_YYYY-MM-DD.duckdb
    pat_old = re.compile(r'^recording_(\d{4}-\d{2}-\d{2})\.duckdb$')
    for fname in os.listdir(external_dir):
        file_date = None
        m_new = pat_new.match(fname)
        m_old = pat_old.match(fname) if not m_new else None
        if m_new:
            day, month, year = m_new.group(1), m_new.group(2), m_new.group(3)
            try:
                file_date = _dt.date(int(year), int(month), int(day))
            except ValueError:
                continue
        elif m_old:
            try:
                file_date = _dt.date.fromisoformat(m_old.group(1))
            except ValueError:
                continue
        if file_date is not None:
            fpath = os.path.join(external_dir, fname)
            size_bytes = os.path.getsize(fpath)
            results.append({
                'path': fpath,
                'date_str': file_date.strftime("%d/%m/%Y"),
                'date': file_date,
                'size_bytes': size_bytes,
                'size_label': _format_size(size_bytes),
            })
    # Also check for legacy automation_data.db
    legacy_path = os.path.join(external_dir, 'automation_data.db')
    if os.path.isfile(legacy_path):
        size_bytes = os.path.getsize(legacy_path)
        if size_bytes > 4096:  # Only show if it has meaningful data
            results.append({
                'path': legacy_path,
                'date_str': 'legacy',
                'date': _dt.date.min,
                'size_bytes': size_bytes,
                'size_label': _format_size(size_bytes),
            })
    results.sort(key=lambda x: x['date'], reverse=True)
    return results


def get_db_memory_info(db_path):
    """
    Get memory usage info for a DuckDB file.
    Returns dict: { 'ram_bytes': int, 'ram_label': str, 'disk_bytes': int, 'disk_label': str, 'row_count': int }
    """
    info = {'ram_bytes': 0, 'ram_label': '0 B', 'disk_bytes': 0, 'disk_label': '0 B', 'row_count': 0}
    if not db_path or not os.path.isfile(db_path):
        return info
    try:
        info['disk_bytes'] = os.path.getsize(db_path)
        size = info['disk_bytes']
        if size < 1024:
            info['disk_label'] = f"{size} B"
        elif size < 1024 * 1024:
            info['disk_label'] = f"{size / 1024:.1f} KB"
        else:
            info['disk_label'] = f"{size / (1024 * 1024):.1f} MB"
    except Exception:
        pass
    try:
        conn = duckdb.connect(database=db_path, read_only=True)
        try:
            # Get row count
            row = conn.execute("SELECT count(*) FROM exchange_variables").fetchone()
            info['row_count'] = row[0] if row else 0
            # Get memory usage via pragma
            try:
                mem_row = conn.execute("CALL pragma_database_size()").fetchone()
                if mem_row:
                    # pragma_database_size returns: database_name, database_size, block_size, total_blocks, used_blocks, free_blocks, wal_size, memory_usage, memory_limit
                    # Index depends on version; try to get memory_usage
                    pass  # DuckDB read_only doesn't track RAM well; we'll use disk size
            except Exception:
                pass
        finally:
            conn.close()
    except Exception:
        pass
    return info


class DynamicPlotWidget(QWidget):
    """
    A wrapper around pyqtgraph.PlotWidget that manages its own data lines.
    Supports dual Y-axes, XY plotting, live value headers, hover inspection, and limit lines.
    """
    def __init__(self, variable_names, x_axis_source="Time (Index)", buffer_size=100000, recipe_params=None, latest_values_cache=None, variable_metadata=None, comm_speed=0.05,
                 graph_title="", y_axis_mode="auto", y_axis_assignments=None, display_deadband=0.0, discrete_index_linked_variable=None,
                 limit_high=None, limit_low=None, all_variable_list=None):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)

        self.variables = variable_names
        self.x_axis_source = x_axis_source
        self.is_discrete_index = (x_axis_source == "Discrete index (1, 2, 3…)")
        self.discrete_index_linked_variable = (discrete_index_linked_variable or "").strip() or None
        self.is_xy_plot = (x_axis_source != "Time (Index)" and not self.is_discrete_index)
        self._discrete_index_counter = 0
        self._discrete_index_last_linked_value = None  # only advance index when linked variable value changes
        self.recipe_params = recipe_params if recipe_params else []
        self.latest_values_cache = latest_values_cache if latest_values_cache else {}
        self.variable_metadata = variable_metadata if variable_metadata else {}
        self.show_recipes_in_tooltip = True  # Default to showing recipes
        self.show_delta_on_graph = False  # When True and 2 variables, plot delta (var2 - var1)
        self.comm_speed = comm_speed  # Communication speed for time calculation
        self.graph_title = (graph_title or "").strip()
        self.graph_default_title = f"{' • '.join(variable_names)}  [vs {x_axis_source}]"
        self.display_deadband = float(display_deadband) if display_deadband else 0.0
        self.y_axis_mode = y_axis_mode  # for 2 vars: "auto" | "same" | "dual"
        self._y_axis_assignments = y_axis_assignments or {}  # for 3+ vars: {var: "y1"|"y2"}
        
        # Limit lines settings
        self.limit_high_settings = limit_high or {"enabled": False}
        self.limit_low_settings = limit_low or {"enabled": False}
        self._all_variable_list = all_variable_list or []
        self._limit_high_line = None
        self._limit_low_line = None
        
        # Setpoint and tolerance lines (controlled from analytics window)
        self._setpoint_lines = {}  # var_name -> InfiniteLine
        self._tolerance_low_lines = {}  # var_name -> InfiniteLine
        self._tolerance_high_lines = {}  # var_name -> InfiniteLine
        self._setpoint_settings = {}  # var_name -> {"enabled": bool, "value": float, "color": str}
        self._tolerance_settings = {}  # var_name -> {"enabled": bool, "value": float (percentage), "color": str}
        
        # Track start time for time-based graphs
        self.start_time = datetime.now()
        self.start_day_of_year = self.start_time.timetuple().tm_yday
        self.start_hour = self.start_time.hour
        # Track the time of the most recent data point for accurate time calculation
        self.most_recent_data_time = datetime.now()

        self.header_layout = QHBoxLayout()
        self.layout.addLayout(self.header_layout)
        self.value_layout = QHBoxLayout()
        self.value_layout.setContentsMargins(5, 0, 5, 0)
        self.header_layout.addLayout(self.value_layout)
        self.value_labels = {}
        
        # Time display label (day number and hour)
        self.time_display_label = QLabel()
        self.time_display_label.setStyleSheet("color: #888; font-size: 11px; margin-right: 10px;")
        self.update_time_display()
        self.header_layout.addWidget(self.time_display_label)
        
        # Timer to update time display every second
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time_display)
        self.time_timer.start(1000)  # Update every second

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Configure Axis Ranges")
        self.btn_settings.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: 1px solid #444; border-radius: 4px; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_settings.clicked.connect(self.open_range_settings)
        self.header_layout.addWidget(self.btn_settings)

        # "A" = Follow X: re-enable auto-scroll so X axis moves with new data (after zoom/pan fixed the view)
        self.btn_follow_x = QPushButton("A")
        self.btn_follow_x.setFixedSize(24, 24)
        self.btn_follow_x.setCursor(Qt.PointingHandCursor)
        self.btn_follow_x.setToolTip("Follow X (auto-scroll to latest). Click after zooming to lock view; click again to follow.")
        self.btn_follow_x.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: 1px solid #444; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #444; color: white; }
            QPushButton:checked { background-color: #1a6fa5; color: white; border-color: #1a6fa5; }
        """)
        self.btn_follow_x.setCheckable(True)
        self.btn_follow_x.setChecked(True)  # start with follow enabled
        self.btn_follow_x.clicked.connect(self._toggle_follow_x)
        self.header_layout.addWidget(self.btn_follow_x)
        self.btn_follow_x.setVisible(not self.is_xy_plot)  # only for time-based plots

        self.btn_export_csv = QPushButton("📥")
        self.btn_export_csv.setFixedSize(24, 24)
        self.btn_export_csv.setCursor(Qt.PointingHandCursor)
        self.btn_export_csv.setToolTip("Export graph data to CSV (semicolon-separated)")
        self.btn_export_csv.setStyleSheet("""
            QPushButton { background-color: transparent; color: #c0c0c0; border: 1px solid #555; border-radius: 4px; }
            QPushButton:hover { background-color: #3e3e42; color: #e8e8e8; }
        """)
        self.btn_export_csv.clicked.connect(self.export_graph_data_to_csv)
        self.header_layout.addWidget(self.btn_export_csv)

        self.plot_widget = pg.PlotWidget()
        self.layout.addWidget(self.plot_widget)
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.getAxis('left').setPen('#888')
        self.plot_widget.getAxis('bottom').setPen('#888')
        self.plot_widget.getAxis('left').setTextPen('#aaa')
        self.plot_widget.getAxis('bottom').setTextPen('#aaa')
        # Disable SI prefix scaling (e.g. showing 385 x0.001 instead of 0.385)
        self.plot_widget.getAxis('left').enableAutoSIPrefix(False)
        self.plot_widget.getAxis('bottom').enableAutoSIPrefix(False)
        if self.is_xy_plot:
            self.plot_widget.setLabel('bottom', self.x_axis_source)
        elif self.is_discrete_index:
            self.plot_widget.setLabel('bottom', 'Index')
        else:
            self.plot_widget.setLabel('bottom', 'Time (MM:SS.mmm)')
        # Set up time formatter for x-axis only when using Time (Index)
        if not self.is_xy_plot and not self.is_discrete_index:
            self.setup_time_formatter()

        # Hover tooltip and crosshair for all plot types (time, discrete index, XY)
        self._setup_plot_hover()

        self.lines = {}
        self.buffers_y = {}
        self.buffers_x = {}
        self.buffers_x_discrete = deque(maxlen=buffer_size)  # one x per "row" when discrete index is linked
        self.buffer_timestamps = deque(maxlen=buffer_size)  # Store actual timestamps for each data point
        self.buffer_x_change_timestamps = deque(maxlen=buffer_size)  # Timestamp when X variable changed (discrete/variable X)
        self.buffer_x_snapshots = deque(maxlen=buffer_size)  # Snapshot of Y+recipe values when X changed (discrete/variable X)
        self.buffer_size = buffer_size
        self.p2 = None
        self.colors = ['#00E676', '#2979FF', '#FF1744', '#FFEA00', '#AA00FF', '#00B0FF', '#FF9100']
        # Initialize range settings from variable metadata
        # X-axis: use metadata if it's a variable, otherwise default
        if self.is_xy_plot and self.x_axis_source in self.variable_metadata:
            x_meta = self.variable_metadata[self.x_axis_source]
            x_min, x_max = x_meta.get("min", 0.0), x_meta.get("max", 10.0)
        else:
            x_min, x_max = 0.0, 100.0  # Default for time/index
        
        # Y-axis: 2 vars use y_axis_mode (auto/same/dual); 3+ vars use _y_axis_assignments (y1/y2)
        group_ids = [self.variable_metadata.get(v, {}).get("group_id") for v in self.variables]
        same_group = len(self.variables) >= 2 and not self.is_xy_plot and len(set(group_ids)) == 1
        if self.is_xy_plot:
            is_dual_y = False
            self._use_single_axis_for_group = False
            self._left_vars = self.variables
            self._right_vars = []
        elif len(self.variables) == 2:
            self._use_single_axis_for_group = (self.y_axis_mode == "same") or (self.y_axis_mode == "auto" and same_group)
            is_dual_y = (self.y_axis_mode == "dual") or (self.y_axis_mode == "auto" and not same_group)
            self._left_vars = [self.variables[0]] if is_dual_y else self.variables
            self._right_vars = [self.variables[1]] if is_dual_y else []
        else:
            # 3+ variables: assign to y1 or y2 (pyqtgraph supports only 2 Y-axes)
            left_vars = [v for v in self.variables if self._y_axis_assignments.get(v) == "y1"]
            right_vars = [v for v in self.variables if self._y_axis_assignments.get(v) == "y2"]
            if not left_vars and not right_vars:
                left_vars = list(self.variables)
                right_vars = []
            self._left_vars = left_vars
            self._right_vars = right_vars
            is_dual_y = bool(left_vars and right_vars)
            self._use_single_axis_for_group = not is_dual_y
        
        if is_dual_y:
            # Dual Y-axis: left_vars on y1, right_vars on y2 (min/max from first of each for metadata)
            def range_for_vars(vars_list):
                mins, maxs = [], []
                for v in vars_list:
                    if v in self.variable_metadata:
                        m = self.variable_metadata[v]
                        mins.append(m.get("min", 0.0)); maxs.append(m.get("max", 10.0))
                return (min(mins), max(maxs)) if mins else (0.0, 10.0)
            y1_min, y1_max = range_for_vars(self._left_vars)
            y2_min, y2_max = range_for_vars(self._right_vars)
        else:
            # Single Y-axis: combine ranges of all variables
            if self.variables:
                y_mins = []
                y_maxs = []
                for var in self.variables:
                    if var in self.variable_metadata:
                        meta = self.variable_metadata[var]
                        y_mins.append(meta.get("min", 0.0))
                        y_maxs.append(meta.get("max", 10.0))
                
                if y_mins and y_maxs:
                    y1_min, y1_max = min(y_mins), max(y_maxs)
                else:
                    y1_min, y1_max = 0.0, 10.0
            else:
                y1_min, y1_max = 0.0, 10.0
            
            y2_min, y2_max = 0.0, 10.0  # Not used for single axis
        
        self.range_settings = {
            "x": {"auto": True, "min": x_min, "max": x_max},
            "y1": {"auto": True, "min": y1_min, "max": y1_max},
            "y2": {"auto": True, "min": y2_min, "max": y2_max},
            "aligned_y_padding_percent": 5.0,
        }

        if is_dual_y:
            self._setup_dual_axis()
        else:
            self._setup_single_axis()

        # When dual Y has same min/max, we will align both axes to the same scale for overlap comparison
        self._dual_y_same_range = (
            self.p2 is not None
            and self.range_settings["y1"]["min"] == self.range_settings["y2"]["min"]
            and self.range_settings["y1"]["max"] == self.range_settings["y2"]["max"]
        )

        # For time-based plots with X auto: use sliding window so latest value stays visible
        if not self.is_xy_plot and self.range_settings["x"]["auto"]:
            self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)

        # When user zooms/scrolls, stop auto-following X so the view stays fixed; re-enable via "A" button
        self._last_programmatic_x_range = None  # (x_min, x_max) when we call setXRange
        vb = self.plot_widget.plotItem.vb
        if hasattr(vb, "sigRangeChangedManually"):
            vb.sigRangeChangedManually.connect(self._on_x_range_changed_manually)
        elif hasattr(vb, "sigXRangeChanged"):
            vb.sigXRangeChanged.connect(self._on_x_range_changed)

        # Set up limit lines (dashed horizontal lines)
        self._setup_limit_lines()

    def _setup_limit_lines(self):
        """Set up horizontal dashed limit lines for Limit High and Limit Low."""
        # Remove existing limit lines if any
        if self._limit_high_line:
            self.plot_widget.removeItem(self._limit_high_line)
            self._limit_high_line = None
        if self._limit_low_line:
            self.plot_widget.removeItem(self._limit_low_line)
            self._limit_low_line = None
        
        # Create Limit High line
        if self.limit_high_settings.get("enabled"):
            color = self.limit_high_settings.get("color", "#FF5252")
            pen = pg.mkPen(color, width=2, style=Qt.DashLine)
            self._limit_high_line = pg.InfiniteLine(angle=0, movable=False, pen=pen)
            self._limit_high_line.setZValue(0.5)  # Below data lines
            self.plot_widget.addItem(self._limit_high_line, ignoreBounds=True)
            
            # Set initial position
            if self.limit_high_settings.get("type") == "fixed":
                self._limit_high_line.setValue(self.limit_high_settings.get("value", 0))
            # Variable-based: will be updated in update_value()
        
        # Create Limit Low line
        if self.limit_low_settings.get("enabled"):
            color = self.limit_low_settings.get("color", "#9C27B0")
            pen = pg.mkPen(color, width=2, style=Qt.DashLine)
            self._limit_low_line = pg.InfiniteLine(angle=0, movable=False, pen=pen)
            self._limit_low_line.setZValue(0.5)  # Below data lines
            self.plot_widget.addItem(self._limit_low_line, ignoreBounds=True)
            
            # Set initial position
            if self.limit_low_settings.get("type") == "fixed":
                self._limit_low_line.setValue(self.limit_low_settings.get("value", 0))
            # Variable-based: will be updated in update_value()

    def _update_limit_lines_from_variables(self, data_dict):
        """Update variable-based limit lines when data is received."""
        # Update Limit High from variable
        if self._limit_high_line and self.limit_high_settings.get("type") == "variable":
            var_name = self.limit_high_settings.get("variable")
            if var_name and var_name in data_dict:
                try:
                    val = float(data_dict[var_name])
                    self._limit_high_line.setValue(val)
                except (ValueError, TypeError):
                    pass
        
        # Update Limit Low from variable
        if self._limit_low_line and self.limit_low_settings.get("type") == "variable":
            var_name = self.limit_low_settings.get("variable")
            if var_name and var_name in data_dict:
                try:
                    val = float(data_dict[var_name])
                    self._limit_low_line.setValue(val)
                except (ValueError, TypeError):
                    pass

    def set_setpoint_line(self, var_name, enabled, value, color='#00ff00'):
        """Set or update the setpoint line for a variable."""
        self._setpoint_settings[var_name] = {"enabled": enabled, "value": value, "color": color}
        self._update_setpoint_line(var_name)
    
    def set_tolerance_lines(self, var_name, enabled, setpoint, tolerance_pct, color='#ffaa00'):
        """Set or update the tolerance lines for a variable."""
        self._tolerance_settings[var_name] = {
            "enabled": enabled, 
            "setpoint": setpoint, 
            "tolerance_pct": tolerance_pct, 
            "color": color
        }
        self._update_tolerance_lines(var_name)
    
    def _update_setpoint_line(self, var_name):
        """Update or remove the setpoint line for a variable."""
        # Remove existing line if any
        if var_name in self._setpoint_lines and self._setpoint_lines[var_name]:
            try:
                self.plot_widget.removeItem(self._setpoint_lines[var_name])
            except:
                pass
            self._setpoint_lines[var_name] = None
        
        settings = self._setpoint_settings.get(var_name, {})
        if settings.get("enabled"):
            color = settings.get("color", "#00ff00")
            value = settings.get("value", 0)
            pen = pg.mkPen(color, width=2, style=Qt.DashLine)
            line = pg.InfiniteLine(pos=value, angle=0, movable=False, pen=pen)
            line.setZValue(0.5)
            self.plot_widget.addItem(line, ignoreBounds=True)
            self._setpoint_lines[var_name] = line
    
    def _update_tolerance_lines(self, var_name):
        """Update or remove the tolerance lines for a variable."""
        # Remove existing lines if any
        for line_dict, key in [(self._tolerance_low_lines, var_name), (self._tolerance_high_lines, var_name)]:
            if key in line_dict and line_dict[key]:
                try:
                    self.plot_widget.removeItem(line_dict[key])
                except:
                    pass
                line_dict[key] = None
        
        settings = self._tolerance_settings.get(var_name, {})
        if settings.get("enabled"):
            color = settings.get("color", "#ffaa00")
            setpoint = settings.get("setpoint", 0)
            tolerance_pct = settings.get("tolerance_pct", 1.0)
            tol_low = setpoint * (1 - tolerance_pct / 100)
            tol_high = setpoint * (1 + tolerance_pct / 100)
            
            pen = pg.mkPen(color, width=2, style=Qt.DashLine)
            
            line_low = pg.InfiniteLine(pos=tol_low, angle=0, movable=False, pen=pen)
            line_low.setZValue(0.5)
            self.plot_widget.addItem(line_low, ignoreBounds=True)
            self._tolerance_low_lines[var_name] = line_low
            
            line_high = pg.InfiniteLine(pos=tol_high, angle=0, movable=False, pen=pen)
            line_high.setZValue(0.5)
            self.plot_widget.addItem(line_high, ignoreBounds=True)
            self._tolerance_high_lines[var_name] = line_high

    def _on_x_range_changed_manually(self, *args):
        """User zoomed or panned (1-button mode or scroll) – stop auto-following X."""
        if not self.is_xy_plot:
            self.range_settings["x"]["auto"] = False
            if hasattr(self, "btn_follow_x"):
                self.btn_follow_x.setChecked(False)

    def _on_x_range_changed(self, new_min, new_max):
        """If X range changed and it wasn't from our sliding window, user zoomed – stop auto-follow."""
        if self.is_xy_plot:
            return
        if self._last_programmatic_x_range is not None:
            x_min, x_max = self._last_programmatic_x_range
            tol = 1.0  # allow 1 unit tolerance
            if abs(new_min - x_min) <= tol and abs(new_max - x_max) <= tol:
                self._last_programmatic_x_range = None
                return
            self._last_programmatic_x_range = None
        self.range_settings["x"]["auto"] = False
        if hasattr(self, "btn_follow_x"):
            self.btn_follow_x.setChecked(False)

    def _toggle_follow_x(self):
        """Re-enable auto-scroll X (follow latest data). Click 'A' after zooming to follow again."""
        if self.is_xy_plot:
            return
        self.range_settings["x"]["auto"] = self.btn_follow_x.isChecked()
        if self.range_settings["x"]["auto"]:
            self._update_time_plot_x_range()

    def _update_time_plot_x_range(self):
        """Shift X range so the graph shows the latest values (sliding window pinned to the right)."""
        if self.is_xy_plot or not self.range_settings["x"]["auto"]:
            return
        ref_var = self.variables[0] if self.variables else None
        window = self.buffer_size
        if self.is_discrete_index and getattr(self, "discrete_index_linked_variable", None):
            x_list = list(self.buffers_x_discrete)
            if not x_list:
                return
            x_max = x_list[-1]
            x_min = max(1, x_max - window + 1)
        else:
            n = len(self.buffers_y.get(ref_var, [])) if ref_var else len(self.buffer_timestamps)
            if n == 0:
                return
            if self.is_discrete_index:
                x_min = max(1, n - window + 1)
                x_max = n
            else:
                x_min = max(0, n - window)
                x_max = n
        self._last_programmatic_x_range = (x_min, x_max)
        self.plot_widget.plotItem.setXRange(x_min, x_max, padding=0)

    def update_time_display(self):
        """Update the time display label with current day number and hour"""
        now = datetime.now()
        hour = now.hour
        # Show date and time
        if hour != self.start_hour:
            self.start_hour = hour
        date_str = now.strftime("%B %d").replace(" 0", " ")  # e.g. "February 9"
        self.time_display_label.setText(f"{date_str} | Hour {hour:02d}:{now.minute:02d}:{now.second:02d}")
    
    def format_time_from_index(self, index):
        """Convert index to time string showing only minutes, seconds, and milliseconds (MM:SS.mmm)
        Uses the actual timestamp when the signal was received"""
        # Use the stored timestamp for this data point index
        if hasattr(self, 'buffer_timestamps') and len(self.buffer_timestamps) > 0:
            try:
                # Convert index to integer, handling negative and out-of-range values
                idx = int(round(index))
                
                # Clamp index to valid range
                if idx < 0:
                    # Negative index, use first timestamp
                    actual_time = self.buffer_timestamps[0]
                elif idx >= len(self.buffer_timestamps):
                    # Index beyond stored timestamps, use most recent
                    actual_time = self.buffer_timestamps[-1]
                else:
                    # Valid index within range
                    actual_time = self.buffer_timestamps[idx]
            except (IndexError, ValueError, TypeError):
                # Fallback to most recent timestamp if any error occurs
                actual_time = self.buffer_timestamps[-1] if len(self.buffer_timestamps) > 0 else datetime.now()
        else:
            # Fallback: use current time
            actual_time = datetime.now()
        
        # Format as MM:SS.mmm (minutes:seconds.milliseconds)
        minutes = actual_time.minute
        seconds = actual_time.second
        milliseconds = int(actual_time.microsecond / 1000)
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    def setup_time_formatter(self):
        """Set up custom formatter for time axis (Time (Index) only)."""
        class TimeAxisItem(pg.AxisItem):
            def __init__(self, widget, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.widget = widget
                # Preserve axis styling
                self.setPen('#888')
                self.setTextPen('#aaa')
            
            def tickStrings(self, values, scale, spacing):
                """Format tick values as time strings"""
                return [self.widget.format_time_from_index(v) for v in values]
        
        # Replace the bottom axis with our custom time axis
        time_axis = TimeAxisItem(self, orientation='bottom')
        self.plot_widget.plotItem.setAxisItems({'bottom': time_axis})

    def _setup_plot_hover(self):
        """Set up hover tooltip and crosshair for all plot types (time, discrete index, XY)."""
        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.DashLine))
        self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('white', width=1, style=Qt.DashLine))
        self.tooltip = pg.TextItem(anchor=(0, 1), color='#ddd', fill=QColor(0, 0, 0, 150))
        self.tooltip.setZValue(2)
        self.plot_widget.addItem(self.crosshair_v, ignoreBounds=True)
        self.plot_widget.addItem(self.crosshair_h, ignoreBounds=True)
        self.plot_widget.addItem(self.tooltip, ignoreBounds=True)
        self.tooltip.hide()
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def _setup_single_axis(self):
        self.line_delta = None  # No delta line for single variable or XY
        for i, var in enumerate(self.variables):
            color = self.colors[i % len(self.colors)]
            self._add_variable(var, color, self.plot_widget.plotItem)
        # Y-axis label: Name [Unit] or combined for same-group vars
        if self.variables:
            meta = self.variable_metadata
            if getattr(self, "_use_single_axis_for_group", False) and len(self.variables) > 1:
                labels = [meta.get(v, {}).get("display_label", v) for v in self.variables]
                unit = meta.get(self.variables[0], {}).get("unit", "")
                if unit:
                    names_only = [l.rsplit(" [", 1)[0] if " [" in l else l for l in labels]
                    y_label = ", ".join(names_only) + f" [{unit}]"
                else:
                    y_label = ", ".join(labels)
            else:
                y_label = meta.get(self.variables[0], {}).get("display_label", self.variables[0])
            self.plot_widget.setLabel("left", y_label)

    def _setup_dual_axis(self):
        """Setup dual Y-axis: _left_vars on left, _right_vars on right (supports 2 or 3+ variables)."""
        left_vars = getattr(self, "_left_vars", self.variables[:1])
        right_vars = getattr(self, "_right_vars", self.variables[1:2] if len(self.variables) > 1 else [])
        meta = self.variable_metadata
        label1 = ", ".join(meta.get(v, {}).get("display_label", v) for v in left_vars)
        label2 = ", ".join(meta.get(v, {}).get("display_label", v) for v in right_vars)
        p1 = self.plot_widget.plotItem
        color_left = self.colors[0]
        p1.setLabels(left=label1)
        p1.getAxis('left').setPen(color_left)
        p1.getAxis('left').setTextPen(color_left)
        for i, var in enumerate(left_vars):
            self._add_variable(var, self.colors[i % len(self.colors)], p1)

        self.p2 = pg.ViewBox()
        p1.showAxis('right')
        p1.scene().addItem(self.p2)
        p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(p1)
        color_right = self.colors[len(left_vars) % len(self.colors)]
        p1.getAxis('right').setLabel(label2, color=color_right)
        p1.getAxis('right').setPen(color_right)
        p1.getAxis('right').setTextPen(color_right)
        p1.getAxis('right').enableAutoSIPrefix(False)  # Show actual values, not scaled
        for i, var in enumerate(right_vars):
            self._add_variable(var, self.colors[(len(left_vars) + i) % len(self.colors)], self.p2)
        # Delta line (var2 - var1) only when exactly 2 variables
        self.line_delta = pg.PlotCurveItem(name="Delta", pen=pg.mkPen('#FF9800', width=2), antialias=True)
        p1.addItem(self.line_delta)
        self.line_delta.hide()
        
        def updateViews():
            self.p2.setGeometry(p1.vb.sceneBoundingRect())
            self.p2.linkedViewChanged(p1.vb, self.p2.XAxis)
        updateViews()
        p1.vb.sigResized.connect(updateViews)

    def apply_background_theme(self, mode="dark"):
        """Apply dark or light background theme to the plot and header elements. mode is 'dark' or 'light'."""
        if mode == "light":
            bg = "#ffffff"
            axis_pen = "#555"
            text_pen = "#333"
            grid_alpha = 0.25
            header_fg = "#555"
            btn_border = "#999"
            btn_hover = "#ddd"
        else:
            bg = "#1e1e1e"
            axis_pen = "#888"
            text_pen = "#aaa"
            grid_alpha = 0.2
            header_fg = "#888"
            btn_border = "#444"
            btn_hover = "#3e3e42"
        self.plot_widget.setBackground(bg)
        self.plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)
        self.plot_widget.getAxis("left").setPen(axis_pen)
        self.plot_widget.getAxis("bottom").setPen(axis_pen)
        self.plot_widget.getAxis("left").setTextPen(text_pen)
        self.plot_widget.getAxis("bottom").setTextPen(text_pen)
        if self.p2 is not None:
            self.plot_widget.getAxis("right").setPen(axis_pen)
            self.plot_widget.getAxis("right").setTextPen(text_pen)
        # Header elements
        if hasattr(self, "time_display_label"):
            self.time_display_label.setStyleSheet(f"color: {header_fg}; font-size: 11px; margin-right: 10px;")
        _btn_hover_fg = "#333" if mode == "light" else "#e8e8e8"
        _btn_style = f"QPushButton {{ background-color: transparent; color: {header_fg}; border: 1px solid {btn_border}; border-radius: 4px; }} QPushButton:hover {{ background-color: {btn_hover}; color: {_btn_hover_fg}; }}"
        _btn_follow_style = _btn_style + " QPushButton:checked { background-color: #1a6fa5; color: white; border-color: #1a6fa5; }"
        if hasattr(self, "btn_settings") and self.btn_settings:
            self.btn_settings.setStyleSheet(_btn_style)
        if hasattr(self, "btn_follow_x") and self.btn_follow_x:
            self.btn_follow_x.setStyleSheet(_btn_follow_style)
        if hasattr(self, "btn_export_csv") and self.btn_export_csv:
            self.btn_export_csv.setStyleSheet(_btn_style)

    def get_display_title(self):
        """Return the graph title to show (custom if set, else default)."""
        return (self.graph_title or "").strip() or self.graph_default_title

    def _display_label(self, var_name):
        """Return display label for variable (Name [Unit] or variable id)."""
        return self.variable_metadata.get(var_name, {}).get("display_label", var_name)

    def _format_value(self, var_name, value):
        """Format a value with the variable's decimals (from CSV Decimals column; default 2)."""
        if value is None:
            return "N/A"
        try:
            v = float(value)
            decimals = self.variable_metadata.get(var_name, {}).get("decimals", 2)
            return f"{v:.{decimals}f}"
        except (ValueError, TypeError):
            return str(value)

    def set_buffer_size(self, new_size):
        """Resize all buffers to new_size, copying existing data (truncates if smaller)."""
        new_size = max(100, min(500000, int(new_size)))
        if new_size == self.buffer_size:
            return
        # Copy and resize deques
        self.buffer_timestamps = deque(list(self.buffer_timestamps)[-new_size:], maxlen=new_size)
        for var in self.buffers_y:
            self.buffers_y[var] = deque(list(self.buffers_y[var])[-new_size:], maxlen=new_size)
        if self.is_xy_plot:
            for var in self.buffers_x:
                self.buffers_x[var] = deque(list(self.buffers_x[var])[-new_size:], maxlen=new_size)
        self.buffers_x_discrete = deque(list(self.buffers_x_discrete)[-new_size:], maxlen=new_size)
        if hasattr(self, "buffer_x_change_timestamps"):
            self.buffer_x_change_timestamps = deque(list(self.buffer_x_change_timestamps)[-new_size:], maxlen=new_size)
        if hasattr(self, "buffer_x_snapshots"):
            self.buffer_x_snapshots = deque(list(self.buffer_x_snapshots)[-new_size:], maxlen=new_size)
        self.buffer_size = new_size

    def _add_variable(self, var, color, plot_item):
        pen = pg.mkPen(color=color, width=2)
        # XY plot: dots at each point; discrete index: small dots only noticeable
        use_symbol = self.is_xy_plot or self.is_discrete_index
        symbol = 'o' if use_symbol else None
        symbolBrush = color if use_symbol else None
        symbolSize = 3 if self.is_discrete_index else (7 if self.is_xy_plot else None)

        opts = {"pen": pen, "symbol": symbol, "symbolBrush": symbolBrush, "antialias": True}
        if symbolSize is not None:
            opts["symbolSize"] = symbolSize
        if isinstance(plot_item, pg.ViewBox):
            line = pg.PlotCurveItem(name=var, **opts)
            plot_item.addItem(line)
        else:
            line = plot_item.plot(name=var, **opts)
        
        self.lines[var] = line
        self.buffers_y[var] = deque(maxlen=self.buffer_size)
        if self.is_xy_plot:
            self.buffers_x[var] = deque(maxlen=self.buffer_size)
        display_label = self.variable_metadata.get(var, {}).get("display_label", var)
        lbl = QLabel(f"{display_label}: --")
        lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px; margin-right: 15px;")
        self.value_layout.addWidget(lbl)
        self.value_labels[var] = lbl

    def open_range_settings(self):
        try:
            # Get the top-level window as parent
            parent_window = self.window() if self.window() else None
            dialog = RangeConfigDialog(
                self.range_settings, 
                has_dual_y=(self.p2 is not None),
                show_recipes=self.show_recipes_in_tooltip,
                has_two_variables=(len(self.variables) == 2),
                show_delta=getattr(self, "show_delta_on_graph", False),
                parent=parent_window,
                buffer_size=self.buffer_size,
                graph_title=getattr(self, "graph_title", "") or "",
                graph_default_title=getattr(self, "graph_default_title", "") or "",
                display_deadband=getattr(self, "display_deadband", 0) or 0,
                limit_high=getattr(self, "limit_high_settings", None),
                limit_low=getattr(self, "limit_low_settings", None),
                variable_list=getattr(self, "_all_variable_list", []),
            )
            dialog.setModal(True)
            # Position dialog near the gear button of this graph
            if self.btn_settings and self.btn_settings.isVisible():
                gear_global = self.btn_settings.mapToGlobal(self.btn_settings.rect().bottomLeft())
                dialog.move(gear_global.x(), gear_global.y() + 4)
                # Keep dialog on screen
                screen = dialog.screen() or QApplication.primaryScreen()
                if screen:
                    geo = screen.availableGeometry()
                    x = min(max(dialog.x(), geo.x()), geo.x() + geo.width() - dialog.width())
                    y = min(max(dialog.y(), geo.y()), geo.y() + geo.height() - dialog.height())
                    dialog.move(x, y)
            if dialog.exec() == QDialog.Accepted:
                settings = dialog.get_settings()
                self.range_settings = settings
                if not self.is_xy_plot and hasattr(self, "btn_follow_x"):
                    self.btn_follow_x.setChecked(settings["x"]["auto"])

                # Update axis ranges (time-based: X "auto" = sliding window; XY/manual = normal)
                if self.is_xy_plot:
                    self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.XAxis, enable=settings["x"]["auto"])
                    if not settings["x"]["auto"]:
                        self.plot_widget.plotItem.setXRange(settings["x"]["min"], settings["x"]["max"], padding=0)
                else:
                    # Time-based: X "auto" means sliding window that follows latest value
                    self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
                    if settings["x"]["auto"]:
                        self._update_time_plot_x_range()
                    else:
                        self.plot_widget.plotItem.setXRange(settings["x"]["min"], settings["x"]["max"], padding=0)
                self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.YAxis, enable=settings["y1"]["auto"])
                if not settings["y1"]["auto"]:
                    self.plot_widget.plotItem.setYRange(settings["y1"]["min"], settings["y1"]["max"], padding=0)
                if self.p2 and "y2" in settings:
                    self.p2.enableAutoRange(axis=pg.ViewBox.YAxis, enable=settings["y2"]["auto"])
                    if not settings["y2"]["auto"]:
                        self.p2.setYRange(settings["y2"]["min"], settings["y2"]["max"], padding=0)
                # When Y1 and Y2 have same min/max, align both axes to the same scale for overlap comparison
                self._dual_y_same_range = (
                    self.p2 is not None
                    and settings["y1"]["min"] == settings["y2"]["min"]
                    and settings["y1"]["max"] == settings["y2"]["max"]
                )
                self.range_settings["aligned_y_padding_percent"] = settings.get("aligned_y_padding_percent", 5.0)
                if self._dual_y_same_range:
                    self._apply_aligned_dual_y_range()
                
                # Update recipe display setting
                if "show_recipes" in settings:
                    self.show_recipes_in_tooltip = settings["show_recipes"]
                if "show_delta" in settings and len(self.variables) == 2:
                    self.show_delta_on_graph = settings["show_delta"]
                    self._update_delta_line()
                # Buffer size, title, deadband (from RangeConfigDialog)
                if "buffer_size" in settings and settings["buffer_size"] != self.buffer_size:
                    self.set_buffer_size(settings["buffer_size"])
                if "graph_title" in settings:
                    self.graph_title = (settings["graph_title"] or "").strip()
                if "display_deadband" in settings:
                    self.display_deadband = float(settings["display_deadband"]) if settings["display_deadband"] else 0.0
                
                # Update limit lines settings
                if "limit_high" in settings:
                    self.limit_high_settings = settings["limit_high"]
                if "limit_low" in settings:
                    self.limit_low_settings = settings["limit_low"]
                # Recreate limit lines with new settings
                self._setup_limit_lines()
                
                # Update container title label if parent is the graph container
                container = self.parent()
                if container is not None and hasattr(container, "lbl_title"):
                    container.lbl_title.setText(self.get_display_title())
        except Exception as e:
            print(f"Error opening range settings dialog: {e}")
            import traceback
            traceback.print_exc()

    def _notify_export_success(self, message):
        """Show export success (toast on main window if available, else QMessageBox)."""
        w = self.window()
        while w and not hasattr(w, "_show_toast"):
            w = w.parent() if hasattr(w, "parent") and callable(w.parent) else None
        if w and hasattr(w, "_show_toast"):
            w._show_toast(message)
        else:
            QMessageBox.information(self, "Export", message)

    def export_graph_data_to_csv(self, path=None):
        """Export current graph buffer data to CSV with semicolon separator.
        
        - Time-based X: every timestamp
        - Discrete/variable X: only rows when X changed (one per dose/etc), with Y and recipe at that moment
        - XY plot: only rows when X variable changed
        
        If path is given, save directly. Otherwise show file dialog.
        Returns True if export succeeded, False otherwise.
        """
        # Determine export mode and row indices
        is_discrete_linked = (self.is_discrete_index and getattr(self, "discrete_index_linked_variable", None))
        timestamps = list(self.buffer_timestamps) if hasattr(self, "buffer_timestamps") else []
        recipe_params = getattr(self, "recipe_params", []) or []

        if is_discrete_linked:
            # Discrete/variable X: one row per X change
            x_list = list(self.buffers_x_discrete)
            n = len(x_list)
            if n == 0:
                QMessageBox.warning(self, "No data", "No data to export (no X-axis changes yet).")
                return
            x_change_ts = list(getattr(self, "buffer_x_change_timestamps", []))
            x_snapshots = list(getattr(self, "buffer_x_snapshots", []))
            row_indices = list(range(n))  # All rows (each is an X change)
        elif self.is_xy_plot:
            # XY: only rows where X changed (x values stored per Y variable, same for all)
            x_src = self.buffers_x.get(self.variables[0], []) if self.variables else []
            x_data = list(x_src)
            n_raw = len(x_data)
            if n_raw == 0:
                QMessageBox.warning(self, "No data", "No data to export.")
                return
            row_indices = []
            for i in range(n_raw):
                if i == 0 or (i < len(x_data) and x_data[i] != x_data[i - 1]):
                    row_indices.append(i)
            n = len(row_indices)
            if n == 0:
                QMessageBox.warning(self, "No data", "No data to export.")
                return
        else:
            # Time-based: every timestamp
            buffers = [list(self.buffers_y.get(v, [])) for v in self.variables]
            if not buffers:
                QMessageBox.warning(self, "No data", "No data to export.")
                return
            n = max(len(b) for b in buffers)
            if n == 0:
                QMessageBox.warning(self, "No data", "No data to export.")
                return
            row_indices = list(range(n))

            use_actual_timestamps = True
            fixed_interval_ms = None
            if not self.is_xy_plot and path is None:
                dialog = QDialog(self)
                dialog.setWindowTitle("CSV Export - Timestamp Options")
                dialog.setModal(True)
                dialog.resize(350, 180)
                dialog.setStyleSheet("background-color: #2b2b2b; color: white;")
                layout = QVBoxLayout(dialog)
                layout.addWidget(QLabel("Choose timestamp format for X-axis:"))
                radio_actual = QRadioButton("Actual timestamps (when signal was received)")
                radio_actual.setChecked(True)
                radio_fixed = QRadioButton("Fixed interval:")
                interval_layout = QHBoxLayout()
                interval_spin = QSpinBox()
                interval_spin.setRange(1, 10000)
                interval_spin.setValue(int(self.comm_speed * 1000))
                interval_spin.setSuffix(" ms")
                interval_spin.setEnabled(False)
                interval_layout.addWidget(interval_spin)
                interval_layout.addStretch()
                radio_fixed.toggled.connect(lambda checked: interval_spin.setEnabled(checked))
                layout.addWidget(radio_actual)
                layout.addWidget(radio_fixed)
                layout.addLayout(interval_layout)
                layout.addSpacing(10)
                btn_layout = QHBoxLayout()
                btn_ok = QPushButton("Export")
                btn_cancel = QPushButton("Cancel")
                btn_ok.clicked.connect(dialog.accept)
                btn_cancel.clicked.connect(dialog.reject)
                btn_layout.addStretch()
                btn_layout.addWidget(btn_ok)
                btn_layout.addWidget(btn_cancel)
                layout.addLayout(btn_layout)
                if dialog.exec() != QDialog.Accepted:
                    return None
                use_actual_timestamps = radio_actual.isChecked()
                fixed_interval_ms = interval_spin.value() if radio_fixed.isChecked() else None

        user_initiated = path is None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Export graph data", "", "CSV (*.csv)")
        if not path:
            return None

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                header_cols = ["Index", "Timestamp"]
                if self.is_xy_plot:
                    header_cols.append(self.x_axis_source)
                elif is_discrete_linked:
                    header_cols.append(self.discrete_index_linked_variable)
                header_cols.extend(self.variables)
                header_cols.extend(recipe_params)
                if self.limit_high_settings.get("enabled", False):
                    header_cols.append("LimitHigh" if self.limit_high_settings.get("type") != "variable" else f"LimitHigh ({self.limit_high_settings.get('variable', 'N/A')})")
                if self.limit_low_settings.get("enabled", False):
                    header_cols.append("LimitLow" if self.limit_low_settings.get("type") != "variable" else f"LimitLow ({self.limit_low_settings.get('variable', 'N/A')})")
                f.write(";".join(header_cols) + "\n")

                max_idx = max(row_indices) + 1 if row_indices else 0
                limit_high_vals = self._export_limit_values(max_idx, "high") if max_idx else []
                limit_low_vals = self._export_limit_values(max_idx, "low") if max_idx else []

                for row_idx, orig_i in enumerate(row_indices, start=1):
                    row = [str(row_idx)]
                    ts_str = ""
                    if is_discrete_linked:
                        if orig_i < len(x_change_ts) and x_change_ts[orig_i]:
                            ts_str = x_change_ts[orig_i].strftime("%M:%S.") + f"{x_change_ts[orig_i].microsecond // 1000:03d}"
                    elif self.is_xy_plot:
                        if orig_i < len(timestamps) and timestamps[orig_i]:
                            ts_str = timestamps[orig_i].strftime("%M:%S.") + f"{timestamps[orig_i].microsecond // 1000:03d}"
                    else:
                        if use_actual_timestamps and orig_i < len(timestamps) and timestamps[orig_i]:
                            ts_str = timestamps[orig_i].strftime("%M:%S.") + f"{timestamps[orig_i].microsecond // 1000:03d}"
                        elif fixed_interval_ms is not None:
                            total_ms = orig_i * fixed_interval_ms
                            ts_str = f"{(total_ms // 60000) % 60:02d}:{(total_ms // 1000) % 60:02d}.{total_ms % 1000:03d}"
                    row.append(ts_str)

                    if self.is_xy_plot:
                        x_data_xy = list(self.buffers_x.get(self.variables[0], [])) if self.variables else []
                        row.append(str(x_data_xy[orig_i]) if orig_i < len(x_data_xy) and x_data_xy[orig_i] is not None else "")
                    elif is_discrete_linked:
                        x_list = list(self.buffers_x_discrete)
                        row.append(str(x_list[orig_i]) if orig_i < len(x_list) and x_list[orig_i] is not None else "")

                    if is_discrete_linked and orig_i < len(x_snapshots):
                        snap = x_snapshots[orig_i]
                        for v in self.variables:
                            val = snap.get(v)
                            row.append(str(val) if val is not None and val != "" else "")
                        for p in recipe_params:
                            val = snap.get(p)
                            row.append(str(val) if val is not None and val != "" else "")
                    else:
                        for v in self.variables:
                            buf = self.buffers_y.get(v, [])
                            val = buf[orig_i] if orig_i < len(buf) else ""
                            row.append(str(val) if val is not None and val != "" else "")
                        for p in recipe_params:
                            val = self.latest_values_cache.get(p)
                            row.append(str(val) if val is not None and val != "" else "")

                    if self.limit_high_settings.get("enabled", False) and orig_i < len(limit_high_vals):
                        row.append(str(limit_high_vals[orig_i]) if limit_high_vals[orig_i] not in (None, "") else "")
                    if self.limit_low_settings.get("enabled", False) and orig_i < len(limit_low_vals):
                        row.append(str(limit_low_vals[orig_i]) if limit_low_vals[orig_i] not in (None, "") else "")
                    f.write(";".join(row) + "\n")
            if user_initiated:
                self._notify_export_success(f"Exported to {os.path.basename(path)}")
            return True
        except Exception as e:
            logging.warning(f"Export CSV failed: {e}")
            if user_initiated:
                QMessageBox.warning(self, "Export failed", str(e))
            return False

    def _export_limit_values(self, n, which):
        """Helper to build limit value list for export."""
        settings = self.limit_high_settings if which == "high" else self.limit_low_settings
        if not settings.get("enabled", False):
            return []
        if settings.get("type") == "fixed":
            return [settings.get("value", "")] * n
        var = settings.get("variable", "")
        if var in self.buffers_y:
            buf = list(self.buffers_y.get(var, []))
            return (buf + [self.latest_values_cache.get(var, "")] * n)[:n]
        return [self.latest_values_cache.get(var, "")] * n

    def _apply_aligned_dual_y_range(self):
        """When dual Y has same min/max, set both axes to the same range so series overlap for comparison."""
        if not getattr(self, "_dual_y_same_range", False) or self.p2 is None or len(self.variables) != 2:
            return
        rs = self.range_settings
        if rs["y1"]["auto"] and rs["y2"]["auto"]:
            # Compute union range from both buffers and apply to both axes
            all_vals = []
            for v in self.variables:
                buf = self.buffers_y.get(v, [])
                for y in buf:
                    if y is not None and isinstance(y, (int, float)) and not np.isnan(y) and not np.isinf(y):
                        all_vals.append(float(y))
            if all_vals:
                y_min, y_max = min(all_vals), max(all_vals)
                padding_pct = rs.get("aligned_y_padding_percent", 5.0) / 100.0  # 0 = exact alignment
                pad = (y_max - y_min) * padding_pct if (y_max - y_min) > 0 else 0.1
                y_min = y_min - pad
                y_max = y_max + pad
                self.plot_widget.plotItem.vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
                self.p2.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
                self.plot_widget.plotItem.vb.setYRange(y_min, y_max, padding=0)
                self.p2.setYRange(y_min, y_max, padding=0)
        else:
            # Manual: both use the same range (y1 and y2 are equal)
            y_min, y_max = rs["y1"]["min"], rs["y1"]["max"]
            self.plot_widget.plotItem.vb.setYRange(y_min, y_max, padding=0)
            self.p2.setYRange(y_min, y_max, padding=0)

    def _update_delta_line(self):
        """Update or show/hide the delta line (var2 - var1) when exactly 2 variables."""
        if getattr(self, "line_delta", None) is None or len(self.variables) != 2:
            return
        if not self.show_delta_on_graph:
            self.line_delta.hide()
            return
        v1, v2 = self.variables[0], self.variables[1]
        b1 = list(self.buffers_y.get(v1, []))
        b2 = list(self.buffers_y.get(v2, []))
        n = min(len(b1), len(b2))
        if n == 0:
            self.line_delta.hide()
            return
        delta = []
        for i in range(n):
            try:
                a, b = float(b1[i]), float(b2[i])
                if not (np.isnan(a) or np.isnan(b) or np.isinf(a) or np.isinf(b)):
                    delta.append(b - a)
            except (ValueError, TypeError):
                continue
        if delta:
            if self.is_discrete_index:
                if getattr(self, "discrete_index_linked_variable", None):
                    x_delta = list(self.buffers_x_discrete)[:len(delta)]
                else:
                    x_delta = list(range(1, len(delta) + 1))
                self.line_delta.setData(x_delta, delta)
            else:
                self.line_delta.setData(delta)
            self.line_delta.show()
        else:
            self.line_delta.hide()

    def _apply_deadband(self, value):
        """Quantize value by display deadband (0 = no change)."""
        if not getattr(self, "display_deadband", 0) or not isinstance(value, (int, float)):
            return value
        try:
            return round(float(value) / self.display_deadband) * self.display_deadband
        except (ValueError, TypeError, ZeroDivisionError):
            return value

    def update_data(self, var_name, y_value, x_value=None):
        # Discrete index linked variable: advance index only when its value changes (e.g. 1→2, 2→3)
        if getattr(self, "discrete_index_linked_variable", None) and var_name == self.discrete_index_linked_variable:
            try:
                new_val = float(y_value) if y_value is not None else None
            except (ValueError, TypeError):
                new_val = y_value
            if new_val != self._discrete_index_last_linked_value:
                self._discrete_index_last_linked_value = new_val
                self._discrete_index_counter += 1
                self.buffers_x_discrete.append(self._discrete_index_counter)
                self.buffer_x_change_timestamps.append(datetime.now())
                # Snapshot Y and recipe values at the moment X changed (for CSV export)
                snap = dict(self.latest_values_cache) if self.latest_values_cache else {}
                self.buffer_x_snapshots.append(snap)
            return
        if var_name not in self.variables:
            return

        # Skip None values to prevent plotting errors
        if y_value is None:
            return

        # Convert to float if possible, otherwise skip
        try:
            y_value = float(y_value)
        except (ValueError, TypeError):
            return
        # Apply display deadband (quantize)
        y_value = self._apply_deadband(y_value)

        # Store timestamp when adding a new data point (when buffer length increases)
        # All variables in the same communication cycle share the same timestamp
        current_buffer_length = len(self.buffers_y.get(var_name, []))
        self.buffers_y[var_name].append(y_value)
        new_buffer_length = len(self.buffers_y[var_name])

        # If buffer length increased, this is a new data point - store its timestamp
        if new_buffer_length > current_buffer_length:
            # Capture the exact timestamp when this signal was received
            data_timestamp = datetime.now()
            # Only store if we don't already have a timestamp for this position
            if len(self.buffer_timestamps) < new_buffer_length:
                self.buffer_timestamps.append(data_timestamp)

        if self.is_xy_plot:
            if x_value is None: x_value = 0.0
            try:
                x_value = float(x_value)
            except (ValueError, TypeError):
                x_value = 0.0
            self.buffers_x[var_name].append(x_value)
            # Filter out None values and convert to numeric before plotting
            x_data = [float(x) for x in self.buffers_x[var_name] if x is not None and isinstance(x, (int, float)) and not np.isnan(x)]
            y_data = [float(y) for y in self.buffers_y[var_name] if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
            # Match lengths by taking minimum
            min_len = min(len(x_data), len(y_data))
            if min_len > 0:
                try:
                    self.lines[var_name].setData(x_data[:min_len], y_data[:min_len])
                except Exception as e:
                    logging.warning(f"Error plotting {var_name}: {e}")
        else:
            # Filter out None values and convert to numpy array for plotting
            y_data = [float(y) for y in self.buffers_y[var_name] if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
            if y_data:
                try:
                    if self.is_discrete_index:
                        if getattr(self, "discrete_index_linked_variable", None):
                            x_list = list(self.buffers_x_discrete)
                            min_len = min(len(x_list), len(y_data))
                            if min_len > 0:
                                x_data = x_list[:min_len]
                                y_plot = y_data[:min_len]
                                self.lines[var_name].setData(x_data, y_plot)
                        else:
                            x_data = list(range(1, len(y_data) + 1))
                            self.lines[var_name].setData(x_data, y_data)
                    else:
                        self.lines[var_name].setData(y_data)
                except Exception as e:
                    logging.warning(f"Error plotting {var_name}: {e}")
        
        # Calculate min/max with None filtering
        data = [d for d in self.buffers_y[var_name] if d is not None and isinstance(d, (int, float)) and not np.isnan(d)]
        if data:
            try:
                min_v, max_v = min(data), max(data)
            except (ValueError, TypeError):
                min_v, max_v = 0.0, 0.0
        else:
            min_v, max_v = 0.0, 0.0
        
        dl = self._display_label(var_name)
        fmt = self._format_value(var_name, y_value)
        min_fmt = self._format_value(var_name, min_v)
        max_fmt = self._format_value(var_name, max_v)
        txt = f"{dl}: {fmt} <span style='font-size:10px; color:#aaa;'>(Min:{min_fmt} Max:{max_fmt})</span>"
        self.value_labels[var_name].setText(txt)
        self._update_time_plot_x_range()
        if len(self.variables) == 2:
            self._update_delta_line()
            self._apply_aligned_dual_y_range()

    def set_static_data(self, x_data, y_series):
        """Load static (offline) data once: x_data = list or None (use index), y_series = {var_name: [y values]}."""
        n = 0
        for var_name in self.variables:
            if var_name not in y_series:
                continue
            ys = y_series[var_name]
            clean = []
            for v in ys:
                try:
                    f = float(v)
                    if not (np.isnan(f) or np.isinf(f)):
                        clean.append(f)
                except (ValueError, TypeError):
                    pass
            self.buffers_y[var_name] = deque(clean, maxlen=self.buffer_size)
            n = max(n, len(clean))
        if n == 0:
            return
        if x_data is None or len(x_data) < n:
            x_list = list(range(1, n + 1)) if self.is_discrete_index else list(range(n))
        else:
            x_list = []
            for v in x_data[:n]:
                try:
                    f = float(v)
                    if not (np.isnan(f) or np.isinf(f)):
                        x_list.append(f)
                except (ValueError, TypeError):
                    pass
            if len(x_list) != n:
                x_list = list(range(1, n + 1)) if self.is_discrete_index else list(range(n))
        for var_name in self.variables:
            if var_name not in self.buffers_y or var_name not in self.lines:
                continue
            y_list = list(self.buffers_y[var_name])
            min_len = min(len(x_list), len(y_list))
            if min_len == 0:
                continue
            if self.is_xy_plot:
                self.buffers_x[var_name] = deque(x_list[:min_len], maxlen=self.buffer_size)
                self.lines[var_name].setData(x_list[:min_len], y_list[:min_len])
            elif self.is_discrete_index:
                x_plot = list(range(1, min_len + 1))
                self.lines[var_name].setData(x_plot, y_list[:min_len])
            else:
                self.lines[var_name].setData(y_list[:min_len])
            if y_list:
                last_val = y_list[-1]
                data = [d for d in y_list if isinstance(d, (int, float)) and not np.isnan(d)]
                min_v = min(data) if data else 0.0
                max_v = max(data) if data else 0.0
                dl = self._display_label(var_name)
                fmt = self._format_value(var_name, last_val)
                min_fmt = self._format_value(var_name, min_v)
                max_fmt = self._format_value(var_name, max_v)
                txt = f"{dl}: {fmt} <span style='font-size:10px; color:#aaa;'>(Min:{min_fmt} Max:{max_fmt})</span>"
                self.value_labels[var_name].setText(txt)
        if len(self.variables) == 2:
            self._update_delta_line()

    def update_data_array(self, var_name, array_values):
        """Add all array values at once to the graph.
        Arrays contain oversampled data that should be plotted together.
        Timestamps are distributed over the communication cycle time.
        For discrete index mode without linked variable, the array REPLACES
        the buffer (history array use case) instead of appending."""
        if var_name not in self.variables:
            return
        # When discrete index is linked to a variable, X is driven by that variable's updates only; skip array Y updates
        if getattr(self, "discrete_index_linked_variable", None):
            return
        if not array_values or len(array_values) == 0:
            return
        
        # Get current timestamp
        current_time = datetime.now()
        array_length = len(array_values)
        
        # For discrete index without linked variable: REPLACE buffer with array (history array use case)
        # This prevents accumulation when the PLC sends the complete history array each cycle
        if self.is_discrete_index:
            clean_values = []
            for val in array_values:
                try:
                    y_val = float(val)
                    if np.isnan(y_val) or np.isinf(y_val):
                        continue
                    y_val = self._apply_deadband(y_val)
                    clean_values.append(y_val)
                except (ValueError, TypeError):
                    continue
            if clean_values:
                self.buffers_y[var_name] = deque(clean_values, maxlen=self.buffer_size)
        else:
            # Calculate time step: distribute array values over the communication cycle
            # Assume array values were sampled over the communication cycle time
            time_step = self.comm_speed / array_length if array_length > 0 else 0
            
            # Add all array values to buffer with distributed timestamps
            for i, val in enumerate(array_values):
                try:
                    y_val = float(val)
                    if np.isnan(y_val) or np.isinf(y_val):
                        continue
                    y_val = self._apply_deadband(y_val)
                    # Add to buffer
                    self.buffers_y[var_name].append(y_val)
                    
                    # Calculate timestamp for this value (distributed over comm cycle)
                    # First value gets current time, subsequent values are spaced by time_step
                    value_timestamp = current_time - timedelta(seconds=(array_length - i - 1) * time_step)
                    
                    # Add timestamp
                    self.buffer_timestamps.append(value_timestamp)
                    
                except (ValueError, TypeError):
                    continue
        
        # Update the plot with all new data
        if self.is_xy_plot:
            # For XY plots, if this is the x_axis_source, we need to update all dependent variables
            # Otherwise, use the x values from x_axis_source
            if var_name == self.x_axis_source:
                # This array is the x-axis source - update x buffer
                for val in array_values:
                    try:
                        x_val = float(val)
                        if not (np.isnan(x_val) or np.isinf(x_val)):
                            self.buffers_x[var_name].append(x_val)
                    except (ValueError, TypeError):
                        continue
                # Update all variables that use this as x-axis
                for other_var in self.variables:
                    if other_var != var_name:
                        x_data = [float(x) for x in self.buffers_x.get(var_name, []) if x is not None and isinstance(x, (int, float)) and not np.isnan(x)]
                        y_data = [float(y) for y in self.buffers_y.get(other_var, []) if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
                        min_len = min(len(x_data), len(y_data))
                        if min_len > 0 and other_var in self.lines:
                            try:
                                self.lines[other_var].setData(x_data[:min_len], y_data[:min_len])
                            except Exception as e:
                                logging.warning(f"Error plotting {other_var}: {e}")
            else:
                # Regular variable in XY plot - use x values from x_axis_source
                x_data = [float(x) for x in self.buffers_x.get(self.x_axis_source, []) if x is not None and isinstance(x, (int, float)) and not np.isnan(x)]
                y_data = [float(y) for y in self.buffers_y[var_name] if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
                min_len = min(len(x_data), len(y_data))
                if min_len > 0:
                    try:
                        self.lines[var_name].setData(x_data[:min_len], y_data[:min_len])
                    except Exception as e:
                        logging.warning(f"Error plotting {var_name}: {e}")
        else:
            # For time-based or discrete-index plots, plot y values
            y_data = [float(y) for y in self.buffers_y[var_name] if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
            if y_data:
                try:
                    if self.is_discrete_index:
                        x_data = list(range(1, len(y_data) + 1))
                        self.lines[var_name].setData(x_data, y_data)
                    else:
                        self.lines[var_name].setData(y_data)
                except Exception as e:
                    logging.warning(f"Error plotting {var_name}: {e}")
        
        # Update value label with latest value from this array update
        # This is the most recent value from the newly received array
        latest_value = array_values[-1] if array_values else 0.0
        data = [d for d in self.buffers_y[var_name] if d is not None and isinstance(d, (int, float)) and not np.isnan(d)]
        if data:
            try:
                min_v, max_v = min(data), max(data)
            except (ValueError, TypeError):
                min_v, max_v = 0.0, 0.0
        else:
            min_v, max_v = 0.0, 0.0
        
        dl = self._display_label(var_name)
        fmt = self._format_value(var_name, latest_value)
        min_fmt = self._format_value(var_name, min_v)
        max_fmt = self._format_value(var_name, max_v)
        txt = f"{dl}: {fmt} <span style='font-size:10px; color:#aaa;'>(Min:{min_fmt} Max:{max_fmt})</span>"
        self.value_labels[var_name].setText(txt)
        self._update_time_plot_x_range()
        if len(self.variables) == 2:
            self._update_delta_line()
            self._apply_aligned_dual_y_range()

    def _get_filtered_y_data(self, var):
        """Return filtered y data list (matching what's actually displayed on plot) for a variable."""
        # First try to get data directly from the plot line (most accurate for tooltip)
        line = self.lines.get(var)
        if line is not None:
            try:
                x_plot, y_plot = line.getData()
                if y_plot is not None and len(y_plot) > 0:
                    return list(y_plot)
            except Exception:
                pass
        # Fallback to buffer
        raw = self.buffers_y.get(var, [])
        return [float(y) for y in raw if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
    
    def _get_filtered_x_data(self, var):
        """Return filtered x data list (matching what's actually displayed on plot) for a variable."""
        line = self.lines.get(var)
        if line is not None:
            try:
                x_plot, y_plot = line.getData()
                if x_plot is not None and len(x_plot) > 0:
                    return list(x_plot)
            except Exception:
                pass
        return []

    def mouse_moved(self, evt):
        pos = evt[0]
        # Check mouse is over the plot (use plot widget scene rect so discrete and time behave the same)
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            self.tooltip.hide()
            self.crosshair_v.hide()
            self.crosshair_h.hide()
            return
        vb = self.plot_widget.plotItem.vb
        mouse_point = vb.mapSceneToView(pos)
        ref_var = self.variables[0] if self.variables else None
        if not ref_var:
            return

        # Capture all filtered data ONCE as a synchronized snapshot from the actual plot lines
        # This ensures the tooltip shows exactly what is displayed on the plot
        filtered_y_data = {var: self._get_filtered_y_data(var) for var in self.variables}
        ref_y_filtered = filtered_y_data.get(ref_var, [])
        n_pts_filtered = len(ref_y_filtered)

        if self.is_xy_plot:
            x_raw = self.buffers_x.get(ref_var, [])
            x_data = np.array([float(x) for x in x_raw if x is not None and isinstance(x, (int, float)) and not np.isnan(x)])
        elif self.is_discrete_index and getattr(self, "discrete_index_linked_variable", None):
            n_x = len(self.buffers_x_discrete)
            min_len = min(n_x, n_pts_filtered)
            if min_len == 0:
                self.tooltip.hide()
                self.crosshair_v.hide()
                self.crosshair_h.hide()
                return
            x_data = np.array(list(self.buffers_x_discrete)[:min_len], dtype=float)
            # Truncate y data to match x data length
            filtered_y_data = {var: filtered_y_data[var][:min_len] for var in self.variables}
        elif self.is_discrete_index:
            # For discrete index without linked variable, use x data from plot line to stay synchronized
            ref_x_from_plot = self._get_filtered_x_data(ref_var)
            if ref_x_from_plot:
                x_data = np.array(ref_x_from_plot, dtype=float)
            else:
                x_data = np.arange(1, n_pts_filtered + 1, dtype=float) if n_pts_filtered > 0 else np.array([])
        else:
            x_data = np.arange(n_pts_filtered, dtype=float) if n_pts_filtered > 0 else np.array([])
        if len(x_data) == 0:
            self.tooltip.hide()
            self.crosshair_v.hide()
            self.crosshair_h.hide()
            return

        idx = np.abs(x_data - mouse_point.x()).argmin()
        if idx >= len(x_data):
            return
        x_val = x_data[idx]

        html = f"<div style='background-color: #333; color: white; padding: 8px; border-radius: 4px;'>"
        if self.is_xy_plot:
            x_fmt = self._format_value(self.x_axis_source, x_val)
            html += f"<b>{self.x_axis_source}: {x_fmt}</b><br/>"
        elif self.is_discrete_index:
            html += f"<b>Index: {int(x_val)}</b><br/>"
        else:
            # Get the actual timestamp from buffer_timestamps corresponding to this index
            idx_int = int(round(idx))
            if hasattr(self, 'buffer_timestamps') and len(self.buffer_timestamps) > 0:
                if idx_int < 0:
                    timestamp = self.buffer_timestamps[0]
                elif idx_int >= len(self.buffer_timestamps):
                    timestamp = self.buffer_timestamps[-1]
                else:
                    timestamp = self.buffer_timestamps[idx_int]
                time_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
            else:
                time_str = self.format_time_from_index(idx)
            html += f"<b>Time: {time_str}</b><br/>"
        html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"

        # Look up y values using the synchronized snapshot
        for var in self.variables:
            y_data = filtered_y_data[var]
            if y_data and idx < len(y_data):
                y_val = y_data[idx]
                color = self.lines[var].opts['pen'].color().name()
                y_fmt = self._format_value(var, y_val)
                html += f"<span style='color: {color}; font-weight: bold;'>{var}: {y_fmt}</span><br/>"

        if len(self.variables) == 2:
            y1_data = filtered_y_data.get(self.variables[0], [])
            y2_data = filtered_y_data.get(self.variables[1], [])
            if y1_data and y2_data and idx < len(y1_data) and idx < len(y2_data):
                try:
                    v1, v2 = float(y1_data[idx]), float(y2_data[idx])
                    if not (np.isnan(v1) or np.isnan(v2)):
                        delta = v2 - v1
                        # Use max decimals of the two variables for delta
                        d1 = self.variable_metadata.get(self.variables[0], {}).get("decimals", 2)
                        d2 = self.variable_metadata.get(self.variables[1], {}).get("decimals", 2)
                        dec = max(d1, d2)
                        delta_fmt = f"{delta:.{dec}f}"
                        html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
                        html += f"<span style='color: #FF9800; font-weight: bold;'>Delta ({self.variables[1]} − {self.variables[0]}): {delta_fmt}</span><br/>"
                except (ValueError, TypeError):
                    pass

        if self.show_recipes_in_tooltip and self.recipe_params:
            html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
            html += "<b style='color: #FFEA00;'>Recipe Parameters:</b><br/>"
            for param in self.recipe_params:
                value = self.latest_values_cache.get(param, "N/A")
                val_str = self._format_value(param, value)
                html += f"<span style='color: #ccc;'>{param.replace('_', ' ')}:</span> <b>{val_str}</b><br/>"
        
        # Show Limit Lines if enabled
        has_limit_high = self.limit_high_settings.get("enabled", False)
        has_limit_low = self.limit_low_settings.get("enabled", False)
        if has_limit_high or has_limit_low:
            html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
            html += "<b style='color: #ccc;'>Limits:</b><br/>"
            
            if has_limit_high:
                color_high = self.limit_high_settings.get("color", "#FF5252")
                if self.limit_high_settings.get("type") == "fixed":
                    val_high = self.limit_high_settings.get("value", 0)
                    html += f"<span style='color: {color_high};'>▬ ▬ Limit High: <b>{val_high}</b></span><br/>"
                elif self.limit_high_settings.get("type") == "variable":
                    var_name = self.limit_high_settings.get("variable", "")
                    val_high = self.latest_values_cache.get(var_name, "N/A")
                    try:
                        val_high = float(val_high)
                        val_str = f"{val_high:.4g}"
                    except (ValueError, TypeError):
                        val_str = str(val_high)
                    html += f"<span style='color: {color_high};'>▬ ▬ Limit High ({var_name}): <b>{val_str}</b></span><br/>"
            
            if has_limit_low:
                color_low = self.limit_low_settings.get("color", "#9C27B0")
                if self.limit_low_settings.get("type") == "fixed":
                    val_low = self.limit_low_settings.get("value", 0)
                    html += f"<span style='color: {color_low};'>▬ ▬ Limit Low: <b>{val_low}</b></span><br/>"
                elif self.limit_low_settings.get("type") == "variable":
                    var_name = self.limit_low_settings.get("variable", "")
                    val_low = self.latest_values_cache.get(var_name, "N/A")
                    try:
                        val_low = float(val_low)
                        val_str = f"{val_low:.4g}"
                    except (ValueError, TypeError):
                        val_str = str(val_low)
                    html += f"<span style='color: {color_low};'>▬ ▬ Limit Low ({var_name}): <b>{val_str}</b></span><br/>"
        
        html += "</div>"

        self.tooltip.setHtml(html)
        x_range = vb.viewRange()[0]
        x_min, x_max = x_range[0], x_range[1]
        x_span = x_max - x_min
        if x_span > 0 and mouse_point.x() > x_min + 0.65 * x_span:
            self.tooltip.setAnchor((1, 1))
        else:
            self.tooltip.setAnchor((0, 1))
        self.tooltip.setPos(mouse_point.x(), mouse_point.y())
        self.tooltip.show()
        self.crosshair_v.setPos(x_val)
        self.crosshair_v.show()
        # Horizontal crosshair: snap to the reference variable's Y value at this index
        ref_y_data = filtered_y_data.get(ref_var, [])
        if ref_y_data and idx < len(ref_y_data):
            self.crosshair_h.setPos(float(ref_y_data[idx]))
            self.crosshair_h.show()
        else:
            self.crosshair_h.hide()


class _GraphAreaWithBackground(QWidget):
    """Widget that draws a highly transparent background image behind the graph area (not the menu)."""
    def __init__(self, image_path, opacity=0.12, parent=None):
        super().__init__(parent)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._pixmap = QPixmap(image_path) if image_path and os.path.isfile(image_path) else QPixmap()
        self.setStyleSheet("background-color: #1e1e1e;")  # base so gaps are dark

    def paintEvent(self, event):
        if self._pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation
        )
        painter.drawPixmap(self.rect(), scaled)
        painter.end()
        super().paintEvent(event)


class _CustomTitleBar(QWidget):
    """Custom title bar that embeds the QMenuBar alongside the window title and controls."""

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: #1e1e1e;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(0)

        # App icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        icon = _app_icon()
        if not icon.isNull():
            pix = icon.pixmap(16, 16)
            self.icon_label.setPixmap(pix)
        layout.addWidget(self.icon_label)
        layout.addSpacing(10)

        # Menu bar (embedded) – fixed width so it doesn't eat the draggable area
        self.menu_bar = QMenuBar()
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: transparent;
                color: #cccccc;
                border: none;
                font-size: 12px;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 6px 10px;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background-color: #3e3e42;
                color: #ffffff;
            }
            QMenuBar::item:pressed {
                background-color: #007ACC;
                color: #ffffff;
            }
        """)
        self.menu_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        layout.addWidget(self.menu_bar)

        # Draggable spacer – this empty label lets mouse events pass to the title bar for dragging
        self._drag_spacer = QLabel()
        self._drag_spacer.setStyleSheet("background: transparent;")
        self._drag_spacer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._drag_spacer, 1)  # stretch factor = 1

        # Window control buttons (minimize, maximize/restore, close)
        btn_style_normal = """
            QPushButton {
                background-color: transparent; color: #999999; border: none;
                font-family: "Segoe MDL2 Assets"; font-size: 10px;
                padding: 0px; min-width: 46px; min-height: 32px;
            }
            QPushButton:hover { background-color: #3e3e42; color: #ffffff; }
        """
        btn_style_close = """
            QPushButton {
                background-color: transparent; color: #999999; border: none;
                font-family: "Segoe MDL2 Assets"; font-size: 10px;
                padding: 0px; min-width: 46px; min-height: 32px;
            }
            QPushButton:hover { background-color: #e81123; color: #ffffff; }
        """

        self.btn_minimize = QPushButton("\uE921")  # Minimize glyph
        self.btn_minimize.setStyleSheet(btn_style_normal)
        self.btn_minimize.clicked.connect(parent.showMinimized)

        self.btn_maximize = QPushButton("\uE922")  # Maximize glyph
        self.btn_maximize.setStyleSheet(btn_style_normal)
        self.btn_maximize.clicked.connect(self._toggle_maximize)

        self.btn_close = QPushButton("\uE8BB")  # Close glyph
        self.btn_close.setStyleSheet(btn_style_close)
        self.btn_close.clicked.connect(parent.close)

        layout.addWidget(self.btn_minimize)
        layout.addWidget(self.btn_maximize)
        layout.addWidget(self.btn_close)

    def _toggle_maximize(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            self.btn_maximize.setText("\uE922")
        else:
            self._parent.showMaximized()
            self.btn_maximize.setText("\uE923")  # Restore glyph

    # ── Dragging ──
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()

    def apply_theme(self, mode="dark"):
        """Apply dark or light theme to title bar and menu."""
        if mode == "light":
            bg = "#f0f0f0"
            fg = "#333333"
            menu_hover = "#d0d0d0"
            menu_selected_fg = "#333333"
        else:
            bg = "#1e1e1e"
            fg = "#cccccc"
            menu_hover = "#3e3e42"
            menu_selected_fg = "#ffffff"
        self.setStyleSheet(f"background-color: {bg};")
        self.menu_bar.setStyleSheet(f"""
            QMenuBar {{ background-color: transparent; color: {fg}; border: none; font-size: 12px; }}
            QMenuBar::item {{ background-color: transparent; padding: 6px 10px; border-radius: 3px; }}
            QMenuBar::item:selected {{ background-color: {menu_hover}; color: {menu_selected_fg}; }}
            QMenuBar::item:pressed {{ background-color: #007ACC; color: white; }}
        """)


class MainWindow(QMainWindow):
    data_signal = Signal(str, object)
    status_signal = Signal(str, str, object)  # status_type, message, details

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DecAutomation Studio")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1280, 800)
        _icon = _app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        self.latest_values = {}
        self.all_variables = []
        self.variable_metadata = {}  # Store min/max from CSV files
        self.recipe_params = []  # Will be loaded from recipe_variables CSV
        _ext = os.path.join(os.path.dirname(__file__), "external")
        # Auto-discover DB-named CSVs (e.g. exchange_variables_DB20.csv), fall back to plain names
        try:
            from external.variable_loader import discover_csv_files
            _disc_ex, _disc_rec = discover_csv_files(_ext)
            self.exchange_variables_path = _disc_ex or os.path.join(_ext, "exchange_variables.csv")
            self.recipe_variables_path = _disc_rec or os.path.join(_ext, "recipe_variables.csv")
        except Exception:
            self.exchange_variables_path = os.path.join(_ext, "exchange_variables.csv")
            self.recipe_variables_path = os.path.join(_ext, "recipe_variables.csv")
        self.apply_theme()

        # Custom title bar with embedded menu
        self._title_bar = _CustomTitleBar(self)
        self._create_menu_bar()

        # Wrap everything in a vertical layout: title bar on top, content below
        self._root_widget = QWidget()
        self._root_widget.setStyleSheet("QWidget#_rootWidget { border: 1px solid #3e3e42; }")
        self._root_widget.setObjectName("_rootWidget")
        _root = self._root_widget
        _root_layout = QVBoxLayout(_root)
        _root_layout.setContentsMargins(1, 0, 1, 1)  # thin border for resize grip visibility
        _root_layout.setSpacing(0)
        _root_layout.addWidget(self._title_bar)

        self.main_widget = QWidget()
        _root_layout.addWidget(self.main_widget, 1)
        # Small resize grip in bottom-right corner
        _grip = QSizeGrip(self)
        _grip.setFixedSize(12, 12)
        _grip.setStyleSheet("QSizeGrip { background: transparent; }")
        _grip_row = QHBoxLayout()
        _grip_row.setContentsMargins(0, 0, 0, 0)
        _grip_row.addStretch()
        _grip_row.addWidget(_grip)
        _root_layout.addLayout(_grip_row)
        self.setCentralWidget(_root)
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        self.main_layout.addWidget(self.splitter)

        self.sidebar = QWidget()
        self.sidebar.setStyleSheet("background-color: #252526;")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)

        # Track offline mode (mutually exclusive with Online/Connection)
        self._offline_mode_active = False
        self.connection_popup = None
        self.load_popup = None

        # Shared label width and row height
        _label_w = 82
        _row_h = 28

        # Connection popup content: Client, IP, Variable files, DB name, Recording, PLC Trigger
        # Connection UI: collapsible "details" (Client, IP, Variable files) + Recording + Trigger
        connection_details_layout = QVBoxLayout()
        connection_details_layout.setSpacing(6)

        # Client Device Type dropdown
        device_type_layout = QHBoxLayout()
        device_type_label = QLabel("Client:")
        device_type_label.setStyleSheet("color: #aaa; font-size: 11px;")
        device_type_label.setFixedWidth(_label_w)
        device_type_label.setMinimumHeight(_row_h)
        device_type_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["Snap7", "ADS", "Simulation"])
        self.device_type_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.device_type_combo.setMinimumHeight(_row_h)
        self.device_type_combo.setToolTip("Snap7: Siemens S7 (e.g. S7-1500). ADS: Beckhoff (EtherCAT). Simulation: CSV-based simulator (no address).")
        self.device_type_combo.currentTextChanged.connect(self.on_device_type_changed)
        device_type_layout.addWidget(device_type_label)
        device_type_layout.addWidget(self.device_type_combo)
        connection_details_layout.addLayout(device_type_layout)

        # Address row (IP for Snap7, Target for ADS; hidden for Simulation)
        self.address_row = QWidget()
        address_row_layout = QHBoxLayout(self.address_row)
        address_row_layout.setContentsMargins(0, 0, 0, 0)
        self.address_label = QLabel("IP:")
        self.address_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.address_label.setFixedWidth(_label_w)
        self.address_label.setMinimumHeight(_row_h)
        self.address_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.ip_input = QLineEdit("192.168.0.20")
        self.ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.ip_input.setMinimumHeight(_row_h)
        self.ip_input.setPlaceholderText("192.168.0.20")
        address_row_layout.addWidget(self.address_label)
        address_row_layout.addWidget(self.ip_input)
        connection_details_layout.addWidget(self.address_row)
        # PC IP row (ADS only)
        self.pc_ip_row = QWidget()
        pc_ip_layout = QHBoxLayout(self.pc_ip_row)
        pc_ip_layout.setContentsMargins(0, 0, 0, 0)
        self.pc_ip_label = QLabel("PC IP:")
        self.pc_ip_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.pc_ip_label.setFixedWidth(_label_w)
        self.pc_ip_label.setMinimumHeight(_row_h)
        self.pc_ip_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.pc_ip_input = QLineEdit("")
        self.pc_ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.pc_ip_input.setMinimumHeight(_row_h)
        self.pc_ip_input.setPlaceholderText("192.168.1.100 or 192.168.1.100.1.1")
        self.pc_ip_input.setToolTip("Your PC's IP (or AmsNetId). This is the address used for the ADS route on the PLC.")
        pc_ip_layout.addWidget(self.pc_ip_label)
        pc_ip_layout.addWidget(self.pc_ip_input)
        connection_details_layout.addWidget(self.pc_ip_row)
        self.pc_ip_row.setVisible(False)

        # Variable files
        vars_label = QLabel("Variable files:")
        vars_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 4px;")
        vars_label.setToolTip(
            "To update CSVs: Disconnect → edit file on disk → click Reload (or Browse to same file), then Connect. No app restart needed."
        )
        connection_details_layout.addWidget(vars_label)
        exchange_row = QHBoxLayout()
        exchange_row.setSpacing(4)
        self.exchange_path_edit = QLineEdit()
        self.exchange_path_edit.setReadOnly(True)
        self.exchange_path_edit.setStyleSheet("background-color: #333; color: #aaa; border: 1px solid #555; padding: 4px; font-size: 10px;")
        self.exchange_path_edit.setPlaceholderText("Exchange variables CSV (browse)")
        self.browse_exchange_btn = QPushButton("Exchange…")
        self.browse_exchange_btn.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 4px;")
        self.browse_exchange_btn.setToolTip("Choose CSV with variable names (column 'Variable'). Use different files for Snap7 vs ADS or between PLCs.")
        self.browse_exchange_btn.clicked.connect(self.browse_exchange_variables)
        exchange_row.addWidget(self.exchange_path_edit)
        exchange_row.addWidget(self.browse_exchange_btn)
        connection_details_layout.addLayout(exchange_row)
        recipe_row = QHBoxLayout()
        recipe_row.setSpacing(4)
        self.recipe_path_edit = QLineEdit()
        self.recipe_path_edit.setReadOnly(True)
        self.recipe_path_edit.setStyleSheet("background-color: #333; color: #aaa; border: 1px solid #555; padding: 4px; font-size: 10px;")
        self.recipe_path_edit.setPlaceholderText("Recipe variables CSV (browse)")
        self.browse_recipe_btn = QPushButton("Recipes…")
        self.browse_recipe_btn.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 4px;")
        self.browse_recipe_btn.setToolTip("Choose CSV with recipe variable names. Optional; use any filename.")
        self.browse_recipe_btn.clicked.connect(self.browse_recipe_variables)
        self.reload_vars_btn = QPushButton("Reload")
        self.reload_vars_btn.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 4px;")
        self.reload_vars_btn.setToolTip("Reload exchange and recipe CSVs from current paths (e.g. after editing files). Disconnect first.")
        self.reload_vars_btn.clicked.connect(self.reload_variables)
        recipe_row.addWidget(self.recipe_path_edit)
        recipe_row.addWidget(self.browse_recipe_btn)
        recipe_row.addWidget(self.reload_vars_btn)
        connection_details_layout.addLayout(recipe_row)

        # DB File Name (editable, default Data_DDMMYYYY)
        db_name_row = QHBoxLayout()
        db_name_row.setSpacing(4)
        db_name_label = QLabel("DB File Name:")
        db_name_label.setStyleSheet("color: #aaa; font-size: 10px;")
        db_name_label.setFixedWidth(80)
        db_name_row.addWidget(db_name_label)
        self.db_filename_edit = QLineEdit()
        self.db_filename_edit.setStyleSheet("background-color: #333; color: #ccc; border: 1px solid #555; padding: 4px; font-size: 10px;")
        self.db_filename_edit.setToolTip(
            "Base name of the daily recording database (.duckdb extension added automatically).\n"
            "Default: Data_DDMMYYYY (e.g. Data_09022026 for February 9, 2026).\n"
            "This field updates automatically each day; you can customise it before connecting."
        )
        self._set_default_db_filename()
        db_name_row.addWidget(self.db_filename_edit)
        db_ext_label = QLabel(".duckdb")
        db_ext_label.setStyleSheet("color: #888; font-size: 10px;")
        db_name_row.addWidget(db_ext_label)
        connection_details_layout.addLayout(db_name_row)

        # Line below Variable files (no frame)
        vars_sep = QFrame()
        vars_sep.setFrameShape(QFrame.Shape.HLine)
        vars_sep.setStyleSheet("background-color: #3e3e42; max-height: 1px; border: none;")
        vars_sep.setFixedHeight(1)
        connection_details_layout.addWidget(vars_sep)

        # Collapsible connection details widget
        self.connection_details_content = QWidget()
        self.connection_details_content.setLayout(connection_details_layout)

        # Connection frame: same box style as PLC TRIGGER had (framed)
        connection_frame = QFrame()
        connection_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                margin-top: 6px;
            }
        """)
        connection_frame_layout = QVBoxLayout(connection_frame)
        connection_frame_layout.setContentsMargins(8, 6, 8, 8)
        connection_frame_layout.setSpacing(6)

        conn_header_row = QWidget()
        conn_header_layout = QHBoxLayout(conn_header_row)
        conn_header_layout.setContentsMargins(0, 0, 0, 0)
        conn_header_label = QLabel("CONNECTION")
        conn_header_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #b0b0b0; margin-bottom: 5px; margin-top: 10px;")
        conn_header_layout.addWidget(conn_header_label)
        conn_header_layout.addStretch()
        self.connection_toggle_btn = QPushButton("▼")
        self.connection_toggle_btn.setFixedSize(22, 22)
        self.connection_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.connection_toggle_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: none; font-size: 10px; }
            QPushButton:hover { color: white; }
        """)
        self.connection_toggle_btn.clicked.connect(self._toggle_connection_section)
        conn_header_layout.addWidget(self.connection_toggle_btn)
        connection_frame_layout.addWidget(conn_header_row)
        connection_frame_layout.addWidget(self.connection_details_content)

        # Recording section (Snap7 only): when to record – time interval or variable change
        self.recording_section = QWidget()
        recording_layout = QVBoxLayout(self.recording_section)
        recording_layout.setContentsMargins(0, 4, 0, 0)
        recording_layout.setSpacing(6)
        rec_ref_row = QHBoxLayout()
        rec_ref_label = QLabel("Recording:")
        rec_ref_label.setStyleSheet("color: #aaa; font-size: 11px;")
        rec_ref_label.setFixedWidth(_label_w)
        rec_ref_label.setMinimumHeight(_row_h)
        rec_ref_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.recording_ref_combo = QComboBox()
        self.recording_ref_combo.addItem("Time (interval)", "time")
        self.recording_ref_combo.addItem("Variable (on change)", "variable")
        self.recording_ref_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.recording_ref_combo.setMinimumHeight(_row_h)
        self.recording_ref_combo.setToolTip("Time: record at fixed interval (min 100 ms). Variable: record only when selected variable changes (saves space).")
        self.recording_ref_combo.currentIndexChanged.connect(self._on_recording_ref_changed)
        rec_ref_row.addWidget(rec_ref_label)
        rec_ref_row.addWidget(self.recording_ref_combo)
        recording_layout.addLayout(rec_ref_row)
        rec_interval_row = QHBoxLayout()
        rec_interval_label = QLabel("Interval (ms):")
        rec_interval_label.setStyleSheet("color: #aaa; font-size: 11px;")
        rec_interval_label.setFixedWidth(_label_w)
        rec_interval_label.setMinimumHeight(_row_h)
        rec_interval_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.recording_interval_ms = QSpinBox()
        self.recording_interval_ms.setRange(100, 3600000)
        self.recording_interval_ms.setValue(500)
        self.recording_interval_ms.setSuffix(" ms")
        self.recording_interval_ms.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.recording_interval_ms.setMinimumHeight(_row_h)
        self.recording_interval_ms.setToolTip("Minimum 100 ms when recording by time.")
        rec_interval_row.addWidget(rec_interval_label)
        rec_interval_row.addWidget(self.recording_interval_ms)
        self.recording_interval_row_widget = QWidget()
        self.recording_interval_row_widget.setLayout(rec_interval_row)
        # Interval (ms) goes to sidebar; do NOT add to recording_layout
        rec_trigger_row = QHBoxLayout()
        rec_trigger_label = QLabel("Trigger var:")
        rec_trigger_label.setStyleSheet("color: #aaa; font-size: 11px;")
        rec_trigger_label.setFixedWidth(_label_w)
        rec_trigger_label.setMinimumHeight(_row_h)
        rec_trigger_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.recording_trigger_combo = QComboBox()
        self.recording_trigger_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.recording_trigger_combo.setMinimumHeight(_row_h)
        self.recording_trigger_combo.setToolTip("Record all variables and recipes when this variable changes (e.g. dose counter).")
        rec_trigger_row.addWidget(rec_trigger_label)
        rec_trigger_row.addWidget(self.recording_trigger_combo)
        self.recording_trigger_row_widget = QWidget()
        self.recording_trigger_row_widget.setLayout(rec_trigger_row)
        self.recording_trigger_row_widget.setVisible(False)
        recording_layout.addWidget(self.recording_trigger_row_widget)
        connection_frame_layout.addWidget(self.recording_section)
        self.recording_section.setVisible(False)

        # PLC Trigger section: same framed style as CONNECTION (match exactly)
        self.trigger_frame = QFrame()
        self.trigger_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                margin-top: 6px;
            }
        """)
        trigger_frame_layout = QVBoxLayout(self.trigger_frame)
        trigger_frame_layout.setContentsMargins(8, 6, 8, 8)
        trigger_frame_layout.setSpacing(6)

        trigger_header = QWidget()
        trigger_header_layout = QHBoxLayout(trigger_header)
        trigger_header_layout.setContentsMargins(0, 0, 0, 0)
        self.trigger_section_label = QLabel("PLC TRIGGER")
        self.trigger_section_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #b0b0b0; margin-bottom: 5px; margin-top: 10px;")
        trigger_header_layout.addWidget(self.trigger_section_label)
        trigger_header_layout.addStretch()
        self.trigger_toggle_btn = QPushButton("▼")
        self.trigger_toggle_btn.setFixedSize(22, 22)
        self.trigger_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.trigger_toggle_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: none; font-size: 10px; }
            QPushButton:hover { color: white; }
        """)
        self.trigger_toggle_btn.clicked.connect(self._toggle_trigger_section)
        trigger_header_layout.addWidget(self.trigger_toggle_btn)
        trigger_frame_layout.addWidget(trigger_header)

        self.trigger_content = QWidget()
        trigger_layout = QVBoxLayout(self.trigger_content)
        trigger_layout.setContentsMargins(0, 2, 0, 0)
        trigger_layout.setSpacing(6)
        var_select_layout = QHBoxLayout()
        var_label = QLabel("Variable:")
        var_label.setStyleSheet("color: #aaa; font-size: 11px;")
        var_label.setFixedWidth(_label_w)
        var_label.setMinimumHeight(_row_h)
        var_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.trigger_var_combo = QComboBox()
        self.trigger_var_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.trigger_var_combo.setMinimumHeight(_row_h)
        self.trigger_var_combo.setToolTip("Select boolean variable to trigger")
        var_select_layout.addWidget(var_label)
        var_select_layout.addWidget(self.trigger_var_combo)
        trigger_layout.addLayout(var_select_layout)
        self.trigger_btn = QPushButton("⚡ Trigger")
        self.trigger_btn.setCursor(Qt.PointingHandCursor)
        self.trigger_btn.setEnabled(False)
        self.trigger_btn.setStyleSheet("""
            QPushButton { background-color: #c46200; color: white; font-weight: bold; padding: 10px; border: none; border-radius: 3px; }
            QPushButton:hover { background-color: #d97706; }
            QPushButton:pressed { background-color: #a05200; }
            QPushButton:disabled { background-color: #3a3a3a; color: #707070; }
        """)
        self.trigger_btn.clicked.connect(self.toggle_trigger)
        trigger_layout.addWidget(self.trigger_btn)
        trigger_frame_layout.addWidget(self.trigger_content)

        self.trigger_active = False
        self.paused = False

        # Connection popup content: connection frame + trigger frame
        connection_popup_content = QWidget()
        connection_popup_layout = QVBoxLayout(connection_popup_content)
        connection_popup_layout.setContentsMargins(8, 8, 8, 8)
        connection_popup_layout.addWidget(connection_frame)
        connection_popup_layout.addWidget(self.trigger_frame)
        self.connection_popup = ConnectionPopup(connection_popup_content, self)

        # Sidebar: Connect, Disconnect, Pause, Speed, Interval only
        ip_connect_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.setStyleSheet("""
            QPushButton { background-color: #1a6fa5; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 3px; }
            QPushButton:hover { background-color: #2580b8; }
            QPushButton:pressed { background-color: #0d5a8a; }
        """)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setCursor(Qt.PointingHandCursor)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton { background-color: #6b2d2d; color: #e8e8e8; font-weight: bold; padding: 5px; border: 1px solid #5a2525; border-radius: 3px; }
            QPushButton:hover { background-color: #7a3535; }
            QPushButton:pressed { background-color: #5a2020; }
            QPushButton:disabled { background-color: #3a3a3a; color: #707070; border-color: #2d2d30; }
        """)
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setToolTip("Pause live updates. Values stay as-is so you can zoom, pan, or export.")
        self.pause_btn.setStyleSheet("""
            QPushButton { background-color: #4a4a4a; color: #e0e0e0; font-weight: bold; padding: 5px; border: 1px solid #3e3e42; border-radius: 3px; }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QPushButton:disabled { background-color: #3a3a3a; color: #707070; border-color: #2d2d30; }
        """)
        ip_connect_layout.addWidget(self.connect_btn)
        ip_connect_layout.addWidget(self.disconnect_btn)
        ip_connect_layout.addWidget(self.pause_btn)

        speed_layout = QHBoxLayout()
        speed_label = QLabel("Speed (s):")
        speed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        speed_label.setFixedWidth(_label_w)
        speed_label.setMinimumHeight(_row_h)
        speed_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.speed_input = QLineEdit("0.05")
        self.speed_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.speed_input.setMinimumHeight(_row_h)
        self.speed_input.setToolTip("Communication cycle time in seconds (default: 0.05)")
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_input)

        sidebar_controls_frame = QFrame()
        sidebar_controls_frame.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 3px; margin-top: 6px; }
        """)
        sidebar_controls_layout = QVBoxLayout(sidebar_controls_frame)
        sidebar_controls_layout.setContentsMargins(8, 6, 8, 8)
        sidebar_controls_layout.setSpacing(6)
        sidebar_controls_layout.addLayout(ip_connect_layout)
        sidebar_controls_layout.addLayout(speed_layout)
        sidebar_controls_layout.addWidget(self.recording_interval_row_widget)
        self.sidebar_interval_row = self.recording_interval_row_widget
        self.sidebar_layout.addWidget(sidebar_controls_frame)
        self.pause_btn.clicked.connect(self.toggle_pause)

        # Offline panel: Load CSV or Recording DB + history (for Load popup)
        self.offline_panel = QWidget()
        offline_main = QVBoxLayout(self.offline_panel)
        offline_main.setContentsMargins(0, 5, 0, 0)
        offline_main.setSpacing(6)

        # Row 1: Load buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.offline_load_csv_btn = QPushButton("Load CSV")
        self.offline_load_csv_btn.setCursor(Qt.PointingHandCursor)
        self.offline_load_csv_btn.setStyleSheet("""
            QPushButton { background-color: #1a6fa5; color: white; font-weight: bold; padding: 7px 12px; border: none; border-radius: 3px; font-size: 11px; }
            QPushButton:hover { background-color: #2580b8; }
            QPushButton:pressed { background-color: #0d5a8a; }
        """)
        self.offline_load_csv_btn.setToolTip("Load a CSV file into memory for plotting")
        self.offline_load_csv_btn.clicked.connect(self.load_offline_csv)
        btn_row.addWidget(self.offline_load_csv_btn)

        self.offline_load_db_btn = QPushButton("Load Recording DB")
        self.offline_load_db_btn.setCursor(Qt.PointingHandCursor)
        self.offline_load_db_btn.setStyleSheet("""
            QPushButton { background-color: #5a3a8a; color: white; font-weight: bold; padding: 7px 12px; border: none; border-radius: 3px; font-size: 11px; }
            QPushButton:hover { background-color: #6a4a9a; }
            QPushButton:pressed { background-color: #4a2a7a; }
        """)
        self.offline_load_db_btn.setToolTip("Browse a .duckdb recording file to load for plotting")
        self.offline_load_db_btn.clicked.connect(self.load_offline_duckdb_file)
        btn_row.addWidget(self.offline_load_db_btn)
        offline_main.addLayout(btn_row)

        # Row 2: Recording history (available daily .duckdb files)
        history_frame = QFrame()
        history_frame.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 4px; }
        """)
        history_layout = QVBoxLayout(history_frame)
        history_layout.setContentsMargins(6, 6, 6, 6)
        history_layout.setSpacing(4)
        history_title = QLabel("Recording History (.duckdb)")
        history_title.setStyleSheet("font-weight: bold; color: #aaa; font-size: 10px; border: none;")
        history_layout.addWidget(history_title)
        self.offline_history_list = QListWidget()
        self.offline_history_list.setMaximumHeight(120)
        self.offline_history_list.setStyleSheet("""
            QListWidget { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 3px; color: #ccc; font-size: 10px; outline: 0; }
            QListWidget::item { padding: 4px 6px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background-color: #094771; color: white; }
            QListWidget::item:hover { background-color: #3e3e42; }
        """)
        self.offline_history_list.setToolTip("Double-click a day to load it, or select and click 'Load Selected Day'")
        self.offline_history_list.itemDoubleClicked.connect(self._load_selected_history_day)
        history_layout.addWidget(self.offline_history_list)
        history_btn_row = QHBoxLayout()
        history_btn_row.setSpacing(4)
        self.offline_load_selected_btn = QPushButton("Load Selected Day")
        self.offline_load_selected_btn.setCursor(Qt.PointingHandCursor)
        self.offline_load_selected_btn.setStyleSheet("""
            QPushButton { background-color: #3a5a3a; color: white; font-size: 10px; padding: 4px 8px; border: none; border-radius: 3px; }
            QPushButton:hover { background-color: #4a6a4a; }
        """)
        self.offline_load_selected_btn.clicked.connect(self._load_selected_history_day)
        history_btn_row.addWidget(self.offline_load_selected_btn)
        self.offline_refresh_btn = QPushButton("Refresh")
        self.offline_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.offline_refresh_btn.setStyleSheet("""
            QPushButton { background-color: #444; color: #ccc; font-size: 10px; padding: 4px 8px; border: none; border-radius: 3px; }
            QPushButton:hover { background-color: #555; }
        """)
        self.offline_refresh_btn.clicked.connect(self._refresh_offline_history)
        history_btn_row.addWidget(self.offline_refresh_btn)
        history_btn_row.addStretch()
        history_layout.addLayout(history_btn_row)
        offline_main.addWidget(history_frame)

        # Row 3: Status labels (loaded file + memory)
        self.offline_path_label = QLabel("No file loaded")
        self.offline_path_label.setStyleSheet("color: #888; font-size: 10px;")
        self.offline_path_label.setWordWrap(True)
        offline_main.addWidget(self.offline_path_label)
        self.offline_memory_label = QLabel("")
        self.offline_memory_label.setStyleSheet("color: #6a9; font-size: 10px;")
        self.offline_memory_label.setWordWrap(True)
        offline_main.addWidget(self.offline_memory_label)

        self.load_popup = LoadPopup(self.offline_panel, self)

        # Offline state: DuckDB connection and column list (set when CSV loaded)
        self.offline_db = None
        self.offline_csv_path = None
        self.offline_columns = []

        self.lbl_vars = QLabel("DATA POINTS")
        self.lbl_vars.setStyleSheet("font-weight: bold; font-size: 12px; color: #888; margin-bottom: 5px; margin-top: 10px;")
        self.sidebar_layout.addWidget(self.lbl_vars)
        self.var_list = QListWidget()
        self.var_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.var_list.setStyleSheet("""
            QListWidget { background-color: #333; border: 1px solid #3e3e42; border-radius: 4px; color: #f0f0f0; outline: 0; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #3e3e42; }
            QListWidget::item:selected { background-color: #094771; color: white; }
            QListWidget::item:hover { background-color: #3e3e42; }
        """)
        self.sidebar_layout.addWidget(self.var_list, 1)
        self.btn_add_graph = QPushButton("Open Selected in Graph")
        self.btn_add_graph.setCursor(Qt.PointingHandCursor)
        self.btn_add_graph.setStyleSheet("""
            QPushButton { background-color: #1a6fa5; color: white; font-weight: bold; padding: 12px; border: none; border-radius: 3px; }
            QPushButton:hover { background-color: #2580b8; }
            QPushButton:pressed { background-color: #0d5a8a; }
        """)
        self.btn_add_graph.clicked.connect(self.add_new_graph)
        self.sidebar_layout.addWidget(self.btn_add_graph)

        # Analytics button - opens a separate window with statistics for all graphs
        self.btn_analytics = QPushButton("📊 Open Analytics")
        self.btn_analytics.setCursor(Qt.PointingHandCursor)
        self.btn_analytics.setStyleSheet("""
            QPushButton { background-color: #4a4a4a; color: #e0e0e0; font-weight: bold; padding: 10px; border: 1px solid #3e3e42; border-radius: 3px; }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
        """)
        self.btn_analytics.setToolTip("Open Analytics window showing real-time statistics and distribution histograms for all plotted graphs")
        self.btn_analytics.clicked.connect(self.open_analytics_window)
        self.sidebar_layout.addWidget(self.btn_analytics)
        
        # Hidden combo for graph config load/save/delete (used by menu bar actions)
        self.config_load_combo = QComboBox()
        self.config_load_combo.hide()
        self._refresh_config_list()

        # Analytics window instance (created on demand)
        self.analytics_window = None

        # Initialize communication status before creating panel
        self.setup_comm_info_panel()

        # Communication Info Panel (collapsible)
        self.comm_info_panel = self.create_comm_info_panel()
        self.sidebar_layout.addWidget(self.comm_info_panel)

        self.splitter.addWidget(self.sidebar)

        # Graph area: background image (highly transparent) behind scroll area
        _base = os.path.dirname(os.path.abspath(__file__))
        _bg_path = os.path.join(_base, "Images", "dec_background_endToEnd_bottomRight.png")
        self.graph_area_widget = _GraphAreaWithBackground(_bg_path, opacity=0.12, parent=self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; } "
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.scroll_content.setAttribute(Qt.WA_TranslucentBackground, True)
        self.graphs_layout = QVBoxLayout(self.scroll_content)
        self.graphs_layout.setContentsMargins(10, 10, 10, 10)

        self.graph_splitter = QSplitter(Qt.Vertical)
        self.graph_splitter.setStyleSheet("QSplitter::handle { background-color: #3e3e42; }")
        self.graph_splitter.setHandleWidth(4)

        self.graphs_layout.addWidget(self.graph_splitter)

        self.scroll_area.setWidget(self.scroll_content)
        layout = QVBoxLayout(self.graph_area_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
        self.splitter.addWidget(self.graph_area_widget)
        self.splitter.setSizes([300, 980])

        self.graphs = []
        self.plc_thread = None
        self.ads_thread = None
        self.simulator_thread = None
        self._during_init = True

        self.connect_btn.clicked.connect(self.start_plc_thread)
        self.disconnect_btn.clicked.connect(self.disconnect_plc)
        self.data_signal.connect(self.update_plot)
        self.status_signal.connect(self.update_comm_status)
        self.speed_input.editingFinished.connect(self.update_speed_while_connected)
        self.on_device_type_changed(self.device_type_combo.currentText())
        self._update_variable_path_display()
        self._load_last_config()
        self._during_init = False
        self._apply_graph_background_theme()

        # Subtle RAM usage indicator (bottom-left, almost hidden)
        self.ram_label = QLabel("", self)
        self.ram_label.setStyleSheet(
            "color: #555; font-size: 9px; background: transparent; padding: 2px 6px;"
        )
        self.ram_label.setToolTip("Current application RAM usage (resident set size)")
        self.ram_label.move(6, self.height() - 18)
        self.ram_label.raise_()
        self._update_ram_label()

        # Toast notification label (auto-dismiss, non-blocking)
        self._toast_label = QLabel("", self)
        self._toast_label.setStyleSheet(
            "background-color: rgba(30, 30, 30, 220); color: #ddd; font-size: 11px;"
            "padding: 8px 16px; border-radius: 6px; border: 1px solid #555;"
        )
        self._toast_label.setWordWrap(True)
        self._toast_label.setMaximumWidth(420)
        self._toast_label.hide()
        self._toast_timer = QTimer()
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)
        self.ram_timer = QTimer()
        self.ram_timer.timeout.connect(self._update_ram_label)
        self.ram_timer.start(5000)  # Update every 5 seconds

    def _load_last_config(self):
        """Restore last saved connection config (device type, IPs, variable paths) from cache."""
        s = QSettings("DecAutomation", "Studio")
        device = s.value("device_type")
        if device and device in ("Snap7", "ADS", "Simulation"):
            idx = self.device_type_combo.findText(device)
            if idx >= 0:
                self.device_type_combo.setCurrentIndex(idx)
        ip = s.value("ip_address")
        if ip:
            self.ip_input.setText(ip)
        pc_ip = s.value("pc_ip")
        if pc_ip:
            self.pc_ip_input.setText(pc_ip)
        ex = s.value("exchange_path")
        if ex:
            self.exchange_variables_path = ex
        rec = s.value("recipe_path")
        if rec:
            self.recipe_variables_path = rec
        speed = s.value("speed")
        if speed:
            self.speed_input.setText(speed)
        # Restore Connection section collapsed state
        conn_collapsed = s.value("connection_section_collapsed", False)
        if isinstance(conn_collapsed, str):
            conn_collapsed = conn_collapsed.lower() in ("true", "1", "yes")
        if hasattr(self, "connection_details_content") and hasattr(self, "connection_toggle_btn"):
            self.connection_details_content.setVisible(not conn_collapsed)
            self.connection_toggle_btn.setText("▲" if conn_collapsed else "▼")
        # Restore PLC Trigger section collapsed state (collapsed = more space for Data Points)
        collapsed = s.value("trigger_section_collapsed", False)
        if isinstance(collapsed, str):
            collapsed = collapsed.lower() in ("true", "1", "yes")
        if hasattr(self, "trigger_content") and hasattr(self, "trigger_toggle_btn"):
            self.trigger_content.setVisible(not collapsed)
            self.trigger_toggle_btn.setText("▲" if collapsed else "▼")
        self.on_device_type_changed(self.device_type_combo.currentText())
        self._update_variable_path_display()
        self.load_variables()

    def _save_last_config(self):
        """Save current connection config so next run shows the latest (e.g. ADS, IPs, variable paths)."""
        s = QSettings("DecAutomation", "Studio")
        s.setValue("device_type", self.device_type_combo.currentText())
        s.setValue("ip_address", self.ip_input.text().strip())
        s.setValue("pc_ip", self.pc_ip_input.text().strip())
        s.setValue("exchange_path", self.exchange_variables_path or "")
        s.setValue("recipe_path", self.recipe_variables_path or "")
        s.setValue("speed", self.speed_input.text().strip())
        s.sync()

    def _set_default_db_filename(self):
        """Set the DB filename field to today's default: Data_DDMMYYYY."""
        from external.plc_thread import PLCThread
        import datetime as _dt
        default_name = PLCThread.default_db_filename_for_date(_dt.date.today())
        self.db_filename_edit.setText(default_name)

    def _update_variable_path_display(self):
        """Refresh the exchange/recipe CSV path display (basename or full path)."""
        self.exchange_path_edit.setText(self.exchange_variables_path or "")
        self.exchange_path_edit.setToolTip(self.exchange_variables_path or "No file chosen")
        self.recipe_path_edit.setText(self.recipe_variables_path or "")
        self.recipe_path_edit.setToolTip(self.recipe_variables_path or "No file chosen")

    def browse_exchange_variables(self):
        """Let user choose exchange variables CSV (any name); reload variable list."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select exchange variables CSV", self.exchange_variables_path or "",
            "CSV (*.csv);;All files (*)"
        )
        if path:
            self.exchange_variables_path = os.path.normpath(path)
            self._update_variable_path_display()
            self.load_variables()

    def browse_recipe_variables(self):
        """Let user choose recipe variables CSV (any name); reload variable list."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select recipe variables CSV", self.recipe_variables_path or "",
            "CSV (*.csv);;All files (*)"
        )
        if path:
            self.recipe_variables_path = os.path.normpath(path)
            self._update_variable_path_display()
            self.load_variables()

    def reload_variables(self):
        """Reload exchange and recipe CSVs from current paths (e.g. after editing files). Disconnect first."""
        if self.comm_status.get("connected"):
            self._show_toast("Disconnect first, then click Reload again.")
            return
        self.load_variables()
        self._show_toast("Variables reloaded from CSV files.")

    def _create_offline_csv_info_widget(self):
        """Create the info widget shown when Offline Data: CSV format rules and example table."""
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        title = QLabel("📋 CSV format")
        title.setStyleSheet("font-weight: bold; color: #ccc; font-size: 11px;")
        layout.addWidget(title)
        desc = QLabel(
            "• First row = column headers (any names)\n"
            "• Numeric columns for plotting\n"
            "• Comma or semicolon separated\n"
            "• One column can be X-axis (time/index)"
        )
        desc.setStyleSheet("color: #aaa; font-size: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        example_label = QLabel("Example:")
        example_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(example_label)
        table = QTableWidget(4, 3)
        table.setHorizontalHeaderLabels(["Time", "Pressure", "Temperature"])
        table.setStyleSheet("""
            QTableWidget { background-color: #1e1e1e; color: #ccc; gridline-color: #3e3e42; }
            QTableWidget::item { padding: 2px; }
            QHeaderView::section { background-color: #3e3e42; color: #ccc; padding: 4px; }
        """)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setMaximumHeight(120)
        example_data = [
            ("0", "1.2", "25.3"),
            ("0.1", "1.3", "25.5"),
            ("0.2", "1.1", "26.0"),
            ("0.3", "1.4", "25.8"),
        ]
        for row, row_data in enumerate(example_data):
            for col, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, col, item)
        layout.addWidget(table)
        return group

    def setup_comm_info_panel(self):
        """Initialize communication status variables"""
        self.comm_status = {
            "connected": False,
            "simulation_mode": False,
            "last_message": "Not connected",
            "read_count": 0,
            "error_count": 0,
            "last_error": None,
            "read_error": None,             # ADS: last variable read failure (e.g. symbol not found)
            "ip_address": None,
            "last_interval_ms": None,      # Actual time between last two received packages (ms)
            "requested_interval_ms": None  # Requested cycle time (ms), e.g. 50 for 50ms
        }

    def create_comm_info_panel(self):
        """Create collapsible communication info panel"""
        container = QFrame()
        container.setStyleSheet("""
            QFrame { 
                background-color: #2d2d30; 
                border: 1px solid #3e3e42; 
                border-radius: 4px; 
                margin-top: 10px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        
        # Header with toggle button
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.comm_info_label = QLabel("📡 Communication Info")
        self.comm_info_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 12px;")
        header_layout.addWidget(self.comm_info_label)
        header_layout.addStretch()
        
        self.comm_toggle_btn = QPushButton("▼")
        self.comm_toggle_btn.setFixedSize(20, 20)
        self.comm_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.comm_toggle_btn.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #888; 
                border: none; 
                font-size: 10px;
            }
            QPushButton:hover { color: white; }
        """)
        self.comm_toggle_btn.clicked.connect(lambda: self.toggle_comm_info())
        header_layout.addWidget(self.comm_toggle_btn)
        
        layout.addWidget(header)
        
        # Info content (initially visible)
        self.comm_info_content = QWidget()
        self.comm_info_content.setVisible(True)
        content_layout = QVBoxLayout(self.comm_info_content)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(5)
        
        self.comm_status_label = QLabel("Status: Not connected")
        self.comm_status_label.setStyleSheet("color: #888; font-size: 11px;")
        content_layout.addWidget(self.comm_status_label)
        
        self.comm_ip_label = QLabel("IP: --")
        self.comm_ip_label.setStyleSheet("color: #aaa; font-size: 10px;")
        content_layout.addWidget(self.comm_ip_label)
        
        self.comm_stats_label = QLabel("Reads: 0 | Errors: 0")
        self.comm_stats_label.setStyleSheet("color: #aaa; font-size: 10px;")
        content_layout.addWidget(self.comm_stats_label)
        
        self.comm_interval_label = QLabel("Last cycle: -- ms (requested: -- ms)")
        self.comm_interval_label.setStyleSheet("color: #aaa; font-size: 10px;")
        self.comm_interval_label.setToolTip("Time between last two received packages. If much higher than requested, PC–PLC communication is slower than the set cycle.")
        content_layout.addWidget(self.comm_interval_label)
        
        self.comm_db_size_label = QLabel("DB: --")
        self.comm_db_size_label.setStyleSheet("color: #6a9; font-size: 10px;")
        self.comm_db_size_label.setToolTip("Current recording database disk size (today's .duckdb file)")
        content_layout.addWidget(self.comm_db_size_label)

        self.comm_message_label = QLabel("")
        self.comm_message_label.setStyleSheet("color: #888; font-size: 10px;")
        self.comm_message_label.setWordWrap(True)
        content_layout.addWidget(self.comm_message_label)
        
        layout.addWidget(self.comm_info_content)
        
        return container

    def toggle_comm_info(self):
        """Toggle visibility of communication info panel"""
        is_visible = self.comm_info_content.isVisible()
        self.comm_info_content.setVisible(not is_visible)
        self.comm_toggle_btn.setText("▼" if not is_visible else "▲")

    def _toggle_connection_section(self):
        """Toggle Connection details (Client, IP, Variable files) expanded/collapsed."""
        is_visible = self.connection_details_content.isVisible()
        self.connection_details_content.setVisible(not is_visible)
        self.connection_toggle_btn.setText("▼" if not is_visible else "▲")
        s = QSettings("DecAutomation", "Studio")
        s.setValue("connection_section_collapsed", is_visible)
        s.sync()

    def _toggle_trigger_section(self):
        """Toggle PLC TRIGGER section expanded/collapsed to free space for Data Points."""
        is_visible = self.trigger_content.isVisible()
        self.trigger_content.setVisible(not is_visible)
        self.trigger_toggle_btn.setText("▼" if not is_visible else "▲")
        s = QSettings("DecAutomation", "Studio")
        s.setValue("trigger_section_collapsed", is_visible)
        s.sync()

    def _unload_offline_data(self):
        """Unload offline DuckDB/CSV and clear variable list for Online mode."""
        if self.offline_db:
            try:
                self.offline_db.close()
            except Exception:
                pass
            self.offline_db = None
        self.offline_csv_path = None
        self.offline_columns = []
        self.offline_path_label.setText("No file loaded")
        self.offline_memory_label.setText("")

    def _set_offline_mode(self, active):
        """Set offline mode and update sidebar + variable list."""
        self._offline_mode_active = active
        self._update_sidebar_for_mode()
        if active:
            self.var_list.clear()
            self.all_variables = []
            if self.offline_columns:
                for c in self.offline_columns:
                    self.var_list.addItem(c)
                self.all_variables = list(self.offline_columns)
            self._refresh_offline_history()
        elif not getattr(self, "_during_init", False):
            self.load_variables()

    def on_device_type_changed(self, device_type):
        """Show/hide address rows and update labels by Client Device Type (Snap7, ADS, Simulation)."""
        if device_type == "Simulation":
            self.address_row.setVisible(False)
            self.pc_ip_row.setVisible(False)
            self.recording_section.setVisible(False)
            if hasattr(self, "sidebar_interval_row"):
                self.sidebar_interval_row.setVisible(False)
        else:
            self.address_row.setVisible(True)
            if device_type == "Snap7":
                self.recording_section.setVisible(True)
                if hasattr(self, "sidebar_interval_row"):
                    self.sidebar_interval_row.setVisible(True)
                self._on_recording_ref_changed()
            else:
                self.recording_section.setVisible(False)
                if hasattr(self, "sidebar_interval_row"):
                    self.sidebar_interval_row.setVisible(False)
            if device_type == "ADS":
                self.address_label.setText("Target (PLC):")
                self.ip_input.setPlaceholderText("192.168.1.10.1.1")
                self.pc_ip_row.setVisible(True)
            else:
                self.address_label.setText("IP:")
                self.ip_input.setPlaceholderText("192.168.0.20")
                self.pc_ip_row.setVisible(False)

    def _on_recording_ref_changed(self):
        """Show interval (ms) when Time, or trigger variable when Variable."""
        ref = self.recording_ref_combo.currentData() or "time"
        self.recording_interval_row_widget.setVisible(ref == "time")
        self.recording_trigger_row_widget.setVisible(ref == "variable")

    def _refresh_offline_history(self):
        """Scan external/ for Data_DDMMYYYY.duckdb files and populate the history list with sizes."""
        self.offline_history_list.clear()
        ext_dir = os.path.join(os.path.dirname(__file__), "external")
        self._offline_db_files = list_recording_db_files(ext_dir)
        import datetime as _dt
        today = _dt.date.today()
        total_bytes = 0
        for entry in self._offline_db_files:
            day_label = entry['date_str']
            if entry['date'] == today:
                day_label += "  (today)"
            elif day_label == 'legacy':
                day_label = "legacy (automation_data.db)"
            text = f"{day_label}    {entry['size_label']}"
            self.offline_history_list.addItem(text)
            total_bytes += entry['size_bytes']
        # Update total history size label
        n_files = len(self._offline_db_files)
        total_label = _format_size(total_bytes)
        if n_files > 0:
            self.offline_memory_label.setText(f"History: {total_label} total ({n_files} file{'s' if n_files != 1 else ''})")
        else:
            self.offline_memory_label.setText("No recording history found")

    def _update_offline_memory_label(self, loaded_file_bytes=0, loaded_row_count=0):
        """Update the offline memory label with loaded file info + total history size."""
        # Loaded file info
        if loaded_file_bytes > 0:
            loaded_text = f"Loaded: {_format_size(loaded_file_bytes)} on disk, {loaded_row_count:,} rows in RAM"
        else:
            loaded_text = ""

        # History total
        ext_dir = os.path.join(os.path.dirname(__file__), "external")
        db_files = list_recording_db_files(ext_dir)
        total_bytes = sum(e['size_bytes'] for e in db_files)
        n_files = len(db_files)
        history_text = f"History: {_format_size(total_bytes)} ({n_files} file{'s' if n_files != 1 else ''})" if n_files > 0 else ""

        parts = [p for p in [loaded_text, history_text] if p]
        self.offline_memory_label.setText("\n".join(parts) if parts else "")

    def _load_selected_history_day(self, item=None):
        """Load the selected recording day from the history list."""
        if not hasattr(self, '_offline_db_files') or not self._offline_db_files:
            self._show_toast("No recording history files found.")
            return
        idx = self.offline_history_list.currentRow()
        if idx < 0:
            self._show_toast("Select a recording day from the list first.")
            return
        if idx >= len(self._offline_db_files):
            return
        entry = self._offline_db_files[idx]
        self._load_duckdb_recording(entry['path'])

    def load_offline_duckdb_file(self):
        """Browse for a .duckdb file and load it for offline plotting."""
        ext_dir = os.path.join(os.path.dirname(__file__), "external")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DuckDB recording file", ext_dir,
            "DuckDB (*.duckdb *.db);;All files (*)"
        )
        if not path:
            return
        path = os.path.normpath(path)
        self._load_duckdb_recording(path)

    def _load_duckdb_recording(self, db_path):
        """Load a .duckdb recording file (read-only) and populate variables for offline plotting."""
        if (self.plc_thread and self.plc_thread.is_alive()) or (self.ads_thread and self.ads_thread.is_alive()) or (self.simulator_thread and self.simulator_thread.isRunning()):
            reply = QMessageBox.question(
                self, "Disconnect to Load Offline?",
                "Disconnect from PLC/simulation to load offline data?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.disconnect_plc()
        try:
            if self.offline_db:
                try:
                    self.offline_db.close()
                except Exception:
                    pass
                self.offline_db = None

            # Open read-only so we don't interfere with active recording
            self.offline_db = duckdb.connect(database=db_path, read_only=True)

            # Get variable names from exchange_variables
            result = self.offline_db.execute(
                "SELECT DISTINCT variable_name FROM exchange_variables ORDER BY variable_name"
            ).fetchall()
            var_names = [row[0] for row in result]
            if not var_names:
                QMessageBox.warning(self, "No data", f"No recording data found in:\n{os.path.basename(db_path)}")
                self.offline_db.close()
                self.offline_db = None
                return

            # Get time range and row count (total rows, not unique timestamps)
            t_row = self.offline_db.execute(
                "SELECT min(timestamp), max(timestamp), count(*) FROM exchange_variables"
            ).fetchone()
            t_min, t_max, row_count = t_row if t_row else (None, None, 0)

            # Estimate unique timestamps (pivot rows) and RAM
            n_vars = len(var_names)
            try:
                ts_count = self.offline_db.execute(
                    "SELECT count(DISTINCT timestamp) FROM exchange_variables"
                ).fetchone()[0]
            except Exception:
                ts_count = row_count // max(n_vars, 1)
            # RAM estimate: pivot table = ts_count rows x (1 timestamp + n_vars doubles)
            # ~8 bytes per double + 8 bytes per timestamp + DuckDB overhead (~2x)
            estimated_ram_bytes = ts_count * (8 + n_vars * 8) * 2
            estimated_ram_mb = estimated_ram_bytes / (1024 * 1024)
            current_ram = get_process_ram_mb() or 0

            # Show confirmation with RAM estimate
            disk_sz = _format_size(os.path.getsize(db_path))
            time_str = ""
            if t_min and t_max:
                time_str = f"\nTime range: {t_min.strftime('%H:%M:%S')} → {t_max.strftime('%H:%M:%S')}"
            reply = QMessageBox.question(
                self,
                "Load recording?",
                f"{os.path.basename(db_path)}  ({disk_sz} on disk)\n"
                f"{n_vars} variables, {ts_count:,} time points{time_str}\n\n"
                f"Estimated RAM for pivot table: ~{estimated_ram_mb:.0f} MB\n"
                f"Current app RAM: {current_ram:.0f} MB → ~{current_ram + estimated_ram_mb:.0f} MB after load",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if reply != QMessageBox.StandardButton.Ok:
                self.offline_db.close()
                self.offline_db = None
                return

            # Pivot: create an offline_data table in memory from the recording
            # Close the read-only connection and create a memory DB that queries the file
            self.offline_db.close()
            self.offline_db = duckdb.connect(":memory:")
            # Attach the recording file as read-only
            self.offline_db.execute(f"ATTACH '{db_path}' AS rec (READ_ONLY)")

            # Build pivot query: timestamp + each variable as a column
            var_cols = ", ".join(
                f"max(CASE WHEN variable_name = '{v}' THEN value END) AS \"{v}\""
                for v in var_names
            )
            self.offline_db.execute(f"""
                CREATE TABLE offline_data AS
                SELECT timestamp, {var_cols}
                FROM rec.exchange_variables
                GROUP BY timestamp
                ORDER BY timestamp
            """)
            self.offline_db.execute("DETACH rec")

            self.offline_columns = ['timestamp'] + var_names
            self.offline_csv_path = db_path
            self.var_list.clear()
            self.all_variables = list(self.offline_columns)
            for col in self.offline_columns:
                self.var_list.addItem(col)

            # Update status
            fname = os.path.basename(db_path)
            disk_size = os.path.getsize(db_path)
            if disk_size < 1024 * 1024:
                sz = f"{disk_size / 1024:.1f} KB"
            else:
                sz = f"{disk_size / (1024 * 1024):.1f} MB"
            time_info = ""
            if t_min and t_max:
                time_info = f"\nTime: {t_min.strftime('%H:%M:%S')} → {t_max.strftime('%H:%M:%S')}"
            self.offline_path_label.setText(f"Loaded: {fname}")
            self.offline_path_label.setToolTip(db_path)

            # Update memory label with loaded file info + history total
            self._update_offline_memory_label(disk_size, row_count)

            self._update_ram_label()  # Refresh RAM indicator after load
            self._show_toast(f"Loaded {fname} — {len(var_names)} vars, {row_count:,} rows", 4000)
            self._set_offline_mode(True)
        except Exception as e:
            logging.error(f"Failed to load DuckDB recording: {e}")
            QMessageBox.warning(
                self, "Load failed",
                f"Could not load DuckDB recording:\n{e}"
            )
            if self.offline_db:
                try:
                    self.offline_db.close()
                except Exception:
                    pass
                self.offline_db = None
            self.offline_columns = []
            self.offline_csv_path = None
            self.offline_path_label.setText("No file loaded")

    def load_offline_csv(self):
        """Load a user-selected CSV into DuckDB and populate variable list for offline plotting."""
        if (self.plc_thread and self.plc_thread.is_alive()) or (self.ads_thread and self.ads_thread.is_alive()) or (self.simulator_thread and self.simulator_thread.isRunning()):
            reply = QMessageBox.question(
                self, "Disconnect to Load Offline?",
                "Disconnect from PLC/simulation to load offline data?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.disconnect_plc()
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV (*.csv);;All files (*)"
        )
        if not path:
            return
        path = os.path.normpath(path)

        # Show RAM estimate before loading (CSV in-memory ≈ 1.5-3x file size)
        try:
            file_size = os.path.getsize(path)
            estimated_ram_mb = (file_size * 2) / (1024 * 1024)  # ~2x file size in RAM
            current_ram = get_process_ram_mb() or 0
            reply = QMessageBox.question(
                self,
                "Load CSV?",
                f"{os.path.basename(path)}  ({_format_size(file_size)} on disk)\n\n"
                f"Estimated RAM: ~{estimated_ram_mb:.0f} MB\n"
                f"Current app RAM: {current_ram:.0f} MB → ~{current_ram + estimated_ram_mb:.0f} MB after load",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
        except Exception:
            pass  # If estimation fails, proceed anyway

        try:
            if self.offline_db:
                try:
                    self.offline_db.close()
                except Exception:
                    pass
                self.offline_db = None
            self.offline_db = duckdb.connect(":memory:")
            # Load CSV into DuckDB for fast querying (avoids re-reading CSV on each plot)
            self.offline_db.execute(
                "CREATE TABLE offline_data AS SELECT * FROM read_csv_auto(?)",
                [path]
            )
            # Get column names
            result = self.offline_db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'offline_data' ORDER BY ordinal_position"
            ).fetchall()
            self.offline_columns = [row[0] for row in result]
            self.offline_csv_path = path
            self.var_list.clear()
            self.all_variables = list(self.offline_columns)
            for col in self.offline_columns:
                self.var_list.addItem(col)
            self.offline_path_label.setText(f"Loaded: {os.path.basename(path)}")
            self.offline_path_label.setToolTip(path)
            # Update memory label with CSV file size
            csv_size = os.path.getsize(path) if os.path.isfile(path) else 0
            row_count = self.offline_db.execute("SELECT count(*) FROM offline_data").fetchone()[0]
            self._update_offline_memory_label(csv_size, row_count)
            self._update_ram_label()  # Refresh RAM indicator after load
            self._show_toast(f"Loaded {os.path.basename(path)} — {len(self.offline_columns)} columns", 4000)
            self._set_offline_mode(True)
        except Exception as e:
            logging.error(f"Failed to load CSV into DuckDB: {e}")
            QMessageBox.warning(
                self, "Load failed",
                f"Could not load CSV into DuckDB:\n{e}"
            )
            if self.offline_db:
                try:
                    self.offline_db.close()
                except Exception:
                    pass
                self.offline_db = None
            self.offline_columns = []
            self.offline_csv_path = None
            self.offline_path_label.setText("No file loaded")

    def start_plc_thread(self):
        if (self.plc_thread and self.plc_thread.is_alive()) or (self.ads_thread and self.ads_thread.is_alive()) or (self.simulator_thread and self.simulator_thread.isRunning()):
            QMessageBox.warning(self, "Connection Active", "Already connected or in simulation mode.")
            return
        if self._offline_mode_active:
            QMessageBox.warning(self, "Offline Mode", "Close Offline Data and open Connection first.")
            return

        # Unload offline data when switching to Online (Connect)
        self._unload_offline_data()

        device_type = self.device_type_combo.currentText()
        
        # Clean up any existing thread first
        if self.plc_thread:
            try:
                self.plc_thread.stop()
                self.plc_thread.join(timeout=1.0)
            except Exception:
                pass
            self.plc_thread = None
        if self.ads_thread:
            try:
                self.ads_thread.stop()
                self.ads_thread.join(timeout=1.0)
            except Exception:
                pass
            self.ads_thread = None
        if self.simulator_thread and self.simulator_thread.isRunning():
            try:
                self.simulator_thread._is_running = False
                self.simulator_thread.wait(2000)
            except Exception:
                pass
            self.simulator_thread = None
        
        address = self.ip_input.text().strip()
        if device_type != "Simulation" and not address:
            QMessageBox.warning(self, "Address Required", "Please enter IP (Snap7) or Target PLC AmsNetId (ADS).")
            return
        pc_ip = self.pc_ip_input.text().strip() if device_type == "ADS" else None
        if device_type == "ADS" and not pc_ip:
            QMessageBox.warning(self, "PC IP Required", "For ADS, enter your PC's IP (or AmsNetId). This is the address used for the route on the PLC.")
            return
        
        # Get communication speed (used for PLC; simulator has its own timing)
        try:
            comm_speed = float(self.speed_input.text())
            if comm_speed <= 0:
                raise ValueError("Speed must be positive")
        except ValueError:
            QMessageBox.warning(self, "Invalid Speed", "Please enter a valid positive number for communication speed (e.g., 0.05)")
            return

        # Recording params (Snap7 only): validate interval >= 100 ms and trigger variable when Variable
        recording_reference = "time"
        recording_interval_sec = 0.5
        recording_trigger_variable = None
        if device_type == "Snap7" and getattr(self, "recording_section", None) and self.recording_section.isVisible():
            ref = self.recording_ref_combo.currentData() or "time"
            recording_reference = ref
            if ref == "time":
                interval_ms = self.recording_interval_ms.value()
                if interval_ms < 100:
                    QMessageBox.warning(
                        self, "Recording interval",
                        "Recording interval must be at least 100 ms when using Time (interval)."
                    )
                    return
                recording_interval_sec = interval_ms / 1000.0
            else:
                trigger_text = (self.recording_trigger_combo.currentText() or "").strip()
                if not trigger_text or trigger_text.startswith("("):
                    QMessageBox.warning(
                        self, "Recording trigger",
                        "Select a variable for 'Variable (on change)' recording, or load variables first."
                    )
                    return
                recording_trigger_variable = trigger_text
        
        # Clear graph buffers before connecting
        for graph in self.graphs:
            for var_name in graph.buffers_y.keys():
                graph.buffers_y[var_name].clear()
                if var_name in graph.buffers_x:
                    graph.buffers_x[var_name].clear()
                if var_name in graph.lines:
                    graph.lines[var_name].setData([], [])
            # Clear timestamp buffer
            if hasattr(graph, 'buffer_timestamps'):
                graph.buffer_timestamps.clear()
        
        self.comm_status["ip_address"] = address if device_type != "Simulation" else None
        self.comm_status["connected"] = False
        self.comm_status["simulation_mode"] = False
        self.comm_status["read_count"] = 0
        self.comm_status["error_count"] = 0
        self.comm_status["last_error"] = None
        self.comm_status["read_error"] = None
        self.update_comm_info_display()

        self._save_last_config()

        if device_type == "Simulation":
            csv_path = self.exchange_variables_path or os.path.join(os.path.dirname(__file__), "external", "exchange_variables.csv")
            self.plc_thread = None
            self.ads_thread = None
            self.simulator_thread = PLCSimulator(csv_path=csv_path, parent=self)
            self.simulator_thread.new_data.connect(self.data_signal.emit)
            self.simulator_thread.start()
            self.status_signal.emit("simulation", "Simulation mode", {})
        elif device_type == "ADS":
            self.plc_thread = None
            self.simulator_thread = None
            # Request exchange + recipe vars so tooltip can show recipe params; plot list stays exchange-only
            vars_to_read = list(self.all_variables) + [p for p in self.recipe_params if p not in self.all_variables]
            self.ads_thread = PLCADSThread(
                address, self.data_signal, self.status_signal, comm_speed,
                local_address=pc_ip, variable_names=vars_to_read
            )
            self.ads_thread.start()
        else:
            self.simulator_thread = None
            self.ads_thread = None
            db_filename = self.db_filename_edit.text().strip() or None
            self.plc_thread = PLCThread(
                address, self.data_signal, self.status_signal, comm_speed,
                recording_reference=recording_reference,
                recording_interval_sec=recording_interval_sec,
                recording_trigger_variable=recording_trigger_variable,
                db_filename=db_filename,
            )
            self.plc_thread.start()
        
        # Update button states
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.ip_input.setEnabled(False)
        if device_type == "ADS":
            self.pc_ip_input.setEnabled(False)
        self.device_type_combo.setEnabled(False)
        self.browse_exchange_btn.setEnabled(False)
        self.browse_recipe_btn.setEnabled(False)
        self.reload_vars_btn.setEnabled(False)
        self.db_filename_edit.setEnabled(False)
        # Speed can be changed while connected, buffer size only applies to new graphs
        self.speed_input.setEnabled(True)
        self.trigger_btn.setEnabled(True)  # Enable trigger when connected
        self.pause_btn.setEnabled(True)
        # Reset trigger and pause state on new connection
        self.trigger_active = False
        self.paused = False
        self.trigger_btn.setText("⚡ Trigger")
        self.pause_btn.setText("⏸ Pause")
        self.pause_btn.setStyleSheet("""
            QPushButton { background-color: #FF9800; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #FFB74D; }
            QPushButton:pressed { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.trigger_btn.setStyleSheet("""
            QPushButton { 
                background-color: #ff6b00; 
                color: white; 
                font-weight: bold; 
                padding: 10px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { background-color: #ff8800; }
            QPushButton:pressed { background-color: #cc5500; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)

    def disconnect_plc(self):
        """Disconnect from PLC, ADS, or stop the simulation thread"""
        was_simulation = False
        if self.simulator_thread and self.simulator_thread.isRunning():
            was_simulation = True
            self.simulator_thread._is_running = False
            if not self.simulator_thread.wait(3000):
                logging.warning("Simulator thread did not stop gracefully")
            self.simulator_thread = None
        elif self.ads_thread and self.ads_thread.is_alive():
            self.ads_thread.stop()
            if not self.ads_thread.join(timeout=2.0):
                logging.warning("ADS thread did not stop gracefully, forcing termination")
            self.ads_thread = None
        elif self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.stop()
            if not self.plc_thread.join(timeout=2.0):
                logging.warning("PLC thread did not stop gracefully, forcing termination")
            self.plc_thread = None
        else:
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.ip_input.setEnabled(True)
            self.pc_ip_input.setEnabled(True)
            self.device_type_combo.setEnabled(True)
            self.speed_input.setEnabled(True)
            self.browse_exchange_btn.setEnabled(True)
            self.browse_recipe_btn.setEnabled(True)
            self.reload_vars_btn.setEnabled(True)
            self.db_filename_edit.setEnabled(True)
            self.trigger_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self._show_toast("No active connection to disconnect.")
            return
        
        # Common cleanup: clear graph buffers, update status, button states
        for graph in self.graphs:
            for var_name in graph.buffers_y.keys():
                graph.buffers_y[var_name].clear()
                if var_name in graph.buffers_x:
                    graph.buffers_x[var_name].clear()
                if var_name in graph.lines:
                    graph.lines[var_name].setData([], [])
                if var_name in graph.value_labels:
                    graph.value_labels[var_name].setText(f"{graph._display_label(var_name)}: --")
            if hasattr(graph, 'buffer_timestamps'):
                graph.buffer_timestamps.clear()
        
        self.comm_status["connected"] = False
        self.comm_status["simulation_mode"] = False
        self.comm_status["last_message"] = "Disconnected from simulation." if was_simulation else "Disconnected from PLC"
        self.comm_status["last_error"] = None
        self.comm_status["read_error"] = None
        self.comm_status["read_count"] = 0
        self.comm_status["error_count"] = 0
        self.update_comm_info_display()
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.ip_input.setEnabled(True)
        self.pc_ip_input.setEnabled(True)
        self.device_type_combo.setEnabled(True)
        self.speed_input.setEnabled(True)
        self.browse_exchange_btn.setEnabled(True)
        self.browse_recipe_btn.setEnabled(True)
        self.reload_vars_btn.setEnabled(True)
        self.db_filename_edit.setEnabled(True)
        self._set_default_db_filename()  # Reset to today's default on disconnect
        self.trigger_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.trigger_active = False
        self.paused = False
        self.trigger_btn.setText("⚡ Trigger")
        self.pause_btn.setText("⏸ Pause")
        self.trigger_btn.setStyleSheet("""
            QPushButton { 
                background-color: #ff6b00; 
                color: white; 
                font-weight: bold; 
                padding: 10px; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { background-color: #ff8800; }
            QPushButton:pressed { background-color: #cc5500; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.pause_btn.setStyleSheet("""
            QPushButton { background-color: #FF9800; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #FFB74D; }
            QPushButton:pressed { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        
        for key in self.latest_values:
            self.latest_values[key] = 0.0

    @Slot(str, str, object)
    def update_comm_status(self, status_type, message, details):
        """Update communication status from PLC thread"""
        if status_type == "simulation":
            self.comm_status["connected"] = True
            self.comm_status["simulation_mode"] = True
            self.comm_status["last_message"] = message
            # Same button states as connected
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.ip_input.setEnabled(False)
            self.speed_input.setEnabled(True)
            self.trigger_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.trigger_active = False
            self.paused = False
            self.trigger_btn.setText("⚡ Trigger")
            self.pause_btn.setText("⏸ Pause")
            self.trigger_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ff6b00; 
                    color: white; 
                    font-weight: bold; 
                    padding: 10px; 
                    border: none; 
                    border-radius: 4px; 
                }
                QPushButton:hover { background-color: #ff8800; }
                QPushButton:pressed { background-color: #cc5500; }
            """)
        elif status_type == "connected":
            self.comm_status["connected"] = True
            self.comm_status["simulation_mode"] = False
            self.comm_status["last_message"] = message
            # Update button states when connected
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.ip_input.setEnabled(False)
            # Speed can be changed while connected, buffer size only applies to new graphs
            self.speed_input.setEnabled(True)
            self.trigger_btn.setEnabled(True)  # Enable trigger when connected
            self.pause_btn.setEnabled(True)
            # Reset trigger and pause state when connection is established
            self.trigger_active = False
            self.paused = False
            self.trigger_btn.setText("⚡ Trigger")
            self.pause_btn.setText("⏸ Pause")
            self.trigger_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ff6b00; 
                    color: white; 
                    font-weight: bold; 
                    padding: 10px; 
                    border: none; 
                    border-radius: 4px; 
                }
                QPushButton:hover { background-color: #ff8800; }
                QPushButton:pressed { background-color: #cc5500; }
            """)
        elif status_type == "disconnected":
            self.comm_status["connected"] = False
            self.comm_status["simulation_mode"] = False
            self.comm_status["last_message"] = message
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.ip_input.setEnabled(True)
            self.pc_ip_input.setEnabled(True)
            self.device_type_combo.setEnabled(True)
            self.speed_input.setEnabled(True)
            self.browse_exchange_btn.setEnabled(True)
            self.browse_recipe_btn.setEnabled(True)
            self.reload_vars_btn.setEnabled(True)
            self.db_filename_edit.setEnabled(True)
            self._set_default_db_filename()
            self.trigger_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            # Reset trigger and pause state when disconnected
            self.trigger_active = False
            self.paused = False
            self.trigger_btn.setText("⚡ Trigger")
            self.pause_btn.setText("⏸ Pause")
            self.trigger_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ff6b00; 
                    color: white; 
                    font-weight: bold; 
                    padding: 10px; 
                    border: none; 
                    border-radius: 4px; 
                }
                QPushButton:hover { background-color: #ff8800; }
                QPushButton:pressed { background-color: #cc5500; }
                QPushButton:disabled { background-color: #555; color: #888; }
            """)
        elif status_type == "error":
            self.comm_status["last_error"] = message
            if "error_count" in details:
                self.comm_status["error_count"] = details["error_count"]
            # If we get an error and we're not connected, re-enable inputs
            if not self.comm_status["connected"]:
                self.connect_btn.setEnabled(True)
                self.disconnect_btn.setEnabled(False)
                self.ip_input.setEnabled(True)
                self.pc_ip_input.setEnabled(True)
                self.device_type_combo.setEnabled(True)
                self.speed_input.setEnabled(True)
                self.browse_exchange_btn.setEnabled(True)
                self.browse_recipe_btn.setEnabled(True)
                self.reload_vars_btn.setEnabled(True)
                self.db_filename_edit.setEnabled(True)
        elif status_type == "stats":
            if "read_count" in details:
                self.comm_status["read_count"] = details["read_count"]
            if "error_count" in details:
                self.comm_status["error_count"] = details["error_count"]
            if "last_interval_ms" in details:
                self.comm_status["last_interval_ms"] = details["last_interval_ms"]
            if "requested_interval_ms" in details:
                self.comm_status["requested_interval_ms"] = details["requested_interval_ms"]
            if "read_error" in details:
                self.comm_status["read_error"] = details["read_error"]
            else:
                self.comm_status["read_error"] = None
        elif status_type == "info":
            self.comm_status["last_message"] = message
        
        self.update_comm_info_display()

    def update_speed_while_connected(self):
        """Update communication speed while connected, or validate if not connected"""
        try:
            new_speed = float(self.speed_input.text())
            if new_speed <= 0:
                raise ValueError("Speed must be positive")
            
            # If connected, update the active client thread speed
            if self.plc_thread and self.plc_thread.is_alive():
                self.plc_thread.update_speed(new_speed)
            if self.ads_thread and self.ads_thread.is_alive():
                self.ads_thread.update_speed(new_speed)
            
            # Update speed for all existing graphs
            for graph in self.graphs:
                if hasattr(graph, 'comm_speed'):
                    graph.comm_speed = new_speed
        except ValueError:
            # Invalid input, show warning and revert to previous value
            QMessageBox.warning(self, "Invalid Speed", 
                              "Please enter a valid positive number for communication speed (e.g., 0.05)")
            # Revert to the last valid speed (get it from the active thread if connected)
            if self.plc_thread and self.plc_thread.is_alive():
                with self.plc_thread._comm_speed_lock:
                    current_speed = self.plc_thread.comm_speed
                self.speed_input.setText(str(current_speed))
            elif self.ads_thread and self.ads_thread.is_alive():
                with self.ads_thread._comm_speed_lock:
                    current_speed = self.ads_thread.comm_speed
                self.speed_input.setText(str(current_speed))
            else:
                self.speed_input.setText("0.05")

    def update_comm_info_display(self):
        """Update the communication info panel display"""
        status = self.comm_status
        
        # Status label with color
        if status.get("simulation_mode"):
            status_text = "Status: Simulation Mode"
            status_color = "#00E676"
        elif status["connected"]:
            status_text = "Status: ✓ Connected"
            status_color = "#00E676"
        else:
            status_text = "Status: ✗ Disconnected"
            status_color = "#FF1744"
        
        self.comm_status_label.setText(status_text)
        self.comm_status_label.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: bold;")
        
        # IP address
        ip_text = f"IP: {status['ip_address']}" if status['ip_address'] else "IP: --"
        self.comm_ip_label.setText(ip_text)
        
        # Statistics
        stats_text = f"Reads: {status['read_count']} | Errors: {status['error_count']}"
        self.comm_stats_label.setText(stats_text)
        
        # Actual vs requested cycle time (PLC only; simulation has its own timing)
        last_ms = status.get("last_interval_ms")
        req_ms = status.get("requested_interval_ms")
        if last_ms is not None and req_ms is not None:
            interval_text = f"Last cycle: {last_ms:.1f} ms (requested: {req_ms:.0f} ms)"
            self.comm_interval_label.setText(interval_text)
            # Highlight if actual is noticeably higher than requested
            if last_ms > req_ms * 1.5:
                self.comm_interval_label.setStyleSheet("color: #FF9800; font-size: 10px;")
            else:
                self.comm_interval_label.setStyleSheet("color: #aaa; font-size: 10px;")
        else:
            self.comm_interval_label.setText("Last cycle: -- ms (requested: -- ms)")
            self.comm_interval_label.setStyleSheet("color: #aaa; font-size: 10px;")
        
        # Database size (today's recording file)
        db_path = None
        if self.plc_thread:
            db_path = getattr(self.plc_thread, "db_path", None)
        if db_path and os.path.isfile(db_path):
            try:
                sz = os.path.getsize(db_path)
                self.comm_db_size_label.setText(f"DB: {_format_size(sz)}  ({os.path.basename(db_path)})")
            except Exception:
                self.comm_db_size_label.setText("DB: --")
        else:
            self.comm_db_size_label.setText("DB: --")

        # Last message/error (connection errors; ADS variable read failures shown via read_error)
        if status["last_error"]:
            self.comm_message_label.setText(f"⚠ {status['last_error']}")
            self.comm_message_label.setStyleSheet("color: #FF1744; font-size: 10px;")
            self.comm_message_label.setToolTip("")
        elif status.get("read_error"):
            err_text = status["read_error"]
            self.comm_message_label.setText(f"⚠ Read: {err_text}")
            self.comm_message_label.setStyleSheet("color: #FF9800; font-size: 10px;")
            # Hint when ADS route is missing: show how to add route and values to use
            if "Missing ADS routes" in err_text or "Target machine not found" in err_text:
                target = self.ip_input.text().strip() or "192.168.0.2"
                route_ip = ".".join(target.split(".")[:4]) if target else "192.168.0.2"
                self.comm_message_label.setToolTip(
                    "Add route on THIS PC: TwinCAT 3 → System → Routes → Add route.\n"
                    f"Target AmsNetId = {target} (or {route_ip}.1.1 if you use IP only).\n"
                    f"Address / IP = {route_ip}\n"
                    "See: external/TWINCAT_ADS_SETUP.md"
                )
            else:
                self.comm_message_label.setToolTip("")
        elif status["last_message"]:
            self.comm_message_label.setText(f"ℹ {status['last_message']}")
            self.comm_message_label.setStyleSheet("color: #888; font-size: 10px;")
            self.comm_message_label.setToolTip("")
        else:
            self.comm_message_label.setText("")
            self.comm_message_label.setToolTip("")

    def apply_theme(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(45, 45, 48))
        palette.setColor(QPalette.Text, QColor(232, 232, 232))
        palette.setColor(QPalette.Button, QColor(62, 62, 66))
        palette.setColor(QPalette.ButtonText, QColor(232, 232, 232))
        palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)
        # App icon: shown in title bar and taskbar; also used as default for all dialogs (config, file, message boxes)
        _icon = _app_icon()
        if not _icon.isNull():
            app.setWindowIcon(_icon)
        # Style context menus, tooltips, and dialogs (e.g. export) for readable dark theme – no black letters
        app.setStyleSheet("""
            QMenu {
                background-color: #3e3e42;
                color: white;
                border: 1px solid #555;
                padding: 2px;
            }
            QMenu::item {
                background-color: transparent;
                padding: 4px 20px 4px 30px;
            }
            QMenu::item:selected {
                background-color: #007ACC;
                color: white;
            }
            QMenu::item:disabled {
                color: #888;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555;
                margin: 2px 0px;
            }
            QToolTip {
                background-color: #3e3e42;
                color: #e8e8e8;
                border: 1px solid #555;
                padding: 6px 8px;
                font-size: 11px;
            }
            QDialog {
                background-color: #2d2d30;
                color: #e8e8e8;
            }
            QDialog QWidget {
                background-color: transparent;
                color: #e8e8e8;
            }
            QDialog QLabel, QDialog QAbstractButton, QDialog QComboBox, QDialog QListWidget,
            QDialog QTableWidget, QDialog QHeaderView::section, QDialog QLineEdit, QDialog QSpinBox,
            QDialog QPlainTextEdit, QDialog QTextEdit {
                background-color: #3e3e42;
                color: #e8e8e8;
                border: 1px solid #555;
            }
            QDialog QComboBox::editable, QDialog QLineEdit {
                background-color: #3e3e42;
                color: #e8e8e8;
                selection-background-color: #1a6fa5;
                selection-color: white;
            }
            QDialog QPushButton, QDialog QAbstractButton {
                background-color: #3e3e42;
                color: #e8e8e8;
                border: 1px solid #555;
            }
            QDialog QPushButton:hover, QDialog QAbstractButton:hover {
                background-color: #505050;
                color: white;
            }
            QDialog QPushButton:pressed, QDialog QAbstractButton:pressed {
                background-color: #1a6fa5;
                color: white;
            }
            QDialog QListWidget::item, QDialog QTableWidget::item {
                color: #e8e8e8;
            }
            QDialog QListWidget::item:selected, QDialog QTableWidget::item:selected {
                background-color: #1a6fa5;
                color: white;
            }
            QDialog QComboBox QAbstractItemView {
                background-color: #3e3e42;
                color: #e8e8e8;
                border: 1px solid #555;
            }
            QDialog QComboBox QAbstractItemView::item {
                color: #e8e8e8;
            }
            QDialog QComboBox QAbstractItemView::item:selected {
                background-color: #1a6fa5;
                color: white;
            }
            QDialog QTreeWidget, QDialog QTreeWidget::item {
                background-color: #3e3e42;
                color: #e8e8e8;
            }
            QDialog QTreeWidget::item:selected {
                background-color: #1a6fa5;
                color: white;
            }
            QDialog QScrollBar:vertical {
                background: #2d2d30;
                width: 12px;
                border-radius: 6px;
            }
            QDialog QScrollBar::handle:vertical {
                background: #555;
                border-radius: 6px;
                min-height: 20px;
            }
            QDialog QScrollBar::handle:vertical:hover {
                background: #666;
            }
        """)

    # ── Menu Bar ───────────────────────────────────────────────────────
    def _create_menu_bar(self):
        """Create the main menu bar with File, View, Graphs, Tools, Help menus."""
        mb = self._title_bar.menu_bar

        # ── File ──
        file_menu = mb.addMenu("File")
        file_menu.addAction("Connect...", self._open_connection_popup)
        file_menu.addAction("Load...", self._open_load_popup)
        file_menu.addSeparator()
        file_menu.addAction("Export Graph Data to CSV", self._menu_export_csv)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # ── View ──
        view_menu = mb.addMenu("View")
        self._toggle_sidebar_action = view_menu.addAction("Hide Sidebar", self._menu_toggle_sidebar)
        view_menu.addAction("Toggle Comm Info", self.toggle_comm_info)
        view_menu.addSeparator()
        # Graph/Analytics background: Dark or Light
        s = QSettings("DecAutomation", "Studio")
        self._graph_background_mode = s.value("graph_background_mode", "dark")
        if self._graph_background_mode not in ("dark", "light"):
            self._graph_background_mode = "dark"
        self._bg_group = QActionGroup(self)
        self._bg_group.setExclusive(True)
        act_dark = QAction("Dark Background", self)
        act_dark.setCheckable(True)
        act_dark.setChecked(self._graph_background_mode == "dark")
        act_dark.triggered.connect(lambda: self._set_graph_background("dark"))
        self._bg_group.addAction(act_dark)
        view_menu.addAction(act_dark)
        act_light = QAction("Light Background", self)
        act_light.setCheckable(True)
        act_light.setChecked(self._graph_background_mode == "light")
        act_light.triggered.connect(lambda: self._set_graph_background("light"))
        self._bg_group.addAction(act_light)
        view_menu.addAction(act_light)

        # ── Graphs ──
        graphs_menu = mb.addMenu("Graphs")
        graphs_menu.addAction("New Graph from Selection", self.add_new_graph)
        graphs_menu.addSeparator()
        graphs_menu.addAction("Save Graph Config...", self._save_graph_config)

        # Submenu: Load Config
        self._config_submenu = graphs_menu.addMenu("Load Graph Config")
        self._rebuild_config_submenu()
        graphs_menu.addAction("Delete Graph Config...", self._delete_graph_config)

        # ── Tools ──
        tools_menu = mb.addMenu("Tools")
        tools_menu.addAction("Open Analytics", self.open_analytics_window)
        tools_menu.addSeparator()
        tools_menu.addAction("Reload Variables", self.reload_variables)

        # ── Help ──
        help_menu = mb.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _menu_toggle_sidebar(self):
        """Toggle sidebar visibility from the menu bar."""
        if self.sidebar.isVisible():
            self.sidebar.hide()
            self._toggle_sidebar_action.setText("Show Sidebar")
        else:
            self.sidebar.show()
            self._toggle_sidebar_action.setText("Hide Sidebar")

    def _open_connection_popup(self):
        """Open Connection popup (Online data). If Load popup is open, ask to close it first."""
        if self.load_popup and self.load_popup.isVisible():
            reply = QMessageBox.question(
                self, "Switch to Online Data",
                "Close Offline Data to open Connection?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.load_popup.hide()
        self._offline_mode_active = False
        self._update_sidebar_for_mode()
        self.connection_popup.show()
        self.connection_popup.raise_()
        self.connection_popup.activateWindow()

    def _open_load_popup(self):
        """Open Load popup (Offline Data). If Connection popup is open, ask to close it first."""
        if self.connection_popup and self.connection_popup.isVisible():
            reply = QMessageBox.question(
                self, "Switch to Offline Data",
                "Close Connection to open Offline Data?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.connection_popup.hide()
        self.load_popup.show()
        self.load_popup.raise_()
        self.load_popup.activateWindow()

    def _update_sidebar_for_mode(self):
        """Gray out Connect, Disconnect, Pause, Speed, Interval when Offline data is selected."""
        gray = self._offline_mode_active
        for w in (self.connect_btn, self.disconnect_btn, self.pause_btn, self.speed_input):
            if w:
                w.setEnabled(not gray)
        if hasattr(self, "sidebar_interval_row") and self.sidebar_interval_row:
            self.sidebar_interval_row.setEnabled(not gray)

    def _set_graph_background(self, mode):
        """Set graph/analytics background to 'dark' or 'light' and apply to all."""
        self._graph_background_mode = mode
        s = QSettings("DecAutomation", "Studio")
        s.setValue("graph_background_mode", mode)
        s.sync()
        self._apply_graph_background_theme()

    def _apply_graph_background_theme(self):
        """Apply current graph background theme to sidebar, title bar, graph area, all graphs, and analytics window."""
        mode = self._graph_background_mode
        if mode == "light":
            area_bg = "#f5f5f5"
            splitter_handle = "#b0b0b0"
            sidebar_bg = "#ebeaea"
            sidebar_fg = "#333333"
            sidebar_input_bg = "#ffffff"
            sidebar_input_border = "#bbb"
            card_bg = "#f0f0f0"
            card_header_fg = "#444"
            root_border = "#c0c0c0"
        else:
            area_bg = "#1e1e1e"
            splitter_handle = "#3e3e42"
            sidebar_bg = "#252526"
            sidebar_fg = "#e0e0e0"
            sidebar_input_bg = "#444"
            sidebar_input_border = "#555"
            card_bg = "#252526"
            card_header_fg = "#ccc"
            root_border = "#3e3e42"

        # Title bar and menu
        if hasattr(self, "_title_bar") and hasattr(self._title_bar, "apply_theme"):
            self._title_bar.apply_theme(mode)

        # Root border
        if hasattr(self, "_root_widget"):
            self._root_widget.setStyleSheet(f"QWidget#_rootWidget {{ border: 1px solid {root_border}; }}")

        # Sidebar with cascading styles for inputs
        if hasattr(self, "sidebar"):
            self.sidebar.setStyleSheet(f"""
                QWidget {{ background-color: {sidebar_bg}; color: {sidebar_fg}; }}
                QLabel {{ color: {sidebar_fg}; }}
                QComboBox, QLineEdit, QSpinBox {{
                    background-color: {sidebar_input_bg}; color: {sidebar_fg};
                    border: 1px solid {sidebar_input_border}; padding: 5px;
                }}
                QPushButton {{ background-color: {sidebar_input_bg}; color: {sidebar_fg}; border: 1px solid {sidebar_input_border}; }}
                QPushButton:hover {{ background-color: #e0e0e0; }}
                QListWidget {{ background-color: {sidebar_input_bg}; color: {sidebar_fg}; border: 1px solid {sidebar_input_border}; }}
                QListWidget::item:selected {{ background-color: #1a6fa5; color: white; }}
                QListWidget::item:hover {{ background-color: #e8e8e8; }}
                QFrame {{ background-color: transparent; border: none; }}
            """)

        # Keep Connect/Disconnect/Pause buttons with their brand colors (re-apply)
        if hasattr(self, "connect_btn"):
            self.connect_btn.setStyleSheet("""
                QPushButton { background-color: #1a6fa5; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 3px; }
                QPushButton:hover { background-color: #2580b8; }
                QPushButton:pressed { background-color: #0d5a8a; }
            """)
        if hasattr(self, "disconnect_btn"):
            self.disconnect_btn.setStyleSheet("""
                QPushButton { background-color: #6b2d2d; color: #e8e8e8; font-weight: bold; padding: 5px; border: 1px solid #5a2525; border-radius: 3px; }
                QPushButton:hover { background-color: #7a3535; }
                QPushButton:pressed { background-color: #5a2020; }
                QPushButton:disabled { background-color: #3a3a3a; color: #707070; border-color: #2d2d30; }
            """)
        if hasattr(self, "pause_btn"):
            self.pause_btn.setStyleSheet(f"""
                QPushButton {{ background-color: {"#5a5a5a" if mode == "dark" else "#e0e0e0"}; color: {"#e0e0e0" if mode == "dark" else "#333"}; font-weight: bold; padding: 5px; border: 1px solid {"#3e3e42" if mode == "dark" else "#bbb"}; border-radius: 3px; }}
                QPushButton:hover {{ background-color: {"#6a6a6a" if mode == "dark" else "#d0d0d0"}; }}
                QPushButton:disabled {{ background-color: #3a3a3a; color: #707070; }}
            """)

        # Comm info header
        if hasattr(self, "comm_info_label"):
            self.comm_info_label.setStyleSheet(f"font-weight: bold; color: {sidebar_fg}; font-size: 12px;")

        # Graph area and splitter
        if hasattr(self, "graph_area_widget"):
            self.graph_area_widget.setStyleSheet(f"background-color: {area_bg};")
        if hasattr(self, "graph_splitter"):
            self.graph_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {splitter_handle}; }}")

        # Graph card containers and their headers
        if hasattr(self, "graph_splitter"):
            for i in range(self.graph_splitter.count()):
                w = self.graph_splitter.widget(i)
                if w and hasattr(w, "setStyleSheet"):
                    w.setStyleSheet(f"background-color: {card_bg}; border-radius: 6px;")
                if w and hasattr(w, "lbl_title") and w.lbl_title:
                    w.lbl_title.setStyleSheet(f"font-weight: bold; color: {card_header_fg}; font-size: 13px;")

        for graph in getattr(self, "graphs", []):
            if hasattr(graph, "apply_background_theme"):
                graph.apply_background_theme(mode)

        if self.analytics_window is not None and self.analytics_window.isVisible():
            self.analytics_window.apply_background_theme(mode)

    def _menu_export_csv(self):
        """Export all graph data to CSV files (base_plot1.csv, base_plot2.csv, ...) — same as on close."""
        if not hasattr(self, 'graphs') or not self.graphs:
            self._show_toast("No graphs to export.")
            return
        base_path, _ = QFileDialog.getSaveFileName(
            self, "Export graph data (base name)", "graph_export.csv", "CSV (*.csv);;All files (*)"
        )
        if not base_path:
            return
        base = base_path.rsplit(".", 1)[0] if "." in base_path else base_path
        exported = 0
        for i, graph in enumerate(self.graphs, start=1):
            plot_path = f"{base}_plot{i}.csv"
            try:
                if graph.export_graph_data_to_csv(path=plot_path):
                    exported += 1
                    logging.info(f"Exported graph {i} to {plot_path}")
            except Exception as e:
                logging.warning(f"Export graph {i} failed: {e}")
        if exported:
            self._show_toast(f"Exported {exported} graph(s) to CSV")

    def _rebuild_config_submenu(self):
        """Rebuild the 'Load Graph Config' submenu from saved configurations."""
        self._config_submenu.clear()
        s = QSettings("DecAutomation", "Studio")
        configs = s.value("graph_configs", {})
        if not configs or not isinstance(configs, dict):
            action = self._config_submenu.addAction("(no saved configs)")
            action.setEnabled(False)
            return
        for name in sorted(configs.keys()):
            self._config_submenu.addAction(name, lambda n=name: self._load_graph_config_by_name(n))

    def _load_graph_config_by_name(self, name):
        """Load a specific graph configuration by name (called from the menu submenu).
        Sets the sidebar combo to the right item and delegates to _load_graph_config."""
        idx = self.config_load_combo.findData(name)
        if idx >= 0:
            self.config_load_combo.setCurrentIndex(idx)
        self._load_graph_config()

    def _show_about(self):
        """Show a stylish About dialog for the application."""
        dlg = QDialog(self)
        dlg.setWindowTitle("About DecAutomation Studio")
        dlg.setFixedSize(460, 420)
        dlg.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
                border: 1px solid #007ACC;
                border-radius: 12px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
            QFrame {
                border: none;
                background: transparent;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(0)

        # ── App icon ──
        icon = _app_icon()
        if not icon.isNull():
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            pix = icon.pixmap(72, 72)
            icon_label.setPixmap(pix)
            icon_label.setStyleSheet("background: transparent; margin-bottom: 6px;")
            layout.addWidget(icon_label)

        # ── App title ──
        title = QLabel("DecAutomation Studio")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            background: transparent;
            color: #ffffff;
            font-size: 20px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-bottom: 2px;
        """)
        layout.addWidget(title)

        # ── Version ──
        version = QLabel("Version 1.0.0")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("""
            background: transparent;
            color: #7eb8da;
            font-size: 12px;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-bottom: 14px;
        """)
        layout.addWidget(version)

        # ── Separator line ──
        sep = QFrame()
        sep.setFrameShape(QFrame.NoFrame)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #007ACC; border: none; margin: 4px 40px;")
        layout.addWidget(sep)

        # ── Description ──
        desc = QLabel(
            "PLC monitoring, real-time graph visualization<br>& advanced analytics tool.<br>"
            '<span style="font-style: italic; color: #8a8a8a;">- Siemens, Beckhoff, STM32 -</span>'
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            background: transparent;
            color: #c0c0c0;
            font-size: 12px;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 12px 0px;
        """)
        layout.addWidget(desc)

        # ── Tech badge ──
        tech = QLabel("Built with PySide6  |  pyqtgraph  |  DuckDB")
        tech.setAlignment(Qt.AlignCenter)
        tech.setStyleSheet("""
            background: rgba(0, 122, 204, 0.15);
            color: #7eb8da;
            font-size: 10px;
            font-family: 'Consolas', 'Courier New', monospace;
            padding: 5px 12px;
            border-radius: 10px;
            margin: 4px 30px 14px 30px;
        """)
        layout.addWidget(tech)

        # ── Separator line ──
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.NoFrame)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: #007ACC; border: none; margin: 4px 40px;")
        layout.addWidget(sep2)

        # ── Creator section ──
        creator_title = QLabel("DEVELOPED BY")
        creator_title.setAlignment(Qt.AlignCenter)
        creator_title.setStyleSheet("""
            background: transparent;
            color: #5a7a9a;
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 3px;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-top: 12px;
            margin-bottom: 2px;
        """)
        layout.addWidget(creator_title)

        creator = QLabel("DEC S&T")
        creator.setAlignment(Qt.AlignCenter)
        creator.setStyleSheet("""
            background: transparent;
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-bottom: 10px;
        """)
        layout.addWidget(creator)

        # ── Contact info ──
        contact = QLabel(
            '<span style="color:#5a7a9a;">Contact: </span>'
            '<a href="mailto:b.luz@dec-group.swiss" style="color:#4fc3f7; text-decoration:none;">'
            'b.luz@dec-group.swiss</a>'
        )
        contact.setAlignment(Qt.AlignCenter)
        contact.setOpenExternalLinks(True)
        contact.setStyleSheet("""
            background: transparent;
            font-size: 12px;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-bottom: 6px;
        """)
        layout.addWidget(contact)

        # ── Copyright ──
        copy_lbl = QLabel(f"\u00A9 {datetime.now().year} DEC Group. All rights reserved.")
        copy_lbl.setAlignment(Qt.AlignCenter)
        copy_lbl.setStyleSheet("""
            background: transparent;
            color: #555555;
            font-size: 10px;
            font-family: 'Segoe UI', Arial, sans-serif;
            margin-top: 4px;
            margin-bottom: 14px;
        """)
        layout.addWidget(copy_lbl)

        # ── Close button ──
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(110)
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #007ACC, stop:1 #005f99);
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                padding: 7px 20px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a8fd4, stop:1 #007ACC);
            }
            QPushButton:pressed {
                background: #005f99;
            }
        """)
        close_btn.clicked.connect(dlg.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        dlg.exec()

    def load_variables(self):
        """Load variables from the chosen exchange and recipe CSV files (browsable; any filename)."""
        self.var_list.clear()
        self.all_variables = []
        self.recipe_params = []
        
        default_ext = os.path.join(os.path.dirname(__file__), "external")
        exchange_path = self.exchange_variables_path or ""
        recipe_path = self.recipe_variables_path or ""

        # Regenerate snap7_node_ids.json from the current CSV paths if they have DB<N> in the name
        try:
            from external.generate_snap7_config import generate_snap7_config
            result = generate_snap7_config(
                directory=default_ext,
                exchange_csv=exchange_path if exchange_path else None,
                recipe_csv=recipe_path if recipe_path else None,
            )
            if result:
                print(f"snap7_node_ids.json regenerated from CSV files")
        except Exception as e:
            print(f"Config generation skipped: {e}")

        # Load boolean variables from the (now up-to-date) JSON for trigger dropdown (Snap7)
        boolean_vars = []
        try:
            config_path = os.path.join(default_ext, "snap7_node_ids.json")
            with open(config_path, 'r') as f:
                config = json.load(f)
                node_config = config.get('snap7_variables') or config.get('Node_id_flexpts_S7_1500_snap7', {})
                # Find all BOOL variables
                for var_name, node_info in node_config.items():
                    if var_name != 'recipes' and isinstance(node_info, list) and len(node_info) >= 3:
                        if node_info[2] == "BOOL":
                            boolean_vars.append(var_name)
        except Exception as e:
            print(f"Error loading boolean variables from JSON: {e}")
        
        # Populate trigger combo box with boolean variables
        self.trigger_var_combo.clear()
        if boolean_vars:
            self.trigger_var_combo.addItems(boolean_vars)
        else:
            self.trigger_var_combo.addItem("No BOOL variables found")
            self.trigger_var_combo.setEnabled(False)
        
        # Load exchange and recipe variables via variable_loader (groups, Name, Unit)
        loaded = load_exchange_and_recipes(
            exchange_path=exchange_path if exchange_path else None,
            recipe_path=recipe_path if recipe_path else None,
        )
        self.all_variables = loaded.all_variables
        self.variable_metadata = loaded.variable_metadata
        self.recipe_params = loaded.recipe_params
        for var_name in self.all_variables:
            if var_name not in self.latest_values:
                self.latest_values[var_name] = 0.0
        self.var_list.clear()
        self.var_list.addItems(self.all_variables)
        # Populate recording trigger combo (Snap7: record when this variable changes)
        self.recording_trigger_combo.clear()
        all_for_trigger = list(self.all_variables) + [p for p in self.recipe_params if p not in self.all_variables]
        if all_for_trigger:
            self.recording_trigger_combo.addItems(all_for_trigger)
        else:
            self.recording_trigger_combo.addItem("(load variables first)", None)

    def _quote_duckdb_identifier(self, name):
        """Quote identifier for DuckDB (handles spaces and special chars)."""
        return '"' + str(name).replace('"', '""') + '"'

    def add_new_graph(self):
        selected_items = self.var_list.selectedItems()
        if not selected_items:
            return
        var_names = [item.text() for item in selected_items]
        is_offline = self._offline_mode_active
        if is_offline:
            if not self.offline_db or not self.offline_columns:
                QMessageBox.warning(self, "No data", "Load a CSV or recording DB first (Offline Data).")
                return
        dialog = GraphConfigDialog(self.all_variables, self, selected_vars=var_names)
        if dialog.exec() != QDialog.Accepted:
            return
        settings = dialog.get_settings()
        container = QFrame()
        container.setStyleSheet("background-color: #252526; border-radius: 6px;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(10,10,10,10)
        vbox.setSpacing(5)

        header = QWidget(styleSheet="background-color: transparent;")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(0,0,0,0)
        # Title set below from graph.get_display_title() after graph is created
        lbl_title = QLabel("", styleSheet="font-weight: bold; color: #ccc; font-size: 13px;")
        btn_close = QPushButton("✕", fixedWidth=24, fixedHeight=24, cursor=Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border-radius: 12px; font-weight: bold; }
            QPushButton:hover { background-color: #cc3333; color: white; }
        """)
        hbox.addWidget(lbl_title)
        hbox.addStretch()
        hbox.addWidget(btn_close)
        vbox.addWidget(header)

        if is_offline:
            # Offline: query DuckDB, create graph, set static data
            x_col = settings['x_axis']
            use_discrete_index = (x_col == "Discrete index (1, 2, 3…)")
            if use_discrete_index:
                cols = list(var_names)
                x_data_for_static = None
            else:
                cols = [x_col] + [v for v in var_names if v != x_col]
                x_data_for_static = None
            try:
                quoted = [self._quote_duckdb_identifier(c) for c in cols]
                sql = f"SELECT {', '.join(quoted)} FROM offline_data"
                result = self.offline_db.execute(sql).fetchall()
            except Exception as e:
                logging.error(f"Offline query failed: {e}")
                QMessageBox.warning(self, "Query failed", f"DuckDB query failed:\n{e}")
                return
            if not result:
                QMessageBox.warning(self, "No rows", "CSV table has no rows.")
                return
            n_rows = len(result)
            buffer_size = min(max(n_rows, 500), 500000)
            comm_speed = 0.05
            new_graph = DynamicPlotWidget(
                var_names,
                x_axis_source=settings['x_axis'],
                buffer_size=buffer_size,
                recipe_params=self.recipe_params,
                latest_values_cache=self.latest_values,
                variable_metadata=self.variable_metadata,
                comm_speed=comm_speed,
                graph_title=settings.get("graph_title", ""),
                y_axis_mode=settings.get("y_axis_mode", "auto"),
                y_axis_assignments=settings.get("y_axis_assignments"),
                display_deadband=settings.get("display_deadband", 0),
                discrete_index_linked_variable=settings.get("discrete_index_linked_variable"),
                limit_high=settings.get("limit_high"),
                limit_low=settings.get("limit_low"),
                all_variable_list=self.all_variables,
            )
            vbox.addWidget(new_graph)
            container.lbl_title = lbl_title
            container.graph = new_graph
            lbl_title.setText(new_graph.get_display_title())
            self.graph_splitter.addWidget(container)
            self.graphs.append(new_graph)
            btn_close.clicked.connect(lambda: self.remove_graph(container, new_graph))
            col_index = {name: i for i, name in enumerate(cols)}
            if not use_discrete_index:
                x_data_for_static = [row[0] for row in result]
            y_series = {v: [row[col_index[v]] for row in result] for v in var_names if v in col_index}
            new_graph.set_static_data(x_data_for_static, y_series)
            new_graph.apply_background_theme(getattr(self, "_graph_background_mode", "dark"))
            return

        # Online: use buffer_size and other options from GraphConfigDialog
        buffer_size = settings.get("buffer_size", 100000)
        has_arrays = any(var_name.startswith('arr') for var_name in var_names)
        if has_arrays:
            array_size = 600
            min_array_updates = 30
            scaled_buffer_size = max(buffer_size, array_size * min_array_updates)
            if scaled_buffer_size > buffer_size:
                logging.info(f"Buffer size scaled from {buffer_size} to {scaled_buffer_size} to accommodate array variables (600 points per update)")
            buffer_size = scaled_buffer_size

        try:
            comm_speed = float(self.speed_input.text())
            if comm_speed <= 0:
                comm_speed = 0.05
        except ValueError:
            comm_speed = 0.05

        new_graph = DynamicPlotWidget(
            var_names,
            x_axis_source=settings['x_axis'],
            buffer_size=buffer_size,
            recipe_params=self.recipe_params,
            latest_values_cache=self.latest_values,
            variable_metadata=self.variable_metadata,
            comm_speed=comm_speed,
            graph_title=settings.get("graph_title", ""),
            y_axis_mode=settings.get("y_axis_mode", "auto"),
            y_axis_assignments=settings.get("y_axis_assignments"),
            display_deadband=settings.get("display_deadband", 0),
            discrete_index_linked_variable=settings.get("discrete_index_linked_variable"),
            limit_high=settings.get("limit_high"),
            limit_low=settings.get("limit_low"),
            all_variable_list=self.all_variables,
        )
        vbox.addWidget(new_graph)
        container.lbl_title = lbl_title
        container.graph = new_graph
        lbl_title.setText(new_graph.get_display_title())
        self.graph_splitter.addWidget(container)
        self.graphs.append(new_graph)
        new_graph.apply_background_theme(getattr(self, "_graph_background_mode", "dark"))
        btn_close.clicked.connect(lambda: self.remove_graph(container, new_graph))

    def remove_graph(self, container, graph_widget):
        container.setParent(None)
        container.deleteLater()
        if graph_widget in self.graphs:
            self.graphs.remove(graph_widget)

    @Slot(str, object)
    def update_plot(self, variable_name, value):
        # Skip None values to prevent errors
        if value is None:
            return
        # When paused, keep all values as they are and do not update graphs
        if self.paused:
            return
        
        # Check if this is an array (list of values)
        if isinstance(value, (list, tuple)):
            # Handle arrays: plot all values at once, but display the latest value
            if len(value) == 0:
                return
            
            # Filter to get only numeric values
            numeric_array = [v for v in value if isinstance(v, (int, float)) and not (isinstance(v, float) and (np.isnan(v) or np.isinf(v)))]
            if len(numeric_array) == 0:
                return
            
            # Store the latest value for display
            latest_value = numeric_array[-1]
            self.latest_values[variable_name] = latest_value
            
            # Update all graphs that use this variable
            for graph in self.graphs:
                if variable_name in graph.variables or variable_name == graph.x_axis_source or variable_name == getattr(graph, "discrete_index_linked_variable", None):
                    # Plot all array values at once (linked variable as array: each element = one step)
                    if variable_name == getattr(graph, "discrete_index_linked_variable", None):
                        for v in numeric_array:
                            graph.update_data(variable_name, v)
                    else:
                        graph.update_data_array(variable_name, numeric_array)
        else:
            # Handle scalar values (original behavior)
            try:
                # For bool values, convert to int (0 or 1)
                if isinstance(value, bool):
                    value = int(value)
                else:
                    value = float(value)
            except (ValueError, TypeError):
                # Skip non-numeric values
                return

            self.latest_values[variable_name] = value
            for graph in self.graphs:
                if variable_name in graph.variables or variable_name == graph.x_axis_source or variable_name == getattr(graph, "discrete_index_linked_variable", None):
                    x_val = None
                    if graph.is_xy_plot:
                        x_val = self.latest_values.get(graph.x_axis_source, 0.0)
                        if x_val is not None:
                            try:
                                x_val = float(x_val)
                            except (ValueError, TypeError):
                                x_val = 0.0
                    graph.update_data(variable_name, value, x_value=x_val)
                
                # Update limit lines if this variable is used as a limit source
                graph._update_limit_lines_from_variables({variable_name: value})

    def open_analytics_window(self):
        """Open the Analytics window showing real-time statistics for all graphs."""
        if not self.graphs:
            self._show_toast("Create at least one graph first to open Analytics.")
            return
        
        # Create or show existing analytics window
        if self.analytics_window is None or not self.analytics_window.isVisible():
            self.analytics_window = AnalyticsWindow(parent=None)
            self.analytics_window.set_graphs(self.graphs, self.variable_metadata)
            self.analytics_window.apply_background_theme(getattr(self, "_graph_background_mode", "dark"))
            self.analytics_window.show()
        else:
            # Window exists and is visible - bring to front and refresh
            self.analytics_window.set_graphs(self.graphs, self.variable_metadata)
            self.analytics_window.apply_background_theme(getattr(self, "_graph_background_mode", "dark"))
            self.analytics_window.raise_()
            self.analytics_window.activateWindow()

    def _refresh_config_list(self):
        """Refresh the dropdown list of saved graph configurations."""
        self.config_load_combo.clear()
        self.config_load_combo.addItem("-- Select config --", "")
        s = QSettings("DecAutomation", "Studio")
        configs = s.value("graph_configs", {})
        if isinstance(configs, dict):
            for name in sorted(configs.keys()):
                self.config_load_combo.addItem(name, name)

    def _save_graph_config(self):
        """Save current graph configuration with a user-provided name."""
        if not self.graphs:
            self._show_toast("Create at least one graph first to save.")
            return
        
        # Ask for config name
        name, ok = QInputDialog.getText(
            self, "Save Configuration", "Enter a short name for this configuration:",
            QLineEdit.Normal, ""
        )
        if not ok or not name.strip():
            return
        name = name.strip()[:30]  # Limit name length
        
        # Collect all graph configurations
        graph_configs = []
        for graph in self.graphs:
            config = {
                "variables": list(graph.variables),
                "x_axis": graph.x_axis_source,
                "buffer_size": graph.buffer_size,
                "graph_title": getattr(graph, "custom_title", "") or "",
                "y_axis_mode": getattr(graph, "y_axis_mode", "auto"),
                "y_axis_assignments": getattr(graph, "y_axis_assignments", None),
                "display_deadband": getattr(graph, "display_deadband", 0),
                "discrete_index_linked_variable": getattr(graph, "discrete_index_linked_variable", None),
                "limit_high": getattr(graph, "limit_high_config", {"enabled": False}),
                "limit_low": getattr(graph, "limit_low_config", {"enabled": False}),
            }
            graph_configs.append(config)
        
        # Save to QSettings
        s = QSettings("DecAutomation", "Studio")
        all_configs = s.value("graph_configs", {})
        if not isinstance(all_configs, dict):
            all_configs = {}
        all_configs[name] = graph_configs
        s.setValue("graph_configs", all_configs)
        
        self._refresh_config_list()
        self._rebuild_config_submenu()
        # Select the just-saved config
        idx = self.config_load_combo.findData(name)
        if idx >= 0:
            self.config_load_combo.setCurrentIndex(idx)
        
        self._show_toast(f"'{name}' saved — {len(graph_configs)} graph(s).")

    def _load_graph_config(self):
        """Load a saved graph configuration."""
        name = self.config_load_combo.currentData()
        if not name:
            self._show_toast("Select a configuration to load.")
            return
        
        s = QSettings("DecAutomation", "Studio")
        all_configs = s.value("graph_configs", {})
        if not isinstance(all_configs, dict) or name not in all_configs:
            QMessageBox.warning(self, "Not Found", f"Configuration '{name}' not found.")
            return
        
        graph_configs = all_configs[name]
        if not graph_configs:
            QMessageBox.warning(self, "Empty", "This configuration has no graphs.")
            return
        
        # Confirm if there are existing graphs
        if self.graphs:
            reply = QMessageBox.question(
                self, "Replace Graphs?",
                f"This will remove existing {len(self.graphs)} graph(s) and load {len(graph_configs)} graph(s) from '{name}'.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            # Remove all existing graphs
            for graph in list(self.graphs):
                parent = graph.parent()
                if parent:
                    parent.setParent(None)
                    parent.deleteLater()
            self.graphs.clear()
        
        # Create graphs from configuration
        is_offline = self._offline_mode_active
        loaded_count = 0
        
        for config in graph_configs:
            var_names = config.get("variables", [])
            if not var_names:
                continue
            
            # Check variables exist
            missing = [v for v in var_names if v not in self.all_variables]
            if missing:
                logging.warning(f"Skipping graph: missing variables {missing}")
                continue
            
            settings = {
                "x_axis": config.get("x_axis", "Time (Index)"),
                "buffer_size": config.get("buffer_size", 100000),
                "graph_title": config.get("graph_title", ""),
                "y_axis_mode": config.get("y_axis_mode", "auto"),
                "y_axis_assignments": config.get("y_axis_assignments"),
                "display_deadband": config.get("display_deadband", 0),
                "discrete_index_linked_variable": config.get("discrete_index_linked_variable"),
                "limit_high": config.get("limit_high", {"enabled": False}),
                "limit_low": config.get("limit_low", {"enabled": False}),
            }
            
            # Create graph (similar to add_new_graph but using saved settings)
            container = QFrame()
            container.setStyleSheet("background-color: #252526; border-radius: 6px;")
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(10, 10, 10, 10)
            vbox.setSpacing(5)

            header = QWidget(styleSheet="background-color: transparent;")
            hbox = QHBoxLayout(header)
            hbox.setContentsMargins(0, 0, 0, 0)
            lbl_title = QLabel("", styleSheet="font-weight: bold; color: #ccc; font-size: 13px;")
            btn_close = QPushButton("✕", fixedWidth=24, fixedHeight=24, cursor=Qt.PointingHandCursor)
            btn_close.setStyleSheet("""
                QPushButton { background-color: transparent; color: #888; border-radius: 12px; font-weight: bold; }
                QPushButton:hover { background-color: #cc3333; color: white; }
            """)
            hbox.addWidget(lbl_title)
            hbox.addStretch()
            hbox.addWidget(btn_close)
            vbox.addWidget(header)

            buffer_size = settings.get("buffer_size", 100000)
            try:
                comm_speed = float(self.speed_input.text())
                if comm_speed <= 0:
                    comm_speed = 0.05
            except ValueError:
                comm_speed = 0.05

            new_graph = DynamicPlotWidget(
                var_names,
                x_axis_source=settings["x_axis"],
                buffer_size=buffer_size,
                recipe_params=self.recipe_params,
                latest_values_cache=self.latest_values,
                variable_metadata=self.variable_metadata,
                comm_speed=comm_speed,
                graph_title=settings.get("graph_title", ""),
                y_axis_mode=settings.get("y_axis_mode", "auto"),
                y_axis_assignments=settings.get("y_axis_assignments"),
                display_deadband=settings.get("display_deadband", 0),
                discrete_index_linked_variable=settings.get("discrete_index_linked_variable"),
                limit_high=settings.get("limit_high"),
                limit_low=settings.get("limit_low"),
                all_variable_list=self.all_variables,
            )
            vbox.addWidget(new_graph)
            container.lbl_title = lbl_title
            container.graph = new_graph
            lbl_title.setText(new_graph.get_display_title())
            self.graph_splitter.addWidget(container)
            self.graphs.append(new_graph)
            new_graph.apply_background_theme(getattr(self, "_graph_background_mode", "dark"))
            btn_close.clicked.connect(lambda checked=False, c=container, g=new_graph: self.remove_graph(c, g))
            loaded_count += 1

        if loaded_count > 0:
            self._show_toast(f"Loaded {loaded_count} graph(s) from '{name}'.")
        else:
            QMessageBox.warning(self, "Load Failed", "No graphs could be loaded (missing variables?).")

    def _delete_graph_config(self):
        """Delete a saved graph configuration."""
        name = self.config_load_combo.currentData()
        if not name:
            self._show_toast("Select a configuration to delete.")
            return
        
        reply = QMessageBox.question(
            self, "Delete Configuration?",
            f"Are you sure you want to delete configuration '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        s = QSettings("DecAutomation", "Studio")
        all_configs = s.value("graph_configs", {})
        if isinstance(all_configs, dict) and name in all_configs:
            del all_configs[name]
            s.setValue("graph_configs", all_configs)
        
        self._refresh_config_list()
        self._rebuild_config_submenu()
        self._show_toast(f"'{name}' deleted.")

    def toggle_pause(self):
        """Toggle pause: freeze current values so user can zoom, pan, or export without new data updating the graphs."""
        if not self.pause_btn.isEnabled():
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.setText("▶ Resume")
            self.pause_btn.setStyleSheet("""
                QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: #66BB6A; }
                QPushButton:pressed { background-color: #388E3C; }
            """)
        else:
            self.pause_btn.setText("⏸ Pause")
            self.pause_btn.setStyleSheet("""
                QPushButton { background-color: #FF9800; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: #FFB74D; }
                QPushButton:pressed { background-color: #F57C00; }
            """)

    def toggle_trigger(self):
        """Toggle trigger state: Trigger (True) or Stop (False). Only Snap7 supports trigger."""
        if (not self.plc_thread or not self.plc_thread.is_alive()) and (not self.ads_thread or not self.ads_thread.is_alive()) and (not self.simulator_thread or not self.simulator_thread.isRunning()):
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first.")
            return
        if self.simulator_thread and self.simulator_thread.isRunning():
            QMessageBox.warning(self, "Simulation Mode", "Trigger is not available in simulation mode.")
            return
        if self.ads_thread and self.ads_thread.is_alive():
            QMessageBox.warning(self, "ADS Mode", "Trigger is not available for ADS yet (Snap7 only).")
            return
        
        selected_var = self.trigger_var_combo.currentText()
        if not selected_var or selected_var == "No BOOL variables found":
            QMessageBox.warning(self, "No Variable Selected", "Please select a boolean variable to trigger.")
            return
        
        try:
            if not self.trigger_active:
                # Start trigger: set to True
                if self.plc_thread.write_bool(selected_var, True):
                    self.trigger_active = True
                    self.trigger_btn.setText("⏹ Stop")
                    self.trigger_btn.setStyleSheet("""
                        QPushButton { 
                            background-color: #cc3333; 
                            color: white; 
                            font-weight: bold; 
                            padding: 10px; 
                            border: none; 
                            border-radius: 4px; 
                        }
                        QPushButton:hover { background-color: #ff4444; }
                        QPushButton:pressed { background-color: #aa2222; }
                    """)
                    logging.info(f"Trigger activated for {selected_var}")
                else:
                    QMessageBox.warning(self, "Trigger Error", f"Failed to set {selected_var} to True")
            else:
                # Stop trigger: set to False
                if self.plc_thread.write_bool(selected_var, False):
                    self.trigger_active = False
                    self.trigger_btn.setText("⚡ Trigger")
                    self.trigger_btn.setStyleSheet("""
                        QPushButton { 
                            background-color: #ff6b00; 
                            color: white; 
                            font-weight: bold; 
                            padding: 10px; 
                            border: none; 
                            border-radius: 4px; 
                        }
                        QPushButton:hover { background-color: #ff8800; }
                        QPushButton:pressed { background-color: #cc5500; }
                    """)
                    logging.info(f"Trigger stopped for {selected_var}")
                else:
                    QMessageBox.warning(self, "Trigger Error", f"Failed to set {selected_var} to False")
        except Exception as e:
            QMessageBox.warning(self, "Trigger Error", f"Failed to toggle trigger: {e}")
            # Reset button state on error
            self.trigger_active = False
            self.trigger_btn.setText("⚡ Trigger")
            self.trigger_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ff6b00; 
                    color: white; 
                    font-weight: bold; 
                    padding: 10px; 
                    border: none; 
                    border-radius: 4px; 
                }
                QPushButton:hover { background-color: #ff8800; }
                QPushButton:pressed { background-color: #cc5500; }
            """)

    def _update_ram_label(self):
        """Update the subtle RAM usage label at the bottom-left."""
        ram_mb = get_process_ram_mb()
        if ram_mb is not None:
            self.ram_label.setText(f"RAM: {ram_mb:.0f} MB")
        else:
            self.ram_label.setText("")
        self.ram_label.adjustSize()

    def _show_toast(self, message, duration_ms=3000):
        """Show a brief non-blocking toast notification at the bottom-center of the window."""
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        # Position: bottom-center, above the RAM label
        x = (self.width() - self._toast_label.width()) // 2
        y = self.height() - self._toast_label.height() - 32
        self._toast_label.move(x, y)
        self._toast_label.raise_()
        self._toast_label.show()
        self._toast_timer.start(duration_ms)

    def resizeEvent(self, event):
        """Keep RAM label and toast anchored on window resize."""
        super().resizeEvent(event)
        if hasattr(self, 'ram_label'):
            self.ram_label.move(6, self.height() - 22)
        if hasattr(self, '_toast_label') and self._toast_label.isVisible():
            x = (self.width() - self._toast_label.width()) // 2
            y = self.height() - self._toast_label.height() - 32
            self._toast_label.move(x, y)

    # ── Frameless window edge-resizing (Windows native hit-test) ────────
    _BORDER = 8  # pixels from edge that trigger resize

    def nativeEvent(self, eventType, message):
        """Handle Windows WM_NCHITTEST for edge/corner resize on frameless window."""
        try:
            import ctypes
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                # Cursor position in physical screen pixels (signed 16-bit)
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                # Use Win32 GetWindowRect so coordinates match lParam's space
                # (avoids DPI logical-vs-physical pixel mismatch with Qt's frameGeometry)
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(msg.hWnd, ctypes.byref(rect))
                b = self._BORDER
                at_left   = x - rect.left < b
                at_right  = rect.right - x < b
                at_top    = y - rect.top < b
                at_bottom = rect.bottom - y < b
                # HTLEFT=10 HTRIGHT=11 HTTOP=12 HTTOPLEFT=13 HTTOPRIGHT=14
                # HTBOTTOM=15 HTBOTTOMLEFT=16 HTBOTTOMRIGHT=17
                if at_top and at_left:
                    return True, 13
                if at_top and at_right:
                    return True, 14
                if at_bottom and at_left:
                    return True, 16
                if at_bottom and at_right:
                    return True, 17
                if at_left:
                    return True, 10
                if at_right:
                    return True, 11
                if at_top:
                    return True, 12
                if at_bottom:
                    return True, 15
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        self._save_last_config()
        # Close analytics window if open
        if self.analytics_window is not None:
            self.analytics_window.close()
            self.analytics_window = None
        # Get recording DB path before stopping thread (Snap7 only)
        db_path = None
        if self.plc_thread:
            db_path = getattr(self.plc_thread, "db_path", None)
        if self.simulator_thread and self.simulator_thread.isRunning():
            self.simulator_thread._is_running = False
            self.simulator_thread.wait(2000)
        if self.ads_thread and self.ads_thread.is_alive():
            self.ads_thread.stop()
            self.ads_thread.join(timeout=2.0)
        if self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.stop()  # CHECKPOINT + close happens in stop()
            self.plc_thread.join(timeout=2.0)
        if self.plc_thread and getattr(self.plc_thread, "db_connection", None):
            try:
                self.plc_thread.db_connection.close()
            except Exception:
                pass
        # Recording DB is kept on disk (daily .duckdb files) — offer CSV export as convenience
        if db_path and recording_has_data(db_path):
            reply = QMessageBox.question(
                self,
                "Export recording to CSV?",
                "Today's recording is saved in the .duckdb file and will persist.\n"
                "Would you also like to export it to CSV?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                t_min, t_max = get_recording_time_range(db_path)
                export_dlg = ExportRecordingDialog(db_path, t_min, t_max, self)
                if export_dlg.exec() == QDialog.Accepted:
                    from_dt, to_dt, interval_sec = export_dlg.get_from_to_interval()
                    path, _ = QFileDialog.getSaveFileName(
                        self, "Export recording to CSV", "", "CSV (*.csv);;All files (*)"
                    )
                    if path:
                        try:
                            n = export_recording_to_csv(db_path, from_dt, to_dt, interval_sec, path)
                            logging.info(f"Exported {n} rows to {path}")
                        except Exception as e:
                            logging.exception("Export recording failed")
                            QMessageBox.warning(
                                self, "Export failed", f"Export failed:\n{e}"
                            )
        # Export each graph to separate CSV (_plot1, _plot2, ...) on close
        if self.graphs:
            reply = QMessageBox.question(
                self,
                "Export graph data to CSV?",
                f"Export data from {len(self.graphs)} graph(s) to separate CSV files?\n"
                "(e.g. filename_plot1.csv, filename_plot2.csv, ...)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                base_path, _ = QFileDialog.getSaveFileName(
                    self, "Export graph data (base name)", "graph_export.csv", "CSV (*.csv);;All files (*)"
                )
                if base_path:
                    base = base_path.rsplit(".", 1)[0] if "." in base_path else base_path
                    exported = 0
                    for i, graph in enumerate(self.graphs, start=1):
                        plot_path = f"{base}_plot{i}.csv"
                        try:
                            if graph.export_graph_data_to_csv(path=plot_path):
                                exported += 1
                                logging.info(f"Exported graph {i} to {plot_path}")
                        except Exception as e:
                            logging.warning(f"Export graph {i} failed: {e}")
                    if exported:
                        self._show_toast(f"Exported {exported} graph(s) to CSV")
        if self.offline_db:
            try:
                self.offline_db.close()
            except Exception:
                pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
