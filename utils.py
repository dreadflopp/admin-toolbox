"""
Compatibility layer: Re-exports from refactored modules.
This file maintains backward compatibility while the codebase is migrated.
"""

# Config helpers
from config_helpers import (
    load_google_maps_api_key,
    config_disable_webengine_map,
    config_prefer_leaflet_map,
    get_default_route_address,
    get_default_location_name,
    get_routines_folder,
    save_routines_folder,
    get_routines_default_file,
    save_routines_default_file,
    get_routines_colors,
    save_routine_color,
    get_routines_zoom,
    save_routine_zoom,
    get_routines_order,
    save_routines_order,
    save_config_updates,
)

# Export functions
from export import (
    export_address_to_csv,
    export_address_to_excel,
    export_route_to_csv,
    export_route_to_excel,
)

# PDF extraction
from pdf_extraction import (
    extract_pdf_data,
    validate_address_columns,
)

# Geocoding
from geocoding import (
    geocode_addresses,
    geocode_route_addresses,
    clear_geocache,
    _geocode_one,  # Used by windows.py
)

# Route processing
from route_processing import (
    get_break_names,
    get_break_lunch_window,
    get_break_evening_window,
    get_break_morning_afternoon_window,
    get_break_afternoon_evening_window,
    save_break_settings,
    get_route_sort_order,
    save_route_sort_order,
    get_route_color_rules,
    save_route_color_rules,
    get_route_colors,
    get_route_rules,
    save_route_rules,
    DEFAULT_ROUTE_RULES,
    DEFAULT_ROUTE_COLOR,
    DEFAULT_ROUTE_COLOR_RULES,
    ROUTE_COLOR_PRESETS,
    TRIP_NAMES,
    load_route_data,
    build_routes_by_date,
    split_route_into_trips,
    sort_routes_for_display,
    get_default_customer,
    _get_trip_visits,  # Used by windows.py
)

# Map server
from map_server import (
    start_map_server,
    get_map_url,
)

# Map rendering
from map_rendering import (
    parse_color_for_marker,
    text_color_for_background,
    title_case_display,
    apply_offset_for_overlapping_pins,
    render_routes_map,
    render_customer_map,
)
