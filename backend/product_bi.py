"""产品团队 BI 数据源 — 钉钉多维表 双维度（仅后端使用，凭证复用 dingtalk_bitable）

口径说明（用户指定 2026-08-05，两个数据元并存）：
┌─ 📦 产品维度：表「产品全流程进度跟踪」 base jb9Y4gmKWrOZdDQYS46kzd0bVGXn6lpz / sheet c4187mk21vpbbmln7t6vm
│    - 月度目标上线数 = 预计上线日期(text "8月27日"，按月匹配)所在月 == 看板设定月 的记录数
│    - 月度已上线数   = 上述记录中「当前已上线渠道」有值（非空）的记录数
│    - 月度达成率     = 月度已上线数 / 月度目标上线数（目标为 0 时不除零）
│    - 负责人达成率   = 该产品负责人本人 已上线数 / 目标上线数（用户已确认为标准口径）
└─ 🎨 设计维度：表「设计每日稿件统计」 base jb9Y4gmKWrOZdDQYS46kzd0bVGXn6lpz / sheet 3rpDrEF（2026-08-11 起与产品表同 base）
     - 月度设计数 = 日期(毫秒时间戳)所在月 == 看板设定月 的记录数
     - 月度通过数 = 上述记录中「是否通过」= '通过' 的记录数（企业口径：仅'通过'算通过）
     - 月度通过率 = 月度通过数 / 月度设计数（用户已确认为标准口径；设计数为 0 时不除零）
     - 设计人员明细 = 每人 设计数 / 通过数 / 通过率

通用规则：
- 负责人/设计人员为空的记录计入部门汇总，不计入成员明细
- 综合评分 = 两维度达成率/通过率的均值（无数据的维度不计入，全空为 None）
- 每表每日刷新一次并使用 24 小时内存缓存；前端普通查询只读缓存，手动同步时强制刷新
- 外部接口失败后 5 分钟内进入冷却，避免失败请求形成重试风暴
- 钉钉接口失败 → source_error 空数据（不返回假数据），与拼多多/淘宝降级策略一致
"""
import logging
import re
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from dingtalk_bitable import DingTalkBitableClient
from schemas import DeptEfficiency, DeptMetric, DeptMember, MemberMetric, SubjectiveEval

logger = logging.getLogger("product_bi")

# ── 产品维度：产品全流程进度跟踪 ──
PRODUCT_BASE = "jb9Y4gmKWrOZdDQYS46kzd0bVGXn6lpz"
PRODUCT_SHEET = "c4187mk21vpbbmln7t6vm"
P_DATE_FIELD = "预计上线日期"       # text: "8月27日"（无年份）
P_CHANNEL_FIELD = "当前已上线渠道"  # multipleSelect: 有值 = 已上线
P_OWNER_FIELD = "产品负责人"       # singleSelect

# ── 设计维度：设计每日稿件统计（2026-08-11 起与产品表同 base，sheet 名「设计每日稿件统计」）──
DESIGN_BASE = "jb9Y4gmKWrOZdDQYS46kzd0bVGXn6lpz"
DESIGN_SHEET = "3rpDrEF"
D_DATE_FIELD = "日期"              # date: 毫秒时间戳
D_PASS_FIELD = "是否通过"          # singleSelect: 仅 '通过' 算通过
D_OWNER_FIELD = "设计人员"         # singleSelect

CACHE_TTL = 24 * 60 * 60  # 每日刷新一次，单位：秒
ERROR_COOLDOWN = 5 * 60  # 外部接口失败后的重试冷却，单位：秒

_cache: Dict[str, Any] = {"ts": {}, "records": {}, "errors": {}}
_cache_lock = threading.Lock()
_fetch_lock = threading.Lock()

# 部门整体雷达维度必须与岗位雷达维度一致：产品负责人一组、设计人员一组。
# 分组名称使用看板口径，前端会据此渲染两个独立雷达图。
_SUBJECTIVE = [
    SubjectiveEval(dimension="新品交付时效", score=83, comment="从立项到上线的全流程节奏稳定，仍可进一步压缩交付周期", trend="up", group="产品团队"),
    SubjectiveEval(dimension="交付准时率", score=79, comment="项目节点整体可控，需持续提升按期交付能力", trend="stable", group="产品团队"),
    SubjectiveEval(dimension="跨部门协同效率", score=76, comment="与运营、设计及供应链协作顺畅，信息同步仍需加强", trend="up", group="产品团队"),
    SubjectiveEval(dimension="新品储备深度", score=86, comment="新品储备和前期准备较充分，可持续支撑后续上线", trend="up", group="产品团队"),
    SubjectiveEval(dimension="市场趋势响应", score=81, comment="能够关注市场变化并推动需求落地，响应速度持续提升", trend="stable", group="产品团队"),
    SubjectiveEval(dimension="视觉转化力", score=83, comment="主图与详情页视觉表达清晰，对用户转化有较好支撑", trend="up", group="设计团队"),
    SubjectiveEval(dimension="视觉创意力", score=79, comment="具备稳定的创意产出能力，差异化表达仍可加强", trend="stable", group="设计团队"),
    SubjectiveEval(dimension="品牌视觉管理", score=76, comment="品牌视觉资产持续沉淀，多店铺一致性需要进一步提升", trend="up", group="设计团队"),
    SubjectiveEval(dimension="设计效率与规范", score=86, comment="设计交付节奏稳定，组件化和模板化规范较好", trend="up", group="设计团队"),
    SubjectiveEval(dimension="部门协同", score=81, comment="与运营、产品和视频团队沟通顺畅，需求响应及时", trend="stable", group="设计团队"),
]


def _fetch_records(base_id: str, sheet_id: str, force: bool = False) -> List[dict]:
    """拉取指定钉钉多维表全部记录。

    普通查询在 24 小时缓存内直接返回；force=True 仅由手动/定时同步使用。
    单飞锁保证缓存失效时并发请求不会同时打到钉钉接口。
    """
    now = time.time()
    with _cache_lock:
        cached = _cache["records"].get(sheet_id)
        if not force and cached is not None and now - _cache["ts"].get(sheet_id, 0) < CACHE_TTL:
            return cached
        last_error = _cache["errors"].get(sheet_id)
        if not force and last_error and now - last_error["ts"] < ERROR_COOLDOWN:
            raise RuntimeError(f"钉钉多维表暂时进入失败冷却，请稍后再试：{last_error['message']}")

    with _fetch_lock:
        # 等待其他请求完成后再次检查缓存，避免重复刷新。
        now = time.time()
        with _cache_lock:
            cached = _cache["records"].get(sheet_id)
            if not force and cached is not None and now - _cache["ts"].get(sheet_id, 0) < CACHE_TTL:
                return cached
            last_error = _cache["errors"].get(sheet_id)
            if not force and last_error and now - last_error["ts"] < ERROR_COOLDOWN:
                raise RuntimeError(f"钉钉多维表暂时进入失败冷却，请稍后再试：{last_error['message']}")

        try:
            client = DingTalkBitableClient()
            client.get_access_token()
            records: List[dict] = []
            token: Optional[str] = None
            while True:
                body: dict = {"pageSize": 500}
                if token:
                    body["nextToken"] = token
                r = client._request("POST", f"/bases/{base_id}/sheets/{sheet_id}/records/list", json=body)
                if isinstance(r, list):
                    records.extend(r)
                    break
                records.extend(r.get("records", r.get("value", [])))
                token = r.get("nextToken")
                if not r.get("hasMore") or not token:
                    break
                time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001 — 保留旧缓存并进入失败冷却
            with _cache_lock:
                _cache["errors"][sheet_id] = {"ts": time.time(), "message": str(exc)}
            raise

        with _cache_lock:
            _cache["records"][sheet_id] = records
            _cache["ts"][sheet_id] = time.time()
            _cache["errors"].pop(sheet_id, None)
        return records


def refresh_product_cache() -> dict:
    """强制刷新产品与设计两张钉钉表，供每日任务和手动同步调用。"""
    product_records = _fetch_records(PRODUCT_BASE, PRODUCT_SHEET, force=True)
    design_records = _fetch_records(DESIGN_BASE, DESIGN_SHEET, force=True)
    return {
        "product_records": len(product_records),
        "design_records": len(design_records),
        "record_count": len(product_records) + len(design_records),
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _parse_month(val: Any) -> Optional[int]:
    """日期值 → 月份 int。支持毫秒时间戳 / text "8月27日" / 'YYYY-MM-DD' / 'YYYY/MM/DD'。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val / 1000).month
        except (ValueError, OSError, OverflowError):
            return None
    s = str(val).strip()
    m = re.search(r"(\d{1,2})月", s)  # "8月27日"
    if m:
        return int(m.group(1))
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).month
        except (ValueError, AttributeError):
            continue
    m = re.search(r"(\d{4})[-/年](\d{1,2})", s)
    if m:
        return int(m.group(2))
    return None


def _extract_name(val: Any) -> str:
    """从 {'name': ...} / list / str 提取名称。"""
    if isinstance(val, dict):
        return str(val.get("name", "") or "")
    if isinstance(val, list):
        return "/".join(_extract_name(v) for v in val)
    return str(val) if val is not None else ""


def _channel_has_value(val: Any) -> bool:
    """当前已上线渠道是否有值（multipleSelect 可能为 list[dict] / dict / str）。"""
    if val is None:
        return False
    if isinstance(val, list):
        return any(_channel_has_value(v) for v in val)
    if isinstance(val, dict):
        return bool(val.get("name"))
    return str(val).strip() != ""


def _is_pass(val: Any) -> bool:
    """是否通过 == '通过'（企业自定义口径：仅'通过'算通过）。"""
    return _extract_name(val) == "通过"


def _roster_position(name: str) -> str:
    """查花名册真实岗位（钉钉 sys00-position，本地 Employee 表），查不到返回空串。

    产品/设计团队岗位以花名册为准（用户口径 2026-08-11）；多维表离职人员（如董晗悦）
    查不到岗位时由调用方回退原岗位名（产品负责人/设计人员）。
    """
    try:
        from database import SessionLocal
        from models import Employee
        db = SessionLocal()
        try:
            r = db.query(Employee).filter(Employee.name == name).first()
            return (r.position or "") if r else ""
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — 本地库异常不阻断多维表数据
        return ""


def _roster_active(name: str) -> bool:
    """花名册在职状态：查不到（多维表新成员，花名册尚未同步）→ 保留；已离职(is_active=no) → 过滤。

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
    except Exception:  # noqa: BLE001 — 本地库异常不阻断多维表数据
        return True


def _error_dept(msg: str) -> DeptEfficiency:
    """数据源不可用时的降级返回：不携带任何客观指标/成员。"""
    return DeptEfficiency(
        department="产品团队", team_size=0, score=None,
        metrics=[], members=[], subjective=_SUBJECTIVE,
        source="dingtalk", source_error=str(msg),
    )


def _parse_ts_date(val: Any) -> Optional[date]:
    """毫秒时间戳 → date。"""
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val / 1000).date()
        except (ValueError, OSError, OverflowError):
            return None
    return None


def _parse_text_date(val: Any, year: int) -> Optional[date]:
    """text 日期 → date。"8月27日"（补当年）/'YYYY-MM-DD'/'YYYY/MM/DD'。"""
    if val is None:
        return None
    s = str(val).strip()
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def member_daily(month: Optional[str], member: str) -> Optional[dict]:
    """某成员当月每日产出序列（真实数据，供抽屉上半部分图表渲染）。

    - 设计部成员：逐日统计 设计数/通过数（「设计每日稿件统计」每条带日期）
    - 产品负责人：按「预计上线日期」逐日统计 预计上线产品数（「产品全流程进度跟踪」）
    返回 None 表示当月无该成员记录。
    """
    if not member:
        return None
    if not month:
        month = date.today().strftime("%Y-%m")
    year, ym = (int(month.split("-")[0]), int(month.split("-")[1])) if "-" in month else (date.today().year, int(month))

    import calendar
    ndays = calendar.monthrange(year, ym)[1]
    days = list(range(1, ndays + 1))

    try:
        design_records = _fetch_records(DESIGN_BASE, DESIGN_SHEET)
        prod_records = _fetch_records(PRODUCT_BASE, PRODUCT_SHEET)
    except Exception as e:  # noqa: BLE001
        logger.error("每日产出数据拉取失败: %s", e)
        return None

    # ── 设计部：每日 设计数/通过数 ──
    d_series = {"设计数": [0] * ndays, "通过数": [0] * ndays}
    found = False
    for rec in design_records:
        fields = rec.get("fields", rec)
        if _extract_name(fields.get(D_OWNER_FIELD)) != member:
            continue
        d = _parse_ts_date(fields.get(D_DATE_FIELD))
        if d and d.year == year and d.month == ym:
            found = True
            d_series["设计数"][d.day - 1] += 1
            if _is_pass(fields.get(D_PASS_FIELD)):
                d_series["通过数"][d.day - 1] += 1
    if found:
        return {
            "group": "设计部", "title": "每日设计产出", "unit": "个", "days": days,
            "series": [
                {"name": "设计数", "type": "bar", "data": d_series["设计数"]},
                {"name": "通过数", "type": "line", "data": d_series["通过数"]},
            ],
        }

    # ── 产品部：每日预计上线分布 ──
    p_daily = [0] * ndays
    found = False
    for rec in prod_records:
        fields = rec.get("fields", rec)
        if _extract_name(fields.get(P_OWNER_FIELD)) != member:
            continue
        d = _parse_text_date(fields.get(P_DATE_FIELD), year)
        if d and d.year == year and d.month == ym:
            found = True
            p_daily[d.day - 1] += 1
    if found:
        return {
            "group": "产品部", "title": "每日预计上线分布", "unit": "个", "days": days,
            "series": [{"name": "预计上线", "type": "bar", "data": p_daily}],
        }
    return None


def build_product_dept(month: Optional[str] = None) -> DeptEfficiency:
    """构建产品团队人效数据（双维度：产品全流程进度 + 设计每日稿件，按看板设定月份统计）。"""
    if not month:
        month = date.today().strftime("%Y-%m")
    year, ym = (int(month.split("-")[0]), int(month.split("-")[1])) if "-" in month else (date.today().year, int(month))

    try:
        prod_records = _fetch_records(PRODUCT_BASE, PRODUCT_SHEET)
        design_records = _fetch_records(DESIGN_BASE, DESIGN_SHEET)
    except Exception as e:  # noqa: BLE001 — 接口异常降级，不拖垮看板
        logger.error("产品数据源不可用: %s", e)
        return _error_dept(f"钉钉多维表拉取失败：{e}")

    # ═══ 产品维度（离职人员不参与统计，与花名册同步）═══
    prod_target = prod_launched = 0
    prod_owner_stat: Dict[str, dict] = {}
    for rec in prod_records:
        fields = rec.get("fields", rec)
        owner = _extract_name(fields.get(P_OWNER_FIELD))
        if owner and not _roster_active(owner):
            continue  # 已离职，不显示在部门人效
        if _parse_month(fields.get(P_DATE_FIELD)) != ym:
            continue
        prod_target += 1
        has_channel = _channel_has_value(fields.get(P_CHANNEL_FIELD))
        if has_channel:
            prod_launched += 1
        if owner:
            st = prod_owner_stat.setdefault(owner, {"target": 0, "launched": 0})
            st["target"] += 1
            if has_channel:
                st["launched"] += 1

    # ═══ 设计维度（离职人员不参与统计，与花名册同步）═══
    design_n = design_pass = 0
    design_owner_stat: Dict[str, dict] = {}
    for rec in design_records:
        fields = rec.get("fields", rec)
        owner = _extract_name(fields.get(D_OWNER_FIELD))
        if owner and not _roster_active(owner):
            continue  # 已离职，不显示在部门人效
        if _parse_month(fields.get(D_DATE_FIELD)) != ym:
            continue
        design_n += 1
        passed = _is_pass(fields.get(D_PASS_FIELD))
        if passed:
            design_pass += 1
        if owner:
            st = design_owner_stat.setdefault(owner, {"design": 0, "passed": 0})
            st["design"] += 1
            if passed:
                st["passed"] += 1

    # ── 部门指标（6 项：产品 3 + 设计 3，均为用户定义口径，group 供前端分两行展示）──
    prod_rate = prod_launched / prod_target if prod_target else 0.0
    design_rate = design_pass / design_n if design_n else 0.0
    metrics = [
        DeptMetric(name="月度目标上线数", value=prod_target, unit="个", target=None, trend="stable", group="产品部"),
        DeptMetric(name="月度已上线数", value=prod_launched, unit="个", target=None, trend="stable", group="产品部"),
        DeptMetric(name="月度达成率", value=round(prod_rate * 100, 2), unit="%", target=None, trend="stable", group="产品部"),
        DeptMetric(name="月度设计数", value=design_n, unit="个", target=None, trend="stable", group="设计部"),
        DeptMetric(name="月度通过数", value=design_pass, unit="个", target=None, trend="stable", group="设计部"),
        DeptMetric(name="月度通过率", value=round(design_rate * 100, 2), unit="%", target=None, trend="stable", group="设计部"),
    ]

    # ── 成员明细：产品负责人 + 设计人员（岗位名以花名册 sys00-position 为准）──
    members: List[DeptMember] = []
    for owner, st in sorted(prod_owner_stat.items(), key=lambda x: -x[1]["target"]):
        o_rate = st["launched"] / st["target"] if st["target"] else 0.0
        members.append(DeptMember(
            name=owner,
            position=_roster_position(owner) or "产品负责人",
            score=round(o_rate * 100, 1),
            metrics=[
                MemberMetric(name="月度目标上线数", value=st["target"], unit="个"),
                MemberMetric(name="月度已上线数", value=st["launched"], unit="个"),
                MemberMetric(name="月度达成率", value=round(o_rate * 100, 2), unit="%"),
            ],
            evaluation=f"{year}年{ym}月 目标上线{st['target']}个，已上线{st['launched']}个，达成率{o_rate*100:.1f}%",
        ))
    for owner, st in sorted(design_owner_stat.items(), key=lambda x: -x[1]["design"]):
        o_rate = st["passed"] / st["design"] if st["design"] else 0.0
        members.append(DeptMember(
            name=owner,
            position=_roster_position(owner) or "设计人员",
            score=round(o_rate * 100, 1),
            metrics=[
                MemberMetric(name="月度设计数", value=st["design"], unit="个"),
                MemberMetric(name="月度通过数", value=st["passed"], unit="个"),
                MemberMetric(name="月度通过率", value=round(o_rate * 100, 2), unit="%"),
            ],
            evaluation=f"{year}年{ym}月 设计稿件{st['design']}份，通过{st['passed']}份，通过率{o_rate*100:.1f}%",
        ))

    # 综合评分：两维度率均值（无数据的维度不计入）
    rates = []
    if prod_target:
        rates.append(prod_rate)
    if design_n:
        rates.append(design_rate)
    score = round(sum(rates) / len(rates) * 100, 1) if rates else None

    return DeptEfficiency(
        department="产品团队",
        team_size=len(prod_owner_stat) + len(design_owner_stat),
        score=score,
        metrics=metrics,
        members=members,
        subjective=_SUBJECTIVE,
        source="dingtalk",
        source_error=None,
    )
