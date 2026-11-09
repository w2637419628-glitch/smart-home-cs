"""套路样本库（自进化的"记忆"）。

一条样本 = 客户问题 + 标准答案 + 这么答的原因（套路）。
样本有状态：pending（待审）→ approved（可被检索）/ rejected。

服务时只召回 approved 的 top-k 条——库变大也不会撑爆上下文。
"""
from __future__ import annotations

import json
from typing import Any

from .. import config
from ..db import cursor
from ..knowledge import embedder
from ..data.seeds import seed_playbook


# ---------------- 写入 ----------------

def add_sample(question: str, answer: str, note: str = "",
               source: str = "taught", scene: str = "",
               status: str = "pending") -> int:
    vector, sig = embedder.embed(question)
    with cursor() as cur:
        cur.execute(
            "INSERT INTO playbook (question, answer, note, source, status, scene, vector, vec_model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (question, answer, note, source, status, scene,
             json.dumps(vector), sig),
        )
        return cur.lastrowid


def approve_sample(sample_id: int) -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("UPDATE playbook SET status='approved' WHERE id=?", (sample_id,))
    return {"ok": True, "id": sample_id, "status": "approved"}


def reject_sample(sample_id: int) -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("UPDATE playbook SET status='rejected' WHERE id=?", (sample_id,))
    return {"ok": True, "id": sample_id, "status": "rejected"}


def update_sample(sample_id: int, question: str, answer: str, note: str) -> dict[str, Any]:
    vector, sig = embedder.embed(question)
    with cursor() as cur:
        cur.execute(
            "UPDATE playbook SET question=?, answer=?, note=?, vector=?, vec_model=? WHERE id=?",
            (question, answer, note, json.dumps(vector), sig, sample_id),
        )
    return {"ok": True}


def delete_sample(sample_id: int) -> dict[str, Any]:
    with cursor() as cur:
        cur.execute("DELETE FROM playbook WHERE id=?", (sample_id,))
    return {"ok": True}


# ---------------- 读取 ----------------

def list_samples(status: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM playbook WHERE 1=1"
    args: list[Any] = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if source:
        sql += " AND source=?"
        args.append(source)
    sql += " ORDER BY id DESC"
    with cursor() as cur:
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def get_sample(sample_id: int) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM playbook WHERE id=?", (sample_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def count(status: str | None = None) -> int:
    with cursor() as cur:
        if status:
            cur.execute("SELECT COUNT(*) AS c FROM playbook WHERE status=?", (status,))
        else:
            cur.execute("SELECT COUNT(*) AS c FROM playbook")
        return cur.fetchone()["c"]


def recall_all_approved() -> list[dict[str, Any]]:
    """全部已通过的样本（供归纳总纲用）。"""
    with cursor() as cur:
        cur.execute("SELECT id, question, answer, note, scene FROM playbook "
                    "WHERE status='approved' ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def _sample_vector(row: dict[str, Any], sig: str) -> list[float]:
    """取样本向量；缺失或后端签名不一致（换过 embedding）则重算并回写。"""
    if row.get("vector") and row.get("vec_model") == sig:
        try:
            return json.loads(row["vector"])
        except (json.JSONDecodeError, TypeError):
            pass
    vector, new_sig = embedder.embed(row["question"])
    with cursor() as cur:
        cur.execute("UPDATE playbook SET vector=?, vec_model=? WHERE id=?",
                    (json.dumps(vector), new_sig, row["id"]))
    return vector


def recall_topk(query: str, k: int) -> list[dict[str, Any]]:
    """按客户这句话做语义检索，返回最相关的 top-k 条【已通过】样本。

    两种打分后端：
    - 配了 ARK → 真向量余弦（语义匹配，换个说法也能命中）
    - 没配   → IDF 加权词法余弦（离线可用，靠"稀有词"压制"你们/能/吗"这类噪声）
    """
    with cursor() as cur:
        cur.execute("SELECT id, question, answer, note, scene, vector, vec_model "
                    "FROM playbook WHERE status='approved' ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        return []
    if not (query or "").strip():
        return [{"id": r["id"], "question": r["question"], "answer": r["answer"],
                 "note": r["note"], "scene": r.get("scene") or ""} for r in rows[:k]]

    if embedder.signature().startswith("ark"):
        sig = embedder.signature()
        qvec, _ = embedder.embed(query)
        scores = [embedder.cosine(qvec, _sample_vector(r, sig)) for r in rows]
    else:
        scores = _idf_scores(query, [r["question"] for r in rows])

    ranked = sorted(zip(scores, rows), key=lambda x: x[0], reverse=True)
    return [{"id": r["id"], "question": r["question"], "answer": r["answer"],
             "note": r["note"], "scene": r.get("scene") or "", "score": round(s, 3)}
            for s, r in ranked[:k]]


def _idf_scores(query: str, docs: list[str]) -> list[float]:
    """IDF 加权的词法余弦：让"弧形/窗帘/保修"这类稀有词主导打分。"""
    import math
    from collections import Counter

    tokenized = [embedder.tokens(d) for d in docs]
    n = len(docs) or 1
    df: Counter[str] = Counter()
    for toks in tokenized:
        df.update(set(toks))

    def weight(t: str) -> float:
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    def vec(toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * weight(t) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    qv = vec(embedder.tokens(query))
    out: list[float] = []
    for toks in tokenized:
        dv = vec(toks)
        out.append(sum(qv[t] * dv[t] for t in (set(qv) & set(dv))))
    return out


# ---------------- 冷启动 ----------------

def seed_if_empty() -> int:
    """首次启动时灌入店长已经教过的 20 条话术（直接 approved）。"""
    if count() > 0:
        return 0
    n = 0
    for s in seed_playbook():
        add_sample(s["question"], s["answer"], s["note"],
                   source=s["source"], scene=s["scene"], status="approved")
        n += 1
    return n
