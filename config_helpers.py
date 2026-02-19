"""
Configuration helpers for loading and saving application settings.
"""

import json
import os
from pathlib import Path

from config import AppConfig


def _load_config() -> dict:
    """Load config.json if it exists."""
    if AppConfig.CONFIG_JSON.exists():
        try:
            return json.loads(AppConfig.CONFIG_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_google_maps_api_key() -> str:
    """Get API key from config.json or env."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        key = (_load_config().get("google_maps_api_key") or "").strip()
    return key


def config_disable_webengine_map() -> bool:
    """Whether to disable WebEngine map (e.g. for headless/testing)."""
    return bool(_load_config().get("disable_webengine_map", False))


def config_prefer_leaflet_map() -> bool:
    """Whether to prefer Leaflet over Google Maps."""
    return bool(_load_config().get("prefer_leaflet_map", False))


def get_default_route_address() -> str:
    """Get default address for route visits with no address (configurable)."""
    return (_load_config().get("default_route_address") or AppConfig.DEFAULT_ROUTE_ADDRESS).strip()


def get_default_location_name() -> str:
    """Get display name for the default/office location (configurable)."""
    return (_load_config().get("default_location_name") or "Kontor").strip() or "Kontor"


def get_routines_folder() -> str:
    """Get Routines markdown folder from config."""
    return (_load_config().get("routines_folder") or "").strip()


def save_routines_folder(path: str) -> None:
    """Save Routines folder to config."""
    save_config_updates({"routines_folder": (path or "").strip()})


def get_routines_default_file() -> str:
    """Get default markdown file to open in Routines (filename only)."""
    return (_load_config().get("routines_default_file") or "").strip()


def save_routines_default_file(filename: str) -> None:
    """Save default Routines file to config."""
    save_config_updates({"routines_default_file": (filename or "").strip()})


def get_routines_colors() -> dict:
    """Get routine colors from config: {filename: hex_color}."""
    cfg = _load_config()
    colors = cfg.get("routines_colors")
    if isinstance(colors, dict):
        return {k: v for k, v in colors.items() if isinstance(v, str) and v.strip()}
    return {}


def save_routine_color(filename: str, color: str) -> None:
    """Save a single routine's color."""
    colors = get_routines_colors()
    if color and color.strip():
        colors[filename] = color.strip()
    elif filename in colors:
        del colors[filename]
    save_config_updates({"routines_colors": colors})


def get_routines_zoom() -> dict:
    """Get routine zoom levels: {filename: {"view": int%, "edit": int pt}}."""
    cfg = _load_config()
    zoom = cfg.get("routines_zoom")
    if isinstance(zoom, dict):
        return {
            k: {"view": v.get("view", 100), "edit": v.get("edit", 9)}
            for k, v in zoom.items()
            if isinstance(v, dict)
        }
    return {}


def save_routine_zoom(filename: str, view_zoom: int, edit_pt: int) -> None:
    """Save zoom level for a routine."""
    zoom = get_routines_zoom()
    zoom[filename] = {"view": view_zoom, "edit": edit_pt}
    save_config_updates({"routines_zoom": zoom})


def get_routines_order() -> list[str]:
    """Get routine tab order from config: [filename1, filename2, ...]."""
    cfg = _load_config()
    order = cfg.get("routines_order")
    if isinstance(order, list):
        return [f for f in order if isinstance(f, str) and f.strip()]
    return []


def save_routines_order(filenames: list[str]) -> None:
    """Save routine tab order to config."""
    save_config_updates({"routines_order": [f.strip() for f in filenames if f and f.strip()]})


def save_config_updates(updates: dict) -> None:
    """Update config.json with given key-value pairs."""
    cfg = _load_config()
    cfg.update(updates)
    AppConfig.CONFIG_JSON.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
