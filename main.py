# main.py
"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Main Script (Wiring)

"""
#TODO - Verify When popup select uses aria when strategy is text
#TODO - ensure id, name, class are prioritized
#TODO - output is new defined structure
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from constant.const_config import PARENT_DIR

ROOT = PARENT_DIR
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import dotenv

from dataclass.conceptual_objects import Intents
from pw_lib_ext.config import AppConfig
from llm_service.grounder import (
    extract_intents_dynamic,
    Grounder,
    LLMClient, _read_text_safe, _summarize_dom_for_llm
)
from llm_service.azure_client import AzureLLMClient
from constant.const_config import LOG_FILE, LOG_FOLDER, PARENT_DIR
from pw_lib_ext.runner import PWStepExecutor
from pw_lib_ext.step_exporter import steps_to_playwright_jsonl

# region Logging Initiation
logger = logging.getLogger()
log_file = LOG_FILE
os.makedirs(LOG_FOLDER, exist_ok=True)

logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s "
        "[%(name)s %(filename)s:%(lineno)d %(funcName)s] %(message)s"
    )

    fh.setFormatter(fmt)
    logger.addHandler(fh)
logger.info("Logging Started For Playwright Execution From LLM English Prompt - ")


# endregion


# region wiring

def main():
    # region Initiate Configuration
    cfg = AppConfig()
    # --- Runtime toggles ---

    # ----Browser Configuration ---

    cfg.browser.engine = "chromium"
    cfg.browser.headless = False
    cfg.browser.slowMoMs = 250
    cfg.browser.locale = "en-IN"

    #------------

    cfg.grounding.assertionMode = "regex"  # "exact" or "regex"
    cfg.grounding.assertionAlsoCheckVisible = True
    cfg.grounding.artifactPolicy.captureOnAutoSuggestVisible = True
    cfg.grounding.artifactPolicy.captureOnEveryStep = True
    cfg.grounding.artifactPolicy.fullPageScreenshots = True
    cfg.grounding.maxAltLocatorsPerStep = 3

    cfg.logging.verbosity = "verbose"
    cfg.logging.saveRunLog = True


    time_stamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(os.path.join(LOG_FOLDER, f'run_{time_stamp}'))
    run_dir.mkdir(parents=True, exist_ok=True)

    # endregion

    # region Define Prompt For LLM -> Each Intent (Step) and Intent To Playwright Step

    # -------- Phase 1: Intents --------
    system_prompt_llm_english = (
        "You are a senior QA test planner. Convert free-form Web UI navigation instructions into "
        "an ordered list of meaningful actions to perform, human-friendly intents.\n"
        "Rules:\n"
        "- Output STRICT JSON only:\n"
        '  { "intents": [ { "step": <int>, "intent": "<meaningful context for LLM to identify content on web UI>" }, ... ] }\n'
        "- IDs start at 1 and are consecutive.\n"
        "- Keep each intent compact (e.g., \"Open homepage\", \"Open https://...\", \"Enter <value>\").\n"
        "- Do NOT include locators or tool syntax.\n"
        "- Prefer meaningful action: open, navigate, focus, enter, choose, click, select, press, press_sequentially, fill, search, read, verify, assert, wait.\n"
        "- Split composite instructions or actions into atomic steps (1 action per intent).\n"
        "- Dont Trim the intent which has some special condition. \n"
        "- Special Conditions Identified By Words such as - Having, Special Note, Such That, If, etc..."
    )
    system_prompt_pw_steps_generation = (
        """
        You are a UI Action Grounder with DOM‑reasoning and vision capability.

Goal:
- Given ONE user intent, the current page’s DOM (domReference) and screenshot (screenReference), produce EXACTLY ONE step that:
  - Uses Playwright ONLY for page rendering, navigation between pages, and assertions.
  - Emits locators that are maximally compatible with Selenium (strict locator priority below).
  - Returns STRICT JSON (single object) that a downstream automation tool will consume to execute actions and asserts.

Hard requirements:
1) Only one step per intent.
2) Use ONLY the artifacts referenced by domReference and screenReference.
3) Output MUST be valid JSON (no extra text).
4) Follow STRICT locator priority and schema.
5) Always produce up to 3 alternate locators for self-healing.
6) The "reason" MUST explicitly note when Selenium-preferred attributes (id, name, test hooks, class) are missing on the chosen element.
7) Case handling and corrective behavior as specified below.

────────────────────────────────────────────────────────
## 1) Action & Intent Interpretation

1.1 Corrective interpretation
- If the requested action is semantically wrong for the element, correct it:
  - “Press button” → treat as **click**
  - “type”, “enter”, “fill” for text entry → **press_sequentially** to mimic keystrokes/events
- Always choose the most correct action for the element type.

1.2 Intent text matching
- Try **case-sensitive** match first against visible labels/names/text.
- If not found, try **case-insensitive**.
- If still not found, apply **semantic reasoning** (typos such as “carrier” ≈ “Career”).
- If multiple candidates match, choose the most contextually relevant and include an **index** for disambiguation.

────────────────────────────────────────────────────────
## 2) Locator Strategy (Selenium‑centric)

### 2.1 Strict priority (highest → lowest)
1. **testHook**  → any attribute value that contains “test” (case-insensitive),
                   e.g., data-test, data-testid, id, name, class, etc. that match regex: `.*[Tt][Ee][Ss][Tt].*`
2. **id**
3. **name**
4. **class**
5. **role**
6. **label**
7. **dataTestId**
8. **aria**
9. **text**
10. **placeholder**
11. **css**
12. **xpath**
13. **relative**

- Prefer strategies 1–4 to maximize Selenium compatibility.
- When role/name are used, you MUST include `"index"` for `.nth(index)` disambiguation.
- The “value” for `testHook` is the attribute selector or description sufficient for downstream tools (e.g., `[data-testid*="test" i]` or explicit attribute name + value).

### 2.2 Visibility constraint
- Choose the “best” locator based on what a **normal user can visibly perceive**.
- Confirm via DOM + screenshot alignment.

────────────────────────────────────────────────────────
## 3) Alternates (Self‑healing)

- Always provide up to **3** alternate locators.
- Follow the same strict priority.
- Rank alternates by stability/uniqueness.
- Even with high confidence, alternates are required.

────────────────────────────────────────────────────────
## 4) Assertions & Rendering

- Playwright is used for:
  - Rendering pages, navigation across routes/pages.
  - Assertions on visibility/text/patterns as needed by the step.
- Assertion mode: `"regex"`.
- Also require visibility for assertions.

────────────────────────────────────────────────────────
## 5) Artifact Capture (context only)

- Capture on URL change: true
- Capture on autosuggest visible: true
- Capture on every step: true

────────────────────────────────────────────────────────
## 6) REQUIRED JSON SCHEMA (STRICT)

Return ONLY a single JSON object with EXACTLY these keys and value types:

{
  "intent": "<human friendly intent string>",
  "action": "navigate|click|press_sequentially|fill|press|select|check|uncheck|hover|scroll|waitFor|assert_text|assert_visible|assert_match|custom",
  "input": "<string or null>",
  "locator": {
    "strategy": "testHook|id|name|class|role|label|dataTestId|aria|text|placeholder|css|xpath|relative",
    "role": "<string or null>",
    "name": "<string or null>",
    "value": "<string or null>",
    "frame": null,
    "index": <int>
  },
  "altLocators": [
    {
      "strategy": "testHook|id|name|class|role|label|dataTestId|aria|text|placeholder|css|xpath|relative",
      "role": "<string or null>",
      "name": "<string or null>",
      "value": "<string or null>",
      "frame": null
    }
  ],
  "wait": { "type": "domReady", "timeoutMs": 10000 },
  "reason": "<one concise sentence that MUST explicitly mention if any of id, name, test hooks, class were unavailable in the DOM for the chosen element>",
  "confidence": <float between 0 and 1>,
  "expectedText": null,
  "pattern": null,
  "domReference": <int>,
  "screenReference": <int>
}

Notes:
- `locator.strategy` MUST honor the strict priority.
- If the best available locator is not in {testHook, id, name, class},
  the `"reason"` MUST include a note, e.g.:
  "Preferred Selenium attributes (id/name/test hooks/class) not found; selected role+name with index."
- When using role/name, ALWAYS provide `"index"`.

────────────────────────────────────────────────────────
## 7) Examples of “reason” text

- "Used id; Selenium‑preferred attribute available. Confidence high."
- "No id/name/test hooks/class present; using role+name with index for visibility."
- "No test hooks found; id missing; chose name with index; alternates include class and text."

────────────────────────────────────────────────────────
## 8) Critical Output Rules

- Output MUST be valid JSON only (no extra commentary).
- Use ONLY information from domReference and screenReference.
- Provide a realistic confidence score aligned with locator stability and priority.


Notes

This prompt enforces Selenium‑ready locators (id, name, test hooks, class) while allowing Playwright to render and assert as you requested.
The reason field explicitly requires a note whenever those preferred attributes are missing, which downstream consumers can use for reporting or remediation.
If you want, I can also supply:

A few‑shot set showing good vs. bad locator choices
A minimal JSON schema (e.g., JSON Schema Draft 2020‑12) to validate outputs at runtime
CSS snippets and regex helpers for detecting “test” in attributes across engines
        """

    )

    # endregion

    # region User Given LLM Instruction In Plain English
    user_prompt = (
        "Open JP Morgan site with url - https://am.jpmorgan.com/us/en/asset-management, "
        "Click on popup window with text - Individual Investors"
        "Click first 'search' button on header on top right of page, "
        "Type text 'Investment' to mimic each character entry in textbox identified by name - 'Search Input' and click second search button, "
        "Click the first relevant link having JPMorgan text aligned to link"
        # "Click the first link on search page related to Investment"

    )

    # endregion

    # region LLM Initialization (LLM Control In LLMClient Interface, Needs Control At Top Layer..TODO)
    # Use LLM client (One can Toggle Between Various LLM Models, Its Abstracted In LLMClient)

    API_BASE = "https://aiml04openai.openai.azure.com"
    API_VERSION = "2025-01-01-preview"
    MODEL_NAME = "insta-gpt-4o"

    # Azure OpenAI Configuration
    dotenv.load_dotenv(dotenv_path=os.path.join(PARENT_DIR, ".env"))

    llm_client: AzureLLMClient = AzureLLMClient(base_url=API_BASE, api_key=os.getenv("API_KEY"),
                                                api_version=API_VERSION, model=MODEL_NAME)
    # self.llm_client = OpenAILLMClient(api_key=os.getenv("OPENAI_API_KEY"))

    llm_client = LLMClient(llm_client=llm_client,
                           system_prompt_plain_english=system_prompt_llm_english,
                           system_prompt_automation_steps=system_prompt_pw_steps_generation)

    # endregion

    # region LLM Service For Getting User Intent In Step Form

    intents: Intents = extract_intents_dynamic(user_prompt, llm_client=llm_client)

    # endregion

    # region Manual Programmatic Interpretation Of Steps Not Required, As LLM Can Support Here

    # -------- Seed Steps Not Required, As PW Steps Suggested By LLM, No Manual Programmatic Interpretation Required---
    # seeded_steps: List[Step] = seed_steps_from_intents(intents, default_wait=("domReady", 10000))

    # endregion

    # region Take Help From LLM To Convert Each Intent To Playwright Compatible Step And Execute Using DOM/Screenshot

    # -------- Phase 2: Grounder (per step) --------
    grounder = Grounder(cfg=cfg, llm=llm_client)

    executor = PWStepExecutor(cfg, run_dir)
    executor.start()
    try:

        final_steps = []
        # intent_list = [intent_item.intent for intent_item in intents.intents]

        # for intent in intent_list:
        for intent in intents.intents:
            dom_id, sc_id = executor.artifacts.latest_ids()
            dom_path = executor.artifacts.get_dom_path_by_id(dom_id) or ""
            sc_path = executor.artifacts.get_screenshot_path_by_id(sc_id) or ""

            dom_raw = _read_text_safe(dom_path) if dom_path else ""
            dom_summary = _summarize_dom_for_llm(dom_raw) if dom_raw else ""
            msg = f'Intent Being Processed is - {intent.step_no}. {intent.intent}'
            logger.info(msg)
            print(msg)
            g_step = grounder.get_pw_step_from_llm(
                intent.intent, dom_id=dom_id, sc_id=sc_id,
                artifact_dom=dom_summary,
                screenshot_path=sc_path
            )

            final_steps.extend(executor.execute_steps([g_step], intent.step_no))  # execute immediately

        executor.save_outputs(final_steps)

    finally:
        time.sleep(5)
        executor.close()

    # endregion

    # Export Playwright JSONL (codegen-style)
    jsonl_path = run_dir / "plan.playwright.jsonl"
    steps_to_playwright_jsonl(final_steps, jsonl_path)

    print(f"\nSaved outputs to: {run_dir.resolve()}")
    print(" - plan.json")
    print(" - artifacts.json")
    if cfg.logging.saveRunLog:
        print(" - run_log.json")
    print(" - plan.playwright.jsonl")


# endregion


if __name__ == "__main__":
    main()
