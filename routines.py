"""
Routines window: Markdown viewer and editor.
Works against a folder of markdown files. Read-only view by default, edit mode for raw markdown.
"""

from datetime import datetime
from pathlib import Path

import markdown
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QPlainTextEdit,
    QLabel,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QStackedWidget,
    QFrame,
    QColorDialog,
    QMenu,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QObject, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QImage, QPixmap, QPainter, QFontMetrics

from config import Styles, AppConfig
from utils import (
    get_routines_folder,
    get_routines_default_file,
    save_routines_default_file,
    get_routines_colors,
    save_routine_color,
    get_routines_zoom,
    save_routine_zoom,
)


class _ViewportZoomFilter(QObject):
    """Forwards Ctrl+wheel from viewport: either callback(delta) or target.zoomIn/Out."""

    def __init__(self, on_zoom_callback=None, zoom_target=None, parent=None):
        super().__init__(parent)
        self._on_zoom = on_zoom_callback
        self._target = zoom_target

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if self._on_zoom:
                    self._on_zoom(1 if delta > 0 else -1)
                elif self._target:
                    if delta > 0:
                        self._target.zoomIn(2)
                    else:
                        self._target.zoomOut(2)
                return True
        return False


class _ZoomableTextEdit(QTextEdit):
    """QTextEdit that zooms with Ctrl+wheel (viewport receives events)."""

    def __init__(self, on_zoom_callback, parent=None):
        super().__init__(parent)
        self.viewport().installEventFilter(_ViewportZoomFilter(on_zoom_callback=on_zoom_callback, parent=self))


class _ZoomablePlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit that zooms with Ctrl+wheel (viewport receives events)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewport().installEventFilter(_ViewportZoomFilter(zoom_target=self, parent=self))


def _luminance(hex_color: str) -> float:
    """Return luminance 0-1. Use black text if > 0.5, white if <= 0.5."""
    c = hex_color.lstrip("#")
    if len(c) != 6:
        return 0.5
    r, g, b = int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255
    return 0.299 * r + 0.587 * g + 0.114 * b


class RoutineChip(QFrame):
    """A routine button styled like a browser tab. Shrinks with ellipsis when space is tight."""

    MAX_WIDTH = 150
    MIN_WIDTH = 40

    def __init__(self, display_name: str, path: Path, color: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._color = color
        self._full_name = display_name
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._main_btn = QPushButton(display_name)
        self._main_btn.setCheckable(True)
        self._main_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._main_btn.setToolTip(display_name)
        layout.addWidget(self._main_btn)
        self._apply_color(color)

    def _apply_color(self, color: str) -> None:
        self._color = color
        text_color = "#000000" if _luminance(color) > 0.5 else "#ffffff"
        self._main_btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: {text_color}; border: none; "
            f"padding: 4px 8px; font-size: 10pt; text-align: left; "
            f"border-top-left-radius: 6px; border-top-right-radius: 6px; "
            f"border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }} "
            f"QPushButton:checked {{ background-color: #ffffff; color: #323130; "
            f"border-bottom-left-radius: 0; border-bottom-right-radius: 0; border: 1px solid #d1d1d1; "
            f"border-top: 1px solid #d1d1d1; border-left: 1px solid #d1d1d1; border-right: 1px solid #d1d1d1; border-bottom: none; }}"
        )
        self._update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_elided_text)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._update_elided_text)

    def _update_elided_text(self) -> None:
        w = self._main_btn.width() - 16  # padding
        if w <= 0:
            return
        fm = QFontMetrics(self._main_btn.font())
        elided = fm.elidedText(self._full_name, Qt.TextElideMode.ElideRight, w)
        self._main_btn.setText(elided)

    @property
    def main_btn(self) -> QPushButton:
        return self._main_btn

    @property
    def path(self) -> Path:
        return self._path


class RoutinesWindow(QMainWindow):
    """
    Markdown viewer and editor. All .md files in the routines folder become buttons.
    Read-only view by default; Edit button switches to raw markdown. Auto-save and manual save.
    """

    def __init__(self, parent=None, log_fn=None):
        super().__init__(parent)
        self._log_fn = log_fn or (lambda msg, level="info": None)
        self.setWindowTitle("Routines")
        self.setMinimumSize(700, 500)
        self.resize(900, 600)

        self._folder = Path(get_routines_folder()) if get_routines_folder() else None
        self._current_file: Path | None = None
        self._dirty = False
        self._view_zoom = 100
        self._edit_font_pt = 9
        self._last_save_time: datetime | None = None
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._do_auto_save)
        self._last_save_update_timer = QTimer(self)
        self._last_save_update_timer.start(1000)  # every second
        self._last_save_update_timer.timeout.connect(self._update_last_save_text)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(0)

        # --- Toolbar: zoom (left) | pen + Default (right) ---
        zoom_icon_size = 16
        m, w = 4, 1

        def _make_plus_icon() -> QIcon:
            img = QImage(zoom_icon_size, zoom_icon_size, QImage.Format.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#333333"))
            painter.drawRect(7, m, w, zoom_icon_size - 2 * m)
            painter.drawRect(m, 7, zoom_icon_size - 2 * m, w)
            painter.end()
            return QIcon(QPixmap.fromImage(img))

        def _make_minus_icon() -> QIcon:
            img = QImage(zoom_icon_size, zoom_icon_size, QImage.Format.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#333333"))
            painter.drawRect(m, 7, zoom_icon_size - 2 * m, w)
            painter.end()
            return QIcon(QPixmap.fromImage(img))

        icon_plus = _make_plus_icon()
        icon_minus = _make_minus_icon()
        zoom_btn_style = (
            "QPushButton { background-color: transparent; border: 1px solid transparent; border-radius: 4px; } "
            "QPushButton:hover { background-color: #e8f0fe; border: 1px solid #0066cc; } "
            "QPushButton:pressed { background-color: #d0e0fc; }"
        )
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("QFrame { background-color: #fafafa; border-radius: 4px; }")
        btn_row = QHBoxLayout(toolbar_frame)
        btn_row.setContentsMargins(4, 4, 4, 4)
        btn_row.setSpacing(4)
        btn_zoom_in = QPushButton()
        btn_zoom_in.setIcon(icon_plus)
        btn_zoom_in.setIconSize(QSize(zoom_icon_size, zoom_icon_size))
        btn_zoom_in.setFixedSize(24, 24)
        btn_zoom_in.setToolTip("Zoom in")
        btn_zoom_in.setStyleSheet(zoom_btn_style)
        btn_zoom_in.clicked.connect(self._zoom_in)
        btn_row.addWidget(btn_zoom_in)
        btn_zoom_out = QPushButton()
        btn_zoom_out.setIcon(icon_minus)
        btn_zoom_out.setIconSize(QSize(zoom_icon_size, zoom_icon_size))
        btn_zoom_out.setFixedSize(24, 24)
        btn_zoom_out.setToolTip("Zoom out")
        btn_zoom_out.setStyleSheet(zoom_btn_style)
        btn_zoom_out.clicked.connect(self._zoom_out)
        btn_row.addWidget(btn_zoom_out)
        btn_row.addStretch()
        self._btn_pen = QPushButton("\u270E")  # ✎ pencil
        self._btn_pen.setToolTip("Routine options (color, rename, delete)")
        self._btn_pen.setFixedSize(24, 24)
        self._btn_pen.setStyleSheet(
            "QPushButton { background-color: transparent; border: none; font-size: 12pt; padding: 0; color: #333333; } "
            "QPushButton:hover { background-color: #e8f0fe; border-radius: 4px; color: #333333; } "
            "QPushButton:disabled { color: #999; }"
        )
        self._btn_pen.clicked.connect(self._show_current_routine_menu)
        btn_row.addWidget(self._btn_pen)
        self._btn_default = QPushButton("Default")
        self._btn_default.setStyleSheet("QPushButton { background-color: #9e9e9e; color: white; padding: 4px 8px; }")
        self._btn_default.clicked.connect(self._set_default)
        btn_row.addWidget(self._btn_default)
        layout.addWidget(toolbar_frame)

        # --- Routines tabs (no scroll: buttons shrink and elide text) ---
        self._routines_widget = QWidget()
        self._routines_widget.setMaximumHeight(48)
        self._routines_layout = QHBoxLayout(self._routines_widget)
        self._routines_layout.setContentsMargins(4, 4, 4, 0)
        self._routines_layout.setSpacing(2)
        layout.addWidget(self._routines_widget)

        # --- Canvas frame: markdown view/edit ---
        canvas_frame = QFrame()
        canvas_frame.setStyleSheet(
            "QFrame { border: 1px solid #d1d1d1; border-top: none; "
            "border-radius: 8px; border-top-left-radius: 0; border-top-right-radius: 0; background: white; }"
        )
        canvas_layout = QVBoxLayout(canvas_frame)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._view_widget = _ZoomableTextEdit(self._on_view_zoom)
        self._view_widget.setReadOnly(True)
        self._view_widget.setPlaceholderText("Select a routine or create a new one.")
        self._view_widget.setStyleSheet("border: none; border-radius: 8px; padding: 12px;")
        self._view_widget.setToolTip("Ctrl+scroll to zoom")
        self._stack.addWidget(self._view_widget)

        self._edit_widget = _ZoomablePlainTextEdit()
        self._edit_widget.setPlaceholderText("Edit markdown...")
        self._edit_widget.setFont(QFont("Consolas", 9))
        self._edit_widget.setStyleSheet("border: none; border-radius: 8px; padding: 12px;")
        self._edit_widget.setToolTip("Ctrl+scroll to zoom")
        self._edit_widget.textChanged.connect(self._on_edit_changed)
        self._stack.addWidget(self._edit_widget)

        self._stack.setCurrentWidget(self._view_widget)
        canvas_layout.addWidget(self._stack)

        layout.addWidget(canvas_frame)

        # --- Bottom: View, Edit (left) | Save (right) ---
        bottom = QHBoxLayout()
        self._btn_view = QPushButton("View")
        self._btn_view.clicked.connect(self._switch_to_view)
        self._btn_view.setEnabled(False)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.clicked.connect(self._switch_to_edit)
        self._btn_save = QPushButton("Save")
        self._btn_save.clicked.connect(self._manual_save)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888;")
        bottom.addWidget(self._btn_view)
        bottom.addWidget(self._btn_edit)
        bottom.addStretch()
        bottom.addWidget(self._btn_save)
        bottom.addWidget(self._status_label)
        layout.addLayout(bottom)

        self._chip_widgets: dict[str, RoutineChip] = {}
        self._btn_save.setVisible(False)  # hidden when viewing
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Refresh routine chips and content."""
        if not self._folder or not self._folder.exists():
            self._chip_widgets.clear()
            self._clear_buttons()
            self._update_default_button_style()
            return

        # Rebuild routine chips (tab style) and + button
        self._clear_buttons()
        files = sorted(self._folder.glob("*.md"), key=lambda p: p.name.lower())
        default = get_routines_default_file()
        colors = get_routines_colors()

        for f in files:
            name = f.name
            display_name = f.stem
            color = colors.get(name, "#9e9e9e")
            chip = RoutineChip(display_name, f, color, self)
            chip._apply_color(color)
            if name == (self._current_file.name if self._current_file else None):
                chip.main_btn.setChecked(True)
            chip.main_btn.clicked.connect(lambda checked, p=f: self._open_file(p))
            self._routines_layout.addWidget(chip, 1)  # stretch=1: equal width, shrink together
            self._chip_widgets[name] = chip

        # Plus button for new routine, after last routine
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#333333"))
        m = 3
        w = 1
        painter.drawRect(7, m, w, 16 - 2 * m)
        painter.drawRect(m, 7, 16 - 2 * m, w)
        painter.end()
        plus_icon = QIcon(pix)

        btn_plus = QPushButton()
        btn_plus.setFixedSize(28, 28)
        btn_plus.setIcon(plus_icon)
        btn_plus.setIconSize(pix.size())
        btn_plus.setFlat(True)
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.setStyleSheet(
            "QPushButton { background-color: #e0e0e0; border: none; border-radius: 4px; } "
            "QPushButton:hover { background-color: #e8f0fe; border: 1px solid #0066cc; } "
            "QPushButton:pressed { background-color: #d0e0fc; }"
        )
        btn_plus.clicked.connect(self._new_file)
        self._routines_layout.addWidget(btn_plus, 0)  # no stretch: fixed size

        # Open default on first load if no routine selected
        if not self._current_file and default and (self._folder / default).exists():
            self._open_file(self._folder / default)
        self._update_default_button_style()

    def _clear_buttons(self) -> None:
        """Remove all routine chips and the + button."""
        while self._routines_layout.count() > 0:
            item = self._routines_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chip_widgets.clear()

    def _show_current_routine_menu(self) -> None:
        """Show menu for current routine (from pen button beside Default)."""
        if not self._current_file:
            return
        name = self._current_file.name
        chip = self._chip_widgets.get(name)
        if chip:
            self._show_routine_menu(self._current_file, chip, anchor=self._btn_pen)

    def _show_routine_menu(self, path: Path, chip: RoutineChip, anchor=None) -> None:
        """Show menu: Change color, Rename, Delete."""
        menu = QMenu(self)
        menu.addAction("Change color...").triggered.connect(lambda: self._change_routine_color(path, chip))
        menu.addAction("Rename").triggered.connect(lambda: self._rename_routine(path))
        menu.addAction("Delete").triggered.connect(lambda: self._delete_routine(path))
        btn = anchor or chip.main_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _change_routine_color(self, path: Path, chip: RoutineChip) -> None:
        """Open color dialog and apply to routine chip."""
        colors = get_routines_colors()
        current = colors.get(path.name, "#9e9e9e")
        color = QColorDialog.getColor(QColor(current), self, "Choose color")
        if color.isValid():
            hex_color = color.name()
            save_routine_color(path.name, hex_color)
            chip._apply_color(hex_color)
            self._log(f"Color updated for {path.stem}", "success")

    def _rename_routine(self, path: Path) -> None:
        """Rename routine (from pen menu)."""
        prev = self._current_file
        self._current_file = path
        self._rename_file()
        if not self._current_file:  # rename failed or cancelled
            self._current_file = prev

    def _delete_routine(self, path: Path) -> None:
        """Delete routine (from pen menu)."""
        self._current_file = path
        self._delete_file()

    def _open_file(self, path: Path) -> None:
        """Open markdown file in read-only view."""
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved changes",
                "Save changes before switching?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Save:
                self._do_save()
        self._current_file = path
        self._dirty = False
        self._stack.setCurrentWidget(self._view_widget)
        self._btn_edit.setEnabled(True)
        self._btn_view.setEnabled(False)
        self._edit_widget.blockSignals(True)
        self._edit_widget.clear()
        try:
            text = path.read_text(encoding="utf-8")
            zoom = get_routines_zoom().get(path.name, {})
            self._view_zoom = zoom.get("view", 100)
            self._edit_font_pt = zoom.get("edit", 9)
            self._view_widget.setHtml(self._md_to_html(text))
            self._edit_widget.setPlainText(text)
            self._edit_widget.setFont(QFont("Consolas", self._edit_font_pt))
            doc = self._view_widget.document()
            font = doc.defaultFont()
            base_pt = 11
            font.setPointSize(max(6, min(28, int(base_pt * self._view_zoom / 100))))
            doc.setDefaultFont(font)
        except Exception as e:
            self._view_widget.setPlainText(f"Error loading: {e}")
        self._edit_widget.blockSignals(False)
        self._update_button_checked()
        self._update_default_button_style()
        try:
            self._last_save_time = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            self._last_save_time = None
        self._btn_save.setVisible(False)
        self._update_last_save_text()

    def _update_button_checked(self) -> None:
        """Update which routine chip is checked."""
        current = self._current_file.name if self._current_file else None
        for name, chip in self._chip_widgets.items():
            chip.main_btn.setChecked(name == current)

    def _switch_to_edit(self) -> None:
        """Switch to edit mode."""
        if not self._current_file:
            return
        self._edit_widget.blockSignals(True)
        try:
            raw = self._current_file.read_text(encoding="utf-8")
            self._edit_widget.setPlainText(raw)
            zoom = get_routines_zoom().get(self._current_file.name, {})
            self._edit_font_pt = zoom.get("edit", 9)
            self._edit_widget.setFont(QFont("Consolas", self._edit_font_pt))
        except Exception:
            pass
        self._edit_widget.blockSignals(False)
        self._stack.setCurrentWidget(self._edit_widget)
        self._btn_edit.setEnabled(False)
        self._btn_view.setEnabled(True)
        self._btn_save.setVisible(True)
        self._update_save_button_state()
        self._update_last_save_text()

    def _switch_to_view(self) -> None:
        """Switch to view mode, save if dirty, and refresh from edited content."""
        if not self._current_file:
            return
        if self._dirty:
            self._do_save()
        text = self._edit_widget.toPlainText()
        self._view_widget.setHtml(self._md_to_html(text))
        self._stack.setCurrentWidget(self._view_widget)
        self._btn_edit.setEnabled(True)
        self._btn_view.setEnabled(False)
        self._btn_save.setVisible(False)
        self._dirty = False
        self._auto_save_timer.stop()
        self._update_last_save_text()

    def _on_edit_changed(self) -> None:
        """Track edits and start auto-save timer."""
        self._dirty = True
        self._auto_save_timer.stop()
        self._auto_save_timer.start(2000)  # 2 second debounce
        self._update_save_button_state()
        self._update_last_save_text()

    def _do_auto_save(self) -> None:
        """Perform auto-save."""
        if self._dirty and self._current_file:
            self._do_save()
            self._update_save_button_state()
            self._update_last_save_text()

    def _manual_save(self) -> None:
        """Manual save."""
        if self._dirty and self._current_file:
            self._do_save()
            self._update_save_button_state()
            self._update_last_save_text()
        elif not self._current_file:
            self._new_file()  # Create new if no file open

    def _do_save(self) -> None:
        """Write current content to file."""
        if not self._current_file:
            return
        try:
            self._current_file.write_text(self._edit_widget.toPlainText(), encoding="utf-8")
            self._dirty = False
            self._last_save_time = datetime.now()
            text = self._edit_widget.toPlainText()
            self._view_widget.setHtml(self._md_to_html(text))
            self._log(f"Saved {self._current_file.name}", "success")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def _update_save_button_state(self) -> None:
        """Grey Save button when nothing to save."""
        if self._dirty and self._current_file:
            self._btn_save.setStyleSheet("")
            self._btn_save.setEnabled(True)
        else:
            self._btn_save.setStyleSheet(
                "QPushButton { background-color: #9e9e9e; color: white; }"
            )
            self._btn_save.setEnabled(False)

    def _format_ago(self, dt: datetime) -> str:
        """Format datetime as 'a second ago', '10 seconds ago', etc."""
        delta = datetime.now() - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            return "just now"
        if secs < 60:
            if secs <= 1:
                return "a second ago"
            return f"{secs} seconds ago"
        mins = secs // 60
        if mins == 1:
            return "a minute ago"
        if mins < 60:
            return f"{mins} minutes ago"
        hours = mins // 60
        if hours == 1:
            return "an hour ago"
        if hours < 24:
            return f"{hours} hours ago"
        days = hours // 24
        if days == 1:
            return "a day ago"
        if days < 30:
            return f"{days} days ago"
        return dt.strftime("%Y-%m-%d")

    def _update_last_save_text(self) -> None:
        """Update status label with 'Last save X ago'."""
        if self._last_save_time is not None:
            self._status_label.setText(f"Last save {self._format_ago(self._last_save_time)}")
        else:
            self._status_label.setText("Last save —")

    def _zoom_in(self) -> None:
        """Zoom in (button or Ctrl+scroll)."""
        self._apply_zoom(1)

    def _zoom_out(self) -> None:
        """Zoom out (button or Ctrl+scroll)."""
        self._apply_zoom(-1)

    def _on_view_zoom(self, delta: int) -> None:
        """Zoom callback from Ctrl+scroll in view."""
        self._apply_zoom(delta)

    def _apply_zoom(self, delta: int) -> None:
        """Apply zoom: delta 1 = zoom in, -1 = zoom out."""
        in_edit = self._stack.currentWidget() is self._edit_widget
        if in_edit:
            step = 2
            self._edit_font_pt = max(6, min(28, self._edit_font_pt + (step if delta > 0 else -step)))
            self._edit_widget.setFont(QFont("Consolas", self._edit_font_pt))
        else:
            self._view_zoom = max(50, min(200, self._view_zoom + delta * 10))
            text = self._edit_widget.toPlainText()
            self._view_widget.setHtml(self._md_to_html(text))
            doc = self._view_widget.document()
            font = doc.defaultFont()
            base_pt = 11
            font.setPointSize(max(6, min(28, int(base_pt * self._view_zoom / 100))))
            doc.setDefaultFont(font)
        if self._current_file:
            save_routine_zoom(self._current_file.name, self._view_zoom, self._edit_font_pt)

    def _md_to_html(self, text: str) -> str:
        """Convert markdown to HTML for display."""
        if not text.strip():
            return "<p></p>"
        text = self._normalize_markdown_table(text)
        try:
            html = markdown.markdown(text, extensions=["fenced_code", "tables"])
            table_css = (
                "table { border-collapse: collapse; width: 100%; margin: 1em 0; } "
                "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; } "
                "th { background-color: #f0f0f0; font-weight: 600; } "
            )
            zoom_style = f"font-size: {self._view_zoom}%;" if self._view_zoom != 100 else ""
            return (
                f'<div style="font-family: sans-serif; line-height: 1.5; {zoom_style}">'
                f'<style>{table_css}</style>{html}</div>'
            )
        except Exception:
            return f"<pre>{text}</pre>"

    def _parse_table_cells(self, line: str) -> list[str]:
        """Parse pipe row into cells. |A|B|C| -> [A,B,C], |A|B|C -> [A,B,C]."""
        line = line.strip()
        if not line.startswith("|"):
            return []
        parts = line.split("|")
        # Drop leading empty (from |) and trailing empty (from trailing |)
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
        return [p.strip() for p in parts]

    def _normalize_markdown_table(self, text: str) -> str:
        """Fix table format for python-markdown: separator and all rows must match header column count."""
        lines = text.split("\n")
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("|") and i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                header_cells = self._parse_table_cells(line)
                header_cols = len(header_cells)
                if header_cols > 0 and next_stripped.startswith("|") and "-" in next_line:
                    # This is a table: header + separator
                    sep_cells = self._parse_table_cells(next_line)
                    sep_cols = len(sep_cells)
                    # Fix separator to match header
                    sep_line = "| " + " | ".join(["---"] * header_cols) + " |"
                    result.append("| " + " | ".join(header_cells) + " |")
                    result.append(sep_line)
                    i += 2
                    # Normalize all data rows until blank or non-table
                    while i < len(lines):
                        row = lines[i]
                        row_stripped = row.strip()
                        if not row_stripped:
                            result.append(row)
                            i += 1
                            break
                        if not row_stripped.startswith("|"):
                            result.append(row)
                            i += 1
                            break
                        cells = self._parse_table_cells(row)
                        while len(cells) < header_cols:
                            cells.append("")
                        cells = cells[:header_cols]
                        result.append("| " + " | ".join(cells) + " |")
                        i += 1
                    continue
            result.append(line)
            i += 1
        return "\n".join(result)

    def _new_file(self) -> None:
        """Create new markdown file."""
        if not self._folder or not self._folder.exists():
            QMessageBox.warning(self, "No folder", "Set Routines folder in Settings first.")
            return
        name, ok = QInputDialog.getText(self, "New Routine", "Name (e.g. notes):", text="untitled")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".md"):
            name += ".md"
        path = self._folder / name
        if path.exists():
            QMessageBox.warning(self, "Exists", f"{name} already exists.")
            return
        try:
            path.write_text("", encoding="utf-8")
            self._refresh_ui()
            self._open_file(path)
            self._last_save_time = None  # new file, not saved yet
            self._update_last_save_text()
            self._switch_to_edit()
            self._log(f"Created {name.removesuffix('.md')}", "success")
        except Exception as e:
            QMessageBox.warning(self, "Create failed", str(e))

    def _rename_file(self) -> None:
        """Rename current routine."""
        if not self._current_file:
            QMessageBox.information(self, "Rename", "Select a routine first.")
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:",
            text=self._current_file.stem
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if not new_name.endswith(".md"):
            new_name += ".md"
        new_path = self._folder / new_name
        if new_path.exists():
            QMessageBox.warning(self, "Exists", f"{new_name} already exists.")
            return
        try:
            old_name = self._current_file.name
            self._current_file.rename(new_path)
            was_default = get_routines_default_file() == old_name
            if was_default:
                save_routines_default_file(new_name)
            # Migrate color to new filename
            colors = get_routines_colors()
            if old_name in colors:
                save_routine_color(new_name, colors[old_name])
                save_routine_color(old_name, "")  # remove old
            self._current_file = new_path
            self._refresh_ui()
            self._log(f"Renamed to {new_name.removesuffix('.md')}", "success")
        except Exception as e:
            QMessageBox.warning(self, "Rename failed", str(e))

    def _delete_file(self) -> None:
        """Delete current routine."""
        if not self._current_file:
            QMessageBox.information(self, "Delete", "Select a routine first.")
            return
        if QMessageBox.question(
            self, "Delete",
            f"Delete {self._current_file.stem}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._current_file.unlink()
            if get_routines_default_file() == self._current_file.name:
                save_routines_default_file("")
            self._current_file = None
            self._last_save_time = None
            self._view_widget.clear()
            self._edit_widget.clear()
            self._refresh_ui()
            self._update_last_save_text()
            self._log("Routine deleted.", "success")
        except Exception as e:
            QMessageBox.warning(self, "Delete failed", str(e))

    def _set_default(self) -> None:
        """Set current routine as default (opens on app start)."""
        if not self._current_file:
            QMessageBox.information(self, "Default", "Select a routine first.")
            return
        save_routines_default_file(self._current_file.name)
        self._update_default_button_style()
        self._log(f"Default set to {self._current_file.stem}", "success")

    def _update_default_button_style(self) -> None:
        """Update Default button: gray normally, green when current is default."""
        is_default = (
            self._current_file
            and get_routines_default_file() == self._current_file.name
        )
        if is_default:
            self._btn_default.setStyleSheet(
                "QPushButton { background-color: #2e7d32; color: white; padding: 4px 8px; }"
            )
        else:
            self._btn_default.setStyleSheet(
                "QPushButton { background-color: #9e9e9e; color: white; padding: 4px 8px; }"
            )
        self._btn_pen.setEnabled(self._current_file is not None)

    def _set_status(self, msg: str) -> None:
        """Update status label."""
        self._status_label.setText(msg)

    def _log(self, msg: str, level: str = "info") -> None:
        """Log to parent."""
        self._log_fn(msg, level)

    def closeEvent(self, event):
        self._log("Routines closed.", "info")
        super().closeEvent(event)
