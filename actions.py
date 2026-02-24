from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def _apply_optional_year_bounds(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    year_min = params.get("year_min")
    year_max = params.get("year_max")
    if year_min is not None:
        out = out[out["Year"] >= int(year_min)]
    if year_max is not None:
        out = out[out["Year"] <= int(year_max)]
    return out


def run_year_totals(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    grouped = df.groupby("Year", as_index=False)["GrossSales"].sum().sort_values("Year")
    return {
        "title": "Year totals",
        "table": grouped,
        "chart": {"kind": "bar", "x": "Year", "y": "GrossSales", "title": "Total Sales by Year"},
    }


def run_top_shows(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    n = int(params.get("n", 10))
    data = _apply_optional_year_bounds(df, params)
    grouped = (
        data.groupby("Show", as_index=False)["GrossSales"]
        .sum()
        .sort_values("GrossSales", ascending=False)
        .head(n)
    )
    return {
        "title": f"Top {n} shows",
        "table": grouped,
        "chart": {"kind": "bar", "x": "Show", "y": "GrossSales", "title": f"Top {n} Shows by Sales"},
    }


def run_show_trend(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    show = str(params.get("show", "")).strip()
    data = df[df["Show"].str.lower() == show.lower()]
    grouped = data.groupby("Year", as_index=False)["GrossSales"].sum().sort_values("Year")
    return {
        "title": f"Trend for {show}",
        "table": grouped,
        "chart": {"kind": "line", "x": "Year", "y": "GrossSales", "title": f"Sales Trend: {show}"},
    }


def run_yoy_by_show(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    mode = params.get("mode", "absolute")
    data = _apply_optional_year_bounds(df, params)
    grouped = data.groupby(["Show", "Year"], as_index=False)["GrossSales"].sum().sort_values(["Show", "Year"])
    grouped["YoYAbsolute"] = grouped.groupby("Show")["GrossSales"].diff()
    grouped["YoYPercent"] = grouped.groupby("Show")["GrossSales"].pct_change() * 100
    grouped = grouped.dropna(subset=["YoYAbsolute"]).copy()
    metric_col = "YoYPercent" if mode == "percent" else "YoYAbsolute"
    view = grouped[["Show", "Year", "GrossSales", metric_col]].sort_values(metric_col, ascending=False)
    return {
        "title": f"YoY by show ({mode})",
        "table": view,
        "chart": {"kind": "none"},
    }


def run_return_after_break(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    min_gap_years = int(params.get("min_gap_years", 2))
    pre_window = int(params.get("pre_window", 2))

    by_show_year = df.groupby(["Show", "Year"], as_index=False)["GrossSales"].sum().sort_values(["Show", "Year"])
    events = []

    for show, g in by_show_year.groupby("Show"):
        years = g["Year"].tolist()
        sales = g["GrossSales"].tolist()
        for i in range(1, len(years)):
            gap = years[i] - years[i - 1]
            if gap >= min_gap_years:
                pre_start = max(0, i - pre_window)
                pre_slice = sales[pre_start:i]
                if not pre_slice:
                    continue
                pre_avg = sum(pre_slice) / len(pre_slice)
                return_sales = sales[i]
                lift_abs = return_sales - pre_avg
                lift_pct = (lift_abs / pre_avg * 100) if pre_avg else None
                events.append(
                    {
                        "Show": show,
                        "LastYearBeforeBreak": years[i - 1],
                        "ReturnYear": years[i],
                        "GapYears": gap,
                        "PreAvgSales": pre_avg,
                        "ReturnYearSales": return_sales,
                        "LiftAbsolute": lift_abs,
                        "LiftPercent": lift_pct,
                    }
                )

    events_df = pd.DataFrame(events)
    if events_df.empty:
        events_df = pd.DataFrame(
            columns=[
                "Show",
                "LastYearBeforeBreak",
                "ReturnYear",
                "GapYears",
                "PreAvgSales",
                "ReturnYearSales",
                "LiftAbsolute",
                "LiftPercent",
            ]
        )
        chart_df = pd.DataFrame(columns=["Metric", "Value"])
    else:
        events_df = events_df.sort_values("LiftAbsolute", ascending=False)
        chart_df = pd.DataFrame(
            {
                "Metric": ["Average lift on return year"],
                "Value": [events_df["LiftAbsolute"].mean()],
            }
        )

    return {
        "title": "Return after break",
        "table": events_df,
        "chart": {"kind": "bar", "x": "Metric", "y": "Value", "title": "Average Lift on Return Year", "data": chart_df},
    }


def run_cohort_by_attendance_number(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    max_attendance_n = int(params.get("max_attendance_n", 6))
    normalize = bool(params.get("normalize", False))

    by_show_year = df.groupby(["Show", "Year"], as_index=False)["GrossSales"].sum().sort_values(["Show", "Year"])
    by_show_year["attendance_number"] = by_show_year.groupby("Show").cumcount() + 1
    by_show_year = by_show_year[by_show_year["attendance_number"] <= max_attendance_n].copy()

    if normalize:
        baseline = (
            by_show_year[by_show_year["attendance_number"] == 1][["Show", "GrossSales"]]
            .rename(columns={"GrossSales": "BaselineSales"})
        )
        by_show_year = by_show_year.merge(baseline, on="Show", how="left")
        by_show_year = by_show_year[by_show_year["BaselineSales"] > 0]
        by_show_year["SalesMetric"] = by_show_year["GrossSales"] / by_show_year["BaselineSales"]
        y_col = "AvgNormalizedSales"
    else:
        by_show_year["SalesMetric"] = by_show_year["GrossSales"]
        y_col = "AvgSales"

    cohort = (
        by_show_year.groupby("attendance_number")["SalesMetric"]
        .agg(["mean", "median", "count"])
        .reset_index()
        .rename(columns={"mean": y_col, "median": "Median", "count": "Shows"})
        .sort_values("attendance_number")
    )

    return {
        "title": "Cohort by attendance number",
        "table": cohort,
        "chart": {
            "kind": "line",
            "x": "attendance_number",
            "y": y_col,
            "title": "Cohort Curve by Attendance Number",
        },
    }



def run_first_five_year_pattern(df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze pattern across first N attendance years per show (default 5)."""
    n_years = int(params.get("n_years", 5))
    by_show_year = (
        df.groupby(["Show", "Year"], as_index=False)["GrossSales"]
        .sum()
        .sort_values(["Show", "Year"])
    )
    by_show_year["attendance_year_index"] = by_show_year.groupby("Show").cumcount() + 1
    first_n = by_show_year[by_show_year["attendance_year_index"] <= n_years].copy()

    summary = (
        first_n.groupby("attendance_year_index")["GrossSales"]
        .agg(["mean", "median", "count"])
        .reset_index()
        .rename(columns={"mean": "AvgSales", "median": "MedianSales", "count": "ShowCount"})
        .sort_values("attendance_year_index")
    )

    return {
        "title": f"Pattern in First {n_years} Years of a Show",
        "table": summary,
        "chart": {
            "kind": "line",
            "x": "attendance_year_index",
            "y": "AvgSales",
            "title": f"Average Sales by Attendance Year (1-{n_years})",
        },
    }
