"""LLM 提供方工厂：配置驱动切换，失败自动降级到离线桩。"""
from __future__ import annotations

from .. import config
from .base import LLMDecision, LLMProvider, ToolCall  # noqa: F401  (对外导出)

_PROVIDER: LLMProvider | None = None


def build_provider(force: bool = False) -> LLMProvider:
    global _PROVIDER
    if _PROVIDER is not None and not force:
        return _PROVIDER

    if config.LLM_PROVIDER == "openai":
        try:
            from .openai_provider import OpenAICompatProvider
            _PROVIDER = OpenAICompatProvider()
            return _PROVIDER
        except Exception as exc:  # 没配 key / 依赖缺失 → 降级，演示不中断
            print(f"[warn] 真实模型不可用（{exc}），降级为离线桩 mock。")

    from .mock_provider import MockLLMProvider
    _PROVIDER = MockLLMProvider()
    return _PROVIDER


def provider_name() -> str:
    return "openai:" + config.LLM_MODEL if config.LLM_PROVIDER == "openai" else "mock(离线桩)"
