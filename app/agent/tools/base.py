"""工具统一接口。

每个工具向模型暴露 name / description / parameters(JSON Schema)，
run() 返回结构化 dict；异常交给 Loop 包装成 observation，不在这里吞掉。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    name: str = ""
    description: str = ""
    # 默认单参数 query；需要结构化入参的工具自行覆盖
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户问题原文"},
        },
        "required": ["query"],
    }

    @abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "parameters": self.parameters}
