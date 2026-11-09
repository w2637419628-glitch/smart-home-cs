"""套路召回：按客户这句话做语义检索，取回店长教过的 top-k 条话术。

这是"自进化"能被感知到的入口——店长教得越多，这个工具捞得越准。
只召回【审核通过】的样本，待审的不参与服务。
"""
from __future__ import annotations

from typing import Any

from ... import config
from ...services import playbook_service
from .base import Tool


class RecallPlaybookTool(Tool):
    name = "recall_playbook"
    description = (
        "检索店长教过的、与客户当前这句话最相关的示范话术"
        "（客户问题 + 标准答案 + 这么答的原因）。回答任何咨询前先调它，"
        "再判断这句话属于哪一类、该怎么应对。"
    )

    def run(self, query: str = "", **kwargs: Any) -> dict[str, Any]:
        samples = playbook_service.recall_topk(query or "", config.PLAYBOOK_TOP_K)
        top = samples[0].get("score", 0.0) if samples else 0.0
        covered = bool(samples) and top >= config.PLAYBOOK_HIT_THRESHOLD
        return {
            "count": len(samples),
            "top_score": round(top, 3),
            "covered": covered,
            "hint": "" if covered else (
                "没有找到匹配的话术，说明店长没教过这个问题。"
                "这种情况必须调用 handoff 转人工，绝对不要凭常识猜一个答案。"
            ),
            "samples": samples,
        }
