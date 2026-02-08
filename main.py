"""
Toolbox - Windows 11 Python Desktop Application
Entry point for the PySide6-based launcher.
"""

import sys
import traceback


def _excepthook(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions to stderr instead of silent crash."""
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from config import AppConfig, Styles
from dashboard import Dashboard


def main() -> int:
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    # Apply Windows 11 Fluent-style QSS
    Styles.apply(app, dark_mode=False)

    # Set default font (avoid Segoe UI Variable - can cause QFont::setPointSize -1 errors on Qt)
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Main window
    window = Dashboard()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
