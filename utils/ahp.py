from dataclasses import dataclass

import numpy as np


RANDOM_INDEX = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}


@dataclass
class AHPResult:
    criteria: list[str]
    weights: np.ndarray
    lambda_max: float
    consistency_index: float
    consistency_ratio: float
    is_consistent: bool


def calculate_ahp(matrix: np.ndarray, criteria: list[str]) -> AHPResult:
    """Calculate standard AHP weights and consistency statistics."""
    values = np.asarray(matrix, dtype=float)
    if values.shape[0] != values.shape[1]:
        raise ValueError("AHP matrix must be square.")
    if np.any(values <= 0):
        raise ValueError("AHP matrix values must be positive.")

    eigenvalues, eigenvectors = np.linalg.eig(values)
    max_index = int(np.argmax(eigenvalues.real))
    lambda_max = float(eigenvalues[max_index].real)
    principal_vector = np.abs(eigenvectors[:, max_index].real)
    weights = principal_vector / principal_vector.sum()

    n = values.shape[0]
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = 0.0 if ri == 0 else ci / ri

    return AHPResult(
        criteria=criteria,
        weights=weights,
        lambda_max=lambda_max,
        consistency_index=float(ci),
        consistency_ratio=float(cr),
        is_consistent=cr <= 0.10,
    )
