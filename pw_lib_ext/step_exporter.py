"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Conversion Of Steps To JSONL
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from dataclass.conceptual_objects import Step, Locator


def _locator_to_playwright(locator: Locator) -> Dict[str, Any]:
    """
    Convert our locator to a Playwright codegen-like method & args.
    This JSONL format is a faithful projection of codegen semantics (not an official format).
    """
    s = locator.strategy
    if s == "role":
        return {"method": "getByRole",
                "args": [locator.role or "", {"name": locator.name} if locator.name else {}, locator.index]}
    if s == "label":
        return {"method": "getByLabel", "args": [locator.value or locator.name or ""]}
    if s == "dataTestId":
        return {"method": "getByTestId", "args": [locator.value or ""]}
    if s == "aria":
        if locator.name:
            return {"method": "getByRole", "args": ["button", {"name": locator.name}]}
        if locator.value:
            return {"method": "locator", "args": [f"[aria-label='{locator.value}']"]}
        return {"method": "locator", "args": ["[aria-label]"]}
    if s == "text":
        return {"method": "getByText", "args": [locator.value or "", {"exact": True}]}
    if s == "placeholder":
        return {"method": "getByPlaceholder", "args": [locator.value or ""]}
    if s == "css":
        return {"method": "locator", "args": [locator.value or ""]}
    if s == "xpath":
        return {"method": "locator", "args": [f"xpath={locator.value}"]}
    if s == "relative":
        # Approximate using text search (improve with anchors if available)
        return {"method": "getByText", "args": [locator.value or "", {"exact": False}]}
    return {"method": "locator", "args": ["html"]}


def steps_to_playwright_jsonl(steps: List[Step], out_path: Path) -> None:
    """
    Emit one JSON object per line, mirroring Playwright codegen semantics:
    - action: navigate/click/fill/... or expect assertions
    - locator: {method, args}
    - input/wait metadata retained
    - alternates included for self-healing
    """
    lines: List[str] = []
    for idx, s in enumerate(steps, start=1):
        entry: Dict[str, Any] = {
            "step": idx,
            "intent": s.intent,
            "action": s.action,
            "wait": {"type": s.wait.type, "timeoutMs": s.wait.timeoutMs},
            "domReference": s.domReference,
            "screenReference": s.screenReference,
        }

        if s.action == "navigate":
            entry["method"] = "goto"
            entry["args"] = [s.input]
            entry["locator"] = None
        else:
            entry["locator"] = _locator_to_playwright(s.locator)
            entry["altLocators"] = [_locator_to_playwright(a) for a in s.altLocators]
            if s.action == "fill":
                entry["input"] = s.input
            elif s.action == "press":
                entry["input"] = s.input
            else:
                entry["input"] = None

        # Assertions mapping to Playwright expect semantics
        if s.action in ("assert_text", "assert_visible", "assert_match"):
            if s.action == "assert_visible":
                entry["expect"] = {"type": "toBeVisible"}
            elif s.action == "assert_text":
                entry["expect"] = {"type": "toHaveText", "value": {"text": s.expectedText}}
            elif s.action == "assert_match":
                # Support /.../i style
                val: Dict[str, Any] = {}
                if s.pattern and s.pattern.startswith("/") and s.pattern.endswith("/i"):
                    val = {"regex": s.pattern[1:-2], "flags": "i"}
                elif s.pattern and s.pattern.startswith("/") and s.pattern.endswith("/"):
                    val = {"regex": s.pattern[1:-1], "flags": ""}
                else:
                    val = {"regex": s.pattern or "", "flags": ""}
                entry["expect"] = {"type": "toHaveText", "value": val}

        lines.append(json.dumps(entry, ensure_ascii=False))

    out_path.write_text("\n".join(lines), encoding="utf-8")
