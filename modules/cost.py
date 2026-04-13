from io import BytesIO

import pandas as pd
import streamlit as st

from utils.monetary import (
    TEMPLATE_LABELS,
    calculate_component_results,
    calculate_monetary_scores,
    calculate_totals,
    check_constraints,
)
from utils.visualization import bar_chart


def _default_schemes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Scheme": ["Scheme A", "Scheme B"],
            "Description": ["Candidate option A", "Candidate option B"],
            "Included": [True, True],
        }
    )


def _default_factors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Factor": [
                "material_quantity",
                "material_unit_price",
                "transport_distance",
                "transport_rate",
                "labor_cost",
                "equipment_cost",
                "admin_cost",
                "surcharge_percent",
                "recycled_ratio",
            ],
            "Label / category": [
                "Material",
                "Material",
                "Transport",
                "Transport",
                "Construction",
                "Construction",
                "Administration",
                "Risk",
                "Material",
            ],
            "Default value": [1000, 75, 35, 1.8, 12000, 9000, 5000, 5, 0.3],
            "Unit": ["tonne", "$/tonne", "km", "$/tonne/km", "$", "$", "$", "%", "ratio"],
            "Varies by scheme": [True, True, True, False, True, True, False, False, True],
            "Required": [True, True, True, True, True, True, True, False, False],
            "Constrained": [False, False, True, False, False, False, False, False, True],
        }
    )


def _default_components() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Component": [
                "Material cost",
                "Transport cost",
                "Construction cost",
                "Administration",
                "Risk surcharge",
            ],
            "Category": ["Material", "Transport", "Construction", "Administration", "Risk"],
            "Template": [
                "quantity_unit_price",
                "quantity_distance_transport_rate",
                "fixed_plus_variable",
                "fixed_plus_variable",
                "percentage_surcharge",
            ],
            "Factor A": [
                "material_quantity",
                "material_quantity",
                "labor_cost",
                "admin_cost",
                "surcharge_percent",
            ],
            "Factor B": [
                "material_unit_price",
                "transport_distance",
                "equipment_cost",
                "",
                "",
            ],
            "Factor C": ["", "transport_rate", "", "", ""],
            "Component refs": [
                "",
                "",
                "",
                "",
                "Material cost,Transport cost,Construction cost,Administration",
            ],
            "Included": [True, True, True, True, True],
        }
    )


def _default_constraints() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Enabled": [True, True],
            "Factor": ["recycled_ratio", "transport_distance"],
            "Type": ["Min", "Max"],
            "Value": [0.2, 80],
            "Other factor": ["", ""],
            "Allowed values": ["", ""],
            "Notes": [
                "Flag schemes with too little recycled content.",
                "Long haul distances may be infeasible or risky.",
            ],
        }
    )


def _make_factor_values(schemes: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    active_schemes = _active_scheme_names(schemes)
    for _, factor in factors.iterrows():
        factor_name = str(factor["Factor"]).strip()
        if not factor_name:
            continue
        varies_by_scheme = bool(factor.get("Varies by scheme", False))
        if pd.isna(factor.get("Varies by scheme", False)):
            varies_by_scheme = False
        if varies_by_scheme:
            for scheme in active_schemes:
                rows.append(
                    {
                        "Scheme": scheme,
                        "Factor": factor_name,
                        "Value": factor["Default value"],
                        "Unit": factor["Unit"],
                    }
                )
        else:
            rows.append(
                {
                    "Scheme": "Global",
                    "Factor": factor_name,
                    "Value": factor["Default value"],
                    "Unit": factor["Unit"],
                }
            )
    return pd.DataFrame(rows)


def _active_scheme_names(schemes: pd.DataFrame) -> list[str]:
    included_mask = schemes["Included"].map(lambda value: False if pd.isna(value) else bool(value))
    return schemes.loc[included_mask, "Scheme"].dropna().astype(str).tolist()


def _sync_factor_values_to_active_schemes(
    factor_values: pd.DataFrame,
    schemes: pd.DataFrame,
) -> pd.DataFrame:
    active_names = set(_active_scheme_names(schemes))
    allowed_names = active_names | {"Global"}
    if factor_values.empty or "Scheme" not in factor_values:
        return factor_values
    return factor_values[factor_values["Scheme"].astype(str).isin(allowed_names)].reset_index(drop=True)


def _download_excel(tables: dict[str, pd.DataFrame], file_name: str) -> None:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    st.download_button(
        "Download Excel report",
        data=output.getvalue(),
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _initialise_monetary_state() -> None:
    st.session_state.setdefault("monetary_schemes", _default_schemes())
    st.session_state.setdefault("monetary_factors", _default_factors())
    st.session_state.setdefault("monetary_components", _default_components())
    st.session_state.setdefault("monetary_constraints", _default_constraints())


def _render_factor_definition() -> tuple[pd.DataFrame, pd.DataFrame]:
    st.write(
        "Define candidate schemes and monetary factors. Factors can be global or vary by scheme. "
        "These values feed structured cost templates rather than unrestricted formulas."
    )

    st.subheader("Candidate schemes")
    schemes = st.data_editor(
        st.session_state["monetary_schemes"],
        num_rows="dynamic",
        use_container_width=True,
        key="monetary_schemes_editor",
        column_config={"Included": st.column_config.CheckboxColumn()},
    )
    st.session_state["monetary_schemes"] = schemes
    st.caption(
        "取消 Included 会让该方案不参与计算。若想清理下面旧的 factor values，点击同步按钮即可。"
    )

    st.subheader("Monetary factors")
    factors = st.data_editor(
        st.session_state["monetary_factors"],
        num_rows="dynamic",
        use_container_width=True,
        key="monetary_factors_editor",
        column_config={
            "Varies by scheme": st.column_config.CheckboxColumn(),
            "Required": st.column_config.CheckboxColumn(),
            "Constrained": st.column_config.CheckboxColumn(),
        },
    )
    st.session_state["monetary_factors"] = factors

    st.subheader("Factor values")
    left, right = st.columns(2)
    with left:
        regenerate = st.button("Generate / refresh factor value table from schemes and factors")
    with right:
        sync_active = st.button("Remove inactive schemes from factor values")
    if regenerate or "monetary_factor_values" not in st.session_state:
        st.session_state["monetary_factor_values"] = _make_factor_values(schemes, factors)
    elif sync_active:
        st.session_state["monetary_factor_values"] = _sync_factor_values_to_active_schemes(
            st.session_state["monetary_factor_values"],
            schemes,
        )

    factor_values = st.data_editor(
        st.session_state["monetary_factor_values"],
        num_rows="dynamic",
        use_container_width=True,
        key="monetary_factor_values_editor",
    )
    st.session_state["monetary_factor_values"] = factor_values
    return schemes, factor_values


def _render_constraints() -> pd.DataFrame:
    st.write(
        "Define simple checks. This first version stores and checks constraints; it does not "
        "solve an optimization problem or automatically design a best scheme."
    )
    with st.form("monetary_constraints_form"):
        constraints = st.data_editor(
            st.session_state["monetary_constraints"],
            num_rows="dynamic",
            use_container_width=True,
            key="monetary_constraints_editor",
            column_config={
                "Enabled": st.column_config.CheckboxColumn(),
                "Type": st.column_config.SelectboxColumn(
                    options=[
                        "Min",
                        "Max",
                        "Equal",
                        "Ratio max",
                        "Ratio min",
                        "Allowed values",
                        "Advisory note",
                    ]
                ),
            },
        )
        saved = st.form_submit_button("Save constraints")
    if saved:
        st.session_state["monetary_constraints"] = constraints
        st.success("Constraints saved.")
    else:
        constraints = st.session_state["monetary_constraints"]
    return constraints


def _render_components() -> pd.DataFrame:
    st.write(
        "Define monetary components using structured calculation templates. Raw costs are "
        "calculated first, then converted to a comparable monetary advantage score."
    )
    with st.form("monetary_components_form"):
        components = st.data_editor(
            st.session_state["monetary_components"],
            num_rows="dynamic",
            use_container_width=True,
            key="monetary_components_editor",
            column_config={
                "Template": st.column_config.SelectboxColumn(
                    options=list(TEMPLATE_LABELS.keys()),
                    help="Choose a supported calculation template.",
                ),
                "Included": st.column_config.CheckboxColumn(),
            },
        )
        saved = st.form_submit_button("Save cost components")
    if saved:
        st.session_state["monetary_components"] = components
        st.success("Cost components saved.")
    else:
        components = st.session_state["monetary_components"]

    with st.expander("Supported templates"):
        st.table(
            pd.DataFrame(
                [{"Template key": key, "Meaning": label} for key, label in TEMPLATE_LABELS.items()]
            )
        )
    return components


def _render_factor_definition() -> tuple[pd.DataFrame, pd.DataFrame]:
    st.write(
        "Step 1: define candidate schemes and monetary factors. Constraints and "
        "scheme-specific values are handled in the next steps."
    )

    st.subheader("Candidate schemes")
    with st.form("monetary_schemes_factors_form"):
        schemes = st.data_editor(
            st.session_state["monetary_schemes"],
            num_rows="dynamic",
            use_container_width=True,
            key="monetary_schemes_editor_v2",
            column_config={"Included": st.column_config.CheckboxColumn()},
        )
        st.subheader("Monetary factors")
        factors = st.data_editor(
            st.session_state["monetary_factors"],
            num_rows="dynamic",
            use_container_width=True,
            key="monetary_factors_editor_v2",
            column_config={
                "Varies by scheme": st.column_config.CheckboxColumn(),
                "Required": st.column_config.CheckboxColumn(),
                "Constrained": st.column_config.CheckboxColumn(),
            },
        )
        saved = st.form_submit_button("Save schemes and factors")

    if saved:
        st.session_state["monetary_schemes"] = schemes
        st.session_state["monetary_factors"] = factors
        st.success("Schemes and monetary factors saved.")
    else:
        schemes = st.session_state["monetary_schemes"]
        factors = st.session_state["monetary_factors"]

    st.caption(
        "Uncheck Included to exclude a scheme from calculations while keeping it available."
    )
    return schemes, factors


def _render_constraint_status(
    schemes: pd.DataFrame,
    factors: pd.DataFrame,
    factor_values: pd.DataFrame,
    constraints: pd.DataFrame,
    title: str,
) -> pd.DataFrame:
    active_schemes = _active_scheme_names(schemes)
    if not active_schemes:
        st.warning("Add at least one included scheme before checking constraints.")
        return pd.DataFrame(columns=["Scheme", "Constraint", "Status", "Detail"])
    if factor_values.empty:
        st.info("Scheme-specific factor values have not been created yet.")
        return pd.DataFrame(columns=["Scheme", "Constraint", "Status", "Detail"])

    report = check_constraints(active_schemes, factors, factor_values, constraints)
    st.subheader(title)
    if report.empty:
        st.success("No current constraint violations or advisory risks were found.")
    else:
        violations = report[report["Status"] == "Violation"]
        risks = report[report["Status"] == "Risk"]
        if not violations.empty:
            st.error(f"{len(violations)} constraint violation(s) found.")
        if not risks.empty:
            st.warning(f"{len(risks)} advisory risk(s) found.")
        st.dataframe(report, use_container_width=True)
    return report


def _render_scheme_inputs_and_components(
    schemes: pd.DataFrame,
    factors: pd.DataFrame,
    constraints: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    st.write(
        "Step 3: enter each scheme's specific factor values and select the cost "
        "components used in the monetary calculation. Constraint warnings update here "
        "as soon as entered values conflict with the defined rules."
    )

    st.subheader("Scheme-specific factor values")
    left, right = st.columns(2)
    with left:
        regenerate = st.button("Generate / refresh factor value table from schemes and factors")
    with right:
        sync_active = st.button("Remove inactive schemes from factor values")

    if regenerate or "monetary_factor_values" not in st.session_state:
        st.session_state["monetary_factor_values"] = _make_factor_values(schemes, factors)
    elif sync_active:
        st.session_state["monetary_factor_values"] = _sync_factor_values_to_active_schemes(
            st.session_state["monetary_factor_values"],
            schemes,
        )

    with st.form("monetary_factor_values_form"):
        factor_values = st.data_editor(
            st.session_state["monetary_factor_values"],
            num_rows="dynamic",
            use_container_width=True,
            key="monetary_factor_values_editor_v2",
        )
        values_saved = st.form_submit_button("Save scheme factor values")

    if values_saved:
        st.session_state["monetary_factor_values"] = factor_values
        st.success("Scheme factor values saved.")
    else:
        factor_values = st.session_state["monetary_factor_values"]

    _render_constraint_status(
        schemes,
        factors,
        factor_values,
        constraints,
        "Immediate constraint warning",
    )

    st.subheader("Cost components and calculation templates")
    components = _render_components()
    return factor_values, components


def _render_calculation_outputs(
    schemes: pd.DataFrame,
    factor_values: pd.DataFrame,
    constraints: pd.DataFrame,
    components: pd.DataFrame,
) -> None:
    active_schemes = _active_scheme_names(schemes)
    if not active_schemes:
        st.warning("Add at least one included scheme.")
        return

    component_results = calculate_component_results(active_schemes, factor_values, components)
    totals = calculate_totals(component_results)
    constraint_report = check_constraints(
        active_schemes,
        st.session_state["monetary_factors"],
        factor_values,
        constraints,
    )

    st.subheader("Component-level monetary results")
    st.dataframe(component_results, use_container_width=True)
    st.plotly_chart(
        bar_chart(component_results, "Scheme", "Cost", "Cost breakdown by component", color="Component"),
        use_container_width=True,
        key="monetary_component_chart",
    )

    st.subheader("Total monetary result")
    st.dataframe(totals, use_container_width=True)
    st.plotly_chart(
        bar_chart(totals, "Scheme", "Total cost", "Raw monetary comparison"),
        use_container_width=True,
        key="monetary_total_chart",
    )

    st.subheader("Constraint and risk checks")
    if constraint_report.empty:
        st.success("No constraint violations or advisory risks were found.")
    else:
        st.dataframe(constraint_report, use_container_width=True)

    st.subheader("Monetary score conversion")
    st.info(
        "Raw cost is not directly added to non-monetary scores. Raw monetary outcomes are "
        "converted into a comparable monetary advantage score first."
    )
    st.caption(
        "Inverse-cost keeps relative cost differences visible. Min-max is more aggressive: "
        "with two valid schemes, the cheapest becomes 1 and the most expensive becomes 0."
    )
    score_method = st.radio(
        "Scoring method",
        options=["inverse_cost", "minmax_lower_better"],
        format_func=lambda item: {
            "minmax_lower_better": "Min-max normalized score, lower cost is better",
            "inverse_cost": "Inverse-cost score",
        }[item],
        horizontal=True,
        key="monetary_score_method",
    )
    scores = calculate_monetary_scores(totals, constraint_report, score_method)
    st.dataframe(scores, use_container_width=True)
    st.plotly_chart(
        bar_chart(scores, "Scheme", "Monetary score", "Standardized monetary advantage score"),
        use_container_width=True,
        key="monetary_score_chart",
    )

    valid_scores = scores[scores["Valid scheme"]]
    if not valid_scores.empty:
        lowest_valid = valid_scores.sort_values("Total cost").iloc[0]
        st.success(
            f"Lowest-cost valid scheme: {lowest_valid['Scheme']} "
            f"with total cost {lowest_valid['Total cost']:.2f}."
        )
    else:
        st.error("No valid schemes are available after constraint checks.")

    st.session_state["monetary_scores"] = scores[
        ["Scheme", "Monetary score", "Total cost", "Valid scheme", "Rank"]
    ]
    st.session_state["monetary_component_results"] = component_results
    st.session_state["monetary_totals"] = totals
    st.session_state["monetary_constraint_report"] = constraint_report

    _download_excel(
        {
            "component_results": component_results,
            "totals": totals,
            "constraint_report": constraint_report,
            "monetary_scores": scores,
        },
        "monetary_results.xlsx",
    )


def render_cost() -> None:
    _initialise_monetary_state()

    st.subheader("Monetary / Cost Analysis")
    st.write(
        "Use this module to compare user-defined candidate schemes. It is a configurable "
        "scenario-comparison tool, not a full automatic optimization engine."
    )
    st.caption(
        "Final decision support should combine Monetary and Non-monetary scores only. "
        "The Additional module remains a warning and expert-review layer."
    )

    factors_tab, constraints_tab, scheme_inputs_tab, results_tab = st.tabs(
        [
            "1. Schemes & Factors",
            "2. Constraints",
            "3. Scheme Inputs & Components",
            "4. Calculation & Score",
        ]
    )

    with factors_tab:
        schemes, factors = _render_factor_definition()
    with constraints_tab:
        constraints = _render_constraints()
        _render_constraint_status(
            st.session_state["monetary_schemes"],
            st.session_state["monetary_factors"],
            st.session_state.get(
                "monetary_factor_values",
                _make_factor_values(
                    st.session_state["monetary_schemes"],
                    st.session_state["monetary_factors"],
                ),
            ),
            constraints,
            "Current check against existing scheme inputs",
        )
    with scheme_inputs_tab:
        factor_values, components = _render_scheme_inputs_and_components(
            st.session_state["monetary_schemes"],
            st.session_state["monetary_factors"],
            st.session_state["monetary_constraints"],
        )
    with results_tab:
        _render_calculation_outputs(
            st.session_state["monetary_schemes"],
            st.session_state.get(
                "monetary_factor_values",
                _make_factor_values(
                    st.session_state["monetary_schemes"],
                    st.session_state["monetary_factors"],
                ),
            ),
            st.session_state["monetary_constraints"],
            st.session_state["monetary_components"],
        )
