import json
import re
from typing import Any, Dict, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import pandas as pd
import streamlit as st

from actions import (
    run_cohort_by_attendance_number,
    run_return_after_break,
    run_show_trend,
    run_top_shows,
    run_year_totals,
    run_yoy_by_show,
)
from ai_router import get_query_plan_with_ai


def load_and_clean_data(uploaded_file) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], Optional[str]]:
    quality = {
        "rows_original": 0,
        "rows_after_cleaning": 0,
        "rows_dropped": 0,
        "dropped_blank_show": 0,
        "dropped_missing_gross": 0,
        "dropped_invalid_year": 0,
        "grosssales_corrected": 0,
        "duplicate_rows": 0,
        "cleaning_steps": [],
    }
    try:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as exc:
        return None, quality, f"Could not read Excel file: {exc}"

    quality["rows_original"] = len(df)
    required = {"Show", "Year", "GrossSales"}
    missing = required - set(df.columns)
    if missing:
        return None, quality, "Missing required columns: " + ", ".join(sorted(missing))

    df = df[["Show", "Year", "GrossSales"]].copy()
    df["Show"] = df["Show"].astype(str).str.strip()
    blank_show_mask = df["Show"].eq("") | df["Show"].str.lower().eq("nan")

    year_numeric = pd.to_numeric(df["Year"], errors="coerce")
    invalid_year_mask = year_numeric.isna()
    df["Year"] = year_numeric

    raw_gross = df["GrossSales"].copy()
    gross_before = pd.to_numeric(raw_gross, errors="coerce")
    gross_text = raw_gross.astype(str).str.replace(r"[$,]", "", regex=True).str.strip()
    gross_after = pd.to_numeric(gross_text, errors="coerce")
    corrected_mask = gross_before.isna() & gross_after.notna()
    gross_missing_mask = gross_after.isna()
    df["GrossSales"] = gross_after

    quality["grosssales_corrected"] = int(corrected_mask.sum())
    quality["dropped_blank_show"] = int(blank_show_mask.sum())
    quality["dropped_missing_gross"] = int(gross_missing_mask.sum())
    quality["dropped_invalid_year"] = int(invalid_year_mask.sum())

    drop_mask = blank_show_mask | gross_missing_mask | invalid_year_mask
    df = df.loc[~drop_mask].copy()
    df["Year"] = df["Year"].astype(int)
    df["GrossSales"] = df["GrossSales"].astype(float)

    quality["duplicate_rows"] = int(df.duplicated().sum())
    quality["rows_after_cleaning"] = len(df)
    quality["rows_dropped"] = quality["rows_original"] - quality["rows_after_cleaning"]
    quality["cleaning_steps"] = [
        "Validated required columns: Show, Year, GrossSales",
        "Coerced Year to integer",
        "Coerced GrossSales to float after removing '$' and ','",
        "Dropped rows with blank Show, invalid Year, or missing GrossSales",
    ]
    return df, quality, None


def format_currency(value: float) -> str:
    return f"${value:,.2f}"


def get_sales_axis_formatter(values: pd.Series) -> Tuple[FuncFormatter, str]:
    max_abs = float(values.abs().max()) if len(values) else 0.0
    if max_abs >= 1_000_000:
        return FuncFormatter(lambda y, _: f"{y / 1_000_000:,.1f}"), "(Millions)"
    if max_abs >= 100_000:
        return FuncFormatter(lambda y, _: f"{y / 100_000:,.1f}"), "(100,000s)"
    return FuncFormatter(lambda y, _: f"{y:,.0f}"), ""


def plot_from_result(result: Dict[str, Any]) -> None:
    chart = result.get("chart", {})
    if chart.get("kind") == "none":
        return

    data = chart.get("data", result["table"])
    if data is None or len(data) == 0:
        st.info("No data to chart for this query.")
        return

    x, y, kind, title = chart.get("x"), chart.get("y"), chart.get("kind"), chart.get("title", "")
    fig, ax = plt.subplots(figsize=(8, 4))
    if kind == "bar":
        ax.bar(data[x], data[y])
    elif kind == "line":
        ax.plot(data[x], data[y], marker="o")
    else:
        return

    formatter, unit_label = get_sales_axis_formatter(pd.Series(data[y]))
    ax.yaxis.set_major_formatter(formatter)
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel("Gross Sales" + (f" {unit_label}" if unit_label else ""))

    if str(x).lower() in {"year", "attendance_number"}:
        xvals = pd.Series(data[x]).dropna().astype(int).sort_values().unique()
        ax.set_xticks(xvals)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig)


def parse_manual_command(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    t = text.strip()
    low = t.lower()
    if low == "year totals":
        return {"action": "year_totals", "params": {}}, None
    if low == "top shows":
        return {"action": "top_shows", "params": {"n": 10}}, None
    if low == "biggest yoy increase":
        return {"action": "yoy_by_show", "params": {"mode": "absolute"}}, None

    m = re.match(r"^trend\s+(.+)$", t, flags=re.IGNORECASE)
    if m:
        return {"action": "show_trend", "params": {"show": m.group(1).strip()}}, None

    return None, "Supported: top shows | trend <show> | year totals | biggest yoy increase"


def execute_plan(df_filtered: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
    action = plan["action"]
    params = plan.get("params", {})
    if action == "year_totals":
        return run_year_totals(df_filtered, params)
    if action == "top_shows":
        return run_top_shows(df_filtered, params)
    if action == "show_trend":
        return run_show_trend(df_filtered, params)
    if action == "yoy_by_show":
        return run_yoy_by_show(df_filtered, params)
    if action == "return_after_break":
        return run_return_after_break(df_filtered, params)
    if action == "cohort_by_attendance_number":
        return run_cohort_by_attendance_number(df_filtered, params)
    raise ValueError("Unsupported action")


def main() -> None:
    st.set_page_config(page_title="Trade Show Sales Analyzer", layout="wide")
    st.title("Trade Show Sales Analyzer")

    with st.sidebar:
        enable_ai = st.toggle("Enable AI", value=False)

    uploaded_file = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])
    if not uploaded_file:
        st.info("Please upload an .xlsx file to begin.")
        return

    df, quality, error = load_and_clean_data(uploaded_file)
    if error:
        st.error(error)
        return
    assert df is not None

    st.subheader("Cleaned Data Preview")
    st.dataframe(df.head(20), use_container_width=True)

    all_shows = sorted(df["Show"].unique().tolist())
    selected_shows = st.multiselect("Show", all_shows, default=all_shows)
    min_year, max_year = int(df["Year"].min()), int(df["Year"].max())
    year_range = st.slider("Year range", min_year, max_year, (min_year, max_year))

    filtered = df[df["Show"].isin(selected_shows) & df["Year"].between(*year_range)].copy()
    if filtered.empty:
        st.warning("No data after applying filters.")
        return

    total_sales = float(filtered["GrossSales"].sum())
    unique_shows = int(filtered["Show"].nunique())
    best_year = int(filtered.groupby("Year")["GrossSales"].sum().idxmax())
    best_show = str(filtered.groupby("Show")["GrossSales"].sum().idxmax())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Gross Sales", format_currency(total_sales))
    c2.metric("Number of Shows", str(unique_shows))
    c3.metric("Best Year", str(best_year))
    c4.metric("Best Show", best_show)

    st.subheader("Standard Charts")
    plot_from_result(run_year_totals(filtered, {}))
    plot_from_result(run_top_shows(filtered, {"n": 10}))


    st.subheader("Quick Show Trend")
    quick_show = st.selectbox("Select a show to view trend", options=all_shows)
    quick_result = run_show_trend(filtered, {"show": quick_show})
    if quick_result["table"].empty:
        st.info("No trend data for selected show under current filters.")
    else:
        st.dataframe(quick_result["table"], use_container_width=True)
        plot_from_result(quick_result)

    ask_text = st.text_input(
        "Ask (manual commands or AI plan)",
        placeholder="Examples: top shows | trend CES | yoy percent by show in 2021-2024",
    )

    plan_used = None
    if ask_text:
        if enable_ai:
            plan, ai_error = get_query_plan_with_ai(ask_text, all_shows)
            if ai_error:
                st.warning(f"AI issue: {ai_error}. Falling back to manual parser.")
                plan, parser_err = parse_manual_command(ask_text)
                if parser_err:
                    st.info(parser_err)
            plan_used = plan
        else:
            plan, parser_err = parse_manual_command(ask_text)
            if parser_err:
                st.info(parser_err)
            plan_used = plan

        if plan_used:
            result = execute_plan(filtered, plan_used)
            st.subheader(result["title"])
            st.dataframe(result["table"], use_container_width=True)
            plot_from_result(result)

    with st.expander("Plan used"):
        st.code(json.dumps(plan_used or {}, indent=2), language="json")

    with st.expander("How calculated"):
        st.write(f"Filtered row count: {len(filtered)}")
        st.write(f"Show filter count: {len(selected_shows)}")
        st.write(f"Year range: {year_range[0]} - {year_range[1]}")
        for step in quality["cleaning_steps"]:
            st.markdown(f"- {step}")

    with st.expander("Data quality"):
        st.write(f"Rows original: {quality['rows_original']}")
        st.write(f"Rows dropped: {quality['rows_dropped']}")
        st.write(f"Dropped blank Show: {quality['dropped_blank_show']}")
        st.write(f"Dropped invalid/missing GrossSales: {quality['dropped_missing_gross']}")
        st.write(f"Dropped invalid Year: {quality['dropped_invalid_year']}")
        st.write(f"Corrected GrossSales rows: {quality['grosssales_corrected']}")
        st.write(f"Duplicate rows count: {quality['duplicate_rows']}")


if __name__ == "__main__":
    main()
