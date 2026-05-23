# autogen/beta/config.py
# Эмуляция autogen.beta.config.OpenAIConfig

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OpenAIConfig:
    model: str = "deepseek-v4-pro"
    temperature: float = 0.7
    max_tokens: int = 2048
    api_key: str = ""
    base_url: Optional[str] = None
    default_headers: Optional[dict] = field(default_factory=dict)
