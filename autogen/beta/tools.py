# autogen/beta/tools.py
# Эмуляция @tools.tool декоратора

import inspect
from typing import Callable, Any


def tool(func: Callable) -> Callable:
    """Декоратор, помечающий функцию как инструмент агента."""
    func._is_tool = True
    return func


def function_to_openai_tool(func: Callable) -> dict:
    """Конвертирует Python-функцию в формат OpenAI function calling."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"

        properties[name] = {"type": param_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["description"] = f"По умолчанию: {param.default}"

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }
    }
