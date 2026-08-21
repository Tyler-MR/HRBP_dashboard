# -*- coding: utf-8 -*-
"""
钉钉日志 → SQLite 同步 + 评分入库。

从 .env 读取凭证，拉取钉钉日志（topapi/report/list），
清洗控制字符 → 规则评分（log_eval）→ 按 report_id 幂等 upsert，
单事务原子提交（失败自动回滚，不产生半截数据）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime

import requests
import urllib3

from database import SessionLocal
from log_eval import evaluate_log
from models import DailyLog

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("dingtalk_logs_sync")

TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
REPORT_LIST_URL = "https://oapi.dingtalk.com/topapi/report/list"
ENV_PATH = __import__("pathlib").Path(__file__).parent / ".env"

_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

MAX_DAYS = 180  # 接口单次时间范围上限


def _require_env(name: str) -> str:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip("\"'")
    raise ValueError(f"缺少凭证: {name}")


def _get_token() -> str:
    r = requests.post(
        TOKEN_URL,
        json={"appKey": _require_env("DINGTALK_APP_KEY"),
              "appSecret": _require_env("DINGTALK_APP_SECRET")},
        timeout=20, verify=False,
    )
    data = r.json()
    if "accessToken" not in data:
        raise RuntimeError(f"获取access_token失败: {data}")
    return data["accessToken"]


def _clean(s) -> str:
    return _ILLEGAL_RE.sub("", s or "")


def fetch_logs(days: int = MAX_DAYS, template: str | None = None) -> list[dict]:
    """分页拉取日志（含重试），返回原始 dict 列表。"""
    token = _get_token()
    now_ms = int(time.time() * 1000)
    start = now_ms - days * 86400 * 1000
    out, cursor = [], 0
    while True:
        body = {"start_time": start, "end_time": now_ms, "cursor": cursor, "size": 20}
        if template:
            body["template_name"] = template
        for attempt in range(3):
            try:
                r = requests.post(f"{REPORT_LIST_URL}?access_token={token}",
                                  json=body, timeout=30, verify=False)
                d = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                logger.warning("拉取日志请求异常(%d/3): %s", attempt + 1, e)
                time.sleep(2)
        if d.get("errcode") != 0:
            raise RuntimeError(f"拉取日志失败: {d.get('errcode')} {d.get('errmsg')}")
        res = d.get("result") or {}
        out.extend(res.get("data_list") or [])
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor", cursor)
        time.sleep(0.15)
    return out


def _row_to_log(x: dict) -> dict:
    """原始钉钉日志 → 入库字典（清洗+评分）。

    「数据支撑度」按岗位族口径评分：先查 17 人名单岗位（TITLE_MAP），
    名单外查花名册 Employee.position，查不到用通用词表。
    """
    contents = x.get("contents") or []
    name = _clean(x.get("creator_name", ""))
    score = evaluate_log(x.get("template_name", ""), contents, _title_for(name))
    return {
        "report_id": str(x.get("report_id", "")),
        "template_name": _clean(x.get("template_name", "")),
        "creator_name": name,
        "creator_id": _clean(x.get("creator_id", "")),
        "dept_name": _clean(x.get("dept_name", "")),
        "create_time": datetime.fromtimestamp((x.get("create_time") or 0) / 1000),
        "contents": json.dumps(contents, ensure_ascii=False),
        **score,
    }


_TITLE_CACHE: dict = {}


def _title_for(name: str) -> str:
    """查询日志创建人岗位（17 人名单 → 花名册 → 空）。"""
    if name in _TITLE_CACHE:
        return _TITLE_CACHE[name]
    title = ""
    try:
        from manager_list import TITLE_MAP
        title = TITLE_MAP.get(name, "")
        if not title:
            from database import SessionLocal
            from models import Employee
            db = SessionLocal()
            try:
                emp = db.query(Employee).filter(Employee.name == name).first()
                title = (emp.position or "") if emp else ""
            finally:
                db.close()
    except Exception:  # noqa: BLE001 — 岗位查询失败不阻断入库，用通用词表
        title = ""
    _TITLE_CACHE[name] = title
    return title


def sync_logs(days: int = MAX_DAYS) -> dict:
    """拉取→评分→入库（单事务原子提交）。返回统计。"""
    raw = fetch_logs(days)
    logger.info("拉取到 %d 条日志", len(raw))
    rows = [_row_to_log(x) for x in raw]

    db = SessionLocal()
    inserted = updated = 0
    try:
        for row in rows:
            if not row["report_id"]:
                continue
            existing = db.query(DailyLog).filter(DailyLog.report_id == row["report_id"]).first()
            if existing:
                for k, v in row.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(DailyLog(**row))
                inserted += 1
        db.commit()
        logger.info("✅ 日志入库完成: 新增 %d, 更新 %d", inserted, updated)
    except Exception:
        db.rollback()
        logger.exception("❌ 日志入库失败，已回滚")
        raise
    finally:
        db.close()
    return {"total": len(rows), "inserted": inserted, "updated": updated}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    days = MAX_DAYS
    print(sync_logs(days))
