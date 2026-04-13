import pandas as pd
import plotly.express as px
import streamlit as st

from utils.visualization import bar_chart


def _combine_scores(
    monetary_scores: pd.DataFrame,
    non_monetary_scores: pd.DataFrame,
    cost_weight: float,
) -> pd.DataFrame:
    non_monetary_weight = 1.0 - cost_weight
    monetary = monetary_scores.rename(columns={"Monetary score": "MonetaryScore"})
    non_monetary = non_monetary_scores.rename(
        columns={"Non-monetary score": "NonMonetaryScore"}
    )
    combined = monetary[["Scheme", "MonetaryScore", "Total cost", "Valid scheme"]].merge(
        non_monetary[["Scheme", "NonMonetaryScore"]],
        on="Scheme",
        how="inner",
    )
    if combined.empty:
        return combined

    combined["Monetary contribution"] = cost_weight * combined["MonetaryScore"]
    combined["Non-monetary contribution"] = (
        non_monetary_weight * combined["NonMonetaryScore"]
    )
    combined["Final score"] = (
        combined["Monetary contribution"] + combined["Non-monetary contribution"]
    )
    combined.loc[~combined["Valid scheme"], "Final score"] = 0.0
    combined = combined.sort_values("Final score", ascending=False).reset_index(drop=True)
    combined["Rank"] = range(1, len(combined) + 1)
    return combined


def _tradeoff_explanation(combined: pd.DataFrame) -> str:
    if len(combined) < 2:
        return "Only one scheme is available for comparison under the current inputs."

    first = combined.iloc[0]
    second = combined.iloc[1]
    score_gap = first["Final score"] - second["Final score"]
    money_gap = first["MonetaryScore"] - second["MonetaryScore"]
    non_money_gap = first["NonMonetaryScore"] - second["NonMonetaryScore"]

    reasons = []
    if money_gap > 0:
        reasons.append("a stronger monetary advantage")
    elif money_gap < 0:
        reasons.append("a weaker monetary result")

    if non_money_gap > 0:
        reasons.append("a stronger non-monetary profile")
    elif non_money_gap < 0:
        reasons.append("a weaker non-monetary profile")

    reason_text = " and ".join(reasons) if reasons else "similar component scores"
    return (
        f"{first['Scheme']} ranks above {second['Scheme']} by {score_gap:.3f} points "
        f"because it has {reason_text} under the current weights."
    )


def _recommendation_status(scheme: str, additional_summary: pd.DataFrame | None) -> str:
    if not isinstance(additional_summary, pd.DataFrame) or additional_summary.empty:
        return "Recommended"

    row = additional_summary[additional_summary["Scheme"].astype(str) == str(scheme)]
    if row.empty:
        return "Recommended"

    warning_level = str(row.iloc[0].get("Warning level", "Low risk"))
    confidence = str(row.iloc[0].get("Confidence level", "High confidence"))
    if warning_level == "High risk" or confidence == "Low confidence":
        return "Expert review required"
    if warning_level == "Medium risk" or confidence == "Moderate confidence":
        return "Recommended with caution"
    return "Recommended"


def _render_sensitivity(
    monetary_scores: pd.DataFrame,
    non_monetary_scores: pd.DataFrame,
    current_best: str,
) -> None:
    st.subheader("Sensitivity check")
    st.write(
        "Explore whether the preferred scheme changes when the cost weight changes. "
        "This is a simple scenario check, not an optimization routine."
    )

    test_weights = [round(value / 10, 1) for value in range(0, 11)]
    rows = []
    for weight in test_weights:
        result = _combine_scores(monetary_scores, non_monetary_scores, weight)
        if result.empty:
            continue
        top = result.iloc[0]
        rows.append(
            {
                "W_cost": weight,
                "W_nonmonetary": round(1.0 - weight, 1),
                "Preferred scheme": top["Scheme"],
                "Top final score": top["Final score"],
                "Ranking changed": top["Scheme"] != current_best,
            }
        )

    sensitivity = pd.DataFrame(rows)
    st.dataframe(sensitivity, use_container_width=True)
    if sensitivity["Ranking changed"].any():
        changed_at = sensitivity.loc[sensitivity["Ranking changed"], "W_cost"].tolist()
        st.warning(
            "The preferred scheme changes at these cost weights: "
            + ", ".join(f"{item:.1f}" for item in changed_at)
            + "."
        )
    else:
        st.success("The preferred scheme is stable across the tested weight range.")


def render_final_decision() -> None:
    st.subheader("Decision Summary")
    st.write(
        "This page integrates Monetary, Non-monetary, and Additional outputs into a final "
        "scenario-comparison summary. Monetary and Non-monetary scores are weighted. "
        "Additional findings remain separate as warnings, confidence indicators, and "
        "expert-review recommendations."
    )
    st.info(
        "This is a decision-support platform for comparing user-provided scenarios, not a "
        "full mathematical optimization engine."
    )

    monetary_scores = st.session_state.get("monetary_scores")
    non_monetary_scores = st.session_state.get("non_monetary_scores")
    additional_summary = st.session_state.get("additional_warning_summary")

    if monetary_scores is None:
        st.warning("Complete the Monetary / Cost module first.")
        return
    if non_monetary_scores is None:
        st.warning("Complete Final Non-monetary Scoring first.")
        return

    cost_weight = st.slider(
        "W_cost",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05,
        help="Weight assigned to the standardized monetary advantage score.",
    )
    non_monetary_weight = 1.0 - cost_weight
    left, right = st.columns(2)
    left.metric("W_cost", f"{cost_weight:.2f}")
    right.metric("W_nonmonetary", f"{non_monetary_weight:.2f}")

    combined = _combine_scores(monetary_scores, non_monetary_scores, cost_weight)

    if combined.empty:
        st.error("No matching schemes were found between Monetary and Non-monetary results.")
        return

    combined["Recommendation"] = combined["Scheme"].apply(
        lambda scheme: _recommendation_status(scheme, additional_summary)
    )

    st.subheader("Preferred scheme")
    preferred = combined.iloc[0]
    if preferred["Recommendation"] == "Expert review required":
        st.error(
            f"{preferred['Scheme']} is currently highest ranked, but expert review is required "
            "before treating it as preferred."
        )
    elif preferred["Recommendation"] == "Recommended with caution":
        st.warning(
            f"{preferred['Scheme']} is currently preferred under the selected weights, "
            "with caution from the Additional review layer."
        )
    else:
        st.success(
            f"{preferred['Scheme']} is currently preferred under the selected weights "
            f"with final score {preferred['Final score']:.3f}."
        )

    st.subheader("Final ranking")
    st.caption(
        "Formula: FinalScore_j = W_cost * MonetaryScore_j + "
        "W_nonmonetary * NonMonetaryScore_j."
    )
    st.dataframe(combined, use_container_width=True)
    st.plotly_chart(
        bar_chart(combined, "Scheme", "Final score", "Final weighted scheme score"),
        use_container_width=True,
        key="final_decision_chart",
    )

    st.subheader("Score breakdown")
    breakdown = combined.melt(
        id_vars=["Scheme"],
        value_vars=["Monetary contribution", "Non-monetary contribution"],
        var_name="Score source",
        value_name="Contribution",
    )
    st.plotly_chart(
        px.bar(
            breakdown,
            x="Scheme",
            y="Contribution",
            color="Score source",
            title="Final score contribution by module",
            text_auto=".3f",
            barmode="stack",
        ),
        use_container_width=True,
        key="decision_breakdown_chart",
    )
    st.dataframe(
        combined[
            [
                "Scheme",
                "Monetary contribution",
                "Non-monetary contribution",
                "Final score",
            ]
        ],
        use_container_width=True,
    )

    st.subheader("Key trade-off explanation")
    st.write(_tradeoff_explanation(combined))

    if isinstance(additional_summary, pd.DataFrame) and not additional_summary.empty:
        st.subheader("Additional warnings")
        st.caption(
            "These warnings are advisory only. They are not added to, subtracted from, "
            "or weighted inside the final score."
        )
        st.dataframe(additional_summary, use_container_width=True)
    else:
        st.subheader("Additional warnings")
        st.info("No Additional warning summary has been recorded yet.")

    _render_sensitivity(monetary_scores, non_monetary_scores, preferred["Scheme"])
    st.session_state["decision_summary"] = combined
