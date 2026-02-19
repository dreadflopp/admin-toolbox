"""
Geocoding utilities with caching support.
"""

import hashlib
import json
import re
import sqlite3
from typing import Optional, Tuple

import pandas as pd

from config import AppConfig


def _hash_address(address: str) -> str:
    """Hash address for storage. Strips whitespace first."""
    return hashlib.sha256(address.strip().encode("utf-8")).hexdigest()


def _ensure_geocache_table(conn: sqlite3.Connection) -> None:
    """Create geocache table. Migrates old schema (address) to new (address_hash) if needed."""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='geocache'")
    if cur.fetchone():
        cur = conn.execute("PRAGMA table_info(geocache)")
        cols = [row[1] for row in cur.fetchall()]
        if "address" in cols and "address_hash" not in cols:
            conn.execute("DROP TABLE geocache")
            conn.commit()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS geocache (address_hash TEXT PRIMARY KEY, lat REAL NOT NULL, lng REAL NOT NULL)"
    )
    conn.commit()


def _get_cached_coords(conn: sqlite3.Connection, address: str) -> Optional[Tuple[float, float]]:
    """Get cached coordinates for an address."""
    addr_hash = _hash_address(address)
    cur = conn.execute("SELECT lat, lng FROM geocache WHERE address_hash = ?", (addr_hash,))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def _cache_coords(conn: sqlite3.Connection, address: str, lat: float, lng: float) -> None:
    """Cache coordinates for an address."""
    addr_hash = _hash_address(address)
    conn.execute(
        "INSERT OR REPLACE INTO geocache (address_hash, lat, lng) VALUES (?, ?, ?)",
        (addr_hash, lat, lng),
    )
    conn.commit()


def clear_geocache() -> int:
    """Delete all cached address data. Returns number of rows deleted."""
    if not AppConfig.GEOCACHE_DB.exists():
        return 0
    try:
        conn = sqlite3.connect(str(AppConfig.GEOCACHE_DB))
        cur = conn.execute("SELECT COUNT(*) FROM geocache")
        count = cur.fetchone()[0]
        conn.execute("DELETE FROM geocache")
        conn.commit()
        conn.close()
        return count
    except sqlite3.OperationalError:
        return 0


def _is_empty_value(val) -> bool:
    """Treat NaN, None, empty string, and string 'nan' as empty."""
    if val is None:
        return True
    if pd.isna(val):
        return True
    s = str(val).strip()
    return s == "" or s.lower() == "nan" or s.lower() == "none"


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
