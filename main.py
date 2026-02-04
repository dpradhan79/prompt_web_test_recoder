# main.py
"""
Date                    Author                          Change Details
02-02-2026              Debasish.P                      Main Script (Wiring)

"""
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
        "You are a UI action grounder with vision capability.\n\n"
        "Given ONE intent and the current page's DOM and screenshot, emit ONE step executable by Playwright automation tools.\n"
        "The generated action should be compliant to Playwright which can be later used by downstream technology \n"
        "and framework specific tools such as selenium, cypress and Playwright itself. \n"
        "Where ever possible, role should be used and for any link, role with link should be used so that \n"
        "playwright can use those references for execution. \n"
        "Provide the best locator and alternate locators based on vision capability by looking at DOM and Screenshot provided with user prompt.\n"
        "The best locator should be based on what's visible on Page To Normal Person.\n"
        "locator should have index in output json structure if role and name is used so that locator().nth(index=index) be used"
        "The text provided by User as intent should be considered as case sensitive,\n"
        "then if case sensitive text is not available then best intuition should be applied to find closest locator based on intent\n"
        "For example - If intent says about - 'Career' and both 'Career' and 'CAREER' is available, the 'Career' should be opted,\n"
        "if 'Career' is found multiple times, then best context should be applied with index in output structure\n"
        "if typing error is noticed such that 'carrier' is not found, rather 'Career' is found,\n"
        "best intuition and context with vision capability should be applied to find most semantics closer locator"
        "Also, use your best knowledge to perform action in corrective mode even if user is mistyped or action does not make sense to current context such as - \n"
        "example - If Intent is Press to button, it should be considered as Click as Press, Type, Fill is not relevant to Button"
        "If intent is Type or enter or fill text,  transform action into - press_sequentially to mimic actual key strokes to trigger events"
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
        '  "action": "navigate|click|press_sequentially|fill|press|select|check|uncheck|hover|scroll|waitFor|assert_text|assert_visible|assert_match|custom",\n'
        '  "input": "<string or null>",\n'
        '  "locator": {{ "strategy": "role|label|dataTestId|aria|text|placeholder|css|xpath|relative",\n'
        '               "role": "<if role>", "name": "<if role/aria>", "value": "<if text/placeholder/label/dataTestId/css/xpath/relative>",\n'
        '               "frame": null, \n'
        '               "index": <int> }},\n'
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
        "convert action such as type, enter, fill to press_sequentially"
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
