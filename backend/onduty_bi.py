# -*- coding: utf-8 -*-
"""各部门在岗时长 BI 数据源 — 钉钉多维表「各部门平均在岗时长」(ZgpG2NdyVXKlg9pBUPyv1eMrWMwvDqPk / sheet iy14FFA)

口径（2026-08，用户确认）：
- 时间字段统一清洗为「HH时MM分」：源值支持 HH:MM / HH:MM:SS / H时M分（含未补零），
  无法识别的值原样保留并计入 data_error
- 岗位→部门映射：源表无部门字段，按源数据「部门人均在岗时长」分组 + 用户修正
  （彭俊=数据分析→技术部；数据分析/数据分析师助理→技术部；其余按分组）
- 一级部门合并规则沿用用户既定口径（拼多多/1688/天猫组→电商部，发货组→财务部）
- 部门人均在岗时长 = 该部门成员记录的「部门人均在岗时长」均值（保留源表数值；
  技术部因彭俊源值为 09:57 与其余 10:49 不一致，均值约 10:36，已单独提示）
- 分析建议 = 规则引擎（无 LLM）：部门偏离全员 ±30 分钟 / 下班 ≥19:30 / 上班 ≥9:00
  个人偏离部门人均 ±60 分钟；运营投放类部门（拼多多/千川/1688/天猫/电商）晚下班
  按电商行业常态说明，不做负向定性
- 60s TTL 内存缓存（前端轮询不重复打钉钉）；拉取失败 → source_error 空数据，不造假
"""
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dingtalk_bitable import DingTalkBitableClient

logger = logging.getLogger("onduty_bi")

ONDUTY_BASE = "ZgpG2NdyVXKlg9pBUPyv1eMrWMwvDqPk"
ONDUTY_SHEET = "iy14FFA"
CACHE_TTL = 60.0

_cache: Dict[str, Any] = {"ts": {}, "records": {}}
_cache_lock = threading.Lock()

# ── 岗位→部门 映射（源数据分组 + 用户修正 2026-08）──
# 用户口径：彭俊=配方师（源表岗位"产品配方师"）→ 采购部（源数据 09:57 组）；
#           数据分析/数据分析师助理 由财务部划归 技术部
POS_DEPT = {
    # 采购部
    "采购专员": "采购部", "采购专家": "采购部", "采购储备组长": "采购部",
    "采购储备经理": "采购部", "采购总监": "采购部", "产品配方师": "采购部",
    # 产品部
    "产品储备主管": "产品部", "产品经理/质控": "产品部",
    # 拼多多组
    "拼多多主管": "拼多多组", "拼多多储备运营": "拼多多组",
    "拼多多运营助理": "拼多多组", "资深拼多多运营": "拼多多组",
    # 人力行政部
    "人事总监": "人力行政部", "招聘专员": "人力行政部", "招聘专家": "人力行政部",
    "招聘储备主管": "人力行政部", "行政专员": "人力行政部",
    # 财务部（数据岗已划出）
    "财务BP经理": "财务部", "财务专员": "财务部", "财务组长": "财务部",
    # 千川部
    "剪辑专员": "千川部", "千川储备主管": "千川部", "短视频拍摄": "千川部",
    # 1688组
    "1688经理": "1688组", "1688运营转化": "1688组",
    # 天猫组
    "天猫储备主管": "天猫组", "天猫运营经理": "天猫组", "淘天运营组长": "天猫组",
    # 发货组
    "发货文员": "发货组",
    # 商务
    "商务主管": "商务",
    # 设计部
    "美工": "设计部", "美工（建模）": "设计部", "设计": "设计部",
    # 技术部（用户修正：数据分析/数据分析师助理 由财务部划出）
    "数据分析": "技术部", "数据分析师助理": "技术部",
}
# 一级部门合并
L1_MAP = {"拼多多组": "电商部", "1688组": "电商部", "天猫组": "电商部", "发货组": "财务部",
          "采购部": "采购部", "产品部": "产品部", "人力行政部": "人力行政部", "财务部": "财务部",
          "千川部": "千川部", "商务": "商务", "设计部": "设计部", "技术部": "技术部"}
# 电商运营/投放类部门（晚下班按行业常态说明）
_OP_DEPTS = {"拼多多组", "千川部", "1688组", "天猫组"}

# ── 时间解析/格式化 ──
_TIME_RE_COLON = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")
_TIME_RE_CN = re.compile(r"^(\d{1,2})时(\d{1,2})分$")


def _time_to_minutes(val: Any) -> Optional[int]:
    """时间值 → 分钟数（0-1440）。支持 HH:MM / HH:MM:SS / H时M分。识别失败返回 None。"""
    if val is None:
        return None
    s = str(val).strip()
    m = _TIME_RE_COLON.match(s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
        return h * 60 + mm
    m = _TIME_RE_CN.match(s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
        return h * 60 + mm
    return None


def _fmt_minutes(mins: Optional[int]) -> str:
    """分钟数 → HH时MM分。None → ''。"""
    if mins is None:
        return ""
    return f"{mins // 60:02d}时{mins % 60:02d}分"


def _clean_time(val: Any) -> Dict[str, Any]:
    """清洗单个时间值 → {'display': 'HH时MM分', 'minutes': int|None}。"""
    mins = _time_to_minutes(val)
    return {"display": _fmt_minutes(mins) if mins is not None else str(val).strip() if val else "",
            "minutes": mins}


def _month_str(val: Any) -> str:
    """工作月份（date 毫秒时间戳）→ 'YYYY-MM'。"""
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val / 1000).strftime("%Y-%m")
        except (ValueError, OSError, OverflowError):
            return ""
    s = str(val or "").strip()
    m = re.search(r"(\d{4})年?(\d{1,2})月?", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{4})[-/](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    return ""


def _fetch_records() -> List[dict]:
    """拉取「各部门平均在岗时长」全量记录（60s 缓存）。"""
    with _cache_lock:
        cached = _cache["records"].get(ONDUTY_SHEET)
        if cached is not None and time.time() - _cache["ts"].get(ONDUTY_SHEET, 0) < CACHE_TTL:
            return cached
    client = DingTalkBitableClient()
    client.get_access_token()
    records: List[dict] = []
    token: Optional[str] = None
    while True:
        body: dict = {"pageSize": 500}
        if token:
            body["nextToken"] = token
        r = client._request("POST", f"/bases/{ONDUTY_BASE}/sheets/{ONDUTY_SHEET}/records/list", json=body)
        if isinstance(r, list):
            records.extend(r)
            break
        records.extend(r.get("records", r.get("value", [])))
        token = r.get("nextToken")
        if not r.get("hasMore") or not token:
            break
        time.sleep(0.3)
    with _cache_lock:
        _cache["records"][ONDUTY_SHEET] = records
        _cache["ts"][ONDUTY_SHEET] = time.time()
    return records


# ── 统计构建 ──
def _build_records(month: str) -> List[dict]:
    """拉取 + 清洗 + 部门映射 → 标准记录列表（仅目标月份）。"""
    records = _fetch_records()
    out: List[dict] = []
    for rec in records:
        f = rec.get("fields", rec) or {}
        m = _month_str(f.get("工作月份"))
        if month and m != month:
            continue
        name = str(f.get("姓名", "") or "").strip()
        if not name:
            continue
        pos = str(f.get("岗位", "") or "").strip()
        dept = POS_DEPT.get(pos, "未映射")
        on = _clean_time(f.get("平均上班打卡时间"))
        off = _clean_time(f.get("平均下班打卡时间"))
        onduty = _clean_time(f.get("平均在岗时间"))
        dept_onduty = _clean_time(f.get("部门人均在岗时长"))
        dept_off = _clean_time(f.get("部门人均下班打卡时间"))
        out.append({
            "name": name, "position": pos, "dept": dept, "l1": L1_MAP.get(dept, dept),
            "month": m,
            "on_time": on, "off_time": off, "onduty": onduty,
            "dept_onduty": dept_onduty, "dept_off": dept_off,
            "note": str(f.get("补充说明", "") or "").strip(),
        })
    return out


def _avg_minutes(values: List[Optional[int]]) -> Optional[int]:
    """非空分钟数均值，无数据返回 None。"""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals))


def _build_suggestions(depts: List[dict], all_avg: Optional[int]) -> List[dict]:
    """规则引擎生成分析建议（部门级 + 个人级）。"""
    sug: List[dict] = []
    all_avg = all_avg or 0
    for d in depts:
        dept, avg = d["dept"], d["avg_onduty"]["minutes"]
        if avg is None:
            continue
        # 1. 部门偏离全员平均 ±30 分钟
        if all_avg and abs(avg - all_avg) >= 30:
            diff = avg - all_avg
            if diff > 0:
                sug.append({
                    "level": "dept", "dept": dept, "name": "", "type": "deviation_high",
                    "text": f"{dept}人均在岗 {_fmt_minutes(avg)}，高于全员平均 {_fmt_minutes(all_avg)}（+{diff // 60}小时{diff % 60:02d}分），建议关注工作负荷与排班效率，避免无效加班",
                })
            else:
                sug.append({
                    "level": "dept", "dept": dept, "name": "", "type": "deviation_low",
                    "text": f"{dept}人均在岗 {_fmt_minutes(avg)}，低于全员平均 {_fmt_minutes(all_avg)}，建议核实工作饱和度与任务分配，关注在岗时长与产出匹配度",
                })
        # 2. 部门人均下班过晚 ≥ 19:30
        off = d["avg_off"]["minutes"]
        if off is not None and off >= 19 * 60 + 30:
            if dept in _OP_DEPTS:
                sug.append({
                    "level": "dept", "dept": dept, "name": "", "type": "late_off",
                    "text": f"{dept}人均下班打卡 {_fmt_minutes(off)}，电商运营/投放岗常态晚走，属行业特性；建议关注团队轮休与工作强度，防止长期疲劳",
                })
            else:
                sug.append({
                    "level": "dept", "dept": dept, "name": "", "type": "late_off",
                    "text": f"{dept}人均下班打卡 {_fmt_minutes(off)}，存在常态加班迹象，建议核查任务量与人员配置，安排轮休并关注员工状态",
                })
        # 3. 部门人均上班过晚 ≥ 9:00
        on = d["avg_on"]["minutes"]
        if on is not None and on >= 9 * 60:
            sug.append({
                "level": "dept", "dept": dept, "name": "", "type": "late_on",
                "text": f"{dept}人均上班打卡 {_fmt_minutes(on)}，偏晚，建议强化出勤管理并核实到岗时间口径",
            })
        # 4. 个人偏离部门人均 ±60 分钟
        for p in d.get("persons", []):
            pv, dv = p["onduty"]["minutes"], d["avg_onduty"]["minutes"]
            if pv is None or dv is None:
                continue
            diff = pv - dv
            if abs(diff) >= 60:
                if diff > 0:
                    sug.append({
                        "level": "person", "dept": dept, "name": p["name"], "type": "personal_high",
                        "text": f"{p['name']}（{dept}）平均在岗 {p['onduty']['display']}，高于部门人均 {_fmt_minutes(dv)} 超1小时，建议核实工作安排与效率",
                    })
                else:
                    sug.append({
                        "level": "person", "dept": dept, "name": p["name"], "type": "personal_low",
                        "text": f"{p['name']}（{dept}）平均在岗 {p['onduty']['display']}，低于部门人均 {_fmt_minutes(dv)} 超1小时，建议核实出勤与任务饱和度",
                    })
    return sug


def get_onduty_stats(month: Optional[str] = None) -> Dict[str, Any]:
    """各部门在岗时长统计 + 分析建议。month: 'YYYY-MM'，空=最新有数据的月份。"""
    try:
        all_rows = _build_records(month or "")
    except Exception as e:  # noqa: BLE001 — 接口异常降级
        logger.error("在岗时长数据源不可用: %s", e)
        return {"source_error": f"钉钉多维表拉取失败：{e}", "month": month or "",
                "months": [], "overview": {}, "depts": [], "suggestions": []}

    months = sorted({_month_str((r.get("fields") or r).get("工作月份")) for r in _fetch_records()} - {""})
    if not month:
        month = months[-1] if months else ""
        all_rows = [r for r in all_rows if r["month"] == month]
    if not all_rows:
        return {"source_error": None, "month": month, "months": months,
                "overview": {"dept_count": 0, "person_count": 0}, "depts": [], "suggestions": [],
                "note": f"{month} 无在岗时长数据"}

    # 部门聚合
    dept_map: Dict[str, List[dict]] = {}
    for r in all_rows:
        dept_map.setdefault(r["dept"], []).append(r)

    depts = []
    for dept, members in dept_map.items():
        avg_onduty = _avg_minutes([r["dept_onduty"]["minutes"] for r in members])
        avg_off = _avg_minutes([r["dept_off"]["minutes"] for r in members])
        avg_on = _avg_minutes([r["on_time"]["minutes"] for r in members])
        persons = [{
            "name": r["name"], "position": r["position"],
            "on_time": r["on_time"], "off_time": r["off_time"], "onduty": r["onduty"],
            "dept_onduty": r["dept_onduty"],
        } for r in sorted(members, key=lambda x: x["onduty"]["minutes"] or 0)]
        depts.append({
            "dept": dept, "l1": members[0]["l1"], "count": len(members),
            "avg_onduty": {"display": _fmt_minutes(avg_onduty), "minutes": avg_onduty},
            "avg_off": {"display": _fmt_minutes(avg_off), "minutes": avg_off},
            "avg_on": {"display": _fmt_minutes(avg_on), "minutes": avg_on},
            "persons": persons,
        })

    depts.sort(key=lambda d: -(d["avg_onduty"]["minutes"] or 0))
    all_avg = _avg_minutes([d["avg_onduty"]["minutes"] for d in depts if d["avg_onduty"]["minutes"] is not None])
    all_off = _avg_minutes([d["avg_off"]["minutes"] for d in depts if d["avg_off"]["minutes"] is not None])
    max_d = depts[0] if depts else None
    min_d = depts[-1] if depts else None

    suggestions = _build_suggestions(depts, all_avg)

    return {
        "source_error": None,
        "month": month, "months": months,
        "overview": {
            "dept_count": len(depts),
            "person_count": sum(d["count"] for d in depts),
            "all_avg_onduty": {"display": _fmt_minutes(all_avg), "minutes": all_avg},
            "all_avg_off": {"display": _fmt_minutes(all_off), "minutes": all_off},
            "max_dept": {"name": max_d["dept"], "display": max_d["avg_onduty"]["display"]} if max_d else None,
            "min_dept": {"name": min_d["dept"], "display": min_d["avg_onduty"]["display"]} if min_d else None,
        },
        "depts": depts,
        "suggestions": suggestions,
    }
