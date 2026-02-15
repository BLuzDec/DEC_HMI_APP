"""
HMI-PLC Main Window.
Similar to Monitoring: connection sidebar, comm info. No datapoints.
Load: Exchange, Recipes, Requests CSVs.
Center: Tabbed HMI screens.
File->Open... for HMI project.
"""
import sys
import json
import os

from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QSplitter, QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox, QFileDialog, QMessageBox,
    QTabWidget, QScrollArea, QDialog, QFormLayout, QGroupBox,
)

from hmi_components import PaletteButton
from hmi_canvas_widget import HmiCanvasWidget
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction

# Add project root for shared and monitoring imports
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from shared.title_bar import CustomTitleBar, get_app_icon, get_project_root
from shared.frameless_resize import FramelessResizeMixin

# Import variable loaders (monitoring external)
_monitoring_ext = os.path.join(_root, "monitoring", "external")
if _monitoring_ext not in sys.path:
    sys.path.insert(0, os.path.join(_root, "monitoring"))

try:
    from external.variable_loader import load_exchange_csv, load_recipe_csv, discover_csv_files
except ImportError:
    load_exchange_csv = load_recipe_csv = discover_csv_files = None

from requests_loader import load_requests_csv
from scl_parser import scl_to_json
from block_definitions import register_block_from_json
from fc_generator import generate_fc_and_dbs
from simulation_config_widget import SimulationConfigPanel


def _app_icon():
    return get_app_icon()


class ConnectionPopup(QDialog):
    """Connection configuration popup (Client, IP, Variable files) - same style as Monitoring."""
    def __init__(self, content_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection")
        if not get_app_icon().isNull():
            self.setWindowIcon(get_app_icon())
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content_widget)
        self.setStyleSheet("QDialog { background-color: #2d2d30; }")
        self.resize(420, 380)


class LoadPopup(QDialog):
    """Load popup: Exchange, Recipes, Requests CSVs."""
    def __init__(self, content_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Variables")
        if not get_app_icon().isNull():
            self.setWindowIcon(get_app_icon())
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content_widget)
        self.setStyleSheet("QDialog { background-color: #2d2d30; }")
        self.resize(420, 480)


class HmiPlcMainWindow(FramelessResizeMixin, QMainWindow):
    """HMI-PLC main window: sidebar (connection, comm info), center (tabbed HMI screens)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HMI-PLC - Dec S&T")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1200, 750)
        if not get_app_icon().isNull():
            self.setWindowIcon(get_app_icon())
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")

        self.exchange_variables_path = ""
        self.recipe_variables_path = ""
        self.requests_variables_path = ""
        self.all_variables = []
        self.recipe_params = []
        self.requests_variables = []
        self.variable_metadata = {}
        self.requests_metadata = {}
        self.current_hmi_project_path = None

        # Title bar with menu
        self._title_bar = CustomTitleBar(self, show_menu_bar=True)
        self._create_menu_bar()

        # Root layout
        root = QWidget()
        root.setObjectName("_rootWidget")
        root.setStyleSheet("QWidget#_rootWidget { border: 1px solid #3e3e42; }")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(1, 0, 1, 1)
        root_layout.addWidget(self._title_bar)

        main_widget = QWidget()
        root_layout.addWidget(main_widget, 1)
        self.setCentralWidget(root)

        # Main splitter: sidebar | center
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # ── Sidebar (connection + comm info, NO datapoints) ──
        sidebar = QWidget()
        sidebar.setStyleSheet("background-color: #252526;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)

        _label_w, _row_h = 82, 28

        # Connection popup content
        conn_layout = QVBoxLayout()
        conn_layout.setSpacing(6)
        device_row = QHBoxLayout()
        device_row.addWidget(QLabel("Client:"))
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["Snap7", "ADS", "Simulation"])
        self.device_type_combo.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        device_row.addWidget(self.device_type_combo)
        conn_layout.addLayout(device_row)

        self.address_row = QWidget()
        addr_layout = QHBoxLayout(self.address_row)
        addr_layout.addWidget(QLabel("IP:"))
        self.ip_input = QLineEdit("192.168.0.20")
        self.ip_input.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 5px;")
        addr_layout.addWidget(self.ip_input)
        conn_layout.addWidget(self.address_row)

        conn_layout.addWidget(QLabel("Variable files:"))
        ex_row = QHBoxLayout()
        self.exchange_path_edit = QLineEdit()
        self.exchange_path_edit.setReadOnly(True)
        self.exchange_path_edit.setPlaceholderText("Exchange CSV")
        self.browse_exchange_btn = QPushButton("Exchange…")
        self.browse_exchange_btn.clicked.connect(self._browse_exchange)
        ex_row.addWidget(self.exchange_path_edit)
        ex_row.addWidget(self.browse_exchange_btn)
        conn_layout.addLayout(ex_row)

        rec_row = QHBoxLayout()
        self.recipe_path_edit = QLineEdit()
        self.recipe_path_edit.setReadOnly(True)
        self.recipe_path_edit.setPlaceholderText("Recipe CSV")
        self.browse_recipe_btn = QPushButton("Recipes…")
        self.browse_recipe_btn.clicked.connect(self._browse_recipe)
        rec_row.addWidget(self.recipe_path_edit)
        rec_row.addWidget(self.browse_recipe_btn)
        conn_layout.addLayout(rec_row)

        req_row = QHBoxLayout()
        self.requests_path_edit = QLineEdit()
        self.requests_path_edit.setReadOnly(True)
        self.requests_path_edit.setPlaceholderText("Requests CSV (outputs to PLC)")
        self.browse_requests_btn = QPushButton("Requests…")
        self.browse_requests_btn.clicked.connect(self._browse_requests)
        req_row.addWidget(self.requests_path_edit)
        req_row.addWidget(self.browse_requests_btn)
        conn_layout.addLayout(req_row)

        conn_frame = QFrame()
        conn_frame.setStyleSheet("QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 3px; }")
        conn_frame_layout = QVBoxLayout(conn_frame)
        conn_frame_layout.addWidget(QLabel("CONNECTION"))
        conn_frame_layout.addLayout(conn_layout)
        sidebar_layout.addWidget(conn_frame)

        # Connect / Disconnect
        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(
            "QPushButton { background-color: #1a6fa5; color: white; font-weight: bold; padding: 5px; border: none; border-radius: 3px; }"
        )
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet(
            "QPushButton { background-color: #6b2d2d; color: #e8e8e8; padding: 5px; border-radius: 3px; }"
            "QPushButton:disabled { background-color: #3a3a3a; color: #707070; }"
        )
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        sidebar_layout.addLayout(btn_row)

        # Load variables button
        self.load_vars_btn = QPushButton("Load Variables")
        self.load_vars_btn.setStyleSheet(
            "QPushButton { background-color: #5a3a8a; color: white; font-weight: bold; padding: 7px; border: none; border-radius: 3px; }"
        )
        self.load_vars_btn.clicked.connect(self._open_load_popup)
        sidebar_layout.addWidget(self.load_vars_btn)

        # Component palette: drag these onto the canvas
        palette_frame = QFrame()
        palette_frame.setStyleSheet("QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 3px; margin-top: 8px; }")
        palette_layout = QVBoxLayout(palette_frame)
        palette_label = QLabel("Drag onto canvas:")
        palette_label.setStyleSheet("font-weight: bold; color: #aaa; font-size: 11px;")
        palette_layout.addWidget(palette_label)
        btn_style = "QPushButton { background-color: #444; color: #ddd; padding: 6px; border: 1px solid #555; border-radius: 3px; } QPushButton:hover { background-color: #555; }"
        for label, ctype in [
            ("Valve (open)", "valve"),
            ("Valve (closed)", "valve_closed"),
            ("Tank", "tank"),
            ("Pump", "pump"),
            ("Block (MPTS)", "block_mpts"),
        ]:
            btn = PaletteButton(label, ctype)
            btn.setStyleSheet(btn_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            palette_layout.addWidget(btn)
        sidebar_layout.addWidget(palette_frame)

        # Communication Info Panel (same style as Monitoring)
        self.comm_info_panel = self._create_comm_info_panel()
        sidebar_layout.addWidget(self.comm_info_panel)
        sidebar_layout.addStretch()

        splitter.addWidget(sidebar)

        # ── Center: Tabbed HMI screens ──
        self.hmi_tabs = QTabWidget()
        self.hmi_tabs.setStyleSheet("""
            QTabWidget::pane { background-color: #1e1e1e; border: 1px solid #3e3e42; }
            QTabBar::tab { background-color: #2d2d30; color: #ccc; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #1e1e1e; color: white; }
            QTabBar::tab:hover:!selected { background-color: #3e3e42; }
        """)
        self.hmi_tabs.setTabsClosable(True)
        self.hmi_tabs.tabCloseRequested.connect(self._close_hmi_tab)
        self._add_default_tab()
        splitter.addWidget(self.hmi_tabs)
        splitter.setSizes([280, 900])

        # Connection popup
        conn_popup_content = QWidget()
        conn_popup_layout = QVBoxLayout(conn_popup_content)
        conn_popup_layout.addWidget(conn_frame)
        self.connection_popup = ConnectionPopup(conn_popup_content, self)

        # Load popup
        self.load_popup_content = self._create_load_popup_content()
        self.load_popup = LoadPopup(self.load_popup_content, self)

        self._load_last_config()

    def _create_comm_info_panel(self):
        """Create collapsible communication info panel (same as Monitoring)."""
        container = QFrame()
        container.setStyleSheet(
            "QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 4px; margin-top: 10px; }"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        header = QWidget()
        h_layout = QHBoxLayout(header)
        self.comm_info_label = QLabel("📡 Communication Info")
        self.comm_info_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 12px;")
        h_layout.addWidget(self.comm_info_label)
        h_layout.addStretch()
        self.comm_toggle_btn = QPushButton("▼")
        self.comm_toggle_btn.setFixedSize(20, 20)
        self.comm_toggle_btn.clicked.connect(self._toggle_comm_info)
        h_layout.addWidget(self.comm_toggle_btn)
        layout.addWidget(header)
        self.comm_info_content = QWidget()
        content_layout = QVBoxLayout(self.comm_info_content)
        self.comm_status_label = QLabel("Status: Not connected")
        self.comm_status_label.setStyleSheet("color: #888; font-size: 11px;")
        content_layout.addWidget(self.comm_status_label)
        self.comm_ip_label = QLabel("IP: --")
        self.comm_ip_label.setStyleSheet("color: #aaa; font-size: 10px;")
        content_layout.addWidget(self.comm_ip_label)
        layout.addWidget(self.comm_info_content)
        return container

    def _toggle_comm_info(self):
        visible = self.comm_info_content.isVisible()
        self.comm_info_content.setVisible(not visible)
        self.comm_toggle_btn.setText("▼" if not visible else "▲")

    def _create_load_popup_content(self):
        """Create Load popup: Exchange, Recipes, Requests CSV browse + load."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Load variable CSVs for HMI bindings:"))
        grp = QGroupBox("Variable files")
        grp.setStyleSheet("QGroupBox { color: #ccc; }")
        form = QFormLayout(grp)
        self.load_exchange_label = QLabel("(none)")
        self.load_exchange_label.setStyleSheet("color: #888; font-size: 10px;")
        self.load_recipe_label = QLabel("(none)")
        self.load_recipe_label.setStyleSheet("color: #888; font-size: 10px;")
        self.load_requests_label = QLabel("(none)")
        self.load_requests_label.setStyleSheet("color: #888; font-size: 10px;")
        form.addRow("Exchange:", self.load_exchange_label)
        form.addRow("Recipes:", self.load_recipe_label)
        form.addRow("Requests:", self.load_requests_label)
        browse_row = QHBoxLayout()
        browse_ex = QPushButton("Browse Exchange…")
        browse_ex.clicked.connect(self._browse_exchange)
        browse_rec = QPushButton("Browse Recipes…")
        browse_rec.clicked.connect(self._browse_recipe)
        browse_req = QPushButton("Browse Requests…")
        browse_req.clicked.connect(self._browse_requests)
        browse_row.addWidget(browse_ex)
        browse_row.addWidget(browse_rec)
        browse_row.addWidget(browse_req)
        form.addRow("", browse_row)
        layout.addWidget(grp)
        load_btn = QPushButton("Load All")
        load_btn.clicked.connect(self._load_all_variables)
        layout.addWidget(load_btn)
        self.load_status_label = QLabel("No variables loaded.")
        self.load_status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.load_status_label)
        layout.addStretch()
        return w

    def _create_menu_bar(self):
        mb = self._title_bar.menu_bar
        file_menu = mb.addMenu("File")
        file_menu.addAction("Open...", self._open_hmi_project)
        file_menu.addAction("Open HMI_MPTS", self._open_hmi_mpts)
        file_menu.addSeparator()
        file_menu.addAction("Import SCL...", self._import_scl)
        file_menu.addAction("Generate FC from SCL...", self._generate_fc_from_scl)
        file_menu.addSeparator()
        file_menu.addAction("Connect...", lambda: self.connection_popup.show() if hasattr(self, "connection_popup") else None)
        file_menu.addAction("Load Variables...", self._open_load_popup)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        view_menu = mb.addMenu("View")
        view_menu.addAction("Add HMI Tab", self._add_hmi_tab)
        view_menu.addAction("Configure simulation...", self._open_simulation_config)

    def _add_default_tab(self):
        """Add default empty HMI tab."""
        self._add_hmi_tab("Screen 1")

    def _add_hmi_tab(self, name=None):
        """Add a new HMI screen tab with drag-and-drop canvas."""
        if name is None:
            name = f"Screen {self.hmi_tabs.count() + 1}"
        canvas = HmiCanvasWidget()
        idx = self.hmi_tabs.addTab(canvas, name)
        self.hmi_tabs.setCurrentIndex(idx)

    def _close_hmi_tab(self, index):
        if self.hmi_tabs.count() > 1:
            self.hmi_tabs.removeTab(index)

    def _browse_exchange(self):
        path, _ = QFileDialog.getOpenFileName(self, "Exchange CSV", "", "CSV (*.csv);;All (*)")
        if path:
            self.exchange_variables_path = path
            self.exchange_path_edit.setText(os.path.basename(path))
            self.exchange_path_edit.setToolTip(path)
            if hasattr(self, "load_exchange_label"):
                self.load_exchange_label.setText(os.path.basename(path))

    def _browse_recipe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Recipe CSV", "", "CSV (*.csv);;All (*)")
        if path:
            self.recipe_variables_path = path
            self.recipe_path_edit.setText(os.path.basename(path))
            self.recipe_path_edit.setToolTip(path)
            if hasattr(self, "load_recipe_label"):
                self.load_recipe_label.setText(os.path.basename(path))

    def _browse_requests(self):
        path, _ = QFileDialog.getOpenFileName(self, "Requests CSV", "", "CSV (*.csv);;All (*)")
        if path:
            self.requests_variables_path = path
            self.requests_path_edit.setText(os.path.basename(path))
            self.requests_path_edit.setToolTip(path)
            if hasattr(self, "load_requests_label"):
                self.load_requests_label.setText(os.path.basename(path))

    def _open_load_popup(self):
        self.load_exchange_label.setText(os.path.basename(self.exchange_variables_path) if self.exchange_variables_path else "(none)")
        self.load_recipe_label.setText(os.path.basename(self.recipe_variables_path) if self.recipe_variables_path else "(none)")
        self.load_requests_label.setText(os.path.basename(self.requests_variables_path) if self.requests_variables_path else "(none)")
        self.load_popup.show()
        self.load_popup.raise_()

    def _load_all_variables(self):
        """Load Exchange, Recipes, Requests from current paths."""
        all_vars = []
        meta = {}
        recipes = []
        requests = []
        req_meta = {}
        ext_dir = os.path.join(get_project_root(), "monitoring", "external")
        if load_exchange_csv and self.exchange_variables_path and os.path.isfile(self.exchange_variables_path):
            v, m = load_exchange_csv(self.exchange_variables_path)
            all_vars.extend(v)
            meta.update(m)
        elif not self.exchange_variables_path and os.path.isdir(ext_dir):
            disc_ex, _ = discover_csv_files(ext_dir) if discover_csv_files else (None, None)
            if disc_ex:
                v, m = load_exchange_csv(disc_ex)
                all_vars.extend(v)
                meta.update(m)
                self.exchange_variables_path = disc_ex
                self.exchange_path_edit.setText(os.path.basename(disc_ex))
        if load_recipe_csv and self.recipe_variables_path and os.path.isfile(self.recipe_variables_path):
            r, meta = load_recipe_csv(self.recipe_variables_path, meta)
            recipes.extend(r)
        if self.requests_variables_path and os.path.isfile(self.requests_variables_path):
            req_v, req_m = load_requests_csv(self.requests_variables_path)
            requests.extend(req_v)
            req_meta.update(req_m)
        elif not self.requests_variables_path:
            sample = os.path.join(ext_dir, "requests_variables_sample.csv")
            if os.path.isfile(sample):
                req_v, req_m = load_requests_csv(sample)
                requests.extend(req_v)
                req_meta.update(req_m)
                self.requests_variables_path = sample
                self.requests_path_edit.setText("requests_variables_sample.csv")
        self.all_variables = all_vars
        self.recipe_params = recipes
        self.requests_variables = requests
        self.variable_metadata = meta
        self.requests_metadata = req_meta
        total = len(all_vars) + len(recipes) + len(requests)
        self.load_status_label.setText(f"Loaded: {len(all_vars)} exchange, {len(recipes)} recipes, {len(requests)} requests ({total} total)")
        self._save_last_config()

    def _open_hmi_mpts(self):
        """Open HMI_MPTS project (block view + visual valves)."""
        proj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "HMI_MPTS.hmi")
        if os.path.isfile(proj_path):
            self._load_hmi_project(proj_path)
        else:
            QMessageBox.information(
                self, "HMI_MPTS",
                f"HMI_MPTS project not found at:\n{proj_path}"
            )

    def _load_hmi_project(self, path):
        """Load HMI project from path."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tabs = data.get("tabs", [])
            if not tabs:
                tabs = [{"name": "Screen 1", "widgets": []}]
            self.hmi_tabs.clear()
            for tab in tabs:
                name = tab.get("name", "Screen")
                canvas = HmiCanvasWidget()
                canvas.load_from_project(tab.get("widgets", []))
                self.hmi_tabs.addTab(canvas, name)
            self.current_hmi_project_path = path
            self.setWindowTitle(f"HMI-PLC - {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Open Failed", str(e))

    def _open_hmi_project(self):
        """Open HMI project file (.hmi or .json) with tabbed screens."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open HMI Project", "",
            "HMI Project (*.hmi *.json);;All (*)"
        )
        if path:
            self._load_hmi_project(path)

    def _load_last_config(self):
        s = QSettings("DecAutomation", "HmiPlc")
        self.exchange_variables_path = s.value("exchange_path", "") or ""
        self.recipe_variables_path = s.value("recipe_path", "") or ""
        self.requests_variables_path = s.value("requests_path", "") or ""
        if self.exchange_variables_path:
            self.exchange_path_edit.setText(os.path.basename(self.exchange_variables_path))
            self.exchange_path_edit.setToolTip(self.exchange_variables_path)
        if self.recipe_variables_path:
            self.recipe_path_edit.setText(os.path.basename(self.recipe_variables_path))
            self.recipe_path_edit.setToolTip(self.recipe_variables_path)
        if self.requests_variables_path:
            self.requests_path_edit.setText(os.path.basename(self.requests_variables_path))
            self.requests_path_edit.setToolTip(self.requests_variables_path)
        ext_dir = os.path.join(get_project_root(), "monitoring", "external")
        if not self.exchange_variables_path and discover_csv_files:
            ex, rec = discover_csv_files(ext_dir)
            if ex:
                self.exchange_variables_path = ex
                self.exchange_path_edit.setText(os.path.basename(ex))
            if rec:
                self.recipe_variables_path = rec
                self.recipe_path_edit.setText(os.path.basename(rec))

    def _import_scl(self):
        """Import .scl file, parse to JSON, save and register block."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import SCL", "",
            "SCL (*.scl);;All (*)"
        )
        if not path:
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save block JSON", os.path.splitext(os.path.basename(path))[0] + ".json",
            "JSON (*.json);;All (*)"
        )
        if not out_path:
            return
        try:
            scl_to_json(path, out_path)
            if register_block_from_json(out_path):
                QMessageBox.information(
                    self, "Import SCL",
                    f"Parsed and saved to:\n{out_path}\n\nBlock registered. Add it from the palette or open a project."
                )
            else:
                QMessageBox.warning(self, "Import SCL", "Saved JSON but failed to register block.")
        except Exception as e:
            QMessageBox.warning(self, "Import SCL", str(e))

    def _open_simulation_config(self):
        """Open dialog to configure simulation type and params per i* variable."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        # Build i* variables from block definitions (e.g. MPTS)
        from block_definitions import BLOCK_REGISTRY
        from simulation import FeedbackSimulator
        mpts = BLOCK_REGISTRY.get("mpts", {})
        inputs = mpts.get("inputs", [])
        mapping = FeedbackSimulator.DEFAULT_MAPPING
        vars_list = []
        for inp in inputs:
            name = inp.get("name", "") if isinstance(inp, dict) else inp[0]
            vtype = inp.get("type", "Real") if isinstance(inp, dict) else (inp[1] if len(inp) > 1 else "Real")
            if name.startswith("i") and name[1:2].isupper() and len(name) > 1:
                setpoint = mapping.get(name, ("", "first_order", {}))[0] if name in mapping else ""
                vars_list.append({"name": name, "type": vtype, "setpoint_var": setpoint})
        if not vars_list:
            vars_list = [
                {"name": "iChamberPressure", "type": "Real", "setpoint_var": "oChamberValvePR"},
                {"name": "iInletValvePressure", "type": "Real", "setpoint_var": "oInletValvePR"},
                {"name": "iOutletValvePressure", "type": "Real", "setpoint_var": "oOutletValvePR"},
            ]
        dlg = QDialog(self)
        dlg.setWindowTitle("Configure simulation")
        layout = QVBoxLayout(dlg)
        panel = SimulationConfigPanel(vars_list)
        layout.addWidget(panel)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.setStyleSheet("QDialog { background-color: #2d2d30; }")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            config = panel.get_config()
            # Store for FeedbackSimulator (could be used when Play starts)
            self._simulation_config = config

    def _generate_fc_from_scl(self):
        """Generate FC + DBs from FB SCL file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FB SCL", "",
            "SCL (*.scl);;All (*)"
        )
        if not path:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Output directory", os.path.dirname(path))
        if not out_dir:
            return
        try:
            fc_path, db_hmi_path, db_plc_path = generate_fc_and_dbs(path, out_dir)
            QMessageBox.information(
                self, "Generate FC",
                f"Generated:\n{fc_path}\n{db_hmi_path}\n{db_plc_path}\n\n"
                "Add DB_HMI_To_PLC and DB_PLC_To_HMI to your PLC project. "
                "Create DB_Parameters, DB_Settings, DB_Timers if the FB uses them."
            )
        except Exception as e:
            QMessageBox.warning(self, "Generate FC", str(e))

    def _save_last_config(self):
        s = QSettings("DecAutomation", "HmiPlc")
        s.setValue("exchange_path", self.exchange_variables_path or "")
        s.setValue("recipe_path", self.recipe_variables_path or "")
        s.setValue("requests_path", self.requests_variables_path or "")
        s.sync()
