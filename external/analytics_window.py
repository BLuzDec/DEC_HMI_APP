"""
Analytics Window for DEC HMI Application.
Displays real-time statistical analysis with time-series tracking of metrics.
"""
import os
import sys
import numpy as np
import pyqtgraph as pg
from collections import deque
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QFrame, QPushButton, QScrollArea,
    QLineEdit, QGridLayout, QProxyStyle, QStyle, QApplication,
    QTabWidget, QCheckBox, QColorDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QPixmap, QPainter, QBrush, QColor, QFont, QIcon

from external.calculations import DataAnalyzer


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", relative_path)


class FastTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 250
        if hint == QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:
            return 5000
        return super().styleHint(hint, option, widget, returnData)


def _app_icon_analytics():
    """Load app icon for the analytics window (same as main window)."""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    dec_group = os.path.join(base, "Images", "Dec Group_bleu_noir_transparent.png")
    if os.path.isfile(dec_group):
        pix = QPixmap(dec_group)
        if not pix.isNull():
            icon = QIcon()
            for size in (16, 24, 32, 48):
                scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon.addPixmap(scaled)
            return icon
    return QIcon()


class _AnalyticsTitleBar(QWidget):
    """Custom dark title bar for the Analytics window (icon + title + window controls)."""

    def __init__(self, parent):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: #1e1e1e;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(0)

        # App icon
        icon_label = QLabel()
        icon_label.setFixedSize(18, 18)
        icon = _app_icon_analytics()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(16, 16))
        layout.addWidget(icon_label)
        layout.addSpacing(8)

        # Title
        title = QLabel("Graph Analytics")
        title.setStyleSheet("color: #cccccc; font-size: 12px; background: transparent;")
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(title)

        # Draggable spacer
        spacer = QLabel()
        spacer.setStyleSheet("background: transparent;")
        spacer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(spacer, 1)

        # Window control buttons
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

        btn_min = QPushButton("\uE921")
        btn_min.setStyleSheet(btn_style_normal)
        btn_min.clicked.connect(parent.showMinimized)

        self.btn_max = QPushButton("\uE922")
        self.btn_max.setStyleSheet(btn_style_normal)
        self.btn_max.clicked.connect(self._toggle_maximize)

        btn_close = QPushButton("\uE8BB")
        btn_close.setStyleSheet(btn_style_close)
        btn_close.clicked.connect(parent.close)

        layout.addWidget(btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(btn_close)

    def _toggle_maximize(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            self.btn_max.setText("\uE922")
        else:
            self._parent.showMaximized()
            self.btn_max.setText("\uE923")

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


class AnalyticsWindow(QWidget):
    """Analytics window with time-series tracking of metrics."""
    
    MAX_HISTORY = 500  # Max points to keep in history
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Graph Analytics')
        self.resize(1100, 700)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        
        icon = _app_icon_analytics()
        if not icon.isNull():
            self.setWindowIcon(icon)
        
        app = QApplication.instance()
        if app and not isinstance(app.style(), FastTooltipStyle):
            app.setStyle(FastTooltipStyle())
        
        self.graphs = []
        self.variable_metadata = {}
        self.setpoints = {}
        self.tolerances = {}
        self._user_set_setpoint = set()  # Track which vars have user-set setpoints
        
        # Line display settings
        self.show_setpoint_line = {}  # var_name -> bool
        self.show_tolerance_lines = {}  # var_name -> bool
        self.setpoint_colors = {}  # var_name -> color string
        self.tolerance_colors = {}  # var_name -> color string
        
        # History tracking for time-series plots
        self.metric_history = {}  # var_name -> {'rsd': deque, 'cp': deque, 'cpk': deque, 'cpm': deque, 'time': deque}
        self.history_counter = 0
        
        self._user_interacting = False
        self._interaction_timer = QTimer()
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.timeout.connect(self._end_interaction)
        
        self._variable_panels = {}
        self._last_data_hash = {}
        
        self._apply_theme()
        
        # Root layout: custom title bar on top, content below
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(1, 0, 1, 1)
        root_layout.setSpacing(0)

        self._title_bar = _AnalyticsTitleBar(self)
        root_layout.addWidget(self._title_bar)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        root_layout.addWidget(content, 1)
        # Resize grip in bottom-right corner
        from PySide6.QtWidgets import QSizeGrip
        _grip = QSizeGrip(self)
        _grip.setFixedSize(12, 12)
        _grip.setStyleSheet("QSizeGrip { background: transparent; }")
        _grip_row = QHBoxLayout()
        _grip_row.setContentsMargins(0, 0, 0, 0)
        _grip_row.addStretch()
        _grip_row.addWidget(_grip)
        root_layout.addLayout(_grip_row)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Graph Analytics")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        self.auto_refresh_btn = QPushButton("Auto-Refresh: ON")
        self.auto_refresh_btn.setCheckable(True)
        self.auto_refresh_btn.setChecked(True)
        self.auto_refresh_btn.setFixedHeight(26)
        self.auto_refresh_btn.setStyleSheet("""
            QPushButton { background-color: #1a6fa5; color: white; padding: 4px 10px; border-radius: 3px; font-size: 11px; }
            QPushButton:!checked { background-color: #555; }
        """)
        self.auto_refresh_btn.clicked.connect(self._toggle_auto_refresh)
        header_layout.addWidget(self.auto_refresh_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet("QPushButton { background-color: #6b4c4c; color: white; padding: 4px 10px; border-radius: 3px; font-size: 11px; }")
        clear_btn.clicked.connect(self._clear_history)
        header_layout.addWidget(clear_btn)
        
        main_layout.addLayout(header_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background-color: #1e1e1e; }")
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #1e1e1e;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(15)
        self.scroll.setWidget(self.content_widget)
        
        main_layout.addWidget(self.scroll)
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_analytics)
        self.refresh_timer.start(1000)  # Update every second for smoother graphs
        
        self.scroll.viewport().installEventFilter(self)
    
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.FocusIn):
            self._start_interaction()
        return super().eventFilter(obj, event)
    
    def _start_interaction(self):
        self._user_interacting = True
        self._interaction_timer.start(3000)
    
    def _end_interaction(self):
        self._user_interacting = False
    
    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QLineEdit { background-color: #333; color: white; border: 1px solid #555; border-radius: 3px; padding: 4px 8px; }
            QLineEdit:focus { border-color: #1a6fa5; }
            QTabWidget::pane { border: 1px solid #3e3e42; background-color: #252526; border-radius: 4px; }
            QTabBar::tab { background-color: #2d2d30; color: #aaa; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background-color: #3e3e42; color: #fff; }
        """)
    
    
    def _toggle_auto_refresh(self, checked):
        self.auto_refresh_btn.setText("Auto-Refresh: ON" if checked else "Auto-Refresh: OFF")
        self.refresh_timer.start(1000) if checked else self.refresh_timer.stop()
    
    def _clear_history(self):
        """Clear all metric history."""
        self.metric_history.clear()
        self.history_counter = 0
        self.update_analytics(force=True)
    
    def set_graphs(self, graphs, variable_metadata=None):
        self.graphs = graphs
        if variable_metadata:
            self.variable_metadata = variable_metadata
        
        for graph in graphs:
            if hasattr(graph, 'variable_metadata') and graph.variable_metadata:
                self.variable_metadata.update(graph.variable_metadata)
            for var in graph.variables:
                if var not in self.setpoints:
                    self.setpoints[var] = 0.0
                if var not in self.tolerances:
                    self.tolerances[var] = 1.0
                if var not in self.metric_history:
                    self.metric_history[var] = {
                        'rsd': deque(maxlen=self.MAX_HISTORY),
                        'cp': deque(maxlen=self.MAX_HISTORY),
                        'cpk': deque(maxlen=self.MAX_HISTORY),
                        'cpm': deque(maxlen=self.MAX_HISTORY),
                        'time': deque(maxlen=self.MAX_HISTORY)
                    }
        
        self._variable_panels.clear()
        self._last_data_hash.clear()
        self.update_analytics(force=True)
    
    def _get_display_name(self, var_name):
        meta = self.variable_metadata.get(var_name, {})
        return meta.get("name", "").strip() or var_name
    
    def _get_unit(self, var_name):
        return self.variable_metadata.get(var_name, {}).get("unit", "").strip()
    
    def _get_x_values_for_analytics(self, graph, n):
        """Get X values array of length n corresponding to buffered data points.
        
        Matches the X values used by the plot so that the axis range settings
        correctly map to the underlying data indices/values.
        """
        try:
            if getattr(graph, 'is_discrete_index', False):
                x_disc = list(getattr(graph, 'buffers_x_discrete', []))
                if x_disc and len(x_disc) >= n:
                    arr = np.array(x_disc[:n], dtype=float)
                    if not np.any(np.isnan(arr)):
                        return arr
                return np.arange(1, n + 1, dtype=float)
            elif getattr(graph, 'is_xy_plot', False):
                x_src = getattr(graph, 'x_axis_source', '')
                x_raw = list(graph.buffers_x.get(x_src, []))
                if x_raw and len(x_raw) >= n:
                    arr = np.array(x_raw[:n], dtype=float)
                    if not np.any(np.isnan(arr)):
                        return arr
                return np.arange(0, n, dtype=float)
        except (ValueError, TypeError):
            pass
        # Time (Index) or fallback: 0-based indices matching pyqtgraph default
        return np.arange(0, n, dtype=float)
    
    def _apply_filters(self, graph, var_name, y_array):
        """Apply X-axis range and tolerance filters to analytics data.
        
        1. X-axis filter: When X range is not 'auto', only include data points
           whose X value falls within [x_min, x_max].
        2. Tolerance filter: Only include data points within setpoint ± tolerance%.
        """
        if len(y_array) == 0:
            return y_array
        
        # --- X-axis range filter ---
        range_settings = getattr(graph, 'range_settings', {})
        x_settings = range_settings.get('x', {})
        if not x_settings.get('auto', True):
            n = len(y_array)
            x_array = self._get_x_values_for_analytics(graph, n)
            min_len = min(len(x_array), n)
            x_array = x_array[:min_len]
            y_array = y_array[:min_len]
            
            x_min = x_settings.get('min', -np.inf)
            x_max = x_settings.get('max', np.inf)
            x_mask = (x_array >= x_min) & (x_array <= x_max)
            y_array = y_array[x_mask]
        
        if len(y_array) == 0:
            return y_array
        
        # --- Tolerance filter (only if user explicitly set a setpoint) ---
        if var_name in self._user_set_setpoint:
            setpoint = self.setpoints.get(var_name, 0.0)
            tolerance = self.tolerances.get(var_name, 1.0)
            if setpoint != 0.0 and tolerance > 0:
                half_range = abs(setpoint) * tolerance / 100
                tol_min = setpoint - half_range
                tol_max = setpoint + half_range
                tol_mask = (y_array >= tol_min) & (y_array <= tol_max)
                y_array = y_array[tol_mask]
        
        return y_array
    
    def update_analytics(self, force=False):
        if not self.graphs or (self._user_interacting and not force):
            return
        # Rebuild if forced, no panels yet, or any panel was "waiting" and now has data
        needs_rebuild = force or not self._variable_panels
        if not needs_rebuild:
            for graph in self.graphs:
                for var_name in graph.variables:
                    refs = self._variable_panels.get(var_name)
                    if refs and 'waiting_label' in refs:
                        y_data = list(graph.buffers_y.get(var_name, []))
                        if y_data:
                            needs_rebuild = True
                            break
                if needs_rebuild:
                    break
        if needs_rebuild:
            self._rebuild_ui()
        else:
            self._update_values_only()
    
    def _rebuild_ui(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._variable_panels.clear()
        
        for idx, graph in enumerate(self.graphs):
            panel = self._create_graph_panel(graph, idx)
            if panel:
                self.content_layout.addWidget(panel)
        
        self.content_layout.addStretch()
    
    def _update_values_only(self):
        self.history_counter += 1
        
        for graph in self.graphs:
            for var_name in graph.variables:
                try:
                    if var_name not in self._variable_panels:
                        continue
                    
                    y_data = list(graph.buffers_y.get(var_name, []))
                    if not y_data:
                        continue
                    
                    # Include range/tolerance settings in hash so analytics update when they change
                    range_settings = getattr(graph, 'range_settings', {})
                    x_settings = range_settings.get('x', {})
                    data_hash = (len(y_data), round(y_data[-1], 10) if y_data else 0,
                                 x_settings.get('auto', True),
                                 round(x_settings.get('min', 0), 6), round(x_settings.get('max', 0), 6),
                                 round(self.setpoints.get(var_name, 0), 6),
                                 round(self.tolerances.get(var_name, 1.0), 6))
                    if self._last_data_hash.get(var_name) == data_hash:
                        continue
                    
                    y_array = np.array(y_data, dtype=float)
                    y_array = y_array[~(np.isnan(y_array) | np.isinf(y_array))]
                    
                    if len(y_array) == 0:
                        self._last_data_hash[var_name] = data_hash
                        continue
                    
                    # Apply X-axis range and tolerance filters
                    y_array = self._apply_filters(graph, var_name, y_array)
                    
                    if len(y_array) == 0:
                        self._last_data_hash[var_name] = data_hash
                        continue
                    
                    analyzer = DataAnalyzer(y_array.reshape(-1, 1), [var_name])
                    stats = analyzer.calculate_basic_stats(var_name)
                    dist_data = analyzer.calculate_frequency_distribution(var_name)
                    
                    setpoint = self.setpoints.get(var_name, stats['mean'])
                    tolerance = self.tolerances.get(var_name, 1.0)
                    capability = analyzer.calculate_process_capability(setpoint, tolerance, stats['std'], stats['mean'])
                    
                    # Add to history
                    history = self.metric_history.get(var_name)
                    if history:
                        history['time'].append(self.history_counter)
                        history['rsd'].append(stats['rsd'])
                        history['cp'].append(capability['cp'])
                        history['cpk'].append(capability['cpk'])
                        history['cpm'].append(capability['cpm'])
                    
                    panel_refs = self._variable_panels[var_name]
                    panel_refs['raw_data'] = y_array
                    panel_refs['stats'] = stats
                    panel_refs['capability'] = capability
                    
                    # Skip tab updates for "waiting" panels (they have no tabs yet)
                    if 'tabs' in panel_refs:
                        self._update_all_tabs(panel_refs, var_name, stats, dist_data, capability)
                    
                    # Only save hash AFTER successful update
                    self._last_data_hash[var_name] = data_hash
                except Exception as e:
                    # Log the error so it's visible in the terminal, then continue
                    import traceback
                    print(f"[Analytics] Update error for '{var_name}': {e}")
                    traceback.print_exc()
                    continue
    
    def _create_graph_panel(self, graph, graph_idx):
        if not graph.variables:
            return None
        
        panel = QFrame()
        panel.setStyleSheet("QFrame { background-color: #252526; border: 1px solid #3e3e42; border-radius: 6px; }")
        
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 12)
        panel_layout.setSpacing(10)
        
        display_names = [self._get_display_name(v) for v in graph.variables]
        title = graph.graph_title or " / ".join(display_names)
        header = QLabel(title)
        header.setStyleSheet("font-size: 13px; font-weight: bold; color: #e0e0e0; border: none;")
        panel_layout.addWidget(header)
        
        for var_name in graph.variables:
            var_section = self._create_variable_tabs(graph, var_name)
            if var_section:
                panel_layout.addWidget(var_section)
        
        return panel
    
    def _create_variable_tabs(self, graph, var_name):
        y_data = list(graph.buffers_y.get(var_name, []))
        
        display_name = self._get_display_name(var_name)
        unit = self._get_unit(var_name)
        
        # Parse raw data
        if y_data:
            y_array_raw = np.array(y_data, dtype=float)
            y_array_raw = y_array_raw[~(np.isnan(y_array_raw) | np.isinf(y_array_raw))]
        else:
            y_array_raw = np.array([], dtype=float)
        
        # Initialize setpoint from unfiltered data if needed
        if len(y_array_raw) > 0 and (var_name not in self.setpoints or self.setpoints[var_name] == 0.0):
            self.setpoints[var_name] = float(np.mean(y_array_raw))
        
        # Apply X-axis range and tolerance filters
        if len(y_array_raw) > 0:
            y_array = self._apply_filters(graph, var_name, y_array_raw.copy())
        else:
            y_array = y_array_raw
        
        has_data = len(y_array) > 0
        
        # Compute stats only if we have data
        if has_data:
            analyzer = DataAnalyzer(y_array.reshape(-1, 1), [var_name])
            stats = analyzer.calculate_basic_stats(var_name)
            dist_data = analyzer.calculate_frequency_distribution(var_name)
            
            setpoint = self.setpoints.get(var_name, stats['mean'])
            tolerance = self.tolerances.get(var_name, 1.0)
            capability = analyzer.calculate_process_capability(setpoint, tolerance, stats['std'], stats['mean'])
        else:
            stats = {'mean': 0, 'std': 0, 'rsd': 0, 'min': 0, 'max': 0, 'count': 0, 'range': 0, 'median': 0}
            dist_data = {'bins': [], 'counts': [], 'bin_centers': [], 'bin_width': 0}
            setpoint = self.setpoints.get(var_name, 0.0)
            tolerance = self.tolerances.get(var_name, 1.0)
            capability = {'cp': 0, 'cpk': 0, 'cpm': 0, 'cp_rating': 'N/A', 'cpk_rating': 'N/A', 'cpm_rating': 'N/A'}
        
        # Initialize history
        if var_name not in self.metric_history:
            self.metric_history[var_name] = {
                'rsd': deque(maxlen=self.MAX_HISTORY),
                'cp': deque(maxlen=self.MAX_HISTORY),
                'cpk': deque(maxlen=self.MAX_HISTORY),
                'cpm': deque(maxlen=self.MAX_HISTORY),
                'time': deque(maxlen=self.MAX_HISTORY)
            }
        
        # Add initial point (only if we have real data)
        if has_data:
            history = self.metric_history[var_name]
            self.history_counter += 1
            history['time'].append(self.history_counter)
            history['rsd'].append(stats['rsd'])
            history['cp'].append(capability['cp'])
            history['cpk'].append(capability['cpk'])
            history['cpm'].append(capability['cpm'])
        
        panel_refs = {
            'raw_data': y_array, 'stats': stats, 'capability': capability,
            'display_name': display_name, 'unit': unit, 'graph': graph,
            'has_data': has_data
        }
        
        container = QFrame()
        container.setStyleSheet("QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 4px; }")
        
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(10, 8, 10, 10)
        main_layout.setSpacing(8)
        
        # Variable title with settings
        header_layout = QHBoxLayout()
        unit_str = f" [{unit}]" if unit else ""
        var_title = QLabel(f"{display_name}{unit_str}")
        var_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #aaa; border: none;")
        header_layout.addWidget(var_title)
        header_layout.addStretch()
        
        # Setpoint
        sp_label = QLabel("Setpoint:")
        sp_label.setStyleSheet("color: #888; font-size: 10px; border: none;")
        sp_edit = QLineEdit(f"{setpoint:.4f}")
        sp_edit.setFixedWidth(90)
        sp_edit.setFixedHeight(22)
        sp_edit.editingFinished.connect(lambda e=sp_edit, v=var_name: self._on_setting_changed(e, 'setpoint', v))
        header_layout.addWidget(sp_label)
        header_layout.addWidget(sp_edit)
        panel_refs['setpoint_edit'] = sp_edit
        
        # Tolerance
        tol_label = QLabel("Tolerance:")
        tol_label.setStyleSheet("color: #888; font-size: 10px; border: none;")
        tol_edit = QLineEdit(f"{tolerance:.2f}%")
        tol_edit.setFixedWidth(70)
        tol_edit.setFixedHeight(22)
        tol_edit.editingFinished.connect(lambda e=tol_edit, v=var_name: self._on_setting_changed(e, 'tolerance', v))
        header_layout.addWidget(tol_label)
        header_layout.addWidget(tol_edit)
        panel_refs['tolerance_edit'] = tol_edit
        
        main_layout.addLayout(header_layout)
        
        # Initialize colors if not set
        if var_name not in self.setpoint_colors:
            self.setpoint_colors[var_name] = '#00ff00'  # Green default
        if var_name not in self.tolerance_colors:
            self.tolerance_colors[var_name] = '#ffaa00'  # Orange default
        if var_name not in self.show_setpoint_line:
            self.show_setpoint_line[var_name] = False
        if var_name not in self.show_tolerance_lines:
            self.show_tolerance_lines[var_name] = False
        
        # Checkboxes and color buttons for graph lines (on the right, same row as Setpoint/Tolerance)
        header_layout.addSpacing(20)
        
        # Setpoint line checkbox and color
        sp_check = QCheckBox("Show Setpoint")
        sp_check.setStyleSheet("color: #aaa; font-size: 10px;")
        sp_check.setChecked(self.show_setpoint_line.get(var_name, False))
        sp_check.stateChanged.connect(lambda state, v=var_name: self._on_line_toggle(v, 'setpoint', state))
        header_layout.addWidget(sp_check)
        panel_refs['sp_check'] = sp_check
        
        sp_color_btn = QPushButton()
        sp_color_btn.setFixedSize(22, 22)
        sp_color_btn.setStyleSheet(f"background-color: {self.setpoint_colors[var_name]}; border: 1px solid #555; border-radius: 3px;")
        sp_color_btn.setToolTip("Choose setpoint line color")
        sp_color_btn.clicked.connect(lambda _, v=var_name, btn=sp_color_btn: self._choose_line_color(v, 'setpoint', btn))
        header_layout.addWidget(sp_color_btn)
        panel_refs['sp_color_btn'] = sp_color_btn
        
        header_layout.addSpacing(15)
        
        # Tolerance lines checkbox and color
        tol_check = QCheckBox("Show Tolerance")
        tol_check.setStyleSheet("color: #aaa; font-size: 10px;")
        tol_check.setChecked(self.show_tolerance_lines.get(var_name, False))
        tol_check.stateChanged.connect(lambda state, v=var_name: self._on_line_toggle(v, 'tolerance', state))
        header_layout.addWidget(tol_check)
        panel_refs['tol_check'] = tol_check
        
        tol_color_btn = QPushButton()
        tol_color_btn.setFixedSize(22, 22)
        tol_color_btn.setStyleSheet(f"background-color: {self.tolerance_colors[var_name]}; border: 1px solid #555; border-radius: 3px;")
        tol_color_btn.setToolTip("Choose tolerance lines color")
        tol_color_btn.clicked.connect(lambda _, v=var_name, btn=tol_color_btn: self._choose_line_color(v, 'tolerance', btn))
        header_layout.addWidget(tol_color_btn)
        panel_refs['tol_color_btn'] = tol_color_btn
        
        # Tab widget (or waiting message if no data yet)
        if not has_data:
            waiting_label = QLabel("Waiting for data...")
            waiting_label.setStyleSheet("color: #888; font-size: 12px; padding: 20px; border: none;")
            waiting_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(waiting_label)
            panel_refs['waiting_label'] = waiting_label
        else:
            tabs = QTabWidget()
            tabs.setStyleSheet("""
                QTabWidget::pane { border: 1px solid #3e3e42; background-color: #1e1e1e; }
                QTabBar::tab { background-color: #2d2d30; color: #999; padding: 6px 12px; font-size: 10px; }
                QTabBar::tab:selected { background-color: #1e1e1e; color: #fff; }
            """)
            
            tab1 = self._create_distribution_tab(var_name, stats, dist_data, capability, panel_refs)
            tab2 = self._create_metric_trend_tab(var_name, 'rsd', '%RSD', '%', panel_refs)
            tab3 = self._create_metric_trend_tab(var_name, 'cp', 'Cp', '', panel_refs)
            tab4 = self._create_metric_trend_tab(var_name, 'cpk', 'Cpk', '', panel_refs)
            tab5 = self._create_metric_trend_tab(var_name, 'cpm', 'Cpm', '', panel_refs)
            
            tabs.addTab(tab1, "Distribution")
            tabs.addTab(tab2, "%RSD Trend")
            tabs.addTab(tab3, "Cp Trend")
            tabs.addTab(tab4, "Cpk Trend")
            tabs.addTab(tab5, "Cpm Trend")
            
            panel_refs['tabs'] = tabs
            main_layout.addWidget(tabs)
        
        self._variable_panels[var_name] = panel_refs
        self._last_data_hash[var_name] = (len(y_data), y_data[-1] if y_data else 0)
        
        return container
    
    def _create_distribution_tab(self, var_name, stats, dist_data, capability, panel_refs):
        """Distribution tab with histogram, stats with tooltips, and RSD indicator."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Left: Histogram
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground('#1e1e1e')
        plot_widget.showGrid(x=True, y=True, alpha=0.15)
        plot_widget.setLabel('left', 'Frequency', color='#888', size='9pt')
        plot_widget.setLabel('bottom', panel_refs['display_name'], color='#888', size='9pt')
        self._draw_histogram(plot_widget, dist_data)
        panel_refs['hist_plot'] = plot_widget
        layout.addWidget(plot_widget, stretch=3)
        
        # Middle: Frequency table
        freq_table = self._create_freq_table(dist_data)
        panel_refs['freq_table'] = freq_table
        layout.addWidget(freq_table, stretch=2)
        
        # Right: Stats + RSD indicator
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Stats with tooltips (RSD is integrated as the first row)
        stats_widget = self._create_stats_with_tooltips(var_name, stats, capability, panel_refs)
        right_layout.addWidget(stats_widget)
        
        right_layout.addStretch()
        layout.addWidget(right_widget, stretch=2)
        
        return tab
    
    def _create_metric_trend_tab(self, var_name, metric_key, metric_name, unit_suffix, panel_refs):
        """Create a trend tab showing metric over time."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Left: Time-series plot
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground('#1e1e1e')
        plot_widget.showGrid(x=True, y=True, alpha=0.2)
        plot_widget.setLabel('left', f'{metric_name}{unit_suffix}', color='#aaa', size='10pt')
        plot_widget.setLabel('bottom', 'Sample #', color='#aaa', size='10pt')
        plot_widget.getAxis('left').setPen('#555')
        plot_widget.getAxis('bottom').setPen('#555')
        
        # Add threshold lines for capability metrics
        if metric_key in ['cp', 'cpk', 'cpm']:
            # Add threshold lines
            line_excellent = pg.InfiniteLine(pos=1.67, angle=0, pen=pg.mkPen('#6bcf6b', width=1, style=Qt.PenStyle.DashLine))
            line_capable = pg.InfiniteLine(pos=1.33, angle=0, pen=pg.mkPen('#8bc34a', width=1, style=Qt.PenStyle.DashLine))
            line_marginal = pg.InfiniteLine(pos=1.0, angle=0, pen=pg.mkPen('#ffc107', width=1, style=Qt.PenStyle.DashLine))
            plot_widget.addItem(line_excellent)
            plot_widget.addItem(line_capable)
            plot_widget.addItem(line_marginal)
        elif metric_key == 'rsd':
            line_5 = pg.InfiniteLine(pos=5, angle=0, pen=pg.mkPen('#6bcf6b', width=1, style=Qt.PenStyle.DashLine))
            line_10 = pg.InfiniteLine(pos=10, angle=0, pen=pg.mkPen('#ffc107', width=1, style=Qt.PenStyle.DashLine))
            plot_widget.addItem(line_5)
            plot_widget.addItem(line_10)
        
        # Create curve
        curve = plot_widget.plot([], [], pen=pg.mkPen('#00b4d8', width=2), symbol='o', symbolSize=4, symbolBrush='#00b4d8')
        panel_refs[f'{metric_key}_plot'] = plot_widget
        panel_refs[f'{metric_key}_curve'] = curve
        
        # Add crosshair for hover value display
        vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#ff6b6b', width=1, style=Qt.PenStyle.DashLine))
        hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#ff6b6b', width=1, style=Qt.PenStyle.DashLine))
        vLine.setVisible(False)
        hLine.setVisible(False)
        plot_widget.addItem(vLine, ignoreBounds=True)
        plot_widget.addItem(hLine, ignoreBounds=True)
        
        # Value label for hover
        value_label = pg.TextItem(text="", color='#fff', anchor=(0, 1))
        value_label.setFont(pg.QtGui.QFont('Arial', 10, pg.QtGui.QFont.Weight.Bold))
        value_label.setVisible(False)
        plot_widget.addItem(value_label, ignoreBounds=True)
        
        # Store references for crosshair
        panel_refs[f'{metric_key}_vline'] = vLine
        panel_refs[f'{metric_key}_hline'] = hLine
        panel_refs[f'{metric_key}_value_label'] = value_label
        
        # Mouse move handler
        def mouse_moved(evt):
            pos = evt[0]
            if plot_widget.sceneBoundingRect().contains(pos):
                mouse_point = plot_widget.getPlotItem().vb.mapSceneToView(pos)
                x, y = mouse_point.x(), mouse_point.y()
                
                # Find closest data point
                history = self.metric_history.get(var_name, {})
                if history and len(history.get('time', [])) > 0 and len(history.get(metric_key, [])) > 0:
                    times = list(history['time'])
                    values = list(history[metric_key])
                    n = min(len(times), len(values))
                    times, values = times[:n], values[:n]
                    
                    # Find nearest x index
                    if n > 0:
                        idx = min(range(n), key=lambda i: abs(times[i] - x))
                        snap_x = times[idx]
                        snap_y = values[idx]
                        
                        vLine.setPos(snap_x)
                        hLine.setPos(snap_y)
                        vLine.setVisible(True)
                        hLine.setVisible(True)
                        
                        value_label.setText(f"Sample: {int(snap_x)}\n{metric_name}: {snap_y:.4f}{unit_suffix}")
                        value_label.setPos(snap_x, snap_y)
                        value_label.setVisible(True)
            else:
                vLine.setVisible(False)
                hLine.setVisible(False)
                value_label.setVisible(False)
        
        # Connect mouse move signal
        proxy = pg.SignalProxy(plot_widget.scene().sigMouseMoved, rateLimit=60, slot=mouse_moved)
        panel_refs[f'{metric_key}_proxy'] = proxy  # Keep reference to prevent garbage collection
        
        # Draw initial data (truncate to min length to prevent shape mismatch)
        history = self.metric_history.get(var_name, {})
        if history and len(history.get('time', [])) > 0 and len(history.get(metric_key, [])) > 0:
            times = list(history['time'])
            values = list(history[metric_key])
            n = min(len(times), len(values))
            curve.setData(times[:n], values[:n])
        
        layout.addWidget(plot_widget, stretch=3)
        
        # Right: Current value and info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(10)
        
        # Current value big display
        current_val = history[metric_key][-1] if history and len(history[metric_key]) > 0 else 0
        
        if metric_key == 'rsd':
            color, rating = self._get_rsd_color_rating(current_val)
        else:
            color = "#6bcf6b" if current_val >= 1.67 else "#8bc34a" if current_val >= 1.33 else "#ffc107" if current_val >= 1.0 else "#ff6b6b"
            rating = "Excellent" if current_val >= 1.67 else "Capable" if current_val >= 1.33 else "Marginal" if current_val >= 1.0 else "Not Capable"
        
        title_lbl = QLabel(f"Current {metric_name}")
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #aaa; border: none;")
        info_layout.addWidget(title_lbl)
        
        val_display = QLabel(f"{current_val:.3f}{unit_suffix}")
        val_display.setStyleSheet(f"font-size: 36px; font-weight: bold; color: {color}; border: none;")
        val_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(val_display)
        panel_refs[f'{metric_key}_current'] = val_display
        
        rating_lbl = QLabel(rating)
        rating_lbl.setStyleSheet(f"font-size: 14px; color: {color}; border: none;")
        rating_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(rating_lbl)
        panel_refs[f'{metric_key}_rating_lbl'] = rating_lbl
        
        # Statistics of the metric
        info_layout.addSpacing(15)
        
        if history and len(history[metric_key]) > 1:
            vals = list(history[metric_key])
            stats_text = f"Min: {min(vals):.3f}\nMax: {max(vals):.3f}\nAvg: {np.mean(vals):.3f}\nSamples: {len(vals)}"
        else:
            stats_text = "Collecting data..."
        
        metric_stats = QLabel(stats_text)
        metric_stats.setStyleSheet("font-size: 10px; color: #888; border: none; background-color: #252526; padding: 8px; border-radius: 4px;")
        info_layout.addWidget(metric_stats)
        panel_refs[f'{metric_key}_stats'] = metric_stats
        
        # Formula
        formulas = {
            'rsd': '%RSD = (σ / µ) × 100',
            'cp': 'Cp = (USL - LSL) / 6σ',
            'cpk': 'Cpk = min((USL-µ)/3σ, (µ-LSL)/3σ)',
            'cpm': 'Cpm = Cp / √(1 + 9·(Cp-Cpk)²)'
        }
        formula_lbl = QLabel(formulas[metric_key])
        formula_lbl.setStyleSheet("font-size: 9px; color: #666; font-family: monospace; border: none;")
        info_layout.addWidget(formula_lbl)
        
        # Threshold guide
        if metric_key == 'rsd':
            guide = "< 0.5%: Excellent\n< 1%: Very Good\n< 2.5%: Medium\n< 5%: Poor\n≥ 5%: High Variability"
        else:
            guide = "≥ 1.67: Excellent\n≥ 1.33: Capable\n≥ 1.00: Marginal\n< 1.00: Not Capable"
        guide_lbl = QLabel(guide)
        guide_lbl.setStyleSheet("font-size: 9px; color: #666; border: none;")
        info_layout.addWidget(guide_lbl)
        
        info_layout.addStretch()
        layout.addWidget(info_widget, stretch=1)
        
        return tab
    
    def _create_stats_with_tooltips(self, var_name, stats, capability, panel_refs):
        """Create statistics widget with detailed tooltips. RSD is shown as the first row."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(2)
        
        setpoint = self.setpoints.get(var_name, stats['mean'])
        tolerance = self.tolerances.get(var_name, 1.0)
        tol_min = setpoint * (1 - tolerance / 100)
        tol_max = setpoint * (1 + tolerance / 100)
        unit = self._get_unit(var_name)
        display_name = self._get_display_name(var_name)
        unit_str = f" {unit}" if unit else ""
        
        def add_row(name, value, tooltip, key, color="#e0e0e0", bold=False):
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(name)
            lbl.setStyleSheet("color: #888; font-size: 10px; border: none;")
            lbl.setToolTip(tooltip)
            lbl.setCursor(Qt.CursorShape.WhatsThisCursor)
            lbl.setFixedWidth(55)
            row.addWidget(lbl)
            weight = "bold" if bold else "normal"
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: {weight}; border: none;")
            val.setToolTip(tooltip)
            row.addWidget(val)
            row.addStretch()
            layout.addLayout(row)
            panel_refs[f'stat_{key}'] = val
            panel_refs[f'stat_{key}_lbl'] = lbl
            panel_refs[f'stat_{key}_tip'] = tooltip
        
        # Build detailed tooltips with consistent symbol explanations
        count_tip = (
            f"━━━ COUNT (n) ━━━\n\n"
            f"Symbol: n = sample size\n\n"
            f"Definition: Total number of valid data points\n"
            f"in the current sample set.\n\n"
            f"Current Value: n = {stats['count']} samples\n\n"
            f"Note: NaN and Inf values are excluded."
        )
        
        mean_tip = (
            f"━━━ MEAN (µ) - Average ━━━\n\n"
            f"Symbol: µ (mu) = arithmetic mean\n\n"
            f"Definition: The arithmetic average of all values.\n"
            f"Represents the central tendency of your data.\n\n"
            f"WHY IT'S USED:\n"
            f"  • Shows where your process is centered\n"
            f"  • Indicates if the process is on target\n"
            f"  • Detects systematic bias or drift\n"
            f"  • Essential for process control decisions\n\n"
            f"WHAT IT SHOWS:\n"
            f"  • Process centering relative to setpoint\n"
            f"  • If mean ≠ setpoint → process is off-center\n"
            f"  • Trend in mean → process drift over time\n\n"
            f"Formula: µ = Σ(xᵢ) / n\n"
            f"  where: Σ = sum, xᵢ = each value, n = count\n\n"
            f"Current Value: µ = {stats['mean']:.6f}{unit_str}\n\n"
            f"Context:\n"
            f"  • Setpoint (Target): {setpoint:.4f}{unit_str}\n"
            f"  • Deviation from target: {abs(stats['mean'] - setpoint):.4f}{unit_str}\n"
            f"  • Process centered: {'Yes ✓' if abs(stats['mean'] - setpoint) < stats['std'] else 'No - Review needed'}"
        )
        
        std_tip = (
            f"━━━ STANDARD DEVIATION (σ) ━━━\n\n"
            f"Symbol: σ (sigma) = standard deviation\n\n"
            f"Definition: Measures the spread/dispersion\n"
            f"of values around the mean (µ).\n\n"
            f"WHY IT'S USED:\n"
            f"  • Quantifies process consistency/repeatability\n"
            f"  • Lower σ = more consistent process\n"
            f"  • Higher σ = more variation (less predictable)\n"
            f"  • Used to calculate process capability (Cp, Cpk)\n"
            f"  • Critical for quality control limits\n\n"
            f"WHAT IT SHOWS:\n"
            f"  • Process stability and predictability\n"
            f"  • If σ is large → inconsistent dosing/filling\n"
            f"  • If σ increases over time → equipment issue\n"
            f"  • Basis for setting control limits (±3σ)\n\n"
            f"Formula: σ = √(Σ(xᵢ - µ)² / n)\n"
            f"  where: µ = mean, xᵢ = each value, n = count\n\n"
            f"Current Value: σ = {stats['std']:.6f}{unit_str}\n\n"
            f"Data Distribution (normal distribution rule):\n"
            f"  • 68% within µ ± 1σ: [{stats['mean']-stats['std']:.4f}, {stats['mean']+stats['std']:.4f}]\n"
            f"  • 95% within µ ± 2σ: [{stats['mean']-2*stats['std']:.4f}, {stats['mean']+2*stats['std']:.4f}]\n"
            f"  • 99.7% within µ ± 3σ: [{stats['mean']-3*stats['std']:.4f}, {stats['mean']+3*stats['std']:.4f}]"
        )
        
        rsd_color, rsd_rating = self._get_rsd_color_rating(stats['rsd'])
        rsd_tip = (
            f"━━━ %RSD - Relative Standard Deviation ━━━\n\n"
            f"Also called: CV (Coefficient of Variation)\n\n"
            f"Definition: Expresses variability as a percentage\n"
            f"of the mean, allowing comparison across different\n"
            f"scales and units.\n\n"
            f"WHY IT'S USED:\n"
            f"  • Compare variability across different products\n"
            f"  • Unit-independent measure of precision\n"
            f"  • Industry standard for dosing/filling accuracy\n"
            f"  • Shows relative consistency regardless of scale\n"
            f"  • e.g., 1% RSD on 100g = 1g variation\n"
            f"        1% RSD on 1000g = 10g variation\n\n"
            f"WHAT IT SHOWS:\n"
            f"  • Process repeatability as a percentage\n"
            f"  • Lower %RSD = more precise/repeatable process\n"
            f"  • Higher %RSD = investigate equipment/material\n"
            f"  • Useful for batch-to-batch comparison\n\n"
            f"Formula: %RSD = (σ / µ) × 100\n"
            f"  where: σ = std deviation, µ = mean\n\n"
            f"Current Calculation:\n"
            f"  %RSD = ({stats['std']:.4f} / {stats['mean']:.4f}) × 100\n"
            f"  %RSD = {stats['rsd']:.2f}%\n"
            f"  Rating: {rsd_rating}\n\n"
            f"Rating Guide:\n"
            f"  • < 0.5%: Excellent - Highly precise\n"
            f"  • < 1%: Very Good - Good precision\n"
            f"  • < 2.5%: Medium - Acceptable\n"
            f"  • < 5%: Poor - Needs improvement\n"
            f"  • ≥ 5%: High Variability - Action required"
        )
        
        min_tip = (
            f"━━━ MINIMUM ━━━\n\n"
            f"Definition: Lowest value in the dataset.\n\n"
            f"Current Value: {stats['min']:.6f}{unit_str}\n\n"
            f"Context:\n"
            f"  • Distance from µ (mean): {abs(stats['min'] - stats['mean']):.4f}\n"
            f"  • LSL (Lower Spec Limit): {tol_min:.4f}\n"
            f"  • Within spec: {'Yes ✓' if stats['min'] >= tol_min else 'No ✗'}"
        )
        
        max_tip = (
            f"━━━ MAXIMUM ━━━\n\n"
            f"Definition: Highest value in the dataset.\n\n"
            f"Current Value: {stats['max']:.6f}{unit_str}\n\n"
            f"Context:\n"
            f"  • Distance from µ (mean): {abs(stats['max'] - stats['mean']):.4f}\n"
            f"  • USL (Upper Spec Limit): {tol_max:.4f}\n"
            f"  • Within spec: {'Yes ✓' if stats['max'] <= tol_max else 'No ✗'}\n\n"
            f"Range (Max - Min): {stats['max'] - stats['min']:.4f}{unit_str}"
        )
        
        # RSD as first row (colored by rating)
        rsd_color, rsd_rating = self._get_rsd_color_rating(stats['rsd'])
        add_row("%RSD:", f"{stats['rsd']:.2f}%  {rsd_rating}", rsd_tip, 'rsd', color=rsd_color, bold=True)
        panel_refs['rsd_display'] = panel_refs['stat_rsd']
        panel_refs['rsd_rating_text'] = rsd_rating

        add_row("Count:", str(stats['count']), count_tip, 'count')
        add_row("Mean:", f"{stats['mean']:.4f}", mean_tip, 'mean')
        add_row("Std Dev:", f"{stats['std']:.4f}", std_tip, 'std')
        add_row("Min:", f"{stats['min']:.4f}", min_tip, 'min')
        add_row("Max:", f"{stats['max']:.4f}", max_tip, 'max')
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3e3e42; border: none;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        
        # Capability metrics with detailed tooltips
        cp_tip = (
            f"━━━ Cp (Process Capability) ━━━\n\n"
            f"Symbols used:\n"
            f"  USL = Upper Specification Limit\n"
            f"  LSL = Lower Specification Limit\n"
            f"  σ (sigma) = standard deviation\n\n"
            f"Definition: Measures potential process capability\n"
            f"if the process were perfectly centered.\n\n"
            f"Formula: Cp = (USL - LSL) / 6σ\n\n"
            f"Current Calculation:\n"
            f"  USL = {tol_max:.4f}\n"
            f"  LSL = {tol_min:.4f}\n"
            f"  σ (Std Dev) = {stats['std']:.4f}\n"
            f"  Cp = ({tol_max:.4f} - {tol_min:.4f}) / (6 × {stats['std']:.4f})\n"
            f"  Cp = {capability['cp']:.4f}\n\n"
            f"Rating: {capability['cp_rating']}\n\n"
            f"Guide:\n"
            f"  • ≥ 1.67: Excellent\n"
            f"  • ≥ 1.33: Capable\n"
            f"  • ≥ 1.00: Marginal\n"
            f"  • < 1.00: Not Capable"
        )
        
        cpk_tip = (
            f"━━━ Cpk (Process Capability Index) ━━━\n\n"
            f"Symbols used:\n"
            f"  USL = Upper Specification Limit\n"
            f"  LSL = Lower Specification Limit\n"
            f"  µ (mu) = mean\n"
            f"  σ (sigma) = standard deviation\n"
            f"  CPU = Upper capability index\n"
            f"  CPL = Lower capability index\n\n"
            f"Definition: Measures actual process capability\n"
            f"accounting for process centering.\n\n"
            f"Formulas:\n"
            f"  CPU = (USL - µ) / 3σ\n"
            f"  CPL = (µ - LSL) / 3σ\n"
            f"  Cpk = min(CPU, CPL)\n\n"
            f"Current Calculation:\n"
            f"  USL = {tol_max:.4f}, LSL = {tol_min:.4f}\n"
            f"  µ (Mean) = {stats['mean']:.4f}, σ (Std Dev) = {stats['std']:.4f}\n\n"
            f"  CPU = (USL - µ) / 3σ\n"
            f"      = ({tol_max:.4f} - {stats['mean']:.4f}) / (3 × {stats['std']:.4f})\n"
            f"      = {capability.get('cpu', 0):.4f}\n\n"
            f"  CPL = (µ - LSL) / 3σ\n"
            f"      = ({stats['mean']:.4f} - {tol_min:.4f}) / (3 × {stats['std']:.4f})\n"
            f"      = {capability.get('cpl', 0):.4f}\n\n"
            f"  Cpk = min(CPU, CPL) = min({capability.get('cpu', 0):.4f}, {capability.get('cpl', 0):.4f})\n"
            f"      = {capability['cpk']:.4f}\n\n"
            f"Rating: {capability['cpk_rating']}\n\n"
            f"Note: Cpk ≤ Cp always. If Cpk << Cp,\n"
            f"the process is off-center from the target."
        )
        
        cpm_tip = (
            f"━━━ Cpm (Taguchi Capability Index) ━━━\n\n"
            f"Symbols used:\n"
            f"  Cp = Process Capability\n"
            f"  µ (mu) = mean\n"
            f"  σ (sigma) = standard deviation\n"
            f"  T = Target (setpoint)\n\n"
            f"Definition: Machine capability index that\n"
            f"penalizes deviation from target.\n\n"
            f"Formula: Cpm = Cp / √(1 + ((µ - T) / σ)²)\n\n"
            f"Current Calculation:\n"
            f"  Cp = {capability['cp']:.4f}\n"
            f"  µ (Mean) = {stats['mean']:.4f}\n"
            f"  T (Target) = {setpoint:.4f}\n"
            f"  σ (Std Dev) = {stats['std']:.4f}\n\n"
            f"  Deviation (µ - T) = {stats['mean'] - setpoint:.4f}\n"
            f"  Cpm = {capability['cpm']:.4f}\n\n"
            f"Rating: {capability['cpm_rating']}\n\n"
            f"Interpretation:\n"
            f"  Cpm accounts for both spread (σ) and centering.\n"
            f"  If Cpm < Cp, the process is off-target."
        )
        
        def get_cap_color(val):
            if val >= 1.67: return "#6bcf6b"
            elif val >= 1.33: return "#8bc34a"
            elif val >= 1.0: return "#ffc107"
            else: return "#ff6b6b"
        
        for metric, tip in [('cp', cp_tip), ('cpk', cpk_tip), ('cpm', cpm_tip)]:
            add_row(f"{metric.upper()}:", f"{capability[metric]:.3f}", tip, metric, 
                   color=get_cap_color(capability[metric]), bold=True)
        
        return widget
    
    def _create_freq_table(self, dist_data):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Range', 'N', '%'])
        table.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: #3e3e42; color: #ccc; padding: 3px; border: none; font-size: 9px; }")
        table.setStyleSheet("QTableWidget { background-color: #252526; gridline-color: #3e3e42; border: none; font-size: 9px; }")
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 35)
        table.setColumnWidth(2, 40)
        table.verticalHeader().setVisible(False)
        table.setMaximumWidth(200)
        self._populate_freq_table(table, dist_data)
        return table
    
    def _populate_freq_table(self, table, dist_data):
        num_rows = len(dist_data['intervals'])
        table.setRowCount(num_rows)
        max_freq = max(dist_data['frequencies']) if num_rows > 0 else 0
        min_freq = min(dist_data['frequencies']) if num_rows > 0 else 0
        
        for row in range(num_rows):
            bin_start, bin_end = dist_data['bin_edges'][row], dist_data['bin_edges'][row + 1]
            freq = dist_data['frequencies'][row]
            ratio = (freq - min_freq) / (max_freq - min_freq) if max_freq != min_freq else 0
            color = QColor(self._get_color_for_ratio(ratio))
            
            for col, text in enumerate([f"{bin_start:.2f}-{bin_end:.2f}", str(int(freq)), f"{dist_data['rel_frequencies'][row]:.1f}"]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(color)
                item.setForeground(QBrush(QColor('#1a1a1a')))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)
    
    def _draw_histogram(self, plot_widget, dist_data):
        plot_widget.clear()
        if len(dist_data['bin_edges']) > 1:
            bin_width = dist_data['bin_edges'][1] - dist_data['bin_edges'][0]
            x_data = dist_data['bin_edges'][:-1] + bin_width / 2
            y_hist = dist_data['frequencies']
            max_freq, min_freq = max(y_hist) if len(y_hist) > 0 else 1, min(y_hist) if len(y_hist) > 0 else 0
            
            for x, y in zip(x_data, y_hist):
                ratio = (y - min_freq) / (max_freq - min_freq) if max_freq != min_freq else 0
                bar = pg.BarGraphItem(x=[x], height=[y], width=bin_width * 0.85,
                                      brush=pg.mkBrush(self._get_color_for_ratio(ratio)),
                                      pen=pg.mkPen('#1e1e1e', width=1))
                plot_widget.addItem(bar)
    
    def _update_all_tabs(self, panel_refs, var_name, stats, dist_data, capability):
        """Update all tabs with new data."""
        setpoint = self.setpoints.get(var_name, stats['mean'])
        tolerance = self.tolerances.get(var_name, 1.0)
        
        # Update distribution tab
        if 'hist_plot' in panel_refs:
            self._draw_histogram(panel_refs['hist_plot'], dist_data)
            # Re-add setpoint/tolerance lines after histogram redraw
            self._update_main_graph_lines(var_name)
        if 'freq_table' in panel_refs:
            self._populate_freq_table(panel_refs['freq_table'], dist_data)
        
        # Update RSD indicator (compact)
        rsd_val = stats['rsd']
        rsd_color, rsd_rating = self._get_rsd_color_rating(rsd_val)
        
        # Build updated RSD tooltip
        rsd_tooltip = (
            f"━━━ %RSD (CV) ━━━\n\n"
            f"Relative Standard Deviation\n"
            f"Also called Coefficient of Variation\n\n"
            f"Formula: %RSD = (σ / µ) × 100\n\n"
            f"Current: {rsd_val:.2f}%\n"
            f"Rating: {rsd_rating}\n\n"
            f"Rating Guide:\n"
            f"  • < 0.5%: Excellent\n"
            f"  • < 1%: Very Good\n"
            f"  • < 2.5%: Medium\n"
            f"  • < 5%: Poor\n"
            f"  • ≥ 5%: High Variability"
        )
        
        if 'rsd_display' in panel_refs:
            panel_refs['rsd_display'].setText(f"{rsd_val:.2f}%  {rsd_rating}")
            panel_refs['rsd_display'].setStyleSheet(f"font-size: 10px; font-weight: bold; color: {rsd_color}; border: none;")
            panel_refs['rsd_display'].setToolTip(rsd_tooltip)
        
        # Update stats tooltips
        self._update_stats_tooltips(panel_refs, stats, capability, var_name)
        
        # Update trend plots
        history = self.metric_history.get(var_name, {})
        
        for metric_key in ['rsd', 'cp', 'cpk', 'cpm']:
            if f'{metric_key}_curve' in panel_refs and history:
                times = list(history.get('time', []))
                values = list(history.get(metric_key, []))
                n = min(len(times), len(values))
                if n > 0:
                    panel_refs[f'{metric_key}_curve'].setData(times[:n], values[:n])
            
            # Update current value display
            if f'{metric_key}_current' in panel_refs:
                current_val = history[metric_key][-1] if history and len(history[metric_key]) > 0 else 0
                unit_suffix = '%' if metric_key == 'rsd' else ''
                
                if metric_key == 'rsd':
                    color = "#6bcf6b" if current_val < 5 else "#ffc107" if current_val < 10 else "#ff6b6b"
                    rating = "Excellent" if current_val < 5 else "Good" if current_val < 10 else "High Variability"
                else:
                    color = "#6bcf6b" if current_val >= 1.67 else "#8bc34a" if current_val >= 1.33 else "#ffc107" if current_val >= 1.0 else "#ff6b6b"
                    rating = "Excellent" if current_val >= 1.67 else "Capable" if current_val >= 1.33 else "Marginal" if current_val >= 1.0 else "Not Capable"
                
                panel_refs[f'{metric_key}_current'].setText(f"{current_val:.3f}{unit_suffix}")
                panel_refs[f'{metric_key}_current'].setStyleSheet(f"font-size: 36px; font-weight: bold; color: {color}; border: none;")
                
                if f'{metric_key}_rating_lbl' in panel_refs:
                    panel_refs[f'{metric_key}_rating_lbl'].setText(rating)
                    panel_refs[f'{metric_key}_rating_lbl'].setStyleSheet(f"font-size: 14px; color: {color}; border: none;")
            
            # Update metric stats
            if f'{metric_key}_stats' in panel_refs and history and len(history[metric_key]) > 1:
                vals = list(history[metric_key])
                stats_text = f"Min: {min(vals):.3f}\nMax: {max(vals):.3f}\nAvg: {np.mean(vals):.3f}\nSamples: {len(vals)}"
                panel_refs[f'{metric_key}_stats'].setText(stats_text)
    
    def _update_stats_tooltips(self, panel_refs, stats, capability, var_name=None):
        """Update statistics values and tooltips with fresh data."""
        setpoint = self.setpoints.get(var_name, stats['mean']) if var_name else stats['mean']
        tolerance = self.tolerances.get(var_name, 1.0) if var_name else 1.0
        tol_min = setpoint * (1 - tolerance / 100)
        tol_max = setpoint * (1 + tolerance / 100)
        unit = self._get_unit(var_name) if var_name else ""
        unit_str = f" {unit}" if unit else ""
        
        # Update values
        for key, val in [('count', stats['count']), ('mean', stats['mean']), ('std', stats['std']), ('min', stats['min']), ('max', stats['max'])]:
            if f'stat_{key}' in panel_refs:
                panel_refs[f'stat_{key}'].setText(str(val) if key == 'count' else f"{val:.4f}")
        
        # Build and update detailed tooltips with symbol explanations
        tooltips = {
            'count': (
                f"━━━ COUNT (n) ━━━\n\n"
                f"Symbol: n = sample size\n\n"
                f"Current: n = {stats['count']} samples"
            ),
            'mean': (
                f"━━━ MEAN (µ) - Average ━━━\n\n"
                f"Symbol: µ (mu) = arithmetic mean\n\n"
                f"WHY IT'S USED:\n"
                f"  • Shows process centering\n"
                f"  • Detects bias or drift\n\n"
                f"WHAT IT SHOWS:\n"
                f"  • If mean ≠ setpoint → off-center\n\n"
                f"Formula: µ = Σ(xᵢ) / n\n\n"
                f"Current: µ = {stats['mean']:.6f}{unit_str}\n"
                f"Deviation from target: {abs(stats['mean'] - setpoint):.4f}{unit_str}"
            ),
            'std': (
                f"━━━ STANDARD DEVIATION (σ) ━━━\n\n"
                f"Symbol: σ (sigma) = standard deviation\n\n"
                f"WHY IT'S USED:\n"
                f"  • Quantifies process consistency\n"
                f"  • Lower σ = more repeatable\n\n"
                f"WHAT IT SHOWS:\n"
                f"  • If σ is large → inconsistent process\n"
                f"  • If σ increases → equipment issue\n\n"
                f"Formula: σ = √(Σ(xᵢ - µ)² / n)\n\n"
                f"Current: σ = {stats['std']:.6f}{unit_str}\n\n"
                f"68% within µ±1σ: [{stats['mean']-stats['std']:.4f}, {stats['mean']+stats['std']:.4f}]\n"
                f"95% within µ±2σ: [{stats['mean']-2*stats['std']:.4f}, {stats['mean']+2*stats['std']:.4f}]"
            ),
            'min': (
                f"━━━ MINIMUM ━━━\n\n"
                f"Current: {stats['min']:.6f}{unit_str}\n\n"
                f"LSL (Lower Spec Limit): {tol_min:.4f}\n"
                f"Within spec: {'Yes ✓' if stats['min'] >= tol_min else 'No ✗'}"
            ),
            'max': (
                f"━━━ MAXIMUM ━━━\n\n"
                f"Current: {stats['max']:.6f}{unit_str}\n\n"
                f"USL (Upper Spec Limit): {tol_max:.4f}\n"
                f"Within spec: {'Yes ✓' if stats['max'] <= tol_max else 'No ✗'}\n\n"
                f"Range: {stats['max'] - stats['min']:.4f}{unit_str}"
            )
        }
        
        for key, tip in tooltips.items():
            if f'stat_{key}' in panel_refs:
                panel_refs[f'stat_{key}'].setToolTip(tip)
            if f'stat_{key}_lbl' in panel_refs:
                panel_refs[f'stat_{key}_lbl'].setToolTip(tip)
        
        # Capability tooltips with symbol explanations
        cap_tooltips = {
            'cp': (
                f"━━━ Cp (Process Capability) ━━━\n\n"
                f"Symbols: USL/LSL = Spec Limits, σ = Std Dev\n\n"
                f"Formula: Cp = (USL - LSL) / 6σ\n\n"
                f"Current:\n"
                f"  USL = {tol_max:.4f}, LSL = {tol_min:.4f}\n"
                f"  σ (Std Dev) = {stats['std']:.4f}\n"
                f"  Cp = {capability['cp']:.4f}\n\n"
                f"Rating: {capability['cp_rating']}"
            ),
            'cpk': (
                f"━━━ Cpk (Process Capability Index) ━━━\n\n"
                f"Symbols: USL/LSL = Spec Limits\n"
                f"         µ = Mean, σ = Std Dev\n\n"
                f"Formula: Cpk = min(CPU, CPL)\n"
                f"  CPU = (USL - µ) / 3σ\n"
                f"  CPL = (µ - LSL) / 3σ\n\n"
                f"Current:\n"
                f"  CPU = {capability.get('cpu', 0):.4f}\n"
                f"  CPL = {capability.get('cpl', 0):.4f}\n"
                f"  Cpk = {capability['cpk']:.4f}\n\n"
                f"Rating: {capability['cpk_rating']}"
            ),
            'cpm': (
                f"━━━ Cpm (Taguchi Index) ━━━\n\n"
                f"Symbols: Cp = Capability, µ = Mean\n"
                f"         T = Target, σ = Std Dev\n\n"
                f"Formula: Cpm = Cp / √(1 + ((µ-T)/σ)²)\n\n"
                f"Current:\n"
                f"  µ - T (deviation) = {stats['mean'] - setpoint:.4f}\n"
                f"  Cpm = {capability['cpm']:.4f}\n\n"
                f"Rating: {capability['cpm_rating']}"
            )
        }
        
        def get_cap_color(v):
            return "#6bcf6b" if v >= 1.67 else "#8bc34a" if v >= 1.33 else "#ffc107" if v >= 1.0 else "#ff6b6b"
        
        for metric in ['cp', 'cpk', 'cpm']:
            if f'stat_{metric}' in panel_refs:
                panel_refs[f'stat_{metric}'].setText(f"{capability[metric]:.3f}")
                panel_refs[f'stat_{metric}'].setStyleSheet(f"color: {get_cap_color(capability[metric])}; font-size: 10px; font-weight: bold; border: none;")
                panel_refs[f'stat_{metric}'].setToolTip(cap_tooltips[metric])
    
    def _on_setting_changed(self, edit_widget, setting_type, var_name):
        try:
            text = edit_widget.text().replace('%', '').strip()
            value = float(text)
            if setting_type == 'setpoint':
                self.setpoints[var_name] = value
                self._user_set_setpoint.add(var_name)
            elif setting_type == 'tolerance':
                self.tolerances[var_name] = value
                # Also mark as user-set so tolerance filter activates
                self._user_set_setpoint.add(var_name)
            self.update_analytics(force=True)
        except ValueError:
            pass
    
    def _on_line_toggle(self, var_name, line_type, state):
        """Toggle visibility of setpoint or tolerance lines on the main graph."""
        is_checked = (state == 2)  # Qt.CheckState.Checked = 2
        if line_type == 'setpoint':
            self.show_setpoint_line[var_name] = is_checked
        elif line_type == 'tolerance':
            self.show_tolerance_lines[var_name] = is_checked
        self._update_main_graph_lines(var_name)
    
    def _choose_line_color(self, var_name, line_type, button):
        """Open color picker for setpoint or tolerance line."""
        current_color = self.setpoint_colors.get(var_name, '#00ff00') if line_type == 'setpoint' else self.tolerance_colors.get(var_name, '#ffaa00')
        color = QColorDialog.getColor(QColor(current_color), self, f"Choose {line_type} line color")
        if color.isValid():
            color_str = color.name()
            if line_type == 'setpoint':
                self.setpoint_colors[var_name] = color_str
            elif line_type == 'tolerance':
                self.tolerance_colors[var_name] = color_str
            button.setStyleSheet(f"background-color: {color_str}; border: 1px solid #555; border-radius: 3px;")
            self._update_main_graph_lines(var_name)
    
    def _update_main_graph_lines(self, var_name):
        """Update setpoint and tolerance lines on the main graph in main_window."""
        if var_name not in self._variable_panels:
            return
        
        panel_refs = self._variable_panels[var_name]
        graph = panel_refs.get('graph')
        if not graph:
            return
        
        setpoint = self.setpoints.get(var_name, 0)
        tolerance = self.tolerances.get(var_name, 1.0)
        
        # Update setpoint line on main graph
        sp_enabled = self.show_setpoint_line.get(var_name, False)
        sp_color = self.setpoint_colors.get(var_name, '#00ff00')
        graph.set_setpoint_line(var_name, sp_enabled, setpoint, sp_color)
        
        # Update tolerance lines on main graph
        tol_enabled = self.show_tolerance_lines.get(var_name, False)
        tol_color = self.tolerance_colors.get(var_name, '#ffaa00')
        graph.set_tolerance_lines(var_name, tol_enabled, setpoint, tolerance, tol_color)
    
    def _get_rsd_color_rating(self, rsd_val):
        """Get color and rating text for RSD value.
        
        Rating scale:
        - < 0.5%: Excellent (green)
        - < 1%: Very good (light green)
        - < 2.5%: Medium (yellow)
        - < 5%: Poor (orange)
        - >= 5%: High variability (red)
        """
        if rsd_val < 0.5:
            return "#6bcf6b", "Excellent"
        elif rsd_val < 1:
            return "#8bc34a", "Very Good"
        elif rsd_val < 2.5:
            return "#ffc107", "Medium"
        elif rsd_val < 5:
            return "#ff9800", "Poor"
        else:
            return "#ff6b6b", "High Variability"
    
    def _get_color_for_ratio(self, ratio):
        colors = ["#78B674", "#86B870", "#96BA6D", "#A8BC6B", "#BAAD66", "#BC9B5E", "#BE8657", "#C07152", "#C2584D"]
        return colors[min(int(ratio * (len(colors) - 1)), len(colors) - 1)]
    
    # ── Frameless window edge-resizing (Windows native hit-test) ────────
    _BORDER = 8

    def nativeEvent(self, eventType, message):
        """Handle Windows WM_NCHITTEST for edge/corner resize on frameless window."""
        try:
            import ctypes
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                if x >= 0x8000:
                    x -= 0x10000
                if y >= 0x8000:
                    y -= 0x10000
                geo = self.frameGeometry()
                b = self._BORDER
                left = abs(x - geo.left()) <= b
                right = abs(x - geo.right()) <= b
                top = abs(y - geo.top()) <= b
                bottom = abs(y - geo.bottom()) <= b
                if top and left:
                    return True, 13
                if top and right:
                    return True, 14
                if bottom and left:
                    return True, 16
                if bottom and right:
                    return True, 17
                if left:
                    return True, 10
                if right:
                    return True, 11
                if top:
                    return True, 12
                if bottom:
                    return True, 15
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        self.refresh_timer.stop()
        self._interaction_timer.stop()
        super().closeEvent(event)
