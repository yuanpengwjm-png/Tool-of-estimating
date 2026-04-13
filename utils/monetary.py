import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


TEMPLATE_LABELS = {
    "quantity_unit_price": "quantity * unit_price",
    "quantity_distance_transport_rate": "quantity * distance * transport_rate",
    "fixed_plus_variable": "fixed_cost + variable_cost",
    "percentage_surcharge": "percentage surcharge",
    "sum_components": "sum of selected components",
}


@dataclass
class MonetaryResults:
    component_results: pd.DataFrame
    totals: pd.DataFrame
    constraints: pd.DataFrame
    scores: pd.DataFrame


def factor_value_lookup(factor_values: pd.DataFrame) -> dict[tuple[str, str], float]:
    lookup = {}
    for _, row in factor_values.iterrows():
        scheme = str(row.get("Scheme", "Global")).strip() or "Global"
        factor = str(row.get("Factor", "")).strip()
        value = pd.to_numeric(row.get("Value"), errors="coerce")
        if factor and not pd.isna(value):
            lookup[(scheme, factor)] = float(value)
    return lookup


def resolve_factor(
    lookup: dict[tuple[str, str], float],
    scheme: str,
    factor: str | float | None,
) -> float:
    if factor is None or pd.isna(factor) or str(factor).strip() == "":
        return 0.0
    factor_name = str(factor).strip()
    if (scheme, factor_name) in lookup:
        return lookup[(scheme, factor_name)]
    return lookup.get(("Global", factor_name), 0.0)


def calculate_component_results(
    schemes: list[str],
    factor_values: pd.DataFrame,
    components: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate component-level monetary outcomes from approved templates."""
    lookup = factor_value_lookup(factor_values)
    rows = []

    for scheme in schemes:
        component_values: dict[str, float] = {}
        for _, component in components.iterrows():
            included = component.get("Included", True)
            if pd.isna(included) or not bool(included):
                continue

            name = str(component.get("Component", "")).strip()
            template = str(component.get("Template", "")).strip()
            category = str(component.get("Category", "")).strip()
            factor_a = component.get("Factor A")
            factor_b = component.get("Factor B")
            factor_c = component.get("Factor C")
            refs = str(component.get("Component refs", "")).strip()

            value_a = resolve_factor(lookup, scheme, factor_a)
            value_b = resolve_factor(lookup, scheme, factor_b)
            value_c = resolve_factor(lookup, scheme, factor_c)

            if template == "quantity_unit_price":
                result = value_a * value_b
                formula = f"{factor_a} * {factor_b}"
            elif template == "quantity_distance_transport_rate":
                result = value_a * value_b * value_c
                formula = f"{factor_a} * {factor_b} * {factor_c}"
            elif template == "fixed_plus_variable":
                result = value_a + value_b
                formula = f"{factor_a} + {factor_b}"
            elif template == "percentage_surcharge":
                base = sum(component_values.get(ref.strip(), 0.0) for ref in refs.split(",") if ref.strip())
                result = base * value_a / 100.0
                formula = f"sum({refs}) * {factor_a} / 100"
            elif template == "sum_components":
                result = sum(component_values.get(ref.strip(), 0.0) for ref in refs.split(",") if ref.strip())
                formula = f"sum({refs})"
            else:
                result = 0.0
                formula = "Unknown template"

            component_values[name] = float(result)
            rows.append(
                {
                    "Scheme": scheme,
                    "Component": name,
                    "Category": category,
                    "Template": TEMPLATE_LABELS.get(template, template),
                    "Formula mapping": formula,
                    "Cost": float(result),
                }
            )

    return pd.DataFrame(rows)


def calculate_totals(component_results: pd.DataFrame) -> pd.DataFrame:
    if component_results.empty:
        return pd.DataFrame(columns=["Scheme", "Total cost", "Difference from lowest"])

    totals = (
        component_results.groupby("Scheme", as_index=False)["Cost"]
        .sum()
        .rename(columns={"Cost": "Total cost"})
    )
    lowest = totals["Total cost"].min()
    totals["Difference from lowest"] = totals["Total cost"] - lowest
    return totals.sort_values("Total cost").reset_index(drop=True)


def check_constraints(
    schemes: list[str],
    factors: pd.DataFrame,
    factor_values: pd.DataFrame,
    constraints: pd.DataFrame,
) -> pd.DataFrame:
    """Check required factors and simple user-defined constraints."""
    lookup = factor_value_lookup(factor_values)
    rows = []

    for scheme in schemes:
        for _, factor in factors.iterrows():
            factor_name = str(factor.get("Factor", "")).strip()
            if not factor_name:
                continue
            value = resolve_factor(lookup, scheme, factor_name)
            required = factor.get("Required", False)
            if pd.isna(required):
                required = False
            if bool(required) and math.isclose(value, 0.0):
                rows.append(
                    {
                        "Scheme": scheme,
                        "Constraint": f"{factor_name} is required",
                        "Status": "Violation",
                        "Detail": "Required factor is missing or zero.",
                    }
                )

        for _, constraint in constraints.iterrows():
            enabled = constraint.get("Enabled", True)
            if pd.isna(enabled) or not bool(enabled):
                continue

            factor_name = str(constraint.get("Factor", "")).strip()
            constraint_type = str(constraint.get("Type", "")).strip()
            limit = pd.to_numeric(constraint.get("Value"), errors="coerce")
            other_factor = str(constraint.get("Other factor", "")).strip()
            allowed_values = str(constraint.get("Allowed values", "")).strip()
            value = resolve_factor(lookup, scheme, factor_name)

            status = "OK"
            detail = ""
            if constraint_type == "Min" and not pd.isna(limit) and value < limit:
                status = "Violation"
                detail = f"{factor_name}={value:g} is below minimum {limit:g}."
            elif constraint_type == "Max" and not pd.isna(limit) and value > limit:
                status = "Violation"
                detail = f"{factor_name}={value:g} is above maximum {limit:g}."
            elif constraint_type == "Equal" and not pd.isna(limit) and not np.isclose(value, limit):
                status = "Violation"
                detail = f"{factor_name}={value:g} is not equal to {limit:g}."
            elif constraint_type in {"Ratio max", "Ratio min"}:
                other_value = resolve_factor(lookup, scheme, other_factor)
                ratio = np.nan if np.isclose(other_value, 0.0) else value / other_value
                if pd.isna(ratio):
                    status = "Violation"
                    detail = f"{other_factor} is zero, so the ratio cannot be checked."
                elif constraint_type == "Ratio max" and not pd.isna(limit) and ratio > limit:
                    status = "Violation"
                    detail = f"{factor_name}/{other_factor}={ratio:g} is above {limit:g}."
                elif constraint_type == "Ratio min" and not pd.isna(limit) and ratio < limit:
                    status = "Violation"
                    detail = f"{factor_name}/{other_factor}={ratio:g} is below {limit:g}."
            elif constraint_type == "Allowed values" and allowed_values:
                allowed = [item.strip() for item in allowed_values.split(",") if item.strip()]
                if str(value) not in allowed and f"{value:g}" not in allowed:
                    status = "Violation"
                    detail = f"{factor_name}={value:g} is not in allowed values: {allowed_values}."
            elif constraint_type == "Advisory note":
                status = "Risk"
                detail = str(constraint.get("Notes", "")).strip() or "Manual expert review recommended."

            if status != "OK":
                rows.append(
                    {
                        "Scheme": scheme,
                        "Constraint": f"{constraint_type}: {factor_name}",
                        "Status": status,
                        "Detail": detail,
                    }
                )

    if not rows:
        return pd.DataFrame(columns=["Scheme", "Constraint", "Status", "Detail"])
    return pd.DataFrame(rows)


def calculate_monetary_scores(
    totals: pd.DataFrame,
    constraint_report: pd.DataFrame,
    method: str,
) -> pd.DataFrame:
    if totals.empty:
        return pd.DataFrame(columns=["Scheme", "Total cost", "Valid scheme", "Monetary score", "Rank"])

    invalid_schemes = set(
        constraint_report.loc[constraint_report["Status"] == "Violation", "Scheme"].tolist()
    ) if not constraint_report.empty else set()

    scores = totals.copy()
    scores["Valid scheme"] = ~scores["Scheme"].isin(invalid_schemes)
    valid_costs = scores.loc[scores["Valid scheme"], "Total cost"]

    if valid_costs.empty:
        scores["Monetary score"] = 0.0
    elif method == "inverse_cost":
        min_cost = valid_costs.min()
        scores["Monetary score"] = scores.apply(
            lambda row: min_cost / row["Total cost"]
            if row["Valid scheme"] and row["Total cost"] > 0
            else 0.0,
            axis=1,
        )
    else:
        min_cost = valid_costs.min()
        max_cost = valid_costs.max()
        if np.isclose(max_cost, min_cost):
            scores["Monetary score"] = scores["Valid scheme"].map(lambda valid: 1.0 if valid else 0.0)
        else:
            scores["Monetary score"] = scores.apply(
                lambda row: (max_cost - row["Total cost"]) / (max_cost - min_cost)
                if row["Valid scheme"]
                else 0.0,
                axis=1,
            )

    scores = scores.sort_values("Monetary score", ascending=False).reset_index(drop=True)
    scores["Rank"] = range(1, len(scores) + 1)
    return scores
