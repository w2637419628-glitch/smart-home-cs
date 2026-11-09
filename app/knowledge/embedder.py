"""文本向量化与相似度。

两种后端，契约统一（都返回 list[float] 稠密向量）：
- ark：火山引擎豆包 multimodal embedding（真实语义向量，需要 Key）
- local：零依赖的本地特征哈希（离线可用）

设计原则：ark 调用失败（欠费/断网）自动降级到 local，绝不因向量化失败中断对话；
换后端时靠 signature() 判断，库里的旧向量会自动重算。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request

from .. import config

_LOCAL_DIM = 1024
_LOCAL_SIG = "local:hash-v1"

_ASCII_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """中文按字符二元组 + 英文/数字整词。"""
    text = (text or "").lower().strip()
    toks = _ASCII_RE.findall(text)
    cjk = "".join(_CJK_RE.findall(text))
    if len(cjk) == 1:
        toks.append(cjk)
    else:
        toks.extend(cjk[i:i + 2] for i in range(len(cjk) - 1))
    return toks


# 对外暴露，供 IDF 词法检索使用
tokens = _tokens


def _local_embed(text: str) -> list[float]:
    vec = [0.0] * _LOCAL_DIM
    for tok in _tokens(text):
        # 用稳定哈希，保证跨进程重启可复现（内置 hash 每次启动都变）
        idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % _LOCAL_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def _ark_embed(text: str) -> list[float]:
    url = config.ARK_BASE_URL.rstrip("/") + "/embeddings/multimodal"
    payload = json.dumps({
        "model": config.ARK_EMBED_MODEL,
        "input": [{"type": "text", "text": text or ""}],
        "encoding_format": "float",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.ARK_API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    data = body.get("data")
    if isinstance(data, list):
        data = data[0] if data else {}
    emb = (data or {}).get("embedding")
    if not emb:
        raise ValueError("embedding 响应缺少向量")
    return [float(x) for x in emb]


def _use_ark() -> bool:
    return bool(config.ARK_API_KEY)


def signature() -> str:
    return f"ark:{config.ARK_EMBED_MODEL}" if _use_ark() else _LOCAL_SIG


def embed(text: str) -> tuple[list[float], str]:
    """返回 (向量, 后端签名)。ark 失败自动降级 local。"""
    if _use_ark():
        try:
            return _ark_embed(text), f"ark:{config.ARK_EMBED_MODEL}"
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError):
            return _local_embed(text), _LOCAL_SIG
    return _local_embed(text), _LOCAL_SIG


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)
