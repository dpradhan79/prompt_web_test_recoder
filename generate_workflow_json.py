# region convert to defined schema in artifacts->def_out_schema_1.json
import json
import os
from pathlib import Path

import dotenv

from constant.const_config import PARENT_DIR, LOG_FOLDER, SCHEMA_FILE
from llm_service.azure_client import AzureLLMClient

# region system prompt
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

# endregion

# region user prompt
log_folder =  Path(os.path.join(LOG_FOLDER, f'run_20260205_222128'))

artifacts_path = log_folder / "artifacts.json"
plan_path = log_folder / "plan.json"
plan_pw_path = log_folder / "plan.playwright.jsonl"
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

# endregion

# region USE LLM To Convert Existing json workflow to desired json work flow format
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
output_json_file = log_folder / "demo_work_flow.json"
messages = [
    {"role": "system", "content": system_prompt_wf_json},
    {"role": "user", "content": user_prompt_wf_json}
]
response = llm_client.execute_chat_completion_api(message=messages, response_format={"type": "json_object"})
output_json_file.write_text(json.dumps(response, indent=2), encoding='utf-8')

# endregion

# endregion