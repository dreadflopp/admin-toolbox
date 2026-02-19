"""
Export functions for CSV and Excel formats.
"""

import pandas as pd


def export_address_to_csv(df: pd.DataFrame, path: str) -> None:
    """Export address data to CSV."""
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_address_to_excel(df: pd.DataFrame, path: str) -> None:
    """Export address data to Excel."""
    df.to_excel(path, index=False, engine="openpyxl")


def export_route_to_csv(df: pd.DataFrame, path: str) -> None:
    """Export route data to CSV."""
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_route_to_excel(df: pd.DataFrame, path: str) -> None:
    """Export route data to Excel."""
    df.to_excel(path, index=False, engine="openpyxl")
