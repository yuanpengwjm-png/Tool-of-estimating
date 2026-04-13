from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DetectionResult:
    data_type: str
    method_label: str
    reason: str
    confidence: float


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(pd.to_numeric, errors="coerce")


def extract_pairwise_matrix(df: pd.DataFrame) -> tuple[list[str], np.ndarray] | None:
    """Extract a square pairwise matrix from common Excel layouts."""
    clean = df.dropna(how="all").dropna(axis=1, how="all").copy()
    if clean.empty:
        return None

    numeric_all = _coerce_numeric(clean)
    if clean.shape[0] == clean.shape[1] and numeric_all.notna().all().all():
        criteria = [str(col) for col in clean.columns]
        return criteria, numeric_all.to_numpy(dtype=float)

    # Common format: first column contains criterion names, remaining columns are numeric.
    if clean.shape[1] >= 2:
        criteria = clean.iloc[:, 0].astype(str).tolist()
        matrix_df = _coerce_numeric(clean.iloc[:, 1:])
        if matrix_df.shape[0] == matrix_df.shape[1] and matrix_df.notna().all().all():
            return criteria, matrix_df.to_numpy(dtype=float)

    return None


def _reciprocal_score(matrix: np.ndarray) -> float:
    n = matrix.shape[0]
    checks = []
    for i in range(n):
        checks.append(np.isclose(matrix[i, i], 1.0, atol=0.05))
        for j in range(i + 1, n):
            if matrix[i, j] > 0 and matrix[j, i] > 0:
                checks.append(np.isclose(matrix[i, j] * matrix[j, i], 1.0, rtol=0.12, atol=0.05))
            else:
                checks.append(False)
    return float(np.mean(checks)) if checks else 0.0


def candidate_rating_columns(df: pd.DataFrame) -> list[str]:
    """Find numeric columns that look like questionnaire importance ratings."""
    candidates = []
    for col in df.columns:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        min_value = series.min()
        max_value = series.max()
        unique_count = series.nunique()
        unique_ratio = unique_count / max(len(series), 1)
        small_sample = len(series) <= 20
        looks_like_id = unique_ratio > 0.95 and max_value > 10
        if (
            0 <= min_value
            and max_value <= 10
            and unique_count <= 11
            and not looks_like_id
            and (small_sample or unique_ratio <= 0.8)
        ):
            candidates.append(col)
    return candidates


def candidate_demographic_columns(df: pd.DataFrame) -> list[str]:
    """Find categorical columns that are useful for stakeholder grouping filters."""
    candidates = []
    for col in df.columns:
        series = df[col].dropna()
        if series.empty:
            continue
        unique_count = series.astype(str).nunique()
        unique_ratio = unique_count / max(len(series), 1)
        if df[col].dtype == "object" and 1 < unique_count <= 20:
            candidates.append(col)
        elif unique_count <= 12 and unique_ratio <= 0.5:
            candidates.append(col)
    return candidates


def detect_dataset_type(df: pd.DataFrame) -> DetectionResult:
    """Classify an uploaded sheet as pairwise AHP, rating data, or unknown."""
    extracted = extract_pairwise_matrix(df)
    if extracted is not None:
        _, matrix = extracted
        if matrix.shape[0] >= 2 and np.all(matrix > 0):
            score = _reciprocal_score(matrix)
            if score >= 0.8:
                return DetectionResult(
                    data_type="pairwise",
                    method_label="Standard AHP pairwise comparison matrix",
                    reason=(
                        "The sheet contains a positive square matrix with reciprocal "
                        "judgements and diagonal values close to 1."
                    ),
                    confidence=score,
                )

    ratings = candidate_rating_columns(df)
    demographics = candidate_demographic_columns(df)
    if len(ratings) >= 2:
        return DetectionResult(
            data_type="ratings",
            method_label="Rating-based approximate AHP questionnaire data",
            reason=(
                f"The sheet has {len(ratings)} numeric rating-like columns and "
                f"{len(demographics)} possible demographic/filter columns."
            ),
            confidence=min(0.95, 0.55 + len(ratings) * 0.06),
        )

    return DetectionResult(
        data_type="unknown",
        method_label="Unknown format",
        reason="The sheet is neither a reciprocal square matrix nor a clear rating questionnaire table.",
        confidence=0.0,
    )
