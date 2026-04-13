from io import BytesIO

import pandas as pd
import streamlit as st

from utils.ahp import calculate_ahp
from utils.approx_ahp import aggregate_group_weights, calculate_rating_weights
from utils.data_loader import load_excel_sheets
from utils.detection import (
    candidate_demographic_columns,
    candidate_rating_columns,
    detect_dataset_type,
    extract_pairwise_matrix,
)
from utils.performance import (
    aggregate_long_performance,
    aggregate_wide_performance,
    guess_scheme_and_criterion,
    normalize_performance,
    score_schemes,
)
from utils.preprocessing import missing_value_report
from utils.visualization import bar_chart, missing_values_chart


def _download_csv(df: pd.DataFrame, file_name: str) -> None:
    st.download_button(
        "Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
    )


def _download_excel(df: pd.DataFrame, file_name: str) -> None:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
    st.download_button(
        "Download Excel",
        data=output.getvalue(),
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _render_exports(results: pd.DataFrame, stem: str) -> None:
    left, right = st.columns(2)
    with left:
        _download_csv(results, f"{stem}.csv")
    with right:
        _download_excel(results, f"{stem}.xlsx")


def _show_upload_diagnostics(df: pd.DataFrame, key_prefix: str) -> None:
    st.subheader("Data preview")
    st.dataframe(df.head(20), use_container_width=True)

    report = missing_value_report(df)
    st.subheader("Missing-value report")
    st.dataframe(report, use_container_width=True)
    st.plotly_chart(
        missing_values_chart(report),
        use_container_width=True,
        key=f"{key_prefix}_missing_chart",
    )

    st.subheader("Basic EDA")
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    st.write(
        {
            "Rows": int(df.shape[0]),
            "Columns": int(df.shape[1]),
            "Numeric columns": len(numeric_cols),
        }
    )
    if numeric_cols:
        st.dataframe(df[numeric_cols].describe().T, use_container_width=True)


def _render_pairwise_importance(df: pd.DataFrame) -> pd.DataFrame | None:
    extracted = extract_pairwise_matrix(df)
    if extracted is None:
        st.error("The file looked pairwise, but a clean square numeric matrix could not be extracted.")
        return

    criteria, matrix = extracted
    st.info(
        "Method selected: standard AHP. The uploaded importance sheet is treated as "
        "a reciprocal pairwise comparison matrix, so lambda_max, CI, and CR are meaningful."
    )
    st.dataframe(pd.DataFrame(matrix, index=criteria, columns=criteria), use_container_width=True)

    result = calculate_ahp(matrix, criteria)
    result_df = pd.DataFrame(
        {"Criterion": result.criteria, "Weight": result.weights}
    ).sort_values("Weight", ascending=False)

    metric_cols = st.columns(4)
    metric_cols[0].metric("lambda_max", f"{result.lambda_max:.4f}")
    metric_cols[1].metric("CI", f"{result.consistency_index:.4f}")
    metric_cols[2].metric("CR", f"{result.consistency_ratio:.4f}")
    metric_cols[3].metric(
        "Consistency",
        "Acceptable" if result.is_consistent else "Review needed",
    )

    if result.is_consistent:
        st.success("The consistency ratio is at or below 0.10.")
    else:
        st.warning("The consistency ratio is above 0.10. Review the pairwise judgements.")

    st.plotly_chart(
        bar_chart(result_df, "Criterion", "Weight", "Standard AHP criterion weights"),
        use_container_width=True,
        key="importance_pairwise_chart",
    )
    st.dataframe(result_df, use_container_width=True)
    _render_exports(result_df, "standard_ahp_importance_weights")
    return result_df


def _build_group_definitions(
    df: pd.DataFrame,
    demographic_cols: list[str],
    key_prefix: str,
) -> list[dict]:
    st.subheader("Stakeholder groups")
    st.write(
        "Default is all respondents with equal group weight. Add filters only when you "
        "want to compare or reweight specific stakeholder groups."
    )

    group_count = st.number_input(
        "Number of stakeholder groups",
        min_value=1,
        max_value=8,
        value=1,
        step=1,
        key=f"{key_prefix}_group_count",
    )
    groups = []

    for index in range(int(group_count)):
        default_name = "All respondents" if index == 0 else f"Group {index + 1}"
        with st.expander(default_name, expanded=index == 0):
            name = st.text_input(
                "Group name",
                value=default_name,
                key=f"{key_prefix}_group_name_{index}",
            )
            group_weight = st.number_input(
                "Group weight",
                min_value=0.0,
                value=1.0,
                step=0.1,
                key=f"{key_prefix}_group_weight_{index}",
            )
            filters = {}
            use_filters = st.checkbox(
                "Apply filters to this group",
                value=False,
                key=f"{key_prefix}_use_filters_{index}",
                help="Leave this off to include everyone in this group.",
            )

            if not use_filters:
                st.caption(f"This group includes all {len(df)} rows.")
                groups.append({"name": name, "weight": group_weight, "filters": filters})
                continue

            st.caption("Choose values to include. Remove values only when defining a subgroup.")
            for col in demographic_cols:
                unique_values = sorted(df[col].dropna().astype(str).unique().tolist())
                selected = st.multiselect(
                    f"Filter {col}",
                    options=unique_values,
                    default=unique_values,
                    key=f"{key_prefix}_group_{index}_{col}",
                    help="All values are selected by default. Remove values to narrow this group.",
                )
                if selected and len(selected) < len(unique_values):
                    filters[col] = selected

            groups.append({"name": name, "weight": group_weight, "filters": filters})

    return groups


def _render_rating_importance(df: pd.DataFrame) -> pd.DataFrame | None:
    rating_candidates = candidate_rating_columns(df)
    demographic_candidates = [
        col for col in candidate_demographic_columns(df) if col not in rating_candidates
    ]

    st.info(
        "Method selected: rating-based approximate AHP. The uploaded importance sheet "
        "is treated as direct criterion importance ratings, such as Likert-scale scores. "
        "Weights are derived from rating averages. This is not full traditional AHP, "
        "and CR is not the main interpretation here."
    )

    st.subheader("Confirm column roles")
    demographic_cols = st.multiselect(
        "Demographic/filter columns",
        options=df.columns.tolist(),
        default=demographic_candidates,
        key="importance_demographic_cols",
    )
    rating_cols = st.multiselect(
        "Criterion importance rating columns",
        options=df.columns.tolist(),
        default=rating_candidates,
        key="importance_rating_cols",
    )

    if not rating_cols:
        st.warning("Select at least one criterion importance rating column to continue.")
        return None

    groups = _build_group_definitions(df, demographic_cols, "importance")
    group_result = aggregate_group_weights(df, rating_cols, groups)

    if group_result.empty:
        st.error("No respondents matched the selected group definitions.")
        return None

    overall = calculate_rating_weights(group_result, rating_cols)
    overall_df = pd.DataFrame(
        {"Criterion": overall.index, "Weight": overall.values}
    ).sort_values("Weight", ascending=False)

    st.subheader("Stakeholder-group-weighted criterion weights")
    st.dataframe(group_result, use_container_width=True)

    st.subheader("Importance Analysis output")
    st.plotly_chart(
        bar_chart(overall_df, "Criterion", "Weight", "Approximate AHP criterion weights"),
        use_container_width=True,
        key="importance_rating_chart",
    )
    st.dataframe(overall_df, use_container_width=True)
    _render_exports(overall_df, "approximate_ahp_importance_weights")
    return overall_df


def _render_importance_analysis() -> None:
    st.write(
        "Use this section to derive weights for non-monetary criteria such as safety, "
        "disturbance to residents, environmental impact, social acceptance, and constructability."
    )
    uploaded_file = st.file_uploader(
        "Upload importance Excel file",
        type=["xlsx", "xls"],
        key="importance_upload",
    )
    if uploaded_file is None:
        st.info("Demo workbook: demo_data/non_monetary_demo.xlsx. Try the importance sheets.")
        return

    sheets = load_excel_sheets(uploaded_file)
    sheet_name = st.selectbox("Importance sheet", options=list(sheets.keys()), key="importance_sheet")
    df = sheets[sheet_name]
    _show_upload_diagnostics(df, "importance")

    detection = detect_dataset_type(df)
    method_options = {
        "pairwise": "Standard AHP pairwise comparison",
        "ratings": "Rating-based approximate AHP",
    }
    detected_method = detection.data_type if detection.data_type in method_options else "ratings"

    st.subheader("Method check")
    st.write(f"Detected method: **{detection.method_label}**")
    st.caption(detection.reason)
    selected_method = st.radio(
        "Confirm or switch the importance weighting method",
        options=list(method_options.keys()),
        format_func=lambda item: method_options[item],
        index=list(method_options.keys()).index(detected_method),
        horizontal=True,
        key="importance_method",
    )

    if selected_method == "pairwise":
        weights_df = _render_pairwise_importance(df)
        method_note = "Standard AHP from pairwise comparison data. CR is reported."
    else:
        weights_df = _render_rating_importance(df)
        method_note = (
            "Rating-based approximate AHP from direct importance ratings. "
            "CR is not used as the main interpretation."
        )

    if weights_df is not None:
        st.session_state["non_monetary_importance_weights"] = weights_df
        st.session_state["non_monetary_importance_method"] = method_note


def _render_wide_performance(df: pd.DataFrame) -> pd.DataFrame | None:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    rating_like = candidate_rating_columns(df)
    default_score_cols = rating_like if len(rating_like) >= 2 else numeric_cols
    demographic_candidates = [
        col for col in candidate_demographic_columns(df) if col not in default_score_cols
    ]

    st.subheader("Confirm performance columns")
    demographic_cols = st.multiselect(
        "Demographic/filter columns",
        options=df.columns.tolist(),
        default=demographic_candidates,
        key="performance_demographic_cols",
    )
    score_cols = st.multiselect(
        "Scheme performance score columns",
        options=df.columns.tolist(),
        default=default_score_cols,
        key="performance_score_cols",
        help="Use columns such as 'Scheme A safety score' or 'Scheme B environmental impact score'.",
    )

    if not score_cols:
        st.warning("Select at least one scheme performance score column.")
        return None

    st.subheader("Map score columns to schemes and criteria")
    column_map = {}
    for col in score_cols:
        guessed_scheme, guessed_criterion = guess_scheme_and_criterion(col)
        left, right = st.columns(2)
        with left:
            scheme = st.text_input(
                f"Scheme for {col}",
                value=guessed_scheme,
                key=f"performance_scheme_{col}",
            )
        with right:
            criterion = st.text_input(
                f"Criterion for {col}",
                value=guessed_criterion,
                key=f"performance_criterion_{col}",
            )
        if scheme.strip() and criterion.strip():
            column_map[col] = (scheme.strip(), criterion.strip())

    groups = _build_group_definitions(df, demographic_cols, "performance")
    return aggregate_wide_performance(df, column_map, groups)


def _render_long_performance(df: pd.DataFrame) -> pd.DataFrame | None:
    demographic_candidates = candidate_demographic_columns(df)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    st.subheader("Confirm long-format columns")
    demographic_cols = st.multiselect(
        "Demographic/filter columns",
        options=df.columns.tolist(),
        default=demographic_candidates,
        key="performance_long_demographic_cols",
    )
    scheme_col = st.selectbox("Scheme column", options=df.columns.tolist(), key="performance_scheme_col")
    criterion_col = st.selectbox("Criterion column", options=df.columns.tolist(), key="performance_criterion_col")
    score_col = st.selectbox(
        "Performance score column",
        options=numeric_cols or df.columns.tolist(),
        key="performance_score_col",
    )

    groups = _build_group_definitions(df, demographic_cols, "performance_long")
    return aggregate_long_performance(df, scheme_col, criterion_col, score_col, groups)


def _render_performance_analysis() -> None:
    st.write(
        "Use this section to evaluate how each candidate scheme performs under each "
        "non-monetary criterion. This is performance scoring, not AHP weighting."
    )
    uploaded_file = st.file_uploader(
        "Upload performance Excel file",
        type=["xlsx", "xls"],
        key="performance_upload",
    )
    if uploaded_file is None:
        st.info("Demo workbook: demo_data/non_monetary_demo.xlsx. Try the Performance scores sheet.")
        return

    sheets = load_excel_sheets(uploaded_file)
    sheet_name = st.selectbox("Performance sheet", options=list(sheets.keys()), key="performance_sheet")
    df = sheets[sheet_name]
    _show_upload_diagnostics(df, "performance")

    st.subheader("Performance data layout")
    layout = st.radio(
        "Choose how scheme scores are stored",
        options=["wide", "long"],
        format_func=lambda item: {
            "wide": "Wide: one score column per scheme-criterion pair",
            "long": "Long: scheme, criterion, and score columns",
        }[item],
        horizontal=True,
        key="performance_layout",
    )

    if layout == "wide":
        performance_df = _render_wide_performance(df)
    else:
        performance_df = _render_long_performance(df)

    if performance_df is None or performance_df.empty:
        st.error("No performance profile could be calculated from the selected columns.")
        return

    criteria = sorted(performance_df["Criterion"].dropna().unique().tolist())
    lower_is_better = st.multiselect(
        "Criteria where lower raw scores are better",
        options=criteria,
        help="Leave empty when higher scores mean better performance for all criteria.",
        key="performance_lower_is_better",
    )
    normalization_method = st.radio(
        "Performance normalization method",
        options=["rating_scale", "minmax_by_criterion"],
        format_func=lambda item: {
            "rating_scale": "Use known rating scale, e.g. 1-10 or 1-5",
            "minmax_by_criterion": "Min-max by criterion across schemes",
        }[item],
        index=0,
        horizontal=True,
        key="performance_normalization_method",
        help=(
            "Use rating scale for survey/expert scores. Min-max is more comparative and "
            "can turn two-scheme results into 0 and 1."
        ),
    )
    scale_cols = st.columns(2)
    with scale_cols[0]:
        score_min = st.number_input(
            "Lowest possible raw score",
            value=0.0,
            step=1.0,
            key="performance_score_min",
            disabled=normalization_method != "rating_scale",
        )
    with scale_cols[1]:
        score_max = st.number_input(
            "Highest possible raw score",
            value=10.0,
            step=1.0,
            key="performance_score_max",
            disabled=normalization_method != "rating_scale",
        )

    normalized_df = normalize_performance(
        performance_df,
        lower_is_better,
        method=normalization_method,
        score_min=score_min,
        score_max=score_max,
    )

    st.subheader("Aggregated non-monetary performance profile")
    st.dataframe(normalized_df, use_container_width=True)
    st.plotly_chart(
        bar_chart(
            normalized_df,
            "Scheme",
            "Normalized performance",
            "Normalized scheme performance by criterion",
            color="Criterion",
        ),
        use_container_width=True,
        key="performance_profile_chart",
    )
    _render_exports(normalized_df, "non_monetary_performance_profile")

    st.session_state["non_monetary_performance_profile"] = normalized_df


def _render_final_scoring() -> None:
    st.write(
        "This section combines criterion importance weights with scheme performance scores. "
        "For each scheme, the non-monetary score is the sum of criterion weight multiplied "
        "by normalized scheme performance under that criterion."
    )

    weights_df = st.session_state.get("non_monetary_importance_weights")
    performance_df = st.session_state.get("non_monetary_performance_profile")

    if weights_df is None:
        st.warning("Complete Importance Analysis first.")
        return
    if performance_df is None:
        st.warning("Complete Performance Analysis first.")
        return

    common_criteria = sorted(
        set(weights_df["Criterion"].astype(str)).intersection(
            set(performance_df["Criterion"].astype(str))
        )
    )
    if not common_criteria:
        st.error(
            "No matching criteria were found between importance weights and performance scores. "
            "Check that criterion names match in both sections."
        )
        return

    filtered_weights = weights_df[weights_df["Criterion"].isin(common_criteria)].copy()
    filtered_weights["Weight"] = filtered_weights["Weight"] / filtered_weights["Weight"].sum()
    filtered_performance = performance_df[performance_df["Criterion"].isin(common_criteria)].copy()

    scores, contributions = score_schemes(filtered_weights, filtered_performance)

    st.subheader("Weighted non-monetary score and ranking")
    st.dataframe(scores, use_container_width=True)
    st.plotly_chart(
        bar_chart(scores, "Scheme", "Non-monetary score", "Final non-monetary scheme ranking"),
        use_container_width=True,
        key="final_score_chart",
    )

    st.subheader("Why schemes scored differently")
    st.dataframe(contributions, use_container_width=True)
    st.plotly_chart(
        bar_chart(
            contributions,
            "Scheme",
            "Weighted contribution",
            "Weighted contribution by criterion",
            color="Criterion",
        ),
        use_container_width=True,
        key="final_contribution_chart",
    )
    _render_exports(scores, "non_monetary_scheme_ranking")
    st.session_state["non_monetary_scores"] = scores
    st.session_state["non_monetary_contributions"] = contributions


def render_non_monetary() -> None:
    st.subheader("Non-monetary Evaluation")
    st.write(
        "This module separates criterion importance from candidate scheme performance. "
        "Importance analysis derives non-monetary criterion weights. Performance analysis "
        "scores how well each scheme performs under those criteria. Final scoring combines both."
    )

    importance_tab, performance_tab, final_tab = st.tabs(
        ["Importance Analysis", "Performance Analysis", "Final Non-monetary Scoring"]
    )

    with importance_tab:
        _render_importance_analysis()
    with performance_tab:
        _render_performance_analysis()
    with final_tab:
        _render_final_scoring()
