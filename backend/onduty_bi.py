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
- 分析建议 = 规则引擎（无 LLM）：部门偏离全员 ±30 分钟 / 下班 ≥19:30 / 上班 ≥09:15
  个人偏离部门人均 ±60 分钟；运营投放类部门（拼多多/千川/1688/天猫/电商）晚下班
  按电商行业常态说明，不做负向定性
- 每日同步 + 手动强制同步；成功数据使用 24h 进程内缓存，普通查询不重复打钉钉；
  拉取失败 → source_error 空数据，不造假
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
CACHE_TTL = 24 * 60 * 60
ERROR_COOLDOWN = 5 * 60

_cache: Dict[str, Any] = {"ts": {}, "records": {}, "errors": {}}
_cache_lock = threading.Lock()
_fetch_lock = threading.Lock()

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

# 用户确认的标准班次：用于解释“人均在岗时长”相对理论班次的偏离，
# 不覆盖钉钉实际统计值，也不把午休、外勤等直接认定为有效工时。
STANDARD_START_MINUTES = 9 * 60 + 15
STANDARD_END_MINUTES = 18 * 60 + 30
STANDARD_ONDUTY_MINUTES = STANDARD_END_MINUTES - STANDARD_START_MINUTES

# 在岗时长只作为管理信号，最终判断要回到各业务链路的交付结果。
_DEPT_ANALYSIS_PROFILES = {
    "拼多多组": {"label": "平台运营与投放", "focus": "GMV、ROI、转化、订单履约、客服响应", "action": "按活动/爆品节奏复核人力，安排轮休并核对投产结果。"},
    "千川部": {"label": "平台运营与投放", "focus": "消耗、ROI、素材产出、转化和投放计划", "action": "将晚下班与投放爬坡、素材交付和 ROI 变化联动复盘。"},
    "1688组": {"label": "平台运营与投放", "focus": "客户开发、订单交付、询盘转化和毛利", "action": "重点核查询盘响应、订单交付与客户开发产出是否匹配。"},
    "天猫组": {"label": "平台运营与投放", "focus": "店铺经营、活动转化、毛利和售后体验", "action": "按活动节点安排峰值班次，结合转化、毛利和售后复盘。"},
    "产品部": {"label": "产品与 OEM 协同", "focus": "打样周期、新品上市、质量异常和需求闭环", "action": "排查需求评审、打样、测试和供应链等待造成的协同耗时。"},
    "采购部": {"label": "采购与 OEM 交付", "focus": "原料/包材到货、成本、交期和供应商异常", "action": "将时长偏高与采购周期、缺料、供应商交期和成本改善一起核查。"},
    "发货组": {"label": "订单履约与仓配", "focus": "发货及时率、爆单处理、错漏发和异常关闭", "action": "结合订单峰值配置弹性排班，关注履约及时率与异常关闭。"},
    "设计部": {"label": "内容与设计交付", "focus": "素材交付及时率、一次通过率和活动支持", "action": "把在岗时长与素材排期、返工次数和活动交付节点对照。"},
    "商务": {"label": "渠道与商务协同", "focus": "渠道拓展、合作转化、坑产和利润", "action": "关注商务沟通投入是否形成有效合作、订单和利润贡献。"},
    "人力行政部": {"label": "管理支持职能", "focus": "招聘交付、组织响应、培训和行政服务 SLA", "action": "用招聘周期、需求关闭率和服务 SLA 校验时长，不与运营岗直接横比。"},
    "财务部": {"label": "经营支持职能", "focus": "结算准确率、报表及时率、预算和利润分析", "action": "重点看平台账单核对、结算、报表和经营分析是否按时闭环。"},
    "技术部": {"label": "数据与系统支持", "focus": "数据准确性、报表及时率、系统稳定和需求 SLA", "action": "将时长与数据交付、系统故障、需求关闭和自动化成果联动。"},
}
_DEFAULT_ANALYSIS_PROFILE = {"label": "综合协同职能", "focus": "任务交付、协同响应、质量和问题闭环", "action": "先核对岗位任务量、交付质量与协同等待，再判断是否需要调配或补员。"}

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


def _fetch_records(force: bool = False) -> List[dict]:
    """拉取「各部门平均在岗时长」全量记录；普通查询使用24h缓存。"""
    with _fetch_lock:
        # 在网络拉取前后都串行化检查，避免缓存失效时多个请求同时打钉钉。
        with _cache_lock:
            cached = _cache["records"].get(ONDUTY_SHEET)
            if (not force and cached is not None
                    and time.time() - _cache["ts"].get(ONDUTY_SHEET, 0) < CACHE_TTL):
                return cached
            last_error = _cache["errors"].get(ONDUTY_SHEET)
            if (not force and last_error
                    and time.time() - last_error["ts"] < ERROR_COOLDOWN):
                raise RuntimeError(last_error["message"])
        try:
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
        except Exception as exc:
            with _cache_lock:
                _cache["errors"][ONDUTY_SHEET] = {"ts": time.time(), "message": str(exc)}
            raise
        with _cache_lock:
            _cache["records"][ONDUTY_SHEET] = records
            _cache["ts"][ONDUTY_SHEET] = time.time()
            _cache["errors"].pop(ONDUTY_SHEET, None)
        return records


def refresh_onduty_cache() -> Dict[str, Any]:
    """强制从钉钉刷新在岗数据，供凌晨任务和手动同步按钮使用。"""
    records = _fetch_records(force=True)
    months = sorted({_month_str((r.get("fields") or r).get("工作月份")) for r in records} - {""})
    return {"record_count": len(records), "months": months, "refreshed_at": datetime.now().isoformat(timespec="seconds")}


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
        # 3. 部门人均上班达到标准班次起点 09:15
        on = d["avg_on"]["minutes"]
        if on is not None and on >= STANDARD_START_MINUTES:
            sug.append({
                "level": "dept", "dept": dept, "name": "", "type": "late_on",
                "text": f"{dept}人均上班打卡 {_fmt_minutes(on)}，达到或晚于标准班次 09时15分，建议核实到岗时间口径与排班执行",
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


def _business_analysis_views() -> List[dict]:
    """固定业务链路解读框架，不随某个月的排名变化。"""
    return [
        {"title": "平台运营与投放", "scope": "拼多多主阵地｜天猫/淘宝、千川辅助",
         "focus": "GMV、ROI、转化、订单履约、客服响应",
         "guidance": "晚下班可由大促、爆品或投放波峰解释，必须用平台经营结果和轮休安排验证。"},
        {"title": "产品与 OEM 协同", "scope": "产品、配方、采购、生产支持",
         "focus": "打样周期、新品上市、原料包材、准时交付、质量异常",
         "guidance": "时长偏高优先排查跨部门等待、缺料、交期和质量返工，不只归因个人效率。"},
        {"title": "订单履约与客户体验", "scope": "发货、客服、售后",
         "focus": "发货及时率、错漏发、响应 SLA、售后关闭率",
         "guidance": "爆单期可以弹性排班，但应同时看履约及时率、异常关闭和客户体验。"},
        {"title": "内容与管理支持", "scope": "设计、商务、人事、财务、技术",
         "focus": "素材交付、渠道转化、招聘交付、结算报表、数据需求 SLA",
         "guidance": "不与运营岗位直接横向比较，使用岗位交付、质量和服务 SLA 校验在岗时长。"},
    ]


def _signed_minutes(minutes: Optional[int]) -> str:
    """分钟差值 → 带方向的中文时长。"""
    if minutes is None:
        return "—"
    if minutes == 0:
        return "持平"
    return f"{'+' if minutes > 0 else '-'}{_fmt_minutes(abs(minutes))}"


def _build_industry_analysis_report(month: str, depts: List[dict], overview: dict,
                                    source_error: Optional[str] = None,
                                    no_data: bool = False) -> dict:
    """面向家清垂类电商管理者的短版在岗时长经营分析报告。

    只使用已清洗的在岗数据生成结论；数据源不可用时仅返回行业分析框架，
    明确提示不能据此下实时结论。
    """
    period_label = (month or "当前周期").replace("-", "年") + ("月" if month else "")
    base = {
        "title": "家清垂类电商在岗时长经营分析",
        "subtitle": "研产销一体 OEM 代工｜拼多多主阵地｜天猫淘宝、千川辅助",
        "period": period_label,
        "status": "unavailable" if source_error else "no_data" if no_data else "ready",
        "headline": "在岗时长是经营温度计，不是单一绩效结论；必须与产出、交付、质量和客户响应一起看。",
        "conclusion": "",
        "summary": [],
        "metrics": [],
        "findings": [],
        "business_views": _business_analysis_views(),
        "dept_insights": [],
        "actions": [
            {"priority": "P0", "title": "把时长与经营结果绑定",
             "text": "拼多多/千川重点看 GMV、投产比、转化、订单履约和客服响应；研发、采购、生产协同重点看新品周期、OEM 准时交付、质量异常和退货率。"},
            {"priority": "P1", "title": "按业务节奏安排峰值用工",
             "text": "大促、爆品放量、投放爬坡期间允许运营/投放岗阶段性晚走，但应配置轮休、替班和峰值复盘，避免把长期加班当成常态能力。"},
            {"priority": "P1", "title": "异常先核实，再做管理动作",
             "text": "部门偏离全员平均约 30 分钟、个人偏离本部门约 60 分钟时，先核对任务量、打卡口径与实际产出，再决定调配、培训或补员。"},
        ],
        "questions": [
            "高在岗时长是否对应活动期、爆单、投放爬坡或 OEM 交付节点？",
            "低在岗时长是否对应工作饱和度不足、打卡缺失，还是岗位本身以结果交付为主？",
            "下个周期能否补充 GMV/ROI、订单履约、新品交付、质量与客服 SLA，形成时长—产出联动？",
        ],
        "definitions": [
            "人均在岗：按当前数据源中的部门人均在岗时长统计，不等同于有效工时。",
            "标准班次：09时15分至18时30分，理论在岗基线为09时15分；实际人均在岗与该基线的差值用于核查，不替代钉钉原始统计。",
            "运营/投放岗晚下班：达到 19:30 仅作为业务节奏信号，不直接判定为低效或加班问题。",
            "异常偏离：部门相对全员约 ±30 分钟、个人相对部门约 ±60 分钟，作为核查触发器。",
        ],
        "data_note": "",
    }
    if source_error:
        base["conclusion"] = "当前无法形成基于实际在岗数据的部门结论；请先恢复钉钉数据源，再输出部门排名、异常判断和人员配置动作。"
        base["summary"] = [
            "实时在岗时长暂不可读取，当前不输出部门排名、个人异常或效率结论。",
            "报告已按家清电商的研产销、OEM 交付和多平台运营链路配置分析口径，数据恢复后自动填充。",
        ]
        base["data_note"] = f"数据状态：钉钉多维表暂不可用。{source_error}"
        return base
    if no_data:
        base["conclusion"] = f"{period_label}没有可用在岗时长记录，暂不能形成部门结论；请先确认月份、字段口径和岗位映射。"
        base["summary"] = [
            f"{period_label}暂无在岗时长记录，当前不输出部门排名、个人异常或效率结论。",
            "建议先确认数据月份、岗位映射和上下班打卡字段，再开始周期比较。",
        ]
        base["data_note"] = "数据状态：接口可访问，但当前周期没有可用记录。"
        return base

    all_avg = overview.get("all_avg_onduty") or {}
    all_off = overview.get("all_avg_off") or {}
    all_avg_minutes = all_avg.get("minutes")
    late_operator = [d for d in depts if d["dept"] in _OP_DEPTS and (d["avg_off"].get("minutes") or 0) >= 19 * 60 + 30]
    late_non_operator = [d for d in depts if d["dept"] not in _OP_DEPTS and (d["avg_off"].get("minutes") or 0) >= 19 * 60 + 30]
    late_on = [d for d in depts if (d["avg_on"].get("minutes") or 0) >= 9 * 60]
    on_values = [d["avg_on"].get("minutes") for d in depts if d["avg_on"].get("minutes") is not None]
    on_range = f"{_fmt_minutes(min(on_values))}—{_fmt_minutes(max(on_values))}" if on_values else "—"
    missing_dept_avg = [d for d in depts if d["avg_onduty"].get("minutes") is None]
    unmapped_depts = [d for d in depts if d.get("dept") == "未映射"]
    high_deviation, low_deviation, personal_outliers = [], [], []
    if all_avg_minutes is not None:
        for d in depts:
            value = d["avg_onduty"].get("minutes")
            if value is None:
                continue
            if value - all_avg_minutes >= 30:
                high_deviation.append(d)
            elif all_avg_minutes - value >= 30:
                low_deviation.append(d)
            for person in d.get("persons", []):
                person_value = person["onduty"].get("minutes")
                if person_value is not None and abs(person_value - value) >= 60:
                    personal_outliers.append((person, d))

    def names(items: list, limit: int = 3) -> str:
        return "、".join(str(item["dept"]) for item in items[:limit]) or "无"

    base["metrics"] = [
        {"label": "部门 / 人员", "value": f"{overview.get('dept_count', 0)} / {overview.get('person_count', 0)}", "note": "纳入当前周期统计"},
        {"label": "全员平均在岗", "value": all_avg.get("display") or "—", "note": "按员工个人平均值计算"},
        {"label": "标准班次在岗", "value": _fmt_minutes(STANDARD_ONDUTY_MINUTES), "note": "09:15—18:30 理论基线"},
        {"label": "平均下班打卡", "value": all_off.get("display") or "—", "note": "用于识别峰值与疲劳风险"},
        {"label": "需核查偏离", "value": f"{len(high_deviation) + len(low_deviation)} 部门 / {len(personal_outliers)} 人", "note": "按约 30 / 60 分钟触发"},
    ]
    base["summary"] = [
        f"本周期纳入 {overview.get('dept_count', 0)} 个部门、{overview.get('person_count', 0)} 人，全员平均在岗 {all_avg.get('display') or '—'}。",
        f"标准班次为 09时15分—18时30分，理论在岗基线 {_fmt_minutes(STANDARD_ONDUTY_MINUTES)}；全员实际人均较基线 {_signed_minutes((all_avg_minutes - STANDARD_ONDUTY_MINUTES) if all_avg_minutes is not None else None)}。",
        f"需要管理核查的偏离为 {len(high_deviation) + len(low_deviation)} 个部门、{len(personal_outliers)} 名员工；偏离本身不是绩效结论。",
    ]
    if late_operator:
        base["summary"].append(f"{names(late_operator)}出现 19:30 后平均下班，优先按大促、爆单、投放节奏和轮休安排解释，不直接负向评价。")
    if late_non_operator:
        base["summary"].append(f"{names(late_non_operator)}也出现 19:30 后平均下班，建议优先检查交付节点、经营支持任务或人员配置。")
    if not late_operator and not late_non_operator:
        base["summary"].append("当前未触发 19:30 后平均下班部门提示，但仍应结合业务峰值和产出复核。")

    # 单独给出一段可直接用于管理决策的最终判断，避免用户需要自行拼接摘要、排行和建议。
    conclusion = (
        f"{period_label}综合结论：本周期纳入 {overview.get('dept_count', 0)} 个部门、{overview.get('person_count', 0)} 人，"
        f"全员平均在岗 {all_avg.get('display') or '—'}、平均下班打卡 {all_off.get('display') or '—'}，"
        f"相对09时15分—18时30分的理论在岗基线（{_fmt_minutes(STANDARD_ONDUTY_MINUTES)}）为{_signed_minutes((all_avg_minutes - STANDARD_ONDUTY_MINUTES) if all_avg_minutes is not None else None)}；"
        "这反映的是投入和排班信号，不等同于有效工时，更不能单独作为绩效或加班结论。"
    )
    conclusion += (
        f"各部门平均上班打卡集中在 {on_range}，相关规则只作为班次、外勤、补卡和采集口径的核查触发器，"
        f"当前个人偏离本部门1小时以上的异常为 {len(personal_outliers)} 人。"
    )
    if high_deviation or low_deviation:
        if high_deviation:
            high_text = "、".join(d["dept"] for d in high_deviation[:3])
            conclusion += f"当前差异主要集中在{high_text}：其人均在岗高于全员平均约30分钟以上"
            if high_deviation[0]["avg_off"].get("display"):
                conclusion += f"，其中{high_deviation[0]['dept']}平均下班为{high_deviation[0]['avg_off']['display']}"
            conclusion += "，优先核查任务堆积、系统/数据需求、跨部门等待和人员配置，不能直接归因于个人效率。"
        if low_deviation:
            low_text = "、".join(d["dept"] for d in low_deviation[:3])
            conclusion += f"{low_text}低于全员平均约30分钟以上，但不代表效率更高，应结合工作量、交付质量和打卡完整性确认。"
    else:
        conclusion += "当前没有触发部门级时长偏离，暂不支持全员性加班或人员不足的判断。"
    if missing_dept_avg:
        missing_text = "、".join(d["dept"] for d in missing_dept_avg[:3])
        conclusion += f"数据边界：{missing_text}的部门人均在岗暂无法形成可比值，不能据此判断其排名。"
    if unmapped_depts:
        conclusion += f"另有{sum(d.get('count', 0) for d in unmapped_depts)}人岗位尚未完成部门映射，后续应先补齐组织归属。"
    conclusion += "当前仅有本周期截面数据，尚无同比或环比基线，不能据此判断趋势变化；管理优先级应为：先补齐数据口径，再将时长与GMV/ROI、订单履约、新品/OEM交付、质量和服务SLA联动复盘，最后决定排班、流程优化或补员。"
    base["conclusion"] = conclusion

    base["findings"] = [
        {"title": "前台经营：时间要和平台结果一起看",
         "text": "拼多多是主阵地，天猫/淘宝与千川是辅助渠道。运营、投放、内容岗位的晚下班可能来自活动、爆品或投放波峰，判断重点应转向 GMV、ROI、转化、订单履约和响应 SLA。",
         "evidence": f"运营/投放类晚下班部门：{names(late_operator)}"},
        {"title": "部门偏离：时间偏高要看交付瓶颈",
         "text": "家清 OEM 业务中，研产供、履约和经营支持岗位的在岗偏高，可能反映打样、排产、原料/包材、交期、结算或数据支持的跨部门等待，不宜只归因于个人效率。",
         "evidence": f"高于全员约 30 分钟部门：{names(high_deviation)}"},
        {"title": "岗位交付：用 SLA 和闭环率校验时长",
         "text": "发货、设计、商务、人事、财务、技术和客服等岗位不宜只按时长横向比较，应结合履约及时率、素材交付、渠道转化、招聘交付、结算报表、数据需求和问题关闭率判断。",
         "evidence": f"低于全员约 30 分钟部门：{names(low_deviation)}；个人偏离部门约 60 分钟：{len(personal_outliers)} 人"},
    ]
    if late_on:
        base["findings"].append({
            "title": "出勤口径：上班打卡偏晚需要先核实",
            "text": "平均上班打卡达到或晚于标准班次 09:15 的部门，先核对弹性班次、外勤、补卡和数据采集口径，再决定是否需要调整排班或出勤管理。",
            "evidence": f"触发部门：{names(late_on)}",
        })

    # 部门级诊断：每个部门都输出同一结构，便于 HRD 做横向核查和后续跟进。
    for d in depts:
        dept = d["dept"]
        profile = _DEPT_ANALYSIS_PROFILES.get(dept, _DEFAULT_ANALYSIS_PROFILE)
        avg = d["avg_onduty"].get("minutes")
        off = d["avg_off"].get("minutes")
        on = d["avg_on"].get("minutes")
        delta = avg - all_avg_minutes if avg is not None and all_avg_minutes is not None else None
        personal_count = 0
        if avg is not None:
            personal_count = sum(1 for p in d.get("persons", [])
                                 if p["onduty"].get("minutes") is not None
                                 and abs(p["onduty"]["minutes"] - avg) >= 60)

        if dept in _OP_DEPTS and off is not None and off >= 19 * 60 + 30:
            status = "业务峰值关注"
            analysis = "运营/投放岗平均下班偏晚，先按活动、爆品、投放爬坡和轮休情况解释，再看投入是否带来经营结果。"
            action = profile["action"]
        elif delta is not None and delta >= 30:
            status = "负荷与流程核查"
            analysis = f"人均在岗高于全员 {_fmt_minutes(abs(delta))}，可能包含业务峰值，也可能反映流程等待、任务堆积或配置不足。"
            action = profile["action"]
        elif delta is not None and delta <= -30:
            status = "饱和度核查"
            analysis = f"人均在岗低于全员 {_fmt_minutes(abs(delta))}，不直接判定效率高，需结合工作量、岗位交付和打卡完整性确认。"
            action = profile["action"]
        elif on is not None and on >= STANDARD_START_MINUTES:
            status = "出勤口径核查"
            analysis = "平均上班打卡达到或晚于标准班次 09:15，先确认弹性班次、外勤、补卡和采集口径，再判断排班或出勤问题。"
            action = profile["action"]
        else:
            status = "正常观察"
            analysis = "当前未触发明显时长偏离，继续观察业务峰值、交付质量和员工状态是否同步变化。"
            action = profile["action"]

        base["dept_insights"].append({
            "dept": dept, "l1": d.get("l1", ""), "count": d.get("count", 0),
            "profile": profile["label"], "focus": profile["focus"],
            "avg_onduty": d["avg_onduty"].get("display") or "—",
            "baseline_delta": _signed_minutes(
                avg - STANDARD_ONDUTY_MINUTES if avg is not None else None
            ),
            "avg_on": d["avg_on"].get("display") or "—",
            "avg_off": d["avg_off"].get("display") or "—",
            "delta": _signed_minutes(delta), "personal_outliers": personal_count,
            "status": status, "analysis": analysis, "action": action,
        })
    base["data_note"] = "数据状态：已读取钉钉在岗时长数据；以上结论基于人均时长与打卡时间，需结合经营结果复核。"
    return base


def get_onduty_stats(month: Optional[str] = None) -> Dict[str, Any]:
    """各部门在岗时长统计 + 分析建议。month: 'YYYY-MM'，空=最新有数据的月份。"""
    try:
        all_rows = _build_records(month or "")
    except Exception as e:  # noqa: BLE001 — 接口异常降级
        logger.error("在岗时长数据源不可用: %s", e)
        return {"source_error": f"钉钉多维表拉取失败：{e}", "month": month or "",
                "months": [], "overview": {}, "depts": [], "suggestions": [],
                "analysis_report": _build_industry_analysis_report(month or "", [], {}, source_error=str(e))}

    months = sorted({_month_str((r.get("fields") or r).get("工作月份")) for r in _fetch_records()} - {""})
    if not month:
        month = months[-1] if months else ""
        all_rows = [r for r in all_rows if r["month"] == month]
    if not all_rows:
        return {"source_error": None, "month": month, "months": months,
                "overview": {"dept_count": 0, "person_count": 0}, "depts": [], "suggestions": [],
                "note": f"{month} 无在岗时长数据",
                "analysis_report": _build_industry_analysis_report(month, [], {"dept_count": 0, "person_count": 0}, no_data=True)}

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
            "baseline_delta": {"display": _signed_minutes(
                avg_onduty - STANDARD_ONDUTY_MINUTES if avg_onduty is not None else None
            ), "minutes": avg_onduty - STANDARD_ONDUTY_MINUTES
                       if avg_onduty is not None else None},
            "avg_off": {"display": _fmt_minutes(avg_off), "minutes": avg_off},
            "avg_on": {"display": _fmt_minutes(avg_on), "minutes": avg_on},
            "persons": persons,
        })

    depts.sort(key=lambda d: -(d["avg_onduty"]["minutes"] or 0))
    # 公司总平均按员工个人均值计算，避免不同规模部门被等权平均。
    all_avg = _avg_minutes([p["onduty"]["minutes"] for d in depts for p in d.get("persons", [])
                            if p["onduty"]["minutes"] is not None])
    all_off = _avg_minutes([p["off_time"]["minutes"] for d in depts for p in d.get("persons", [])
                            if p["off_time"]["minutes"] is not None])
    max_d = depts[0] if depts else None
    min_d = depts[-1] if depts else None

    suggestions = _build_suggestions(depts, all_avg)

    overview = {
        "dept_count": len(depts),
        "person_count": sum(d["count"] for d in depts),
        "all_avg_onduty": {"display": _fmt_minutes(all_avg), "minutes": all_avg},
        "standard_schedule": {
            "start": _fmt_minutes(STANDARD_START_MINUTES),
            "end": _fmt_minutes(STANDARD_END_MINUTES),
            "onduty": _fmt_minutes(STANDARD_ONDUTY_MINUTES),
            "onduty_minutes": STANDARD_ONDUTY_MINUTES,
        },
        "all_avg_onduty_delta": _signed_minutes(
            all_avg - STANDARD_ONDUTY_MINUTES if all_avg is not None else None
        ),
        "all_avg_off": {"display": _fmt_minutes(all_off), "minutes": all_off},
        "max_dept": {"name": max_d["dept"], "display": max_d["avg_onduty"]["display"]} if max_d else None,
        "min_dept": {"name": min_d["dept"], "display": min_d["avg_onduty"]["display"]} if min_d else None,
    }

    return {
        "source_error": None,
        "month": month, "months": months,
        "overview": overview,
        "depts": depts,
        "suggestions": suggestions,
        "analysis_report": _build_industry_analysis_report(month, depts, overview),
    }


def sync_onduty_stats(month: Optional[str] = None) -> Dict[str, Any]:
    """强制刷新在岗数据后返回指定月份统计，供手动同步接口使用。"""
    try:
        sync_meta = refresh_onduty_cache()
    except Exception as e:  # noqa: BLE001 — 同步接口返回可读错误，不重复发起查询
        logger.error("在岗时长手动同步失败: %s", e)
        error_text = f"钉钉多维表同步失败：{e}"
        return {
            "source_error": error_text, "month": month or "", "months": [],
            "overview": {}, "depts": [], "suggestions": [],
            "sync": {"ok": False, "record_count": 0, "message": error_text},
            "analysis_report": _build_industry_analysis_report(month or "", [], {}, source_error=error_text),
        }
    data = get_onduty_stats(month)
    data["sync"] = {
        "ok": not bool(data.get("source_error")),
        "record_count": sync_meta["record_count"],
        "months": sync_meta["months"],
        "refreshed_at": sync_meta["refreshed_at"],
    }
    return data
