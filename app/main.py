"""FastAPI 入口：对话、教学、待审、总纲、工单、看板。

本项目对外只暴露 HTTP API，界面用 FastAPI 自动生成的交互式文档（/docs）。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import config
from .db import init_db
from .llm.factory import provider_name
from .models import (ChatRequest, ChatResponse, DirectiveUpdate, SummaryUpdate,
                     TeachRequest, TicketTeachRequest)
from .services import (chat_service, coach_service, lead_service,
                       playbook_service, quota_service, review_service,
                       settings_service)

app = FastAPI(title=config.APP_NAME)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    n = playbook_service.seed_if_empty()
    if n:
        print(f"[init] 已灌入 {n} 条种子话术（店长已教过的经验）")


# ---------------- 咨询对话 ----------------

def _client_ip(request: Request) -> str:
    """取真实客户端 IP。挂在 nginx 后面时看 X-Forwarded-For。"""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    ok, msg = quota_service.check_and_consume(_client_ip(request))
    if not ok:
        raise HTTPException(status_code=429, detail=msg)

    result = chat_service.handle_chat(req.message, req.session_id)
    lead = lead_service.get(req.session_id) or {}
    return ChatResponse(
        reply=result.reply,
        handoff=result.handoff,
        ticket_id=result.ticket_id,
        survey_id=result.survey_id,
        trace=result.trace,
        lead={k: lead.get(k) for k in list(config.SLOT_KEYS) + ["stage"] if lead.get(k)},
        slots_filled=lead_service.filled_count(lead),
        slots_total=len(config.SLOT_KEYS),
    )


@app.post("/api/session/reset")
def reset_session(session_id: str = "demo") -> dict:
    chat_service.reset_session(session_id)
    return {"ok": True}


@app.get("/api/lead/{session_id}")
def get_lead(session_id: str) -> dict:
    lead = lead_service.get(session_id) or {}
    return {
        "lead": lead,
        "filled": lead_service.filled_count(lead),
        "total": len(config.SLOT_KEYS),
        "missing": lead_service.missing_slots(lead),
    }


# ---------------- 教学模式 ----------------

@app.post("/api/teach")
def teach(req: TeachRequest) -> dict:
    """店长教一条 → 进【待审】队列（通过后才生效）。"""
    sample_id = playbook_service.add_sample(
        req.question, req.answer, req.note, source="taught",
        scene=req.scene, status="pending")
    return {"ok": True, "sample_id": sample_id, "status": "pending"}


@app.get("/api/playbook")
def list_playbook(status: str | None = None, source: str | None = None) -> list[dict]:
    return playbook_service.list_samples(status, source)


@app.post("/api/playbook/{sample_id}/approve")
def approve(sample_id: int) -> dict:
    """审核通过 = 入库 + 自动归纳总纲 + 关闭"同一个问题"的重复工单。"""
    playbook_service.approve_sample(sample_id)
    out: dict = {"ok": True, "summary_changed": False, "tickets_closed": 0}
    if config.AUTO_REFRESH_SUMMARY:
        r = coach_service.refresh_summary()
        out.update({"summary_changed": r["changed"], "added": r.get("added", []),
                    "summary": r.get("summary", "")})
    # 学会了 → 把同一个问题的其它工单一起收掉
    sample = playbook_service.get_sample(sample_id)
    if sample:
        out["tickets_closed"] = review_service.close_merged_tickets(sample["question"])
    return out


@app.post("/api/playbook/{sample_id}/reject")
def reject(sample_id: int) -> dict:
    return playbook_service.reject_sample(sample_id)


@app.delete("/api/playbook/{sample_id}")
def delete_sample(sample_id: int) -> dict:
    return playbook_service.delete_sample(sample_id)


# ---------------- 套路总纲 ----------------

@app.get("/api/summary")
def get_summary() -> dict:
    """已保存的总纲；从未生成过则首次自动归纳（会调一次模型）。"""
    summary = settings_service.get_summary()
    if not summary.strip() and playbook_service.count("approved") > 0:
        r = coach_service.refresh_summary(force_all=True)
        summary = r["summary"]
    prev = settings_service.get_summary_prev()
    added, removed = coach_service.diff_summary(prev, summary)
    return {"summary": summary, "prev": prev, "added": added, "removed": removed}


@app.put("/api/summary")
def save_summary(req: SummaryUpdate) -> dict:
    """店长手动改写总纲（重归纳时会被保留，不会被覆盖）。"""
    settings_service.set_summary(req.text)
    return {"ok": True}


@app.post("/api/summary/refresh")
def refresh_summary(force_all: bool = False, rebuild: bool = False) -> dict:
    return coach_service.refresh_summary(force_all=force_all, rebuild=rebuild)


# ---------------- 工单 / 待审 ----------------

@app.get("/api/tickets")
def list_tickets(kind: str | None = None, status: str | None = None,
                 annotate: bool = True) -> list[dict]:
    return review_service.list_tickets(kind, status, annotate=annotate)


@app.post("/api/tickets/{ticket_id}/close")
def close_ticket(ticket_id: int) -> dict:
    return review_service.close_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/teach")
def teach_ticket(ticket_id: int, req: TicketTeachRequest) -> dict:
    return review_service.teach_from_ticket(ticket_id, req.answer, req.note)


# ---------------- 业务设定 / 提示词 ----------------

@app.get("/api/settings/directive")
def get_directive() -> dict:
    return {"directive": settings_service.get_directive()}


@app.put("/api/settings/directive")
def put_directive(req: DirectiveUpdate) -> dict:
    return settings_service.set_directive(req.text)


@app.get("/api/settings/system-prompt")
def get_system_prompt() -> dict:
    """完整生效的系统提示词（四层拼装后的原文），用于核对"到底教进去了什么"。"""
    return {"prompt": coach_service.effective_system_prompt()}


# ---------------- 看板 / 状态 ----------------

@app.get("/api/metrics")
def metrics() -> dict:
    return review_service.metrics()


@app.get("/api/status")
def status() -> dict:
    return {"app": config.APP_NAME, "tagline": config.APP_TAGLINE,
            "provider": provider_name(),
            "auto_refresh_summary": config.AUTO_REFRESH_SUMMARY,
            "quota": quota_service.snapshot(),
            "slots": [{"key": k, "label": lb} for k, lb, _ in config.REQUIRED_SLOTS]}


# ---------------- 根路径 ----------------

@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """本项目对外只提供 HTTP API，界面用 FastAPI 自动生成的 /docs。"""
    return RedirectResponse(url="/docs")
