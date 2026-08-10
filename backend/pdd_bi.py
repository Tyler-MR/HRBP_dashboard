"""拼多多团队 BI 数据源 — MySQL bi.pdd_web_profit_data（仅后端使用，凭证只在 .env）

口径说明：
- 数据表: bi.pdd_web_profit_data（日级链接利润数据，2026-06 起，278K+ 行）
- 当月 = 表内最新数据月（MAX(数据日期)），上月用于环比 trend
- 部门级经营指标 = 全表行聚合（不按负责人过滤，收入/成本/利润为全店真实值）
- 团队人数/成员 = 具名负责人（负责人 去重，排除 NULL/空值）
- 比例（毛利率/推广费占比/利润率/ROI）= 汇总金额重算，不做行均值
- MySQL 连接失败时重试 3 次，仍失败则返回 source_error 空数据（不返回假数据）
- 成员职位按月销售额排名：第 1 名「运营主管」，其余「运营专员」
"""
import logging
from typing import List

from taobao_bi import TaobaoDBError, _connect, _month_range, _require_env, _trend
from schemas import DeptEfficiency, DeptMetric, DeptMember, MemberMetric, SubjectiveEval

logger = logging.getLogger("pdd_bi")

TABLE = "pdd_web_profit_data"

# 主观评价（人工主观项，非客观数据，按用户要求保留、不清空）
# 评估维度（用户口径）：数据驱动与选品力 / 店群品效管理 / 渠道拓展与策略贡献 / 运营人效 / 抗压与执行
_SUBJECTIVE = [
    SubjectiveEval(dimension="数据驱动与选品力", score=85, comment="以数据驱动选品，选品成功率较高", trend="up"),
    SubjectiveEval(dimension="店群品效管理", score=82, comment="店群运营流程顺畅，品效持续优化", trend="up"),
    SubjectiveEval(dimension="渠道拓展与策略贡献", score=80, comment="渠道策略执行到位，拓展有成效", trend="stable"),
    SubjectiveEval(dimension="运营人效", score=88, comment="人效表现良好，目标达成率高", trend="up"),
    SubjectiveEval(dimension="抗压与执行", score=78, comment="抗压能力强，执行落地快", trend="up"),
]


def _latest_month(conn) -> tuple:
    """返回 (最新数据月, 上月)，均 'YYYY-MM'"""
    from datetime import date, timedelta
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX(数据日期) AS d FROM {TABLE}")
        row = cur.fetchone()
    latest = row["d"] if row and row["d"] else date.today()
    cur_month = latest.strftime("%Y-%m")
    prev_month = (latest.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return cur_month, prev_month


def _month_aggregate(conn, month: str) -> dict:
    """单月整体聚合（部门口径：全表行，不按负责人过滤）。"""
    start, end = _month_range(month)
    sql = f"""
        SELECT
            COUNT(DISTINCT 店铺名称) AS stores,
            COUNT(DISTINCT 链接id)   AS links,
            COALESCE(SUM(单量), 0)        AS qty,
            COALESCE(SUM(收入), 0)        AS revenue,
            COALESCE(SUM(成本), 0)        AS cost,
            COALESCE(SUM(快递), 0)        AS shipping,
            COALESCE(SUM(推广费), 0)      AS promotion,
            COALESCE(SUM(毛利), 0)        AS gross_profit,
            COALESCE(SUM(平台利润), 0)    AS profit
        FROM {TABLE}
        WHERE 数据日期 >= %s AND 数据日期 < %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start, end))
        row = cur.fetchone()
    return row or {"stores": 0, "links": 0, "qty": 0.0, "revenue": 0.0, "cost": 0.0,
                   "shipping": 0.0, "promotion": 0.0, "gross_profit": 0.0, "profit": 0.0}


def _member_aggregates(conn, month: str) -> List[dict]:
    """按负责人聚合（排除 NULL/空负责人）。"""
    start, end = _month_range(month)
    sql = f"""
        SELECT 负责人 AS person,
               COUNT(DISTINCT 店铺名称) AS stores,
               COUNT(DISTINCT 链接id)   AS links,
               COALESCE(SUM(单量), 0)   AS qty,
               COALESCE(SUM(收入), 0)   AS revenue,
               COALESCE(SUM(推广费), 0) AS promotion,
               COALESCE(SUM(毛利), 0)   AS gross_profit,
               COALESCE(SUM(平台利润), 0) AS profit
        FROM {TABLE}
        WHERE 数据日期 >= %s AND 数据日期 < %s
          AND 负责人 IS NOT NULL AND 负责人 != ''
        GROUP BY 负责人
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start, end))
        return cur.fetchall() or []


def _derive_score(agg: dict) -> float:
    """综合评分：毛利率/利润率/推广费占比 加权推导（非写死）。
    毛利率 50% 记满分；利润率 5% 记满分；推广费占比每 1% 扣 2 分（50% 归零）。"""
    margin_pct = agg["gross_profit"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    profit_pct = agg["profit"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    promo_pct = agg["promotion"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    margin_score = min(100.0, margin_pct / 50.0 * 100)
    profit_score = min(100.0, profit_pct / 5.0 * 100)
    promo_score = max(0.0, min(100.0, 100.0 - promo_pct * 2))
    return round(0.4 * margin_score + 0.3 * profit_score + 0.3 * promo_score, 1)


# 成员岗位配置（人事口径，按姓名固定；未配置的新负责人默认"运营专员"）
_MEMBER_POSITIONS = {
    "朱康": "拼多多主管",
    "周恒": "拼多多运营",
    "吴永丽": "运营组长",
    "周玉佳": "运营助理",
    "李迎瑞": "储备运营",
    "戎晨琪": "拼多多运营",
}


def _error_dept(msg: str) -> DeptEfficiency:
    """数据源不可用时的降级返回：不携带任何客观指标/成员（不显示假数据）。"""
    return DeptEfficiency(
        department="拼多多团队", team_size=0, score=None,
        metrics=[], members=[], subjective=_SUBJECTIVE,
        source="pdd", source_error=str(msg),
    )


def _member_radar_dims(db) -> tuple:
    """按成员个人雷达评分聚合部门雷达维度（用户口径：每个维度 = 已评分成员该维度均值）。

    返回 (subjective列表, 综合评分)；无任何成员评分时返回 (None, None) 供调用方回退。
    """
    from models import MemberScore

    dims = ["数据驱动与选品力", "店群品效管理", "渠道拓展与策略贡献", "运营人效", "抗压与执行"]
    acc = {d: [] for d in dims}
    try:
        rows = db.query(MemberScore).filter(MemberScore.department == "拼多多团队").all()
    except Exception:  # noqa: BLE001 — 本地库异常回退
        return None, None
    for r in rows:
        if r.dimension in acc and r.score is not None:
            acc[r.dimension].append(r.score)
    means = {d: (sum(v) / len(v) if v else None) for d, v in acc.items()}
    scored = [m for m in means.values() if m is not None]
    if not scored:
        return None, None
    fallback = sum(scored) / len(scored)  # 未评分维度用已评分维度均值兜底
    # 成员评分为 10 分制（电商口径），部门雷达为百分制，聚合时 ×10 换算
    subjective = [
        SubjectiveEval(dimension=d, score=round((means[d] if means[d] is not None else fallback) * 10, 1),
                       comment="成员评分均值聚合", trend="stable")
        for d in dims
    ]
    overall = sum(s.score for s in subjective) / len(subjective)
    return subjective, round(overall, 1)


def build_pdd_dept() -> DeptEfficiency:
    """构建拼多多团队人效数据（MySQL 实时）。连接失败重试 3 次后返回 source_error 空数据。"""
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
        logger.error("拼多多数据源不可用: %s", e)
        return _error_dept(e)
    except Exception as e:  # noqa: BLE001 — 查询类异常同样降级，不拖垮整个看板
        logger.exception("拼多多数据源查询异常")
        return _error_dept(f"MySQL 查询异常：{e}")

    revenue_wan = agg["revenue"] / 10000.0
    qty_wan = agg["qty"] / 10000.0
    roi = agg["revenue"] / agg["promotion"] if agg["promotion"] else 0.0
    team_size = len(members_raw)  # 具名负责人数（排除 NULL/空值）
    person_eff = revenue_wan / team_size if team_size else 0.0
    prev_roi = (prev["revenue"] / prev["promotion"]) if prev["promotion"] else None
    prev_eff = (prev["revenue"] / 10000.0 / len(members_prev)) if members_prev else None

    margin_pct = agg["gross_profit"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    profit_pct = agg["profit"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    promo_pct = agg["promotion"] / agg["revenue"] * 100 if agg["revenue"] else 0.0
    prev_margin = (prev["gross_profit"] / prev["revenue"] * 100) if prev["revenue"] else None
    prev_profit_pct = (prev["profit"] / prev["revenue"] * 100) if prev["revenue"] else None
    prev_promo_pct = (prev["promotion"] / prev["revenue"] * 100) if prev["revenue"] else None

    metrics = [
        DeptMetric(name="运营店铺数", value=agg["stores"], unit="个", target=None,
                   trend=_trend(agg["stores"], prev["stores"])),
        DeptMetric(name="月销售额", value=round(revenue_wan, 2), unit="万元", target=None,
                   trend=_trend(agg["revenue"], prev["revenue"])),
        DeptMetric(name="月订单量", value=round(qty_wan, 2), unit="万单", target=None,
                   trend=_trend(agg["qty"], prev["qty"])),
        DeptMetric(name="毛利率", value=round(margin_pct, 2), unit="%", target=None,
                   trend=_trend(margin_pct, prev_margin)),
        DeptMetric(name="推广费占比", value=round(promo_pct, 2), unit="%", target=None,
                   trend=_trend(promo_pct, prev_promo_pct)),
        DeptMetric(name="推广ROI", value=round(roi, 2), unit="倍", target=None,
                   trend=_trend(roi, prev_roi)),
        DeptMetric(name="平台利润率", value=round(profit_pct, 2), unit="%", target=None,
                   trend=_trend(profit_pct, prev_profit_pct)),
        DeptMetric(name="人效(销售额/人)", value=round(person_eff, 2), unit="万元/人", target=None,
                   trend=_trend(person_eff, prev_eff)),
    ]

    members: List[DeptMember] = []
    ranked = sorted(members_raw, key=lambda r: r["revenue"], reverse=True)
    max_rev = ranked[0]["revenue"] if ranked else 0.0
    for r in ranked:
        rev_wan = r["revenue"] / 10000.0
        per_store = rev_wan / r["stores"] if r["stores"] else 0.0
        profit_wan = r["profit"] / 10000.0
        profit_pct = r["profit"] / r["revenue"] * 100 if r["revenue"] else 0.0
        members.append(DeptMember(
            name=r["person"],
            position=_MEMBER_POSITIONS.get(r["person"], "运营专员"),  # 岗位按人事配置
            score=round(min(100.0, r["revenue"] / max_rev * 100), 1) if max_rev else 0.0,
            metrics=[
                MemberMetric(name="管辖店铺数", value=r["stores"], unit="个"),
                MemberMetric(name="月销售额", value=round(rev_wan, 2), unit="万元"),
                MemberMetric(name="月订单量", value=round(r["qty"] / 10000.0, 2), unit="万单"),
                MemberMetric(name="利润率", value=round(profit_pct, 2), unit="%"),
                MemberMetric(name="利润值", value=round(profit_wan, 2), unit="万元"),
                MemberMetric(name="单店销售额", value=round(per_store, 2), unit="万元/店"),
            ],
            evaluation=f"{cur_month} 管辖{r['stores']}家店铺，月销售额{rev_wan:.2f}万元，月订单{r['qty']:.0f}单，利润{profit_wan:.2f}万元（利润率{profit_pct:.2f}%）",
        ))

    # 综合评分与雷达维度：优先按成员个人雷达评分聚合（每维度=已评分成员均值），无成员评分时回退经营推导+主观评价
    subjective = _SUBJECTIVE
    score = _derive_score(agg)
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            subj_agg, score_agg = _member_radar_dims(db)
        finally:
            db.close()
        if subj_agg is not None:
            subjective, score = subj_agg, score_agg
    except Exception as e:  # noqa: BLE001 — 聚合异常回退，不拖垮看板
        logger.warning("成员雷达聚合失败，回退经营推导评分: %s", e)

    return DeptEfficiency(
        department="拼多多团队",
        team_size=team_size,
        score=score,
        metrics=metrics,
        members=members,
        subjective=subjective,
        source="pdd",
        source_error=None,
    )
