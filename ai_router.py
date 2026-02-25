from __future__ import annotations

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


def _extract_response_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = getattr(resp, "output", None) or []
    parts = []
    for item in output:
        content = getattr(item, "content", None) or []
        for c in content:
            ctext = getattr(c, "text", None)
            if ctext:
                parts.append(str(ctext))
    return "\n".join(parts).strip()




def _build_debug_payload(resp: Any) -> Dict[str, Any]:
    """Collect lightweight debug fields to explain empty responses."""
    usage = getattr(resp, "usage", None)
    output_items = getattr(resp, "output", None) or []
    out = {
        "id": getattr(resp, "id", None),
        "status": getattr(resp, "status", None),
        "model": getattr(resp, "model", None),
        "incomplete_details": getattr(resp, "incomplete_details", None),
        "output_count": len(output_items),
        "output_types": [getattr(item, "type", None) for item in output_items],
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        },
    }
    return out

def get_full_ai_analysis(question: str, excel_bytes: bytes, filename: str, max_output_tokens: int = 20000) -> Dict[str, Any]:
    """Send Excel file + user question directly to model, return plain text answer only."""
    api_key = get_openai_api_key()
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not found in Streamlit secrets or environment."}

    try:
        from openai import OpenAI
    except Exception:
        return {"ok": False, "error": "openai package is not installed."}

    client = OpenAI(api_key=api_key)

    try:
        upload = client.files.create(file=(filename, excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), purpose="assistants")

        resp = client.responses.create(
            model="gpt-5-mini",
            max_output_tokens=max_output_tokens,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze the attached Excel file and answer the user's question. "
                                "Use only data in the file. Return concise plain text only.\n\n"
                                f"Question: {question}"
                            ),
                        },
                        {"type": "input_file", "file_id": upload.id},
                    ],
                }
            ],
        )

        answer_text = _extract_response_text(resp)
        debug = _build_debug_payload(resp)
        if not answer_text:
            return {
                "ok": False,
                "error": "The model returned an empty response. See debug details below.",
                "debug": debug,
            }

        usage = getattr(resp, "usage", None)
        usage_data = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        return {"ok": True, "answer": answer_text, "usage": usage_data, "debug": debug}
    except Exception as exc:
        return {"ok": False, "error": f"Full AI analysis failed: {exc}"}
