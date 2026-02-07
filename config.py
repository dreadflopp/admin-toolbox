"""
Application configuration and styles for the Toolbox desktop app.
Provides AppConfig for paths/settings and Styles for Windows 11 Fluent Design.
"""

import sys
from pathlib import Path


def _frozen() -> bool:
    """True when running as PyInstaller exe."""
    return getattr(sys, "frozen", False)


def _bundle_dir() -> Path:
    """Directory for bundled resources (map template, etc). When frozen, use PyInstaller's extract dir."""
    if _frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _exe_dir() -> Path:
    """Directory containing the exe (when frozen) or the project (when running from source).
    Used for config.json and geocache.db so they always live next to the exe."""
    if _frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent


# =============================================================================
# AppConfig: Central configuration for paths, defaults, and app settings
# =============================================================================
# Inject your file structure expectations here once known:
# - Expected columns for Address Source File
# - Expected columns for Route Data File
# - default_export_dir, etc.
# =============================================================================


class AppConfig:
    """Central application configuration."""

    APP_NAME = "Toolbox"
    APP_VERSION = "1.0.0"
    ORGANIZATION = "Toolbox"

    # Default paths (user's home or current working directory)
    DEFAULT_EXPORT_DIR = str(Path.home() / "Documents" / "Toolbox_Exports")

    # Address Source: PDF with multi-page table, header on each page
    # Columns to extract: Färg, Förnamn, Efternamn, Adress
    ADDRESS_SOURCE_COLUMNS = ["Färg", "Förnamn", "Efternamn", "Adress"]

    # Route Data: Excel only. Required columns:
    ROUTE_DATA_COLUMNS = ["Starttid", "Sluttid", "Namn", "Adress", "Slinga", "Besökstyp", "Insatser", "Sign."]

    # Supported file extensions for validation
    ADDRESS_SOURCE_EXTENSIONS = {".pdf"}
    ROUTE_DATA_EXTENSIONS = {".xlsx", ".xls"}

    # Default customer (always first in list)
    DEFAULT_CUSTOMER = {
        "Färg": "#000000",
        "Förnamn": "Kontor",
        "Efternamn": "",
        "Adress": "Angereds Torg 5, 42465 Angered",
    }

    # Default address when route visit has no address (configurable via Settings)
    DEFAULT_ROUTE_ADDRESS = "Angereds Torg 5, 42465 Angered"

    # Paths
    PROJECT_DIR = Path(__file__).parent
    CONFIG_JSON = _exe_dir() / "config.json"
    MAP_TEMPLATE_GOOGLE = _bundle_dir() / "map_template_google.html"
    GEOCACHE_DB = _exe_dir() / "geocache.db"  # always next to exe (portable)


# =============================================================================
# Styles: Windows 11 Fluent Design compatible QSS
# Dark/light mode compatible palette, rounded corners, hover effects
# =============================================================================


class Styles:
    """Windows 11 Fluent Design compatible QSS styles."""

    # Font family - Segoe UI Variable for Windows 11 look
    FONT_FAMILY = "Segoe UI, sans-serif"

    # Base styles applied to the main application
    MAIN_STYLE = f"""
        QWidget {{
            font-family: {FONT_FAMILY};
            font-size: 11pt;
        }}
        QMainWindow {{
            background-color: #f3f3f3;
        }}
        QLabel {{
            color: #323130;
        }}
        QLineEdit {{
            padding: 8px 12px;
            border: 1px solid #d1d1d1;
            border-radius: 8px;
            background-color: #ffffff;
            selection-background-color: #0078d4;
        }}
        QLineEdit:focus {{
            border-color: #0078d4;
        }}
        QLineEdit:disabled {{
            background-color: #f3f3f3;
            color: #a19f9d;
        }}
        QPushButton {{
            padding: 8px 20px;
            border: none;
            border-radius: 8px;
            background-color: #0078d4;
            color: white;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: #106ebe;
        }}
        QPushButton:pressed {{
            background-color: #005a9e;
        }}
        QPushButton:disabled {{
            background-color: #c8c6c4;
            color: #8a8886;
        }}
        QPushButton#secondary {{
            background-color: #424242;
        }}
        QPushButton#secondary:hover {{
            background-color: #505050;
        }}
        QGroupBox {{
            font-weight: 600;
            border: 1px solid #e1dfdd;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            background-color: #f3f3f3;
        }}
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
    """

    # Dark mode variant (can be toggled if implementing theme switch)
    DARK_MAIN_STYLE = f"""
        QWidget {{
            font-family: {FONT_FAMILY};
            font-size: 11pt;
        }}
        QMainWindow {{
            background-color: #202020;
        }}
        QLabel {{
            color: #f3f3f3;
        }}
        QLineEdit {{
            padding: 8px 12px;
            border: 1px solid #3b3a39;
            border-radius: 8px;
            background-color: #292827;
            color: #f3f3f3;
            selection-background-color: #0078d4;
        }}
        QLineEdit:focus {{
            border-color: #0078d4;
        }}
        QLineEdit:disabled {{
            background-color: #323130;
            color: #605e5c;
        }}
        QPushButton {{
            padding: 8px 20px;
            border: none;
            border-radius: 8px;
            background-color: #0078d4;
            color: white;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: #1084d8;
        }}
        QPushButton:pressed {{
            background-color: #005a9e;
        }}
        QPushButton:disabled {{
            background-color: #3b3a39;
            color: #605e5c;
        }}
        QGroupBox {{
            font-weight: 600;
            border: 1px solid #3b3a39;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            background-color: #202020;
        }}
    """

    @classmethod
    def apply(cls, app, dark_mode: bool = False) -> None:
        """Apply the current style to the application."""
        style = cls.DARK_MAIN_STYLE if dark_mode else cls.MAIN_STYLE
        app.setStyleSheet(style)
