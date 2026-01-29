import sys
import json
import os
import logging

import duckdb
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                               QListWidget, QPushButton, QSplitter, QScrollArea,
                               QAbstractItemView, QLabel, QApplication, QFrame,
                               QDialog, QComboBox, QDialogButtonBox, QFormLayout,
                               QCheckBox, QLineEdit, QMessageBox, QFileDialog,
                               QTableWidget, QTableWidgetItem, QGroupBox, QHeaderView)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSettings
from PySide6.QtGui import QPalette, QColor
import pyqtgraph as pg
from collections import deque
import numpy as np
from external.plc_thread import PLCThread
from external.plc_ads_thread import PLCADSThread
from external.plc_simulator import PLCSimulator

class GraphConfigDialog(QDialog):
    """Dialog to configure graph parameters before creation."""
    def __init__(self, variable_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graph Configuration")
        self.resize(300, 150)
        self.setStyleSheet("""
            QDialog { background-color: #333; color: white; }
            QLabel { color: white; font-size: 14px; }
            QComboBox {
                background-color: #444; color: white; border: 1px solid #555; padding: 5px;
            }
            QPushButton {
                background-color: #007ACC; color: white; padding: 8px 15px; border: none;
            }
            QPushButton:hover { background-color: #0098FF; }
        """)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.combo_x_axis = QComboBox()
        self.combo_x_axis.addItem("Time (Index)")
        for var in variable_list:
            self.combo_x_axis.addItem(var)
        form_layout.addRow("X-Axis Source:", self.combo_x_axis)
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        return {"x_axis": self.combo_x_axis.currentText()}

class RangeConfigDialog(QDialog):
    """Dialog to configure Min/Max ranges for axes."""
    def __init__(self, current_settings, has_dual_y=False, show_recipes=True, has_two_variables=False, show_delta=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Axis Range Settings")
        self.setModal(True)
        self.resize(400, 250)
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
            spin_min = pg.SpinBox(value=vals.get("min", 0.0), decimals=2, bounds=(-1e9, 1e9))
            spin_min.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            spin_min.setEnabled(not vals.get("auto", True))
            spin_max = pg.SpinBox(value=vals.get("max", 10.0), decimals=2, bounds=(-1e9, 1e9))
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
        return settings

class DynamicPlotWidget(QWidget):
    """
    A wrapper around pyqtgraph.PlotWidget that manages its own data lines.
    Supports dual Y-axes, XY plotting, live value headers, and hover inspection.
    """
    def __init__(self, variable_names, x_axis_source="Time (Index)", buffer_size=500, recipe_params=None, latest_values_cache=None, variable_metadata=None, comm_speed=0.05):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)

        self.variables = variable_names
        self.x_axis_source = x_axis_source
        self.is_xy_plot = (x_axis_source != "Time (Index)")
        self.recipe_params = recipe_params if recipe_params else []
        self.latest_values_cache = latest_values_cache if latest_values_cache else {}
        self.variable_metadata = variable_metadata if variable_metadata else {}
        self.show_recipes_in_tooltip = True  # Default to showing recipes
        self.show_delta_on_graph = False  # When True and 2 variables, plot delta (var2 - var1)
        self.comm_speed = comm_speed  # Communication speed for time calculation
        
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

        self.btn_export_csv = QPushButton("📥")
        self.btn_export_csv.setFixedSize(24, 24)
        self.btn_export_csv.setCursor(Qt.PointingHandCursor)
        self.btn_export_csv.setToolTip("Export graph data to CSV (semicolon-separated)")
        self.btn_export_csv.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: 1px solid #444; border-radius: 4px; }
            QPushButton:hover { background-color: #444; color: white; }
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
        self.plot_widget.setLabel('bottom', self.x_axis_source if self.is_xy_plot else 'Time (MM:SS.mmm)')
        
        # Set up time formatter for x-axis when using Time (Index)
        if not self.is_xy_plot:
            self.setup_time_formatter()

        self.lines = {}
        self.buffers_y = {}
        self.buffers_x = {}
        self.buffer_timestamps = deque(maxlen=buffer_size)  # Store actual timestamps for each data point
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
        
        # Y-axis: determine if dual axis will be used
        is_dual_y = (len(self.variables) == 2 and not self.is_xy_plot)
        
        if is_dual_y:
            # Dual Y-axis: first variable on y1, second on y2
            var1 = self.variables[0]
            var2 = self.variables[1]
            
            if var1 in self.variable_metadata:
                y1_meta = self.variable_metadata[var1]
                y1_min, y1_max = y1_meta.get("min", 0.0), y1_meta.get("max", 10.0)
            else:
                y1_min, y1_max = 0.0, 10.0
            
            if var2 in self.variable_metadata:
                y2_meta = self.variable_metadata[var2]
                y2_min, y2_max = y2_meta.get("min", 0.0), y2_meta.get("max", 10.0)
            else:
                y2_min, y2_max = 0.0, 10.0
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
            "y2": {"auto": True, "min": y2_min, "max": y2_max}
        }

        if len(self.variables) == 2 and not self.is_xy_plot:
            self._setup_dual_axis()
        else:
            self._setup_single_axis()

        # For time-based plots with X auto: use sliding window so latest value stays visible
        if not self.is_xy_plot and self.range_settings["x"]["auto"]:
            self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)

    def _update_time_plot_x_range(self):
        """Shift X range so the graph shows the latest values (sliding window pinned to the right)."""
        if self.is_xy_plot or not self.range_settings["x"]["auto"]:
            return
        n = len(self.buffer_timestamps)
        if n == 0:
            return
        window = self.buffer_size
        x_min = max(0, n - window)
        x_max = n
        self.plot_widget.plotItem.setXRange(x_min, x_max, padding=0)

    def update_time_display(self):
        """Update the time display label with current day number and hour"""
        now = datetime.now()
        day_of_year = now.timetuple().tm_yday
        hour = now.hour
        # Show day number and hour, update if hour changes
        if hour != self.start_hour:
            self.start_hour = hour
        self.time_display_label.setText(f"Day {day_of_year} | Hour {hour:02d}:{now.minute:02d}:{now.second:02d}")
    
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
        """Set up custom formatter for time axis"""
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

        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.DashLine))
        self.tooltip = pg.TextItem(anchor=(0, 1), color='#ddd', fill=QColor(0, 0, 0, 150))
        self.tooltip.setZValue(2)
        self.plot_widget.addItem(self.crosshair_v, ignoreBounds=True)
        self.plot_widget.addItem(self.tooltip, ignoreBounds=True)
        self.tooltip.hide()
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def _setup_single_axis(self):
        self.line_delta = None  # No delta line for single variable or XY
        for i, var in enumerate(self.variables):
            color = self.colors[i % len(self.colors)]
            self._add_variable(var, color, self.plot_widget.plotItem)

    def _setup_dual_axis(self):
        var1, var2 = self.variables[0], self.variables[1]
        color1, color2 = self.colors[0], self.colors[1]
        p1 = self.plot_widget.plotItem
        p1.setLabels(left=var1)
        p1.getAxis('left').setPen(color1)
        p1.getAxis('left').setTextPen(color1)
        self._add_variable(var1, color1, p1)

        self.p2 = pg.ViewBox()
        p1.showAxis('right')
        p1.scene().addItem(self.p2)
        p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(p1)
        p1.getAxis('right').setLabel(var2, color=color2)
        p1.getAxis('right').setPen(color2)
        p1.getAxis('right').setTextPen(color2)
        self._add_variable(var2, color2, self.p2)
        # Delta line (var2 - var1) on left axis, shown only when "Show delta" is enabled
        self.line_delta = pg.PlotCurveItem(name="Delta", pen=pg.mkPen('#FF9800', width=2), antialias=True)
        p1.addItem(self.line_delta)
        self.line_delta.hide()
        
        def updateViews():
            self.p2.setGeometry(p1.vb.sceneBoundingRect())
            self.p2.linkedViewChanged(p1.vb, self.p2.XAxis)
        updateViews()
        p1.vb.sigResized.connect(updateViews)

    def _add_variable(self, var, color, plot_item):
        pen = pg.mkPen(color=color, width=2)
        symbol = 'o' if self.is_xy_plot else None
        symbolBrush = color if self.is_xy_plot else None

        if isinstance(plot_item, pg.ViewBox):
            line = pg.PlotCurveItem(name=var, pen=pen, symbol=symbol, symbolBrush=symbolBrush, antialias=True)
            plot_item.addItem(line)
        else:
            line = plot_item.plot(name=var, pen=pen, symbol=symbol, symbolBrush=symbolBrush, antialias=True)
        
        self.lines[var] = line
        self.buffers_y[var] = deque(maxlen=self.buffer_size)
        if self.is_xy_plot:
            self.buffers_x[var] = deque(maxlen=self.buffer_size)
        lbl = QLabel(f"{var}: --")
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
                parent=parent_window
            )
            dialog.setModal(True)
            if dialog.exec() == QDialog.Accepted:
                settings = dialog.get_settings()
                self.range_settings = settings
                
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
                
                # Update recipe display setting
                if "show_recipes" in settings:
                    self.show_recipes_in_tooltip = settings["show_recipes"]
                if "show_delta" in settings and len(self.variables) == 2:
                    self.show_delta_on_graph = settings["show_delta"]
                    self._update_delta_line()
        except Exception as e:
            print(f"Error opening range settings dialog: {e}")
            import traceback
            traceback.print_exc()

    def export_graph_data_to_csv(self):
        """Export current graph buffer data to CSV with semicolon separator. Format: index;var1;var2;..."""
        path, _ = QFileDialog.getSaveFileName(self, "Export graph data", "", "CSV (*.csv)")
        if not path:
            return
        try:
            # Build rows: common length across all variable buffers
            buffers = [list(self.buffers_y.get(v, [])) for v in self.variables]
            if not buffers:
                return
            n = max(len(b) for b in buffers)
            if n == 0:
                return
            with open(path, "w", newline="", encoding="utf-8") as f:
                header = "index;" + ";".join(self.variables)
                f.write(header + "\n")
                for i in range(n):
                    row = [str(i)]
                    for v in self.variables:
                        buf = self.buffers_y.get(v, [])
                        val = buf[i] if i < len(buf) else ""
                        row.append(str(val) if val != "" and val is not None else "")
                    f.write(";".join(row) + "\n")
        except Exception as e:
            logging.warning(f"Export CSV failed: {e}")
            QMessageBox.warning(self, "Export failed", str(e))

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
            self.line_delta.setData(delta)
            self.line_delta.show()
        else:
            self.line_delta.hide()

    def update_data(self, var_name, y_value, x_value=None):
        if var_name not in self.variables: return
        
        # Skip None values to prevent plotting errors
        if y_value is None:
            return
        
        # Convert to float if possible, otherwise skip
        try:
            y_value = float(y_value)
        except (ValueError, TypeError):
            return
        
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
        
        txt = f"{var_name}: {y_value:.2f} <span style='font-size:10px; color:#aaa;'>(Min:{min_v:.1f} Max:{max_v:.1f})</span>"
        self.value_labels[var_name].setText(txt)
        self._update_time_plot_x_range()
        if len(self.variables) == 2:
            self._update_delta_line()

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
            x_list = list(range(n))
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
                x_list = list(range(n))
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
            else:
                self.lines[var_name].setData(y_list[:min_len])
            if y_list:
                last_val = y_list[-1]
                data = [d for d in y_list if isinstance(d, (int, float)) and not np.isnan(d)]
                min_v = min(data) if data else 0.0
                max_v = max(data) if data else 0.0
                txt = f"{var_name}: {last_val:.2f} <span style='font-size:10px; color:#aaa;'>(Min:{min_v:.1f} Max:{max_v:.1f})</span>"
                self.value_labels[var_name].setText(txt)
        if len(self.variables) == 2:
            self._update_delta_line()

    def update_data_array(self, var_name, array_values):
        """Add all array values at once to the graph.
        Arrays contain oversampled data that should be plotted together.
        Timestamps are distributed over the communication cycle time."""
        if var_name not in self.variables:
            return
        
        if not array_values or len(array_values) == 0:
            return
        
        # Get current timestamp
        current_time = datetime.now()
        array_length = len(array_values)
        
        # Calculate time step: distribute array values over the communication cycle
        # Assume array values were sampled over the communication cycle time
        time_step = self.comm_speed / array_length if array_length > 0 else 0
        
        # Add all array values to buffer with distributed timestamps
        base_buffer_length = len(self.buffers_y.get(var_name, []))
        
        for i, val in enumerate(array_values):
            try:
                y_val = float(val)
                if np.isnan(y_val) or np.isinf(y_val):
                    continue
                
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
            # For time-based plots, plot all y values
            y_data = [float(y) for y in self.buffers_y[var_name] if y is not None and isinstance(y, (int, float)) and not np.isnan(y)]
            if y_data:
                try:
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
        
        txt = f"{var_name}: {latest_value:.2f} <span style='font-size:10px; color:#aaa;'>(Min:{min_v:.1f} Max:{max_v:.1f})</span>"
        self.value_labels[var_name].setText(txt)
        self._update_time_plot_x_range()
        if len(self.variables) == 2:
            self._update_delta_line()

    def mouse_moved(self, evt):
        pos = evt[0]
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            ref_var = self.variables[0] if self.variables else None
            if not ref_var: return
            
            x_data = np.array(self.buffers_x.get(ref_var, [])) if self.is_xy_plot else np.arange(len(self.buffers_y.get(ref_var, [])))
            if len(x_data) == 0: return

            idx = np.abs(x_data - mouse_point.x()).argmin()
            if idx >= len(x_data): return
            x_val = x_data[idx]

            html = f"<div style='background-color: #333; color: white; padding: 8px; border-radius: 4px;'>"
            if self.is_xy_plot:
                html += f"<b>{self.x_axis_source}: {x_val:.2f}</b><br/>"
            else:
                # Get the actual timestamp from buffer_timestamps corresponding to this index
                # The index should correspond to the position in the buffer
                idx_int = int(round(idx))
                if hasattr(self, 'buffer_timestamps') and len(self.buffer_timestamps) > 0:
                    # Clamp index to valid range
                    if idx_int < 0:
                        timestamp = self.buffer_timestamps[0]
                    elif idx_int >= len(self.buffer_timestamps):
                        timestamp = self.buffer_timestamps[-1]
                    else:
                        timestamp = self.buffer_timestamps[idx_int]
                    
                    # Format timestamp as HH:MM:SS.mmm
                    time_str = timestamp.strftime("%H:%M:%S.%f")[:-3]  # Remove last 3 digits of microseconds to get milliseconds
                else:
                    # Fallback: calculate time from index and comm_speed
                    time_str = self.format_time_from_index(idx)
                html += f"<b>Time: {time_str}</b><br/>"
            html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
            for var in self.variables:
                y_data = self.buffers_y.get(var)
                if y_data and idx < len(y_data):
                    y_val = y_data[idx]
                    color = self.lines[var].opts['pen'].color().name()
                    html += f"<span style='color: {color}; font-weight: bold;'>{var}: {y_val:.2f}</span><br/>"

            # Delta (difference) between the two variables, only when exactly 2 variables
            if len(self.variables) == 2:
                y1_data = self.buffers_y.get(self.variables[0])
                y2_data = self.buffers_y.get(self.variables[1])
                if y1_data and y2_data and idx < len(y1_data) and idx < len(y2_data):
                    try:
                        v1, v2 = float(y1_data[idx]), float(y2_data[idx])
                        if not (np.isnan(v1) or np.isnan(v2)):
                            delta = v2 - v1
                            html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
                            html += f"<span style='color: #FF9800; font-weight: bold;'>Delta ({self.variables[1]} − {self.variables[0]}): {delta:.2f}</span><br/>"
                    except (ValueError, TypeError):
                        pass

            # Show recipe parameters only if enabled
            if self.show_recipes_in_tooltip and self.recipe_params:
                html += "<hr style='border-top: 1px solid #555; margin: 4px 0;'/>"
                html += "<b style='color: #FFEA00;'>Recipe Parameters:</b><br/>"
                for param in self.recipe_params:
                    value = self.latest_values_cache.get(param, "N/A")
                    val_str = f"{value:.2f}" if isinstance(value, (float, int)) else str(value)
                    html += f"<span style='color: #ccc;'>{param.replace('_', ' ')}:</span> <b>{val_str}</b><br/>"
            html += "</div>"

            self.tooltip.setHtml(html)
            self.tooltip.setPos(mouse_point.x(), mouse_point.y())
            self.tooltip.show()
            self.crosshair_v.setPos(x_val)
            self.crosshair_v.show()
        else:
            self.tooltip.hide()
            self.crosshair_v.hide()

class MainWindow(QMainWindow):
    data_signal = Signal(str, object)
    status_signal = Signal(str, str, object)  # status_type, message, details

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProAutomation Studio")
        self.resize(1280, 800)
        self.latest_values = {}
        self.all_variables = []
        self.variable_metadata = {}  # Store min/max from CSV files
        self.recipe_params = []  # Will be loaded from recipe_variables.csv
        _ext = os.path.join(os.path.dirname(__file__), "external")
        self.exchange_variables_path = os.path.join(_ext, "exchange_variables.csv")
        self.recipe_variables_path = os.path.join(_ext, "recipe_variables.csv")
        self.apply_theme()
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
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

        # Data mode: Online (real-time) vs Offline (CSV → DuckDB)
        data_mode_layout = QHBoxLayout()
        data_mode_label = QLabel("Data:")
        data_mode_label.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold;")
        data_mode_label.setFixedWidth(50)
        self.data_mode_combo = QComboBox()
        self.data_mode_combo.addItems(["Online Data", "Offline Data"])
        self.data_mode_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.data_mode_combo.setToolTip("Online: real-time PLC/ADS/Simulation. Offline: load a CSV into DuckDB and plot (faster for many parameters).")
        self.data_mode_combo.currentTextChanged.connect(self.on_data_mode_changed)
        data_mode_layout.addWidget(data_mode_label)
        data_mode_layout.addWidget(self.data_mode_combo)
        self.sidebar_layout.addLayout(data_mode_layout)

        # Online panel: connection UI (shown when Online Data)
        self.online_panel = QWidget()
        online_layout = QVBoxLayout(self.online_panel)
        online_layout.setContentsMargins(0, 5, 0, 0)
        online_layout.setSpacing(0)

        # Connection UI
        self.connection_layout = QVBoxLayout()
        
        # Client Device Type dropdown (above Connect/Disconnect)
        device_type_layout = QHBoxLayout()
        device_type_label = QLabel("Client:")
        device_type_label.setStyleSheet("color: #aaa; font-size: 11px;")
        device_type_label.setFixedWidth(60)
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["Snap7", "ADS", "Simulation"])
        self.device_type_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.device_type_combo.setToolTip("Snap7: Siemens S7 (e.g. S7-1500). ADS: Beckhoff (EtherCAT). Simulation: CSV-based simulator (no address).")
        self.device_type_combo.currentTextChanged.connect(self.on_device_type_changed)
        device_type_layout.addWidget(device_type_label)
        device_type_layout.addWidget(self.device_type_combo)
        self.connection_layout.addLayout(device_type_layout)
        
        # Address row (IP for Snap7, Target for ADS; hidden for Simulation)
        self.address_row = QWidget()
        address_row_layout = QHBoxLayout(self.address_row)
        address_row_layout.setContentsMargins(0, 0, 0, 0)
        self.address_label = QLabel("IP:")
        self.address_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.address_label.setFixedWidth(60)
        self.ip_input = QLineEdit("192.168.0.20")
        self.ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.ip_input.setPlaceholderText("192.168.0.20")
        address_row_layout.addWidget(self.address_label)
        address_row_layout.addWidget(self.ip_input)
        self.connection_layout.addWidget(self.address_row)
        # PC IP row (ADS only): your PC's IP/AmsNetId used for the route / local address
        self.pc_ip_row = QWidget()
        pc_ip_layout = QHBoxLayout(self.pc_ip_row)
        pc_ip_layout.setContentsMargins(0, 0, 0, 0)
        self.pc_ip_label = QLabel("PC IP:")
        self.pc_ip_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.pc_ip_label.setFixedWidth(60)
        self.pc_ip_input = QLineEdit("")
        self.pc_ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.pc_ip_input.setPlaceholderText("192.168.1.100 or 192.168.1.100.1.1")
        self.pc_ip_input.setToolTip("Your PC's IP (or AmsNetId). This is the address used for the ADS route on the PLC.")
        pc_ip_layout.addWidget(self.pc_ip_label)
        pc_ip_layout.addWidget(self.pc_ip_input)
        self.connection_layout.addWidget(self.pc_ip_row)
        self.pc_ip_row.setVisible(False)
        # Connect/Disconnect row
        ip_connect_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.setStyleSheet("""
            QPushButton { background-color: #007ACC; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #0098FF; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setCursor(Qt.PointingHandCursor)
        self.disconnect_btn.setEnabled(False)  # Disabled initially
        self.disconnect_btn.setStyleSheet("""
            QPushButton { background-color: #cc3333; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #ff4444; }
            QPushButton:pressed { background-color: #aa2222; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setToolTip("Pause live updates. Values stay as-is so you can zoom, pan, or export.")
        self.pause_btn.setStyleSheet("""
            QPushButton { background-color: #FF9800; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #FFB74D; }
            QPushButton:pressed { background-color: #F57C00; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        ip_connect_layout.addWidget(self.connect_btn)
        ip_connect_layout.addWidget(self.disconnect_btn)
        ip_connect_layout.addWidget(self.pause_btn)
        
        # Speed input row
        speed_layout = QHBoxLayout()
        speed_label = QLabel("Speed (s):")
        speed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        speed_label.setFixedWidth(60)
        self.speed_input = QLineEdit("0.05")
        self.speed_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.speed_input.setToolTip("Communication cycle time in seconds (default: 0.05)")
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_input)
        
        # Buffer size input row
        buffer_layout = QHBoxLayout()
        buffer_label = QLabel("Buffer:")
        buffer_label.setStyleSheet("color: #aaa; font-size: 11px;")
        buffer_label.setFixedWidth(60)
        self.buffer_size_input = QLineEdit("5000")
        self.buffer_size_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.buffer_size_input.setToolTip("Number of data points to keep in graph buffer (default: 5000). For array variables (600 points per update), buffer is automatically scaled to ~18,000 points to show ~30 array updates. Oldest values are automatically removed when limit is reached.")
        buffer_layout.addWidget(buffer_label)
        buffer_layout.addWidget(self.buffer_size_input)
        
        # Variable files: choose exchange and recipe CSVs (any name, browse before connecting)
        vars_label = QLabel("Variable files:")
        vars_label.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold; margin-top: 6px;")
        self.connection_layout.addWidget(vars_label)
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
        self.connection_layout.addLayout(exchange_row)
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
        recipe_row.addWidget(self.recipe_path_edit)
        recipe_row.addWidget(self.browse_recipe_btn)
        self.connection_layout.addLayout(recipe_row)
        
        self.connection_layout.addLayout(ip_connect_layout)
        self.connection_layout.addLayout(speed_layout)
        self.connection_layout.addLayout(buffer_layout)
        online_layout.addLayout(self.connection_layout)

        # PLC Trigger Button Section
        trigger_label = QLabel("PLC TRIGGER")
        trigger_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #888; margin-bottom: 5px; margin-top: 10px;")
        self.sidebar_layout.addWidget(trigger_label)
        
        trigger_layout = QVBoxLayout()
        
        # Variable selection
        var_select_layout = QHBoxLayout()
        var_label = QLabel("Variable:")
        var_label.setStyleSheet("color: #aaa; font-size: 11px;")
        var_label.setFixedWidth(60)
        self.trigger_var_combo = QComboBox()
        self.trigger_var_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        self.trigger_var_combo.setToolTip("Select boolean variable to trigger")
        var_select_layout.addWidget(var_label)
        var_select_layout.addWidget(self.trigger_var_combo)
        trigger_layout.addLayout(var_select_layout)
        
        # Trigger button - push button style (Trigger/Stop toggle)
        self.trigger_btn = QPushButton("⚡ Trigger")
        self.trigger_btn.setCursor(Qt.PointingHandCursor)
        self.trigger_btn.setEnabled(False)  # Disabled until connected
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
        self.trigger_btn.clicked.connect(self.toggle_trigger)
        trigger_layout.addWidget(self.trigger_btn)
        self.pause_btn.clicked.connect(self.toggle_pause)
        
        # Track trigger and pause state
        self.trigger_active = False
        self.paused = False
        
        online_layout.addLayout(trigger_layout)
        self.sidebar_layout.addWidget(self.online_panel)

        # Offline panel: Load CSV → DuckDB + CSV format info (shown when Offline Data)
        self.offline_panel = QWidget()
        offline_main = QHBoxLayout(self.offline_panel)
        offline_main.setContentsMargins(0, 5, 0, 0)
        offline_main.setSpacing(8)
        # Left: Load button and path
        offline_left = QVBoxLayout()
        offline_left.setSpacing(4)
        self.offline_load_btn = QPushButton("Load CSV → DuckDB")
        self.offline_load_btn.setCursor(Qt.PointingHandCursor)
        self.offline_load_btn.setStyleSheet("""
            QPushButton { background-color: #007ACC; color: white; font-weight: bold; padding: 8px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #0098FF; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        self.offline_load_btn.setToolTip("Load a CSV file into DuckDB for fast querying and plotting. Use for large files or many parameters instead of reading CSV repeatedly.")
        self.offline_load_btn.clicked.connect(self.load_offline_csv)
        offline_left.addWidget(self.offline_load_btn)
        self.offline_path_label = QLabel("No file loaded")
        self.offline_path_label.setStyleSheet("color: #888; font-size: 10px;")
        self.offline_path_label.setWordWrap(True)
        offline_left.addWidget(self.offline_path_label)
        offline_main.addLayout(offline_left)
        # Right: CSV format info and example table
        self.offline_info_widget = self._create_offline_csv_info_widget()
        offline_main.addWidget(self.offline_info_widget, 1)
        self.offline_panel.setVisible(False)
        self.sidebar_layout.addWidget(self.offline_panel)

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
        self.sidebar_layout.addWidget(self.var_list)
        self.btn_add_graph = QPushButton("Open Selected in Graph")
        self.btn_add_graph.setCursor(Qt.PointingHandCursor)
        self.btn_add_graph.setStyleSheet("""
            QPushButton { background-color: #007ACC; color: white; font-weight: bold; padding: 12px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #0098FF; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        self.btn_add_graph.clicked.connect(self.add_new_graph)
        self.sidebar_layout.addWidget(self.btn_add_graph)

        # Initialize communication status before creating panel
        self.setup_comm_info_panel()

        # Communication Info Panel (collapsible)
        self.comm_info_panel = self.create_comm_info_panel()
        self.sidebar_layout.addWidget(self.comm_info_panel)

        self.splitter.addWidget(self.sidebar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #1e1e1e; }")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: #1e1e1e;")
        self.graphs_layout = QVBoxLayout(self.scroll_content)
        self.graphs_layout.setContentsMargins(10, 10, 10, 10)

        self.graph_splitter = QSplitter(Qt.Vertical)
        self.graph_splitter.setStyleSheet("QSplitter::handle { background-color: #3e3e42; }")
        self.graph_splitter.setHandleWidth(4)

        self.graphs_layout.addWidget(self.graph_splitter)

        self.scroll_area.setWidget(self.scroll_content)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.setSizes([300, 980])

        self.graphs = []
        self.plc_thread = None
        self.ads_thread = None
        self.simulator_thread = None
        self.load_variables()

        self.connect_btn.clicked.connect(self.start_plc_thread)
        self.disconnect_btn.clicked.connect(self.disconnect_plc)
        self.data_signal.connect(self.update_plot)
        self.status_signal.connect(self.update_comm_status)
        self.speed_input.editingFinished.connect(self.update_speed_while_connected)
        self.on_device_type_changed(self.device_type_combo.currentText())
        self.on_data_mode_changed(self.data_mode_combo.currentText())
        self._update_variable_path_display()
        self._load_last_config()

    def _load_last_config(self):
        """Restore last saved connection config (device type, IPs, variable paths) from cache."""
        s = QSettings("ProAutomation", "Studio")
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
        buf = s.value("buffer_size")
        if buf:
            self.buffer_size_input.setText(buf)
        self.on_device_type_changed(self.device_type_combo.currentText())
        self._update_variable_path_display()
        self.load_variables()

    def _save_last_config(self):
        """Save current connection config so next run shows the latest (e.g. ADS, IPs, variable paths)."""
        s = QSettings("ProAutomation", "Studio")
        s.setValue("device_type", self.device_type_combo.currentText())
        s.setValue("ip_address", self.ip_input.text().strip())
        s.setValue("pc_ip", self.pc_ip_input.text().strip())
        s.setValue("exchange_path", self.exchange_variables_path or "")
        s.setValue("recipe_path", self.recipe_variables_path or "")
        s.setValue("speed", self.speed_input.text().strip())
        s.setValue("buffer_size", self.buffer_size_input.text().strip())
        s.sync()

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

    def on_data_mode_changed(self, mode_text):
        """Switch between Online Data (real-time) and Offline Data (CSV → DuckDB)."""
        if mode_text == "Offline Data":
            self.online_panel.setVisible(False)
            self.offline_panel.setVisible(True)
            # Clear variable list until user loads a CSV
            self.var_list.clear()
            self.all_variables = []
            if self.offline_columns:
                for c in self.offline_columns:
                    self.var_list.addItem(c)
                self.all_variables = list(self.offline_columns)
        else:
            self.online_panel.setVisible(True)
            self.offline_panel.setVisible(False)
            self.load_variables()

    def on_device_type_changed(self, device_type):
        """Show/hide address rows and update labels by Client Device Type (Snap7, ADS, Simulation)."""
        if device_type == "Simulation":
            self.address_row.setVisible(False)
            self.pc_ip_row.setVisible(False)
        else:
            self.address_row.setVisible(True)
            if device_type == "ADS":
                self.address_label.setText("Target (PLC):")
                self.ip_input.setPlaceholderText("192.168.1.10.1.1")
                self.pc_ip_row.setVisible(True)
            else:
                self.address_label.setText("IP:")
                self.ip_input.setPlaceholderText("192.168.0.20")
                self.pc_ip_row.setVisible(False)

    def load_offline_csv(self):
        """Load a user-selected CSV into DuckDB and populate variable list for offline plotting."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV (*.csv);;All files (*)"
        )
        if not path:
            return
        path = os.path.normpath(path)
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
            self.offline_path_label.setText(os.path.basename(path))
            self.offline_path_label.setToolTip(path)
            QMessageBox.information(
                self, "CSV loaded",
                f"Loaded {path} into DuckDB.\n{len(self.offline_columns)} columns available for plotting."
            )
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
            self.ads_thread = PLCADSThread(
                address, self.data_signal, self.status_signal, comm_speed,
                local_address=pc_ip, variable_names=list(self.all_variables)
            )
            self.ads_thread.start()
        else:
            self.simulator_thread = None
            self.ads_thread = None
            self.plc_thread = PLCThread(address, self.data_signal, self.status_signal, comm_speed)
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
        # Speed can be changed while connected, buffer size only applies to new graphs
        self.speed_input.setEnabled(True)
        self.buffer_size_input.setEnabled(False)
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
            self.buffer_size_input.setEnabled(True)
            self.browse_exchange_btn.setEnabled(True)
            self.browse_recipe_btn.setEnabled(True)
            self.trigger_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            QMessageBox.information(self, "Not Connected", "No active PLC, ADS, or simulation to disconnect.")
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
                    graph.value_labels[var_name].setText(f"{var_name}: --")
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
        self.buffer_size_input.setEnabled(True)
        self.browse_exchange_btn.setEnabled(True)
        self.browse_recipe_btn.setEnabled(True)
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
        
        msg = "Successfully disconnected from simulation." if was_simulation else "Successfully disconnected from PLC."
        QMessageBox.information(self, "Disconnected", msg)

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
            self.buffer_size_input.setEnabled(False)
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
            self.buffer_size_input.setEnabled(False)
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
            self.buffer_size_input.setEnabled(True)
            self.browse_exchange_btn.setEnabled(True)
            self.browse_recipe_btn.setEnabled(True)
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
                self.buffer_size_input.setEnabled(True)
                self.browse_exchange_btn.setEnabled(True)
                self.browse_recipe_btn.setEnabled(True)
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
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        app.setPalette(palette)
        # Style context menus to be visible with dark theme
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
        """)

    def load_variables(self):
        """Load variables from the chosen exchange and recipe CSV files (browsable; any filename)."""
        import csv
        
        self.var_list.clear()
        self.all_variables = []
        self.recipe_params = []
        
        # Load boolean variables from JSON for trigger dropdown (Snap7)
        boolean_vars = []
        try:
            config_path = os.path.join("external", "snap7_node_ids.json")
            with open(config_path, 'r') as f:
                config = json.load(f)
                node_config = config.get('Node_id_flexpts_S7_1500_snap7', {})
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
        
        # Load variables from chosen exchange_variables CSV (any name)
        exchange_csv_path = self.exchange_variables_path or os.path.join(os.path.dirname(__file__), "external", "exchange_variables.csv")
        try:
            if os.path.isfile(exchange_csv_path):
                with open(exchange_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        var_name = row.get('Variable', '').strip()
                        if var_name and var_name not in self.all_variables:
                            self.var_list.addItem(var_name)
                            self.all_variables.append(var_name)
                            self.latest_values[var_name] = 0.0
                            try:
                                min_val = float(row.get('Min', '0'))
                                max_val = float(row.get('Max', '10'))
                                self.variable_metadata[var_name] = {"min": min_val, "max": max_val}
                            except (ValueError, TypeError):
                                self.variable_metadata[var_name] = {"min": 0.0, "max": 10.0}
            else:
                logging.warning("Exchange variables file not found: %s", exchange_csv_path)
        except Exception as e:
            logging.error("Error loading exchange variables CSV %s: %s", exchange_csv_path, e)
        
        # Load recipe parameters from chosen recipe_variables CSV (any name)
        recipe_csv_path = self.recipe_variables_path or os.path.join(os.path.dirname(__file__), "external", "recipe_variables.csv")
        try:
            if os.path.isfile(recipe_csv_path):
                with open(recipe_csv_path, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        var_name = row.get('Variable', '').strip()
                        if var_name:
                            self.recipe_params.append(var_name)
                            if var_name not in self.latest_values:
                                self.latest_values[var_name] = 0.0
                            try:
                                min_val = float(row.get('Min', '0'))
                                max_val = float(row.get('Max', '10'))
                                self.variable_metadata[var_name] = {"min": min_val, "max": max_val}
                            except (ValueError, TypeError):
                                self.variable_metadata[var_name] = {"min": 0.0, "max": 10.0}
            else:
                logging.warning("Recipe variables file not found: %s", recipe_csv_path)
        except Exception as e:
            logging.error("Error loading recipe variables CSV %s: %s", recipe_csv_path, e)
            self.recipe_params = []

    def _quote_duckdb_identifier(self, name):
        """Quote identifier for DuckDB (handles spaces and special chars)."""
        return '"' + str(name).replace('"', '""') + '"'

    def add_new_graph(self):
        selected_items = self.var_list.selectedItems()
        if not selected_items:
            return
        var_names = [item.text() for item in selected_items]
        is_offline = self.data_mode_combo.currentText() == "Offline Data"
        if is_offline:
            if not self.offline_db or not self.offline_columns:
                QMessageBox.warning(self, "No data", "Load a CSV first (Offline Data → Load CSV → DuckDB).")
                return
        dialog = GraphConfigDialog(self.all_variables, self)
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
        title_text = f"{' • '.join(var_names)}  [vs {settings['x_axis']}]"
        lbl_title = QLabel(title_text, styleSheet="font-weight: bold; color: #ccc; font-size: 13px;")
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
            cols = [x_col] + [v for v in var_names if v != x_col]
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
                comm_speed=comm_speed
            )
            vbox.addWidget(new_graph)
            self.graph_splitter.addWidget(container)
            self.graphs.append(new_graph)
            btn_close.clicked.connect(lambda: self.remove_graph(container, new_graph))
            col_index = {name: i for i, name in enumerate(cols)}
            x_data = [row[0] for row in result]
            y_series = {v: [row[col_index[v]] for row in result] for v in var_names if v in col_index}
            new_graph.set_static_data(x_data, y_series)
            return

        # Online: existing behavior
        try:
            buffer_size = int(self.buffer_size_input.text())
            if buffer_size <= 0:
                raise ValueError("Buffer size must be positive")
        except ValueError:
            QMessageBox.warning(self, "Invalid Buffer Size", "Please enter a valid positive integer for buffer size (e.g., 500). Using default: 500")
            buffer_size = 500

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
            comm_speed=comm_speed
        )
        vbox.addWidget(new_graph)
        self.graph_splitter.addWidget(container)
        self.graphs.append(new_graph)
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
                if variable_name in graph.variables or variable_name == graph.x_axis_source:
                    # Plot all array values at once
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
                if variable_name in graph.variables or variable_name == graph.x_axis_source:
                    x_val = self.latest_values.get(graph.x_axis_source, 0.0) if graph.is_xy_plot else None
                    # Ensure x_val is numeric if provided
                    if x_val is not None:
                        try:
                            x_val = float(x_val)
                        except (ValueError, TypeError):
                            x_val = 0.0
                    graph.update_data(variable_name, value, x_value=x_val)

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

    def closeEvent(self, event):
        self._save_last_config()
        if self.simulator_thread and self.simulator_thread.isRunning():
            self.simulator_thread._is_running = False
            self.simulator_thread.wait(2000)
        if self.ads_thread and self.ads_thread.is_alive():
            self.ads_thread.stop()
            self.ads_thread.join(timeout=2.0)
        if self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.stop()
            self.plc_thread.join(timeout=2.0)
        if self.plc_thread and getattr(self.plc_thread, 'db_connection', None):
            try:
                self.plc_thread.db_connection.close()
            except Exception:
                pass
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
