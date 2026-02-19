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
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from config import AppConfig, Styles, ensure_config_exists
# Import splash screen early (lightweight)
from splash_screen import SplashScreen
# Dashboard import deferred until after splash is shown (heavy imports)


def main() -> int:
    # High DPI support (must be set before QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    # Show splash screen IMMEDIATELY - before any heavy initialization
    splash = SplashScreen(app)
    splash.show()
    # Force immediate display with multiple event processing
    for _ in range(3):
        app.processEvents()
    splash.raise_()
    splash.activateWindow()
    app.processEvents()

    # Now do heavy initialization while splash is visible
    # Apply Windows 11 Fluent-style QSS (includes DPI-scaled font)
    Styles.apply(app, dark_mode=False)
    app.processEvents()  # Keep splash responsive

    # Set default font — matches Styles._base_font_pt for consistency
    font_pt = Styles._base_font_pt(app)
    font = QFont("Segoe UI", font_pt)
    app.setFont(font)
    app.processEvents()  # Keep splash responsive

    # Import Dashboard now (this triggers heavy imports like pandas, etc.)
    # but splash is already visible
    from dashboard import Dashboard
    
    # Main window creation (may take a moment due to lazy imports)
    window = Dashboard()
    app.processEvents()  # Keep splash responsive
    
    # Finish initialization and close splash screen
    def finish_startup():
        window.show()
        # Ensure window is ready before closing splash
        app.processEvents()
        splash.finish(window)
        # Defer config check to after UI is shown for faster startup
        ensure_config_exists()
    
    # Small delay to ensure main window is fully ready and splash is visible
    QTimer.singleShot(200, finish_startup)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
