import json
import os
import re
from typing import Any, Dict, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


def load_and_clean_data(uploaded_file) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], Optional[str]]:
    """Load, validate, and clean the uploaded Excel file."""
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
        return (
            None,
            quality,
            "Missing required columns: " + ", ".join(sorted(missing)),
        )

    # Keep only required columns for a clean prototype.
    df = df[["Show", "Year", "GrossSales"]].copy()

    # Normalize Show
    df["Show"] = df["Show"].astype(str).str.strip()
    blank_show_mask = df["Show"].eq("") | df["Show"].str.lower().eq("nan")

    # Coerce Year to integer
    year_numeric = pd.to_numeric(df["Year"], errors="coerce")
    invalid_year_mask = year_numeric.isna()
    df["Year"] = year_numeric

    # Coerce GrossSales to float, cleaning $, commas and spaces
    raw_gross = df["GrossSales"].copy()
    gross_before = pd.to_numeric(raw_gross, errors="coerce")
    gross_as_text = raw_gross.astype(str).str.replace(r"[$,]", "", regex=True).str.strip()
    gross_after = pd.to_numeric(gross_as_text, errors="coerce")
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


def action_top_shows(df: pd.DataFrame, n: int = 10) -> None:
    top = (
        df.groupby("Show", as_index=False)["GrossSales"]
        .sum()
        .sort_values("GrossSales", ascending=False)
        .head(n)
    )
    st.write(f"Top {n} shows by total sales")
    st.dataframe(top, use_container_width=True)


def action_trend_show(df: pd.DataFrame, show_name: str) -> None:
    show_df = df[df["Show"].str.lower() == show_name.lower()]
    if show_df.empty:
        st.warning(f"No rows found for show '{show_name}' in the current filtered dataset.")
        return

    trend = show_df.groupby("Year", as_index=False)["GrossSales"].sum().sort_values("Year")
    st.dataframe(trend, use_container_width=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(trend["Year"], trend["GrossSales"], marker="o")
    ax.set_title(f"Sales Trend: {show_name}")
    ax.set_xlabel("Year")
    ax.set_ylabel("Gross Sales")
    ax.grid(alpha=0.3)
    st.pyplot(fig)


def action_year_totals(df: pd.DataFrame) -> None:
    totals = df.groupby("Year", as_index=False)["GrossSales"].sum().sort_values("Year")
    st.dataframe(totals, use_container_width=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(totals["Year"].astype(str), totals["GrossSales"])
    ax.set_title("Total Sales by Year")
    ax.set_xlabel("Year")
    ax.set_ylabel("Gross Sales")
    plt.xticks(rotation=45)
    st.pyplot(fig)


def action_biggest_yoy(df: pd.DataFrame) -> None:
    by_show_year = df.groupby(["Show", "Year"], as_index=False)["GrossSales"].sum()
    by_show_year = by_show_year.sort_values(["Show", "Year"])
    by_show_year["YoYDelta"] = by_show_year.groupby("Show")["GrossSales"].diff()

    result = by_show_year.dropna(subset=["YoYDelta"]).sort_values("YoYDelta", ascending=False)
    st.write("Largest positive YoY increases")
    st.dataframe(result.head(20), use_container_width=True)


def parse_manual_command(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    t = text.strip()
    t_lower = t.lower()

    if t_lower == "top shows":
        return "top_shows", {}
    if t_lower == "year totals":
        return "year_totals", {}
    if t_lower == "biggest yoy increase":
        return "biggest_yoy_increase", {}

    match = re.match(r"^trend\s+(.+)$", t, flags=re.IGNORECASE)
    if match:
        return "trend_show", {"show": match.group(1).strip()}

    return None, {}


def translate_with_openai(user_text: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, {}, "OPENAI_API_KEY is not set. AI mode was disabled."

    try:
        from openai import OpenAI
    except Exception:
        return None, {}, "openai package is not installed. AI mode was disabled."

    client = OpenAI(api_key=api_key)

    prompt = (
        "Translate user request into one allowed action. "
        "Allowed actions: top_shows, trend_show, year_totals, biggest_yoy_increase. "
        "Return strict JSON only with schema: "
        '{"action":"top_shows","params":{"n":10}}. '
        "For trend_show use params.show. "
        "If unsure, choose year_totals."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
        )
        content = resp.choices[0].message.content or ""
        parsed = json.loads(content)
    except Exception as exc:
        return None, {}, f"AI translation failed: {exc}"

    action = parsed.get("action")
    params = parsed.get("params", {})
    allowed = {"top_shows", "trend_show", "year_totals", "biggest_yoy_increase"}
    if action not in allowed:
        return None, {}, "AI returned an unsupported action."

    # Sanitize params.
    safe_params: Dict[str, Any] = {}
    if action == "top_shows":
        try:
            safe_params["n"] = max(1, min(50, int(params.get("n", 10))))
        except Exception:
            safe_params["n"] = 10
    elif action == "trend_show":
        safe_params["show"] = str(params.get("show", "")).strip()

    return action, safe_params, None


def run_action(action: str, params: Dict[str, Any], df_filtered: pd.DataFrame, top_n_default: int) -> None:
    if action == "top_shows":
        n = int(params.get("n", top_n_default))
        action_top_shows(df_filtered, n=n)
    elif action == "trend_show":
        show_name = params.get("show", "")
        if not show_name:
            st.info("Please provide a show name, e.g. `trend CES`.")
            return
        action_trend_show(df_filtered, show_name)
    elif action == "year_totals":
        action_year_totals(df_filtered)
    elif action == "biggest_yoy_increase":
        action_biggest_yoy(df_filtered)


def main() -> None:
    st.set_page_config(page_title="Trade Show Sales Analyzer", layout="wide")
    st.title("Trade Show Sales Analyzer")
    st.caption("Upload an Excel file and explore sales by show and year.")

    with st.sidebar:
        st.header("Settings")
        ai_mode = st.toggle("Enable AI (OpenAI)", value=False)

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

    # Filters
    st.subheader("Filters")
    all_shows = sorted(df["Show"].unique().tolist())
    selected_shows = st.multiselect("Show", options=all_shows, default=all_shows)

    min_year, max_year = int(df["Year"].min()), int(df["Year"].max())
    year_range = st.slider("Year range", min_year, max_year, (min_year, max_year))

    filtered = df[
        df["Show"].isin(selected_shows)
        & df["Year"].between(year_range[0], year_range[1])
    ].copy()

    if filtered.empty:
        st.warning("No data after applying filters.")
        return

    # KPIs
    total_sales = float(filtered["GrossSales"].sum())
    unique_shows = int(filtered["Show"].nunique())

    year_totals = filtered.groupby("Year")["GrossSales"].sum()
    best_year = int(year_totals.idxmax()) if not year_totals.empty else None

    show_totals = filtered.groupby("Show")["GrossSales"].sum()
    best_show = str(show_totals.idxmax()) if not show_totals.empty else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Gross Sales", format_currency(total_sales))
    c2.metric("Number of Shows", f"{unique_shows}")
    c3.metric("Best Year", str(best_year) if best_year is not None else "N/A")
    c4.metric("Best Show", best_show if best_show else "N/A")

    st.subheader("Charts")

    # Total sales by year
    by_year = filtered.groupby("Year", as_index=False)["GrossSales"].sum().sort_values("Year")
    fig1, ax1 = plt.subplots(figsize=(8, 4))
    ax1.bar(by_year["Year"].astype(str), by_year["GrossSales"])
    ax1.set_title("Total Sales by Year")
    ax1.set_xlabel("Year")
    ax1.set_ylabel("Gross Sales")
    plt.xticks(rotation=45)
    st.pyplot(fig1)

    # Top N shows
    top_n = st.slider("Top N shows", min_value=3, max_value=25, value=10)
    by_show = (
        filtered.groupby("Show", as_index=False)["GrossSales"]
        .sum()
        .sort_values("GrossSales", ascending=False)
        .head(top_n)
    )
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    ax2.bar(by_show["Show"], by_show["GrossSales"])
    ax2.set_title(f"Top {top_n} Shows by Total Sales")
    ax2.set_xlabel("Show")
    ax2.set_ylabel("Gross Sales")
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig2)

    # YoY section
    st.subheader("YoY Change by Show")
    yoy_mode = st.radio("YoY scope", ["Selected show", "Top 10 shows"], horizontal=True)

    yoy_base = filtered.groupby(["Show", "Year"], as_index=False)["GrossSales"].sum()
    yoy_base = yoy_base.sort_values(["Show", "Year"])
    yoy_base["YoYDelta"] = yoy_base.groupby("Show")["GrossSales"].diff()

    if yoy_mode == "Selected show":
        show_choice = st.selectbox("Choose show", options=all_shows)
        yoy_table = yoy_base[yoy_base["Show"] == show_choice].copy()
        st.dataframe(yoy_table, use_container_width=True)

        if st.checkbox("Show line chart for selected show", value=True):
            trend = (
                filtered[filtered["Show"] == show_choice]
                .groupby("Year", as_index=False)["GrossSales"]
                .sum()
                .sort_values("Year")
            )
            fig3, ax3 = plt.subplots(figsize=(8, 4))
            ax3.plot(trend["Year"], trend["GrossSales"], marker="o")
            ax3.set_title(f"Trend for {show_choice}")
            ax3.set_xlabel("Year")
            ax3.set_ylabel("Gross Sales")
            ax3.grid(alpha=0.3)
            st.pyplot(fig3)
    else:
        top10_shows = (
            filtered.groupby("Show")["GrossSales"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .index.tolist()
        )
        yoy_table = yoy_base[yoy_base["Show"].isin(top10_shows)].copy()
        st.dataframe(yoy_table, use_container_width=True)

    # Ask box
    st.subheader("Ask (prototype)")
    ask_text = st.text_input(
        "Ask a question",
        placeholder="Try: top shows | trend CES | year totals | biggest yoy increase",
    )

    if ask_text:
        action = None
        params: Dict[str, Any] = {}

        if ai_mode:
            action, params, ai_error = translate_with_openai(ask_text)
            if ai_error:
                st.warning(ai_error)
                ai_mode = False

        if not action:
            action, params = parse_manual_command(ask_text)

        if action:
            run_action(action, params, filtered, top_n_default=top_n)
        else:
            st.info(
                "Supported commands: `top shows`, `trend <show name>`, "
                "`year totals`, `biggest yoy increase`."
            )

    # Debug / trust panels
    with st.expander("How this was calculated"):
        st.write(f"Filtered row count: {len(filtered)}")
        st.write("Cleaning steps applied:")
        for step in quality["cleaning_steps"]:
            st.markdown(f"- {step}")

    with st.expander("Data quality"):
        st.write(f"Rows original: {quality['rows_original']}")
        st.write(f"Rows dropped: {quality['rows_dropped']}")
        st.write(f"Dropped for blank Show: {quality['dropped_blank_show']}")
        st.write(f"Dropped for missing/invalid GrossSales: {quality['dropped_missing_gross']}")
        st.write(f"Dropped for invalid Year: {quality['dropped_invalid_year']}")
        st.write(f"Non-numeric GrossSales rows corrected: {quality['grosssales_corrected']}")
        st.write(f"Duplicate rows count: {quality['duplicate_rows']}")


if __name__ == "__main__":
    main()
