"""
Application configuration and styles for the Toolbox desktop app.
Provides AppConfig for paths/settings and Styles for Windows 11 Fluent Design.
"""

import json
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
    PROJECT_DIR = _bundle_dir() if _frozen() else Path(__file__).parent
    CONFIG_JSON = _exe_dir() / "config.json"
    MAP_TEMPLATE_GOOGLE = _bundle_dir() / "map_template_google.html"
    GEOCACHE_DB = _exe_dir() / "geocache.db"  # always next to exe (portable)

    # Default config written when config.json is missing (e.g. first run of exe)
    DEFAULT_CONFIG = {"google_maps_api_key": ""}


def ensure_config_exists() -> None:
    """Create config.json with default content if it does not exist (e.g. first run of built exe)."""
    path = AppConfig.CONFIG_JSON
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(AppConfig.DEFAULT_CONFIG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


# =============================================================================
# Styles: Windows 11 Fluent Design compatible QSS
# Dark/light mode compatible palette, rounded corners, hover effects
# =============================================================================


class Styles:
    """Windows 11 Fluent Design compatible QSS styles.
    Uses pt for font sizes (scales with DPI). Padding uses em where supported.
    """

    FONT_FAMILY = "Segoe UI, sans-serif"

    @classmethod
    def _base_font_pt(cls, app) -> int:
        """Base font size in pt, scaled for DPI (150% laptop vs 4K)."""
        try:
            screen = app.primaryScreen()
            if screen:
                log_dpi = screen.logicalDotsPerInch()
                scale = log_dpi / 96.0
                return max(8, min(11, int(9 * scale)))
        except Exception:
            pass
        return 9

    @classmethod
    def _build_style(cls, font_pt: int, dark_mode: bool) -> str:
        """Build QSS with given base font size."""
        if dark_mode:
            return f"""
                QWidget {{
                    font-family: {cls.FONT_FAMILY};
                    font-size: {font_pt}pt;
                }}
                QMainWindow {{
                    background-color: #202020;
                }}
                QLabel {{
                    color: #f3f3f3;
                }}
                QLineEdit {{
                    padding: 0.6em 0.8em;
                    border: 1px solid #3b3a39;
                    border-radius: 6px;
                    background-color: #292827;
                    color: #f3f3f3;
                    selection-background-color: #0078d4;
                }}
                QLineEdit:focus {{
                    border-color: #0078d4;
                    outline: none;
                }}
                QLineEdit:disabled {{
                    background-color: #323130;
                    color: #605e5c;
                }}
                QLineEdit#filePath {{
                    font-size: 8pt;
                    padding: 4px 8px;
                }}
                QPushButton {{
                    padding: 0.5em 1em;
                    border: none;
                    border-radius: 6px;
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
                QPushButton#secondary {{
                    background-color: #5c5c5c;
                }}
                QPushButton#secondary:hover {{
                    background-color: #6e6e6e;
                }}
                QPushButton#secondary:disabled {{
                    background-color: #3b3a39;
                }}
                QPushButton#tertiary {{
                    background-color: transparent;
                    color: #8a8886;
                }}
                QPushButton#tertiary:hover {{
                    background-color: #3b3a39;
                    color: #f3f3f3;
                }}
                QPushButton#zoom {{
                    background-color: #5c5c5c;
                    color: #f3f3f3;
                    border: 1px solid #6e6e6e;
                    font-size: 14pt;
                    font-weight: bold;
                }}
                QPushButton#zoom:hover {{
                    background-color: #6e6e6e;
                }}
                QPushButton#zoom:pressed {{
                    background-color: #4a4a4a;
                }}
                QGroupBox {{
                    font-weight: 600;
                    border: 1px solid #3b3a39;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding: 10px 10px 10px 10px;
                    padding-top: 14px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 12px;
                    padding: 0 6px;
                    background-color: #202020;
                }}
                QTableWidget::item {{
                    selection-background-color: #1e3a5f;
                    selection-color: #f3f3f3;
                }}
                QTableWidget::item:hover {{
                    background-color: #2d3e50;
                }}
                QScrollArea {{
                    border: none;
                    background-color: transparent;
                }}
            """
        # Light mode (default)
        return f"""
            QWidget {{
                font-family: {cls.FONT_FAMILY};
                font-size: {font_pt}pt;
            }}
            QMainWindow {{
                background-color: #fafafa;
            }}
            QLabel {{
                color: #323130;
            }}
            QLineEdit {{
                padding: 0.6em 0.8em;
                border: 1px solid #e1dfdd;
                border-radius: 6px;
                background-color: #ffffff;
                selection-background-color: #0078d4;
            }}
            QLineEdit:focus {{
                border-color: #0078d4;
                outline: none;
            }}
            QLineEdit:disabled {{
                background-color: #f3f2f1;
                color: #a19f9d;
            }}
            QLineEdit#filePath {{
                font-size: 8pt;
                padding: 4px 8px;
            }}
            QPushButton {{
                padding: 0.5em 1em;
                border: none;
                border-radius: 6px;
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
                background-color: #e1dfdd;
                color: #8a8886;
            }}
            QPushButton#secondary {{
                background-color: #edebe9;
                color: #323130;
            }}
            QPushButton#secondary:hover {{
                background-color: #d2d0ce;
            }}
            QPushButton#secondary:disabled {{
                background-color: #f3f2f1;
                color: #a19f9d;
            }}
            QPushButton#tertiary {{
                background-color: transparent;
                color: #605e5c;
            }}
            QPushButton#tertiary:hover {{
                background-color: #edebe9;
                color: #323130;
            }}
            QPushButton#zoom {{
                background-color: #e1e1e1;
                color: #1a1a1a;
                border: 1px solid #ccc;
                font-size: 14pt;
                font-weight: bold;
            }}
            QPushButton#zoom:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton#zoom:pressed {{
                background-color: #c0c0c0;
            }}
            QGroupBox {{
                font-weight: 600;
                border: 1px solid #edebe9;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px 10px 10px 10px;
                padding-top: 14px;
                background-color: #ffffff;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                background-color: #fafafa;
            }}
            QTableWidget::item {{
                selection-background-color: #bbdefb;
                selection-color: #323130;
            }}
            QTableWidget::item:hover {{
                background-color: #e3f2fd;
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """

    @classmethod
    def apply(cls, app, dark_mode: bool = False) -> None:
        """Apply the current style to the application.
        Font size scales with DPI for 150% laptop and 4K screens.
        """
        font_pt = cls._base_font_pt(app)
        style = cls._build_style(font_pt, dark_mode)
        app.setStyleSheet(style)
