import pandas as pd
import plotly.express as px


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None):
    return px.bar(df, x=x, y=y, color=color, title=title, text_auto=".3f", barmode="group")


def missing_values_chart(report: pd.DataFrame):
    chart_df = report.sort_values("Missing values", ascending=False)
    return px.bar(
        chart_df,
        x="Column",
        y="Missing values",
        title="Missing values by column",
        text_auto=True,
    )
