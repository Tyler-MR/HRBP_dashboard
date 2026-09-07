"""拼多多团队 BI 数据源 — MySQL bi.pdd_web_profit_data（仅后端使用，凭证只在 .env）

口径说明：
- 数据表: bi.pdd_web_profit_data（日级链接利润数据，2026-06 起，278K+ 行）
- 当月 = 看板选择月份；未选择时使用表内最新数据月（MAX(数据日期），上月用于环比 trend）
- 部门级经营指标 = 全表行聚合（不按负责人过滤，收入/成本/利润为全店真实值）
- 团队人数/成员 = 具名负责人（负责人 去重，排除 NULL/空值）
- 比例（毛利率/推广费占比/利润率/ROI）= 汇总金额重算，不做行均值
- MySQL 连接失败时重试 3 次，仍失败则返回 source_error 空数据（不返回假数据）
- 成员职位按月销售额排名：第 1 名「运营主管」，其余「运营专员」
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from taobao_bi import TaobaoDBError, _connect, _month_range, _require_env, _trend
from schemas import (
    DeptEfficiency,
    DeptMetric,
    DeptMember,
    MemberMetric,
    PddProductAnalysis,
    PddProductOwner,
    PddProductPeriod,
    PddProductReport,
    PddSupervisorBrief,
    PddSupervisorAnalysis,
    SubjectiveEval,
)

logger = logging.getLogger("pdd_bi")

TABLE = "pdd_web_profit_data"

# 钉钉 AI 多维表「拼多多打品成功率」
# 该表与招聘/在岗表使用同一已授权 Base，数据读取沿用统一 24 小时缓存。
PDD_PRODUCT_BASE = "ZgpG2NdyVXKlg9pBUPyv1eMrWMwvDqPk"
PDD_PRODUCT_SHEET = "YawtNoV"
PDD_PRODUCT_SHEET_NAME = "拼多多打品成功率"
PDD_PRODUCT_DATE = "日期"
PDD_PRODUCT_OWNER = "运营姓名"
PDD_PRODUCT_COUNT = "产品数"
PDD_B_COUNT = "B款连接数（日销500元+）"
PDD_A_COUNT = "A款链接数（日销1000元+）"

# 主观评价（人工主观项，非客观数据，按用户要求保留、不清空）
# 评估维度（用户口径）：数据驱动与选品力 / 店群品效管理 / 渠道拓展与策略贡献 / 运营人效 / 抗压与执行
_SUBJECTIVE = [
    SubjectiveEval(dimension="数据驱动与选品力", score=85, comment="以数据驱动选品，选品成功率较高", trend="up"),
    SubjectiveEval(dimension="店群品效管理", score=82, comment="店群运营流程顺畅，品效持续优化", trend="up"),
    SubjectiveEval(dimension="渠道拓展与策略贡献", score=80, comment="渠道策略执行到位，拓展有成效", trend="stable"),
    SubjectiveEval(dimension="运营人效", score=88, comment="人效表现良好，目标达成率高", trend="up"),
    SubjectiveEval(dimension="抗压与执行", score=78, comment="抗压能力强，执行落地快", trend="up"),
]


def _number(value: Any) -> float:
    """多维表数字字段可能以字符串返回，统一转成非负数。"""
    if value is None or value == "":
        return 0.0
    if isinstance(value, dict):
        value = value.get("value", value.get("text", ""))
    try:
        return max(0.0, float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    """提取文本/单选字段中的可读名称。"""
    if isinstance(value, list):
        return "/".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return str(value.get("name", value.get("text", value.get("value", ""))) or "").strip()
    return str(value or "").strip()


def _record_month(value: Any) -> Optional[str]:
    """将钉钉日期字段统一成 YYYY-MM，按中国时区解释毫秒时间戳。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            stamp = float(value) / 1000 if abs(float(value)) > 10_000_000_000 else float(value)
            # 钉钉日期时间戳为 UTC 毫秒，转换到中国时区后再取月份。
            dt = datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(hours=8)
            return dt.strftime("%Y-%m")
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m")
        except ValueError:
            continue
    import re
    match = re.search(r"(20\d{2})[-/年](\d{1,2})", text)
    return f"{match.group(1)}-{int(match.group(2)):02d}" if match else None


def _record_day(value: Any) -> Optional[str]:
    """将钉钉日期字段统一成 YYYY-MM-DD，供阶段性快照对比。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            stamp = float(value) / 1000 if abs(float(value)) > 10_000_000_000 else float(value)
            dt = datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(hours=8)
            return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _pdd_product_records(force: bool = False) -> List[dict]:
    """读取打品表全部记录，复用产品/设计表的 24 小时缓存和单飞锁。"""
    from product_bi import _fetch_records
    return _fetch_records(PDD_PRODUCT_BASE, PDD_PRODUCT_SHEET, force=force)


def _pdd_product_aggregate(rows: List[dict]) -> dict:
    product_count = sum(row["product_count"] for row in rows)
    b_count = sum(row["b_count"] for row in rows)
    a_count = sum(row["a_count"] for row in rows)
    a_rate = round(a_count / product_count * 100, 1) if product_count else 0.0
    b_rate = round(b_count / product_count * 100, 1) if product_count else 0.0
    return {
        "product_count": int(round(product_count)),
        "b_count": int(round(b_count)),
        "b_rate": b_rate,
        "a_count": int(round(a_count)),
        "a_rate": a_rate,
        "success_rate": round(a_rate * 0.6 + b_rate * 0.4, 1),
    }


def _build_pdd_product_report(period: str, summary: dict,
                              trend: List[PddProductPeriod],
                              owners: List[PddProductOwner],
                              team_performance: Optional[Dict[str, float]] = None) -> Optional[PddProductReport]:
    """用团队成功率、趋势、运营业绩和人效生成简洁的管理层判断。"""
    if not period or not summary.get("product_count"):
        return None

    quality_score = summary["success_rate"]
    if len(trend) >= 2:
        previous, current = trend[-2], trend[-1]
        success_delta = current.success_rate - previous.success_rate
        trend_text = (
            f"较{previous.month}，综合打品成功率{_trend_word(success_delta)}"
            f"{abs(success_delta):.1f}个百分点，A款成功率{_trend_word(current.a_rate - previous.a_rate)}"
            f"{abs(current.a_rate - previous.a_rate):.1f}个百分点，"
            f"B款成功率{_trend_word(current.b_rate - previous.b_rate)}"
            f"{abs(current.b_rate - previous.b_rate):.1f}个百分点。"
        )
    else:
        trend_text = "当前仅有一个月有效记录，暂不能判断环比波动，后续需持续沉淀月度数据。"

    ranked_owners = [item for item in owners if item.rank > 0]
    top_owner = ranked_owners[0] if ranked_owners else None
    quality_owner = max(owners, key=lambda item: item.success_score) if owners else None
    profit_owners = [item for item in owners if item.performance_available]
    negative_profit = [item for item in profit_owners if item.profit_margin < 0]
    highlights = [
        f"团队本期完成 {summary['product_count']} 个产品，综合打品成功率 {quality_score:.1f}%（A款 {summary['a_rate']:.1f}%×60% + B款 {summary['b_rate']:.1f}%×40%）。",
        trend_text,
    ]
    team_performance = team_performance or {}
    if team_performance.get("person_efficiency") is not None:
        highlights.append(
            f"团队月销售额 {team_performance.get('sales_revenue', 0):.2f} 万元，"
            f"人效 {team_performance.get('person_efficiency', 0):.2f} 万元/人，"
            f"利润率 {team_performance.get('profit_margin', 0):.2f}%，ROI {team_performance.get('roi', 0):.2f}。"
        )
    if top_owner:
        highlights.append(
            f"综合排名第一为{top_owner.name}：综合分 {top_owner.combined_score:.1f}，"
            f"月销售额 {top_owner.sales_revenue:.2f} 万元，A/B 款成功率 {top_owner.a_rate:.1f}%/{top_owner.b_rate:.1f}%。"
        )

    actions = [
        "将综合打品成功率作为团队质量指标，A款作为高质量结果指标、B款作为规模转化过程指标，按月复盘波动原因。",
        "综合排名按打品质量分50%+月销售额指数50%计算；对排名靠后或利润率为负的运营，逐项核查选品、投放、链接维护和利润结构。",
    ]
    if quality_owner and top_owner and quality_owner.name != top_owner.name:
        actions.insert(0, f"重点复盘{quality_owner.name}的打品方法，并与{top_owner.name}的销售业绩和店铺经营动作交叉验证。")
    if negative_profit:
        actions.append(f"当前有{len(negative_profit)}名运营出现负利润率，建议将利润和 ROI 纳入下一轮打品复盘。")

    return PddProductReport(
        headline=f"{period}团队综合打品成功率 {quality_score:.1f}%：人效 {team_performance.get('person_efficiency', 0):.2f} 万元/人。",
        conclusion=(
            f"团队当前综合打品成功率为{quality_score:.1f}%，应结合人效、利润率和ROI判断增长质量；"
            f"排名同时看打品质量与销售业绩，不能用单一成功率替代经营结果。{trend_text}"
        ),
        highlights=highlights,
        actions=actions[:3],
    )


def _trend_word(delta: float) -> str:
    if delta > 0:
        return "上升"
    if delta < 0:
        return "下降"
    return "持平"


def _pdd_supervisor_brief(product_rows: Optional[List[dict]] = None) -> PddSupervisorBrief:
    """返回主管提供的 8.15—9.1 阶段性判断，并补充源表可核对项。"""
    brief = PddSupervisorBrief(
        period="2026-08-15—2026-09-01",
        overall="从 8.15 日到 9.1 日，基础打品（500+）占比上涨 8 个点，优质打品（1000+）上涨 7 个点。",
        people=[
            "头部运营（朱康、周恒、戎晨琪、玉佳）：9.1 打品成功率大幅上涨，能够抓住预热窗口期红利；朱康表现最为亮眼，1000 元以上优质链接占比达到 35%，是团队标杆。",
            "吴永丽：两项指标完全没有增长，500+维持 20%，1000+维持 10%，没有借到 9.1 流量红利，需要复盘选品、打品动作。",
            "迎瑞：9.1 产品数量从 5 增加到 8，但打品占比反而下滑，500+从 20% 跌到 13%，扩品没有带来打品产出，属于扩品低效，新增产品没有跑出来。",
        ],
        focus=[
            "迎瑞：重点关注起品周期、起品概率和大爆链接诞生，本月目标至少 2 条日销 1 万元链接。",
            "晨琪：重点补足头部链接数量，本月目标 3 条以上日销 1 万元链接。",
        ],
        ai_comparison=[
            "周期粒度不同：主管判断使用 8.15—9.1 两个阶段快照，AI看板当前按月份聚合；不能直接用单月卡片替代阶段增幅。",
            "指标范围不同：AI可核对产品数、A/B链接数与占比，但当前打品表没有‘日销1万元链接数’和‘预热窗口红利’字段，相关目标与原因需要业务数据继续补充。",
        ],
    )
    rows = product_rows or []
    days = sorted({row.get("day") for row in rows if row.get("day")})
    if len(days) >= 2:
        first_day, last_day = days[0], days[-1]
        first = _pdd_product_aggregate([row for row in rows if row.get("day") == first_day])
        last = _pdd_product_aggregate([row for row in rows if row.get("day") == last_day])
        brief.ai_comparison.insert(
            0,
            f"AI源表复核（{first_day}→{last_day}）：500+占比 {first['b_rate']:.1f}%→{last['b_rate']:.1f}%，"
            f"上涨 {last['b_rate'] - first['b_rate']:.1f} 个百分点；1000+占比 {first['a_rate']:.1f}%→{last['a_rate']:.1f}%，"
            f"上涨 {last['a_rate'] - first['a_rate']:.1f} 个百分点。",
        )

        def owner_snapshot(name: str, day: str) -> Optional[dict]:
            owner_rows = [row for row in rows if row.get("day") == day and row.get("owner") == name]
            return _pdd_product_aggregate(owner_rows) if owner_rows else None

        early_yingrui = owner_snapshot("李迎瑞", first_day)
        late_yingrui = owner_snapshot("李迎瑞", last_day)
        early_yujia = owner_snapshot("周玉佳", first_day)
        late_yujia = owner_snapshot("周玉佳", last_day)
        if early_yingrui and late_yingrui:
            brief.ai_comparison.append(
                f"需核对迎瑞口径：AI源表中李迎瑞的 B款占比为 {early_yingrui['b_rate']:.1f}%→{late_yingrui['b_rate']:.1f}%，"
                "与主管文字中的‘20%降至13%’方向不一致，需确认姓名别名、日期或统计版本。"
            )
        if early_yujia and late_yujia:
            brief.ai_comparison.append(
                f"需核对玉佳口径：AI源表中周玉佳的综合成功率为 {early_yujia['success_rate']:.1f}%→{late_yujia['success_rate']:.1f}%，"
                "与主管文字中的‘大幅上涨’方向不一致，需确认是否为同一运营或另一版数据。"
            )
    else:
        brief.ai_comparison.append("当前源表不足两个日期快照，AI暂不能复核 8.15—9.1 的阶段增幅。")
    return brief


def _pdd_manager_log_text(rows: list) -> str:
    """合并本地已同步的管理人员日报，保留日期作为原文证据边界。"""
    parts = []
    for row in rows:
        try:
            contents = json.loads(row.contents) if row.contents else []
        except (TypeError, ValueError, json.JSONDecodeError):
            contents = []
        values = []
        for item in contents if isinstance(contents, list) else []:
            if isinstance(item, dict) and item.get("value"):
                values.append(str(item["value"]).strip())
        if values:
            date_label = row.create_time.strftime("%Y-%m-%d") if row.create_time else "未知日期"
            parts.append(f"[{date_label}]\n" + "\n".join(values))
    return "\n\n".join(parts)


def _pdd_month_bounds(period: str) -> tuple:
    """返回看板月份对应的本地日报查询区间 [start, end)。"""
    try:
        year, month_num = int(period[:4]), int(period[5:7])
        start = datetime(year, month_num, 1)
        end = datetime(year + 1, 1, 1) if month_num == 12 else datetime(year, month_num + 1, 1)
        return start, end
    except (TypeError, ValueError, IndexError):
        return None, None


def _build_pdd_supervisor_analysis(period: str, summary: dict,
                                   trend: List[PddProductPeriod],
                                   owners: List[PddProductOwner],
                                   team_performance: Optional[Dict[str, float]] = None,
                                   product_rows: Optional[List[dict]] = None) -> PddSupervisorAnalysis:
    """把朱康的拼多多主管日报原文与数值看板拆开，并生成可追溯差异说明。

    打品成功率多维表没有主管文字字段，主管原文只从本地已同步的日报读取；
    没有日志时保留空状态，避免把规则引擎生成的 AI 文本伪装成人工分析。
    """
    result = PddSupervisorAnalysis(period=period, supervisor_brief=_pdd_supervisor_brief(product_rows))
    start, end = _pdd_month_bounds(period)
    if not start or not end:
        result.status = "source_error"
        result.source_error = f"无法将看板周期 {period or '空'} 转换为日报月份"
        return result

    try:
        from database import SessionLocal
        from models import DailyLog
        from log_eval import evaluate_writing_reference

        db = SessionLocal()
        try:
            rows = (db.query(DailyLog)
                    .filter(DailyLog.creator_name == "朱康",
                            DailyLog.create_time >= start,
                            DailyLog.create_time < end)
                    .order_by(DailyLog.create_time).all())
            raw_text = _pdd_manager_log_text(rows)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — 日志源异常不影响打品数值看板
        result.status = "source_error"
        result.source_error = f"管理人员日报读取失败：{exc}"
        return result

    result.log_count = len(rows)
    result.raw_text = raw_text
    if not raw_text:
        result.conclusion = (
            f"{period} 周期暂无朱康（拼多多主管）日报原文；AI部分仍按钉钉打品数据和 MySQL 业绩数据生成，"
            "不能将 AI 分析当作主管意见。建议先补齐日报，再进行文字判断与经营结果复盘。"
        )
        result.differences = [
            "当前没有主管原文可对照，无法判断主管对成功率波动的具体原因和动作。",
            "AI分析只回答结果和排名，不具备主管原文中的经营背景、原因解释和下一步承诺。",
        ]
        result.ai_focus = _pdd_ai_focus(summary, trend, owners, team_performance)
        result.ai_only = [
            "A/B 成功率按链接数 ÷ 产品数汇总，并按 A款60% + B款40% 形成统一成功率。",
            "跨运营比较打品质量、销售额、人效、利润率和 ROI，形成综合排名。",
        ]
        return result

    result.status = "available"
    writing = evaluate_writing_reference(raw_text, "拼多多主管", "朱康")
    result.covered_dimensions = writing.get("hit") or []
    result.missing_dimensions = writing.get("miss") or []
    result.evidence = [
        f"{item['name']}：{item['evidence']}"
        for item in (writing.get("detail") or [])
        if item.get("covered") and item.get("evidence")
    ]
    result.supervisor_focus = [
        f"已覆盖「{'、'.join(result.covered_dimensions)}」等主管日志维度，重点记录经营动作、问题处理和明日安排。"
    ] if result.covered_dimensions else []
    if result.missing_dimensions:
        result.supervisor_focus.append(
            f"原文尚未覆盖「{'、'.join(result.missing_dimensions[:3])}」等参考维度，需补充对应证据。"
        )

    lower_text = raw_text.lower()
    has_result = any(word in lower_text for word in ["gmv", "销售额", "销量", "成交", "业绩", "投产", "roi"])
    has_flow = any(word in lower_text for word in ["活动", "流量", "推广", "曝光", "点击", "转化", "搜索", "百亿"])
    has_issue = any(word in lower_text for word in ["问题", "原因", "解决", "调整", "优化", "库存", "云仓", "工厂"])
    has_plan = any(word in lower_text for word in ["明日", "明天", "计划", "安排", "目标", "后续", "跟进"])

    result.ai_focus = _pdd_ai_focus(summary, trend, owners, team_performance)
    if has_result:
        result.consensus.append("主管日志关注爆品、销量或投产等经营结果，和 AI 用 A/B 成功率及业绩指标衡量结果的方向一致。")
    if has_flow:
        result.consensus.append("主管日志关注活动、流量和推广节奏，和 AI 追踪成功率波动、转化质量的经营目标一致。")
    if has_issue:
        result.consensus.append("主管日志记录供应链、库存或链接问题，AI 可提供结果异常的量化信号，双方可形成‘发现—定位’闭环。")
    if not result.consensus:
        result.consensus.append("双方都围绕拼多多打品质量和经营结果展开，但使用的证据类型不同。")

    if has_flow:
        result.supervisor_only.append("平台活动、流量获取、推广节奏等过程判断，AI 当前只能看到结果变化，不能仅凭成功率还原原因。")
    if has_issue:
        result.supervisor_only.append("爆品延伸、库存/云仓、工厂与上架节奏等具体业务动作，这些上下文未进入打品成功率数值表。")
    if has_plan:
        result.supervisor_only.append("明日计划、责任动作和跟进承诺，属于主管的前瞻性管理信息，不是 AI 结果指标。")
    if not result.supervisor_only:
        result.supervisor_only.append("主管原文中的业务判断和动作语境，需要继续保留在日报中，不能由成功率数值替代。")

    result.ai_only = [
        "按 A款60% + B款40% 汇总团队成功率，并同步展示 A/B 数量、成功率和趋势。",
        "按运营横向比较打品质量与月销售额指数，并联动人效、利润率和 ROI。",
    ]
    result.differences = [
        "主管原文回答‘为什么、做什么、何时跟进’，AI看板回答‘结果多少、波动怎样、谁更好’；两者不能互相替代。",
        "主管原文是日级事项与经营上下文，AI按月汇总产品和业绩数据；月度结果可能掩盖具体日期的异常原因。",
        "若文字判断与数值结果不一致，应先核对周期、产品数、A/B链接数及业绩口径，再由主管补充原因，不直接判定执行问题。",
    ]
    result.conclusion = (
        f"{period} 已读取朱康 {result.log_count} 篇日报：主管侧偏重爆品上架、活动推广、供应链准备和明日动作，"
        f"AI侧以 {summary.get('success_rate', 0):.1f}% 综合打品成功率及运营业绩做量化验证。"
        "建议用主管原文解释原因和动作，用 AI 结果确认效果，形成同一周期的经营复盘。"
    )
    return result


def _pdd_ai_focus(summary: dict, trend: List[PddProductPeriod],
                  owners: List[PddProductOwner],
                  team_performance: Optional[Dict[str, float]] = None) -> List[str]:
    """供主管原文对照的 AI/规则引擎分析摘要。"""
    focus = [
        f"结果量化：{summary.get('product_count', 0)} 个产品，A款 {summary.get('a_count', 0)} 个/{summary.get('a_rate', 0):.1f}%，"
        f"B款 {summary.get('b_count', 0)} 个/{summary.get('b_rate', 0):.1f}%，综合成功率 {summary.get('success_rate', 0):.1f}%。"
    ]
    if len(trend) >= 2:
        delta = trend[-1].success_rate - trend[-2].success_rate
        focus.append(f"趋势判断：综合成功率较上个有效月份{_trend_word(delta)} {abs(delta):.1f} 个百分点。")
    else:
        focus.append("趋势判断：当前仅有一个有效月份，暂不能确认环比波动。")
    team_performance = team_performance or {}
    if team_performance.get("person_efficiency") is not None:
        focus.append(
            f"经营质量：人效 {team_performance.get('person_efficiency', 0):.2f} 万元/人，"
            f"利润率 {team_performance.get('profit_margin', 0):.2f}%，ROI {team_performance.get('roi', 0):.2f}。"
        )
    ranked = [item for item in owners if item.rank > 0]
    if ranked:
        focus.append(f"横向比较：{ranked[0].name} 当前综合排名第一，综合分 {ranked[0].combined_score:.1f}。")
    return focus


def build_pdd_product_analysis(month: Optional[str] = None,
                               performance_by_owner: Optional[Dict[str, dict]] = None,
                               team_performance: Optional[Dict[str, float]] = None) -> PddProductAnalysis:
    """构建拼多多打品成功率分析：团队趋势 + 当月运营综合排名 + 人效分析报告。

    成功率按链接数/产品数重算，不对多维表中的逐行占比做简单平均，避免不同产品量
    的运营被等权处理。B 款定义为日销 500 元以上，A 款定义为日销 1000 元以上。
    performance_by_owner 来自同一统计周期的拼多多 MySQL 业绩聚合。
    """
    try:
        records = _pdd_product_records()
    except Exception as exc:  # noqa: BLE001 — 外部表异常不影响 MySQL 人效看板
        return PddProductAnalysis(
            source_sheet=PDD_PRODUCT_SHEET_NAME,
            source_error=f"钉钉多维表读取失败：{exc}",
        )

    rows: List[dict] = []
    for record in records:
        fields = record.get("fields", record) if isinstance(record, dict) else {}
        record_month = _record_month(fields.get(PDD_PRODUCT_DATE))
        product_count = _number(fields.get(PDD_PRODUCT_COUNT))
        if not record_month or product_count <= 0:
            continue
        rows.append({
            "month": record_month,
            "day": _record_day(fields.get(PDD_PRODUCT_DATE)),
            "owner": _text(fields.get(PDD_PRODUCT_OWNER)),
            "product_count": product_count,
            "b_count": _number(fields.get(PDD_B_COUNT)),
            "a_count": _number(fields.get(PDD_A_COUNT)),
        })

    if not rows:
        return PddProductAnalysis(
            source_sheet=PDD_PRODUCT_SHEET_NAME,
            source_error="钉钉多维表暂无可分析的产品记录",
        )

    latest_month = max(row["month"] for row in rows)
    period = month or latest_month
    period_rows = [row for row in rows if row["month"] == period]
    summary = _pdd_product_aggregate(period_rows)

    by_month: Dict[str, List[dict]] = {}
    for row in rows:
        if row["month"] <= period:
            by_month.setdefault(row["month"], []).append(row)
    trend = [PddProductPeriod(month=month_key, **_pdd_product_aggregate(by_month[month_key]))
             for month_key in sorted(by_month)[-6:]]

    trend_delta = None
    trend_label = ""
    if len(trend) >= 2:
        trend_delta = round(trend[-1].success_rate - trend[-2].success_rate, 1)
        trend_label = _trend_word(trend_delta)

    by_owner: Dict[str, List[dict]] = {}
    for row in period_rows:
        if row["owner"]:
            by_owner.setdefault(row["owner"], []).append(row)
    performance_by_owner = performance_by_owner or {}
    owners = []
    owner_names = sorted(set(by_owner) | set(performance_by_owner))
    for name in owner_names:
        owner_rows = by_owner.get(name, [])
        owner_summary = _pdd_product_aggregate(owner_rows)
        performance = performance_by_owner.get(name) or {}
        has_product_data = bool(owner_rows)
        success_score = owner_summary["success_rate"] if has_product_data else 0.0
        has_performance = bool(performance)
        performance_score = round(float(performance.get("performance_score") or 0), 1)
        combined_score = round((success_score + performance_score) / 2, 1) if has_product_data and has_performance else success_score
        owners.append(PddProductOwner(
            name=name,
            **owner_summary,
            success_score=success_score,
            performance_score=performance_score,
            combined_score=combined_score,
            performance_available=has_performance,
            sales_revenue=round(float(performance.get("sales_revenue") or 0), 2),
            profit=round(float(performance.get("profit") or 0), 2),
            profit_margin=round(float(performance.get("profit_margin") or 0), 2),
            roi=round(float(performance.get("roi") or 0), 2),
            stores=int(performance.get("stores") or 0),
            product_data_available=has_product_data,
        ))
    owners.sort(key=lambda item: (
        not (item.product_data_available and item.performance_available),
        -item.combined_score,
        -item.success_score,
        -item.product_count,
        item.name,
    ))
    rank = 1
    for owner in owners:
        if owner.product_data_available and owner.performance_available:
            owner.rank = rank
            rank += 1

    source_error = None if period_rows else f"{period} 暂无打品记录"
    team_performance = team_performance or {}
    return PddProductAnalysis(
        period=period,
        **summary,
        trend_delta=trend_delta,
        trend_label=trend_label,
        trend=trend,
        owners=owners,
        team_size=int(team_performance.get("team_size") or 0),
        team_sales_revenue=round(float(team_performance.get("sales_revenue") or 0), 2),
        team_profit=round(float(team_performance.get("profit") or 0), 2),
        team_profit_margin=round(float(team_performance.get("profit_margin") or 0), 2),
        team_roi=round(float(team_performance.get("roi") or 0), 2),
        team_person_efficiency=round(float(team_performance.get("person_efficiency") or 0), 2),
        report=_build_pdd_product_report(period, summary, trend, owners, team_performance),
        supervisor_analysis=_build_pdd_supervisor_analysis(
            period, summary, trend, owners, team_performance, product_rows=rows
        ),
        source_sheet=PDD_PRODUCT_SHEET_NAME,
        source_error=source_error,
    )


def refresh_pdd_product_cache() -> dict:
    """强制刷新拼多多打品成功率表，供每日任务和手动同步调用。"""
    records = _pdd_product_records(force=True)
    return {
        "pdd_product_records": len(records),
        "pdd_product_sheet": PDD_PRODUCT_SHEET_NAME,
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


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


def _previous_month(month: str) -> str:
    """返回 YYYY-MM 的上月，供看板选择历史月份时计算环比。"""
    year, month_num = int(month[:4]), int(month[5:7])
    return f"{year - 1:04d}-12" if month_num == 1 else f"{year:04d}-{month_num - 1:02d}"


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


def _roster_active(name: str) -> bool:
    """花名册在职状态：查不到（经营数据含非花名册负责人/店铺名）→ 保留；已离职(is_active=no) → 过滤。

    与钉钉花名册同步一致（用户口径 2026-08-11）：离职人员不显示在部门人效里。
    """
    try:
        from database import SessionLocal
        from models import Employee
        db = SessionLocal()
        try:
            r = db.query(Employee).filter(Employee.name == name).first()
            return True if r is None else r.is_active == "yes"
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — 本地库异常不阻断经营数据
        return True


def _error_dept(msg: str, month: Optional[str] = None) -> DeptEfficiency:
    """MySQL 不可用时保留独立的钉钉打品分析，经营指标/成员仍不伪造。"""
    product_analysis = None
    try:
        # 打品成功率来自独立的钉钉多维表，不应因拼多多经营 MySQL 超时而整体隐藏。
        product_analysis = build_pdd_product_analysis(month)
    except Exception as exc:  # noqa: BLE001 — 双重数据源均异常时只返回主错误
        logger.warning("MySQL 降级时拼多多打品分析也不可用: %s", exc)
    return DeptEfficiency(
        department="拼多多团队", team_size=0, score=None,
        metrics=[], members=[], subjective=_SUBJECTIVE,
        pdd_product_analysis=product_analysis,
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
    # 成员评分与部门雷达统一为单维 20 分制，五维合计 100 分
    subjective = [
        SubjectiveEval(dimension=d, score=round((means[d] if means[d] is not None else fallback), 1),
                       comment="成员评分均值聚合", trend="stable")
        for d in dims
    ]
    overall = sum(s.score for s in subjective) / len(subjective)
    return subjective, round(overall, 1)


def build_pdd_dept(month: Optional[str] = None) -> DeptEfficiency:
    """构建拼多多团队人效数据（MySQL 实时）。连接失败重试 3 次后返回 source_error 空数据。"""
    try:
        conn = _connect()
        try:
            latest_month, latest_prev_month = _latest_month(conn)
            cur_month = month or latest_month
            prev_month = _previous_month(cur_month) if month else latest_prev_month
            agg = _month_aggregate(conn, cur_month)
            prev = _month_aggregate(conn, prev_month)
            members_raw = _member_aggregates(conn, cur_month)
            members_prev = _member_aggregates(conn, prev_month)
        finally:
            conn.close()
    except TaobaoDBError as e:
        logger.error("拼多多数据源不可用: %s", e)
        return _error_dept(e, month)
    except Exception as e:  # noqa: BLE001 — 查询类异常同样降级，不拖垮整个看板
        logger.exception("拼多多数据源查询异常")
        return _error_dept(f"MySQL 查询异常：{e}", month)

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
    performance_by_owner: Dict[str, dict] = {}
    ranked = sorted(members_raw, key=lambda r: r["revenue"], reverse=True)
    max_rev = ranked[0]["revenue"] if ranked else 0.0
    for r in ranked:
        if not _roster_active(r["person"]):
            continue  # 已离职，不显示在部门人效（与钉钉花名册同步）
        rev_wan = r["revenue"] / 10000.0
        per_store = rev_wan / r["stores"] if r["stores"] else 0.0
        profit_wan = r["profit"] / 10000.0
        owner_profit_pct = r["profit"] / r["revenue"] * 100 if r["revenue"] else 0.0
        owner_roi = r["revenue"] / r["promotion"] if r["promotion"] else 0.0
        performance_by_owner[r["person"]] = {
            "performance_score": min(100.0, r["revenue"] / max_rev * 100) if max_rev else 0.0,
            "sales_revenue": rev_wan,
            "profit": profit_wan,
            "profit_margin": profit_pct,
            "roi": owner_roi,
            "stores": r["stores"],
        }
        members.append(DeptMember(
            name=r["person"],
            position=_MEMBER_POSITIONS.get(r["person"], "运营专员"),  # 岗位按人事配置
            score=round(min(100.0, r["revenue"] / max_rev * 100), 1) if max_rev else 0.0,
            metrics=[
                MemberMetric(name="管辖店铺数", value=r["stores"], unit="个"),
                MemberMetric(name="月销售额", value=round(rev_wan, 2), unit="万元"),
                MemberMetric(name="月订单量", value=round(r["qty"] / 10000.0, 2), unit="万单"),
                MemberMetric(name="利润率", value=round(owner_profit_pct, 2), unit="%"),
                MemberMetric(name="利润值", value=round(profit_wan, 2), unit="万元"),
                MemberMetric(name="推广ROI", value=round(owner_roi, 2), unit="倍"),
                MemberMetric(name="单店销售额", value=round(per_store, 2), unit="万元/店"),
            ],
            evaluation=f"{cur_month} 管辖{r['stores']}家店铺，月销售额{rev_wan:.2f}万元，月订单{r['qty']:.0f}单，利润{profit_wan:.2f}万元（利润率{owner_profit_pct:.2f}%）",
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
        pdd_product_analysis=build_pdd_product_analysis(
            month,
            performance_by_owner,
            {
                "team_size": team_size,
                "sales_revenue": revenue_wan,
                "profit": agg["profit"] / 10000.0,
                "profit_margin": profit_pct,
                "roi": roi,
                "person_efficiency": person_eff,
            },
        ),
        source="pdd",
        source_error=None,
    )
