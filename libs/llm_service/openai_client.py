import logging

from openai import OpenAI

from libs.abstract.abstract_llm_client import AbstractLLMClient

logger = logging.getLogger(__name__)


class OpenAILLMClient(AbstractLLMClient):
    def __init__(self, api_key: str, model: str = 'gpt-4o-mini'):
        self.api_key = api_key
        self.model = model
        try:
            self.client = OpenAI(
                api_key=self.api_key
            )
            logger.info("Azure OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Azure OpenAI client: {e}")
            raise e

        init_client_config = {
            "api_key": self.api_key,
            "model": self.model,
            "client": self.client
        }

        super().__init__(init_client_config)
