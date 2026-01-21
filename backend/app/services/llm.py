from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import AsyncOpenAI

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _build_prompt(pr: Dict[str, Any], files: List[Dict[str, Any]]) -> str:
    file_blocks = []
    for file in files:
        patch = file.get("patch") or "(no diff)"
        file_blocks.append(
            f"File: {file.get('filename')}\n"
            f"Status: {file.get('status')}\n"
            f"Patch:\n{patch}\n"
        )

    prompt = (
        "You are an expert code reviewer. Review the pull request diff and return a JSON object "
        "with a concise summary and a list of comments. Focus on correctness, security, "
        "performance, and maintainability. Avoid style-only notes unless they prevent bugs.\n\n"
        f"Title: {pr.get('title')}\n"
        f"Description: {pr.get('body') or 'N/A'}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "comments": [\n'
        '    {"file_path": "string", "line_start": int, "line_end": int, "message": "string", "severity": "info|warning|critical"}\n'
        "  ]\n"
        "}\n\n"
        "Diffs:\n" + "\n".join(file_blocks)
    )
    return prompt


async def generate_review(pr: Dict[str, Any], files: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    client = AsyncOpenAI(api_key=api_key)
    prompt = _build_prompt(pr, files)
    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": "You are a precise code review assistant."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {"summary": "Unable to parse LLM response.", "comments": []}

    if "summary" not in data:
        data["summary"] = "Review completed."
    if "comments" not in data:
        data["comments"] = []

    return data
