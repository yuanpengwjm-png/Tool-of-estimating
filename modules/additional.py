import pandas as pd
import streamlit as st


REVIEW_AREAS = [
    "Hydrology",
    "Permeability uncertainty",
    "Long-term material performance",
    "Site-specific ground conditions",
    "Construction staging",
    "Traffic disruption",
    "Regulatory approval",
    "Community acceptance",
    "Field testing",
]


def _scheme_names_from_state() -> list[str]:
    monetary_schemes = st.session_state.get("monetary_schemes")
    if isinstance(monetary_schemes, pd.DataFrame) and "Scheme" in monetary_schemes:
        if "Included" in monetary_schemes:
            included_mask = monetary_schemes["Included"].map(
                lambda value: False if pd.isna(value) else bool(value)
            )
            monetary_schemes = monetary_schemes[included_mask]
        names = monetary_schemes["Scheme"].dropna().astype(str).tolist()
        if names:
            return names

    non_monetary_scores = st.session_state.get("non_monetary_scores")
    if isinstance(non_monetary_scores, pd.DataFrame) and "Scheme" in non_monetary_scores:
        names = non_monetary_scores["Scheme"].dropna().astype(str).tolist()
        if names:
            return names

    return ["Scheme A", "Scheme B"]


def _default_review_items(schemes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Scheme": schemes,
            "Data gap identified": [False] * len(schemes),
            "Expert review recommended": [False] * len(schemes),
            "Field testing recommended": [False] * len(schemes),
            "Uncertain assumption": [""] * len(schemes),
            "Risk reason": [""] * len(schemes),
            "Scheme-specific notes": [""] * len(schemes),
        }
    )


def _warning_level(row: pd.Series) -> str:
    trigger_count = int(bool(row["Data gap identified"]))
    trigger_count += int(bool(row["Expert review recommended"]))
    trigger_count += int(bool(row["Field testing recommended"]))
    trigger_count += int(bool(str(row["Uncertain assumption"]).strip()))
    if trigger_count >= 3:
        return "High risk"
    if trigger_count >= 1:
        return "Medium risk"
    return "Low risk"


def _confidence_level(warning_level: str) -> str:
    return {
        "Low risk": "High confidence",
        "Medium risk": "Moderate confidence",
        "High risk": "Low confidence",
    }[warning_level]


def _recommendation(row: pd.Series) -> str:
    recommendations = []
    if row["Data gap identified"]:
        recommendations.append("Resolve missing or incomplete inputs.")
    if row["Expert review recommended"]:
        recommendations.append("Seek expert judgement before relying on ranking.")
    if row["Field testing recommended"]:
        recommendations.append("Undertake field or laboratory testing.")
    if str(row["Uncertain assumption"]).strip():
        recommendations.append("Document and validate uncertain assumptions.")
    if not recommendations:
        recommendations.append("No additional review trigger recorded.")
    recommendations.append("Do not rely on automatic ranking alone.")
    return " ".join(recommendations)


def _automatic_gap_summary() -> list[str]:
    messages = []
    if st.session_state.get("monetary_scores") is None:
        messages.append("Monetary score is not available yet.")
    if st.session_state.get("non_monetary_scores") is None:
        messages.append("Non-monetary score is not available yet.")

    monetary_constraints = st.session_state.get("monetary_constraint_report")
    if isinstance(monetary_constraints, pd.DataFrame) and not monetary_constraints.empty:
        violations = monetary_constraints[monetary_constraints["Status"] == "Violation"]
        risks = monetary_constraints[monetary_constraints["Status"] == "Risk"]
        if not violations.empty:
            messages.append(f"{len(violations)} monetary constraint violation(s) found.")
        if not risks.empty:
            messages.append(f"{len(risks)} monetary advisory risk(s) found.")

    return messages


def render_additional() -> None:
    st.subheader("Additional Review")
    st.write(
        "Use this module to capture uncertainty, missing data, expert-review needs, and "
        "decision risks that are not fully captured by the Monetary and Non-monetary modules."
    )
    st.info(
        "Additional review does not contribute directly to the final weighted score. "
        "It provides warnings, confidence indicators, and recommendations only."
    )

    automatic_messages = _automatic_gap_summary()
    if automatic_messages:
        st.subheader("Automatic data gap checks")
        for message in automatic_messages:
            st.warning(message)
    else:
        st.success("No automatic data gaps detected from completed modules.")

    st.subheader("Expert-review topics")
    selected_topics = st.multiselect(
        "Select topics that need expert attention",
        options=REVIEW_AREAS,
        default=[],
        help="These topics are advisory and do not affect the weighted score.",
    )
    if selected_topics:
        st.warning("Expert review recommended for: " + ", ".join(selected_topics))

    schemes = _scheme_names_from_state()
    existing = st.session_state.get("additional_review_items")
    if not isinstance(existing, pd.DataFrame) or set(existing["Scheme"]) != set(schemes):
        st.session_state["additional_review_items"] = _default_review_items(schemes)

    st.subheader("Assumptions, notes, and scheme warnings")
    review_items = st.data_editor(
        st.session_state["additional_review_items"],
        num_rows="dynamic",
        use_container_width=True,
        key="additional_review_editor",
        column_config={
            "Data gap identified": st.column_config.CheckboxColumn(),
            "Expert review recommended": st.column_config.CheckboxColumn(),
            "Field testing recommended": st.column_config.CheckboxColumn(),
        },
    )
    st.session_state["additional_review_items"] = review_items

    summary = review_items.copy()
    summary["Warning level"] = summary.apply(_warning_level, axis=1)
    summary["Confidence level"] = summary["Warning level"].map(_confidence_level)
    summary["Recommendation summary"] = summary.apply(_recommendation, axis=1)

    st.subheader("Warning profile")
    for _, row in summary.iterrows():
        level = row["Warning level"]
        label = f"{row['Scheme']}: {level} - {row['Confidence level']}"
        if level == "High risk":
            st.error(label)
        elif level == "Medium risk":
            st.warning(label)
        else:
            st.success(label)
        st.caption(row["Recommendation summary"])
        if str(row["Risk reason"]).strip():
            st.write(f"Reason: {row['Risk reason']}")
        if str(row["Scheme-specific notes"]).strip():
            st.write(f"Notes: {row['Scheme-specific notes']}")

    st.subheader("Additional output")
    output = summary[
        [
            "Scheme",
            "Warning level",
            "Confidence level",
            "Recommendation summary",
            "Risk reason",
            "Scheme-specific notes",
        ]
    ]
    st.dataframe(output, use_container_width=True)
    st.session_state["additional_warning_summary"] = output
