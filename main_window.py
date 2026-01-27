import sys
import csv
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                               QListWidget, QPushButton, QSplitter, QScrollArea, 
                               QAbstractItemView, QLabel, QApplication, QFrame,
                               QDialog, QComboBox, QDialogButtonBox, QFormLayout,
                               QCheckBox)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPalette, QColor
import pyqtgraph as pg
from collections import deque

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
        return {
            "x_axis": self.combo_x_axis.currentText()
        }

class RangeConfigDialog(QDialog):
    """Dialog to configure Min/Max ranges for axes."""
    def __init__(self, current_settings, has_dual_y=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Axis Range Settings")
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
        
        # Helper to create row
        def create_axis_row(axis_id, label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(80)
            
            # Get values or defaults
            vals = self.current_settings.get(axis_id, {"auto": True, "min": 0.0, "max": 10.0})

            chk_auto = QCheckBox("Auto")
            chk_auto.setChecked(vals["auto"])
            
            spin_min = pg.SpinBox(value=vals["min"]) 
            spin_min.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            spin_min.setDecimals(2)
            spin_min.setRange(-1e9, 1e9)
            spin_min.setEnabled(not vals["auto"])
            
            spin_max = pg.SpinBox(value=vals["max"])
            spin_max.setStyleSheet("background-color: #444; color: white; border: 1px solid #555;")
            spin_max.setDecimals(2)
            spin_max.setRange(-1e9, 1e9)
            spin_max.setEnabled(not vals["auto"])
            
            chk_auto.toggled.connect(lambda checked: spin_min.setEnabled(not checked))
            chk_auto.toggled.connect(lambda checked: spin_max.setEnabled(not checked))
            
            row.addWidget(lbl)
            row.addWidget(chk_auto)
            row.addWidget(QLabel("Min:"))
            row.addWidget(spin_min)
            row.addWidget(QLabel("Max:"))
            row.addWidget(spin_max)
            return row, chk_auto, spin_min, spin_max

        # X Axis
        self.x_row, self.chk_x_auto, self.spin_x_min, self.spin_x_max = create_axis_row("x", "X Axis")
        layout.addLayout(self.x_row)
        
        # Y Axis 1
        self.y1_row, self.chk_y1_auto, self.spin_y1_min, self.spin_y1_max = create_axis_row("y1", "Y Axis (Left)")
        layout.addLayout(self.y1_row)
        
        # Y Axis 2 (Optional)
        self.has_dual_y = has_dual_y
        if has_dual_y:
            self.y2_row, self.chk_y2_auto, self.spin_y2_min, self.spin_y2_max = create_axis_row("y2", "Y Axis (Right)")
            layout.addLayout(self.y2_row)
            
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        settings = {
            "x": {"auto": self.chk_x_auto.isChecked(), "min": self.spin_x_min.value(), "max": self.spin_x_max.value()},
            "y1": {"auto": self.chk_y1_auto.isChecked(), "min": self.spin_y1_min.value(), "max": self.spin_y1_max.value()},
        }
        if self.has_dual_y:
             settings["y2"] = {"auto": self.chk_y2_auto.isChecked(), "min": self.spin_y2_min.value(), "max": self.spin_y2_max.value()}
        return settings

class DynamicPlotWidget(QWidget):
    """
    A wrapper around pyqtgraph.PlotWidget that manages its own data lines.
    Supports dual Y-axes, XY plotting, and live value headers with range stats.
    """
    def __init__(self, variable_names, x_axis_source="Time (Index)", buffer_size=500):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        
        self.variables = variable_names
        self.x_axis_source = x_axis_source
        self.is_xy_plot = (x_axis_source != "Time (Index)")
        
        # --- Live Value Header ---
        self.header_layout = QHBoxLayout()
        self.layout.addLayout(self.header_layout)
        
        self.value_layout = QHBoxLayout()
        self.value_layout.setContentsMargins(5, 0, 5, 0)
        self.header_layout.addLayout(self.value_layout)
        
        self.value_labels = {}
        
        # Settings Button
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Configure Axis Ranges")
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #888; border: 1px solid #444; border-radius: 4px;
            }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_settings.clicked.connect(self.open_range_settings)
        self.header_layout.addWidget(self.btn_settings)

        # --- Plot Widget ---
        self.plot_widget = pg.PlotWidget()
        self.layout.addWidget(self.plot_widget)
        
        # Modern Plot Styling
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.getAxis('left').setPen('#888')
        self.plot_widget.getAxis('bottom').setPen('#888')
        self.plot_widget.getAxis('left').setTextPen('#aaa')
        self.plot_widget.getAxis('bottom').setTextPen('#aaa')
        
        if self.is_xy_plot:
            self.plot_widget.setLabel('bottom', self.x_axis_source)
        else:
            self.plot_widget.setLabel('bottom', 'Time')

        self.lines = {}
        self.buffers_y = {} # Stores Y values
        self.buffers_x = {} # Stores X values (if XY plot)
        self.buffer_size = buffer_size
        self.p2 = None # Secondary ViewBox
        
        # Neon/Modern Colors
        self.colors = ['#00E676', '#2979FF', '#FF1744', '#FFEA00', '#AA00FF', '#00B0FF', '#FF9100']
        
        # Init Range Settings Persistence
        self.range_settings = {
             "x": {"auto": True, "min": 0.0, "max": 10.0},
             "y1": {"auto": True, "min": 0.0, "max": 10.0},
             "y2": {"auto": True, "min": 0.0, "max": 10.0}
        }

        # Setup Axes and Lines
        # Note: Dual Axis logic is complex with XY plotting, so we simplify:
        # If XY plot, use single Y axis for now (or multiple lines on same axis).
        # If Time plot, keep Dual Axis logic if exactly 2 vars.
        if len(self.variables) == 2 and not self.is_xy_plot:
            self._setup_dual_axis()
        else:
            self._setup_single_axis()

    def _setup_single_axis(self):
        for i, var in enumerate(self.variables):
            color = self.colors[i % len(self.colors)]
            self._add_variable(var, color, self.plot_widget.plotItem)

    def _setup_dual_axis(self):
        var1 = self.variables[0]
        color1 = self.colors[0]
        p1 = self.plot_widget.plotItem
        
        p1.setLabels(left=var1)
        p1.getAxis('left').setPen(color1)
        p1.getAxis('left').setTextPen(color1)
        
        self._add_variable(var1, color1, p1)
        
        var2 = self.variables[1]
        color2 = self.colors[1]
        
        self.p2 = pg.ViewBox()
        p1.showAxis('right')
        p1.scene().addItem(self.p2)
        p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(p1)
        
        p1.getAxis('right').setLabel(var2, color=color2)
        p1.getAxis('right').setPen(color2)
        p1.getAxis('right').setTextPen(color2)
        
        def updateViews():
            self.p2.setGeometry(p1.vb.sceneBoundingRect())
            self.p2.linkedViewChanged(p1.vb, self.p2.XAxis)
            
        updateViews()
        p1.vb.sigResized.connect(updateViews)
        
        self._add_variable(var2, color2, self.p2)

    def _add_variable(self, var, color, plot_item):
        pen = None
        symbol = None
        
        if self.is_xy_plot:
            # Scatter / Line for XY
            pen = None # No line connecting points usually looks better for XY unless sorted
            symbol = 'o' # Dots
            pen = pg.mkPen(color=color, width=2) # Line connecting them
        else:
            pen = pg.mkPen(color=color, width=2)
            
        if isinstance(plot_item, pg.ViewBox):
             line = pg.PlotCurveItem(pen=pen, symbol=symbol, symbolBrush=color, name=var)
             plot_item.addItem(line)
        else:
             line = plot_item.plot(name=var, pen=pen, symbol=symbol, symbolBrush=color)
        
        self.lines[var] = line
        self.buffers_y[var] = deque(maxlen=self.buffer_size)
        if self.is_xy_plot:
            self.buffers_x[var] = deque(maxlen=self.buffer_size)
        
        # Header Label with stats
        lbl = QLabel(f"{var}: --")
        lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px; margin-right: 15px;")
        self.value_layout.addWidget(lbl)
        self.value_labels[var] = lbl

    def open_range_settings(self):
        has_dual = (self.p2 is not None)
        dialog = RangeConfigDialog(self.range_settings, has_dual_y=has_dual, parent=self)
        
        if dialog.exec() == QDialog.Accepted:
            # Update settings persistence
            self.range_settings = dialog.get_settings()
            settings = self.range_settings
            
            # Apply X Axis
            if settings["x"]["auto"]:
                self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.XAxis)
            else:
                self.plot_widget.plotItem.setXRange(settings["x"]["min"], settings["x"]["max"], padding=0)

            # Apply Y Axis 1 (Left)
            if settings["y1"]["auto"]:
                self.plot_widget.plotItem.enableAutoRange(axis=pg.ViewBox.YAxis)
            else:
                self.plot_widget.plotItem.setYRange(settings["y1"]["min"], settings["y1"]["max"], padding=0)
                
            # Apply Y Axis 2 (Right) - if applicable
            if has_dual and "y2" in settings:
                if settings["y2"]["auto"]:
                    self.p2.enableAutoRange(axis=pg.ViewBox.YAxis)
                else:
                    self.p2.setYRange(settings["y2"]["min"], settings["y2"]["max"], padding=0)

    def update_data(self, var_name, y_value, x_value=None):
        if var_name not in self.variables:
            return

        # Update Buffers
        self.buffers_y[var_name].append(y_value)
        
        if self.is_xy_plot:
            if x_value is None: x_value = 0 # Fallback
            self.buffers_x[var_name].append(x_value)
            self.lines[var_name].setData(list(self.buffers_x[var_name]), list(self.buffers_y[var_name]))
        else:
            self.lines[var_name].setData(list(self.buffers_y[var_name]))

        # Update Stats Label
        data = list(self.buffers_y[var_name])
        min_v = min(data)
        max_v = max(data)
        
        # Format: Name: Val (Min: x, Max: y)
        txt = f"{var_name}: {y_value:.2f} <span style='font-size:10px; color:#aaa;'>(Min:{min_v:.1f} Max:{max_v:.1f})</span>"
        self.value_labels[var_name].setText(txt)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProAutomation Studio")
        self.resize(1280, 800)
        
        self.latest_values = {} # Cache for XY plotting
        self.all_variables = [] # List of all known vars

        self.apply_theme()

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        self.main_layout.addWidget(self.splitter)

        # Left Panel
        self.sidebar = QWidget()
        self.sidebar.setStyleSheet("background-color: #252526;")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        
        self.lbl_vars = QLabel("DATA POINTS")
        self.lbl_vars.setStyleSheet("font-weight: bold; font-size: 12px; color: #888; margin-bottom: 5px;")
        self.sidebar_layout.addWidget(self.lbl_vars)
        
        self.var_list = QListWidget()
        self.var_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.var_list.setStyleSheet("""
            QListWidget {
                background-color: #333333;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                color: #f0f0f0;
                outline: 0;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
        """)
        self.sidebar_layout.addWidget(self.var_list)
        
        self.btn_add_graph = QPushButton("Open Selected in Graph")
        self.btn_add_graph.setCursor(Qt.PointingHandCursor)
        self.btn_add_graph.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                font-weight: bold;
                padding: 12px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0098FF;
            }
            QPushButton:pressed {
                background-color: #005A9E;
            }
        """)
        self.btn_add_graph.clicked.connect(self.add_new_graph)
        self.sidebar_layout.addWidget(self.btn_add_graph)
        
        self.splitter.addWidget(self.sidebar)

        # Right Panel
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #1e1e1e; }")
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: #1e1e1e;")
        self.graphs_layout = QVBoxLayout(self.scroll_content)
        self.graphs_layout.setAlignment(Qt.AlignTop)
        self.graphs_layout.setSpacing(10)
        self.graphs_layout.setContentsMargins(10, 10, 10, 10)
        
        self.scroll_area.setWidget(self.scroll_content)
        
        self.splitter.addWidget(self.scroll_area)
        self.splitter.setSizes([300, 980])

        self.graphs = []
        self.load_variables()

    def apply_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(palette)

    def load_variables(self):
        try:
            with open("exchange_variables.csv", 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    var = row['Variable']
                    self.var_list.addItem(var)
                    self.all_variables.append(var)
                    self.latest_values[var] = 0.0 # Init cache
        except Exception as e:
            print(f"Error loading CSV: {e}")

    def add_new_graph(self):
        selected_items = self.var_list.selectedItems()
        if not selected_items:
            return
            
        var_names = [item.text() for item in selected_items]
        
        # Show Configuration Dialog
        dialog = GraphConfigDialog(self.all_variables, self)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            
            # Create container
            container = QFrame()
            container.setStyleSheet("background-color: #252526; border-radius: 6px;")
            container.setFixedHeight(350)
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(10,10,10,10)
            vbox.setSpacing(5)
            
            # Header
            header = QWidget()
            header.setStyleSheet("background-color: transparent;")
            hbox = QHBoxLayout(header)
            hbox.setContentsMargins(0,0,0,0)
            
            x_title = settings['x_axis']
            title_text = f"{' • '.join(var_names)}  [vs {x_title}]"
            
            lbl_title = QLabel(title_text)
            lbl_title.setStyleSheet("font-weight: bold; color: #ccc; font-size: 13px;")
            
            btn_close = QPushButton("✕")
            btn_close.setFixedSize(24, 24)
            btn_close.setCursor(Qt.PointingHandCursor)
            btn_close.setStyleSheet("""
                QPushButton {
                    background-color: transparent; 
                    color: #888; 
                    border-radius: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #cc3333;
                    color: white;
                }
            """)
            
            hbox.addWidget(lbl_title)
            hbox.addStretch()
            hbox.addWidget(btn_close)
            vbox.addWidget(header)

            # Plot
            new_graph = DynamicPlotWidget(var_names, x_axis_source=settings['x_axis'])
            vbox.addWidget(new_graph)
            
            self.graphs_layout.addWidget(container)
            self.graphs.append(new_graph)
            
            btn_close.clicked.connect(lambda: self.remove_graph(container, new_graph))

    def remove_graph(self, container, graph_widget):
        self.graphs_layout.removeWidget(container)
        container.deleteLater()
        if graph_widget in self.graphs:
            self.graphs.remove(graph_widget)

    @Slot(str, float)
    def update_plot(self, variable_name, value):
        # Update Cache
        self.latest_values[variable_name] = value
        
        # Notify Graphs
        for graph in self.graphs:
            # If this graph tracks this variable (Y-axis)
            if variable_name in graph.variables:
                
                # Determine X Value
                x_val = None
                if graph.is_xy_plot:
                    # Get the current value of the configured X-axis variable
                    x_src = graph.x_axis_source
                    x_val = self.latest_values.get(x_src, 0.0)
                
                graph.update_data(variable_name, value, x_value=x_val)
