import numpy as np
import pandas as pd


def filter_group(df: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    """Apply stakeholder group filters to a questionnaire dataframe."""
    group_df = df.copy()
    for col, selected_values in filters.items():
        if selected_values:
            group_df = group_df[group_df[col].astype(str).isin(selected_values)]
    return group_df


def _normalise(values: pd.Series) -> pd.Series:
    values = values.astype(float).clip(lower=0)
    total = values.sum()
    if np.isclose(total, 0.0):
        return pd.Series(np.zeros(len(values)), index=values.index)
    return values / total


def aggregate_group_weights(
    df: pd.DataFrame,
    rating_cols: list[str],
    groups: list[dict],
) -> pd.DataFrame:
    """Compute criterion weights inside each group and attach group weights."""
    rows = []
    for group in groups:
        group_df = filter_group(df, group.get("filters", {}))
        if group_df.empty:
            continue

        numeric_ratings = group_df[rating_cols].apply(pd.to_numeric, errors="coerce")
        mean_scores = numeric_ratings.mean(skipna=True).fillna(0)
        criterion_weights = _normalise(mean_scores)

        row = {
            "Group": group.get("name", "Group"),
            "Respondents": len(group_df),
            "Group weight": float(group.get("weight", 1.0)),
        }
        row.update({col: float(criterion_weights[col]) for col in rating_cols})
        rows.append(row)

    return pd.DataFrame(rows)


def calculate_rating_weights(group_result: pd.DataFrame, rating_cols: list[str]) -> pd.Series:
    """Aggregate group-level approximate AHP weights into an overall result."""
    group_weights = group_result["Group weight"].astype(float).clip(lower=0)
    if np.isclose(group_weights.sum(), 0.0):
        group_weights = pd.Series(np.ones(len(group_result)), index=group_result.index)
    group_weights = group_weights / group_weights.sum()

    weighted = group_result[rating_cols].multiply(group_weights, axis=0)
    overall = weighted.sum(axis=0)
    total = overall.sum()
    return overall / total if not np.isclose(total, 0.0) else overall
