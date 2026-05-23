# autogen/beta/__init__.py
# Совместимый слой, эмулирующий autogen.beta API через openai

from .agent import Agent
from . import config
from .memory import MemoryStream
from . import tools
