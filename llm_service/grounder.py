"""
Date                    Author                          Change Details
02-02-2026              Coforge                         LLM Call With Intent, Video, DOM
                                                        Finding correct locator using LLM visual capability,
                                                        Execution

"""
import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from bs4 import BeautifulSoup, Comment

from dataclass.conceptual_objects import (
    Intents, IntentItem, get_intents_from_json_str, get_intents_from_dict, Step, Locator, WaitConfig, json_obj_to_step
)
from llm_service.abstract_llm_client import AbstractLLMClient
from pw_lib_ext.config import AppConfig


def _read_text_safe(path: str, limit: int = 5_000_000) -> str:
    """
    Read a text file safely, trimming to 'limit' characters if needed.
    Returns an empty string on error or missing path.
    """
    if not path:
        return ""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="ignore")
        if len(txt) > limit:
            half = limit // 2
            return txt[:half] + "\n...\n" + txt[-half:]
        return txt
    except Exception as e:
        raise e


def _image_to_data_uri(path: str) -> str:
    """
    Convert local PNG/JPG to a base64 data URI for vision models.
    Returns empty string if file is missing or unreadable.
    """
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    mime = "image/png" if p.suffix.lower() in (".png",) else "image/jpeg"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


# def _summarize_dom_for_llm(html: str, max_chars: int = 60_000) -> str:
#     """
#     Build an LLM-friendly textual summary from raw HTML:
#       - TITLE, OG tags
#       - HEADINGS (h1..h6)
#       - LINKS (<a> inner text)
#       - BUTTONS (<button> inner text)
#       - LABELS (<label> inner text)
#       - PLACEHOLDERS (placeholder=... values)
#     It deduplicates, normalizes whitespace, caps per-section sizes, and
#     returns a single string. Always returns ('' for empty input).
#     """
#     if not html:
#         return ""
#
#     # -------------------------------
#     # 1) Extract
#     # -------------------------------
#     # Title
#     title_m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
#     title_txt = title_m.group(1).strip() if title_m else ""
#
#     # OpenGraph (best-effort: look for two common OG metas)
#     og_title = re.findall(
#         r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
#         html, flags=re.I,
#     )
#     og_desc = re.findall(
#         r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
#         html, flags=re.I,
#     )
#
#     # Headings, links, buttons, labels
#     headings = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, flags=re.I | re.S)
#     links = re.findall(r"<a\b[^>]*>(.*?)</a>", html, flags=re.I | re.S)
#     buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", html, flags=re.I | re.S)
#     labels = re.findall(r"<label\b[^>]*>(.*?)</label>", html, flags=re.I | re.S)
#
#     # Placeholders (attribute values)
#     placeholders = re.findall(r'\bplaceholder\s*=\s*"(.*?)"', html, flags=re.I)
#     placeholders += re.findall(r"\bplaceholder\s*=\s*'(.*?)'", html, flags=re.I)
#
#     # -------------------------------
#     # 2) Normalize (strip tags, collapse whitespace)
#     # -------------------------------
#     def strip_html(text: str) -> str:
#         text = re.sub(r"<[^>]+>", "", text)  # remove tags
#         text = re.sub(r"\s+", " ", text).strip()  # collapse spaces
#         return text
#
#     headings = [strip_html(h) for h in headings]
#     links = [strip_html(x) for x in links]
#     buttons = [strip_html(x) for x in buttons]
#     labels = [strip_html(x) for x in labels]
#     placeholders = [re.sub(r"\s+", " ", x).strip() for x in placeholders]
#
#     # -------------------------------
#     # 3) Deduplicate + cap sections
#     # -------------------------------
#     def clean_cap(items, join_cap_chars: int, max_item_len: int = 2000):
#         out, seen = [], set()
#         running = 0
#         for it in items:
#             if not it or len(it) < 2:
#                 continue
#             if len(it) > max_item_len:
#                 it = it[:max_item_len] + "…"
#             key = it.lower()
#             if key in seen:
#                 continue
#             seen.add(key)
#             out.append(it)
#             running += len(it) + 3  # approx " | "
#             if running >= join_cap_chars:
#                 break
#         return out
#
#     headings = clean_cap(headings, 1500)
#     links = clean_cap(links, 2500)
#     buttons = clean_cap(buttons, 1000)
#     labels = clean_cap(labels, 2000)
#     placeholders = clean_cap(placeholders, 500)
#
#     # -------------------------------
#     # 4) Assemble sections
#     # -------------------------------
#     parts = []
#     if title_txt:
#         parts.append(f"TITLE: {title_txt}")
#     if og_title:
#         parts.append("OG_TITLE: " + " | ".join(og_title))
#     if og_desc:
#         parts.append("OG_DESC: " + " | ".join(og_desc))
#     if headings:
#         parts.append("HEADINGS: " + " | ".join(headings))
#     if links:
#         parts.append("LINKS: " + " | ".join(links))
#     if buttons:
#         parts.append("BUTTONS: " + " | ".join(buttons))
#     if labels:
#         parts.append("LABELS: " + " | ".join(labels))
#     if placeholders:
#         parts.append("PLACEHOLDERS: " + " | ".join(placeholders))
#
#     summary = "\n".join(parts)
#
#     # -------------------------------
#     # 5) Final clamp and RETURN
#     # -------------------------------
#     if len(summary) > max_chars:
#         half = max_chars // 2
#         summary = summary[:half] + "\n...\n" + summary[-half:]
#
#     return summary


def sanitize_html_for_llm(html: str, max_attr_len: int = 1024) -> str:
    """
    Strip non-structural noise before sending to LLM:
    - remove <script>, <style>, <noscript>, <template>, and HTML comments
    - trim overly long attribute values (e.g., base64 data URIs)
    - drop inline event handlers (on*)
    - keep structural & interactive semantics (roles, inputs, buttons, links)
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-structural nodes
    for tag_name in ("script", "style", "noscript", "template"):
        for t in soup.find_all(tag_name):
            t.decompose()

    # Remove HTML comments
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # Trim very long attribute values & remove event handlers
    for el in soup.find_all(True):
        # remove inline event handlers
        for attr in list(el.attrs.keys()):
            if attr.lower().startswith("on"):
                del el.attrs[attr]
        # clamp attribute values
        for attr, val in list(el.attrs.items()):
            if isinstance(val, list):
                el.attrs[attr] = [
                    (v[:max_attr_len] + "…") if isinstance(v, str) and len(v) > max_attr_len else v
                    for v in val
                ]
            elif isinstance(val, str) and len(val) > max_attr_len:
                el.attrs[attr] = val[:max_attr_len] + "…"

    return str(soup)


def _summarize_dom_for_llm(html: str, max_chars: int = 5_000_000) -> str:
    """
        Produce a clean, LLM-friendly DOM text. We run BeautifulSoup.prettify()
        on the already sanitized HTML to preserve meaningful structure/semantics.
        """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    summary = soup.prettify()
    if len(summary) > max_chars:
        half = max_chars // 2
        summary = summary[:half] + "\n...\n" + summary[-half:]
    return summary


# --------- LLM client abstraction ---------
class LLMAgent:
    """
    LLM client with two distinct prompts:
      - intents_prompt  : Phase-1 (plain English -> intents JSON)
      - grounding_prompt: Phase-2 (intent + DOM/screenshot -> grounded step JSON)
    """

    def __init__(self, llm_client: AbstractLLMClient, system_prompt_plain_english: str,
                 system_prompt_automation_steps: str):
        # API_BASE = "https://aiml04openai.openai.azure.com"
        # API_VERSION = "2025-01-01-preview"
        # MODEL_NAME = "insta-gpt-4o"
        self.system_prompt_plain_english = system_prompt_plain_english
        self.system_prompt_automation_steps_conversion = system_prompt_automation_steps
        self.llm_client = llm_client
        # Azure OpenAI Configuration
        # dotenv.load_dotenv(dotenv_path=os.path.join(PARENT_DIR, ".env"))
        #
        # self.llm_client: AzureLLMClient = AzureLLMClient(base_url=API_BASE, api_key=os.getenv("API_KEY"),
        #                                                  api_version=API_VERSION, model=MODEL_NAME)
        # self.llm_client = OpenAILLMClient(api_key=os.getenv("OPENAI_API_KEY"))

    def get_playwright_json(self, grounding_payload: Dict[str, Any]) -> Dict[str, Any]:
        dom_text = grounding_payload.get("artifactDOM", "")
        img_data_uri = grounding_payload.get("artifactImageDataURI", "")

        envelope = {
            "intent": grounding_payload.get("intent"),
            "locale": grounding_payload.get("locale"),
            "domReference": grounding_payload.get("domReference"),
            "screenReference": grounding_payload.get("screenReference"),
            "waitDefaults": grounding_payload.get("waitDefaults"),
        }

        user_content = [
            {"type": "text", "text": "GROUND THIS INTENT USING THE CURRENT PAGE ARTIFACTS BELOW."},
            {"type": "text", "text": f"INTENT: {envelope['intent']}"},
            {"type": "text",
             "text": f"CONTEXT: locale={envelope['locale']} domRef={envelope['domReference']} screenRef={envelope['screenReference']}"},
        ]
        if dom_text:
            user_content.append({"type": "text", "text": f"ARTIFACT_DOM_SUMMARY:\n{dom_text}"})
        if img_data_uri:
            user_content.append({"type": "image_url", "image_url": {"url": img_data_uri, "detail": "high"}})

        messages = [

            {"role": "system", "content": self.system_prompt_automation_steps_conversion},
            {"role": "user", "content": user_content}

        ]
        response: dict = self._chat_completion(messages)

        if isinstance(response, dict):
            if "steps" in response and isinstance(response["steps"], list) and response["steps"]:
                return response["steps"][0]
            return response
        if isinstance(response, list) and response:
            return response[0]
        raise ValueError("Grounder must return a JSON object (single step).")

    def extract_intents(self, user_prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt_plain_english},
            {"role": "user", "content": user_prompt}
        ]
        response: dict = self._chat_completion(messages)
        return response

    def _chat_completion(self, messages: List[Dict[str, str]]) -> dict:
        if self.llm_client.get_chat_history():
            messages = messages + self.llm_client.get_chat_history()
        response: dict = self.llm_client.execute_chat_completion_api(messages, response_format={"type": "json_object"})
        self.llm_client.add_chat_history({"role": "assistant", "content": json.dumps(response)})
        return response


# --------- Grounder System Prompt builder (Phase-2) ---------
def build_grounder_system_prompt(cfg: AppConfig) -> str:
    return (
        "You are a UI action grounder with vision capability.\n\n"
        "Given ONE intent and the current page's DOM and screenshot, emit ONE step executable by Playwright automation tools.\n"
        "The generated action should be compliant to Playwright which can be later used by downstream technology \n"
        "and framework specific tools such as selenium, cypress and Playwright itself. \n"
        "Where ever possible, role should be used and for any link, role with link should be used so that \n"
        "playwright can use those references for execution. \n"
        "Provide the best locator and alternate locators based on vision capability by looking at DOM and Screenshot provided with user prompt.\n"
        "Use ONLY the current artifacts referenced by domReference and screenReference.\n\n"
        "Selector priority (strict): role > label > dataTestId > aria > text > placeholder > css > xpath > relative\n\n"
        "Generate alternate locators for self-healing:\n"
        f"- Include up to {cfg.grounding.maxAltLocatorsPerStep} alternate locators ranked by stability/uniqueness.\n"
        "- Always include alternates even when confidence is high.\n\n"
        "Assertion mode:\n"
        f"- Mode: {cfg.grounding.assertionMode}\n"
        f"- Also require visibility assertion: {cfg.grounding.assertionAlsoCheckVisible}\n\n"
        "Artifact cadence (context only):\n"
        f"- Capture on URL change: {cfg.grounding.artifactPolicy.captureOnUrlChange}\n"
        f"- Capture on autosuggest visible: {cfg.grounding.artifactPolicy.captureOnAutoSuggestVisible}\n"
        f"- Capture on every step: {cfg.grounding.artifactPolicy.captureOnEveryStep}\n\n"
        "Return a STRICT JSON OBJECT (not an array). Produce exactly one dictionary with all keys shown in the schema below:\n"
        "{{\n"
        '  "intent": "<human friendly>",\n'
        '  "action": "navigate|click|fill|press|select|check|uncheck|hover|scroll|waitFor|assert_text|assert_visible|assert_match|custom",\n'
        '  "input": "<string or null>",\n'
        '  "locator": {{ "strategy": "role|label|dataTestId|aria|text|placeholder|css|xpath|relative",\n'
        '               "role": "<if role>", "name": "<if role/aria>", "value": "<if text/placeholder/label/dataTestId/css/xpath/relative>",\n'
        '               "frame": null }},\n'
        '  "altLocators": [ {{ "strategy": "...", "role": "...", "name": "...", "value": "...", "frame": null }} ],\n'
        '  "wait": {{ "type": "domReady", "timeoutMs": 10000 }},\n'
        '  "reason": "<one sentence>",\n'
        '  "confidence": 0.0,\n'
        '  "expectedText": null,\n'
        '  "pattern": null,\n'
        '  "domReference": 0,\n'
        '  "screenReference": 0\n'
        "}}\n"
        "Rules:\n"
        "- Output STRICT JSON only:\n"
        "Dictionary Key - intent - must have"
        "All Keys - Must Have"
    )


# --------- Phase-1: Intent Extraction (LLM-first, deterministic fallback) ---------
def extract_intents_dynamic(user_prompt: str, llm_client: Optional[LLMAgent] = None) -> Intents:
    if llm_client:

        out = llm_client.extract_intents(user_prompt=user_prompt)
        if isinstance(out, str):
            logging.info(f'Intents - \n'
                         f'{out}')
            return get_intents_from_json_str(out)
        logging.info(f'Intents - \n'
                     f'{json.dumps(out, indent=2)}')
        return get_intents_from_dict(out)

    return _extract_intents_without_llm(user_prompt)


def _sentence_split(text: str) -> List[str]:
    parts = re.split(r'(?:\.|\n|;|,| and )+', text, flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def _normalize_intent(phrase: str) -> str:
    s = phrase.strip()
    s = re.sub(r'^(please|kindly)\s+', '', s, flags=re.I)
    s = re.sub(r'^\s*(?:go to|visit)\s+', 'Open ', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s)
    return s[0].upper() + s[1:] if s else s


def _extract_intents_without_llm(prompt: str) -> Intents:
    sentences = _sentence_split(prompt)
    intents: List[IntentItem] = []
    step = 1
    for raw in sentences:
        low = raw.lower()
        url = re.search(r'(https?://\S+)', raw)
        if url:
            intents.append(IntentItem(step_no=step, intent=f"Open {url.group(1)}"))
        elif any(x in low for x in ["open", "navigate", "go to", "visit"]):
            intents.append(IntentItem(step_no=step, intent="Open homepage"))
        elif "career" in low and "open" not in low:
            intents.append(IntentItem(step_no=step, intent="Open Careers"))
        elif "enter" in low or "type" in low or "fill" in low or "input" in low:
            m = re.search(r'(?i)(?:enter|type|fill|input)\s+(.+)', raw)
            val = (m.group(1).strip() if m else raw).strip()
            intents.append(IntentItem(step_no=step, intent=f"Enter {val}"))
        elif "click search" in low or "search icon" in low or "submit search" in low:
            intents.append(IntentItem(step_no=step, intent="Click Search"))
        elif "choose first" in low or "select first" in low or "pick first" in low:
            intents.append(IntentItem(step_no=step, intent="Choose first suggestion"))
        elif any(x in low for x in ["read", "fetch", "capture", "get"]):
            intents.append(IntentItem(step_no=step, intent="Read result"))
        elif any(x in low for x in ["verify", "assert", "check"]):
            intents.append(IntentItem(step_no=step, intent="Verify result"))
        else:
            intents.append(IntentItem(step_no=step, intent=_normalize_intent(raw)))
        step += 1
    return Intents(intents=intents)


# --------- Phase-1 to Phase-2: seed steps (domain-agnostic) ---------
def seed_steps_from_intents(intents: Intents, default_wait=("domReady", 10000)) -> List[Step]:
    wait = WaitConfig(type=default_wait[0], timeoutMs=default_wait[1])
    steps: List[Step] = []
    for it in intents.intents:
        intent = it.intent
        low = intent.lower()
        if low.startswith("open "):
            action = "navigate"
            url_match = re.search(r'(https?://\S+)', intent)
            input_val = url_match.group(1) if url_match else None
        elif low.startswith("enter ") or any(k in low for k in ["type", "fill", "input"]):
            action = "fill"
            m = re.search(r'(?i)^(enter|type|fill|input)\s+(.+)$', intent)
            input_val = m.group(2).strip() if m else None
        elif any(k in low for k in ["choose", "select", "pick"]):
            action = "select"
            input_val = None
        elif any(k in low for k in ["read", "fetch", "capture", "get"]):
            action = "assert_match"
            input_val = None
        elif any(k in low for k in ["verify", "assert", "check"]):
            action = "assert_text"
            input_val = None
        else:
            action = "click"
            input_val = None

        placeholder = Locator(strategy="text", value=intent)
        step = Step(
            intent=intent,
            action=action,
            input=input_val,
            locator=placeholder,
            altLocators=[],
            wait=wait,
            reason="Seed step; will be grounded using current DOM and screenshot.",
            confidence=0.0,
            expectedText=None,
            pattern=r"/\b\d+\s+jobs\b/i" if action == "assert_match" else None,
            domReference=0,
            screenReference=0
        )
        steps.append(step)
    return steps


# --------- Phase-2 Grounder (per-step) ---------
class Grounder:
    """
    Produces a grounded Step for a given intent based on the CURRENT artifacts.
    If LLM is provided, uses it; else returns a heuristic step.
    """

    def __init__(self, cfg: AppConfig, llm: Optional[LLMAgent] = None):
        self.cfg = cfg
        self.llm = llm

    def get_pw_step_from_llm(self, intent: str, dom_id: int, sc_id: int,
                             artifact_dom: Optional[str] = None,
                             screenshot_path: Optional[str] = None) -> Step:
        if self.llm:
            img_data_uri = _image_to_data_uri(screenshot_path) if screenshot_path else ""
            payload = {
                "intent": intent,
                "locale": self.cfg.browser.locale,
                "domReference": dom_id,
                "screenReference": sc_id,
                "artifactDOM": artifact_dom or "",
                "artifactImageDataURI": img_data_uri,
                "waitDefaults": self.cfg.grounding.waitDefaults.interaction
            }
            response = self.llm.get_playwright_json(payload)  # single dict
            logging.info(f'Intent to LLM: \n'
                         f'{intent}\n'
                         f'Step Returned By LLM : \n'
                         f'{json.dumps(response, indent=2)}')
            return json_obj_to_step(response)
