"""
Date                            Author                                          Changes

"""
import json
import logging
import time
from abc import ABC
from multiprocessing.context import AuthenticationError
from typing import List, Dict

from openai import OpenAI, BadRequestError, PermissionDeniedError

logger = logging.getLogger(__name__)


class AbstractLLMClient(ABC):
    def __init__(self, init_client_config: dict):
        self.history: List[Dict] = []
        self.base_url = init_client_config.get("base_url") if init_client_config.get("base_url") else None
        self.api_key = init_client_config.get("api_key") if init_client_config.get("api_key") else None
        self.api_version = init_client_config.get("api_version") if init_client_config.get("api_version") else None
        self.model = init_client_config.get("model") if init_client_config.get("model") else None
        self.client: OpenAI = init_client_config.get("client") if init_client_config.get("client") else None
        client_msg = f'Initialized' if self.client is not None else None
        logger.info(
            f'base_url: {self.base_url}, api_version: {self.api_version}, model: {self.model}, client: {client_msg}')

    def execute_chat_completion_api(self, message: List[Dict], response_format=None,
                                    temperature=0.2, max_tokens=16000
                                    ) -> str:
        if response_format is None:
            response_format = dict(
                type="json_object")
        success: bool = False
        MAX_ATTEMPT_COUNTER = 2
        attempt_counter = 1
        while not success and attempt_counter <= MAX_ATTEMPT_COUNTER:
            print(f'Fetching LLM Chat Completion API Response (Attempt Counter) - {attempt_counter}')
            try:

                response = self.client.chat.completions.create(model=self.model,
                                                               messages=message,
                                                               response_format=response_format,
                                                               temperature=temperature,
                                                               max_tokens=max_tokens)

                logger.info(f'chat completion response after Attempt - {attempt_counter}- \n '
                            f'message - {message} \n'
                            f'response - {response}')
                success = True
                if response_format.get("type") in "json_object":
                    return json.loads(response.choices[0].message.content)
                else:
                    return response.choices[0].message.content
            except AuthenticationError as e:
                msg = 'LLM Authentication Error'
                logger.info(msg)
                print(msg)
                raise e
            except BadRequestError as e:
                msg = 'LLM Bad Request Error'
                logger.info(msg)
                print(msg)
                raise e
            except PermissionDeniedError as e:
                msg = 'LLM Permission Denied Error'
                print(msg)
                raise e

            except Exception as e:
                attempt_counter += 1
                time.sleep(1)
                if not success and attempt_counter > MAX_ATTEMPT_COUNTER:
                    raise ValueError(f'LLM Codel - Chat Completion Not Working')
        return None

    def add_chat_history(self, list_message):
        self.history.append(list_message)

    def get_chat_history(self):
        return self.history
