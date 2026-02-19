"""
Map rendering utilities for Leaflet HTML generation.
"""

import json
import re


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
