"""SQLite 建表与轻量读写封装。

7 张表：
  playbook       套路样本库（含 status 待审/通过）
  settings       键值配置（业务铁律 / 套路总纲 / 上一版总纲）
  leads          客户档案（6 个需求槽位 + 阶段）
  tickets        工单（答不上的问题）
  packages       智能家居方案套餐（只有区间，没有精确总价）
  cases          完工案例
  metrics_log    会话埋点
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS playbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                note TEXT,
                source TEXT NOT NULL DEFAULT 'taught',      -- taught | ticket
                status TEXT NOT NULL DEFAULT 'pending',     -- pending | approved | rejected
                scene TEXT,                                 -- 价格/需求/竞品/安装/售后/通用
                vector TEXT,
                vec_model TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                community TEXT, layout TEXT, area REAL,
                scenario TEXT, budget TEXT, stage_reno TEXT,
                phone TEXT,
                stage TEXT NOT NULL DEFAULT 'inquiry',      -- inquiry | qualified | survey_booked
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                kind TEXT NOT NULL DEFAULT 'ticket',        -- ticket(答不上) | survey(上门勘测)
                question TEXT NOT NULL,
                context TEXT,
                status TEXT NOT NULL DEFAULT 'open',        -- open | closed
                dupe_count INTEGER NOT NULL DEFAULT 1,      -- 同一个问题被问了几次
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        # 兼容旧库：补 dupe_count 列
        tcols = {row["name"] for row in cur.execute("PRAGMA table_info(tickets)")}
        if "dupe_count" not in tcols:
            cur.execute("ALTER TABLE tickets ADD COLUMN dupe_count INTEGER NOT NULL DEFAULT 1")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                tier TEXT,
                scenario TEXT,
                price_min INTEGER,
                price_max INTEGER,
                area_min INTEGER,
                area_max INTEGER,
                includes TEXT,
                excludes TEXT,
                duration_days INTEGER,
                highlight TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                community TEXT, layout TEXT, area REAL,
                scenario TEXT,
                cost_min INTEGER, cost_max INTEGER,
                highlight TEXT, quote TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                question TEXT,
                playbook_hit INTEGER NOT NULL DEFAULT 0,
                handoff INTEGER NOT NULL DEFAULT 0,
                slots_filled INTEGER NOT NULL DEFAULT 0,
                tools_used TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
