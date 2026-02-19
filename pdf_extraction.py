"""
PDF extraction utilities for address source files.
"""

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import pdfplumber

from config import AppConfig


def _normalize_header(cell: str) -> str:
    """Normalize header cell value."""
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
