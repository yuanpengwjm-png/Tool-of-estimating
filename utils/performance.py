import numpy as np
import pandas as pd

from utils.approx_ahp import filter_group


def guess_scheme_and_criterion(column_name: str) -> tuple[str, str]:
    """Guess scheme and criterion names from a wide performance score column."""
    cleaned = str(column_name).replace("_", " ").replace("-", " ").strip()
    lower = cleaned.lower()
    if lower.endswith(" score"):
        cleaned = cleaned[:-6].strip()

    words = cleaned.split()
    if len(words) >= 3 and words[0].lower() == "scheme":
        return " ".join(words[:2]), " ".join(words[2:])
    if len(words) >= 2:
        return words[0], " ".join(words[1:])
    return cleaned, cleaned


def aggregate_wide_performance(
    df: pd.DataFrame,
    column_map: dict[str, tuple[str, str]],
    groups: list[dict],
) -> pd.DataFrame:
    """Aggregate wide score columns into scheme-by-criterion performance values."""
    rows = []
    for group in groups:
        group_df = filter_group(df, group.get("filters", {}))
        if group_df.empty:
            continue

        group_weight = float(group.get("weight", 1.0))
        for source_col, (scheme, criterion) in column_map.items():
            scores = pd.to_numeric(group_df[source_col], errors="coerce")
            rows.append(
                {
                    "Group": group.get("name", "Group"),
                    "Respondents": int(scores.notna().sum()),
                    "Group weight": group_weight,
                    "Scheme": scheme,
                    "Criterion": criterion,
                    "Performance score": float(scores.mean(skipna=True)),
                }
            )

    return _weighted_group_profile(pd.DataFrame(rows))


def aggregate_long_performance(
    df: pd.DataFrame,
    scheme_col: str,
    criterion_col: str,
    score_col: str,
    groups: list[dict],
) -> pd.DataFrame:
    """Aggregate long-format performance data into scheme-by-criterion values."""
    rows = []
    for group in groups:
        group_df = filter_group(df, group.get("filters", {}))
        if group_df.empty:
            continue

        grouped = (
            group_df.assign(**{"__score": pd.to_numeric(group_df[score_col], errors="coerce")})
            .groupby([scheme_col, criterion_col], dropna=True)["__score"]
            .agg(["mean", "count"])
            .reset_index()
        )
        for _, item in grouped.iterrows():
            rows.append(
                {
                    "Group": group.get("name", "Group"),
                    "Respondents": int(item["count"]),
                    "Group weight": float(group.get("weight", 1.0)),
                    "Scheme": str(item[scheme_col]),
                    "Criterion": str(item[criterion_col]),
                    "Performance score": float(item["mean"]),
                }
            )

    return _weighted_group_profile(pd.DataFrame(rows))


def _weighted_group_profile(group_scores: pd.DataFrame) -> pd.DataFrame:
    if group_scores.empty:
        return group_scores

    rows = []
    for (scheme, criterion), block in group_scores.groupby(["Scheme", "Criterion"]):
        weights = block["Group weight"].astype(float).clip(lower=0)
        if np.isclose(weights.sum(), 0.0):
            weights = pd.Series(np.ones(len(block)), index=block.index)
        weights = weights / weights.sum()
        rows.append(
            {
                "Scheme": scheme,
                "Criterion": criterion,
                "Performance score": float((block["Performance score"] * weights).sum()),
                "Total respondents": int(block["Respondents"].sum()),
            }
        )
    return pd.DataFrame(rows)


def normalize_performance(
    performance_df: pd.DataFrame,
    lower_is_better: list[str] | None = None,
    method: str = "rating_scale",
    score_min: float = 0.0,
    score_max: float = 10.0,
) -> pd.DataFrame:
    """Normalize performance scores to 0-1 within each criterion."""
    lower_is_better = lower_is_better or []
    result = performance_df.copy()
    normalized_values = []

    for criterion, block in result.groupby("Criterion", sort=False):
        values = block["Performance score"].astype(float)
        if method == "rating_scale":
            denominator = score_max - score_min
            if np.isclose(denominator, 0.0):
                normalized = pd.Series(np.zeros(len(values)), index=values.index)
            elif criterion in lower_is_better:
                normalized = (score_max - values) / denominator
            else:
                normalized = (values - score_min) / denominator
            normalized = normalized.clip(lower=0.0, upper=1.0)
        elif criterion in lower_is_better:
            min_value = values.min()
            max_value = values.max()
            if np.isclose(max_value, min_value):
                normalized = pd.Series(np.ones(len(values)), index=values.index)
            else:
                normalized = (max_value - values) / (max_value - min_value)
        else:
            min_value = values.min()
            max_value = values.max()
            if np.isclose(max_value, min_value):
                normalized = pd.Series(np.ones(len(values)), index=values.index)
            else:
                normalized = (values - min_value) / (max_value - min_value)
        normalized_values.append(normalized)

    result["Normalized performance"] = pd.concat(normalized_values).sort_index()
    result["Normalization method"] = method
    return result


def score_schemes(weights_df: pd.DataFrame, performance_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Combine criterion weights and normalized performance into scheme scores."""
    weights = weights_df.rename(columns={"Weight": "Criterion weight"})
    merged = performance_df.merge(weights, on="Criterion", how="inner")
    merged["Weighted contribution"] = (
        merged["Criterion weight"] * merged["Normalized performance"]
    )
    scores = (
        merged.groupby("Scheme", as_index=False)["Weighted contribution"]
        .sum()
        .rename(columns={"Weighted contribution": "Non-monetary score"})
        .sort_values("Non-monetary score", ascending=False)
        .reset_index(drop=True)
    )
    scores["Rank"] = range(1, len(scores) + 1)
    return scores, merged
