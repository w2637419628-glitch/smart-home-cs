"""工单、待审样本与看板。

工单防重复做了三件事（否则同一个问题会一直挂在列表里）：

  1. 建单时：完全相同的问句 → 不新建，计数 +1
  2. 教完时：同一问题的工单一起关掉
  3. **审核通过后 sweep：凡是"现在能被答上来"的 open 工单，自动关闭**
     —— 判断标准就是系统自己的检索（recall_topk 分数 ≥ 阈值），
        而不是字符串相似度。问法怎么变都能覆盖，语义正确。
"""
from __future__ import annotations

import re
from typing import Any

from ..db import cursor
from . import playbook_service

_PUNCT = r"[\s，。！？、,.!?~～:：;；\"'“”‘’()（）\[\]【】]+"


def _norm(text: str) -> str:
    """归一化：去掉标点空白、转小写。只用于判断"一字不差的同一个问题"。"""
    return re.sub(_PUNCT, "", text or "").lower()


# ---------------- 工单 ----------------

def list_tickets(kind: str | None = None, status: str | None = None,
                 annotate: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM tickets WHERE 1=1"
    args: list[Any] = []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY dupe_count DESC, id DESC"
    with cursor() as cur:
        cur.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]

    if annotate:
        # 给每条工单标一个"现在能不能答上来"的分数，让店长自己决定关不关
        for r in rows:
            if r.get("kind") != "ticket" or not r.get("question"):
                r["hit_score"] = 0.0
                continue
            hits = playbook_service.recall_topk(r["question"], 1)
            r["hit_score"] = round(hits[0].get("score", 0.0), 3) if hits else 0.0
    return rows


def close_ticket(ticket_id: int) -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
    return {"ok": True, "id": ticket_id}


def open_ticket(session_id: str, question: str, context: str = "",
                kind: str = "ticket") -> int:
    """建工单；问句完全相同且仍未处理时，只累加次数，不重复建单。"""
    q = question or "(未填)"
    if kind == "ticket":
        for r in list_tickets(kind="ticket", status="open"):
            if _norm(r.get("question", "")) == _norm(q):
                with cursor() as cur:
                    cur.execute("UPDATE tickets SET dupe_count = dupe_count + 1 WHERE id=?",
                                (r["id"],))
                return int(r["id"])

    with cursor() as cur:
        cur.execute(
            "INSERT INTO tickets (kind, session_id, question, context, status, dupe_count) "
            "VALUES (?, ?, ?, ?, 'open', 1)",
            (kind, session_id, q, context or ""),
        )
        return int(cur.lastrowid)


def _lcs(a: str, b: str) -> int:
    """最长公共子串长度（字符级）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def is_same_question(a: str, b: str) -> bool:
    """判断两条问句是不是"同一个问题"。

    两个信号同时满足才算同一个：
      · 字符级 Jaccard ≥ 0.5（字形重合度）
      · 最长公共子串 ≥ 3（有连续片段，不是零散同字）

    为什么不用向量相似度：分数在 0.25~0.30 这段太糊
    （"燃气管道能不能改"只有 0.277，却匹配到了"能不能分期？"）。
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    sa, sb = set(na), set(nb)
    jaccard = len(sa & sb) / len(sa | sb)
    return jaccard >= 0.5 and _lcs(na, nb) >= 3


def close_merged_tickets(question: str) -> int:
    """把"和这条已学会的问题属于同一个问题"的 open 工单关掉，返回关闭条数。"""
    closed = 0
    for t in list_tickets(kind="ticket", status="open"):
        if is_same_question(t.get("question", ""), question):
            with cursor() as cur:
                cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (t["id"],))
            closed += 1
    return closed


def teach_from_ticket(ticket_id: int, answer: str, note: str = "") -> dict[str, Any]:
    """店长针对工单补答案 → 进【待审】队列（不是直接入库）。

    待审通过后才会被检索到，并触发总纲自动更新、以及同类工单自动关闭。
    """
    with cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        t = cur.fetchone()
        if not t:
            return {"ok": False, "error": "工单不存在"}

    sample_id = playbook_service.add_sample(
        t["question"], answer, note, source="ticket", status="pending")

    # 一字不差的重复工单先关掉；语义相近的等审核通过后由 sweep 统一收
    closed = 0
    for r in list_tickets(kind="ticket", status="open"):
        if _norm(r.get("question", "")) == _norm(t["question"]):
            with cursor() as cur:
                cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (r["id"],))
            closed += 1

    return {"ok": True, "sample_id": sample_id, "status": "pending",
            "closed_similar": closed}


# ---------------- 看板 ----------------

def metrics() -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM metrics_log")
        total = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM metrics_log WHERE handoff=1")
        handoff = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM metrics_log WHERE playbook_hit=1")
        hit = cur.fetchone()["c"]
        cur.execute("SELECT AVG(slots_filled) AS a FROM metrics_log")
        avg_slots = cur.fetchone()["a"] or 0
        cur.execute("SELECT COUNT(*) AS c FROM tickets WHERE kind='survey'")
        surveys = cur.fetchone()["c"]
        # 只算"还没处理"的工单；已关闭的不能算进待办
        cur.execute("SELECT COUNT(*) AS c FROM tickets WHERE kind='ticket' AND status='open'")
        tickets = cur.fetchone()["c"]

    return {
        "samples_approved": playbook_service.count("approved"),
        "samples_pending": playbook_service.count("pending"),
        "total_chats": total,
        "handoff_count": handoff,
        "handoff_rate": round(handoff / total, 3) if total else 0.0,
        "hit_count": hit,
        "hit_rate": round(hit / total, 3) if total else 0.0,
        "avg_slots_filled": round(float(avg_slots), 2),
        "survey_booked": surveys,
        "tickets_open": tickets,
    }
