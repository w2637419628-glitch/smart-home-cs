"""工具注册表。新增能力 → 在这里登记一行，Agent Loop 立刻能用。"""
from .base import Tool
from .recall_playbook import RecallPlaybookTool
from .save_requirements import SaveRequirementsTool
from .package_search import PackageSearchTool
from .case_search import CaseSearchTool
from .book_survey import BookSurveyTool
from .handoff import HandoffTool


def build_registry() -> dict[str, Tool]:
    tools: list[Tool] = [
        RecallPlaybookTool(),
        SaveRequirementsTool(),
        PackageSearchTool(),
        CaseSearchTool(),
        BookSurveyTool(),
        HandoffTool(),
    ]
    return {t.name: t for t in tools}
