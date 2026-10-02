"""Runtime configuration, read from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    model_slm: str
    model_large: str
    model_default: str
    llm_timeout_s: float

    def resolve_model(self, name: str | None) -> str:
        """Map 'slm' / 'large' aliases to model ids; any other value is taken as a model id."""
        name = name or self.model_default
        return {"slm": self.model_slm, "large": self.model_large}.get(name, name)


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        llm_base_url=os.getenv("HS_LLM_BASE_URL", "http://localhost:1234/v1"),
        model_slm=os.getenv("HS_MODEL_SLM", "qwen/qwen3-4b-2507"),
        model_large=os.getenv("HS_MODEL_LARGE", "qwen2.5-7b-instruct"),
        model_default=os.getenv("HS_MODEL_DEFAULT", "large"),
        llm_timeout_s=float(os.getenv("HS_LLM_TIMEOUT_S", "120")),
    )
