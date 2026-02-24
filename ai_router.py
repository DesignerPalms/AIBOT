from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

ALLOWED_ACTIONS = {
    "year_totals",
    "top_shows",
    "show_trend",
    "yoy_by_show",
    "return_after_break",
    "cohort_by_attendance_number",
}

PLAN_SCHEMA: Dict[str, Any] = {
    "name": "query_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
            "params": {"type": "object"},
        },
        "required": ["action", "params"],
    },
}

FULL_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "name": "full_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "insights": {"type": "array", "items": {"type": "string"}},
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": ["string", "number", "boolean", "null"]},
                            },
                        },
                    },
                    "required": ["name", "columns", "rows"],
                },
            },
            "chart": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string", "enum": ["bar", "line", "none"]},
                    "title": {"type": "string"},
                    "x": {"type": "string"},
                    "y": {"type": "string"},
                    "series": {"type": ["string", "null"]},
                    "data": {"type": "string"},
                },
                "required": ["type", "title", "x", "y", "series", "data"],
            },
        },
        "required": ["answer", "insights", "tables", "chart"],
    },
}


def get_openai_api_key() -> Optional[str]:
    try:
        key = str(st.secrets["OPENAI_API_KEY"]).strip()
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


def _validate_int(value: Any, low: int, high: int, name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def validate_plan(plan: Dict[str, Any], show_names: List[str]) -> Dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object")

    action = plan.get("action")
    params = plan.get("params", {})
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Unsupported action in plan")
    if not isinstance(params, dict):
        raise ValueError("params must be an object")

    validated: Dict[str, Any] = {"action": action, "params": {}}

    if action == "year_totals":
        if params:
            raise ValueError("year_totals does not accept params")

    elif action == "top_shows":
        n = params.get("n", 10)
        validated["params"]["n"] = _validate_int(n, 1, 50, "n")
        for bound in ["year_min", "year_max"]:
            if bound in params and params[bound] is not None:
                validated["params"][bound] = int(params[bound])

    elif action == "show_trend":
        show = str(params.get("show", "")).strip()
        if not show:
            raise ValueError("show is required for show_trend")
        show_map = {s.lower(): s for s in show_names}
        if show.lower() not in show_map:
            raise ValueError("show must match a Show value in data")
        validated["params"]["show"] = show_map[show.lower()]

    elif action == "yoy_by_show":
        mode = params.get("mode", "absolute")
        if mode not in {"percent", "absolute"}:
            raise ValueError("mode must be 'percent' or 'absolute'")
        validated["params"]["mode"] = mode
        for bound in ["year_min", "year_max"]:
            if bound in params and params[bound] is not None:
                validated["params"][bound] = int(params[bound])

    elif action == "return_after_break":
        validated["params"]["min_gap_years"] = _validate_int(params.get("min_gap_years", 2), 1, 10, "min_gap_years")
        validated["params"]["pre_window"] = _validate_int(params.get("pre_window", 2), 1, 5, "pre_window")
        validated["params"]["post_window"] = _validate_int(params.get("post_window", 0), 0, 5, "post_window")

    elif action == "cohort_by_attendance_number":
        validated["params"]["max_attendance_n"] = _validate_int(
            params.get("max_attendance_n", 6), 2, 10, "max_attendance_n"
        )
        normalize = params.get("normalize", False)
        if not isinstance(normalize, bool):
            raise ValueError("normalize must be a boolean")
        validated["params"]["normalize"] = normalize

    return validated


def _build_system_prompt() -> str:
    return (
        "You are a routing assistant. Return only JSON query plans. "
        "Never include code. Choose one action and params only."
    )


def get_query_plan_with_ai(user_text: str, show_names: List[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    api_key = get_openai_api_key()
    if not api_key:
        return None, "OPENAI_API_KEY not found in Streamlit secrets or environment."

    try:
        from openai import OpenAI
    except Exception:
        return None, "openai package is not installed."

    client = OpenAI(api_key=api_key)

    input_prompt = {
        "question": user_text,
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "notes": "show_trend.show must be a show name from dataset",
    }

    last_error = None
    for _ in range(2):
        try:
            resp = client.chat.completions.create(
                model="gpt-5-mini",
                response_format={"type": "json_schema", "json_schema": PLAN_SCHEMA},
                messages=[
                    {"role": "system", "content": _build_system_prompt()},
                    {"role": "user", "content": json.dumps(input_prompt)},
                ],
            )
            content = resp.choices[0].message.content or "{}"
            plan = json.loads(content)
            validated = validate_plan(plan, show_names)
            return validated, None
        except Exception as exc:
            last_error = str(exc)

    return None, f"AI plan was invalid after retry: {last_error}"


def get_full_ai_analysis(question: str, csv_data: str, max_output_tokens: int = 900) -> Dict[str, Any]:
    api_key = get_openai_api_key()
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not found in Streamlit secrets or environment."}

    try:
        from openai import OpenAI
    except Exception:
        return {"ok": False, "error": "openai package is not installed."}

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are a data analyst. Use only the provided CSV data to answer. "
        "Return JSON only matching the schema. Do not output code."
    )
    user_payload = {
        "question": question,
        "csv": csv_data,
        "rules": "Use only CSV; provide short answer, insights, optional tables and chart instruction.",
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            max_completion_tokens=max_output_tokens,
            response_format={"type": "json_schema", "json_schema": FULL_ANALYSIS_SCHEMA},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        usage_data = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        try:
            parsed = json.loads(content)
            return {"ok": True, "data": parsed, "raw": content, "usage": usage_data}
        except Exception:
            return {"ok": False, "error": "AI returned invalid JSON.", "raw": content, "usage": usage_data}
    except Exception as exc:
        return {"ok": False, "error": f"Full AI analysis failed: {exc}"}
