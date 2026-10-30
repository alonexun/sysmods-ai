# -*- coding: utf-8 -*-
"""SQLite 持久层：账号（含会话 token）/ 会话 checkpoint / 积分台账。"""
import json
import os
import sqlite3
import time
import uuid
from typing import Optional

DB_PATH = os.environ.get("SYSMODS_DB",
                         os.path.join(os.path.dirname(__file__), "sysmods_ai.db"))

# 测试态验证码固定（生产态接阿里云短信——V1.2 §2.1，此处可注入）
TEST_VERIFY_CODE = "000000"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        phone TEXT PRIMARY KEY,
        credits INTEGER NOT NULL DEFAULT 100,
        free_monthly INTEGER NOT NULL DEFAULT 50,
        free_month TEXT,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS sessions(
        sid TEXT PRIMARY KEY,
        phone TEXT NOT NULL,
        checkpoint TEXT NOT NULL,
        updated_at REAL
    );
    CREATE TABLE IF NOT EXISTS ledger(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        delta INTEGER NOT NULL,
        balance INTEGER NOT NULL,
        reason TEXT,
        ref TEXT,
        ts REAL
    );
    """)
    # 兼容升级：users 增加 token 列（会话鉴权）
    try:
        con.execute("ALTER TABLE users ADD COLUMN token TEXT")
        con.commit()
    except sqlite3.OperationalError:
        pass   # 已存在
    con.commit()
    con.close()


def issue_token(phone: str) -> str:
    """注册/登录后签发会话 token（uuid），存库。"""
    token = uuid.uuid4().hex
    con = connect()
    try:
        con.execute("UPDATE users SET token=? WHERE phone=?", (token, phone))
        con.commit()
        return token
    finally:
        con.close()


def verify_token(phone: str, token: Optional[str]) -> bool:
    """校验 token 与手机号归属（无 token 一律拒绝）。"""
    if not token:
        return False
    con = connect()
    try:
        row = con.execute("SELECT token FROM users WHERE phone=?", (phone,)).fetchone()
        return bool(row and row["token"] and row["token"] == token)
    finally:
        con.close()


class LedgerError(ValueError):
    pass


class Ledger:
    """积分台账：每笔变动可对账（合同号/操作明细），失败自动返还（V1.2 §9.2）。"""

    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def _balance(self, phone: str) -> int:
        row = self.con.execute("SELECT credits FROM users WHERE phone=?", (phone,)).fetchone()
        if row is None:
            raise LedgerError("用户不存在")
        return int(row["credits"])

    def balance(self, phone: str) -> int:
        return self._balance(phone)

    def charge(self, phone: str, amount: int, reason: str, ref: str = "") -> int:
        if amount < 0:
            raise LedgerError("扣减不能为负")
        b = self._balance(phone)
        # 优先扣月度免费额度
        free_used = 0
        row = self.con.execute("SELECT free_monthly, free_month FROM users WHERE phone=?", (phone,)).fetchone()
        month = time.strftime("%Y-%m")
        if row["free_month"] != month:
            self.con.execute("UPDATE users SET free_monthly=50, free_month=? WHERE phone=?", (month, phone))
            free = 50
        else:
            free = int(row["free_monthly"])
        if amount > 0:
            take_free = min(free, amount)
            self.con.execute("UPDATE users SET free_monthly=? WHERE phone=?", (free - take_free, phone))
            free_used = take_free
        pay = amount - free_used
        if pay > b:
            self.con.execute("UPDATE users SET free_monthly=? WHERE phone=?", (free, phone))
            raise LedgerError(f"积分不足：余额 {b}（本次需 {amount}，免费额度 {free_used}）")
        new_b = b - pay
        self.con.execute("UPDATE users SET credits=? WHERE phone=?", (new_b, phone))
        self.con.execute(
            "INSERT INTO ledger(phone, delta, balance, reason, ref, ts) VALUES(?,?,?,?,?,?)",
            (phone, -pay, new_b, reason, ref, time.time()))
        self.con.commit()
        return new_b

    def grant(self, phone: str, amount: int, reason: str, ref: str = "") -> int:
        """返还/充值（线下打款后客服/财务确认发放——V1.2 §9.1）。"""
        b = self._balance(phone)
        new_b = b + amount
        self.con.execute("UPDATE users SET credits=? WHERE phone=?", (new_b, phone))
        self.con.execute(
            "INSERT INTO ledger(phone, delta, balance, reason, ref, ts) VALUES(?,?,?,?,?,?)",
            (phone, amount, new_b, reason, ref, time.time()))
        self.con.commit()
        return new_b

    def statement(self, phone: str):
        rows = self.con.execute(
            "SELECT * FROM ledger WHERE phone=? ORDER BY id DESC LIMIT 100", (phone,)).fetchall()
        return [dict(r) for r in rows]


def register_user(phone: str, code: str) -> bool:
    """手机号+验证码注册（网安法基线实名；测试态验证码固定）。"""
    if code != TEST_VERIFY_CODE:
        return False
    con = connect()
    try:
        con.execute("INSERT OR IGNORE INTO users(phone, created_at) VALUES(?,?)", (phone, time.time()))
        con.commit()
        return True
    finally:
        con.close()


def save_checkpoint(sid: str, phone: str, checkpoint: dict) -> None:
    con = connect()
    try:
        con.execute(
            "INSERT INTO sessions(sid, phone, checkpoint, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(sid) DO UPDATE SET checkpoint=excluded.checkpoint, updated_at=excluded.updated_at",
            (sid, phone, json.dumps(checkpoint, ensure_ascii=False), time.time()))
        con.commit()
    finally:
        con.close()


def load_checkpoint(sid: str) -> Optional[dict]:
    con = connect()
    try:
        row = con.execute("SELECT checkpoint FROM sessions WHERE sid=?", (sid,)).fetchone()
        return json.loads(row["checkpoint"]) if row else None
    finally:
        con.close()
