import sys
import json
import os
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                               QListWidget, QPushButton, QSplitter, QScrollArea,
                               QAbstractItemView, QLabel, QApplication, QFrame,
                               QDialog, QComboBox, QDialogButtonBox, QFormLayout,
                               QCheckBox, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QTimer
from PySide6.QtGui import QPalette, QColor
import pyqtgraph as pg
from collections import deque
import numpy as np
from external.plc_thread import PLCThread

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
    def __init__(self, current_settings, has_dual_y=False, show_recipes=True, parent=None):
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
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        settings = {
            "x": {"auto": self.chk_x_auto.isChecked(), "min": self.spin_x_min.value(), "max": self.spin_x_max.value()},
            "y1": {"auto": self.chk_y1_auto.isChecked(), "min": self.spin_y1_min.value(), "max": self.spin_y1_max.value()},
            "show_recipes": self.chk_show_recipes.isChecked()
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
        except Exception as e:
            print(f"Error opening range settings dialog: {e}")
            import traceback
            traceback.print_exc()

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

        # Connection UI
        self.connection_layout = QVBoxLayout()
        
        # IP and Connect/Disconnect row
        ip_connect_layout = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.0.20")
        self.ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
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
        ip_connect_layout.addWidget(self.ip_input)
        ip_connect_layout.addWidget(self.connect_btn)
        ip_connect_layout.addWidget(self.disconnect_btn)
        
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
        
        self.connection_layout.addLayout(ip_connect_layout)
        self.connection_layout.addLayout(speed_layout)
        self.connection_layout.addLayout(buffer_layout)
        self.sidebar_layout.addLayout(self.connection_layout)

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
        
        # Track trigger state
        self.trigger_active = False
        
        self.sidebar_layout.addLayout(trigger_layout)

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
        self.load_variables()

        self.connect_btn.clicked.connect(self.start_plc_thread)
        self.disconnect_btn.clicked.connect(self.disconnect_plc)
        self.data_signal.connect(self.update_plot)
        self.status_signal.connect(self.update_comm_status)
        self.speed_input.editingFinished.connect(self.update_speed_while_connected)

    def setup_comm_info_panel(self):
        """Initialize communication status variables"""
        self.comm_status = {
            "connected": False,
            "last_message": "Not connected",
            "read_count": 0,
            "error_count": 0,
            "last_error": None,
            "ip_address": None
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

    def start_plc_thread(self):
        if self.plc_thread and self.plc_thread.is_alive():
            QMessageBox.warning(self, "Connection Active", "Already connected to the PLC.")
            return
        
        # Clean up any existing thread first
        if self.plc_thread:
            try:
                self.plc_thread.stop()
                self.plc_thread.join(timeout=1.0)
            except:
                pass
        
        ip_address = self.ip_input.text()
        
        # Get communication speed
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
        
        self.comm_status["ip_address"] = ip_address
        self.comm_status["connected"] = False
        self.comm_status["read_count"] = 0
        self.comm_status["error_count"] = 0
        self.comm_status["last_error"] = None
        self.update_comm_info_display()
        
        self.plc_thread = PLCThread(ip_address, self.data_signal, self.status_signal, comm_speed)
        self.plc_thread.start()
        
        # Update button states
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.ip_input.setEnabled(False)
        # Speed can be changed while connected, buffer size only applies to new graphs
        self.speed_input.setEnabled(True)
        self.buffer_size_input.setEnabled(False)
        self.trigger_btn.setEnabled(True)  # Enable trigger when connected
        # Reset trigger state on new connection
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
            QPushButton:disabled { background-color: #555; color: #888; }
        """)

    def disconnect_plc(self):
        """Disconnect from PLC and stop the communication thread"""
        if not self.plc_thread or not self.plc_thread.is_alive():
            # Even if thread is not alive, we need to re-enable the IP input
            # This handles the case where connection failed but UI is still disabled
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.ip_input.setEnabled(True)
            self.speed_input.setEnabled(True)
            self.buffer_size_input.setEnabled(True)
            self.trigger_btn.setEnabled(False)  # Disable trigger when disconnected
            QMessageBox.information(self, "Not Connected", "No active PLC connection to disconnect.")
            return
        
        # Stop the PLC thread
        self.plc_thread.stop()
        
        # Wait for thread to finish (with timeout)
        if not self.plc_thread.join(timeout=2.0):
            # Force stop if thread doesn't respond
            logging.warning("PLC thread did not stop gracefully, forcing termination")
        
        # Clear graph buffers to remove any None values
        for graph in self.graphs:
            for var_name in graph.buffers_y.keys():
                # Clear and reinitialize buffers
                graph.buffers_y[var_name].clear()
                if var_name in graph.buffers_x:
                    graph.buffers_x[var_name].clear()
                # Clear the plot line
                if var_name in graph.lines:
                    graph.lines[var_name].setData([], [])
                # Reset value labels
                if var_name in graph.value_labels:
                    graph.value_labels[var_name].setText(f"{var_name}: --")
            # Clear timestamp buffer
            if hasattr(graph, 'buffer_timestamps'):
                graph.buffer_timestamps.clear()
        
        # Update status
        self.comm_status["connected"] = False
        self.comm_status["last_message"] = "Disconnected from PLC"
        self.comm_status["last_error"] = None
        self.comm_status["read_count"] = 0
        self.comm_status["error_count"] = 0
        self.update_comm_info_display()
        
        # Update button states
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.ip_input.setEnabled(True)
        self.speed_input.setEnabled(True)
        self.buffer_size_input.setEnabled(True)
        self.trigger_btn.setEnabled(False)  # Disable trigger when disconnected
        # Reset trigger state on disconnect
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
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        
        # Clear latest values
        for key in self.latest_values:
            self.latest_values[key] = 0.0
        
        QMessageBox.information(self, "Disconnected", "Successfully disconnected from PLC.")

    @Slot(str, str, object)
    def update_comm_status(self, status_type, message, details):
        """Update communication status from PLC thread"""
        if status_type == "connected":
            self.comm_status["connected"] = True
            self.comm_status["last_message"] = message
            # Update button states when connected
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.ip_input.setEnabled(False)
            # Speed can be changed while connected, buffer size only applies to new graphs
            self.speed_input.setEnabled(True)
            self.buffer_size_input.setEnabled(False)
            self.trigger_btn.setEnabled(True)  # Enable trigger when connected
            # Reset trigger state when connection is established
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
        elif status_type == "disconnected":
            self.comm_status["connected"] = False
            self.comm_status["last_message"] = message
            # Update button states when disconnected
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.ip_input.setEnabled(True)
            self.speed_input.setEnabled(True)
            self.trigger_btn.setEnabled(False)  # Disable trigger when disconnected
            self.buffer_size_input.setEnabled(True)
            # Reset trigger state when disconnected
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
                QPushButton:disabled { background-color: #555; color: #888; }
            """)
        elif status_type == "error":
            self.comm_status["last_error"] = message
            if "error_count" in details:
                self.comm_status["error_count"] = details["error_count"]
            # If we get an error and we're not connected, re-enable the IP input
            # This handles the case where connection fails immediately
            if not self.comm_status["connected"]:
                self.connect_btn.setEnabled(True)
                self.disconnect_btn.setEnabled(False)
                self.ip_input.setEnabled(True)
                self.speed_input.setEnabled(True)
                self.buffer_size_input.setEnabled(True)
        elif status_type == "stats":
            if "read_count" in details:
                self.comm_status["read_count"] = details["read_count"]
            if "error_count" in details:
                self.comm_status["error_count"] = details["error_count"]
        elif status_type == "info":
            self.comm_status["last_message"] = message
        
        self.update_comm_info_display()

    def update_speed_while_connected(self):
        """Update communication speed while connected, or validate if not connected"""
        try:
            new_speed = float(self.speed_input.text())
            if new_speed <= 0:
                raise ValueError("Speed must be positive")
            
            # If connected, update the PLC thread speed dynamically
            if self.plc_thread and self.plc_thread.is_alive():
                self.plc_thread.update_speed(new_speed)
            
            # Update speed for all existing graphs
            for graph in self.graphs:
                if hasattr(graph, 'comm_speed'):
                    graph.comm_speed = new_speed
        except ValueError:
            # Invalid input, show warning and revert to previous value
            QMessageBox.warning(self, "Invalid Speed", 
                              "Please enter a valid positive number for communication speed (e.g., 0.05)")
            # Revert to the last valid speed (get it from the thread if connected, otherwise use default)
            if self.plc_thread and self.plc_thread.is_alive():
                with self.plc_thread._comm_speed_lock:
                    current_speed = self.plc_thread.comm_speed
                self.speed_input.setText(str(current_speed))
            else:
                self.speed_input.setText("0.05")

    def update_comm_info_display(self):
        """Update the communication info panel display"""
        status = self.comm_status
        
        # Status label with color
        if status["connected"]:
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
        
        # Last message/error
        if status["last_error"]:
            self.comm_message_label.setText(f"⚠ {status['last_error']}")
            self.comm_message_label.setStyleSheet("color: #FF1744; font-size: 10px;")
        elif status["last_message"]:
            self.comm_message_label.setText(f"ℹ {status['last_message']}")
            self.comm_message_label.setStyleSheet("color: #888; font-size: 10px;")
        else:
            self.comm_message_label.setText("")

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
        """Load variables from CSV files and recipe parameters separately."""
        import csv
        
        # Load boolean variables from JSON for trigger dropdown
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
        
        # Load regular variables from exchange_variables.csv
        try:
            exchange_csv_path = os.path.join("external", "exchange_variables.csv")
            with open(exchange_csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    var_name = row.get('Variable', '').strip()
                    if var_name and var_name not in self.all_variables:
                        self.var_list.addItem(var_name)
                        self.all_variables.append(var_name)
                        self.latest_values[var_name] = 0.0
                        # Store metadata (min/max) from CSV
                        try:
                            min_val = float(row.get('Min', '0'))
                            max_val = float(row.get('Max', '10'))
                            self.variable_metadata[var_name] = {"min": min_val, "max": max_val}
                        except (ValueError, TypeError):
                            # Default values if parsing fails
                            self.variable_metadata[var_name] = {"min": 0.0, "max": 10.0}
        except FileNotFoundError:
            print("Error: exchange_variables.csv not found in external folder.")
        except Exception as e:
            print(f"Error loading exchange_variables.csv: {e}")
        
        # Load recipe parameters from recipe_variables.csv
        try:
            recipe_csv_path = os.path.join("external", "recipe_variables.csv")
            with open(recipe_csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                self.recipe_params = []
                for row in reader:
                    var_name = row.get('Variable', '').strip()
                    if var_name:
                        self.recipe_params.append(var_name)
                        # Initialize recipe parameter values
                        if var_name not in self.latest_values:
                            self.latest_values[var_name] = 0.0
                        # Store metadata for recipe parameters too
                        try:
                            min_val = float(row.get('Min', '0'))
                            max_val = float(row.get('Max', '10'))
                            self.variable_metadata[var_name] = {"min": min_val, "max": max_val}
                        except (ValueError, TypeError):
                            self.variable_metadata[var_name] = {"min": 0.0, "max": 10.0}
        except FileNotFoundError:
            print("Error: recipe_variables.csv not found in external folder.")
            # Fallback to empty list
            self.recipe_params = []
        except Exception as e:
            print(f"Error loading recipe_variables.csv: {e}")
            self.recipe_params = []

    def add_new_graph(self):
        selected_items = self.var_list.selectedItems()
        if not selected_items: return
        var_names = [item.text() for item in selected_items]
        dialog = GraphConfigDialog(self.all_variables, self)
        if dialog.exec() == QDialog.Accepted:
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
            
            # Get buffer size from input, validate it
            try:
                buffer_size = int(self.buffer_size_input.text())
                if buffer_size <= 0:
                    raise ValueError("Buffer size must be positive")
            except ValueError:
                QMessageBox.warning(self, "Invalid Buffer Size", "Please enter a valid positive integer for buffer size (e.g., 500). Using default: 500")
                buffer_size = 500
            
            # Check if any selected variables are arrays (they add 600 points per update)
            # If arrays are present, scale buffer size to accommodate more array updates
            has_arrays = any(var_name.startswith('arr') for var_name in var_names)
            if has_arrays:
                # Arrays add 600 points per communication cycle
                # Scale buffer to hold at least 25-30 array updates for better visibility
                # If user set 5000, that's ~8 array updates, scale to ~30 updates = 18,000 points
                array_size = 600  # Standard array size
                min_array_updates = 30  # Minimum number of array updates to keep in buffer
                scaled_buffer_size = max(buffer_size, array_size * min_array_updates)
                if scaled_buffer_size > buffer_size:
                    # Inform user that buffer was scaled up for arrays
                    logging.info(f"Buffer size scaled from {buffer_size} to {scaled_buffer_size} to accommodate array variables (600 points per update)")
                    buffer_size = scaled_buffer_size
            
            # Get current communication speed
            try:
                comm_speed = float(self.speed_input.text())
                if comm_speed <= 0:
                    comm_speed = 0.05  # Default
            except ValueError:
                comm_speed = 0.05  # Default
            
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
            
            self.graph_splitter.addWidget(container) # Add to splitter
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

    def toggle_trigger(self):
        """Toggle trigger state: Trigger (True) or Stop (False)"""
        if not self.plc_thread or not self.plc_thread.is_alive():
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first.")
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
        if self.plc_thread and self.plc_thread.is_alive():
            self.plc_thread.stop()
            self.plc_thread.join()
        if self.plc_thread and self.plc_thread.db_connection:
            self.plc_thread.db_connection.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
