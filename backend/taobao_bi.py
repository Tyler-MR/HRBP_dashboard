"""淘宝团队 BI 数据源 — MySQL bi.taobao_bi_data（仅后端使用，凭证只在 .env）

口径说明：
- 数据表: bi.taobao_bi_data（日级商品/链接经营数据，2026-06 起）
- 当月 = 表内最新数据月（MAX(data_date)），上月用于环比 trend
- 部门级经营指标 = 全表行聚合（含无负责人标注的真实商品行，避免低估销售额）
- 团队人数/成员 = 具名负责人（person 去重，排除 '公司' 汇总行与空值）
- MySQL 连接失败时重试 3 次，仍失败则返回 source_error 空数据（不返回假数据）
- 成员职位按月销售额排名：第 1 名「运营主管」，其余「运营专员」
"""
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pymysql

from schemas import DeptEfficiency, DeptMetric, DeptMember, MemberMetric, SubjectiveEval

logger = logging.getLogger("taobao_bi")

CONNECT_MAX_ATTEMPTS = 3            # 连接失败重试次数（用户要求 3 次）
CONNECT_RETRY_DELAYS = (0.5, 1.0)   # 第 2、3 次尝试前的等待秒数
PERSON_EXCLUDE = "公司"              # 汇总行负责人，不计入团队/成员
TABLE = "taobao_bi_data"

# 主观评价（人工主观项，非客观数据，按用户要求保留、不清空）
# 评估维度（用户口径）：数据驱动与选品力 / 店群品效管理 / 渠道拓展与策略贡献 / 运营人效 / 抗压与执行
_SUBJECTIVE = [
    SubjectiveEval(dimension="数据驱动与选品力", score=78, comment="选品有数据支撑，选品成功率需提升", trend="down"),
    SubjectiveEval(dimension="店群品效管理", score=80, comment="店铺运营稳定，品效管理待优化", trend="stable"),
    SubjectiveEval(dimension="渠道拓展与策略贡献", score=82, comment="渠道策略执行到位，经验丰富", trend="stable"),
    SubjectiveEval(dimension="运营人效", score=85, comment="人效表现良好，响应及时", trend="up"),
    SubjectiveEval(dimension="抗压与执行", score=75, comment="抗压能力尚可，新玩法执行需加强", trend="down"),
]


class TaobaoDBError(Exception):
    """淘宝 MySQL 数据源连接/查询失败"""


def _require_env(name: str, default: str = "") -> str:
    """读取环境变量，缺失时回退解析 backend/.env（与 dingtalk_sync 同规则）。"""
    val = os.getenv(name, "").strip()
    if val:
        return val
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip("\"'")
    return default


def _conn_params() -> dict:
    return dict(
        host=_require_env("MYSQL_HOST"),
        port=int(_require_env("MYSQL_PORT", "3306") or 3306),
        user=_require_env("MYSQL_USER"),
        password=_require_env("MYSQL_PASSWORD"),
        database=_require_env("MYSQL_DB", "bi") or "bi",
        charset="utf8mb4",
        connect_timeout=8,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _connect() -> pymysql.Connection:
    """连接 MySQL，失败自动重试 3 次（第 2/3 次前分别等待 0.5s/1s）。"""
    last_err: Optional[Exception] = None
    for attempt in range(1, CONNECT_MAX_ATTEMPTS + 1):
        try:
            return pymysql.connect(**_conn_params())
        except Exception as e:  # noqa: BLE001 — 连接类错误统一走重试
            last_err = e
            logger.warning("MySQL 连接失败(第%d/%d次): %s", attempt, CONNECT_MAX_ATTEMPTS, e)
            if attempt < CONNECT_MAX_ATTEMPTS:
                time.sleep(CONNECT_RETRY_DELAYS[attempt - 1])
    raise TaobaoDBError(f"MySQL 连接失败（已重试{CONNECT_MAX_ATTEMPTS}次）：{last_err}")


def _month_range(month: str) -> Tuple[date, date]:
    """'YYYY-MM' -> (当月1号, 次月1号)，左闭右开区间"""
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def _latest_month(conn: pymysql.Connection) -> Tuple[str, str]:
    """返回 (最新数据月, 上月)，均 'YYYY-MM'"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX(data_date) AS d FROM {TABLE}")
        row = cur.fetchone()
    latest = row["d"] if row and row["d"] else date.today()
    cur_month = latest.strftime("%Y-%m")
    prev_month = (latest.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return cur_month, prev_month


def _month_aggregate(conn: pymysql.Connection, month: str) -> dict:
    """单月整体聚合（部门口径：全表行均属淘宝团队经营，不做 person 过滤；
    公司汇总行仅影响成员/人数统计，不影响经营额）。"""
    start, end = _month_range(month)
    sql = f"""
        SELECT
            COUNT(DISTINCT store_name) AS stores,
            COALESCE(SUM(revenue), 0)  AS revenue,
            COALESCE(SUM(orders), 0)   AS orders,
            COALESCE(SUM(refund_rate * orders) / NULLIF(SUM(orders), 0), 0) AS refund_rate,
            COALESCE(SUM(gross_profit) / NULLIF(SUM(revenue), 0), 0)        AS gross_margin,
            COALESCE(SUM(promotion), 0)          AS promotion,
            COALESCE(SUM(platform_profit), 0)    AS platform_profit
        FROM {TABLE}
        WHERE data_date >= %s AND data_date < %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start, end))
        row = cur.fetchone()
    return row or {"stores": 0, "revenue": 0.0, "orders": 0.0,
                   "refund_rate": 0.0, "gross_margin": 0.0, "promotion": 0.0, "platform_profit": 0.0}


def _member_aggregates(conn: pymysql.Connection, month: str) -> List[dict]:
    """按负责人聚合（排除 person='公司'）。"""
    start, end = _month_range(month)
    sql = f"""
        SELECT person,
               COUNT(DISTINCT store_name) AS stores,
               COALESCE(SUM(revenue), 0)  AS revenue,
               COALESCE(SUM(orders), 0)   AS orders
        FROM {TABLE}
        WHERE data_date >= %s AND data_date < %s
          AND person IS NOT NULL AND person != ''
          AND person != %s
        GROUP BY person
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start, end, PERSON_EXCLUDE))
        return cur.fetchall() or []


def _trend(cur: float, prev: Optional[float], positive: bool = True) -> str:
    """环比趋势。positive=True 指标越大越好；退款率等 negative 指标越小越好。"""
    if prev is None or prev == 0:
        return "stable"
    if cur > prev:
        return "up" if positive else "down"
    if cur < prev:
        return "down" if positive else "up"
    return "stable"


def _derive_score(agg: dict, roi: float) -> float:
    """综合评分：毛利率/ROI/退款率 加权推导（非写死）。
    毛利率 20% 记满分；ROI 6 记满分；退款率每 1% 扣 10 分（10% 归零）。"""
    margin_pct = agg["gross_margin"] * 100
    refund_pct = agg["refund_rate"] * 100
    margin_score = min(100.0, margin_pct / 20.0 * 100)
    roi_score = min(100.0, roi / 6.0 * 100)
    refund_score = max(0.0, min(100.0, 100.0 - refund_pct * 10))
    return round(0.4 * margin_score + 0.3 * roi_score + 0.3 * refund_score, 1)


# 成员岗位配置（人事口径，按姓名固定；未配置的新负责人默认"运营专员"）
_MEMBER_POSITIONS = {
    "王新朝": "天猫经理",
    "李晓军": "天猫储备主管",
    "李世豪": "天猫组长",
}


def _error_dept(msg: str) -> DeptEfficiency:
    """数据源不可用时的降级返回：不携带任何客观指标/成员（不显示假数据）。"""
    return DeptEfficiency(
        department="淘宝团队", team_size=0, score=None,
        metrics=[], members=[], subjective=_SUBJECTIVE,
        source="mysql", source_error=str(msg),
    )


def build_taobao_dept() -> DeptEfficiency:
    """构建淘宝团队人效数据（MySQL 实时）。连接失败重试 3 次后返回 source_error 空数据。"""
    try:
        conn = _connect()
        try:
            cur_month, prev_month = _latest_month(conn)
            agg = _month_aggregate(conn, cur_month)
            prev = _month_aggregate(conn, prev_month)
            members_raw = _member_aggregates(conn, cur_month)
            members_prev = _member_aggregates(conn, prev_month)
        finally:
            conn.close()
    except TaobaoDBError as e:
        logger.error("淘宝数据源不可用: %s", e)
        return _error_dept(e)
    except Exception as e:  # noqa: BLE001 — 查询类异常同样降级，不拖垮整个看板
        logger.exception("淘宝数据源查询异常")
        return _error_dept(f"MySQL 查询异常：{e}")

    revenue_wan = agg["revenue"] / 10000.0
    orders_wan = agg["orders"] / 10000.0
    profit_wan = agg["platform_profit"] / 10000.0
    roi = agg["revenue"] / agg["promotion"] if agg["promotion"] else 0.0
    team_size = len(members_raw)  # 具名负责人数（排除'公司'/空值）
    person_eff = revenue_wan / team_size if team_size else 0.0
    prev_roi = (prev["revenue"] / prev["promotion"]) if prev["promotion"] else None
    prev_eff = (prev["revenue"] / 10000.0 / len(members_prev)) if members_prev else None

    metrics = [
        DeptMetric(name="运营店铺数", value=agg["stores"], unit="个", target=None,
                   trend=_trend(agg["stores"], prev["stores"], positive=True)),
        DeptMetric(name="月销售额", value=round(revenue_wan, 2), unit="万元", target=None,
                   trend=_trend(agg["revenue"], prev["revenue"], positive=True)),
        DeptMetric(name="月订单量", value=round(orders_wan, 2), unit="万单", target=None,
                   trend=_trend(agg["orders"], prev["orders"], positive=True)),
        DeptMetric(name="退款率", value=round(agg["refund_rate"] * 100, 2), unit="%", target=None,
                   trend=_trend(agg["refund_rate"], prev["refund_rate"])),
        DeptMetric(name="毛利率", value=round(agg["gross_margin"] * 100, 2), unit="%", target=None,
                   trend=_trend(agg["gross_margin"], prev["gross_margin"], positive=True)),
        DeptMetric(name="推广ROI", value=round(roi, 2), unit="", target=None,
                   trend=_trend(roi, prev_roi, positive=True)),
        DeptMetric(name="平台利润", value=round(profit_wan, 2), unit="万元", target=None,
                   trend=_trend(agg["platform_profit"], prev["platform_profit"], positive=True)),
        DeptMetric(name="人效(销售额/人)", value=round(person_eff, 2), unit="万元/人", target=None,
                   trend=_trend(person_eff, prev_eff, positive=True)),
    ]

    members: List[DeptMember] = []
    ranked = sorted(members_raw, key=lambda r: r["revenue"], reverse=True)
    max_rev = ranked[0]["revenue"] if ranked else 0.0
    for r in ranked:
        rev_wan = r["revenue"] / 10000.0
        per_store = rev_wan / r["stores"] if r["stores"] else 0.0
        members.append(DeptMember(
            name=r["person"],
            position=_MEMBER_POSITIONS.get(r["person"], "运营专员"),  # 岗位按人事配置
            score=round(min(100.0, r["revenue"] / max_rev * 100), 1) if max_rev else 0.0,
            metrics=[
                MemberMetric(name="管辖店铺数", value=r["stores"], unit="个"),
                MemberMetric(name="月销售额", value=round(rev_wan, 2), unit="万元"),
                MemberMetric(name="月订单量", value=round(r["orders"] / 10000.0, 2), unit="万单"),
                MemberMetric(name="单店销售额", value=round(per_store, 2), unit="万元/店"),
            ],
            evaluation=f"{cur_month} 管辖{r['stores']}家店铺，月销售额{rev_wan:.2f}万元，月订单{r['orders']:.0f}单",
        ))

    return DeptEfficiency(
        department="淘宝团队",
        team_size=team_size,
        score=_derive_score(agg, roi),
        metrics=metrics,
        members=members,
        subjective=_SUBJECTIVE,
        source="mysql",
        source_error=None,
    )
