# app.py
"""
Date                    Author                          Change Details
02-02-2026              Coforge                         Main Script (Wiring)

"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from constant.const_config import PARENT_DIR, SCHEMA_FILE
from prompts.prompts_template import get_ai_sys_role_for_use_case_to_intent_mapping, \
    get_ai_sys_role_for_intent_to_pw_step_mapping, get_ai_user_role_artifacts_to_transform_to_desired_schema, \
    get_ai_sys_role_to_transform_artifacts_to_desired_schema

ROOT = PARENT_DIR
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import dotenv

from dataclass.conceptual_objects import Intents, Step
from pw_lib_ext.config import AppConfig
from llm_service.grounder import (
    extract_intents_dynamic,
    Grounder,
    LLMAgent, _read_text_safe, _summarize_dom_for_llm, sanitize_html_for_llm
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
    cfg.browser.recordVideo = True

    # ------------

    cfg.grounding.assertionMode = "regex"  # "exact" or "regex"
    cfg.grounding.assertionAlsoCheckVisible = True
    cfg.grounding.artifactPolicy.captureOnAutoSuggestVisible = True
    cfg.grounding.artifactPolicy.captureOnEveryStep = True
    cfg.grounding.artifactPolicy.fullPageScreenshots = True
    cfg.grounding.maxAltLocatorsPerStep = 3

    cfg.logging.verbosity = "verbose"
    cfg.logging.saveRunLog = True

    # region Generated File Details
    time_stamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")
    log_dir = Path(os.path.join(LOG_FOLDER, f'run_{time_stamp}'))
    log_dir.mkdir(parents=True, exist_ok=True)
    pw_style_file_json = 'playwright.jsonl'
    plan_file_json = "plan.json"
    artifacts_file_json = "artifacts.json"
    run_log_file_json = "run_log.json"
    schema_based_output_file_json = "schema_based_output.json"
    # endregion

    # endregion

    # region LLM Initialization

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
    # llm_client = OpenAILLMClient(api_key=os.getenv("OPENAI_API_KEY"))

    # endregion

    # region Define Prompt For LLM -> User Story To List Of Intents - > [Execute Each UI Action For Each Intent ]

    # -------- Phase 1: Intents --------
    system_prompt_llm_english = get_ai_sys_role_for_use_case_to_intent_mapping()
    system_prompt_pw_steps_generation = get_ai_sys_role_for_intent_to_pw_step_mapping()

    # endregion

    # region Define Agent For Communication With AI Model

    llm_agent = LLMAgent(llm_client=llm_client,
                         system_prompt_plain_english=system_prompt_llm_english,
                         system_prompt_automation_steps=system_prompt_pw_steps_generation)

    # endregion

    # region User's Story

    user_prompt_wf_json = (

        "Open JP Morgan site with url - https://am.jpmorgan.com/us/en/asset-management, "
        "Click on popup window with text - Individual Investors"
        "Click first 'search' button on header on top right of page, "
        "Type text 'Investment' to mimic user is typing, no 'fill' action in 'Search' textbox in header below last clicked search button "
        "and click second search button with visible text 'Search' to right of textbox where 'Investment' was typed, "
        "Click the first relevant link having JPMorgan text aligned to link"
    )
    # endregion

    # region LLM Service For Getting Use Case Into Intents
    intents: Intents = extract_intents_dynamic(user_prompt_wf_json, llm_client=llm_agent)

    # endregion

    # -------- Phase 2: Grounder (per step) --------

    # region Ground The Intent To Actual Tool Based UI Action
    grounder = Grounder(cfg=cfg, llm=llm_agent)

    runner = PWStepExecutor(cfg, log_dir)
    runner.start()
    final_steps = []
    try:
        for intent in intents.intents:
            dom_id, sc_id = runner.artifacts.latest_ids()
            dom_path = runner.artifacts.get_dom_path_by_id(dom_id) or ""
            sc_path = runner.artifacts.get_screenshot_path_by_id(sc_id) or ""

            dom_raw = _read_text_safe(dom_path, limit=5_000_000) if dom_path else ""
            dom_clean = sanitize_html_for_llm(dom_raw, max_attr_len=1024) if dom_raw else ""
            dom_summary = _summarize_dom_for_llm(dom_clean, max_chars=5_000_000) if dom_raw else ""
            msg = f'Intent Being Processed is - {intent.step_no}. {intent.intent}'
            logger.info(msg)
            print(msg)
            g_step = grounder.get_pw_step_from_llm(
                intent.intent, dom_id=dom_id, sc_id=sc_id,
                artifact_dom=dom_summary,
                screenshot_path=sc_path
            )

            steps: List[Step] = runner.execute_steps([g_step], intent.step_no)
            final_steps.extend(steps)
    except Exception as e:
        runner.close()
        msg = f'Exception Encountered - {type(e).__name__}'
        print(msg)
        logger.info(msg)
        raise e

    finally:
        runner.close()

        # region Write Execution Info To Log / JSON file
        msg = (f'Execution Completed...'
               f'\nArtifacts Being Generated...'
               f'\nLog Details Will Be Shared Soon...'
               f'\nAppreciate Your Patience...'
               )
        print(msg)
        logger.info(msg)
        runner.save_outputs(final_steps,
                            plan_file=plan_file_json,
                            artifacts_file=artifacts_file_json,
                            run_log_file=run_log_file_json)
        jsonl_path = log_dir / pw_style_file_json
        steps_to_playwright_jsonl(final_steps, jsonl_path)
        schema = Path(SCHEMA_FILE).read_text(encoding='utf-8')

        log_folder = runner.run_dir
        artifacts_contents = Path(log_folder / artifacts_file_json).read_text(encoding='utf-8')
        plan_contents = Path(log_folder / plan_file_json).read_text(encoding='utf-8')
        plan_pw_contents = Path(log_folder / pw_style_file_json).read_text(encoding='utf-8')
        run_log_contents = Path(log_folder / run_log_file_json).read_text(encoding='utf-8')
        schema_based_output_file_json_path = Path(log_folder / schema_based_output_file_json)

        system_prompt_to_generate_output_in_desired_schema = get_ai_sys_role_to_transform_artifacts_to_desired_schema()
        user_prompt_to_generate_output_in_desired_schema = get_ai_user_role_artifacts_to_transform_to_desired_schema(
            schema=schema,
            artifacts_json=artifacts_contents,
            plan_json=plan_contents,
            pw_json=plan_pw_contents,
            run_log_json=run_log_contents
        )
        messages = [
            {"role": "system", "content": system_prompt_to_generate_output_in_desired_schema},
            {"role": "system", "content": user_prompt_to_generate_output_in_desired_schema}
        ]
        response = llm_client.execute_chat_completion_api(message=messages, response_format={"type": "json_object"})
        schema_based_output_file_json_path.write_text(json.dumps(response, indent=2), encoding='utf-8')

        # endregion

        # region Display Log Details

        msg = (f'\nThanks For Your Patience...\n'
               f'Here is log details...\n'
               f'Saved outputs to - {log_dir.resolve()}\n'
               f' - {plan_file_json}\n'
               f' - {artifacts_file_json}\n'
               f' - {pw_style_file_json}\n'
               f' - {run_log_file_json if cfg.logging.saveRunLog else ""}\n'
               f' - {schema_based_output_file_json}')

        print(msg)
        logger.info(msg)

        # endregion

    # endregion


# endregion

if __name__ == "__main__":
    main()
