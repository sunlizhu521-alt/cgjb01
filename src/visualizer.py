from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


CHART_TEMPLATE = "plotly_white"


def supplier_bar_chart(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return go.Figure()
    fig = px.bar(
        summary.sort_values("降本金额", ascending=True),
        x="降本金额",
        y="供应商名称",
        orientation="h",
        text="降本金额",
        color="降本金额",
        color_continuous_scale="Tealgrn",
        template=CHART_TEMPLATE,
    )
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
    fig.update_layout(
        title="Top 15 供应商降本贡献",
        xaxis_title="降本金额",
        yaxis_title="供应商",
        coloraxis_showscale=False,
        height=max(420, 26 * len(summary)),
        margin=dict(l=12, r=80, t=60, b=20),
    )
    return fig


def monthly_line_chart(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return go.Figure()
    fig = px.line(
        summary,
        x="月份",
        y="降本金额",
        markers=True,
        template=CHART_TEMPLATE,
    )
    fig.update_traces(line=dict(width=3, color="#2563eb"), marker=dict(size=8))
    fig.update_layout(
        title="月度降本趋势",
        xaxis_title="月份",
        yaxis_title="降本金额",
        height=360,
        margin=dict(l=12, r=24, t=60, b=20),
    )
    return fig
