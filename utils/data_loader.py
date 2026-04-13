from typing import BinaryIO

import pandas as pd


def load_excel_sheets(uploaded_file: BinaryIO) -> dict[str, pd.DataFrame]:
    """Read all sheets from an uploaded Excel workbook."""
    return pd.read_excel(uploaded_file, sheet_name=None, engine="openpyxl")
