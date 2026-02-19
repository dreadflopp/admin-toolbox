"""
Route Rules Editor Window - edit route data processing rules.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QComboBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from utils import get_route_rules, save_route_rules, DEFAULT_ROUTE_RULES


def _rule_to_display(rule: dict) -> str:
    """Format rule for display in list."""
    rtype = rule.get("type", "")
    col = rule.get("column", "")
    if rtype == "fill_default_address":
        prefs = rule.get("prefixes", [])
        prefs_str = ", ".join(prefs) if isinstance(prefs, list) else str(prefs)
        return f"Fill address when {col} starts with: {prefs_str}"
    if rtype == "remove_empty":
        return f"Remove when {col} is empty"
    if rtype == "remove_starts_with":
        pat = rule.get("pattern", "")
        return f"Remove when {col} starts with: {pat}"
    return f"{rtype}: {col}"


class RuleEditorWindow(QMainWindow):
    """Window to edit route data rules (fill address, remove rows)."""

    def __init__(self, parent=None, log_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Route Rules Editor")
        self._log = log_fn or (lambda msg, lvl="info": None)
        self.setMinimumSize(500, 400)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._get_rules = get_route_rules
        self._save_rules = save_route_rules
        self._default_rules = DEFAULT_ROUTE_RULES
        self._rules = list(self._get_rules())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(QLabel("Rules are applied in order when loading route data:"))
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Rule", "Details"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._on_add)
        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._on_edit)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._on_remove)
        btn_up = QPushButton("Move up")
        btn_up.clicked.connect(self._on_move_up)
        btn_down = QPushButton("Move down")
        btn_down.clicked.connect(self._on_move_down)
        btn_reset = QPushButton("Reset to default")
        btn_reset.clicked.connect(self._on_reset)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addStretch()
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        self._refresh_table()

    def _refresh_table(self) -> None:
        self._table.setRowCount(len(self._rules))
        for i, r in enumerate(self._rules):
            rtype = r.get("type", "")
            self._table.setItem(i, 0, QTableWidgetItem(rtype))
            self._table.setItem(i, 1, QTableWidgetItem(_rule_to_display(r)))

    def _edit_rule_dialog(self, rule: dict | None = None) -> dict | None:
        """Show edit dialog, return rule dict or None if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Rule" if rule else "Add Rule")
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Type:"))
        type_combo = QComboBox()
        type_combo.addItems(["fill_default_address", "remove_empty", "remove_starts_with"])
        if rule:
            idx = type_combo.findText(rule.get("type", ""))
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
        layout.addWidget(type_combo)

        layout.addWidget(QLabel("Column:"))
        col_edit = QLineEdit()
        col_edit.setPlaceholderText("e.g. Besökstyp, Adress, Slinga, Sign.")
        if rule:
            col_edit.setText(rule.get("column", ""))
        layout.addWidget(col_edit)

        layout.addWidget(QLabel("Pattern (for remove_starts_with):"))
        pattern_edit = QLineEdit()
        pattern_edit.setPlaceholderText("e.g. xExterna, AVBOK, SJUKHUS")
        if rule and rule.get("type") == "remove_starts_with":
            pattern_edit.setText(rule.get("pattern", ""))
        layout.addWidget(pattern_edit)

        layout.addWidget(QLabel("Prefixes (for fill_default_address, comma-separated):"))
        prefs_edit = QLineEdit()
        prefs_edit.setPlaceholderText("e.g. AVSLUT, UPPSTART, RAST")
        if rule and rule.get("type") == "fill_default_address":
            prefs = rule.get("prefixes", [])
            prefs_edit.setText(", ".join(prefs) if isinstance(prefs, list) else str(prefs))
        layout.addWidget(prefs_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        rtype = type_combo.currentText().strip()
        col = col_edit.text().strip()
        result = {"type": rtype, "column": col}
        if rtype == "remove_starts_with":
            result["pattern"] = pattern_edit.text().strip()
        elif rtype == "fill_default_address":
            parts = [p.strip() for p in prefs_edit.text().split(",") if p.strip()]
            result["prefixes"] = parts
        return result

    def _on_add(self) -> None:
        r = self._edit_rule_dialog()
        if r:
            self._rules.append(r)
            self._refresh_table()

    def _on_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        r = self._edit_rule_dialog(self._rules[row])
        if r:
            self._rules[row] = r
            self._refresh_table()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._rules.pop(row)
            self._refresh_table()

    def _on_move_up(self) -> None:
        row = self._table.currentRow()
        if row > 0:
            self._rules[row], self._rules[row - 1] = self._rules[row - 1], self._rules[row]
            self._refresh_table()
            self._table.selectRow(row - 1)

    def _on_move_down(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._rules) - 1:
            self._rules[row], self._rules[row + 1] = self._rules[row + 1], self._rules[row]
            self._refresh_table()
            self._table.selectRow(row + 1)

    def _on_reset(self) -> None:
        if QMessageBox.question(
            self, "Reset", "Reset all rules to default?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._rules = list(self._default_rules)
            self._refresh_table()

    def _on_save(self) -> None:
        self._save_rules(self._rules)
        QMessageBox.information(self, "Saved", "Rules saved. They will apply when loading route data.")
        self._log("Route rules saved.", "success")
        self.close()

    def closeEvent(self, event):
        self._log("Route Rules Editor closed.", "info")
        super().closeEvent(event)
