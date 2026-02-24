import json
from typing import Any, Dict, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import pandas as pd
import streamlit as st

from actions import run_return_after_break, run_show_trend, run_top_shows, run_year_totals
from ai_router import get_full_ai_analysis, get_openai_api_key

CSV_CHAR_LIMIT = 200_000


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


def plot_from_result(result: Dict[str, Any], container=None) -> None:
    target = container if container is not None else st
    chart = result.get("chart", {})
    if chart.get("kind") == "none":
        return

    data = chart.get("data", result["table"])
    if data is None or len(data) == 0:
        target.info("No data to chart for this query.")
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
    target.pyplot(fig)


def render_ai_analysis_result(ai_result: Dict[str, Any], container) -> None:
    if not ai_result.get("ok"):
        container.warning(ai_result.get("error", "AI analysis unavailable."))
        raw = ai_result.get("raw")
        if raw:
            with container.expander("Raw AI response"):
                container.code(raw)
        return

    container.write(ai_result.get("answer", ""))
    usage = ai_result.get("usage") or {}
    if usage.get("total_tokens") is not None:
        container.caption(
            f"Token usage — prompt: {usage.get('prompt_tokens')}, completion: {usage.get('completion_tokens')}, total: {usage.get('total_tokens')}"
        )


def maybe_render_local_fallback(question: str, filtered: pd.DataFrame) -> None:
    q = question.lower()

    # Heuristic local support for the AI answer (trusted pandas analytics).
    if "break" in q or "return" in q:
        st.markdown("### Supporting local data (break/return)")
        result = run_return_after_break(filtered, {"min_gap_years": 2, "pre_window": 2, "post_window": 0})
        st.dataframe(result["table"], use_container_width=True)
        plot_from_result(result)
        return

    if "trend" in q:
        for show in sorted(filtered["Show"].unique().tolist()):
            if show.lower() in q:
                st.markdown(f"### Supporting local data (trend for {show})")
                result = run_show_trend(filtered, {"show": show})
                st.dataframe(result["table"], use_container_width=True)
                plot_from_result(result)
                return

    if "top" in q:
        st.markdown("### Supporting local data (top shows)")
        result = run_top_shows(filtered, {"n": 10})
        st.dataframe(result["table"], use_container_width=True)
        plot_from_result(result)
        return

    if "year" in q or "annual" in q:
        st.markdown("### Supporting local data (year totals)")
        result = run_year_totals(filtered, {})
        st.dataframe(result["table"], use_container_width=True)
        plot_from_result(result)
        return


def main() -> None:
    st.set_page_config(page_title="Trade Show Sales Analyzer", layout="wide")
    st.title("Trade Show Sales Analyzer")

    with st.sidebar:
        full_ai_mode = st.toggle("Enable AI analysis (send filtered data)", value=False)
        if full_ai_mode:
            st.caption("⚠️ This sends your filtered sales data to the model.")

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
        "Ask AI about the filtered data",
        placeholder="Example: Which show has the strongest growth and show a chart",
    )

    if ask_text:
        st.subheader("AI analysis result")
        if not full_ai_mode:
            st.info("Enable 'Enable AI analysis (send filtered data)' in the sidebar to run AI analysis.")
        elif not get_openai_api_key():
            st.warning("OPENAI_API_KEY missing. Use st.secrets['OPENAI_API_KEY'] or environment variable OPENAI_API_KEY.")
        else:
            can_send = True
            if len(filtered) > 900:
                st.warning("Filtered dataset has more than 900 rows. Confirm before sending to AI.")
                can_send = st.checkbox("I confirm I want to send >900 filtered rows to AI")

            if can_send:
                csv_data = filtered[["Show", "Year", "GrossSales"]].to_csv(index=False)
                if len(csv_data) > CSV_CHAR_LIMIT:
                    csv_data = csv_data[:CSV_CHAR_LIMIT]
                    st.warning("Filtered CSV was truncated to 200,000 characters before sending to AI.")

                ai_result = get_full_ai_analysis(ask_text, csv_data, max_output_tokens=500)
                render_ai_analysis_result(ai_result, st)
                maybe_render_local_fallback(ask_text, filtered)

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
