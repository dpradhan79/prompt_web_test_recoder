# region convert to defined schema in artifacts->def_out_schema_1.json
import json
import os
from pathlib import Path

import dotenv

from constant.const_config import LOG_FOLDER, SCHEMA_FILE, PARENT_DIR
from llm_service.azure_client import AzureLLMClient
from prompts.prompts_template import get_ai_sys_role_to_transform_artifacts_to_desired_schema, \
    get_ai_user_role_artifacts_to_transform_to_desired_schema

pw_style_file_json = 'playwright.jsonl'
plan_file_json = "plan.json"
artifacts_file_json = "artifacts.json"
run_log_file_json = "run_log.json"
schema_based_output_file_json = "schema_based_output.json"
log_folder = Path(os.path.join(LOG_FOLDER, f'run_20260205_222128'))
artifacts_contents = Path(log_folder / artifacts_file_json).read_text(encoding='utf-8')
plan_contents = Path(log_folder / plan_file_json).read_text(encoding='utf-8')
plan_pw_contents = Path(log_folder / pw_style_file_json).read_text(encoding='utf-8')
run_log_contents = Path(log_folder / run_log_file_json).read_text(encoding='utf-8')
schema_based_output_file_json_path = Path(log_folder / schema_based_output_file_json)

schema = Path(SCHEMA_FILE).read_text(encoding='utf-8')

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
API_BASE = "https://nt-genai-foundry-us2.cognitiveservices.azure.com/"
API_VERSION = "2025-01-01-preview"
MODEL_NAME = "gpt-4o"

# Azure OpenAI Configuration
dotenv.load_dotenv(dotenv_path=os.path.join(PARENT_DIR, ".env"))

llm_client: AzureLLMClient = AzureLLMClient(base_url=API_BASE, api_key=os.getenv("API_KEY"),
                                            api_version=API_VERSION, model=MODEL_NAME)
response = llm_client.execute_chat_completion_api(message=messages, response_format={"type": "json_object"})
schema_based_output_file_json_path.write_text(json.dumps(response, indent=2), encoding='utf-8')
