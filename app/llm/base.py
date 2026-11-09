"""LLM 提供方抽象。

Agent Loop 只依赖这个接口：把 messages + 可用工具交给模型，拿回一个决策。
换模型（DeepSeek / 豆包 / 本地）只需实现 chat()，引擎与工具零改动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """模型本步请求调用的单个工具。id 用于结果回填时配对。"""
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMDecision:
    """一次模型决策。

    type == "tool_call"  需要调用 tool_calls（可一步并行多个）
    type == "final"      产出最终回复 content
    thought              本步思考，仅用于轨迹可视化
    """
    type: str
    thought: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    content: Optional[str] = None


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]]) -> LLMDecision:
        """根据对话历史（含已执行的工具结果）与可用工具，决定下一步。"""
        raise NotImplementedError
