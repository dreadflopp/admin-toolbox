"""
Compatibility layer: Re-exports from refactored window modules.
This file maintains backward compatibility while the codebase is migrated.
"""

# Common components
from windows_common import (
    HAS_WEBENGINE,
    MapPage,
    MARKER_INDEX_ROLE,
    VISIT_ROLE,
    SELECTION_BG,
    SELECTION_TEXT,
    CUSTOM_PIN_ID_BASE,
    CustomerTableDelegate,
    CollapsibleSection,
    CustomAddressesSection,
    _add_default_customer,
)

# Window classes
from customer_map_window import CustomerListMapWindow
from routes_map_window import RoutesMapWindow
from rule_editor_window import RuleEditorWindow, _rule_to_display
