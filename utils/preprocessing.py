import pandas as pd


def missing_value_report(df: pd.DataFrame) -> pd.DataFrame:
    """Return missing-value counts and percentages for every column."""
    total_rows = len(df)
    missing = df.isna().sum()
    percent = (missing / total_rows * 100).round(2) if total_rows else missing
    return pd.DataFrame(
        {
            "Column": missing.index,
            "Missing values": missing.values,
            "Missing percent": percent.values,
            "Data type": [str(dtype) for dtype in df.dtypes],
        }
    )
