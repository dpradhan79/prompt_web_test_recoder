# main.py
"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Main Script (Wiring)

"""
import json
import logging
import os
import sys

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from constant.const_config import PARENT_DIR, SCHEMA_FILE

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
    user_prompt_wf_json = (
        "Open JP Morgan site with url - https://am.jpmorgan.com/us/en/asset-management, "
        "Click on popup window with text - Individual Investors"
        "Click first 'search' button on header on top right of page, "
        "Type text 'Investment' to mimic user is typing, no 'fill' action in 'Search Input' textbox and click second search button, "
        "Click the first relevant link having JPMorgan text aligned to link"
    )

    # endregion

    # region LLM Initialization (LLM Control In LLMClient Interface, Needs Control At Top Layer.)
    # Use LLM client (One can Toggle Between Various LLM Models, Its Abstracted In LLMClient)

    # API_BASE = "https://aiml04openai.openai.azure.com"
    # API_VERSION = "2025-01-01-preview"
    # MODEL_NAME = "insta-gpt-4o"

    API_BASE = "https://nt-genai-foundry-us2.cognitiveservices.azure.com/"

    API_VERSION = "2025-01-01-preview"
    MODEL_NAME = "gpt-4o"

    # Azure OpenAI Configuration
    dotenv.load_dotenv(dotenv_path=os.path.join(PARENT_DIR, ".env"))

    llm_client: AzureLLMClient = AzureLLMClient(base_url=API_BASE, api_key=os.getenv("API_KEY"),
                                                api_version=API_VERSION, model=MODEL_NAME)
    # self.llm_client = OpenAILLMClient(api_key=os.getenv("OPENAI_API_KEY"))

    scrapper_client = LLMClient(llm_client=llm_client,
                           system_prompt_plain_english=system_prompt_llm_english,
                           system_prompt_automation_steps=system_prompt_pw_steps_generation)

    # endregion

    # region LLM Service For Getting User Intent In Step Form

    intents: Intents = extract_intents_dynamic(user_prompt_wf_json, llm_client=scrapper_client)

    # endregion

    # region Manual Programmatic Interpretation Of Steps Not Required, As LLM Can Support Here

    # -------- Seed Steps Not Required, As PW Steps Suggested By LLM, No Manual Programmatic Interpretation Required---
    # seeded_steps: List[Step] = seed_steps_from_intents(intents, default_wait=("domReady", 10000))

    # endregion

    # region Take Help From LLM To Convert Each Intent To Playwright Compatible Step And Execute Using DOM/Screenshot

    # -------- Phase 2: Grounder (per step) --------
    grounder = Grounder(cfg=cfg, llm=scrapper_client)

    executor = PWStepExecutor(cfg, run_dir)
    executor.start()
    final_steps = []
    try:


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



    finally:
        #time.sleep(5)
        executor.close()
        executor.save_outputs(final_steps)

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

    #region convert to defined schema in artifacts->def_out_schema_1.json

    #region system prompt
    system_prompt_wf_json = (
        """
       You are a transformation engine that synthesizes a single JSON document named new_work_flow_template.json that STRICTLY conforms to the provided “POC Workflow Schema (Minimal Scaffold + Screenshots)”.

INPUTS THE USER WILL PROVIDE (inline or as files):
- artifacts.json (screenshots + DOM snapshots with pathRef, url, timestamp, domHash)
- plan.json (planned intents/actions/locators with domReference/screenReference)
- plan.playwright.jsonl (per-step, codegen-style locators & args)
- run_log.json (executed steps: chosen locator, timings, meta, pass/fail)

OUTPUT:
- A SINGLE JSON OBJECT (UTF-8). Output ONLY the JSON—no prose, no comments.
- Use ONLY facts available in inputs. If data is missing, OMIT the field. Do NOT invent attributes or values.

PRECEDENCE (resolve contradictions with this order):
1) run_log.json
2) plan.playwright.jsonl
3) plan.json
4) artifacts.json

TOP-LEVEL FIELDS:
- schemaVersion: "1.0"
- stage: "A4" (or omit if user instructs otherwise)
- runId: derive from any run identifier in inputs (e.g., folder or meta); else omit
- status: "completed" if all steps passed in run_log; otherwise "partial" or "failed"
- constraintsApplied: include only constraints evidenced by inputs (e.g., "singleTabOnly", "awaitDomReady", "headedMode", "rankingWeights_id_gt_name", "role_label_independent")
- sourceContext:
  - baseUrl: from earliest navigation URL (protocol + host or host + base path if clear)
  - Include other fields ONLY if provided (adoWorkItemId, storyTitle, environment)
- executionContext:
  - browser, mode (headed/headless), startedAt, completedAt from run_log meta
  - durationSeconds: compute if both timestamps exist (completedAt - startedAt, in seconds)
- pages:
  - One entry per unique URL appearing in artifacts.dom[*].url
  - pageGuid: stable string identifier derived from URL (e.g., "page@{url}")
  - snapshots: for each artifacts.dom item belonging to that URL:
    - snapshotId: e.g., "dom-0001" (aligned to artifacts.dom.id)
    - triggeredByStepNo: map to the step with matching domReference or nearest logical step number
    - capturedAt: copy EXACT timestamp
    - storageRef: copy EXACT pathRef
    - hash: copy EXACT domHash (omit if not present)
  - screenshots (optional): include ONLY if artifacts.json.screenshots exist
    - For each artifacts.screenshots item matching this page URL:
      - snapshotId: e.g., "screen-0001" (aligned to artifacts.screenshots.id) or leave as provided if an id is given
      - triggeredByStepNo: the step index that aligns to the screenshot timing/screenReference; if unclear, omit
      - capturedAt: copy EXACT timestamp
      - storageRef: copy EXACT pathRef
      - hash: include only if explicitly provided (do NOT compute)
      - domSnapshotId: link to the nearest "dom-XXXX" if you can confidently map by time/url/reference; else omit
- stepBindings:
  - For each executed step in run_log.steps:
    - stepNo: run_log.steps.index
    - stepName: the action (e.g., "navigate", "click", "press_sequentially")
    - description: use the intent from plan or run_log if provided
    - pageGuid: the page URL matching the step’s domReference (via artifacts.dom.url)
    - domSnapshotId: "dom-XXXX" based on the step’s domReference
    - targetHint:
      - role: ARIA role if present from inputs (e.g., button, link, textbox, combobox)
      - label: accessible name ONLY (aria-label, getByLabel, explicit form labels). Do NOT merge with role.
    - locatorCandidates: ordered list (best to worst) of candidates EVIDENCED by inputs. For each:
      - rank (1 = best after scoring), tier (bucket by final score), type, value, matchCount (if known), stability, why (1–2 sentences)
      - Canonical types: testhook, id, name, role, label, text, placeholder, css, xpath, relative
      - Selenium-first preference: testhook/id/name > role/label > text/placeholder > css/xpath > relative
      - You MAY include a composite CSS candidate that CONJOINS multiple REAL attributes (e.g., [aria-label='X'] plus another non-positional attribute) ONLY if ALL such attributes are clearly evidenced in the inputs. Do NOT invent [role='…'] unless it is explicitly present as an attribute. If role is only implied (via Playwright), do NOT emit [role='…'] CSS.
      - If indexing/positional logic was used (e.g., .nth(1), :nth-of-type(2), XPath [2]), add a separate “relative” candidate to reflect positional reliance.
    - chosenLocator:
      - Reflect what actually worked (per run_log). Use the closest matching candidate type and its value (e.g., “text”: "Search", “css”: "button.search-button:nth-of-type(2)", “placeholder”: "Search").
    - evidence:
      - elementFingerprint:
        - tag: include only if safely implied from inputs (e.g., “button” from class “search-button” or role/button). Omit if uncertain.
        - attributes: include only attributes explicitly implied by chosen locator or candidates (e.g., class, placeholder, href substring, aria-label). Do NOT invent.
      - outerHtmlSnippet: OMIT unless a verbatim snippet is provided in inputs.

- unboundSteps: steps that couldn’t be resolved or were skipped; include reason + recommendation
- warnings: array of { stepNo, reason } for ambiguity, index-based fragility, or when a stronger evidenced candidate exists than what was executed
- artifacts:
  - a4JsonRef: if a canonical A4 step bindings file path exists in inputs, include it; else include the most relevant source file path or omit
  - domSnapshotRefs: array of artifacts.dom[*].pathRef in observed order
  - screenSnapshotRefs (optional): array of artifacts.screenshots[*].pathRef in observed order
  - logRef: a path or label to run_log.json if provided

LOCATOR RANKING POLICY (id > name; role & label independent):
- Canonical types: testhook, id, name, role, label, text, placeholder, css, xpath, relative
- Strategy weights (BaseScore):
    testhook: 1.00  // any attribute whose NAME contains “test” (case-insensitive) e.g., data-testid, data-test-id, dataTestId, data-test
    id:       0.95
    name:     0.90
    role:     0.80  // ARIA role ONLY (e.g., button, link); do NOT bundle label with role
    label:    0.75  // accessible name (aria-label, getByLabel, <label for=…>)
    text:     0.70
    placeholder: 0.60
    css:      0.50
    xpath:    0.45
    relative: 0.40

- Adjustments (additive; clamp to [0, 1]):
    • Composite CSS that CONJOINS multiple REAL attributes (e.g., [aria-label='X'] + another non-positional attribute)  +0.35
        - ONLY if EVERY attribute is explicitly present in inputs (e.g., aria-label is present; role as attribute is present). 
        - Never assume [role='…'] exists unless DOM shows a role attribute or inputs explicitly state it.
        - Cap composite CSS at ≤ 0.90 so it never outranks a true id (0.95) or testhook (1.00).
    • Index/positional penalty (.nth(n), :nth-of-type(n), XPath [n])  −0.10
    • Ambiguity penalty (matchCount ≥ 2 or strict-mode violations)    −0.05
    • Exact visible text bonus (for text exact match only)            +0.03
    • Substring attribute penalty (e.g., a[href*='...'])              −0.02

- Stability labels:
    high:    testhook, id, name (non-index), exact unique text, exact unique label, composite CSS (non-index) when attributes are confirmed
    medium:  role, placeholder, generic class/attribute CSS, substring attribute matches, any index usage
    low:     xpath (esp. indexed), text contains, positional/DOM-order dependent selectors

- Tie-break (after final score):
    1) Lower matchCount first (more unique)
    2) Stability: high > medium > low
    3) Specificity: attribute selectors (testhook/id/name/label/confirmed composite CSS) > class CSS > generic text
    4) Non-indexed > indexed
    5) Shorter selector
    6) Source precedence: run_log > jsonl > plan

CHOSEN LOCATOR SELECTION:
- Always mirror what actually worked in run_log for chosenLocator to preserve reproducibility.
- If brittle (index-based or ambiguous), keep it but add:
  - a “relative” candidate to reflect positional reliance
  - a “warnings” entry recommending the most stable evidenced candidate (e.g., testhook, id, name, or label; or composite CSS if attributes are explicitly present)
- NEVER emit a candidate that is not evidenced by inputs. Do NOT invent [role='…'] attributes unless present.

SCREENSHOTS HANDLING (optional):
- If artifacts.json includes screenshots[], include a “screenshots” array per page with entries carrying snapshotId, triggeredByStepNo (if confidently mapped), capturedAt, storageRef, and optionally domSnapshotId.
- Do NOT compute or fabricate image hashes. If not provided, omit “hash”.
- Also populate artifacts.screenSnapshotRefs with the screenshot pathRef values in observed order.

SERIALIZATION & VALIDATION RULES:
- Output must be valid JSON with double quotes, no trailing commas.
- Preserve all timestamps, paths, and hashes EXACTLY as given.
- If an array would be empty, output an empty array (e.g., "warnings": []) rather than omitting it.
- Do not include extra fields not defined by the schema (other than allowed by additionalProperties).

END.
        """

    )

    #endregion

    #region user prompt
    log_folder = executor.run_dir

    artifacts_path = log_folder / "artifacts.json"
    plan_path = log_folder / "plan.json"
    plan_pw_path = jsonl_path
    runlog_path = log_folder / "run_log.json"
    schema = Path(SCHEMA_FILE).read_text(encoding='utf-8')
    artifacts_json = artifacts_path.read_text(encoding='utf-8')
    plan_json = plan_path.read_text(encoding='utf-8')
    plan_pw_json = plan_pw_path.read_text(encoding='utf-8')
    run_log_json = runlog_path.read_text(encoding='utf-8')
    user_prompt_wf_json = (
       f"""
       Build new_work_flow_template.json using ONLY the provided inputs. Omit unknown fields. Do not guess. Output only the JSON object (no prose).

    ### Schema (for validation)
{schema}

### Inputs
artifacts.json:
{artifacts_json}

plan.json:
{plan_json}

plan.playwright.jsonl:
{plan_pw_json}

run_log.json:
{run_log_json}

### Output requirements
- Output only the JSON object (no prose).
- Follow the locator ranking policy (id > name; role & label independent; composite CSS only when ALL attributes are explicitly present in inputs).
- Group DOM snapshots by page URL.
- If screenshots exist, include pages[*].screenshots[] with snapshotId, capturedAt, storageRef, and optional triggeredByStepNo/domSnapshotId (only when confidently mapped).
- Populate artifacts.domSnapshotRefs and, if available, artifacts.screenSnapshotRefs from artifacts.json.
- Map each step to domSnapshotId using domReference.
- Compute durationSeconds from startedAt/completedAt if present.

       """


    )

    #endregion

    # region USE LLM To Convert Existing json workflow to desired json work flow format

    output_json_file = log_folder / "demo_work_flow.json"
    messages = [
        {"role":"system", "content": system_prompt_wf_json},
        {"role":"system", "content": user_prompt_wf_json}
    ]
    response = llm_client.execute_chat_completion_api(message=messages, response_format={"type": "json_object"})
    output_json_file.write_text(json.dumps(response, indent=2), encoding='utf-8')
    msg = f'Comprehensive Workflow output - {output_json_file}'
    print(msg)
    logger.info(msg)

    #endregion

    #endregion


# endregion


if __name__ == "__main__":
    main()
