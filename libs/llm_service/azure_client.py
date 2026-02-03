import logging

from openai import AzureOpenAI

from libs.abstract.abstract_llm_client import AbstractLLMClient

logger = logging.getLogger(__name__)


class AzureLLMClient(AbstractLLMClient):
    def __init__(self, base_url: str = None, api_key: str = None, api_version: str = None, model: str = None):
        self.base_url = base_url
        self.api_key = api_key
        self.api_version = api_version
        self.model = model
        try:

            self.client = AzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.base_url,
                api_key=self.api_key,

            )
            logger.info("Azure OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Azure OpenAI client: {e}")
            raise e

        init_client_config = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "api_version": self.api_version,
            "model": self.model,
            "client": self.client
        }

        super().__init__(init_client_config)
