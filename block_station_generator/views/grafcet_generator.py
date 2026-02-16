"""
Grafcet Generation view: NLP prompt, table, and real-time canvas.
Vertical layout with orthogonal (90°) lines. Rounded 3D-style steps, transitions, actions.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QGraphicsScene, QGraphicsView, QGraphicsRectItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsPathItem, QGraphicsObject,
    QColorDialog, QLabel, QAbstractItemView, QFrame, QPlainTextEdit, QLineEdit,
    QMessageBox, QApplication, QFileDialog, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QPointF, QThread, QRectF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPainterPath, QLinearGradient

from ..core.grafcet_model import GrafcetModel, GrafcetStep
from ..core.stepper_generator import generate_state_constants, generate_stepper_logic
from ..core.nlp_gemini import generate_grafcet_from_prompt


class _GenerateWorker(QThread):
    """Background worker for Gemini API call with status updates."""
    status_updated = Signal(str)
    finished = Signal(object, str)  # model, error

    def __init__(self, prompt: str):
        super().__init__()
        self._prompt = prompt

    def run(self):
        def on_status(msg: str):
            self.status_updated.emit(msg)

        model, err = generate_grafcet_from_prompt(self._prompt, status_callback=on_status)
        self.finished.emit(model, err or "")


# Default step colors
GRAFCET_BG = "#0078D4"
GRAFCET_BORDER = "#005A9E"
GRAFCET_TEXT = "#FFFFFF"
GRAFCET_LINE = "#4CAF50"
GRAFCET_HIGHLIGHT = "#FFB74D"  # Amber highlight when selected
GRAFCET_TRANSITION_BG = "#37474F"
GRAFCET_TRANSITION_BORDER = "#546E7A"

STEP_SIZE = 64
STEP_WIDTH = 88
GAP_V = 12
TRANSITION_BAR_H = 22
SLOT_HEIGHT = STEP_SIZE + TRANSITION_BAR_H + GAP_V  # step + transition + gap
GAP_H = 48
CORNER_RADIUS = 10


def _orthogonal_line_path(
    x1: float, y1: float, x2: float, y2: float,
    src_bottom: bool = True, dst_top: bool = True
) -> QPainterPath:
    """Build path with 90-degree segments only (no diagonals)."""
    path = QPainterPath()
    path.moveTo(x1, y1)
    mid_y = (y1 + y2) / 2
    if abs(x2 - x1) < 4:
        path.lineTo(x1, y2)
    else:
        path.lineTo(x1, mid_y)
        path.lineTo(x2, mid_y)
        path.lineTo(x2, y2)
    return path


def _rounded_rect_path(rect: QRectF, radius: float) -> QPainterPath:
    """Create a rounded rectangle path."""
    path = QPainterPath()
    r = min(radius, rect.width() / 2, rect.height() / 2)
    path.addRoundedRect(rect, r, r)
    return path


class GrafcetStepGraphicsItem(QGraphicsObject):
    """Clickable step with rounded corners, 3D gradient, step id and actions."""
    step_clicked = Signal(str)

    def __init__(self, step_id: str, actions: str, base_color: QColor, highlighted: bool = False):
        super().__init__()
        self._step_id = step_id
        self._actions = (actions or "").strip()
        self._base_color = base_color
        self._highlighted = highlighted
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, False)

    def set_highlighted(self, on: bool):
        if self._highlighted != on:
            self._highlighted = on
            self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, STEP_WIDTH, STEP_SIZE)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        color = QColor(GRAFCET_HIGHLIGHT) if self._highlighted else self._base_color

        # 3D gradient: lighter top, darker bottom
        grad = QLinearGradient(0, 0, 0, rect.height())
        grad.setColorAt(0, color.lighter(130))
        grad.setColorAt(0.4, color)
        grad.setColorAt(1, color.darker(130))

        path = _rounded_rect_path(rect, CORNER_RADIUS)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillPath(path, QBrush(grad))

        # Border with slight 3D effect (darker on bottom-right)
        border_color = QColor(GRAFCET_BORDER) if not self._highlighted else QColor("#E65100")
        painter.setPen(QPen(border_color, 2))
        painter.drawPath(path)

        # Step ID (bold, centered top)
        painter.setPen(QColor(GRAFCET_TEXT))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 4, STEP_WIDTH, 22), Qt.AlignmentFlag.AlignCenter, self._step_id)

        # Actions (smaller, wrapped below)
        if self._actions:
            actions_short = self._actions[:25] + "…" if len(self._actions) > 25 else self._actions
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor("#E0E0E0"))
            painter.drawText(QRectF(2, 26, STEP_WIDTH - 4, STEP_SIZE - 30),
                            Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, actions_short)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.step_clicked.emit(self._step_id)
        super().mousePressEvent(event)


class GrafcetTransitionBar(QGraphicsObject):
    """Horizontal bar showing transition condition between steps."""
    transition_clicked = Signal(str)

    def __init__(self, transition_text: str, width: float, step_id: str):
        super().__init__()
        self._text = (transition_text or "").strip()
        self._width = max(width, 40)
        self._step_id = step_id
        self._highlighted = False
        self.setAcceptHoverEvents(True)

    def set_highlighted(self, on: bool):
        if self._highlighted != on:
            self._highlighted = on
            self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, TRANSITION_BAR_H)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        path = _rounded_rect_path(rect, 4)
        color = QColor(GRAFCET_TRANSITION_BG)
        if self._highlighted:
            color = QColor("#546E7A")
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillPath(path, QBrush(color))
        painter.setPen(QPen(QColor(GRAFCET_TRANSITION_BORDER), 1))
        painter.drawPath(path)
        painter.setPen(QColor("#B0BEC5"))
        painter.setFont(QFont("Segoe UI", 8))
        text = self._text[:20] + "…" if len(self._text) > 20 else self._text
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text or "—")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.transition_clicked.emit(self._step_id)
        super().mousePressEvent(event)


class GrafcetCanvas(QGraphicsView):
    """Canvas: vertical flow, orthogonal lines, rounded 3D steps, transitions, actions."""

    step_clicked = Signal(str)  # Emitted when step or its transition is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.setMinimumSize(300, 400)
        self._step_color = QColor(GRAFCET_BG)
        self._line_color = QColor(GRAFCET_LINE)
        self._highlighted_step_id: str | None = None
        self._step_items: dict[str, GrafcetStepGraphicsItem] = {}
        self._transition_items: dict[str, GrafcetTransitionBar] = {}

    def set_step_color(self, color: QColor):
        self._step_color = color

    def set_highlighted_step(self, step_id: str | None):
        """Highlight a step (and its transition) in the canvas."""
        if self._highlighted_step_id == step_id:
            return
        old_id = self._highlighted_step_id
        self._highlighted_step_id = step_id
        if old_id and old_id in self._step_items:
            self._step_items[old_id].set_highlighted(False)
        if old_id and old_id in self._transition_items:
            self._transition_items[old_id].set_highlighted(False)
        if step_id and step_id in self._step_items:
            self._step_items[step_id].set_highlighted(True)
        if step_id and step_id in self._transition_items:
            self._transition_items[step_id].set_highlighted(True)

    def rebuild(self, model: GrafcetModel):
        """Vertical layout: steps with rounded 3D style, transition bars, actions. Orthogonal lines."""
        scene = self.scene()
        scene.clear()
        self._step_items.clear()
        self._transition_items.clear()
        if not model.steps:
            return

        # Vertical layout: level by graph, siblings horizontal
        step_map = {s.id: s for s in model.steps}
        step_ids = [s.id for s in model.steps]
        levels: dict[str, int] = {}
        level_siblings: dict[int, list[str]] = {}

        def assign_level(sid: str, lvl: int):
            if sid in levels and levels[sid] <= lvl:
                return
            levels[sid] = lvl
            if lvl not in level_siblings:
                level_siblings[lvl] = []
            if sid not in level_siblings[lvl]:
                level_siblings[lvl].append(sid)
            s = step_map.get(sid)
            if s and s.next_steps:
                for nid in s.next_steps:
                    if nid in step_map:
                        assign_level(nid, lvl + 1)
            elif s and not s.next_steps:
                idx = step_ids.index(sid) if sid in step_ids else -1
                for nid in step_ids[idx + 1:]:
                    if nid not in levels:
                        assign_level(nid, lvl + 1)
                        break

        if model.steps:
            assign_level(model.steps[0].id, 0)
        for sid in step_ids:
            if sid not in levels:
                assign_level(sid, max(levels.values(), default=0) + 1)

        # Positions: vertical = level (with slot for step + transition), horizontal = centered
        max_level = max(levels.values()) if levels else 0
        pos: dict[str, QPointF] = {}
        trans_pos: dict[str, QPointF] = {}
        for lvl in range(max_level + 1):
            sids = level_siblings.get(lvl, [])
            n = len(sids)
            if n == 0:
                continue
            total_w = n * STEP_WIDTH + (n - 1) * GAP_H
            start_x = -total_w / 2 + STEP_WIDTH / 2 + GAP_H / 2
            for i, sid in enumerate(sids):
                x = start_x + i * (STEP_WIDTH + GAP_H)
                y = 50 + lvl * SLOT_HEIGHT
                pos[sid] = QPointF(x, y)
                trans_pos[sid] = QPointF(x + (STEP_WIDTH - 60) / 2, y + STEP_SIZE + 4)

        items: dict[str, GrafcetStepGraphicsItem] = {}
        for sid, pt in pos.items():
            s = step_map.get(sid)
            if not s:
                continue
            step_item = GrafcetStepGraphicsItem(
                sid, getattr(s, "actions", "") or "", self._step_color,
                highlighted=(sid == self._highlighted_step_id)
            )
            step_item.setPos(pt)
            step_item.setZValue(2)
            step_item.step_clicked.connect(self._on_step_clicked)
            scene.addItem(step_item)
            items[sid] = step_item
            self._step_items[sid] = step_item

            # Transition bar below step
            tpt = trans_pos.get(sid)
            if tpt is not None:
                trans_bar = GrafcetTransitionBar(s.transition, 60, sid)
                trans_bar.setPos(tpt)
                trans_bar.setZValue(2)
                trans_bar.transition_clicked.connect(self._on_step_clicked)
                scene.addItem(trans_bar)
                self._transition_items[sid] = trans_bar

        # Transition lines: normal (down/side) or jump/goto (to upper step)
        line_offset = STEP_SIZE + TRANSITION_BAR_H + 4
        jump_down = 50  # pixels down for jump arrow
        for s in model.steps:
            if not s.next_steps:
                continue
            src_item = items.get(s.id)
            if not src_item:
                continue
            src_level = levels.get(s.id, 0)
            src_pt = src_item.scenePos()
            src_cx = src_pt.x() + STEP_WIDTH / 2
            src_bottom = src_pt.y() + line_offset

            for nid in s.next_steps:
                dst_item = items.get(nid)
                if not dst_item:
                    continue
                dst_level = levels.get(nid, 0)
                dst_pt = dst_item.scenePos()
                dst_cx = dst_pt.x() + STEP_WIDTH / 2
                dst_top = dst_pt.y()

                # Jump/goto: destination is above (lower level) or same level but different column
                is_jump = dst_level < src_level or (dst_level == src_level and abs(dst_cx - src_cx) > 4)

                if is_jump:
                    # Line down, arrow, label with target step
                    path = QPainterPath()
                    path.moveTo(src_cx, src_bottom)
                    path.lineTo(src_cx, src_bottom + jump_down)
                    path_item = QGraphicsPathItem(path)
                    path_item.setPen(QPen(self._line_color, 2))
                    path_item.setZValue(0)
                    scene.addItem(path_item)
                    # Arrowhead (small triangle pointing down)
                    arrow_y = src_bottom + jump_down
                    arrow_path = QPainterPath()
                    arrow_path.moveTo(src_cx, arrow_y + 10)
                    arrow_path.lineTo(src_cx - 6, arrow_y - 4)
                    arrow_path.lineTo(src_cx + 6, arrow_y - 4)
                    arrow_path.closeSubpath()
                    arrow_item = QGraphicsPathItem(arrow_path)
                    arrow_item.setPen(QPen(self._line_color, 2))
                    arrow_item.setBrush(QBrush(self._line_color))
                    arrow_item.setZValue(0)
                    scene.addItem(arrow_item)
                    # Label: "→ S20" below the arrow
                    label = QGraphicsTextItem(f"→ {nid}")
                    label.setDefaultTextColor(QColor(self._line_color))
                    label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    br = label.boundingRect()
                    label.setPos(src_cx - br.width() / 2, arrow_y + 4)
                    label.setZValue(1)
                    scene.addItem(label)
                else:
                    # Normal: orthogonal line to step below
                    path = _orthogonal_line_path(src_cx, src_bottom, dst_cx, dst_top)
                    path_item = QGraphicsPathItem(path)
                    path_item.setPen(QPen(self._line_color, 2))
                    path_item.setZValue(0)
                    scene.addItem(path_item)

        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))

    def _on_step_clicked(self, step_id: str):
        self.step_clicked.emit(step_id)


class GrafcetGeneratorView(QWidget):
    """Main Grafcet view: NLP prompt, table, canvas."""

    model_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = GrafcetModel()
        self._step_counter = 0
        self._setup_ui()

    def _next_step_id(self) -> str:
        self._step_counter += 1
        return f"S{self._step_counter * 10}"

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # NLP prompt area
        prompt_grp = QFrame()
        prompt_grp.setStyleSheet("QFrame { border-bottom: 1px solid #3e3e42; }")
        prompt_layout = QVBoxLayout(prompt_grp)
        prompt_layout.addWidget(QLabel("NLP prompt (Gemini API)"))
        row = QHBoxLayout()
        self._prompt_edit = QLineEdit()
        self._prompt_edit.setPlaceholderText(
            "e.g. 3 steps: init, run, done. Init goes to run when ready. Run goes to done when finished."
        )
        self._prompt_edit.setStyleSheet("background: #252526; color: #d4d4d4; padding: 8px;")
        row.addWidget(self._prompt_edit)
        self._gen_btn = QPushButton("Generate")
        self._gen_btn.clicked.connect(self._on_generate)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel_generate)
        self._cancel_btn.setVisible(False)
        row.addWidget(self._gen_btn)
        row.addWidget(self._cancel_btn)
        prompt_layout.addLayout(row)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self._status_label.setWordWrap(True)
        prompt_layout.addWidget(self._status_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate
        self._progress_bar.setVisible(False)
        prompt_layout.addWidget(self._progress_bar)
        layout.addWidget(prompt_grp)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: table
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Steps & Transitions"))
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Step", "Name", "Transition", "Next Step(s)", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setRowCount(0)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Step")
        add_btn.clicked.connect(self._add_step)
        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(self._move_up)
        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(self._move_down)
        del_btn = QPushButton("Remove")
        del_btn.clicked.connect(self._remove_step)
        export_btn = QPushButton("Export JSON")
        export_btn.clicked.connect(self._export_json)
        import_btn = QPushButton("Import JSON")
        import_btn.clicked.connect(self._import_json)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(up_btn)
        btn_layout.addWidget(down_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(import_btn)
        left_layout.addLayout(btn_layout)
        splitter.addWidget(left)

        # Right: canvas + color
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Grafcet Preview"))

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Step color:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(32, 24)
        self._color_btn.setStyleSheet(f"background-color: {GRAFCET_BG}; border: 1px solid #333;")
        self._color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self._color_btn)
        color_layout.addStretch()
        right_layout.addLayout(color_layout)

        self._canvas = GrafcetCanvas()
        self._canvas.step_clicked.connect(self._on_canvas_step_clicked)
        right_layout.addWidget(self._canvas)
        splitter.addWidget(right)
        splitter.setSizes([400, 500])
        layout.addWidget(splitter)

        # Preview
        preview_grp = QFrame()
        preview_grp.setStyleSheet("QFrame { border-top: 1px solid #3e3e42; }")
        preview_layout = QVBoxLayout(preview_grp)
        preview_layout.addWidget(QLabel("Generated Stepper Preview"))
        self._preview_edit = QPlainTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setMaximumHeight(120)
        self._preview_edit.setStyleSheet("background: #252526; color: #d4d4d4;")
        preview_layout.addWidget(self._preview_edit)
        layout.addWidget(preview_grp)

        self._apply_styles()
        self.model_changed.connect(self._update_preview)
        self._update_preview()

    def _on_generate(self):
        prompt = self._prompt_edit.text().strip()
        if not prompt:
            QMessageBox.information(self, "Prompt", "Enter a short description of the GRAFCET steps.")
            return
        if getattr(self, "_gen_worker", None) and self._gen_worker.isRunning():
            return
        self._gen_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._status_label.setText("Starting...")
        self._gen_worker = _GenerateWorker(prompt)
        self._gen_worker.status_updated.connect(self._on_gen_status)
        self._gen_worker.finished.connect(self._on_gen_finished)
        self._gen_worker.start()

    def _on_gen_status(self, msg: str):
        self._status_label.setText(msg)

    def _on_cancel_generate(self):
        if getattr(self, "_gen_worker", None) and self._gen_worker.isRunning():
            self._gen_worker.terminate()
            self._gen_worker.wait(2000)
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        self._status_label.setText("Cancelled.")

    def _on_gen_finished(self, model, err: str):
        self._gen_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        if err:
            self._status_label.setText(f"Error: {err[:80]}...")
            QMessageBox.warning(self, "Generation", err)
            return
        if model is None:
            self._status_label.setText("Error: No model returned")
            return
        self._model = model
        self._step_counter = max((int(s.id[1:]) for s in model.steps if s.id[1:].isdigit()), default=0) // 10
        self._refresh_table()
        self._canvas.rebuild(self._model)
        self.model_changed.emit()
        self._status_label.setText("Done.")

    def _update_preview(self):
        state_const, stepper = self.get_generated_scl()
        text = "// STATE_CONSTANTS:\n" + state_const + "\n\n// STEPPER_LOGIC:\n" + stepper
        self._preview_edit.setPlainText(text)

    def _apply_styles(self):
        self.setStyleSheet("""
            QTableWidget { background: #252526; color: #d4d4d4; gridline-color: #3e3e42; }
            QTableWidget::item:selected { background: #FFB74D; color: #1e1e1e; }
            QHeaderView::section { background: #2d2d30; color: #cccccc; padding: 6px; }
            QPushButton { background: #0e639c; color: white; border: none; padding: 6px 12px; }
            QPushButton:hover { background: #1177bb; }
            QPushButton:pressed { background: #094771; }
            QLabel { color: #cccccc; }
            QLineEdit { color: #d4d4d4; }
        """)

    def _on_canvas_step_clicked(self, step_id: str):
        """When a step is clicked in the canvas, highlight it and select the corresponding table row."""
        self._canvas.set_highlighted_step(step_id)
        for i, s in enumerate(self._model.steps):
            if s.id == step_id:
                self._table.blockSignals(True)
                self._table.selectRow(i)
                self._table.blockSignals(False)
                break

    def _on_table_selection_changed(self):
        """When table row selection changes, highlight the corresponding step in the canvas."""
        row = self._table.currentRow()
        if 0 <= row < len(self._model.steps):
            step_id = self._model.steps[row].id
            self._canvas.set_highlighted_step(step_id)
        else:
            self._canvas.set_highlighted_step(None)

    def _pick_color(self):
        color = QColorDialog.getColor(self._canvas._step_color, self, "Step color")
        if color.isValid():
            self._canvas.set_step_color(color)
            self._color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #333;")
            self._canvas.rebuild(self._model)

    def _add_step(self):
        step_id = self._next_step_id()
        value = int(step_id[1:]) if step_id[1:].isdigit() else (len(self._model.steps) + 1) * 10
        step = GrafcetStep(id=step_id, name=f"STEP_{step_id}", value=value, order=len(self._model.steps), actions="")
        self._model.add_step(step)
        self._refresh_table()
        self._canvas.rebuild(self._model)
        self.model_changed.emit()

    def _update_table_from_model(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._model.steps))
        for i, s in enumerate(self._model.steps):
            self._table.setItem(i, 0, QTableWidgetItem(s.id))
            self._table.setItem(i, 1, QTableWidgetItem(s.name))
            self._table.setItem(i, 2, QTableWidgetItem(s.transition))
            self._table.setItem(i, 3, QTableWidgetItem(", ".join(s.next_steps)))
            self._table.setItem(i, 4, QTableWidgetItem(getattr(s, "actions", "") or ""))
        self._table.blockSignals(False)

    def _refresh_table(self):
        self._update_table_from_model()
        self._canvas.rebuild(self._model)

    def _on_cell_changed(self, row: int, col: int):
        if row >= len(self._model.steps):
            return
        s = self._model.steps[row]
        if col == 0:
            s.id = self._table.item(row, col).text() or s.id
        elif col == 1:
            s.name = self._table.item(row, col).text() or s.name
        elif col == 2:
            s.transition = self._table.item(row, col).text()
        elif col == 3:
            text = self._table.item(row, col).text()
            s.next_steps = [x.strip() for x in text.split(",") if x.strip()]
        elif col == 4:
            s.actions = self._table.item(row, col).text()
        self._canvas.rebuild(self._model)
        self.model_changed.emit()

    def _move_up(self):
        row = self._table.currentRow()
        if row >= 0 and row < len(self._model.steps):
            s = self._model.steps[row]
            if self._model.move_step_up(s.id):
                self._refresh_table()
                self._table.selectRow(row - 1)
                self.model_changed.emit()

    def _move_down(self):
        row = self._table.currentRow()
        if row >= 0 and row < len(self._model.steps):
            s = self._model.steps[row]
            if self._model.move_step_down(s.id):
                self._refresh_table()
                self._table.selectRow(row + 1)
                self.model_changed.emit()

    def _remove_step(self):
        row = self._table.currentRow()
        if row >= 0 and row < len(self._model.steps):
            s = self._model.steps[row]
            self._model.remove_step(s.id)
            self._refresh_table()
            self.model_changed.emit()

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Grafcet", "", "JSON (*.json)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._model.to_json())
                QMessageBox.information(self, "Export", f"Saved to {path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Error", str(e))

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Grafcet", "", "JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._model = GrafcetModel.from_json(f.read())
                self._step_counter = max((int(s.id[1:]) for s in self._model.steps if s.id[1:].isdigit()), default=0) // 10
                self._refresh_table()
                self.model_changed.emit()
                QMessageBox.information(self, "Import", f"Loaded from {path}")
            except Exception as e:
                QMessageBox.warning(self, "Import Error", str(e))

    def get_model(self) -> GrafcetModel:
        return self._model

    def get_generated_scl(self) -> tuple[str, str]:
        return generate_state_constants(self._model), generate_stepper_logic(self._model)
