"""
Settings dialog for application configuration.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QScrollArea,
    QWidget,
    QFrame,
    QMessageBox,
)

from utils import (
    get_default_route_address,
    get_default_location_name,
    get_routines_folder,
    save_routines_folder,
    clear_geocache,
    get_break_names,
    get_break_lunch_window,
    get_break_evening_window,
    save_break_settings,
    get_route_sort_order,
    save_route_sort_order,
    get_route_color_rules,
    save_route_color_rules,
    save_config_updates,
    ROUTE_COLOR_PRESETS,
)


def _browse_routines_folder(edit: QLineEdit) -> None:
    """Open folder dialog for Routines folder."""
    from PySide6.QtWidgets import QFileDialog
    folder = QFileDialog.getExistingDirectory(None, "Select Routines Folder", edit.text() or str(Path.home()))
    if folder:
        edit.setText(folder)


class SettingsDialog(QDialog):
    """Settings dialog for application configuration."""

    def __init__(self, parent=None, log_fn=None):
        super().__init__(parent)
        self.log_fn = log_fn or (lambda msg, level="info": None)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout(self)

        # Default address
        layout.addWidget(QLabel("Default address for route visits with no address:"))
        self.addr_edit = QLineEdit()
        self.addr_edit.setText(get_default_route_address())
        self.addr_edit.setPlaceholderText("e.g. Angereds Torg 5, 42465 Angered")
        layout.addWidget(self.addr_edit)

        # Default location name
        layout.addWidget(QLabel("Display name for default location (Kontor, office, etc.):"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(get_default_location_name())
        self.name_edit.setPlaceholderText("e.g. Kontor")
        layout.addWidget(self.name_edit)

        # Routines folder
        routines_row = QHBoxLayout()
        routines_row.addWidget(QLabel("Routines folder (markdown files):"))
        self.routines_edit = QLineEdit()
        self.routines_edit.setText(get_routines_folder())
        self.routines_edit.setPlaceholderText("e.g. C:\\Users\\Me\\Routines")
        routines_row.addWidget(self.routines_edit)
        btn_browse_routines = QPushButton("Browse")
        btn_browse_routines.clicked.connect(lambda: _browse_routines_folder(self.routines_edit))
        routines_row.addWidget(btn_browse_routines)
        layout.addLayout(routines_row)

        # Break / schedule settings
        break_group = QGroupBox("Schedule breaks (for route trips)")
        break_layout = QVBoxLayout(break_group)
        break_layout.addWidget(
            QLabel("Break names in schedule (semicolon-separated, case insensitive):")
        )
        self.break_names_edit = QLineEdit()
        self.break_names_edit.setText("; ".join(get_break_names()))
        self.break_names_edit.setPlaceholderText("e.g. RAST; RAST + 10 adm")
        break_layout.addWidget(self.break_names_edit)
        break_layout.addWidget(
            QLabel("Lunch break (HH:MM-HH:MM):")
        )
        self.lunch_edit = QLineEdit()
        lunch_start, lunch_end = get_break_lunch_window()
        self.lunch_edit.setText(f"{lunch_start.strftime('%H:%M')}-{lunch_end.strftime('%H:%M')}")
        self.lunch_edit.setPlaceholderText("e.g. 10:00-14:00")
        break_layout.addWidget(self.lunch_edit)
        break_layout.addWidget(
            QLabel("Evening break (HH:MM-HH:MM):")
        )
        self.evening_edit = QLineEdit()
        evening_start, evening_end = get_break_evening_window()
        self.evening_edit.setText(f"{evening_start.strftime('%H:%M')}-{evening_end.strftime('%H:%M')}")
        self.evening_edit.setPlaceholderText("e.g. 15:00-19:00")
        break_layout.addWidget(self.evening_edit)
        layout.addWidget(break_group)

        # Route sort order
        sort_group = QGroupBox("Route sorting")
        sort_layout = QVBoxLayout(sort_group)
        sort_layout.addWidget(QLabel("Sort routes by:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.addItem("First trip type (morning/afternoon/evening, then by name)", "time")
        sort_order = get_route_sort_order()
        idx = self.sort_combo.findData(sort_order)
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)
        sort_layout.addWidget(self.sort_combo)
        layout.addWidget(sort_group)

        # Route color rules
        color_group = QGroupBox("Route colors")
        color_layout = QVBoxLayout(color_group)
        color_layout.addWidget(QLabel("Use color if route name contains (first match wins):"))
        rules_widget = QWidget()
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rule_rows = []

        def add_rule_row(rule=None):
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            color_combo = QComboBox()
            for preset_name, hex_val in ROUTE_COLOR_PRESETS:
                color_combo.addItem(preset_name, hex_val)
            color_combo.setMinimumWidth(120)
            contains_edit = QLineEdit()
            contains_edit.setPlaceholderText("e.g. A, B, Nord")
            contains_edit.setMinimumWidth(140)
            remove_btn = QPushButton("Remove")
            remove_btn.setFlat(True)
            remove_btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
            if rule:
                rule_color = (rule.get("color") or "").strip()
                found = False
                for i in range(color_combo.count()):
                    if (color_combo.itemData(i) or "").lower() == rule_color.lower():
                        color_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found and rule_color:
                    color_combo.addItem(rule_color, rule_color)
                    color_combo.setCurrentIndex(color_combo.count() - 1)
                contains_edit.setText(rule.get("contains", ""))
            row_layout.addWidget(QLabel("Use"))
            row_layout.addWidget(color_combo)
            row_layout.addWidget(QLabel("if route name contains:"))
            row_layout.addWidget(contains_edit)
            row_layout.addWidget(remove_btn)
            row_layout.addStretch()

            def remove_row():
                rules_layout.removeWidget(row)
                row.deleteLater()
                self.rule_rows.remove((row, color_combo, contains_edit))

            remove_btn.clicked.connect(remove_row)
            rules_layout.addWidget(row)
            self.rule_rows.append((row, color_combo, contains_edit))

        for rule in get_route_color_rules():
            add_rule_row(rule)
        if not self.rule_rows:
            add_rule_row()

        add_btn = QPushButton("Add rule")
        add_btn.setFlat(True)
        add_btn.clicked.connect(lambda: add_rule_row())
        rules_layout.addWidget(add_btn)

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content_layout.addWidget(rules_widget)  # no stretch - stays compact
        scroll_content_layout.addStretch(1)  # extra space goes here, not between rows

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setMinimumHeight(120)
        color_layout.addWidget(scroll, 1)  # stretch=1 so list grows when window grows
        layout.addWidget(color_group, 1)  # stretch=1 so group (and scroll) grows when dialog grows

        # Delete cached address data (geocache)
        data_group = QGroupBox("Data")
        data_layout = QVBoxLayout(data_group)
        data_layout.addWidget(QLabel("Cached geocoded addresses are stored locally. Delete to remove all cached data."))
        btn_clear_geocache = QPushButton("Delete cached address data")
        btn_clear_geocache.clicked.connect(self._on_clear_geocache)
        data_layout.addWidget(btn_clear_geocache)
        layout.addWidget(data_group)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_clear_geocache(self) -> None:
        """Delete all cached address data after confirmation."""
        if (
            QMessageBox.question(
                self,
                "Delete cached data",
                "Delete all cached address data? Addresses will be re-geocoded when you next open a map.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        count = clear_geocache()
        QMessageBox.information(self, "Deleted", f"Deleted {count} cached address entries.")
        self.log_fn(f"Cached address data cleared ({count} entries).", "info")

    def accept(self) -> None:
        """Save settings when dialog is accepted."""
        updates = {}
        if self.addr_edit.text().strip():
            updates["default_route_address"] = self.addr_edit.text().strip()
        if self.name_edit.text().strip():
            updates["default_location_name"] = self.name_edit.text().strip()
        if updates:
            save_config_updates(updates)
        save_routines_folder(self.routines_edit.text().strip())
        save_break_settings(
            self.break_names_edit.text().strip() or "RAST",
            self.lunch_edit.text().strip() or "10:00-14:00",
            self.evening_edit.text().strip() or "15:00-19:00",
        )
        save_route_sort_order(self.sort_combo.currentData() or "time")
        rules = []
        for _, color_combo, contains_edit in self.rule_rows:
            contains = contains_edit.text().strip()
            if contains:
                color = color_combo.currentData() or "#777777"
                rules.append({"color": color, "contains": contains})
        save_route_color_rules(rules)
        self.log_fn("Settings saved.", "success")
        super().accept()
