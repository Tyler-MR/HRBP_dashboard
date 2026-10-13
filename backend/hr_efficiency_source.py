"""钉钉多维表「人效数据-公司/部门」的人效数据源。

优先通过钉钉多维表 API 自动读取；API 暂时不可用时才回退到最近一次
结构化快照。源表的金额字段虽然标注为「万元」，这里保持源表原值和标签，
不做单位换算。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

from dingtalk_bitable import DingTalkBitableClient

logger = logging.getLogger("hr_efficiency_source")

SOURCE_NAME = "钉钉多维表：人效数据-公司/部门"
SOURCE_SHEETS = "公司人效月度数据；公司人效看板-部门人效数据"
SOURCE_NOTE = (
    "公司月度指标来自公司人效月度数据；年度汇总行仅用于年度摘要，"
    "不与1-12月重复相加。部门人数和营收按有效部门记录汇总，排除合计、"
    "排名说明、空值、0值和公式文本行；部门表与公司月度表覆盖范围不同，"
    "不用于回算公司指标。金额保持源表显示值。"
)

HR_EFFICIENCY_BASE_ID = "R1zknDm0WRblLYgOIzyPMLXmWBQEx5rG"
HR_EFFICIENCY_DEPT_SHEET_ID = "4Dm37Kh"
HR_EFFICIENCY_MONTHLY_SHEET_ID = "A8lTbHJ"
HR_EFFICIENCY_CACHE_TTL = 300


def _env(name: str, default: str = "") -> str:
    """读取环境变量或 backend/.env，不返回任何凭据到 API。"""
    value = os.getenv(name, "").strip()
    if value:
        return value
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip("\"'")
    return default


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("name")
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _period_key(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000).strftime("%Y-%m")
    text = str(value).strip()
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return ""


def _all_records(client: DingTalkBitableClient, sheet_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token = None
    while True:
        result = client.list_records(sheet_id, page_size=500, page_token=page_token)
        page = result.get("records", result.get("value", [])) if isinstance(result, dict) else result
        rows.extend(page or [])
        page_token = result.get("nextToken") if isinstance(result, dict) else None
        if not page_token or not isinstance(result, dict) or not result.get("hasMore", False):
            break
        time.sleep(0.2)
    return rows

# 月度源表没有单独的在岗人数列。人数由「人力总成本 / 人均成本」反推，
# 得到 73、73、74、77、85、76、76，与源表人均指标保持一致。
DINGTALK_HR_EFFICIENCY_MONTHLY = [
    {
        "month": "2026-01", "label": "2026年01月", "revenue": 2973409.55,
        "net_profit": 247002.13, "total_labor_cost": 572873.83,
        "headcount": 73, "revenue_per_employee": 40731.65,
        "cost_per_employee": 7847.59, "profit_per_employee": 3383.59,
        "cost_efficiency": 5.19,
    },
    {
        "month": "2026-02", "label": "2026年02月", "revenue": 1677188.69,
        "net_profit": 147305.78, "total_labor_cost": 596340.72,
        "headcount": 73, "revenue_per_employee": 22975.18,
        "cost_per_employee": 8169.05, "profit_per_employee": 2017.89,
        "cost_efficiency": 2.81,
    },
    {
        "month": "2026-03", "label": "2026年03月", "revenue": 3189715.49,
        "net_profit": 309288.78, "total_labor_cost": 533851.39,
        "headcount": 74, "revenue_per_employee": 43104.28,
        "cost_per_employee": 7214.21, "profit_per_employee": 4179.58,
        "cost_efficiency": 5.97,
    },
    {
        "month": "2026-04", "label": "2026年04月", "revenue": 3135731.34,
        "net_profit": 198482.88, "total_labor_cost": 514113.72,
        "headcount": 77, "revenue_per_employee": 40723.77,
        "cost_per_employee": 6676.80, "profit_per_employee": 2577.70,
        "cost_efficiency": 6.10,
    },
    {
        "month": "2026-05", "label": "2026年05月", "revenue": 3310286.87,
        "net_profit": 245451.41, "total_labor_cost": 557916.71,
        "headcount": 85, "revenue_per_employee": 38944.58,
        "cost_per_employee": 6563.73, "profit_per_employee": 2887.66,
        "cost_efficiency": 5.93,
    },
    {
        "month": "2026-06", "label": "2026年06月", "revenue": 2503186.46,
        "net_profit": 166889.54, "total_labor_cost": 518272.66,
        "headcount": 76, "revenue_per_employee": 32936.68,
        "cost_per_employee": 6819.38, "profit_per_employee": 2195.91,
        "cost_efficiency": 4.83,
    },
    {
        "month": "2026-07", "label": "2026年07月", "revenue": 2995900.00,
        "net_profit": 191020.00, "total_labor_cost": 469377.54,
        "headcount": 76, "revenue_per_employee": 39419.74,
        "cost_per_employee": 6176.02, "profit_per_employee": 2513.42,
        "cost_efficiency": 6.38, "note": "暂估",
    },
]

# 08-12 月在源表为空。显式保留空行，让前端图表和明细表显示数据缺口，
# 而不是把缺失值误当成 0。
for _month, _label in [
    ("2026-08", "2026年08月"), ("2026-09", "2026年09月"),
    ("2026-10", "2026年10月"), ("2026-11", "2026年11月"),
    ("2026-12", "2026年12月"),
]:
    DINGTALK_HR_EFFICIENCY_MONTHLY.append({
        "month": _month, "label": _label, "note": "源表缺失",
        "revenue": None, "net_profit": None, "total_labor_cost": None,
        "headcount": None, "revenue_per_employee": None,
        "cost_per_employee": None, "profit_per_employee": None,
        "cost_efficiency": None,
    })

# 源表第 13 行「年度汇总」，不能再与月度行相加。
DINGTALK_HR_EFFICIENCY_ANNUAL = {
    "month": "2026", "label": "年度汇总", "revenue": 19785418.40,
    "net_profit": 1505440.52, "total_labor_cost": 3762746.57,
    "headcount": 76.2857, "revenue_per_employee": 259359.40,
    "cost_per_employee": 49324.39, "profit_per_employee": 19734.24,
    "cost_efficiency": 5.26,
}

# 部门表的有效记录汇总，用于公司人效页上的部门对比。这里不把「合计」
# 或「排名说明」作为一个部门，也不填充没有有效值的人均排名。
DINGTALK_DEPT_EFFICIENCY = [
    {"department": "淘宝", "headcount": 14, "revenue": 1600088.28},
    {"department": "商务", "headcount": 52, "revenue": 3507417.48},
    {"department": "千川", "headcount": 28, "revenue": 133616.76},
    {"department": "拼多多", "headcount": 26, "revenue": 9777375.74},
]


def _configured_sheet_ids() -> tuple[str, str, str]:
    return (
        _env("DINGTALK_HR_EFFICIENCY_BASE_ID", HR_EFFICIENCY_BASE_ID),
        _env("DINGTALK_HR_EFFICIENCY_DEPT_SHEET_ID", HR_EFFICIENCY_DEPT_SHEET_ID),
        _env("DINGTALK_HR_EFFICIENCY_MONTHLY_SHEET_ID", HR_EFFICIENCY_MONTHLY_SHEET_ID),
    )


def _live_snapshot() -> dict[str, Any]:
    """从两个已配置的钉钉 sheet 读取并清洗公司/部门人效数据。"""
    base_id, dept_sheet_id, monthly_sheet_id = _configured_sheet_ids()
    client = DingTalkBitableClient()
    client.app_id = base_id
    client.get_access_token()

    monthly_rows: list[dict[str, Any]] = []
    annual: dict[str, Any] | None = None
    for record in _all_records(client, monthly_sheet_id):
        fields = record.get("fields", record)
        month = _period_key(fields.get("期间"))
        note = str(fields.get("备注") or "").strip()
        revenue = _to_float(fields.get("营收(万元)"))
        profit = _to_float(fields.get("平台利润(万元)"))
        labor = _to_float(fields.get("人力总成本(万元)"))
        headcount = _to_float(fields.get("在岗人数"))
        item = {
            "month": month,
            "label": f"{month[:4]}年{month[5:7]}月" if month else "年度汇总",
            "revenue": revenue,
            "net_profit": profit,
            "total_labor_cost": labor,
            "headcount": headcount,
            "revenue_per_employee": _to_float(fields.get("人均收入(万元)")),
            "cost_per_employee": _to_float(fields.get("人均成本(万元)")),
            "profit_per_employee": _to_float(fields.get("人均净利润(万元)")),
            "cost_efficiency": _to_float(fields.get("成本效能")),
            "note": note,
        }
        if not month and (note == "年度汇总" or revenue is not None):
            item["month"] = "年度"
            item["label"] = "年度汇总"
            annual = item
        elif month:
            monthly_rows.append(item)

    monthly_rows.sort(key=lambda row: row["month"])
    if not monthly_rows:
        raise RuntimeError("公司人效月度数据表未返回有效月份")

    if annual is None:
        valid = [row for row in monthly_rows if row.get("revenue") is not None]
        if not valid:
            raise RuntimeError("公司人效月度数据没有可汇总的有效记录")
        revenue = sum(row["revenue"] for row in valid)
        profit = sum(row["net_profit"] or 0 for row in valid)
        labor = sum(row["total_labor_cost"] or 0 for row in valid)
        headcount = sum(row["headcount"] or 0 for row in valid) / len(valid)
        annual = {
            "month": "年度", "label": "年度汇总", "revenue": revenue,
            "net_profit": profit, "total_labor_cost": labor, "headcount": headcount,
            "revenue_per_employee": revenue / headcount if headcount else None,
            "cost_per_employee": labor / headcount if headcount else None,
            "profit_per_employee": profit / headcount if headcount else None,
            "cost_efficiency": revenue / labor if labor else None,
            "note": "按有效月份自动汇总",
        }

    department_totals: dict[str, dict[str, float]] = {}
    excluded = {"合计", "排名说明"}
    for record in _all_records(client, dept_sheet_id):
        fields = record.get("fields", record)
        department = str(fields.get("部门") or "").strip()
        if not department or department in excluded or "公式" in department:
            continue
        headcount = _to_float(fields.get("人数"))
        revenue = _to_float(fields.get("营收(万元)"))
        if headcount is None and revenue is None:
            continue
        item = department_totals.setdefault(department, {"headcount": 0.0, "revenue": 0.0})
        item["headcount"] += headcount or 0
        item["revenue"] += revenue or 0
    departments = [
        {"department": name, "headcount": round(values["headcount"], 2), "revenue": round(values["revenue"], 2)}
        for name, values in sorted(department_totals.items())
    ]
    if not departments:
        raise RuntimeError("公司人效部门数据表未返回有效部门记录")

    return {
        "monthly": monthly_rows,
        "annual": annual,
        "departments": departments,
        "source": f"{SOURCE_NAME}（API自动同步）",
        "source_note": SOURCE_NOTE + " 当前数据由钉钉多维表 API 自动读取。",
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0


def get_hr_efficiency_snapshot(force: bool = False) -> dict[str, Any]:
    """读取带 TTL 缓存的人效源数据；失败时回退本地快照，避免看板伪造 0 值。"""
    global _CACHE, _CACHE_AT
    ttl = max(30, int(_env("DINGTALK_HR_EFFICIENCY_CACHE_TTL", str(HR_EFFICIENCY_CACHE_TTL))))
    with _CACHE_LOCK:
        if not force and _CACHE is not None and time.time() - _CACHE_AT < ttl:
            return deepcopy(_CACHE)
        try:
            live = _live_snapshot()
            _CACHE = live
            _CACHE_AT = time.time()
            return deepcopy(live)
        except Exception as exc:  # noqa: BLE001 — API 暂时不可用时保留最近快照
            logger.warning("钉钉人效数据自动同步失败，回退本地快照：%s", exc)
            fallback = {
                "monthly": deepcopy(DINGTALK_HR_EFFICIENCY_MONTHLY),
                "annual": deepcopy(DINGTALK_HR_EFFICIENCY_ANNUAL),
                "departments": deepcopy(DINGTALK_DEPT_EFFICIENCY),
                "source": f"{SOURCE_NAME}（本地快照）",
                "source_note": SOURCE_NOTE + f" API暂不可用，使用本地快照：{exc}",
                "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            return fallback
