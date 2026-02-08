"""
Utility functions for data extraction, export, geocoding, and map rendering.
"""

import json
import os
import re
import sqlite3
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import pdfplumber

from config import AppConfig


# =============================================================================
# Config helpers
# =============================================================================


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


def get_default_customer() -> dict:
    """Get default customer dict with configurable name and address."""
    return {
        "Färg": AppConfig.DEFAULT_CUSTOMER["Färg"],
        "Förnamn": get_default_location_name(),
        "Efternamn": "",
        "Adress": get_default_route_address(),
    }


def save_config_updates(updates: dict) -> None:
    """Update config.json with given key-value pairs."""
    cfg = _load_config()
    cfg.update(updates)
    AppConfig.CONFIG_JSON.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# =============================================================================
# Route color rules: "Use X if route name contains Y"
# =============================================================================

ROUTE_COLOR_PRESETS = [
    ("Red", "#e74c3c"),
    ("Blue", "#3498db"),
    ("Light blue", "#5dade2"),
    ("Dark blue", "#2980b9"),
    ("Green", "#27ae60"),
    ("Light green", "#58d68d"),
    ("Dark green", "#1e8449"),
    ("Pink", "#e91e63"),
    ("Light pink", "#f48fb1"),
    ("Cyan", "#00bcd4"),
    ("Light cyan", "#4dd0e1"),
    ("Orange", "#e67e22"),
    ("Yellow", "#f1c40f"),
    ("Purple", "#9b59b6"),
    ("Light purple", "#ce93d8"),
]

DEFAULT_ROUTE_COLOR = "#777777"

# Default rules: Swedish color names (Rosa, Blå, Röd, etc.)
DEFAULT_ROUTE_COLOR_RULES = [
    {"color": "#e91e63", "contains": "Rosa"},
    {"color": "#3498db", "contains": "Blå"},
    {"color": "#e74c3c", "contains": "Röd"},
    {"color": "#27ae60", "contains": "Grön"},
    {"color": "#f1c40f", "contains": "Gul"},
    {"color": "#e67e22", "contains": "Orange"},
    {"color": "#9b59b6", "contains": "Lila"},
    {"color": "#00bcd4", "contains": "Cyan"},
]


def get_route_color_rules() -> list:
    """Get route color rules from config: [{color, contains}, ...]. Uses defaults if none set."""
    cfg = _load_config()
    rules = cfg.get("route_color_rules")
    if rules is not None and isinstance(rules, list):
        user_rules = [r for r in rules if isinstance(r, dict) and "color" in r]
        if user_rules:
            return user_rules
    return list(DEFAULT_ROUTE_COLOR_RULES)


def save_route_color_rules(rules: list) -> None:
    """Save route color rules to config."""
    save_config_updates({"route_color_rules": rules})


def _hex_to_rgb(hex_str: str) -> tuple:
    """Convert #RRGGBB to (r, g, b) 0-255."""
    hex_str = (hex_str or "").strip().lstrip("#")
    if len(hex_str) >= 6:
        return (
            int(hex_str[0:2], 16),
            int(hex_str[2:4], 16),
            int(hex_str[4:6], 16),
        )
    return (119, 119, 119)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _tint_color(hex_str: str, tint_index: int) -> str:
    """Apply tint: 0=base, 1=light, 2=dark, 3=lighter, 4=darker. Blend with white/black."""
    r, g, b = _hex_to_rgb(hex_str)
    # 0=base, 1=light (blend 60% white), 2=dark (blend 40% black), 3=lighter, 4=darker
    blends = [(1.0, 0), (0.6, 255), (0.85, 0), (0.45, 255), (0.7, 0)]
    blend, mix = blends[tint_index % len(blends)]
    r = int(r * blend + mix * (1 - blend))
    g = int(g * blend + mix * (1 - blend))
    b = int(b * blend + mix * (1 - blend))
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return _rgb_to_hex(r, g, b)


def get_route_colors(route_names: list) -> dict:
    """
    Get color for each route name based on config rules.
    Multiple routes with same base color get different tints.
    Returns {route_name: hex_color}.
    """
    rules = get_route_color_rules()
    color_counts = {}
    result = {}
    for name in route_names:
        name_upper = (name or "").upper()
        base_color = None
        for rule in rules:
            contains = (rule.get("contains") or "").strip()
            if contains and contains.upper() in name_upper:
                base_color = (rule.get("color") or DEFAULT_ROUTE_COLOR).strip()
                break
        if not base_color:
            base_color = DEFAULT_ROUTE_COLOR
        idx = color_counts.get(base_color, 0)
        result[name] = _tint_color(base_color, idx)
        color_counts[base_color] = idx + 1
    return result


# =============================================================================
# Map server (serves Google map with API key injected)
# =============================================================================

_server = None
_server_port = None


def _make_request_handler(api_key: str):
    key = (api_key or "").strip()
    project_dir = str(AppConfig.PROJECT_DIR)

    class MapRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=project_dir)

        def do_GET(self):
            if self.path == "/map_google.html" and key and AppConfig.MAP_TEMPLATE_GOOGLE.exists():
                html = AppConfig.MAP_TEMPLATE_GOOGLE.read_text(encoding="utf-8")
                html = html.replace("API_KEY_PLACEHOLDER", key)
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            super().do_GET()

    return MapRequestHandler


def start_map_server(api_key: str) -> bool:
    """Start local HTTP server for map. Returns True if started."""
    global _server, _server_port
    for port in range(8765, 8780):
        try:
            handler = _make_request_handler(api_key)
            _server = HTTPServer(("127.0.0.1", port), handler)
            _server_port = port
            thread = threading.Thread(target=_server.serve_forever, daemon=True)
            thread.start()
            return True
        except OSError:
            continue
    return False


def get_map_url() -> str:
    """Get URL for Google map page."""
    global _server_port
    if _server_port:
        return f"http://127.0.0.1:{_server_port}/map_google.html"
    return ""


# =============================================================================
# PDF Extraction
# =============================================================================


def _normalize_header(cell: str) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


# Column name normalization: PDF headers may vary (FÄRG, ADRESS, etc.)
_COLUMN_ALIASES = {
    "FÄRG": "Färg", "FARG": "Färg",
    "FÖRNAMN": "Förnamn", "FORNAMN": "Förnamn",
    "EFTERNAMN": "Efternamn",
    "ADRESS": "Adress", "ADDRESS": "Adress",
}


def _normalize_column_names(headers: list) -> list:
    """Map variable header names to expected column names."""
    result = []
    for h in headers:
        key = str(h).strip().upper()
        result.append(_COLUMN_ALIASES.get(key, h))
    return result


def extract_pdf_data(pdf_path: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Extract table data from Address Source PDF.
    Returns (DataFrame, None) on success, (None, error_message) on failure.
    """
    path = Path(pdf_path)
    if not path.exists():
        return None, f"File not found: {path}"
    all_rows = []
    header_row = None
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables or []:
                    for row in table or []:
                        if not row:
                            continue
                        norm = [_normalize_header(c) for c in row]
                        if norm and norm[0]:
                            # Check any cell in the row for header keywords (Färg may not be first column)
                            row_upper = " ".join(str(c).upper() for c in norm)
                            if any(
                                h in row_upper
                                for h in ("FÄRG", "FARG", "FÖRNAMN", "FORNAMN", "ADRESS", "ADDRESS")
                            ):
                                header_row = _normalize_column_names(norm)
                            elif header_row and len(norm) >= 4:
                                all_rows.append(dict(zip(header_row, norm)))
        if not header_row:
            return None, (
                "No header row found. Expected columns like Färg, Förnamn, Efternamn, Adress. "
                "Check that the PDF contains a table with these headers."
            )
        if not all_rows:
            return None, (
                "No data rows found. A header row was detected but no data rows matched. "
                "Ensure the table has at least 4 columns and data below the header."
            )
        return pd.DataFrame(all_rows), None
    except Exception as e:
        return None, f"PDF extraction failed: {type(e).__name__}: {e}"


def validate_address_columns(df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
    """Validate that df has required address columns."""
    if df is None or df.empty:
        return False, "No data"
    cols = [str(c).strip() for c in df.columns]
    required = [c for c in AppConfig.ADDRESS_SOURCE_COLUMNS]
    missing = [r for r in required if r not in cols]
    if missing:
        return False, f"Missing columns: {', '.join(missing)}"
    return True, None


# =============================================================================
# Route data loading
# =============================================================================


def _is_empty_value(val) -> bool:
    """Treat NaN, None, empty string, and string 'nan' as empty."""
    if val is None:
        return True
    if pd.isna(val):
        return True
    s = str(val).strip()
    return s == "" or s.lower() == "nan" or s.lower() == "none"


# Rule types: fill_default_address (pre-process), remove_empty, remove_starts_with (filter)
DEFAULT_ROUTE_RULES = [
    {
        "type": "fill_default_address",
        "column": "Besökstyp",
        "prefixes": ["AVSLUT", "UPPSTART", "RAST"],
    },
    {"type": "remove_starts_with", "column": "Besökstyp", "pattern": "ÄO Ringtillsyn"},
    {"type": "remove_empty", "column": "Adress"},
    {"type": "remove_empty", "column": "Slinga"},
    {"type": "remove_starts_with", "column": "Slinga", "pattern": "xExterna"},
    {"type": "remove_starts_with", "column": "Sign.", "pattern": "AVBOK"},
    {"type": "remove_starts_with", "column": "Sign.", "pattern": "SJUKHUS"},
]


def get_route_rules() -> list:
    """Get route rules from config."""
    cfg = _load_config()
    rules = cfg.get("route_rules")
    if rules is not None and isinstance(rules, list):
        return [r for r in rules if isinstance(r, dict) and r.get("type")]
    return list(DEFAULT_ROUTE_RULES)


def save_route_rules(rules: list) -> None:
    """Save route rules to config."""
    save_config_updates({"route_rules": rules})


def _apply_route_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Apply route rules: first fill_default_address, then filter rows."""
    rules = get_route_rules()
    default_addr = get_default_route_address()

    for rule in rules:
        rtype = rule.get("type", "")
        col = rule.get("column", "")

        if rtype == "fill_default_address" and col and col in df.columns and "Adress" in df.columns:
            prefixes = rule.get("prefixes", [])
            if not isinstance(prefixes, list):
                prefixes = [str(p).strip() for p in str(prefixes).split(",") if p.strip()]
            prefixes_upper = [str(p).strip().upper() for p in prefixes if p]

            df = df.copy()
            for idx in df.index:
                if _is_empty_value(df.at[idx, "Adress"]):
                    val = str(df.at[idx, col] or "").strip().upper()
                    for pre in prefixes_upper:
                        if val.startswith(pre):
                            df.at[idx, "Adress"] = default_addr
                            break

        elif rtype == "remove_empty" and col and col in df.columns:
            mask = df[col].apply(lambda v: not _is_empty_value(v))
            df = df[mask].reset_index(drop=True)

        elif rtype == "remove_starts_with" and col and col in df.columns:
            pattern = str(rule.get("pattern", "") or "").strip().upper()
            if pattern:
                mask = df[col].apply(
                    lambda v: not str(v or "").strip().upper().startswith(pattern)
                )
                df = df[mask].reset_index(drop=True)

    return df


def load_route_data(path: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load route data from Excel file."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {path}"
    if p.suffix.lower() not in {".xlsx", ".xls"}:
        return None, "Route data must be an Excel file (.xlsx or .xls)"
    try:
        df = pd.read_excel(path)
        if df.empty:
            return None, "File is empty"
        df.columns = df.columns.str.strip()
        required = set(AppConfig.ROUTE_DATA_COLUMNS)
        missing = required - set(df.columns)
        if missing:
            return None, f"Missing columns: {', '.join(sorted(missing))}"
        df = df[[c for c in AppConfig.ROUTE_DATA_COLUMNS if c in df.columns]]
        df = _apply_route_rules(df)
        return df, None
    except Exception as e:
        return None, f"Route load failed: {type(e).__name__}: {e}"


# =============================================================================
# Route grouping by date and Slinga
# =============================================================================


def build_routes_by_date(df: pd.DataFrame, default_address: str) -> dict:
    """
    Group route data by date, then by Slinga.
    Returns: {date_str: {slinga: [visit_dicts]}}
    Each visit has: starttid, sluttid, namn, adress, besokstyp, slinga
    If Namn is empty, use Besökstyp. If Adress is empty, use default_address.
    """
    from datetime import datetime

    result = {}
    if df is None or df.empty:
        return result

    for _, row in df.iterrows():
        starttid = row.get("Starttid")
        if pd.isna(starttid):
            continue
        try:
            if hasattr(starttid, "date"):
                dt = starttid
            else:
                dt = pd.to_datetime(starttid)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = "unknown"

        slinga = str(row.get("Slinga", "") or "").strip()
        if not slinga:
            slinga = "(ingen slinga)"

        namn_raw = row.get("Namn", "")
        namn = "" if _is_empty_value(namn_raw) else str(namn_raw).strip()
        besokstyp = str(row.get("Besökstyp", "") or "").strip()
        adress_val = row.get("Adress", "")
        adress = default_address if _is_empty_value(adress_val) else str(adress_val).strip()
        if adress == default_address:
            display_name = get_default_location_name()
        else:
            display_name = namn if namn else besokstyp

        visit = {
            "starttid": starttid,
            "sluttid": row.get("Sluttid"),
            "namn": display_name,
            "adress": adress,
            "besokstyp": besokstyp,
            "slinga": slinga,
        }

        if date_str not in result:
            result[date_str] = {}
        if slinga not in result[date_str]:
            result[date_str][slinga] = []
        result[date_str][slinga].append(visit)

    for date_str in result:
        for slinga in result[date_str]:
            result[date_str][slinga].sort(key=lambda v: (v["starttid"], v["adress"]))

    return result


def split_route_into_trips(visits: list, default_address: str) -> list:
    """
    Split a route's visits into trips. A visit to the default address (that is not
    the first or last visit) divides the route. The default visit belongs to the
    trip (as the last visit of the current trip).
    Returns: list of trips, each trip is a list of visit dicts.
    """
    if not visits:
        return []
    default_norm = default_address.strip().lower()
    trips = []
    current = []
    for i, v in enumerate(visits):
        addr = (v.get("adress") or "").strip().lower()
        is_default = addr == default_norm
        is_first = i == 0
        is_last = i == len(visits) - 1
        current.append(v)
        if is_default and not is_first and not is_last:
            trips.append(current)
            current = []
    if current:
        trips.append(current)
    return trips


# =============================================================================
# Export
# =============================================================================


def export_address_to_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_address_to_excel(df: pd.DataFrame, path: str) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


def export_route_to_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_route_to_excel(df: pd.DataFrame, path: str) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


# =============================================================================
# Geocoding with geocache
# =============================================================================


def _ensure_geocache_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS geocache (address TEXT PRIMARY KEY, lat REAL NOT NULL, lng REAL NOT NULL)"
    )
    conn.commit()


def _get_cached_coords(conn: sqlite3.Connection, address: str) -> Optional[Tuple[float, float]]:
    cur = conn.execute("SELECT lat, lng FROM geocache WHERE address = ?", (address.strip(),))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def _cache_coords(conn: sqlite3.Connection, address: str, lat: float, lng: float) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO geocache (address, lat, lng) VALUES (?, ?, ?)",
        (address.strip(), lat, lng),
    )
    conn.commit()


def _geocode_one(address: str, api_key: str, log_fn) -> Optional[Tuple[float, float]]:
    """Geocode single address. Uses cache first, then Google or Nominatim."""
    address = (address or "").strip()
    if not address:
        return None

    conn = sqlite3.connect(str(AppConfig.GEOCACHE_DB))
    _ensure_geocache_table(conn)
    cached = _get_cached_coords(conn, address)
    if cached:
        conn.close()
        return cached

    coords = None
    if api_key:
        try:
            import urllib.request
            import urllib.parse
            url = "https://maps.googleapis.com/maps/api/geocode/json?address=" + urllib.parse.quote(address) + "&key=" + api_key
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("status") == "OK" and data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    coords = (loc["lat"], loc["lng"])
        except Exception as e:
            log_fn(f"Google geocode failed for {address[:50]}...: {e}", "warn")

    if not coords:
        try:
            from geopy.geocoders import Nominatim
            from geopy.exc import GeocoderTimedOut, GeocoderServiceError
            locator = Nominatim(user_agent="toolbox_app")
            loc = locator.geocode(address, timeout=10)
            if loc:
                coords = (loc.latitude, loc.longitude)
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            log_fn(f"Geocoding failed for {address[:50]}...: {e}", "warn")

    if coords:
        _cache_coords(conn, address, coords[0], coords[1])
    conn.close()
    return coords


def geocode_addresses(
    df: pd.DataFrame, api_key: str, log_fn=None
) -> list:
    """
    Geocode addresses from address DataFrame (Färg, Förnamn, Efternamn, Adress).
    Returns list of {lat, lng, label, address, color}.
    """
    log_fn = log_fn or (lambda msg, lvl="info": None)
    result = []
    for i, row in df.iterrows():
        addr = str(row.get("Adress", "") or "").strip()
        if not addr or _is_empty_value(addr):
            continue
        coords = _geocode_one(addr, api_key, log_fn)
        if coords:
            fnamn = str(row.get("Förnamn", "") or "").strip()
            enamn = str(row.get("Efternamn", "") or "").strip()
            label = f"{fnamn} {enamn}".strip() or addr
            color = str(row.get("Färg", "#0078d4") or "#0078d4").strip()
            if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                color = "#0078d4"
            result.append({"lat": coords[0], "lng": coords[1], "label": label, "address": addr, "color": color})
        else:
            log_fn(f"Could not geocode: {addr[:60]}...", "warn")
    return result


def geocode_route_addresses(
    addresses: list, api_key: str, log_fn=None
) -> list:
    """
    Geocode a list of addresses (strings). Returns list of {lat, lng, address}.
    """
    log_fn = log_fn or (lambda msg, lvl="info": None)
    result = []
    for addr in addresses:
        addr = (addr or "").strip()
        if not addr:
            continue
        coords = _geocode_one(addr, api_key, log_fn)
        if coords:
            result.append({"lat": coords[0], "lng": coords[1], "address": addr})
        else:
            log_fn(f"Could not geocode: {addr[:60]}...", "warn")
    return result


# =============================================================================
# Color and display helpers
# =============================================================================


def parse_color_for_marker(val) -> str:
    """Parse color value for map marker."""
    s = str(val or "").strip()
    if re.match(r"^#[0-9A-Fa-f]{6}$", s):
        return s
    colors = {"r": "#e74c3c", "g": "#27ae60", "b": "#3498db", "y": "#f1c40f", "blå": "#3498db", "röd": "#e74c3c", "grön": "#27ae60", "gul": "#f1c40f"}
    return colors.get(s.lower(), "#0078d4")


def text_color_for_background(hex_color: str) -> str:
    """Return black or white for contrast on given background."""
    if not hex_color or len(hex_color) < 7:
        return "#000000"
    try:
        r = int(hex_color[1:3], 16) / 255
        g = int(hex_color[3:5], 16) / 255
        b = int(hex_color[5:7], 16) / 255
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return "#FFFFFF" if lum < 0.5 else "#000000"
    except Exception:
        return "#000000"


def title_case_display(s: str) -> str:
    """Title-case for display (e.g. names)."""
    if not s:
        return ""
    return " ".join(w.capitalize() if w else "" for w in str(s).split())


# =============================================================================
# Pin overlap offset
# =============================================================================


def apply_offset_for_overlapping_pins(markers: list) -> list:
    """Add label_offset_x/y for overlapping pins."""
    if not markers:
        return markers
    out = []
    for i, m in enumerate(markers):
        m = dict(m)
        m.setdefault("label_offset_x", 0)
        m.setdefault("label_offset_y", 0)
        for j, other in enumerate(markers):
            if i == j:
                continue
            if abs(m["lat"] - other["lat"]) < 0.0001 and abs(m["lng"] - other["lng"]) < 0.0001:
                m["label_offset_x"] = (i % 3 - 1) * 12
                m["label_offset_y"] = (i // 3) * 10
                break
        out.append(m)
    return out


# =============================================================================
# Leaflet map HTML (fallback)
# =============================================================================


def render_routes_map(
    markers: list,
    polylines: list,
    center_lat: float = 57.71,
    center_lng: float = 11.97,
) -> str:
    """Render Leaflet HTML for route pins and polylines (arrows)."""
    pins_js = json.dumps(
        [
            {
                "lat": m["lat"],
                "lng": m["lng"],
                "name": m.get("label", ""),
                "address": m.get("address", ""),
                "color": m.get("color", "#0078d4"),
            }
            for m in markers
        ]
    )
    lines_js = json.dumps([{"path": p["path"], "color": p.get("color", "#0078d4")} for p in polylines])
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script></head>
<body style="margin:0"><div id="map" style="width:100%;height:100vh;"></div>
<script>
const pins = {pins_js};
const polylines = {lines_js};
const map = L.map('map').setView([{center_lat}, {center_lng}], 12);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
pins.forEach((p, i) => {{
  const m = L.marker([p.lat, p.lng]).addTo(map);
  m.bindPopup('<b>' + (p.name || '') + '</b><br>' + (p.address || ''));
}});
polylines.forEach(pl => {{
  const latlngs = pl.path.map(x => [x[0], x[1]]);
  L.polyline(latlngs, {{ color: pl.color || '#0078d4', weight: 4, opacity: 0.8 }}).addTo(map);
}});
</script></body></html>
"""


def render_customer_map(
    markers: list, center_lat: float = 57.71, center_lng: float = 11.97
) -> str:
    """Render Leaflet HTML for customer pins."""
    pins_js = "[]"
    if markers:
        pins_js = json.dumps([{"lat": m["lat"], "lng": m["lng"], "name": m.get("label", ""), "color": m.get("color", "#0078d4")}])
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script></head>
<body style="margin:0"><div id="map" style="width:100%;height:100vh;"></div>
<script>
const pins = {pins_js};
const map = L.map('map').setView([{center_lat}, {center_lng}], 12);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
pins.forEach((p, i) => {{
  const m = L.marker([p.lat, p.lng]).addTo(map);
  m.bindPopup('<b>' + (p.name || '') + '</b>');
}});
</script></body></html>
"""
