from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Iterable

import numpy as np
import pandas as pd


PARTS_SHEET_KEYWORDS = ("配件采购",)
CROSS_BORDER_SHEET_KEYWORDS = ("成品采购", "跨境")

BASIC_COLUMNS = {
    "序号": 0,
    "供应商名称": 1,
    "品号": 2,
    "中文名称": 3,
    "规格": 4,
    "下单人": 5,
    "降本金额汇总": 7,
}


@dataclass(frozen=True)
class MonthColumnMap:
    month: int
    price: int
    verified_price: int
    price_diff: int
    quantity: int
    verified_quantity: int
    quantity_diff: int
    reduction_amount: int


def build_month_maps(max_month: int = 12) -> list[MonthColumnMap]:
    """Build month column indexes based on the seven-column monthly cycle."""
    maps: list[MonthColumnMap] = []
    for month in range(1, max_month + 1):
        start = 9 + (month - 1) * 7
        maps.append(
            MonthColumnMap(
                month=month,
                price=start,
                verified_price=start + 1,
                price_diff=start + 2,
                quantity=start + 3,
                verified_quantity=start + 4,
                quantity_diff=start + 5,
                reduction_amount=start + 6,
            )
        )
    return maps


MONTH_MAPS = build_month_maps()


def list_sheet_names(file_path_or_bytes: str | BinaryIO) -> list[str]:
    excel = pd.ExcelFile(file_path_or_bytes)
    return excel.sheet_names


def find_sheet_name(sheet_names: Iterable[str], keywords: Iterable[str]) -> str | None:
    keywords = tuple(keywords)
    for sheet_name in sheet_names:
        if all(keyword in sheet_name for keyword in keywords):
            return sheet_name
    return None


def load_and_clean_data(file_path_or_bytes: str | BinaryIO, sheet_name: str) -> pd.DataFrame:
    """Load a ledger worksheet, forward-fill merged supplier cells, and remove empty rows."""
    df = pd.read_excel(file_path_or_bytes, sheet_name=sheet_name, skiprows=2, header=None)
    if df.empty:
        return df

    df = df.dropna(how="all").copy()
    if 1 in df.columns:
        df[1] = df[1].ffill()

    if {2, 3}.issubset(df.columns):
        df = df[df[2].notna() | df[3].notna()]

    if 1 in df.columns:
        df = df[df[1].astype(str).str.strip() != "合计"]

    return df.reset_index(drop=True)


def to_number(value) -> float:
    if value is None or pd.isna(value):
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").replace("￥", "").replace("¥", "").strip()
        if value in {"", "-", "--"}:
            return 0.0
    result = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(result) else float(result)


def safe_cell(row: pd.Series, index: int):
    return row[index] if index in row.index else np.nan


def get_numeric_column(df: pd.DataFrame, index: int) -> pd.Series:
    if index not in df.columns:
        return pd.Series(dtype=float)
    return df[index].map(to_number)


def get_total_reduction(df: pd.DataFrame, fallback_months: bool = True) -> float:
    summary_idx = BASIC_COLUMNS["降本金额汇总"]
    if summary_idx in df.columns:
        total = get_numeric_column(df, summary_idx).sum()
        if total != 0:
            return float(total)
    if not fallback_months:
        return 0.0
    amount_indexes = [m.reduction_amount for m in MONTH_MAPS if m.reduction_amount in df.columns]
    return float(sum(get_numeric_column(df, idx).sum() for idx in amount_indexes))


def monthly_reduction_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month_map in MONTH_MAPS:
        if month_map.reduction_amount not in df.columns:
            continue
        rows.append(
            {
                "月份": f"{month_map.month}月",
                "降本金额": get_numeric_column(df, month_map.reduction_amount).sum(),
            }
        )
    return pd.DataFrame(rows)


def supplier_reduction_summary(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    supplier_idx = BASIC_COLUMNS["供应商名称"]
    amount_idx = BASIC_COLUMNS["降本金额汇总"]
    if supplier_idx not in df.columns:
        return pd.DataFrame(columns=["供应商名称", "降本金额"])

    source = df[[supplier_idx]].copy()
    source["降本金额"] = get_numeric_column(df, amount_idx) if amount_idx in df.columns else 0.0
    source.columns = ["供应商名称", "降本金额"]
    source["供应商名称"] = source["供应商名称"].astype(str).str.strip()
    source = source[source["供应商名称"].ne("")]
    return (
        source.groupby("供应商名称", as_index=False)["降本金额"]
        .sum()
        .sort_values("降本金额", ascending=False)
        .head(top_n)
    )


def extract_verification(df: pd.DataFrame, months: Iterable[int] = (1, 2, 3)) -> pd.DataFrame:
    """Return rows with non-zero price or quantity verification differences."""
    month_maps = {m.month: m for m in MONTH_MAPS}
    mismatches = []

    for idx, row in df.iterrows():
        details = []
        for month in months:
            month_map = month_maps[month]
            price_diff = to_number(safe_cell(row, month_map.price_diff))
            quantity_diff = to_number(safe_cell(row, month_map.quantity_diff))
            if price_diff != 0 or quantity_diff != 0:
                details.append(
                    {
                        "月份": f"{month}月",
                        "单价差异": price_diff,
                        "数量差异": quantity_diff,
                    }
                )

        if details:
            base = {
                "Excel行号": idx + 3,
                "供应商名称": safe_cell(row, BASIC_COLUMNS["供应商名称"]),
                "品号": safe_cell(row, BASIC_COLUMNS["品号"]),
                "中文名称": safe_cell(row, BASIC_COLUMNS["中文名称"]),
            }
            for item in details:
                mismatches.append({**base, **item})

    return pd.DataFrame(mismatches)


def prepare_display_table(df: pd.DataFrame) -> pd.DataFrame:
    column_names = {
        0: "序号",
        1: "供应商名称",
        2: "品号",
        3: "中文名称",
        4: "规格",
        5: "下单人",
        7: "降本金额汇总",
    }
    selected = [idx for idx in column_names if idx in df.columns]
    display = df[selected].copy()
    display.columns = [column_names[idx] for idx in selected]
    return display
