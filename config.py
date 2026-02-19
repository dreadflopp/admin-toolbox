"""
Application configuration and styles for the Toolbox desktop app.
Provides AppConfig for paths/settings and Styles for Windows 11 Fluent Design.
"""

import json
import sys
from pathlib import Path

# Cache Path.home() to avoid repeated slow calls on network drives
_cached_home_dir = None

def _get_home_dir() -> Path:
    """Get home directory, cached to avoid repeated slow calls."""
    global _cached_home_dir
    if _cached_home_dir is None:
        _cached_home_dir = Path.home()
    return _cached_home_dir


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


class _DefaultExportDir:
    """Descriptor for lazy computation of DEFAULT_EXPORT_DIR."""
    def __get__(self, obj, objtype=None):
        return str(_get_home_dir() / "Documents" / "Toolbox_Exports")


class AppConfig:
    """Central application configuration."""

    APP_NAME = "Toolbox"
    APP_VERSION = "1.0.0"
    ORGANIZATION = "Toolbox"

    # Default paths (user's home or current working directory)
    # Uses cached home directory to avoid slow Path.home() calls on network drives
    DEFAULT_EXPORT_DIR = _DefaultExportDir()

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
        """Base font size in pt, scaled for DPI (150% laptop vs 4K).
        Cached per app instance to avoid repeated screen queries.
        """
        # Cache the result per app instance (app object is unique per run)
        if not hasattr(cls, '_font_cache'):
            cls._font_cache = {}
        cache_key = id(app)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]
        
        try:
            screen = app.primaryScreen()
            if screen:
                log_dpi = screen.logicalDotsPerInch()
                scale = log_dpi / 96.0
                result = max(8, min(11, int(9 * scale)))
            else:
                result = 9
        except Exception:
            result = 9
        
        cls._font_cache[cache_key] = result
        return result

    @classmethod
    def _get_color_palette(cls, dark_mode: bool) -> dict:
        """Get color palette for dark or light mode."""
        if dark_mode:
            return {
                "main_bg": "#202020",
                "text": "#f3f3f3",
                "lineedit_border": "#3b3a39",
                "lineedit_bg": "#292827",
                "lineedit_disabled_bg": "#323130",
                "lineedit_disabled_text": "#605e5c",
                "button_hover": "#1084d8",
                "button_disabled_bg": "#3b3a39",
                "button_disabled_text": "#605e5c",
                "button_secondary_bg": "#5c5c5c",
                "button_secondary_hover": "#6e6e6e",
                "button_tertiary_text": "#8a8886",
                "button_tertiary_hover_bg": "#3b3a39",
                "button_zoom_bg": "#5c5c5c",
                "button_zoom_text": "#f3f3f3",
                "button_zoom_border": "#6e6e6e",
                "button_zoom_hover": "#6e6e6e",
                "button_zoom_pressed": "#4a4a4a",
                "groupbox_border": "#3b3a39",
                "groupbox_title_bg": "#202020",
                "table_selection_bg": "#1e3a5f",
                "table_selection_text": "#f3f3f3",
                "table_hover_bg": "#2d3e50",
            }
        # Light mode
        return {
            "main_bg": "#fafafa",
            "text": "#323130",
            "lineedit_border": "#e1dfdd",
            "lineedit_bg": "#ffffff",
            "lineedit_disabled_bg": "#f3f2f1",
            "lineedit_disabled_text": "#a19f9d",
            "button_hover": "#106ebe",
            "button_disabled_bg": "#e1dfdd",
            "button_disabled_text": "#8a8886",
            "button_secondary_bg": "#edebe9",
            "button_secondary_text": "#323130",
            "button_secondary_hover": "#d2d0ce",
            "button_secondary_disabled_bg": "#f3f2f1",
            "button_secondary_disabled_text": "#a19f9d",
            "button_tertiary_text": "#605e5c",
            "button_tertiary_hover_bg": "#edebe9",
            "button_zoom_bg": "#e1e1e1",
            "button_zoom_text": "#1a1a1a",
            "button_zoom_border": "#ccc",
            "button_zoom_hover": "#d0d0d0",
            "button_zoom_pressed": "#c0c0c0",
            "groupbox_border": "#edebe9",
            "groupbox_bg": "#ffffff",
            "groupbox_title_bg": "#fafafa",
            "table_selection_bg": "#bbdefb",
            "table_selection_text": "#323130",
            "table_hover_bg": "#e3f2fd",
        }

    @classmethod
    def _build_style(cls, font_pt: int, dark_mode: bool) -> str:
        """Build QSS with given base font size."""
        colors = cls._get_color_palette(dark_mode)
        
        # Common QSS template with color placeholders
        return f"""
            QWidget {{
                font-family: {cls.FONT_FAMILY};
                font-size: {font_pt}pt;
            }}
            QMainWindow {{
                background-color: {colors['main_bg']};
            }}
            QLabel {{
                color: {colors['text']};
            }}
            QLineEdit {{
                padding: 0.6em 0.8em;
                border: 1px solid {colors['lineedit_border']};
                border-radius: 6px;
                background-color: {colors['lineedit_bg']};
                color: {colors['text']};
                selection-background-color: #0078d4;
            }}
            QLineEdit:focus {{
                border-color: #0078d4;
                outline: none;
            }}
            QLineEdit:disabled {{
                background-color: {colors['lineedit_disabled_bg']};
                color: {colors['lineedit_disabled_text']};
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
                background-color: {colors['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: #005a9e;
            }}
            QPushButton:disabled {{
                background-color: {colors['button_disabled_bg']};
                color: {colors['button_disabled_text']};
            }}
            QPushButton#secondary {{
                background-color: {colors['button_secondary_bg']};
                {f"color: {colors['button_secondary_text']};" if 'button_secondary_text' in colors else ''}
            }}
            QPushButton#secondary:hover {{
                background-color: {colors['button_secondary_hover']};
            }}
            QPushButton#secondary:disabled {{
                background-color: {colors.get('button_secondary_disabled_bg', colors['button_disabled_bg'])};
                color: {colors.get('button_secondary_disabled_text', colors['button_disabled_text'])};
            }}
            QPushButton#tertiary {{
                background-color: transparent;
                color: {colors['button_tertiary_text']};
            }}
            QPushButton#tertiary:hover {{
                background-color: {colors['button_tertiary_hover_bg']};
                color: {colors['text']};
            }}
            QPushButton#zoom {{
                background-color: {colors['button_zoom_bg']};
                color: {colors['button_zoom_text']};
                border: 1px solid {colors['button_zoom_border']};
                font-size: 14pt;
                font-weight: bold;
            }}
            QPushButton#zoom:hover {{
                background-color: {colors['button_zoom_hover']};
            }}
            QPushButton#zoom:pressed {{
                background-color: {colors['button_zoom_pressed']};
            }}
            QGroupBox {{
                font-weight: 600;
                border: 1px solid {colors['groupbox_border']};
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px 10px 10px 10px;
                padding-top: 14px;
                {f"background-color: {colors['groupbox_bg']};" if 'groupbox_bg' in colors else ''}
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                background-color: {colors['groupbox_title_bg']};
            }}
            QTableWidget::item {{
                selection-background-color: {colors['table_selection_bg']};
                selection-color: {colors['table_selection_text']};
            }}
            QTableWidget::item:hover {{
                background-color: {colors['table_hover_bg']};
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
