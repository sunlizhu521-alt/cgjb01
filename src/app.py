from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from parser import (
    CROSS_BORDER_SHEET_KEYWORDS,
    PARTS_SHEET_KEYWORDS,
    extract_verification,
    find_sheet_name,
    get_total_reduction,
    list_sheet_names,
    load_and_clean_data,
    monthly_reduction_summary,
    prepare_display_table,
    supplier_reduction_summary,
)
from visualizer import monthly_line_chart, supplier_bar_chart


st.set_page_config(
    page_title="采购 2026 降本数据看板",
    page_icon="📊",
    layout="wide",
)


def metric_number(value: float) -> str:
    return f"¥{value:,.2f}"


def dataframe_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def read_upload_bytes(uploaded_file) -> BytesIO:
    return BytesIO(uploaded_file.getvalue())


st.title("采购 2026 降本台账数据看板")
st.caption("上传 Excel 台账后，自动解析配件采购与跨境成品采购数据，展示 KPI、供应商贡献、月度趋势和 Q1 对账差异。")

with st.sidebar:
    st.header("数据源")
    uploaded_file = st.file_uploader("上传采购降本台账 Excel", type=["xlsx", "xlsm", "xls"])
    st.divider()
    st.subheader("解析设置")
    show_raw_columns = st.toggle("显示原始列索引", value=False)
    top_n = st.slider("供应商排行数量", min_value=5, max_value=30, value=15, step=5)

if uploaded_file is None:
    st.info("请先在左侧上传《采购2026降本台账》Excel 文件。")
    st.stop()

try:
    workbook_for_names = read_upload_bytes(uploaded_file)
    sheet_names = list_sheet_names(workbook_for_names)
except Exception as exc:
    st.error(f"无法读取 Excel 文件：{exc}")
    st.stop()

default_parts_sheet = find_sheet_name(sheet_names, PARTS_SHEET_KEYWORDS) or sheet_names[0]
default_cross_sheet = find_sheet_name(sheet_names, CROSS_BORDER_SHEET_KEYWORDS)

with st.sidebar:
    parts_sheet = st.selectbox(
        "配件采购工作表",
        sheet_names,
        index=sheet_names.index(default_parts_sheet),
    )
    cross_sheet_options = ["不读取"] + sheet_names
    cross_default_index = cross_sheet_options.index(default_cross_sheet) if default_cross_sheet else 0
    cross_sheet = st.selectbox("跨境成品采购工作表", cross_sheet_options, index=cross_default_index)

try:
    df_parts = load_and_clean_data(read_upload_bytes(uploaded_file), parts_sheet)
    df_cross = (
        load_and_clean_data(read_upload_bytes(uploaded_file), cross_sheet)
        if cross_sheet != "不读取"
        else pd.DataFrame()
    )
except Exception as exc:
    st.error(f"解析工作表失败：{exc}")
    st.stop()

if df_parts.empty:
    st.warning("配件采购工作表没有读取到有效数据。")
    st.stop()

parts_total = get_total_reduction(df_parts)
cross_total = get_total_reduction(df_cross) if not df_cross.empty else 0.0
supplier_count = df_parts[1].nunique() if 1 in df_parts.columns else 0
part_count = df_parts[2].nunique() if 2 in df_parts.columns else 0

st.subheader("核心指标")
col1, col2, col3, col4 = st.columns(4)
col1.metric("配件降本总额", metric_number(parts_total))
col2.metric("跨境成品降本总额", metric_number(cross_total))
col3.metric("配件供应商数", f"{supplier_count:,}")
col4.metric("配件品号数", f"{part_count:,}")

tab_overview, tab_audit, tab_explorer = st.tabs(["总览", "对账审计", "数据明细"])

with tab_overview:
    chart_col1, chart_col2 = st.columns([1.1, 1])
    supplier_summary = supplier_reduction_summary(df_parts, top_n=top_n)
    monthly_summary = monthly_reduction_summary(df_parts)

    with chart_col1:
        if supplier_summary.empty:
            st.info("暂无供应商降本金额数据。")
        else:
            st.plotly_chart(supplier_bar_chart(supplier_summary), use_container_width=True)

    with chart_col2:
        if monthly_summary.empty:
            st.info("暂无月度降本金额数据。")
        else:
            st.plotly_chart(monthly_line_chart(monthly_summary), use_container_width=True)

    if not supplier_summary.empty:
        st.dataframe(supplier_summary, use_container_width=True, hide_index=True)

with tab_audit:
    st.subheader("Q1 对账差异检查")
    mismatches = extract_verification(df_parts, months=(1, 2, 3))
    if mismatches.empty:
        st.success("Q1 未发现非零单价差异或数量差异。")
    else:
        price_issue_count = (mismatches["单价差异"] != 0).sum()
        quantity_issue_count = (mismatches["数量差异"] != 0).sum()
        audit_col1, audit_col2, audit_col3 = st.columns(3)
        audit_col1.metric("异常记录数", f"{len(mismatches):,}")
        audit_col2.metric("单价差异记录", f"{price_issue_count:,}")
        audit_col3.metric("数量差异记录", f"{quantity_issue_count:,}")

        st.dataframe(mismatches, use_container_width=True, hide_index=True)
        st.download_button(
            "下载 Q1 对账异常 CSV",
            data=dataframe_to_csv(mismatches),
            file_name="q1_verification_mismatches.csv",
            mime="text/csv",
        )

with tab_explorer:
    st.subheader("配件采购明细")
    display_df = prepare_display_table(df_parts)
    suppliers = sorted(display_df["供应商名称"].dropna().astype(str).unique()) if "供应商名称" in display_df else []

    filter_col1, filter_col2 = st.columns([1, 2])
    selected_supplier = filter_col1.selectbox("供应商筛选", ["全部"] + suppliers)
    keyword = filter_col2.text_input("搜索品号 / 中文名称 / 规格")

    filtered_df = display_df.copy()
    if selected_supplier != "全部" and "供应商名称" in filtered_df:
        filtered_df = filtered_df[filtered_df["供应商名称"].astype(str) == selected_supplier]
    if keyword:
        searchable = filtered_df.astype(str).agg(" ".join, axis=1)
        filtered_df = filtered_df[searchable.str.contains(keyword, case=False, na=False)]

    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    st.download_button(
        "下载当前明细 CSV",
        data=dataframe_to_csv(filtered_df),
        file_name="procurement_detail.csv",
        mime="text/csv",
    )

    if show_raw_columns:
        st.subheader("原始列索引数据")
        st.dataframe(df_parts, use_container_width=True)
