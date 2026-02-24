from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import streamlit as st


def get_openai_api_key() -> Optional[str]:
    try:
        key = str(st.secrets["OPENAI_API_KEY"]).strip()
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


def _extract_message_text(choice_message: Any) -> str:
    if choice_message is None:
        return ""

    content = getattr(choice_message, "content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if t:
                    parts.append(str(t))
            else:
                t = getattr(item, "text", "") or getattr(item, "content", "")
                if t:
                    parts.append(str(t))
        return "\n".join(parts).strip()

    return str(content or "")


def _chat_completion_request(client: Any, system_prompt: str, user_payload: Dict[str, Any], max_output_tokens: int) -> Any:
    return client.chat.completions.create(
        model="gpt-5-mini",
        max_completion_tokens=max_output_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    )


def _parse_hint(answer_text: str) -> Dict[str, str]:
    hint = "none"
    show = ""
    for line in answer_text.splitlines():
        if line.strip().upper().startswith("CHART_HINT:"):
            raw = line.split(":", 1)[1].strip().lower()
            if raw.startswith("show_trend:"):
                hint = "show_trend"
                show = raw.split(":", 1)[1].strip()
            else:
                hint = raw
            break
    return {"hint": hint, "show": show}


def get_full_ai_analysis(question: str, csv_data: str, max_output_tokens: int = 500) -> Dict[str, Any]:
    """Plain-text AI analysis with robust retries and chart hint extraction."""
    api_key = get_openai_api_key()
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not found in Streamlit secrets or environment."}

    try:
        from openai import OpenAI
    except Exception:
        return {"ok": False, "error": "openai package is not installed."}

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are a trade show sales analyst. Use ONLY the provided CSV data. "
        "Return plain text only with this format:\n"
        "ANSWER: <2-5 sentence answer>\n"
        "INSIGHTS:\n- <bullet>\n- <bullet>\n- <bullet>\n"
        "CHART_HINT: <one of: first5_cohort, year_totals, top_shows, return_after_break, show_trend:<show_name>, none>\n"
        "Never return JSON or code."
    )

    attempts = [csv_data, csv_data[:120_000], csv_data[:70_000]]
    last_usage = {}
    for payload_csv in attempts:
        try:
            resp = _chat_completion_request(
                client,
                system_prompt,
                {"question": question, "csv": payload_csv},
                max_output_tokens,
            )
            message = resp.choices[0].message if resp.choices else None
            answer_text = _extract_message_text(message).strip()

            usage = getattr(resp, "usage", None)
            last_usage = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }

            if answer_text:
                parsed_hint = _parse_hint(answer_text)
                return {
                    "ok": True,
                    "answer": answer_text,
                    "usage": last_usage,
                    "chart_hint": parsed_hint["hint"],
                    "hint_show": parsed_hint["show"],
                }
        except Exception:
            continue

    return {
        "ok": False,
        "error": "The model returned an empty response after retries. Try a narrower year range or fewer shows.",
        "usage": last_usage,
    }
