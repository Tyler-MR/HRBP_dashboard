"""FastAPI 主应用 — 仅在此区域改动（API 路由 + 模拟数据初始化）"""
import random
import calendar
import logging
import time
from datetime import date, timedelta, datetime
from typing import Optional, List, Dict, Any

import threading
from datetime import datetime as _dt
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
from models import Recruiter, Position, Candidate, Employee, HrEfficiency, TalentProfile, MemberScore, ManagerEvaluation, DailyLog
from schemas import (
    DashboardResponse, OverviewStats, FunnelData, FunnelStage,
    PositionStat, OfferStatusItem, OfferStatusData, RecruiterOutput,
    OfferReviewItem,
    ProgressItem, ProgressSummary,
    AttritionOverview, AttritionByDept, AttritionByReason, AttritionMonthly, AttritionByTenure, AttritionResponse,
    HrEfficiencyMonthly, HrEfficiencySummary, HrEfficiencyResponse,
    HrStaffStats, AgeDistribution, EducationDistribution, TenureDistribution, DeptHeadcount, EduFilterOption,
    MonthlyStaffTrend,
    DeptMetric, DeptEfficiency, DeptEfficiencyResponse,
    SubjectiveEval, DeptMember, MemberMetric,
    MemberScoreItem, MemberRadarResponse, MemberScoreSave, ManagerEvaluationSave, RadarDimInfo,
    TalentDimension, TalentRadarData, DeptTalentScore, TalentAnalysisResponse,
)

app = FastAPI(title="月度招聘看板 API", version="1.0.0")

# CORS — 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 初始化模拟数据 ====================
def init_demo_data():
    """初始化示例数据，仅首次运行无数据时执行"""
    db = SessionLocal()
    try:
        if db.query(Recruiter).count() > 0:
            return  # 已有数据，跳过

        # 招聘人员
        recruiters_data = [
            ("张琳", "招聘一组"),
            ("王浩", "招聘一组"),
            ("李婷", "招聘二组"),
            ("陈晨", "招聘二组"),
            ("刘洋", "招聘三组"),
        ]
        recruiters = []
        for name, dept in recruiters_data:
            r = Recruiter(name=name, department=dept)
            db.add(r)
            recruiters.append(r)
        db.flush()

        # 岗位
        positions_data = [
            ("高级前端工程师", "技术部", 3, recruiters[0].id),
            ("Java后端工程师", "技术部", 4, recruiters[1].id),
            ("产品经理", "产品部", 2, recruiters[2].id),
            ("UI设计师", "设计部", 2, recruiters[3].id),
            ("运营专员", "运营部", 3, recruiters[4].id),
            ("测试工程师", "质量部", 2, recruiters[0].id),
            ("数据分析师", "数据部", 2, recruiters[2].id),
            ("HRBP", "人力资源部", 1, recruiters[3].id),
        ]
        positions = []
        for name, dept, hc, rid in positions_data:
            p = Position(name=name, department=dept, headcount=hc, recruiter_id=rid)
            db.add(p)
            positions.append(p)
        db.flush()

        # 候选人 — 生成模拟数据
        first_names = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈",
                       "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许",
                       "何", "吕", "施", "张", "孔", "曹", "严", "华", "金", "魏"]
        last_names = ["伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
                      "勇", "艳", "杰", "婷", "明", "超", "秀英", "华", "平", "刚",
                      "桂英", "文", "鑫", "慧", "宇", "琳", "浩", "辉", "雪", "峰"]

        # 流程状态和对应人数
        status_chain = [
            ("简历初筛", 120),
            ("邀约面试", 95),
            ("到面", 75),
            ("初试通过", 50),
            ("复试通过", 35),
            ("发Offer", 30),
            ("已接收", 25),
            ("已到岗", 20),
            ("满7天", 18),
        ]

        today = date.today()
        candidate_id = 0
        for pos in positions:
            for _ in range(random.randint(8, 20)):
                name = random.choice(first_names) + random.choice(last_names)
                c = Candidate(name=name, position_id=pos.id, recruiter_id=pos.recruiter_id)

                # 随机决定该候选人走多远
                stage_idx = random.choices(
                    range(len(status_chain)),
                    weights=[5, 10, 15, 20, 20, 15, 10, 5, 3],
                    k=1
                )[0]
                current_status = status_chain[stage_idx][0]
                c.status = current_status

                # 按时间线填充各环节日期（倒推：最新环节最接近今天）
                total_days_back = {
                    0: random.randint(1, 10),
                    1: random.randint(3, 15),
                    2: random.randint(5, 20),
                    3: random.randint(10, 30),
                    4: random.randint(15, 35),
                    5: random.randint(20, 40),
                    6: random.randint(25, 45),
                    7: random.randint(30, 55),
                    8: random.randint(40, 65),
                }
                days_back = total_days_back.get(stage_idx, random.randint(1, 30))

                c.resume_received_date = today - timedelta(days=days_back + random.randint(0, 5))

                if stage_idx >= 1:
                    c.interview_invited_date = c.resume_received_date + timedelta(days=random.randint(1, 3))
                if stage_idx >= 2:
                    c.interview_attended_date = c.interview_invited_date + timedelta(days=random.randint(1, 2))
                if stage_idx >= 3:
                    c.first_round_date = c.interview_attended_date + timedelta(days=random.randint(1, 3))
                    c.first_round_pass = "pass"
                if stage_idx >= 4:
                    c.second_round_date = c.first_round_date + timedelta(days=random.randint(2, 5))
                    c.second_round_pass = "pass"
                if stage_idx >= 5:
                    c.offer_sent_date = c.second_round_date + timedelta(days=random.randint(1, 3))
                if stage_idx >= 6:
                    c.offer_accepted = "accepted"
                if stage_idx >= 7:
                    c.onboard_date = c.offer_sent_date + timedelta(days=random.randint(3, 7))
                if stage_idx >= 8:
                    c.retention_7day = "yes"

                # 记录部分"未通过"候选人
                if stage_idx == 3 and random.random() < 0.3:
                    c.first_round_pass = "fail"
                    c.status = "初试未通过"
                elif stage_idx == 4 and random.random() < 0.2:
                    c.second_round_pass = "fail"
                    c.status = "复试未通过"
                elif stage_idx == 6 and random.random() < 0.2:
                    c.offer_accepted = "rejected"
                    c.status = "拒绝Offer"
                elif stage_idx == 7 and random.random() < 0.15:
                    c.retention_7day = "no"
                    c.status = "未满7天离职"

                db.add(c)
                candidate_id += 1

        # 更新已入职人数
        for pos in positions:
            hired = db.query(Candidate).filter(
                Candidate.position_id == pos.id,
                Candidate.onboard_date.isnot(None),
            ).count()
            pos.hired_count = hired

        db.commit()
        print(f"✅ 初始化完成: {len(recruiters)} 名招聘人员, {len(positions)} 个岗位, {candidate_id} 名候选人")
    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败: {e}")
    finally:
        db.close()


def init_employees():
    """初始化在职员工数据"""
    db = SessionLocal()
    try:
        if db.query(Employee).count() > 0:
            return

        departments = ["技术部", "技术部", "技术部", "技术部", "技术部",
                       "产品部", "产品部", "设计部", "设计部", "设计部",
                       "运营部", "运营部", "运营部", "质量部", "质量部",
                       "数据部", "数据部", "人力资源部", "人力资源部",
                       "财务部", "财务部", "客服部", "客服部", "客服部",
                       "采购部", "千川部", "千川部", "行政部"]

        first_names = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈",
                       "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许",
                       "何", "吕", "施", "张", "孔", "曹", "严", "华"]
        last_names = ["伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
                      "勇", "艳", "杰", "婷", "明", "超", "华", "平", "刚",
                      "文", "鑫", "慧", "宇", "琳", "浩", "辉", "雪", "峰"]

        educations = ["高中/中专", "大专", "本科", "硕士", "博士"]
        edu_weights = [0.05, 0.25, 0.50, 0.18, 0.02]  # 本科为主

        employees_list = []
        for i, dept in enumerate(departments):
            name = random.choice(first_names) + random.choice(last_names)
            age = random.randint(21, 55)
            education = random.choices(educations, weights=edu_weights, k=1)[0]
            tenure = round(random.uniform(0.2, 12), 1)
            emp = Employee(
                name=name,
                department=dept,
                age=age,
                education=education,
                tenure_years=tenure,
                is_active="yes" if random.random() > 0.05 else "no",
                employee_status="试用" if random.random() < 0.15 else "正式",
            )
            db.add(emp)
            employees_list.append(emp)

        db.commit()
        active_count = sum(1 for e in employees_list if e.is_active == "yes")
        print(f"✅ 在职员工初始化完成: {len(employees_list)} 人（在职 {active_count} 人）")
    except Exception as e:
        db.rollback()
        print(f"❌ 员工初始化失败: {e}")
    finally:
        db.close()


def init_talent_profiles():
    """初始化人才评估数据"""
    from sqlalchemy.orm import Session
    db = SessionLocal()
    try:
        if db.query(TalentProfile).count() > 0:
            return
        employees = db.query(Employee).filter(Employee.is_active == "yes").all()
        dimensions = ["专业能力", "沟通协作", "创新能力", "执行力", "学习能力", "责任感"]
        positions = {
            "技术部": ["前端工程师","后端工程师","全栈工程师","技术主管","架构师"],
            "产品部": ["产品经理","产品助理","高级产品经理"],
            "设计部": ["UI设计师","平面设计师","包装设计师","美工"],
            "运营部": ["运营专员","运营主管","新媒体运营"],
            "质量部": ["测试工程师","QA主管"],
            "数据部": ["数据分析师","数据工程师"],
            "人力资源部": ["HRBP","招聘专员","HR经理"],
            "财务部": ["会计","财务主管","财务分析师"],
            "客服部": ["客服专员","客服主管","售后专员"],
            "千川部": ["千川运营","剪辑专员","投流专员"],
            "采购部": ["采购专员"],
            "行政部": ["行政专员","行政主管"],
        }
        for emp in employees:
            import random
            dept_positions = positions.get(emp.department, ["员工"])
            pos = random.choice(dept_positions)
            for dim in dimensions:
                # 基础分 + 随机波动，不同维度有一定差异
                base = random.randint(60, 95)
                score = max(30, min(100, base + random.randint(-10, 10)))
                db.add(TalentProfile(
                    employee_id=emp.id,
                    dimension=dim,
                    score=score,
                    period="2026-07",
                ))
        db.commit()
        print(f"✅ 人才评估数据初始化完成: {len(employees)} 名员工, 6 个维度")
    except Exception as e:
        db.rollback()
        print(f"❌ 人才数据初始化失败: {e}")
    finally:
        db.close()


def init_hr_efficiency_data():
    """初始化月度人效数据（模拟）"""
    db = SessionLocal()
    try:
        if db.query(HrEfficiency).count() > 0:
            return

        months = [
            "2024-01", "2024-02", "2024-03", "2024-04",
            "2024-05", "2024-06", "2024-07", "2024-08",
            "2024-09", "2024-10", "2024-11", "2024-12",
        ]

        # 模拟营收数据 — 逐年递增 + 季节性波动（电商618/双11等）
        revenue_base = [180, 165, 195, 210, 230, 380, 310, 290, 270, 320, 420, 480]
        headcount_base = [120, 122, 125, 128, 132, 138, 142, 145, 148, 150, 155, 158]

        for i, month in enumerate(months):
            revenue = round(revenue_base[i] + random.uniform(-10, 15), 1)
            headcount = headcount_base[i] + random.randint(-2, 3)

            # 净利润约为营收的12%-22%
            profit_margin = random.uniform(0.12, 0.22)
            net_profit = round(revenue * profit_margin, 1)

            # 人力成本：人均月成本约0.8-1.2万，逐渐增长
            avg_cost_per = round(random.uniform(0.82, 1.18) * (1 + i * 0.008), 2)
            total_labor_cost = round(avg_cost_per * headcount, 1)

            db.add(HrEfficiency(
                month=month,
                revenue=revenue,
                net_profit=net_profit,
                total_labor_cost=total_labor_cost,
                headcount=headcount,
            ))
        db.commit()
        print(f"✅ 人效数据初始化完成: 12 个月数据")
    except Exception as e:
        db.rollback()
        print(f"❌ 人效数据初始化失败: {e}")
    finally:
        db.close()


# ==================== API 路由 ====================

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # 以下初始化函数已废弃：数据改为通过钉钉API实时同步
    # init_demo_data()
    # init_employees()
    # init_talent_profiles()
    init_hr_efficiency_data()
    # 启动后台自动同步线程
    _start_auto_sync()


# ═══════════════════════════════════════════════════
# 后台自动同步（每日 00:05 从钉钉拉取业务数据）
# ═══════════════════════════════════════════════════

_sync_lock = threading.Lock()

def _seconds_until_daily_sync(hour: int = 0, minute: int = 5) -> float:
    """计算距离下一次每日同步时间的秒数，使用服务器本地时区。"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _auto_sync_loop():
    """后台线程：每日 00:05 同步招聘、花名册并预热在岗时长缓存。"""
    import time
    logger = logging.getLogger("auto_sync")
    while True:
        wait_seconds = _seconds_until_daily_sync()
        logger.info("下次钉钉自动同步将在约 %.0f 秒后执行（每日 00:05）", wait_seconds)
        time.sleep(wait_seconds)
        if not _sync_lock.acquire(blocking=False):
            logger.warning("手动同步尚未完成，跳过本次每日自动同步")
            continue
        try:
            logger.info("⏰ 开始自动同步招聘数据...")
            from dingtalk_bitable import sync_recruitment_data
            # 钉钉临时故障自动重试：整点限流(QpsLimitForApi)与服务端临时不可用(ServiceUnavailable)均等待后重试，最多 3 次
            result = None
            for attempt in range(3):
                try:
                    result = sync_recruitment_data()
                    break
                except Exception as e:
                    if any(k in str(e) for k in ["QpsLimitForApi", "ServiceUnavailable"]) and attempt < 2:
                        logger.warning("⚠️ 钉钉接口临时故障，%d 秒后重试 (%d/3): %s", 10 * (attempt + 1), attempt + 1, e)
                        time.sleep(10 * (attempt + 1))
                    else:
                        raise
            synced = result.get("synced", 0)
            logger.info("✅ 自动同步完成: %s 条面试记录", synced)
        except Exception as e:
            logger.exception("❌ 自动同步失败: %s", e)
        finally:
            _sync_lock.release()

        # ── 花名册同步（独立锁，离职状态与钉钉保持一致；失败不影响招聘同步）──
        try:
            from dingtalk_sync import sync_employees
            r = sync_employees()
            logger.info("✅ 花名册自动同步: %s 人 (message=%s)", r.get("synced", 0), r.get("message", ""))
        except Exception as e:
            logger.exception("❌ 花名册自动同步失败: %s", e)

        # 在岗时长采用独立缓存，凌晨完成一次强制刷新；前端普通查询只读缓存。
        try:
            from onduty_bi import refresh_onduty_cache
            r = refresh_onduty_cache()
            logger.info("✅ 在岗时长自动刷新: %s 条记录，周期=%s", r.get("record_count", 0), r.get("months", []))
        except Exception as e:
            logger.exception("❌ 在岗时长自动刷新失败: %s", e)

        # 产品/设计/拼多多打品人效采用独立 24 小时缓存，凌晨完成一次强制刷新。
        try:
            from product_bi import refresh_product_cache
            r = refresh_product_cache()
            from pdd_bi import refresh_pdd_product_cache
            pdd_r = refresh_pdd_product_cache()
            _clear_dept_metrics_cache()
            logger.info("✅ 产品/设计/拼多多打品人效自动刷新: 产品 %s 条、设计 %s 条、打品 %s 条",
                        r.get("product_records", 0), r.get("design_records", 0),
                        pdd_r.get("pdd_product_records", 0))
        except Exception as e:
            logger.exception("❌ 产品/设计/拼多多打品人效自动刷新失败: %s", e)

def _start_auto_sync():
    """在后台线程中启动自动同步"""
    thread = threading.Thread(target=_auto_sync_loop, daemon=True, name="auto-sync")
    thread.start()
    print("📌 后台自动同步已启动（每日 00:05）")


def _month_boundary(month: str):
    """将 'YYYY-MM' 转为 (month_start, month_end) 日期元组"""
    try:
        y, m = int(month[:4]), int(month[5:7])
        start = date(y, m, 1)
        _, last = calendar.monthrange(y, m)
        end = date(y, m, last)
        return start, end
    except:
        return None, None


def _year_boundary(year_str: str):
    """将 'YYYY' 转为 (year_start, year_end) 日期元组"""
    try:
        y = int(year_str.strip())
        return date(y, 1, 1), date(y, 12, 31)
    except:
        return None, None


def _build_hr_staff_stats(db: Session, edu_filter: Optional[str] = None, month: Optional[str] = None, period: str = "month") -> HrStaffStats:
    """构建人员结构统计数据。edu_filter='本科,硕士' 按学历筛选；month='YYYY-MM' 按该月末在岗快照统计（近似：无离职日期，历史月=当月前入职且当前在职）；period=month/quarter/half/year 趋势粒度。"""
    today = date.today()
    cur_month = today.strftime("%Y-%m")
    month = month or cur_month
    try:
        y, m = int(month.split("-")[0]), int(month.split("-")[1])
        month_end = date(y, m, calendar.monthrange(y, m)[1])
    except (ValueError, TypeError):
        month, y, m = cur_month, today.year, today.month
        month_end = today

    base_query = db.query(Employee).filter(Employee.is_active == "yes")
    if month != cur_month:
        # 历史月份快照（近似）：该月末前入职且当前仍在职
        base_query = base_query.filter(Employee.hired_date.isnot(None), Employee.hired_date <= month_end)

    # 试用期/转正人数（与总人数同一月度快照口径，不受学历筛选影响）
    all_active = base_query.all()
    probation_count = sum(1 for e in all_active if e.employee_status == "试用")
    regular_count = sum(1 for e in all_active if e.employee_status == "正式")

    # 学历筛选（仅影响分布图表，不影响总人数/转正/试用卡片）
    query = base_query
    if edu_filter:
        edu_list = [e.strip() for e in edu_filter.split(",") if e.strip()]
        if edu_list:
            query = query.filter(Employee.education.in_(edu_list))

    employees = query.all()
    total_active = len(employees)

    # 可用学历选项（所有在职员工）
    all_educations = db.query(Employee.education, func.count(Employee.id).label('cnt'))\
        .filter(Employee.is_active == "yes")\
        .group_by(Employee.education).all()
    available_educations = [EduFilterOption(level=edu, total=cnt) for edu, cnt in all_educations]

    # 年龄分布（基于筛选后的 employees）
    age_ranges = [("20-25", 0), ("26-30", 0), ("31-35", 0), ("36-40", 0),
                  ("41-45", 0), ("46-50", 0), ("50+", 0)]
    age_buckets = {
        (20, 25): "20-25", (26, 30): "26-30", (31, 35): "31-35",
        (36, 40): "36-40", (41, 45): "41-45", (46, 50): "46-50",
    }
    age_dist_map = {label: 0 for _, label in enumerate([r for r, _ in age_ranges])}
    for emp in employees:
        label = None
        for (lo, hi), lb in age_buckets.items():
            if lo <= emp.age <= hi:
                label = lb
                break
        if label is None and emp.age > 50:
            label = "50+"
        if label is None and emp.age < 20:
            label = "20-25"
        if label:
            age_dist_map[label] = age_dist_map.get(label, 0) + 1
    age_distribution = [AgeDistribution(range=k, count=v) for k, v in age_dist_map.items()]

    # 学历分布（基于筛选后的 employees）
    edu_map = {}
    for emp in employees:
        edu_map[emp.education] = edu_map.get(emp.education, 0) + 1
    education_distribution = [EducationDistribution(level=k, count=v) for k, v in
                              sorted(edu_map.items(),
                                     key=lambda x: ["高中/中专", "大专", "本科", "硕士", "博士"].index(x[0])
                                     if x[0] in ["高中/中专", "大专", "本科", "硕士", "博士"] else 99)]

    # 司龄分布（基于筛选后的 employees）
    tenure_ranges = [("0-1年", 0, 1), ("1-3年", 1, 3), ("3-5年", 3, 5),
                     ("5-10年", 5, 10), ("10年+", 10, 999)]
    tenure_map = {label: 0 for label, _, _ in tenure_ranges}
    for emp in employees:
        for label, lo, hi in tenure_ranges:
            if lo <= emp.tenure_years < hi:
                tenure_map[label] += 1
                break
    tenure_distribution = [TenureDistribution(range=k, count=v) for k, v in tenure_map.items()]

    # 各部门在职人数（基于筛选后的 employees，按一级部门归并）
    _DEPT_MAP = {
        # 二级 → 一级
        "拼多多组": "电商部", "淘天组": "电商部", "1688组": "电商部", "一类电商部": "电商部",
        "运营组": "千川部", "运营部": "千川部",
        "招聘组": "人力行政部",
        "发货组": "财务部",
        "剪辑组": "千川部", "拍摄组": "千川部", "千川运营": "千川部",
        "行政组": "人力行政部", "行政部": "人力行政部",
        "人力行政部": "人力行政部",
        "总经办,一类电商部": "总经办",
    }
    def _first_level(dept: str) -> str:
        return _DEPT_MAP.get(dept, dept)

    dept_map = {}
    for emp in employees:
        fl = _first_level(emp.department)
        dept_map[fl] = dept_map.get(fl, 0) + 1
    dept_headcount = [
        DeptHeadcount(department=k, count=v,
                      percentage=round(v / total_active * 100, 1) if total_active > 0 else 0)
        for k, v in sorted(dept_map.items(), key=lambda x: -x[1])
    ]

    # 月度趋势：近12个月（截至统计月）入职人数 + 月末在岗人数（当前月精确，历史月近似），按 period 粒度聚合
    month_points = []  # (YYYY-MM, hires, headcount)
    for i in range(11, -1, -1):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        start = date(yy, mm, 1)
        end = date(yy, mm, calendar.monthrange(yy, mm)[1])
        label = f"{yy}-{mm:02d}"
        hires = db.query(Employee).filter(
            Employee.hired_date >= start, Employee.hired_date <= end).count()
        if label == cur_month:
            headcount = db.query(Employee).filter(Employee.is_active == "yes").count()
        else:
            headcount = db.query(Employee).filter(
                Employee.is_active == "yes",
                Employee.hired_date.isnot(None),
                Employee.hired_date <= end,
            ).count()
        month_points.append((label, hires, headcount))

    def _period_key(ym: str) -> str:
        yy2, mm2 = ym.split("-")
        mi = int(mm2)
        if period == "quarter":
            return f"{yy2}-Q{(mi - 1) // 3 + 1}"
        if period == "half":
            return f"{yy2}-H{1 if mi <= 6 else 2}"
        if period == "year":
            return yy2
        return ym

    groups: dict = {}
    for ym, hires, headcount in month_points:
        key = _period_key(ym)
        g = groups.setdefault(key, {"hires": 0, "headcount": headcount})
        g["hires"] += hires
        g["headcount"] = headcount  # 期末在岗 = 该粒度最后一个月
    monthly_trend = [MonthlyStaffTrend(month=k, hires=g["hires"], headcount=g["headcount"])
                     for k, g in groups.items()]

    return HrStaffStats(
        total_active=total_active,
        probation_count=probation_count,
        regular_count=regular_count,
        age_distribution=age_distribution,
        education_distribution=education_distribution,
        tenure_distribution=tenure_distribution,
        dept_headcount=dept_headcount,
        available_educations=available_educations,
        month=month,
        monthly_trend=monthly_trend,
    )


@app.get("/api/dashboard", response_model=DashboardResponse)
def get_dashboard(view_type: str = 'monthly', month: Optional[str] = None, year: Optional[str] = None, edu_filter: Optional[str] = None, staff_period: str = Query("month", description="人员结构趋势粒度 month/quarter/half/year"), db: Session = Depends(get_db)):
    """获取看板全部数据。view_type='monthly'/'yearly', 缺省为当月"""
    today = date.today()

    if view_type == 'yearly':
        y = year or str(today.year)
        ms, me = _year_boundary(y)
        if ms is None:
            ms, me = date(today.year, 1, 1), date(today.year, 12, 31)
    else:
        if month:
            ms, me = _month_boundary(month)
            if ms is None:
                ms, me = today.replace(day=1), today
        else:
            ms, me = today.replace(day=1), today

    # 无数据自动回退：请求范围无任何面试记录时，回退到最近有数据的月份
    has_data = db.query(Candidate).filter(
        Candidate.resume_received_date >= ms,
        Candidate.resume_received_date <= me,
        Candidate.resume_received_date.isnot(None),
    ).first()
    if not has_data and view_type != 'yearly':
        latest = db.query(Candidate.resume_received_date).filter(
            Candidate.resume_received_date.isnot(None)
        ).order_by(Candidate.resume_received_date.desc()).first()
        if latest and latest[0]:
            ms, me = _month_boundary(latest[0].strftime('%Y-%m'))

    mf = (Candidate.resume_received_date >= ms) & (Candidate.resume_received_date <= me)
    # 试岗日期月份过滤（已到岗=试岗日期在当月）
    omf = (Candidate.onboard_date >= ms) & (Candidate.onboard_date <= me)

    # 1. 概览统计
    total_resumes = db.query(Candidate).filter(
        mf, Candidate.resume_received_date.isnot(None)
    ).count()

    total_invited = db.query(Candidate.name).filter(
        mf, Candidate.resume_received_date.isnot(None)
    ).distinct().count()

    total_interviews = db.query(Candidate.name).filter(
        mf, Candidate.interview_attended_date.isnot(None)
    ).distinct().count()  # 到面量=姓名去重（与漏斗邀约面试口径一致，防同名多记录虚高）

    first_round_passes = db.query(Candidate).filter(
        mf, Candidate.first_round_pass == "pass"
    ).count()

    second_round_passes = db.query(Candidate).filter(
        mf, Candidate.second_round_pass == "pass"
    ).count()

    offers_sent = db.query(Candidate).filter(
        mf, Candidate.offer_sent_date.isnot(None)
    ).count()

    offers_accepted = db.query(Candidate).filter(
        mf, Candidate.offer_accepted == "accepted"
    ).count()

    onboarded = db.query(Candidate.name).filter(
        omf, Candidate.onboard_date.isnot(None)
    ).distinct().count()

    retention_7day = db.query(Candidate.name).filter(
        omf, Candidate.retention_7day == "yes"
    ).distinct().count()

    active_positions = db.query(Position).count()

    overview = OverviewStats(
        total_resumes=total_resumes,
        total_invited=total_invited,
        total_interviews=total_interviews,
        first_round_passes=first_round_passes,
        second_round_passes=second_round_passes,
        offers_sent=offers_sent,
        offers_accepted=offers_accepted,
        onboarded=onboarded,
        retention_7day=retention_7day,
        active_positions=active_positions,
    )

    # 2. 漏斗数据
    # 邀约面试 = 到面日期在当月，按姓名去重（钉钉源数据无邀约日期字段，统一用去重到面口径）
    funnel_invited = db.query(Candidate.name).filter(
        mf, Candidate.resume_received_date.isnot(None)
    ).distinct().count()
    funnel_stages = [
        FunnelStage(name="邀约面试", value=funnel_invited),
        FunnelStage(name="初试通过", value=first_round_passes),
        FunnelStage(name="复试通过", value=second_round_passes),
        FunnelStage(name="已接收", value=offers_accepted),
        FunnelStage(name="已到岗", value=onboarded),
        FunnelStage(name="满7天", value=retention_7day),
    ]
    for i in range(1, len(funnel_stages)):
        prev = funnel_stages[i - 1].value
        funnel_stages[i].rate = round(funnel_stages[i].value / prev * 100, 1) if prev > 0 else 0.0

    funnel = FunnelData(stages=funnel_stages)

    # 3. 岗位明细
    positions_list = []

    # 预读取试岗信息（新表「人事招聘源数据」已合并试岗数据，直接读本地库）
    _prob_trial_names = set()
    _prob_hired_names = set()
    _prob_all_names = set()
    try:
        # 入职（满7天）= retention_7day == "yes"
        for (n,) in db.query(Candidate.name).filter(
            Candidate.retention_7day == "yes"
        ).all():
            _prob_hired_names.add(n)
        # 试岗中 = 有试岗日期(onboard_date) 但未满7天
        for (n,) in db.query(Candidate.name).filter(
            Candidate.onboard_date.isnot(None)
        ).all():
            _prob_all_names.add(n)
            if n not in _prob_hired_names:
                _prob_trial_names.add(n)
    except Exception:
        pass

    for pos in db.query(Position).all():
        # 到面 = interview_attended_date not null
        interviews = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.interview_attended_date.isnot(None)
        ).distinct().count()
        if interviews == 0:
            continue  # 只展示当月有到面的岗位

        # 初试 = first_round_pass == "pass"
        first_passes = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.first_round_pass == "pass"
        ).distinct().count()

        # 复试 = second_round_pass == "pass"
        second_passes = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.second_round_pass == "pass"
        ).distinct().count()

        # offer接受 = offer_accepted == "accepted"
        off_accepted = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.offer_accepted == "accepted"
        ).distinct().count()

        # 入职 = retention_7day == "yes"（试岗记录表结果=入职）
        retention_pos = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.retention_7day == "yes"
        ).distinct().count()

        # 试岗 = 当月有到面的候选人中，姓名在试岗记录表结果=试岗中的
        trial_pos = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.name.in_(list(_prob_trial_names)) if _prob_trial_names else False
        ).distinct().count()

        # 复试通过率 = 复试="通过" / 复试总行数
        second_total = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.second_round_pass.isnot(None)
        ).distinct().count()
        pass_rate = round(second_passes / second_total * 100, 1) if second_total > 0 else 0.0
        fill_rate = round(pos.hired_count / pos.headcount * 100, 1) if pos.headcount > 0 else 0
        offer_accept_rate = round(off_accepted / second_passes * 100, 1) if second_passes > 0 else 0.0
        # 入职率 = 结果列中的入职 / 结果列总行
        trial_total = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.name.in_(list(_prob_all_names)) if _prob_all_names else False
        ).distinct().count()
        onboard_rate = round(retention_pos / trial_total * 100, 1) if trial_total > 0 else 0.0

        positions_list.append(PositionStat(
            id=pos.id, name=pos.name, department=pos.department,
            headcount=pos.headcount,
            到面=interviews, 初试=first_passes, 复试=second_passes,
            复试通过率=pass_rate,
            offer接受=off_accepted, offer接受率=offer_accept_rate,
            试岗=trial_pos,
            入职=retention_pos, 入职率=onboard_rate,
            recruiter_name=None, fill_rate=fill_rate,
        ))

    # 4. Offer 状态
    sent_count = db.query(Candidate).filter(mf, Candidate.offer_sent_date.isnot(None)).count()
    rejected_count = db.query(Candidate).filter(mf, Candidate.offer_accepted == "rejected").count()
    offer_status = OfferStatusData(items=[
        OfferStatusItem(status="已发送", count=sent_count),
        OfferStatusItem(status="已接收", count=offers_accepted),
        OfferStatusItem(status="已拒绝", count=rejected_count),
    ])

    # 5. 招聘人员产出
    recruiters_list = []
    for rec in db.query(Recruiter).all():
        resumes_handled = db.query(Candidate.name).filter(
            mf, Candidate.recruiter_id == rec.id
        ).distinct().count()
        interviews_arranged = db.query(Candidate.name).filter(
            mf, Candidate.recruiter_id == rec.id,
            Candidate.interview_attended_date.isnot(None)
        ).distinct().count()
        if resumes_handled == 0:
            continue  # 只展示当月有活动的招聘人员
        hires = db.query(Candidate.name).filter(
            omf, Candidate.recruiter_id == rec.id,
            Candidate.onboard_date.isnot(None)
        ).distinct().count()
        accepted = db.query(Candidate.name).filter(
            mf, Candidate.recruiter_id == rec.id,
            Candidate.offer_accepted == "accepted"
        ).distinct().count()
        accept_rate = round(accepted / interviews_arranged * 100, 1) if interviews_arranged > 0 else 0
        recruiters_list.append(RecruiterOutput(
            id=rec.id,
            name=rec.name,
            department=rec.department,
            resumes_handled=resumes_handled,
            interviews_arranged=interviews_arranged,
            hires=hires,
            offer_accept_rate=accept_rate,
        ))

    # 6. 复试通过及Offer复盘明细 — 动态计算
    offer_review = []
    for pos in db.query(Position).all():
        second_p = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.second_round_pass == "pass"
        ).distinct().count()
        off_accept = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.offer_accepted == "accepted"
        ).distinct().count()
        off_decline = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.offer_accepted == "rejected"
        ).distinct().count()
        in_prog = db.query(Candidate.name).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.offer_accepted == "accepted",
            Candidate.onboard_date.is_(None)
        ).distinct().count()
        if second_p == 0 and off_accept == 0 and off_decline == 0:
            continue

        # 收集放弃原因
        rej_candidates = db.query(Candidate.decline_reason).filter(
            mf, Candidate.position_id == pos.id,
            Candidate.offer_accepted == "rejected",
            Candidate.decline_reason.isnot(None),
            Candidate.decline_reason != ""
        ).all()
        reasons = [r[0] for r in rej_candidates if r[0]]
        combined_reason = "；".join(reasons) if reasons else ""

        offer_review.append(OfferReviewItem(
            department=pos.department, position=pos.name,
            second_round_passes=second_p,
            offers_accepted=off_accept,
            offers_declined=off_decline,
            in_progress=in_prog,
            decline_reason=combined_reason,
        ))

    # 合计行
    total_second = sum(i.second_round_passes for i in offer_review)
    total_accept = sum(i.offers_accepted for i in offer_review)
    total_decline = sum(i.offers_declined for i in offer_review)
    total_prog = sum(i.in_progress for i in offer_review)
    offer_review.append(OfferReviewItem(
        department="", position="合计",
        second_round_passes=total_second,
        offers_accepted=total_accept,
        offers_declined=total_decline,
        in_progress=total_prog,
        decline_reason="",
    ))

    # 7. 招聘达成进度一览 — 目标数据 + 动态实际值
    _progress_defs = [
        ("一类电商部", "拼多多资深运营/基础运营", 6, 3),
        ("一类电商部", "拼多多运营主管", 2, 1),
        ("财务部", "AI+自动化技术师", 2, 1),
        ("财务部", "财务主管", 2, 1),
        ("设计部", "美工提示词优化师", 4, 2),
        ("设计部", "包装设计", 2, 2),
        ("产品部", "项目经理", 2, 1),
        ("千川部", "剪辑专员", 4, 2),
        ("千川部", "千川运营", 2, 1),
        ("采购部", "资深采购", 2, 1),
        ("人力行政部", "招聘经理/人力经理", 2, 1),
    ]
    progress_items = []
    for dept, pos_name, target_int, target_onb in _progress_defs:
        # 按部门+岗位名匹配候选人（通过 Position 关联）
        pos_ids = [p[0] for p in db.query(Position.id).filter(Position.department.like(f'%{dept}%')).all()]
        if not pos_ids:
            pos_ids = [-1]

        # 实际面试通过 = second_round_pass == "pass"
        actual_int = db.query(Candidate.name).filter(
            mf, Candidate.position_id.in_(pos_ids),
            Candidate.second_round_pass == "pass"
        ).distinct().count()

        # 实际试岗/入职
        actual_prob = db.query(Candidate.name).filter(
            mf, Candidate.position_id.in_(pos_ids),
            Candidate.retention_7day == "yes"
        ).distinct().count()

        # 试岗中
        prob_ing = db.query(Candidate.name).filter(
            mf, Candidate.position_id.in_(pos_ids),
            Candidate.name.in_(list(_prob_trial_names)) if _prob_trial_names else False
        ).distinct().count()

        # 满7天
        ret_7 = db.query(Candidate.name).filter(
            mf, Candidate.position_id.in_(pos_ids),
            Candidate.retention_7day == "yes"
        ).distinct().count()

        progress_items.append(ProgressItem(
            department=dept, position=pos_name,
            target_interview=target_int, actual_interview=actual_int,
            target_onboarding=target_onb, actual_probation=actual_prob,
            probationing=prob_ing, retention_7day=ret_7,
        ))
    _sum = lambda k: sum(getattr(i, k) for i in progress_items)
    progress_summary = ProgressSummary(
        target_interview=_sum('target_interview'),
        actual_interview=_sum('actual_interview'),
        target_onboarding=_sum('target_onboarding'),
        actual_probation=_sum('actual_probation'),
        probationing=_sum('probationing'),
        retention_7day=_sum('retention_7day'),
        interview_rate=round(_sum('actual_interview') / _sum('target_interview') * 100, 1) if _sum('target_interview') > 0 else 0.0,
        probation_rate=round(_sum('actual_probation') / _sum('target_onboarding') * 100, 1) if _sum('target_onboarding') > 0 else 0.0,
    )

    # 8. 人员结构（在职员工统计，按月快照，趋势按粒度）
    hr_staff = _build_hr_staff_stats(db, edu_filter=edu_filter, month=month, period=staff_period)

    return DashboardResponse(
        overview=overview,
        funnel=funnel,
        positions=positions_list,
        offer_status=offer_status,
        recruiters=recruiters_list,
        offer_review=offer_review,
        progress_items=progress_items,
        progress_summary=progress_summary,
        hr_staff=hr_staff,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.get("/api/health")
def health():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ==================== 人效数据看板 API ====================

@app.get("/api/hr-efficiency", response_model=HrEfficiencyResponse)
def get_hr_efficiency(period: str = Query("month", description="month/quarter/half/year 聚合粒度"), db: Session = Depends(get_db)):
    """获取人效数据，支持 月度/季度/半年度/年度 聚合（营收/成本/利润求和，在岗人数取均值，人均指标重算）。"""
    records = db.query(HrEfficiency).order_by(HrEfficiency.month).all()

    def _agg(recs):
        rev = sum(r.revenue for r in recs)
        profit = sum(r.net_profit for r in recs)
        labor = sum(r.total_labor_cost for r in recs)
        hc = sum(r.headcount for r in recs) / len(recs) if recs else 0
        return rev, profit, labor, hc

    def _item(key, rev, profit, labor, hc):
        return HrEfficiencyMonthly(
            month=key, label=key,
            revenue=round(rev, 1), net_profit=round(profit, 1),
            total_labor_cost=round(labor, 1), headcount=round(hc, 1),
            revenue_per_employee=round(rev / hc, 2) if hc > 0 else 0,
            cost_per_employee=round(labor / hc, 2) if hc > 0 else 0,
            profit_per_employee=round(profit / hc, 2) if hc > 0 else 0,
            cost_efficiency=round(rev / labor, 2) if labor > 0 else 0,
        )

    monthly = []
    if period == "month":
        for rec in records:
            monthly.append(_item(rec.month, rec.revenue, rec.net_profit, rec.total_labor_cost, rec.headcount))
    else:
        groups: dict = {}
        for rec in records:
            y, m = rec.month.split("-")
            mi = int(m)
            if period == "quarter":
                key = f"{y}-Q{(mi - 1) // 3 + 1}"
            elif period == "half":
                key = f"{y}-H{1 if mi <= 6 else 2}"
            else:  # year
                key = y
            groups.setdefault(key, []).append(rec)
        for key in sorted(groups):
            monthly.append(_item(key, *_agg(groups[key])))

    # 汇总（年度口径：各聚合项求和=全年，在岗取均值）
    if monthly:
        total_rev = sum(m.revenue for m in monthly)
        total_profit = sum(m.net_profit for m in monthly)
        total_labor = sum(m.total_labor_cost for m in monthly)
        avg_hc = sum(m.headcount for m in monthly) / len(monthly)
        summary = HrEfficiencySummary(
            total_revenue=round(total_rev, 1),
            total_net_profit=round(total_profit, 1),
            total_labor_cost=round(total_labor, 1),
            avg_headcount=round(avg_hc, 0),
            avg_revenue_per_employee=round(total_rev / avg_hc, 2) if avg_hc > 0 else 0,
            avg_cost_per_employee=round(total_labor / avg_hc, 2) if avg_hc > 0 else 0,
            avg_profit_per_employee=round(total_profit / avg_hc, 2) if avg_hc > 0 else 0,
            avg_cost_efficiency=round(total_rev / total_labor, 2) if total_labor > 0 else 0,
        )
    else:
        summary = None

    return HrEfficiencyResponse(monthly=monthly, summary=summary)


# ==================== 离职分析 API ====================

def _gen_attrition_data(view_type: str, db: Session):
    """生成离职分析模拟数据"""
    today = date.today()

    if view_type == "yearly":
        ms, me = date(today.year, 1, 1), date(today.year, 12, 31)
        label = f"{today.year}年"
    else:
        ms, me = date(today.year, today.month, 1), today
        label = f"{today.year}年{today.month}月"

    total_hc = db.query(Employee).count() or 200
    period_hc = db.query(Employee).filter(Employee.hire_date.between(ms, me) if hasattr(Employee, 'hire_date') else True).count()
    total_hc = max(total_hc, 200)

    # 模拟数据
    leavers_map = {
        "技术部": 3, "产品部": 2, "设计部": 2, "运营部": 2,
        "质量部": 1, "数据部": 1, "人力资源部": 1, "财务部": 1,
        "客服部": 3, "采购部": 1, "千川部": 2, "行政部": 1,
    }
    if view_type == "yearly":
        leavers_map = {k: v * 3 + random.randint(0, 2) for k, v in leavers_map.items()}

    total_leavers = sum(leavers_map.values())
    voluntary = int(total_leavers * 0.7)
    involuntary = total_leavers - voluntary

    by_dept = [
        AttritionByDept(department=dept, leavers=n, headcount=max(total_hc // 12, 5),
                        rate=round(n / max(total_hc // 12, 5) * 100, 1))
        for dept, n in sorted(leavers_map.items(), key=lambda x: -x[1])
    ]

    reasons = [
        ("薪资不满意", int(total_leavers * 0.3)),
        ("职业发展受限", int(total_leavers * 0.2)),
        ("家庭/个人原因", int(total_leavers * 0.15)),
        ("工作环境不适应", int(total_leavers * 0.1)),
        ("找到其他工作", int(total_leavers * 0.15)),
        ("合同到期不续签", int(total_leavers * 0.1)),
    ]
    reason_total = sum(r[1] for r in reasons)
    by_reason = [
        AttritionByReason(reason=r, count=c, percentage=round(c / total_leavers * 100, 1))
        for r, c in reasons
    ]

    # 离职周期（司龄段）
    tenure_data = [
        ("7天内", int(total_leavers * 0.08)),
        ("1个月内", int(total_leavers * 0.15)),
        ("3个月内", int(total_leavers * 0.20)),
        ("6个月内", int(total_leavers * 0.22)),
        ("1年内",   int(total_leavers * 0.15)),
        ("2年内",   int(total_leavers * 0.10)),
        ("3-5年内", int(total_leavers * 0.07)),
        ("5年以上", total_leavers - sum(int(total_leavers * r) for _, r in
            [("7天内",0.08),("1个月内",0.15),("3个月内",0.20),("6个月内",0.22),("1年内",0.15),("2年内",0.10),("3-5年内",0.07)])),
    ]
    by_tenure = [
        AttritionByTenure(range=r, count=c, percentage=round(c / total_leavers * 100, 1))
        for r, c in tenure_data
    ]

    if view_type == "monthly":
        monthly_trend = []
        for i in range(6):
            m = today.month - (6 - 1 - i)
            y = today.year
            if m <= 0:
                m += 12
                y -= 1
            monthly_trend.append(AttritionMonthly(
                month=f"{y}-{m:02d}",
                leavers=random.randint(2, 8),
                rate=round(random.uniform(1.0, 4.0), 1),
            ))
    else:
        monthly_trend = []
        for i in range(12):
            m = i + 1
            monthly_trend.append(AttritionMonthly(
                month=f"{today.year}-{m:02d}",
                leavers=random.randint(1, 6),
                rate=round(random.uniform(1.0, 5.0), 1),
            ))

    overview = AttritionOverview(
        total_leavers=total_leavers,
        voluntary=voluntary,
        involuntary=involuntary,
        attrition_rate=round(total_leavers / total_hc * 100, 1),
        headcount=total_hc,
    )

    return AttritionResponse(
        overview=overview,
        by_dept=by_dept,
        by_reason=by_reason,
        by_tenure=by_tenure,
        monthly_trend=monthly_trend,
        view_type=view_type,
        label=label,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.get("/api/attrition", response_model=AttritionResponse)
def get_attrition(view_type: str = "monthly", db: Session = Depends(get_db)):
    """获取离职分析数据"""
    return _gen_attrition_data(view_type, db)


# ==================== 部门人效 API ====================

def _apply_member_radar_scores_legacy(depts):
    """成员评分 = 个人人才雷达图**当前维度体系** 5 维合计分（用户口径：合计，非均值）。

    - 只聚合该成员当前维度（_member_radar_dims）下的评分，历史旧维度分（如默认
      \"人才质量/财务产出\"）不再计入，避免口径混杂与失真放大。
    - 已评分成员：score = Σ(5维分)，score_max = 单维满分×5 = 100。
    - 未评分成员：保留数据源原始分，score_max 统一为 100。"""
    from database import SessionLocal
    from models import MemberScore
    db = SessionLocal()
    try:
        rows = db.query(MemberScore).all()
    except Exception:  # noqa: BLE001 — 本地库异常保留原分
        db.close()
        return depts
    db.close()
    acc: dict = {}
    for r in rows:
        if r.score is None:
            continue
        acc.setdefault((r.department, r.member_name), {})[r.dimension] = r.score
    for dept in depts:
        for m in dept.members:
            dims = _member_radar_dims(dept.department, m.name, m.position)
            vals = [acc.get((dept.department, m.name), {}).get(d) for d in dims]
            vals = [v for v in vals if v is not None]
            if vals:
                m.score = round(sum(vals), 1)  # 5 维合计分（非均值）
                m.score_max = _member_radar_max(dept.department, m.name, m.position) * 5
    return depts


# 部门人效响应 60s TTL 缓存（产品/设计钉钉表另有 24 小时缓存；
# 这里仅用于保护 MySQL/本地计算，前端不再轮询）
_dept_metrics_cache: Dict[str, Any] = {"ts": {}, "data": {}}
_DEPT_METRICS_CACHE_TTL = 60


def _clear_dept_metrics_cache():
    """清除部门人效响应缓存，让手动/定时同步后的首次查询重算。"""
    _dept_metrics_cache["ts"].clear()
    _dept_metrics_cache["data"].clear()


def _apply_manager_evaluations(depts):
    """把已保存的直属上级主观评价覆盖到部门成员卡片。"""
    db = SessionLocal()
    try:
        rows = db.query(ManagerEvaluation).all()
    except Exception:  # noqa: BLE001 - 评价表不存在或数据库异常时保留默认内容
        db.close()
        return depts
    db.close()

    saved = {(row.department, row.member_name): row.evaluation or "" for row in rows}
    for dept in depts:
        for member in dept.members:
            key = (dept.department, member.name)
            if key in saved:
                # 空字符串也是有意清空，不能回退到代码内置的旧评价。
                member.manager_evaluation = saved[key]
    return depts


def _hr_team_members():
    """人力团队成员：花名册真实人员（部门=招聘组/行政组/人力行政部，在职）。

    归组：招聘组→position=招聘人员；行政组/人力行政部→行政人员。
    未接入真实数据时返回空列表（不编造占位成员）。"""
    from database import SessionLocal
    from models import Employee
    from datetime import date
    db = SessionLocal()
    try:
        rows = db.query(Employee).filter(
            Employee.is_active == "yes",
            Employee.department.in_(["招聘组", "行政组", "人力行政部"]),
        ).order_by(Employee.department).all()
        members = []
        for r in rows:
            group = "招聘人员" if r.department == "招聘组" else "行政人员"
            status = r.employee_status or "正式"
            days = 0
            if r.hired_date:
                days = max(0, (date.today() - r.hired_date).days)
            ev = f"{r.department} · {status}"
            if r.hired_date:
                ev += f" · {r.hired_date}入职"
            members.append(DeptMember(
                name=r.name,
                position=r.position or group,  # 钉钉真实岗位（sys00-position），空值回退组名
                score=0.0,  # 未评分，抽屉内由 MemberScore 覆盖
                metrics=[
                    MemberMetric(name="司龄", value=round(r.tenure_years or 0, 1), unit="年"),
                    MemberMetric(name="在职天数", value=days, unit="天"),
                ],
                evaluation=ev,
            ))
        return members
    except Exception:  # noqa: BLE001 — 本地库异常返回空成员，不编造
        return []
    finally:
        db.close()


def _procurement_team_members():
    """采购团队成员：花名册真实人员（部门=采购部，在职），不编造占位。"""
    from database import SessionLocal
    from models import Employee
    from datetime import date
    manager_evaluations = {
        "赵艺乐": "责任心、执行力均可，结果反馈效率高，但自驱力较弱。",
        "樊亚楠": "主观能动性、学习力、结果交付、执行力、责任心均可；专业度需持续提升，工厂沟通管理需持续提升；细节性处理较完善，但业务全链路管控、考虑问题全面性欠缺。",
        "张琳辉": "业务全链路熟悉，数据汇总及问题分析有深度，逻辑思维较强；自驱力一般，责任心一般。",
        "张永伟": "责任心可；逻辑思维能力欠缺，业务全局把控表现一般，统筹协作及工厂沟通管理表现一般。",
    }
    db = SessionLocal()
    try:
        rows = db.query(Employee).filter(
            Employee.is_active == "yes", Employee.department == "采购部",
        ).order_by(Employee.hired_date).all()
        members = []
        for r in rows:
            status = r.employee_status or "正式"
            days = max(0, (date.today() - r.hired_date).days) if r.hired_date else 0
            ev = f"采购部 · {status}" + (f" · {r.hired_date}入职" if r.hired_date else "")
            members.append(DeptMember(
                name=r.name,
                position=r.position or "采购人员",  # 钉钉真实岗位（sys00-position），空值回退
                score=0.0,  # 未评分，抽屉内由 MemberScore 覆盖
                metrics=[
                    MemberMetric(name="司龄", value=round(r.tenure_years or 0, 1), unit="年"),
                    MemberMetric(name="在职天数", value=days, unit="天"),
                ],
                evaluation=ev,
                manager_evaluation=manager_evaluations.get(r.name, ""),
            ))
        return members
    except Exception:  # noqa: BLE001 — 本地库异常返回空成员，不编造
        return []
    finally:
        db.close()


def _roster_dept_members(departments, position):
    """通用：花名册真实人员成员卡片（部门∈departments 且在职），不编造占位。

    与 _procurement_team_members/_hr_team_members 同款：指标=司龄/在职天数，
    evaluation=部门·状态·入职日期，score=0（未评分，抽屉内由 MemberScore 覆盖）。
    position: 无钉钉岗位时的回退岗位名（如"客服人员"/"财务人员"）。
    """
    from database import SessionLocal
    from models import Employee
    from datetime import date
    db = SessionLocal()
    try:
        rows = db.query(Employee).filter(
            Employee.is_active == "yes",
            Employee.department.in_(departments),
        ).order_by(Employee.hired_date).all()
        members = []
        for r in rows:
            status = r.employee_status or "正式"
            days = max(0, (date.today() - r.hired_date).days) if r.hired_date else 0
            ev = f"{r.department} · {status}" + (f" · {r.hired_date}入职" if r.hired_date else "")
            members.append(DeptMember(
                name=r.name,
                position=r.position or position,  # 钉钉真实岗位（sys00-position），空值回退
                score=0.0,  # 未评分，抽屉内由 MemberScore 覆盖
                metrics=[
                    MemberMetric(name="司龄", value=round(r.tenure_years or 0, 1), unit="年"),
                    MemberMetric(name="在职天数", value=days, unit="天"),
                ],
                evaluation=ev,
            ))
        return members
    except Exception:  # noqa: BLE001 — 本地库异常返回空成员，不编造
        return []
    finally:
        db.close()


def _customer_service_team_members():
    """客服团队成员：花名册真实人员（部门=客服部，在职），不编造占位。"""
    return _roster_dept_members(["客服部"], "客服人员")


def _finance_team_members():
    """财务团队成员：财务部 + 发货组在职人员，按财务岗位标签展示。"""
    # 财务看板口径：谢辉不纳入财务团队展示（保留花名册原始记录，不影响其他模块）。
    members = [
        member for member in _roster_dept_members(["财务部", "发货组"], "财务人员")
        if member.name != "谢辉"
    ]
    for member in members:
        role = FINANCE_MEMBER_ROLE.get(member.name)
        if not role:
            continue
        # 花名册中的发货组岗位名保留在来源字段中，但财务看板统一按“财务专员·职责岗”呈现。
        base_position = "财务组长" if member.name == "耿艺雪" else "财务专员"
        member.position = f"{base_position} · {role}"
    return members


def _hr_recruit_metrics(month: Optional[str] = None):
    """人力团队卡片指标：招聘模块实时数据（口径与招聘看板漏斗一致，姓名去重防同名虚高）。

    招聘模块暂无的指标不在此处（后续由用户设置）。month: YYYY-MM，缺省当月。
    查询异常返回 None，由调用方回退占位指标。"""
    from database import SessionLocal
    from models import Candidate, Position
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        today = date.today()
        ms, me = _month_boundary(month) if month else (today.replace(day=1), today)
        if ms is None:
            ms, me = today.replace(day=1), today
        pms = (ms.replace(day=1) - timedelta(days=1)).replace(day=1)
        pme = ms - timedelta(days=1)

        def _counts(s, e):
            mf = (Candidate.resume_received_date >= s) & (Candidate.resume_received_date <= e)
            omf = (Candidate.onboard_date >= s) & (Candidate.onboard_date <= e)
            return {
                "邀约面试": db.query(Candidate.name).filter(mf, Candidate.resume_received_date.isnot(None)).distinct().count(),
                "初试通过": db.query(Candidate).filter(mf, Candidate.first_round_pass == "pass").count(),
                "复试通过": db.query(Candidate).filter(mf, Candidate.second_round_pass == "pass").count(),
                "已接收": db.query(Candidate).filter(mf, Candidate.offer_accepted == "accepted").count(),
                "已到岗": db.query(Candidate.name).filter(omf, Candidate.onboard_date.isnot(None)).distinct().count(),
                "满7天": db.query(Candidate.name).filter(omf, Candidate.retention_7day == "yes").distinct().count(),
                "简历总数": db.query(Candidate).filter(mf, Candidate.resume_received_date.isnot(None)).count(),
            }

        cur, prev = _counts(ms, me), _counts(pms, pme)
        metrics = [
            DeptMetric(name=n, value=v, unit="人", target=None,
                       trend="up" if v > prev[n] else "down" if v < prev[n] else "stable")
            for n, v in cur.items()
        ]
        # 在招岗位数（需求侧，全局口径，与招聘看板一致；无环比）
        metrics.append(DeptMetric(name="在招岗位数", value=db.query(Position).count(),
                                  unit="个", target=None, trend="stable"))
        return metrics
    except Exception:  # noqa: BLE001 — 本地库异常回退占位，不拖垮看板
        return None
    finally:
        db.close()


def _dept_metrics_data(month: Optional[str] = None):
    """各部门专属人效指标 + 成员人效 + 主管主观评价

    month: 看板设定月份 YYYY-MM，产品团队和拼多多团队按此月统计；
           淘宝团队仍自动取表内最新数据月。
    """
    cache_key = month or ""
    cached = _dept_metrics_cache["data"].get(cache_key)
    if cached is not None and time.time() - _dept_metrics_cache["ts"].get(cache_key, 0) < _DEPT_METRICS_CACHE_TTL:
        return cached

    from datetime import datetime as dt
    now = dt.now().strftime("%Y-%m-%d %H:%M:%S")

    # 真实数据源部门：拼多多(pdd_web_profit_data) / 淘宝(taobao_bi_data)，MySQL 实时
    from pdd_bi import build_pdd_dept
    from taobao_bi import build_taobao_dept
    from product_bi import build_product_dept  # 产品团队：钉钉多维表「产品全流程进度跟踪」
    depts = [build_pdd_dept(month), build_taobao_dept()]

    # ═══ 展示占位部门（暂无经营数据源，按用户要求恢复展示，指标为占位值；产品团队已接钉钉多维表）═══

    def _subjectives():
        return [
            SubjectiveEval(dimension="人才质量", score=82, comment="团队整体能力扎实，核心骨干突出", trend="up"),
            SubjectiveEval(dimension="组织活力", score=78, comment="氛围活跃，但需加强跨部门互动", trend="stable"),
            SubjectiveEval(dimension="创新成长", score=75, comment="有一定创新意识，落地能力待提升", trend="up"),
            SubjectiveEval(dimension="执行力", score=85, comment="任务响应快，交付质量稳定", trend="up"),
            SubjectiveEval(dimension="团队协作", score=80, comment="内部配合良好，跨部门需加强", trend="stable"),
        ]

    # 人力/采购/客服/财务团队成员：花名册真实人员（不编造占位）
    hr_members = _hr_team_members()
    purchase_members = _procurement_team_members()
    cs_members = _customer_service_team_members()
    fin_members = _finance_team_members()
    depts += [
        DeptEfficiency(department="人力团队", team_size=len(hr_members), score=78.9,
            # 指标=招聘模块实时数据（漏斗口径，姓名去重）；招聘模块暂无的指标后续由用户设置
            metrics=_hr_recruit_metrics(month) or [
                DeptMetric(name="邀约面试", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="初试通过", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="复试通过", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="已接收", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="已到岗", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="满7天", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="简历总数", value=0, unit="人", target=None, trend="stable"),
                DeptMetric(name="在招岗位数", value=0, unit="个", target=None, trend="stable"),
            ],
            subjective=[
                # 人力行政部由招聘组 + 行政组组成，两组维度不同（用户口径）
                SubjectiveEval(dimension="业务理解", score=79, comment="对业务需求理解到位，招聘策略贴合业务", trend="up", group="招聘组"),
                SubjectiveEval(dimension="招聘交付力", score=82, comment="招聘交付高效，周期可控", trend="up", group="招聘组"),
                SubjectiveEval(dimension="人才配置与储备", score=76, comment="人才梯队建设良好，储备充足", trend="stable", group="招聘组"),
                SubjectiveEval(dimension="制度流程与用工风控", score=75, comment="制度完善，用工风控到位", trend="stable", group="招聘组"),
                SubjectiveEval(dimension="服务意识与协同", score=80, comment="服务意识强，协同顺畅", trend="up", group="招聘组"),
                SubjectiveEval(dimension="业务理解", score=78, comment="熟悉业务流程，行政支撑到位", trend="stable", group="行政组"),
                SubjectiveEval(dimension="行政后勤管理", score=76, comment="后勤保障有力，响应及时", trend="up", group="行政组"),
                SubjectiveEval(dimension="制度流程建设", score=74, comment="制度流程持续完善，落地执行好", trend="stable", group="行政组"),
                SubjectiveEval(dimension="成本管控", score=75, comment="成本管控合理，节约意识强", trend="up", group="行政组"),
                SubjectiveEval(dimension="服务意识与协同", score=79, comment="服务意识好，跨部门协同顺畅", trend="stable", group="行政组"),
            ],
            # 成员=花名册真实人员（招聘组/行政组/人力行政部），不编造占位
            members=hr_members),
        DeptEfficiency(department="采购团队", team_size=len(purchase_members), score=84.1,
            metrics=[
                DeptMetric(name="月采购额", value=620, unit="万元", target=600, trend="up"),
                DeptMetric(name="成本节约率", value=5.8, unit="%", target=5, trend="up"),
                DeptMetric(name="在管供应商数", value=38, unit="家", target=40, trend="stable"),
                DeptMetric(name="采购准时交付率", value=92.0, unit="%", target=95, trend="up"),
                DeptMetric(name="人效(采购额/人)", value=155.0, unit="万元/人", target=150, trend="up"),
                DeptMetric(name="库存周转天数", value=28, unit="天", target=25, trend="down"),
            ],
            subjective=[
                SubjectiveEval(dimension="成本优化", score=84, comment="原料、包材及 OEM 加工成本控制到位", trend="up"),
                SubjectiveEval(dimension="订单履约", score=80, comment="订单交付稳定，准时履约能力良好", trend="up"),
                SubjectiveEval(dimension="库存管理", score=77, comment="库存周转良好，结构可优化", trend="stable"),
                SubjectiveEval(dimension="供应商开发", score=87, comment="供应商资源丰富，开发有成效", trend="up"),
                SubjectiveEval(dimension="跨部门协同", score=82, comment="跨部门配合顺畅，响应及时", trend="stable"),
            ],
            # 成员=花名册真实人员（采购部在职），不编造占位
            members=purchase_members),
        build_product_dept(month),
        DeptEfficiency(department="客服团队", team_size=len(cs_members), score=81.6,
            metrics=[
                DeptMetric(name="日均处理量", value=3200, unit="单", target=3000, trend="up"),
                DeptMetric(name="客户满意度", value=91.5, unit="%", target=93, trend="up"),
                DeptMetric(name="平均响应时长", value=38, unit="秒", target=30, trend="down"),
                DeptMetric(name="客诉解决率", value=94.0, unit="%", target=95, trend="up"),
                DeptMetric(name="一次解决率", value=82.0, unit="%", target=85, trend="up"),
                DeptMetric(name="人效(处理量/人)", value=533, unit="单/人", target=500, trend="up"),
            ],
            subjective=[
                SubjectiveEval(dimension="销售转化", score=81, comment="转化能力良好，话术有效", trend="up"),
                SubjectiveEval(dimension="售后处理", score=77, comment="售后处理专业，时效待提升", trend="stable"),
                SubjectiveEval(dimension="响应效率", score=74, comment="响应较快，高峰时段可优化", trend="stable"),
                SubjectiveEval(dimension="用户洞察", score=84, comment="洞察用户需求，反馈质量高", trend="up"),
                SubjectiveEval(dimension="情绪韧性", score=79, comment="情绪管理良好，抗压稳定", trend="stable"),
            ],
            # 成员=花名册真实人员（客服部在职），不编造占位
            members=cs_members),
        DeptEfficiency(department="财务团队", team_size=len(fin_members), score=76.0,
            metrics=[
                DeptMetric(name="月资金流水", value=1860, unit="万元", target=1800, trend="up"),
                DeptMetric(name="结算准时率", value=96.0, unit="%", target=98, trend="up"),
                DeptMetric(name="费用报销时效", value=2.5, unit="天", target=3, trend="down"),
                DeptMetric(name="财务报表及时率", value=100.0, unit="%", target=100, trend="stable"),
                DeptMetric(name="税务申报合规率", value=100.0, unit="%", target=100, trend="stable"),
                DeptMetric(name="人效(单据处理量/人)", value=420, unit="单/人", target=400, trend="up"),
            ],
            # 电商财务岗位专属五维雷达：每维20分，部门分数由成员评分逐维均值汇总
            subjective=[
                SubjectiveEval(dimension="财务核算与报表质量", score=16, comment="账务与经营报表基础稳定，持续提升平台账单核对和差异闭环能力", trend="up"),
                SubjectiveEval(dimension="预算与经营分析", score=15, comment="能够支持预算与经营复盘，建议进一步加强费用、毛利和ROI偏差分析", trend="up"),
                SubjectiveEval(dimension="资金与结算管理", score=15, comment="回款、付款和报销流程总体稳定，需持续强化现金流预测与节点管理", trend="stable"),
                SubjectiveEval(dimension="税务合规与风险控制", score=16, comment="报税与发票管理执行及时，继续完善平台规则和合同风险检查", trend="stable"),
                SubjectiveEval(dimension="业务协同与数字化", score=15, comment="已具备业务支持意识，建议推动财务报表自动化和数据口径统一", trend="up"),
            ],
            # 成员=花名册真实人员（财务部在职），不编造占位
            members=fin_members),
    ]

    # 直属上级评价按部门+姓名覆盖内置/花名册评价；评价不参与雷达分数计算。
    depts = _apply_manager_evaluations(depts)

    # 部门雷达统一由员工个人雷达评分逐维汇总（未评分时保留可用的基准值）
    depts = _apply_member_radar_scores(depts)

    resp = DeptEfficiencyResponse(items=depts, updated_at=now)
    _dept_metrics_cache["data"][cache_key] = resp
    _dept_metrics_cache["ts"][cache_key] = time.time()
    return resp

@app.get("/api/dept-efficiency", response_model=DeptEfficiencyResponse)
def get_dept_efficiency(month: Optional[str] = Query(None, description="看板设定月份 YYYY-MM，产品团队按此月统计")):
    """获取各部门人效数据"""
    return _dept_metrics_data(month)


@app.post("/api/sync-dept-efficiency")
def sync_dept_efficiency(month: Optional[str] = Query(None, description="看板设定月份 YYYY-MM，产品团队按此月统计")):
    """强制刷新产品/设计/拼多多打品钉钉数据，并返回指定月份的部门人效看板。"""
    from product_bi import refresh_product_cache
    from pdd_bi import refresh_pdd_product_cache
    try:
        sync_meta = refresh_product_cache()
        sync_meta.update(refresh_pdd_product_cache())
    except Exception as exc:  # noqa: BLE001 — 将外部数据源错误明确返回给前端
        logger.exception("❌ 手动刷新产品/设计/拼多多打品人效失败: %s", exc)
        return {
            "items": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sync": {"ok": False, "message": str(exc)},
        }

    _clear_dept_metrics_cache()
    data = _dept_metrics_data(month)
    payload = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    payload["sync"] = {"ok": True, **sync_meta}
    return payload


@app.get("/api/dept-efficiency/member-daily")
def get_member_daily(department: str, member: str, month: Optional[str] = Query(None)):
    """成员当月每日产出序列（产品团队抽屉图表，真实数据）。

    - 设计部成员：每日 设计数/通过数（设计每日稿件统计 逐日统计）
    - 产品负责人：每日 预计上线产品数（预计上线日期分布）
    其他部门暂不支持，返回 daily=None。
    """
    if department != "产品团队":
        return {"department": department, "member": member, "month": month,
                "daily": None, "error": "仅产品团队支持每日产出数据"}
    from product_bi import member_daily
    data = member_daily(month, member)
    if data is None:
        return {"department": department, "member": member, "month": month,
                "daily": None, "error": "该成员当月无记录"}
    return {"department": department, "member": member, "month": month, **data}


# ==================== 成员个人人才雷达图 API（每人一个打分入口） ====================

# 个人雷达图维度（与部门主观评价一致，便于后续按部门聚合分析）
MEMBER_RADAR_DIMS = ["财务产出", "运营效率", "人才质量", "执行力", "创新成长"]
# 财务团队通用维度：未提供职责拆分的财务人员使用此套；每项满分20分，五维合计100分
FINANCE_MEMBER_RADAR_DIMS = ["财务核算与报表质量", "预算与经营分析", "资金与结算管理", "税务合规与风险控制", "业务协同与数字化"]
FINANCE_RADAR_STANDARDS = {
    "财务核算与报表质量": "重点：账务、平台账单、应收应付及经营报表的准确性、完整性与及时性。",
    "预算与经营分析": "重点：围绕GMV、毛利、费用、ROI和利润目标开展预算、预测及偏差分析。",
    "资金与结算管理": "重点：平台回款、供应商付款、报销和现金流节点的准确性、安全性与及时性。",
    "税务合规与风险控制": "重点：发票、税费申报、合同、平台规则及内控流程的合规与风险预警。",
    "业务协同与数字化": "重点：支持运营、采购、产品决策，统一数据口径并推动报表和流程自动化。",
}

# 财务团队按实际工作内容拆分岗位雷达。长指标口径压缩为看板可直接阅读的重点指标摘要，
# 评分仍严格采用 5 个维度 × 20 分 = 100 分上限。
FINANCE_ROLE_PROFILES = {
    "核算岗": {
        "dims": ["数据拉取与对账时效", "对账准确性", "审批提交时效与合规性", "库存数量核对质量", "单量处理与产出效率"],
        "standards": {
            "数据拉取与对账时效": "重点：数据拉取及时率、平均对账时长、逾期未对账供应商数及金额。",
            "对账准确性": "重点：对账差异率、差异构成、差异解决时效和错对漏对笔数。",
            "审批提交时效与合规性": "重点：提交及时率、一次通过率、单据完整率和平均提交延迟。",
            "库存数量核对质量": "重点：账实相符率、收发存一致率、差异跟进时效和重复发生率。",
            "单量处理与产出效率": "重点：日均处理量、单笔耗时、月末关账准时率和大促高峰产能。",
        },
    },
    "经营报表岗": {
        "dims": ["日利润表出具时效", "报表数据准确性", "往来账务处理时效与质量", "售后报表整理质量与时效", "综合产能与关键节点达成率"],
        "standards": {
            "日利润表出具时效": "重点：按时出具率、平均出具耗时及月末延迟天数；目标及时率100%、月末不延迟。",
            "报表数据准确性": "重点：报表准确率、业务与经营报表勾稽一致率、返工次数和口径稳定性。",
            "往来账务处理时效与质量": "重点：入账及时率、长期挂账清理率、账龄健康度和往来凭证差错率。",
            "售后报表整理质量与时效": "重点：整理及时率、退款退货等字段完整率、费用分类准确率和异常预警及时性。",
            "综合产能与关键节点达成率": "重点：报表/凭证/售后处理量、单件耗时、关键节点达成率和紧急任务响应。",
        },
    },
    "数据审核岗": {
        "dims": ["发货明细审核时效与覆盖率", "成本收入数据审核准确性", "数据整合质量与时效", "账务处理时效与质量", "月度结算核对与综合产能"],
        "standards": {
            "发货明细审核时效与覆盖率": "重点：审核及时率、审核覆盖率、平均审核延迟和超时积压量；覆盖率目标100%。",
            "成本收入数据审核准确性": "重点：差错拦截率、漏网差错率、成本核对准确率和收入匹配率。",
            "数据整合质量与时效": "重点：平台/物流/ERP整合及时率、勾稽一致率及错位遗漏重复率。",
            "账务处理时效与质量": "重点：凭证入账及时率、凭证准确率和成本/收入/往来科目归集准确率。",
            "月度结算核对与综合产能": "重点：月度结算按时完成率、结算差异率、差异解决时效和日均处理量。",
        },
    },
    "发货岗": {
        "dims": ["订单发货时效", "物流预警处理时效", "赔付单整理与追偿", "运费模板屏蔽区域管理", "综合产能与店铺履约质量"],
        "standards": {
            "订单发货时效": "重点：平台时限内发货率、平均发货时长、超时风险订单数和催发响应率。",
            "物流预警处理时效": "重点：预警处理及时率、揽收及时率、物流停滞订单数和预警响应时长。",
            "赔付单整理与追偿": "重点：赔付整理及时率、材料及金额准确率、追偿成功率和平均追偿周期。",
            "运费模板屏蔽区域管理": "重点：区域调整及时率与准确率、异常订单拦截数和漏防赔付金额。",
            "综合产能与店铺履约质量": "重点：负责店铺数、日均订单量、店铺履约率、异常响应时效和高峰产能。",
        },
    },
    "出纳岗": {
        "dims": ["收入登记时效与准确性", "报销支付时效", "账务处理质量", "网银U盾管理合规性", "单据处理量与产出效率"],
        "standards": {
            "收入登记时效与准确性": "重点：到账24小时内登记率、平均登记延迟、登记准确率及平台回款匹配率。",
            "报销支付时效": "重点：审批通过至付款平均时长、逾期支付率和银行退回率。",
            "账务处理质量": "重点：日结及时率、账实相符率及冲正/调账单据率。",
            "网银U盾管理合规性": "重点：保管与借出登记、付款双人复核执行率及错转/重复支付/U盾遗失事件；目标零事故。",
            "单据处理量与产出效率": "重点：收入登记和报销支付日均量、单笔耗时及月末/对账高峰处理能力。",
        },
    },
}
# 花名册姓名 → 财务岗位标签。未在此表中的人员保留花名册岗位并使用通用财务维度。
FINANCE_MEMBER_ROLE = {
    "姜灵": "核算岗",
    "耿艺雪": "经营报表岗",
    "曹静雨": "数据审核岗",
    "李玲玲": "发货岗",
    "王圪平": "发货岗",
    "罗薇薇": "出纳岗",
}
# 电商团队（拼多多/淘宝）成员雷达维度：按用户要求与部门雷达一致
ECOMMERCE_MEMBER_RADAR_DIMS = ["数据驱动与选品力", "店群品效管理", "渠道拓展与策略贡献", "运营人效", "抗压与执行"]
# 采购团队成员雷达维度：按用户要求与部门雷达一致
PURCHASE_MEMBER_RADAR_DIMS = ["成本优化", "订单履约", "库存管理", "供应商管理", "部门协同"]
# 赵艺乐个人雷达维度：首项为数据信息管理，其余维度与采购团队一致
PURCHASE_ZHAO_MEMBER_RADAR_DIMS = ["数据信息管理", "订单履约", "库存管理", "供应商管理", "部门协同"]
PURCHASE_RADAR_STANDARDS = {
    "成本优化": "针对原料、包材及 OEM 加工费进行成本核算、议价和降本改善的能力。",
    "订单履约": "确保 OEM 工厂按订单节点准时交货，应对爆单时产能协调和异常闭环的能力。",
    "库存管理": "家用清洁类目体积大，需极高周转，避免呆滞库存的能力。",
    "供应商管理": "供应商准入、分级、绩效跟进、交付与异常协调管理能力。",
    "部门协同": "与运营（备货计划）、产品（打样）及工厂的配合度与主动性。",
}
PURCHASE_ZHAO_RADAR_STANDARDS = {
    **PURCHASE_RADAR_STANDARDS,
    "数据信息管理": "采购数据台账、订单、成本、库存和供应商信息的准确维护、汇总分析与及时反馈能力。",
}
# 采购个人雷达维度改名兼容：新名称 -> 历史存储名称
PURCHASE_LEGACY_DIM_ALIASES = {
    "供应商管理": "供应商开发",
    "部门协同": "跨部门协同",
}
# 客服团队成员雷达维度：按用户要求与部门雷达一致
CUSTOMER_MEMBER_RADAR_DIMS = ["销售转化", "售后处理", "响应效率", "用户洞察", "情绪韧性"]
CUSTOMER_RADAR_STANDARDS = {
    "销售转化": "售前询单转化率、关联推荐及催付能力。",
    "售后处理": "纠纷退款率、平台介入率、差评挽回及DSR维护能力。",
    "响应效率": "平均响应时长、首次回复时长。",
    "用户洞察": "收集清洁产品客诉反馈，反哺产品/运营优化的能力。",
    "情绪韧性": "应对\u201c仅退款\u201d、恶意买家及高强度工作的心态调节能力。",
}
# 人力行政部（人力团队）成员雷达维度：按用户要求，招聘组/行政组各一套
HR_RECRUIT_DIMS = ["业务理解", "招聘交付力", "人才配置与储备", "制度流程与用工风控", "服务意识与协同"]
HR_ADMIN_DIMS = ["业务理解", "行政后勤管理", "制度流程建设", "成本管控", "服务意识与协同"]
# 人力团队占位成员 → 组归属（真实花名册接入后按岗位归组）
_HR_ADMIN_MEMBER_GROUP = {"赵敏": "招聘组", "钱丽": "招聘组", "孙丽": "行政组", "李娜": "行政组", "周琴": "行政组"}
# 产品负责人（产品团队-产品部）成员雷达维度：单维满分20分
PRODUCT_OWNER_DIMS = ["新品交付时效", "交付准时率", "跨部门协同效率", "新品储备深度", "市场趋势响应"]
PRODUCT_RADAR_STANDARDS = {
    "新品交付时效": "衡量从立项到上架的全流程速度，评估能否极致压缩开发周期，快速响应前端需求。",
    "交付准时率": "衡量项目管理的可靠性，评估能否严格按节点推进，确保各环节无缝衔接，实现100%准时交付。",
    "跨部门协同效率": "衡量与各部门的协作效能，评估能否主动同步信息、快速解决问题，减少内耗，推动项目高效落地。",
    "新品储备深度": "衡量\u201c弹药库\u201d建设能力，评估能否持续开发并完成前期准备，形成随时可上线的新品池。",
    "市场趋势响应": "衡量将市场洞察转化为行动的速度，评估能否捕捉新趋势并快速启动开发，确保产品线贴近市场。",
}
# 产品团队（产品部/设计部）成员雷达维度（历史通用维度，已按岗位拆分为 产品负责人/设计人员 两套）
PRODUCT_MEMBER_RADAR_DIMS = ["人才质量", "组织活力", "创新成长", "执行力", "团队协作"]
# 设计人员（产品团队-设计部）成员雷达维度：单维满分20分
DESIGN_MEMBER_RADAR_DIMS = ["视觉转化力", "视觉创意力", "品牌视觉管理", "设计效率与规范", "部门协同"]
DESIGN_RADAR_STANDARDS = {
    "视觉转化力": "详情页/主图对\u201c清洁效果\u201d的视觉呈现及点击率/转化率优化能力。",
    "视觉创意力": "在信息流/短视频/直播间场景下，通过差异化视觉设计抓住用户眼球、提升停留时长的能力。",
    "品牌视觉管理": "在店群/多链接模式下，确保品牌视觉资产（VI/色调/调性）统一性，避免廉价感，提升品牌溢价的能力。",
    "设计效率与规范": "应对海量SKU需求时的作图速度，以及建立组件化/模板化设计体系以赋能团队的能力。",
    "部门协同": "与运营（卖点提炼）、产品（包装落地）、视频（素材配合）的高效沟通与协作能力。",
}

# 电商团队（拼多多/淘宝）成员雷达评分标准（每项满分20分）
ECOMMERCE_RADAR_STANDARDS = {
    "数据驱动与选品力": "对拼多多/千川后台数据的解读能力及从测款到爆款的完整操盘能力，衡量数据洞察与打品结果的双重产出。",
    "店群品效管理": "黑标店群矩阵管理效率及单链接产出能力，衡量\u201c管店能力\u201d与\u201c单链接产出效率\u201d的综合表现。",
    "渠道拓展与策略贡献": "淘宝/天猫/达播/千川短视频的协同或独立开拓能力，以及输出可复用方法论推动团队效率提升的能力。",
    "运营人效": "个人负责的GMV（或毛利）与个人薪资成本的比值，直接衡量\u201c个人产出价值\u201d与\u201c投入产出比\u201d。",
    "抗压与执行": "应对大促、平台规则突变及高强度店群操作的韧性与执行力，衡量在高压环境下持续产出结果的能力。",
}
# 所有带评分标准的维度，统一为 20 分制；财务岗位维度来自各岗位 profile
_FINANCE_ROLE_RADAR_STANDARDS = {
    dimension: standard
    for profile in FINANCE_ROLE_PROFILES.values()
    for dimension, standard in profile["standards"].items()
}
_RADAR_STANDARDS = {**ECOMMERCE_RADAR_STANDARDS, **DESIGN_RADAR_STANDARDS, **PURCHASE_RADAR_STANDARDS,
                    **PURCHASE_ZHAO_RADAR_STANDARDS,
                    **PRODUCT_RADAR_STANDARDS, **CUSTOMER_RADAR_STANDARDS, **FINANCE_RADAR_STANDARDS,
                    **_FINANCE_ROLE_RADAR_STANDARDS}
# 评分标准按部门/岗位区分（"跨部门协同"等同名维度在不同岗位标准不同，避免 dict 合并覆盖）
_RADAR_STANDARDS_BY_ROLE = {
    "拼多多团队": ECOMMERCE_RADAR_STANDARDS,
    "淘宝团队": ECOMMERCE_RADAR_STANDARDS,
    "采购团队": PURCHASE_RADAR_STANDARDS,
    "客服团队": CUSTOMER_RADAR_STANDARDS,
    "财务团队": FINANCE_RADAR_STANDARDS,
    "产品负责人": PRODUCT_RADAR_STANDARDS,
    "设计人员": DESIGN_RADAR_STANDARDS,
}
# 成员雷达单维满分：五个维度统一为 20 分，合计上限 100 分
_MEMBER_RADAR_MAX = {"拼多多团队": 20, "淘宝团队": 20, "采购团队": 20, "产品团队": 20, "客服团队": 20, "财务团队": 20}


def _member_radar_max(department: str, member: str = None, position: str = "", dimension: str = None) -> int:
    """Return the uniform 20-point maximum for every radar dimension."""
    if dimension is not None and dimension in _RADAR_STANDARDS:
        return 20
    return _MEMBER_RADAR_MAX.get(department, 20)


def _member_radar_dims(department: str, member: str = None, position: str = ""):
    """按部门（人力团队按成员组、产品团队按产品/设计岗位）返回个人雷达图维度。"""
    if department == "产品团队":
        # 岗位名以花名册为准（设计/美工→设计维度；产品岗位→产品维度；兼容旧值"设计人员"）
        if "设计" in position or "美工" in position:
            return DESIGN_MEMBER_RADAR_DIMS
        return PRODUCT_OWNER_DIMS
    if department in ("拼多多团队", "淘宝团队"):
        return ECOMMERCE_MEMBER_RADAR_DIMS
    if department == "采购团队":
        if member == "赵艺乐":
            return PURCHASE_ZHAO_MEMBER_RADAR_DIMS
        return PURCHASE_MEMBER_RADAR_DIMS
    if department == "客服团队":
        return CUSTOMER_MEMBER_RADAR_DIMS
    if department == "财务团队":
        role = FINANCE_MEMBER_ROLE.get(member)
        return FINANCE_ROLE_PROFILES.get(role, {}).get("dims", FINANCE_MEMBER_RADAR_DIMS)
    if department == "人力团队":
        # 真实花名册成员按岗位归组（钉钉 sys00-position：含"招聘"→招聘组，否则→行政组）
        # 兼容旧值"招聘人员"/"行政人员"及旧姓名映射
        if "招聘" in position or _HR_ADMIN_MEMBER_GROUP.get(member) == "招聘组":
            return HR_RECRUIT_DIMS
        return HR_ADMIN_DIMS
    return MEMBER_RADAR_DIMS


# Keep the public department API and the member-radar API on the same 20-point
# dimension scale. This definition intentionally sits after the radar constants
# so it can also aggregate the role-specific product and HR dimension groups.
def _apply_member_radar_scores(depts):
    """Apply member totals and roll same-position scores into department radars."""
    from database import SessionLocal
    from models import MemberScore

    db = SessionLocal()
    try:
        rows = db.query(MemberScore).all()
    except Exception:  # noqa: BLE001 - keep the dashboard available on DB errors
        db.close()
        return depts
    db.close()

    stored: dict = {}
    for row in rows:
        if row.score is not None:
            stored.setdefault((row.department, row.member_name), {})[row.dimension] = row.score

    def radar_group(department, dims, member_name=""):
        if department == "产品团队":
            return "设计团队" if dims == DESIGN_MEMBER_RADAR_DIMS else "产品团队"
        if department == "人力团队":
            return "招聘组" if dims == HR_RECRUIT_DIMS else "行政组"
        if department == "财务团队":
            return FINANCE_MEMBER_ROLE.get(member_name, "")
        return ""

    # Static fallback values were authored on a 0-100 scale. Normalize them to
    # 0-20 per dimension while leaving already migrated values unchanged.
    for dept in depts:
        for item in dept.subjective or []:
            if item.score is not None and item.score > 20:
                item.score = round(item.score / 5, 1)

    # (department, group, position, dimension) -> scores from members.
    position_values: dict = {}
    for dept in depts:
        for member in dept.members:
            dims = _member_radar_dims(dept.department, member.name, member.position)
            raw_values = dict(stored.get((dept.department, member.name), {}))
            # 维度改名时兼容旧评分记录，避免历史分数因名称调整丢失。
            if dept.department == "采购团队":
                legacy_dims = dict(PURCHASE_LEGACY_DIM_ALIASES)
                if member.name == "赵艺乐":
                    legacy_dims["数据信息管理"] = "成本优化"
                for new_dim, old_dim in legacy_dims.items():
                    raw_values.setdefault(new_dim, raw_values.get(old_dim))
            current_values = {
                dim: max(0.0, min(20.0, float(raw_values[dim])))
                for dim in dims
                if raw_values.get(dim) is not None
            }
            # All five dimensions together have a hard ceiling of 100 points.
            member.score_max = 100
            if current_values:
                member.score = round(sum(current_values.values()), 1)

            group = radar_group(dept.department, dims, member.name)
            position = (member.position or "未标注岗位").strip()
            by_position = position_values.setdefault(dept.department, {})
            for dimension, value in current_values.items():
                key = (group, position, dimension)
                by_position.setdefault(key, []).append(value)

    # Average members within the same position first, then average positions.
    dept_values: dict = {}
    for department, by_position in position_values.items():
        by_dimension = dept_values.setdefault(department, {})
        for (group, _position, dimension), values in by_position.items():
            role_mean = sum(values) / len(values)
            by_dimension.setdefault((group, dimension), []).append(role_mean)

    # 财务成员使用岗位专属维度：有实际评分后，部门雷达按岗位生成独立分组。
    # 同一岗位先逐维平均（如两名发货岗），再供部门雷达展示；未评分岗位不生成虚假雷达组。
    finance_values = dept_values.get("财务团队", {})
    if finance_values:
        finance_dept = next((d for d in depts if d.department == "财务团队"), None)
        if finance_dept is not None:
            for role, profile in FINANCE_ROLE_PROFILES.items():
                if not any((role, dim) in finance_values for dim in profile["dims"]):
                    continue
                for dim in profile["dims"]:
                    values = finance_values.get((role, dim), [])
                    score = round(sum(values) / len(values), 1) if values else 0
                    finance_dept.subjective.append(SubjectiveEval(
                        dimension=dim,
                        score=score,
                        comment=profile["standards"].get(dim, ""),
                        trend="stable",
                        group=role,
                    ))

    for dept in depts:
        by_dimension = dept_values.get(dept.department, {})
        if not by_dimension:
            continue
        group_values: dict = {}
        for (group, _dimension), values in by_dimension.items():
            group_values.setdefault(group, []).extend(values)
        for item in dept.subjective or []:
            # 采购部门整体雷达仍沿用原有部门口径，但读取个人新维度的评分。
            department_dim_aliases = {
                "供应商开发": "供应商管理",
                "跨部门协同": "部门协同",
            } if dept.department == "采购团队" else {}
            key = (item.group or "", department_dim_aliases.get(item.dimension, item.dimension))
            values = by_dimension.get(key)
            if values:
                item.score = round(sum(values) / len(values), 1)
            elif dept.department != "财务团队" and group_values.get(item.group or ""):
                # Partially scored groups use their scored-dimension mean for
                # the remaining dimensions instead of mixing score scales.
                values = group_values[item.group or ""]
                item.score = round(sum(values) / len(values), 1)
            item.score = max(0, min(20, item.score))
    return depts


@app.get("/api/member-radar", response_model=MemberRadarResponse)
def get_member_radar(department: str, db: Session = Depends(get_db)):
    """获取部门成员列表及每人各维度评分（未评分维度为 None），附维度满分与评分标准。"""
    dept = next((d for d in _dept_metrics_data().items if d.department == department), None)
    if dept is None:
        return MemberRadarResponse(department=department, items=[])
    rows = db.query(MemberScore).filter(MemberScore.department == department).all()
    score_map = {(r.member_name, r.dimension): r.score for r in rows}
    items = []
    dims_info: dict = {}  # dimension -> standard（保留首次出现顺序）
    for m in dept.members:
        dims = _member_radar_dims(department, m.name, m.position)
        scores = {dim: score_map.get((m.name, dim)) for dim in dims}
        # 兼容采购维度改名前的历史评分，展示新维度时沿用原分数。
        if department == "采购团队":
            legacy_dims = dict(PURCHASE_LEGACY_DIM_ALIASES)
            if m.name == "赵艺乐":
                legacy_dims["数据信息管理"] = "成本优化"
            for new_dim, old_dim in legacy_dims.items():
                if scores.get(new_dim) is None:
                    scores[new_dim] = score_map.get((m.name, old_dim))
        last = max((r.updated_at for r in rows if r.member_name == m.name), default="")
        items.append(MemberScoreItem(name=m.name, position=m.position, scores=scores, updated_at=last))
        # 产品团队岗位名以花名册为准（设计/美工/产品储备主管等），按维度集取标准
        if department == "产品团队":
            std = DESIGN_RADAR_STANDARDS if dims == DESIGN_MEMBER_RADAR_DIMS else PRODUCT_RADAR_STANDARDS
        elif department == "采购团队" and m.name == "赵艺乐":
            std = PURCHASE_ZHAO_RADAR_STANDARDS
        elif department == "财务团队":
            role = FINANCE_MEMBER_ROLE.get(m.name)
            std = FINANCE_ROLE_PROFILES.get(role, {}).get("standards", FINANCE_RADAR_STANDARDS)
        else:
            std = _RADAR_STANDARDS_BY_ROLE.get(m.position) or _RADAR_STANDARDS_BY_ROLE.get(department, {})
        for d in dims:  # 维度并集（产品团队=产品5维+设计5维），标准按岗位取
            dims_info.setdefault(d, std.get(d, ""))
    dims = [RadarDimInfo(dimension=d, max=_member_radar_max(department, dimension=d),
                         standard=s) for d, s in dims_info.items()]
    return MemberRadarResponse(department=department, items=items, dims=dims)


@app.put("/api/member-radar")
def save_member_radar(payload: MemberScoreSave, db: Session = Depends(get_db)):
    """保存某成员 5 维评分（按 部门+姓名+维度 upsert，每人独立打分入口）。
    每个维度最高 20 分，五个维度合计最高 100 分。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    position = payload.position
    if not position:  # 兼容旧前端：按成员在部门内的岗位补齐
        dept = next((d for d in _dept_metrics_data().items if d.department == payload.department), None)
        if dept:
            position = next((m.position for m in dept.members if m.name == payload.member), "")
    dims = _member_radar_dims(payload.department, payload.member, position)
    for dim, score in payload.scores.items():
        if dim not in dims:
            continue
        max_score = _member_radar_max(payload.department, payload.member, position, dim)
        score = max(0, min(max_score, int(score)))
        row = db.query(MemberScore).filter_by(
            department=payload.department, member_name=payload.member, dimension=dim).first()
        if row:
            row.score = score
            row.updated_at = now
        else:
            db.add(MemberScore(department=payload.department, member_name=payload.member,
                               dimension=dim, score=score, updated_at=now))
    db.commit()
    return {"ok": True, "member": payload.member, "updated_at": now}


@app.put("/api/dept-efficiency/manager-evaluation")
def save_manager_evaluation(payload: ManagerEvaluationSave, db: Session = Depends(get_db)):
    """保存部门人效看板中的直属上级主观评价，可通过提交空文本清空。"""
    department = payload.department.strip()
    member = payload.member.strip()
    evaluation = (payload.evaluation or "").strip()
    if not department or not member:
        raise HTTPException(status_code=422, detail="部门和成员姓名不能为空")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = db.query(ManagerEvaluation).filter_by(
        department=department, member_name=member,
    ).first()
    if row:
        row.evaluation = evaluation
        row.updated_at = now
    else:
        db.add(ManagerEvaluation(
            department=department,
            member_name=member,
            evaluation=evaluation,
            updated_at=now,
        ))
    db.commit()
    _clear_dept_metrics_cache()
    return {
        "ok": True,
        "department": department,
        "member": member,
        "evaluation": evaluation,
        "updated_at": now,
    }


# ==================== 人才雷达图 + 部门人才质量分析 API ====================

@app.get("/api/talent-analysis", response_model=TalentAnalysisResponse)
def get_talent_analysis(db: Session = Depends(get_db)):
    """人才雷达图 + 部门质量分析"""
    employees = db.query(Employee).filter(Employee.is_active == "yes").all()
    profiles = db.query(TalentProfile).all()

    # Build profile map: employee_id -> {dimension: score}
    from collections import defaultdict
    profile_map = defaultdict(dict)
    for p in profiles:
        profile_map[p.employee_id][p.dimension] = p.score

    positions = {
        "技术部": ["前端工程师","后端工程师","全栈工程师","技术主管","架构师"],
        "产品部": ["产品经理","产品助理","高级产品经理"],
        "设计部": ["UI设计师","平面设计师","包装设计师","美工"],
        "运营部": ["运营专员","运营主管","新媒体运营"],
        "质量部": ["测试工程师","QA主管"],
        "数据部": ["数据分析师","数据工程师"],
        "人力资源部": ["HRBP","招聘专员","HR经理"],
        "财务部": ["会计","财务主管","财务分析师"],
        "客服部": ["客服专员","客服主管","售后专员"],
        "千川部": ["千川运营","剪辑专员","投流专员"],
        "采购部": ["采购专员"],
    }

    import random
    talent_employees = []
    dept_scores = defaultdict(lambda: {"scores": [], "count": 0})

    for emp in employees:
        dims = profile_map.get(emp.id, {})
        dept_positions = positions.get(emp.department, ["员工"])
        pos = random.choice(dept_positions)

        talent_dimensions = []
        for dim_name in ["专业能力", "沟通协作", "创新能力", "执行力", "学习能力", "责任感"]:
            score = dims.get(dim_name, random.randint(50, 90))
            talent_dimensions.append(TalentDimension(dimension=dim_name, score=score))

        talent_employees.append(TalentRadarData(
            employee_id=emp.id,
            name=emp.name,
            department=emp.department,
            position=pos,
            dimensions=talent_dimensions,
        ))

        # Aggregate dept scores
        dept_scores[emp.department]["scores"].append({
            "专业能力": dims.get("专业能力", 50),
            "沟通协作": dims.get("沟通协作", 50),
            "创新能力": dims.get("创新能力", 50),
            "执行力": dims.get("执行力", 50),
            "学习能力": dims.get("学习能力", 50),
            "责任感": dims.get("责任感", 50),
        })
        dept_scores[emp.department]["count"] += 1

    # Build department analysis
    dim_keys = ["专业能力", "沟通协作", "创新能力", "执行力", "学习能力", "责任感"]
    dim_attrs = ["avg_professional", "avg_communication", "avg_innovation", "avg_execution", "avg_learning", "avg_responsibility"]

    dept_list = []
    for dept, data in dept_scores.items():
        count = data["count"]
        if count == 0:
            continue
        scores_list = data["scores"]
        avgs = {}
        for dk in dim_keys:
            avgs[dk] = round(sum(s[dk] for s in scores_list) / count, 1)
        overall = round(sum(avgs.values()) / len(avgs), 1)

        # Grade
        if overall >= 85: grade = "S"
        elif overall >= 75: grade = "A"
        elif overall >= 65: grade = "B"
        else: grade = "C"

        dept_list.append({
            "department": dept,
            "count": count,
            "avg_professional": avgs["专业能力"],
            "avg_communication": avgs["沟通协作"],
            "avg_innovation": avgs["创新能力"],
            "avg_execution": avgs["执行力"],
            "avg_learning": avgs["学习能力"],
            "avg_responsibility": avgs["责任感"],
            "overall": overall,
            "grade": grade,
        })

    # Rank by overall score
    dept_list.sort(key=lambda x: -x["overall"])
    final_depts = []
    for rank, d in enumerate(dept_list, 1):
        final_depts.append(DeptTalentScore(
            department=d["department"],
            employee_count=d["count"],
            avg_professional=d["avg_professional"],
            avg_communication=d["avg_communication"],
            avg_innovation=d["avg_innovation"],
            avg_execution=d["avg_execution"],
            avg_learning=d["avg_learning"],
            avg_responsibility=d["avg_responsibility"],
            overall_score=d["overall"],
            grade=d["grade"],
            rank=rank,
        ))

    from datetime import datetime
    return TalentAnalysisResponse(
        employees=talent_employees,
        departments=final_depts,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── 钉钉花名册同步（凭证仅在后端，不暴露给前端）──
@app.post("/api/sync-roster")
def sync_roster():
    """从钉钉智能人事拉取花名册数据并更新本地员工表。凭证仅在 .env 中，不进入 API 响应。"""
    from dingtalk_sync import run_sync
    result = run_sync()
    return {
        **result,
        "note": "凭证仅在后端 .env 文件中，未暴露给此接口或前端",
    }


# ── 钉钉多维表招聘数据同步 ──
@app.get("/api/inspect-bitable")
def inspect_bitable():
    """检查多维表结构（表/字段）。"""
    from dingtalk_bitable import run_inspect
    result = run_inspect()
    return {
        **result,
        "note": "多维表凭证仅在代码中，未暴露给前端",
    }


@app.post("/api/sync-recruitment")
def sync_recruitment():
    """从钉钉多维表「面试记录-2026」同步招聘数据。"""
    if not _sync_lock.acquire(blocking=False):
        return {"synced": 0, "error": "同步正在进行中，请稍后再试"}
    try:
        from dingtalk_bitable import run_sync
        result = run_sync()
        return {
            **result,
            "note": "多维表凭证仅在代码中，未暴露给前端",
        }
    finally:
        _sync_lock.release()


# ═══════════════════════════════════════════════════
# 管理人员日志评分（钉钉日报 → 规则评分 → 排名/优点/需改进）
# ═══════════════════════════════════════════════════

def _normalize_logs_month(month: Optional[str]) -> Optional[str]:
    """校验并标准化日志筛选月份，返回 YYYY-MM；空值表示当前月份。"""
    if month is None or str(month).strip() == "":
        return None
    value = str(month).strip()
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("月份格式应为 YYYY-MM") from exc


def _logs_period_range(period: str, month: Optional[str] = None) -> tuple:
    """按粒度取时间区间；传入 month 时，以该月作为季度/半年/年度锚点。"""
    if period not in _LOGS_PERIOD_LABELS:
        raise ValueError("周期参数应为 month/quarter/half/year")
    now = datetime.now()
    month_key = _normalize_logs_month(month)
    anchor = datetime.strptime(month_key, "%Y-%m") if month_key else now
    anchor = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if period == "month":
        start = anchor
        end_month = anchor.month + 1
    elif period == "quarter":
        start = anchor.replace(month=((anchor.month - 1) // 3) * 3 + 1)
        end_month = start.month + 3
    elif period == "half":
        start = anchor.replace(month=(1 if anchor.month <= 6 else 7))
        end_month = start.month + 6
    else:  # year
        start = anchor.replace(month=1)
        end_month = 13

    end_year = start.year + ((end_month - 1) // 12)
    end_month = ((end_month - 1) % 12) + 1
    end_start = start.replace(year=end_year, month=end_month)

    # 未指定月份时保持原逻辑：统计从本周期开始到当前时刻；
    # 指定历史月份时统计完整周期，指定当前月份时截止到当前时刻。
    if month_key is None:
        end = now
    else:
        end = min(now, end_start - timedelta(microseconds=1))
    return start, end


_LOGS_PERIOD_LABELS = {
    "month": "本月",
    "quarter": "本季",
    "half": "半年",
    "year": "今年",
}


def _logs_period_label(period: str, month: Optional[str] = None) -> str:
    """返回综合评估页面使用的周期名称，并校验下载接口的周期参数。"""
    if period not in _LOGS_PERIOD_LABELS:
        raise ValueError("周期参数应为 month/quarter/half/year")
    month_key = _normalize_logs_month(month)
    if month_key:
        anchor = datetime.strptime(month_key, "%Y-%m")
        if period == "month":
            return f"{anchor.year}年{anchor.month}月"
        if period == "quarter":
            return f"{anchor.year}年第{((anchor.month - 1) // 3) + 1}季度"
        if period == "half":
            return f"{anchor.year}年下半年" if anchor.month > 6 else f"{anchor.year}年上半年"
        return f"{anchor.year}年"
    return _LOGS_PERIOD_LABELS[period]


def _logs_text(logs) -> str:
    """合并多条日志 contents（JSON）的 value 为全文。"""
    import json as _json
    parts = []
    for l in logs:
        try:
            contents = _json.loads(l.contents) if l.contents else []
        except Exception:
            contents = []
        parts.extend((c.get("value") or "") for c in contents if c.get("value"))
    return "\n".join(parts)


@app.post("/api/sync-logs")
def sync_logs_api(days: int = Query(180, ge=1, le=180)):
    """从钉钉拉取日志 → 规则评分 → 入库（手动触发）。"""
    from dingtalk_logs_sync import sync_logs
    result = sync_logs(days)
    return {**result, "note": "日志已按规则评分（完整度25/数据20/结构15/规划20/深度20）"}


@app.get("/api/logs-ranking")
def logs_ranking(period: str = Query("month", description="month/quarter/half/year"),
                 dept: str = Query("", description="部门筛选（空=全部）"),
                 month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                 db: Session = Depends(get_db)):
    """管理人员日志评分排名（仅名单内人员，按综合评分降序）。
    综合评估 = 五维日志质量 + 岗位职责契合 + 业绩导向 + 团队管理 + 岗位书写参考维度 → 综合评级 A/B/C/D + 综合点评。"""
    from collections import defaultdict
    from log_eval import (person_profile, evaluate_role_fit,
                          evaluate_industry_focus, evaluate_writing_reference,
                          comprehensive_eval,
                          _PERF_GROUPS, _MGMT_GROUPS)
    from manager_list import MANAGERS, MANAGER_NAMES, TITLE_MAP, get_role_keywords

    month_key = _normalize_logs_month(month)
    start, end = _logs_period_range(period, month_key)
    q = db.query(DailyLog).filter(
        DailyLog.create_time >= start, DailyLog.create_time <= end,
        DailyLog.creator_name.in_(MANAGER_NAMES))
    if dept:
        q = q.filter(DailyLog.dept_name == dept)
    rows = q.all()

    # 全员（名单内）平均 — 作为相对参照（key 不带 score_ 前缀，与 person_profile 对齐）
    all_avg = {}
    if rows:
        n = len(rows)
        for dim in ["completeness", "data", "structure", "planning", "depth"]:
            all_avg[dim] = sum(getattr(l, "score_" + dim) or 0 for l in rows) / n

    groups = defaultdict(list)
    for r in rows:
        groups[r.creator_name].append(r)

    people = []
    for name, title in MANAGERS:
        key_logs = groups.get(name, [])
        if not key_logs:
            people.append({"name": name, "title": title, "dept": "", "log_count": 0,
                           "avg_score": 0, "avg_completeness": 0, "avg_data": 0,
                           "avg_structure": 0, "avg_planning": 0, "avg_depth": 0,
                           "role_fit": 0, "role_hit": [], "role_miss": [],
                           "perf_focus": 0, "mgmt_focus": 0,
                           "writing_reference": evaluate_writing_reference("", title, name),
                           "grade": "", "grade_cn": "—", "comp_score": 0, "comment": "",
                           "strengths": "暂无日志", "improvements": "尚未提交日志",
                           "last_log_time": ""})
            continue
        n = len(key_logs)
        p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in key_logs) / n, 1)
                 for dim in ["completeness", "data", "structure", "planning", "depth"]}
        full_text = _logs_text(key_logs)
        role = evaluate_role_fit(full_text, get_role_keywords(name, title))
        perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
        mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
        writing_ref = evaluate_writing_reference(full_text, title, name)
        profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
        comp = comprehensive_eval(
            round(sum(l.score_total or 0 for l in key_logs) / n, 1),
            role["role_fit"], perf, mgmt,
            role["role_hit"], role["role_miss"],
            profile["top_dim"], profile["weak_dim"], writing_ref["score"])
        latest = max(key_logs, key=lambda l: l.create_time)
        people.append({
            "name": name, "title": title, "dept": key_logs[0].dept_name or "",
            "log_count": n, "avg_score": round(sum(l.score_total or 0 for l in key_logs) / n, 1),
            **{f"avg_{dim}": p_avg[dim] for dim in ["completeness", "data", "structure", "planning", "depth"]},
            "role_fit": role["role_fit"], "role_hit": role["role_hit"], "role_miss": role["role_miss"],
            "perf_focus": perf, "mgmt_focus": mgmt,
            "writing_reference": writing_ref,
            "grade": comp["grade"], "grade_cn": comp["grade_cn"],
            "comp_score": comp["comp_score"], "comment": comp["comment"],
            **profile,
            "last_log_time": latest.create_time.strftime("%Y-%m-%d"),
        })

    # 综合评估看板以最终综合评分排名；日志均分仅作为评分构成中的基础分展示。
    people.sort(key=lambda p: (-(p["log_count"] > 0), -(p["comp_score"] or 0)))
    for i, p in enumerate(people, 1):
        p["rank"] = i if p["log_count"] > 0 else None
    return {
        "period": period,
        "month": month_key or datetime.now().strftime("%Y-%m"),
        "period_label": _logs_period_label(period, month_key),
        "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
        "total_logs": len(rows), "total_people": len(people),
        "people": people,
    }


def _logs_comprehensive_payload(period: str, db: Session, month: Optional[str] = None) -> dict:
    """综合评估下载数据：排名摘要补齐四项评估明细，并按综合评分排序。"""
    month_key = _normalize_logs_month(month)
    label = _logs_period_label(period, month_key)
    summary = logs_ranking(period=period, dept="", month=month_key, db=db)
    people = []
    for item in summary.get("people") or []:
        person = dict(item)
        detail = logs_evaluation(name=person["name"], period=period, month=month_key, db=db)
        person["assess"] = detail.get("assess") or {}
        person["writing_reference"] = detail.get("writing_reference") or person.get("writing_reference") or {}
        person["display_score"] = person.get("comp_score") or 0
        people.append(person)
    people.sort(key=lambda p: (-(1 if p.get("log_count") else 0), -(p.get("display_score") or 0)))
    for index, person in enumerate(people, 1):
        person["rank"] = index if person.get("log_count") else None
    return {
        "period": period,
        "month": month_key or datetime.now().strftime("%Y-%m"),
        "period_label": label,
        "board_kind": "综合评估",
        "start": summary.get("start"),
        "end": summary.get("end"),
        "total_logs": summary.get("total_logs", 0),
        "total_people": summary.get("total_people", 0),
        "people": people,
    }


@app.get("/api/logs-evaluation")
def logs_evaluation(name: str = Query(..., description="人员姓名"),
                    period: str = Query("month"),
                    month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                    db: Session = Depends(get_db)):
    """单人日志评估分析报告：五维雷达 + 岗位职责深度评估（含证据）+ 多条优缺点 + 综合评级 + 深度分析建议。"""
    from manager_list import MANAGER_NAMES, TITLE_MAP, get_role_keywords, LEVEL_MAP, LEVEL_REQ
    from log_eval import (evaluate_role_fit, evaluate_industry_focus,
                          evaluate_writing_reference,
                          comprehensive_eval, person_profile, build_report_items,
                          build_deep_advice, data_dim_label, evaluate_level_fit,
                          weekly_assessment,
                          _PERF_GROUPS, _MGMT_GROUPS)
    title = TITLE_MAP.get(name, "")
    month_key = _normalize_logs_month(month)
    if name not in MANAGER_NAMES:
        return {"name": name, "title": title, "period": period, "month": month_key or datetime.now().strftime("%Y-%m"), "detail": [],
                "radar": [], "recent": [], "total": 0, "avg_score": 0, "role_fit": 0,
                "role_hit": [], "role_miss": [], "role_detail": [],
                "perf_focus": 0, "mgmt_focus": 0,
                "writing_reference": evaluate_writing_reference("", title, name),
                "assess": {"industry": {"score": 0, "comment": "周期内无日志，无法评估行业属性"},
                           "role": {"score": 0, "comment": "周期内无日志，无法评估岗位要求"},
                           "writing_reference": evaluate_writing_reference("", title, name),
                           "writing": {"score": 0, "comment": "周期内无日志，无法评估书写展现"}},
                "grade": "", "grade_cn": "", "comment": "",
                "strengths_list": [], "improvements_list": [],
                "deep_strengths": [], "deep_improvements": []}
    start, end = _logs_period_range(period, month_key)
    rows = (db.query(DailyLog)
            .filter(DailyLog.creator_name == name, DailyLog.create_time >= start, DailyLog.create_time <= end)
            .order_by(DailyLog.create_time).all())
    if not rows:
        return {"name": name, "title": title, "period": period, "month": month_key or datetime.now().strftime("%Y-%m"), "detail": [],
                "radar": [], "recent": [], "total": 0, "avg_score": 0, "role_fit": 0,
                "role_hit": [], "role_miss": [], "role_detail": [],
                "perf_focus": 0, "mgmt_focus": 0,
                "writing_reference": evaluate_writing_reference("", title, name),
                "assess": {"industry": {"score": 0, "comment": "周期内无日志，无法评估行业属性"},
                           "role": {"score": 0, "comment": "周期内无日志，无法评估岗位要求"},
                           "writing_reference": evaluate_writing_reference("", title, name),
                           "writing": {"score": 0, "comment": "周期内无日志，无法评估书写展现"}},
                "grade": "", "grade_cn": "", "comment": "",
                "strengths_list": [], "improvements_list": [],
                "deep_strengths": [], "deep_improvements": []}
    n = len(rows)
    full_text = _logs_text(rows)
    role = evaluate_role_fit(full_text, get_role_keywords(name, title))
    perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
    mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
    avg_score = round(sum(l.score_total or 0 for l in rows) / n, 1)

    # 全员（名单内、同周期）平均 — 相对参照
    all_rows = (db.query(DailyLog)
                .filter(DailyLog.create_time >= start, DailyLog.create_time <= end,
                        DailyLog.creator_name.in_(MANAGER_NAMES)).all())
    all_avg = {}
    if all_rows:
        m = len(all_rows)
        for dim in ["completeness", "data", "structure", "planning", "depth"]:
            all_avg[dim] = sum(getattr(l, "score_" + dim) or 0 for l in all_rows) / m
    p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in rows) / n, 1)
             for dim in ["completeness", "data", "structure", "planning", "depth"]}
    profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
    level = LEVEL_MAP.get(name, "")
    level_req = LEVEL_REQ.get(level, [])
    level_covered, _ = evaluate_level_fit(full_text, level_req)
    # 综合评估与周度评估共用同一套四项评估维度，保证岗位书写参考维度口径一致。
    assess = weekly_assessment(title, full_text, p_avg, role, level, level_covered,
                               level_req, n, name)
    writing_ref = assess["writing_reference"]
    comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                              role["role_hit"], role["role_miss"],
                              profile["top_dim"], profile["weak_dim"], writing_ref["score"])
    items = build_report_items(avg_score, role, perf, mgmt,
                               profile["strengths"], profile["improvements"],
                               writing_ref["score"])
    deep = build_deep_advice(title, get_role_keywords(name, title), role["role_hit"],
                             role["role_miss"], profile["weak_dim"], perf, mgmt,
                             LEVEL_MAP.get(name, ""))
    detail = [{"date": l.create_time.strftime("%Y-%m-%d"), "template": l.template_name,
               "score": l.score_total or 0} for l in rows]
    radar = [
        {"dimension": "内容完整度", "score": round(sum(l.score_completeness or 0 for l in rows) / n, 1), "max": 25},
        {"dimension": data_dim_label(title), "score": round(sum(l.score_data or 0 for l in rows) / n, 1), "max": 20},
        {"dimension": "结构化程度", "score": round(sum(l.score_structure or 0 for l in rows) / n, 1), "max": 15},
        {"dimension": "规划性", "score": round(sum(l.score_planning or 0 for l in rows) / n, 1), "max": 20},
        {"dimension": "复盘深度", "score": round(sum(l.score_depth or 0 for l in rows) / n, 1), "max": 20},
    ]
    recent = [{"date": l.create_time.strftime("%Y-%m-%d"), "score": l.score_total or 0,
               "strengths": l.strengths or "", "improvements": l.improvements or ""}
              for l in rows[-3:]][::-1]
    return {"name": name, "title": title, "period": period, "month": month_key or datetime.now().strftime("%Y-%m"), "detail": detail, "radar": radar,
            "recent": recent, "total": n,
            "avg_score": avg_score,
            "role_fit": role["role_fit"], "role_hit": role["role_hit"],
            "role_miss": role["role_miss"], "role_detail": role["role_detail"],
            "perf_focus": perf, "mgmt_focus": mgmt,
            "writing_reference": writing_ref,
            "assess": assess,
            "grade": comp["grade"], "grade_cn": comp["grade_cn"],
            "comp_score": comp["comp_score"], "comment": comp["comment"],
            "strengths_list": items["strengths_list"], "improvements_list": items["improvements_list"],
            "deep_strengths": deep["deep_strengths"], "deep_improvements": deep["deep_improvements"],
            "strengths": profile["strengths"], "improvements": profile["improvements"]}


# ═══════════════════════════════════════════════════
# 各部门在岗时长统计及分析建议（钉钉多维表 → 清洗 HH时MM分 → 统计/建议）
# ═══════════════════════════════════════════════════

@app.get("/api/onduty-stats")
def onduty_stats(month: str = Query("", description="月份 YYYY-MM，空=最新月份")):
    """各部门在岗时长统计（部门排行/人均/上下班打卡）+ 规则引擎分析建议。"""
    from onduty_bi import get_onduty_stats
    return get_onduty_stats(month or None)


@app.post("/api/sync-onduty")
def sync_onduty(month: str = Query("", description="月份 YYYY-MM，空=最新月份")):
    """强制刷新钉钉在岗时长数据，并返回指定月份统计。"""
    from onduty_bi import sync_onduty_stats
    return sync_onduty_stats(month or None)


@app.get("/api/onduty-detail")
def onduty_detail(dept: str = Query(..., description="部门名"), month: str = Query("")):
    """某部门人员明细（每人平均在岗/上下班打卡）。"""
    from onduty_bi import get_onduty_stats
    data = get_onduty_stats(month or None)
    if data.get("source_error"):
        return {"source_error": data["source_error"], "dept": dept, "persons": []}
    for d in data.get("depts", []):
        if d["dept"] == dept:
            return {"source_error": None, "dept": dept, "month": data["month"],
                    "persons": d["persons"]}
    return {"source_error": None, "dept": dept, "month": data["month"], "persons": []}


# ═══════════════════════════════════════════════════
# 管理人员周度日志评分报告（整改 + 通晒）
# ═══════════════════════════════════════════════════

def _logs_week_bounds(week_label: str) -> tuple:
    """周标签 'YYYY-Www' → (周一 00:00, 下周一 00:00)，ISO 自然周（周一~周日）。"""
    try:
        y, w = str(week_label).split("-W")
        year, week = int(y), int(w)
    except (ValueError, AttributeError):
        raise ValueError(f"周格式应为 YYYY-Www，收到: {week_label}")
    monday = datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u")
    return monday, monday + timedelta(days=7)


def _logs_current_week() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _logs_week_offset(week_label: str, offset: int) -> str:
    monday, _ = _logs_week_bounds(week_label)
    iso = (monday + timedelta(weeks=offset)).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _logs_available_weeks(db) -> list:
    """名单内人员有日志的周标签（近一年），最新在前。"""
    from manager_list import MANAGER_NAMES
    rows = db.query(DailyLog.create_time).filter(
        DailyLog.create_time >= datetime.now() - timedelta(days=365),
        DailyLog.creator_name.in_(MANAGER_NAMES)).all()
    weeks = set()
    for (t,) in rows:
        iso = t.isocalendar()
        weeks.add(f"{iso[0]}-W{iso[1]:02d}")
    return sorted(weeks, reverse=True)


def _weekly_person_dict(name: str, title: str, key_logs: list, all_avg: dict) -> dict:
    """单人周报聚合：五维均分 + 岗位职责 + 业绩/团队 + 综合评级 + 职级覆盖 + 四项评估 + 整改建议。"""
    from log_eval import (person_profile, evaluate_role_fit, evaluate_industry_focus,
                          evaluate_writing_reference,
                          comprehensive_eval, evaluate_level_fit, build_rectify_suggestions,
                          weekly_assessment, _PERF_GROUPS, _MGMT_GROUPS)
    from manager_list import get_role_keywords, LEVEL_MAP, LEVEL_REQ
    level = LEVEL_MAP.get(name, "")
    level_req = LEVEL_REQ.get(level, [])
    if not key_logs:
        return {"name": name, "title": title, "level": level, "dept": "", "log_count": 0,
                "avg_score": 0, "avg_completeness": 0, "avg_data": 0, "avg_structure": 0,
                "avg_planning": 0, "avg_depth": 0, "role_fit": 0, "role_hit": [],
                "role_miss": [], "role_detail": [], "perf_focus": 0, "mgmt_focus": 0,
                "grade": "", "grade_cn": "—", "comp_score": 0, "comment": "",
                "strengths": "暂无日志", "improvements": "尚未提交日志",
                "rectify": ["本周未提交日志，无法评估，建议恢复工作日日志提交"],
                "level_covered": 0, "level_req": level_req, "last_log_time": "",
                "assess": {"industry": {"score": 0, "comment": "本周无日志，无法评估行业属性"},
                           "role": {"score": 0, "comment": "本周无日志，无法评估岗位要求"},
                           "writing_reference": evaluate_writing_reference("", title, name),
                           "writing": {"score": 0, "comment": "本周无日志，无法评估书写展现"}}}
    n = len(key_logs)
    p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in key_logs) / n, 1)
             for dim in ["completeness", "data", "structure", "planning", "depth"]}
    full_text = _logs_text(key_logs)
    role = evaluate_role_fit(full_text, get_role_keywords(name, title))
    perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
    mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
    profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
    avg_score = round(sum(l.score_total or 0 for l in key_logs) / n, 1)
    level_covered, uncov = evaluate_level_fit(full_text, level_req)
    rectify = build_rectify_suggestions(n, role["role_miss"], profile["weak_dim"],
                                        perf, mgmt, level, uncov)
    # 四项评估：电商行业属性 / 岗位要求 / 岗位书写参考维度 / 日报书写展现（各 20 分制 + 评语）
    assess = weekly_assessment(title, full_text, p_avg, role, level, level_covered,
                               level_req, n, name)
    writing_ref = assess["writing_reference"]
    comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                              role["role_hit"], role["role_miss"],
                              profile["top_dim"], profile["weak_dim"], writing_ref["score"])
    if assess["industry"]["score"] < 10:
        family = assess["industry"]["family"]
        rectify.append(f"结合电商行业属性：日志缺少{family}核心经营指标支撑，建议用数据量化经营结果")
    if assess["writing"]["score"] < 10:
        rectify.append("日报书写待改进：内容较零散，建议按『完成-数据-问题-计划』分点书写并提炼结论")
    if writing_ref["score"] < 10:
        rectify.append(f"岗位书写参考维度待补：建议补充「{'、'.join(writing_ref['miss'][:3])}」等板块")
    rectify = rectify[:6]
    latest = max(key_logs, key=lambda l: l.create_time)
    return {"name": name, "title": title, "level": level, "dept": key_logs[0].dept_name or "",
            "log_count": n, "avg_score": avg_score,
            **{f"avg_{dim}": p_avg[dim] for dim in ["completeness", "data", "structure", "planning", "depth"]},
            "role_fit": role["role_fit"], "role_hit": role["role_hit"],
            "role_miss": role["role_miss"], "role_detail": role["role_detail"],
            "perf_focus": perf, "mgmt_focus": mgmt,
            "grade": comp["grade"], "grade_cn": comp["grade_cn"],
            "comp_score": comp["comp_score"], "comment": comp["comment"],
            "strengths": profile["strengths"], "improvements": profile["improvements"],
            "rectify": rectify, "level_covered": level_covered, "level_req": level_req,
            "assess": assess,
            "last_log_time": latest.create_time.strftime("%Y-%m-%d")}


def _logs_weekly_payload(week: str, db) -> dict:
    """周报核心数据（通晒汇总），供 API 与 Excel 导出共用。"""
    from manager_list import MANAGERS, MANAGER_NAMES, TITLE_MAP
    from collections import defaultdict
    if not week:
        weeks = _logs_available_weeks(db)
        week = weeks[0] if weeks else _logs_current_week()
    start, end = _logs_week_bounds(week)
    rows = db.query(DailyLog).filter(
        DailyLog.create_time >= start, DailyLog.create_time < end,
        DailyLog.creator_name.in_(MANAGER_NAMES)).all()

    all_avg = {}
    if rows:
        m = len(rows)
        for dim in ["completeness", "data", "structure", "planning", "depth"]:
            all_avg[dim] = sum(getattr(l, "score_" + dim) or 0 for l in rows) / m

    groups = defaultdict(list)
    for r in rows:
        groups[r.creator_name].append(r)

    people = []
    for name, title in MANAGERS:
        p = _weekly_person_dict(name, title, groups.get(name, []), all_avg)
        p["title"] = TITLE_MAP.get(name, title)
        people.append(p)
    people.sort(key=lambda p: (-(p["log_count"] > 0), -p["avg_score"]))
    for i, p in enumerate(people, 1):
        p["rank"] = i if p["log_count"] > 0 else None
    return {"week": week, "start": start.strftime("%Y-%m-%d"),
            "end": (end - timedelta(seconds=1)).strftime("%Y-%m-%d"),
            "total_logs": len(rows), "people": people}


@app.get("/api/logs-weekly")
def logs_weekly(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                name: str = Query("", description="人员姓名，空=管理人员通晒汇总"),
                db: Session = Depends(get_db)):
    """周度日志评分报告：管理人员通晒汇总或单人周报详情（含整改建议、周环比）。"""
    from manager_list import MANAGER_NAMES, TITLE_MAP, get_role_keywords, LEVEL_MAP, LEVEL_REQ
    from log_eval import (evaluate_role_fit, evaluate_industry_focus, evaluate_writing_reference,
                          comprehensive_eval,
                          person_profile, build_report_items, evaluate_level_fit,
                          build_rectify_suggestions, weekly_assessment, data_dim_label,
                          _PERF_GROUPS, _MGMT_GROUPS)
    payload = _logs_weekly_payload(week, db)
    week = payload["week"]

    if name:
        title = TITLE_MAP.get(name, "")
        if name not in MANAGER_NAMES:
            return {"name": name, "title": title, "week": week, "total": 0,
                    "avg_score": 0, "radar": [], "rectify": [],
                    "prev_week": None, "role_detail": [], "grade": "", "grade_cn": "",
                    "level": "", "level_covered": 0, "level_req": [], "comment": ""}
        start, end = _logs_week_bounds(week)
        rows = (db.query(DailyLog)
                .filter(DailyLog.creator_name == name,
                        DailyLog.create_time >= start, DailyLog.create_time < end)
                .order_by(DailyLog.create_time).all())
        level = LEVEL_MAP.get(name, "")
        level_req = LEVEL_REQ.get(level, [])
        if not rows:
            return {"name": name, "title": title, "week": week, "total": 0, "avg_score": 0,
                    "radar": [], "rectify": ["本周未提交日志，无法评估，建议恢复工作日日志提交"],
                    "prev_week": None, "role_detail": [], "role_fit": 0, "role_hit": [],
                    "role_miss": [], "perf_focus": 0, "mgmt_focus": 0,
                    "grade": "", "grade_cn": "", "comp_score": 0, "comment": "",
                    "strengths_list": [], "improvements_list": [],
                    "level": level, "level_covered": 0, "level_req": level_req,
                    "strengths": "暂无日志", "improvements": "尚未提交日志",
                    "assess": {"industry": {"score": 0, "comment": "本周无日志，无法评估行业属性"},
                               "role": {"score": 0, "comment": "本周无日志，无法评估岗位要求"},
                               "writing_reference": evaluate_writing_reference("", title, name),
                               "writing": {"score": 0, "comment": "本周无日志，无法评估书写展现"}}}
        n = len(rows)
        full_text = _logs_text(rows)
        role = evaluate_role_fit(full_text, get_role_keywords(name, title))
        perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
        mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
        avg_score = round(sum(l.score_total or 0 for l in rows) / n, 1)
        p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in rows) / n, 1)
                 for dim in ["completeness", "data", "structure", "planning", "depth"]}
        # 同周全员平均（相对参照）
        all_rows = (db.query(DailyLog)
                    .filter(DailyLog.create_time >= start, DailyLog.create_time < end,
                            DailyLog.creator_name.in_(MANAGER_NAMES)).all())
        all_avg = {}
        if all_rows:
            m = len(all_rows)
            for dim in ["completeness", "data", "structure", "planning", "depth"]:
                all_avg[dim] = sum(getattr(l, "score_" + dim) or 0 for l in all_rows) / m
        profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
        level_covered, uncov = evaluate_level_fit(full_text, level_req)
        rectify = build_rectify_suggestions(n, role["role_miss"], profile["weak_dim"],
                                            perf, mgmt, level, uncov)
        # 四项评估：电商行业属性 / 岗位要求 / 岗位书写参考维度 / 日报书写展现（各 20 分制 + 评语）
        assess = weekly_assessment(title, full_text, p_avg, role, level, level_covered,
                                   level_req, n, name)
        writing_ref = assess["writing_reference"]
        comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                                  role["role_hit"], role["role_miss"],
                                  profile["top_dim"], profile["weak_dim"], writing_ref["score"])
        items = build_report_items(avg_score, role, perf, mgmt,
                                   profile["strengths"], profile["improvements"],
                                   writing_ref["score"])
        if assess["industry"]["score"] < 10:
            rectify.append(f"结合电商行业属性：日志缺少{assess['industry']['family']}核心经营指标支撑，建议用数据量化经营结果")
        if assess["writing"]["score"] < 10:
            rectify.append("日报书写待改进：内容较零散，建议按『完成-数据-问题-计划』分点书写并提炼结论")
        if writing_ref["score"] < 10:
            rectify.append(f"岗位书写参考维度待补：建议补充「{'、'.join(writing_ref['miss'][:3])}」等板块")
        rectify = rectify[:6]
        # 周环比（上周）
        prev_label = _logs_week_offset(week, -1)
        p_start, p_end = _logs_week_bounds(prev_label)
        prev_rows = (db.query(DailyLog)
                     .filter(DailyLog.creator_name == name,
                             DailyLog.create_time >= p_start, DailyLog.create_time < p_end).all())
        prev = None
        if prev_rows:
            pn = len(prev_rows)
            p_avg_score = round(sum(l.score_total or 0 for l in prev_rows) / pn, 1)
            p_text = _logs_text(prev_rows)
            p_role = evaluate_role_fit(p_text, get_role_keywords(name, title))
            p_comp = comprehensive_eval(p_avg_score, p_role["role_fit"],
                                        evaluate_industry_focus(p_text, _PERF_GROUPS),
                                        evaluate_industry_focus(p_text, _MGMT_GROUPS),
                                        p_role["role_hit"], p_role["role_miss"],
                                        writing_ref=evaluate_writing_reference(p_text, title, name)["score"])
            prev = {"week": prev_label, "log_count": pn, "avg_score": p_avg_score,
                    "grade": p_comp["grade"], "grade_cn": p_comp["grade_cn"],
                    "delta": round(avg_score - p_avg_score, 1)}
        radar = [
            {"dimension": "内容完整度", "score": p_avg["completeness"], "max": 25},
            {"dimension": data_dim_label(title), "score": p_avg["data"], "max": 20},
            {"dimension": "结构化程度", "score": p_avg["structure"], "max": 15},
            {"dimension": "规划性", "score": p_avg["planning"], "max": 20},
            {"dimension": "复盘深度", "score": p_avg["depth"], "max": 20},
        ]
        return {"name": name, "title": title, "week": week, "total": n,
                "avg_score": avg_score, "radar": radar,
                "role_fit": role["role_fit"], "role_hit": role["role_hit"],
                "role_miss": role["role_miss"], "role_detail": role["role_detail"],
                "perf_focus": perf, "mgmt_focus": mgmt,
                "grade": comp["grade"], "grade_cn": comp["grade_cn"],
                "comp_score": comp["comp_score"], "comment": comp["comment"],
                "strengths_list": items["strengths_list"], "improvements_list": items["improvements_list"],
                "strengths": profile["strengths"], "improvements": profile["improvements"],
                "rectify": rectify, "prev_week": prev,
                "level": level, "level_covered": level_covered, "level_req": level_req,
                "assess": assess}

    return {"week": week, "start": payload["start"], "end": payload["end"],
            "total_logs": payload["total_logs"], "people": payload["people"]}


def _weekly_report_file(week: str, name: str):
    """Return the persisted PNG path for one manager and one ISO week."""
    import re
    from pathlib import Path

    if not re.fullmatch(r"\d{4}-W\d{2}", str(week)):
        raise ValueError("周格式应为 YYYY-Www")
    _logs_week_bounds(week)  # validate the calendar week as well
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(name)).strip("_") or "manager"
    folder = Path(__file__).resolve().parent / "generated_reports" / "weekly" / str(week)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{safe_name}.png"


def _comprehensive_report_folder(period: str, month: Optional[str] = None):
    """Return the persisted report directory, namespaced by selected month when provided."""
    from pathlib import Path

    month_key = _normalize_logs_month(month)
    _logs_period_label(period, month_key)
    folder = Path(__file__).resolve().parent / "generated_reports" / "comprehensive" / period
    if month_key:
        folder = folder / month_key
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _comprehensive_report_file(period: str, name: str, month: Optional[str] = None):
    """Return the persisted PNG path for one manager and one comprehensive period."""
    import re

    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(name)).strip("_") or "manager"
    return _comprehensive_report_folder(period, month) / f"{safe_name}.png"


def _comprehensive_ranking_report_file(period: str, month: Optional[str] = None):
    """Return the persisted PNG path for one comprehensive ranking board."""
    return _comprehensive_report_folder(period, month) / "管理人员综合评估排名看板.png"


def _weekly_report_font(size: int, bold: bool = False):
    """Use a Chinese-capable system font, with a safe PIL fallback."""
    from PIL import ImageFont
    candidates = (
        [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"]
        if bold else [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _weekly_report_lines(draw, text, font, max_width: int):
    """Wrap Chinese/Latin text by rendered width for the PNG report."""
    raw = str(text or "—")
    lines = []
    for paragraph in raw.splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current or " ")
    return lines


def _weekly_report_text(draw, text, xy, font, fill, max_width: int, line_gap: int = 7, max_lines=None):
    lines = _weekly_report_lines(draw, text, font, max_width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1].rstrip("。；， ") + "…"
    line_height = font.getbbox("中")[3] - font.getbbox("中")[1] + line_gap
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _weekly_report_num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _render_weekly_report_png(report: dict, output_path):
    """Render one person's weekly or comprehensive score report and persist it as a PNG."""
    import math
    from datetime import datetime as dt
    from PIL import Image, ImageDraw

    width, height = 1400, 1900
    bg = "#f6f7fb"
    indigo = "#4f46e5"
    text = "#182033"
    muted = "#64748b"
    green = "#059669"
    amber = "#d97706"
    red = "#dc2626"
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    f_title = _weekly_report_font(40, True)
    f_name = _weekly_report_font(30, True)
    f_section = _weekly_report_font(24, True)
    f_body = _weekly_report_font(20)
    f_small = _weekly_report_font(17)
    f_score = _weekly_report_font(56, True)
    f_metric = _weekly_report_font(25, True)

    def card(box, fill="#ffffff", outline="#e5e7eb", radius=18):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    name = report.get("name") or "管理人员"
    title = report.get("title") or ""
    week = report.get("week") or ""
    week_label = str(week).replace("-W", "年第") + "周"
    report_kind = report.get("report_kind") or "周度"
    period_label = report.get("period_label") or week_label
    scope_label = report.get("scope_label") or period_label
    average_label = "周均分" if report_kind == "周度" else "周期均分"
    cycle_word = "本周" if report_kind == "周度" else "本周期"

    draw.rectangle((0, 0, width, 205), fill=indigo)
    draw.text((65, 42), f"管理人员{report_kind}日志评分报告", font=f_title, fill="#ffffff")
    draw.text((65, 112), f"{name}  ·  {title}", font=f_name, fill="#e0e7ff")
    draw.text((width - 65, 62), period_label, font=f_section, fill="#ffffff", anchor="ra")
    draw.text((width - 65, 112), f"生成于 {dt.now().strftime('%Y-%m-%d %H:%M')}", font=f_small, fill="#c7d2fe", anchor="ra")

    card((55, 245, 790, 760))
    draw.text((90, 280), "五维日志质量雷达", font=f_section, fill=text)
    radar = report.get("radar") or []
    center = (420, 570)
    radius = 165
    if radar:
        count = len(radar)

        def point_at(index, scale):
            angle = -math.pi / 2 + index * 2 * math.pi / count
            return (center[0] + math.cos(angle) * radius * scale,
                    center[1] + math.sin(angle) * radius * scale)

        for scale in (0.25, 0.5, 0.75, 1.0):
            grid = [point_at(i, scale) for i in range(count)]
            draw.line(grid + [grid[0]], fill="#cbd5e1", width=2)
        values = []
        for i, item in enumerate(radar):
            max_value = float(item.get("max") or 1)
            score_value = max(0.0, min(max_value, float(item.get("score") or 0)))
            values.append(point_at(i, score_value / max_value))
            draw.line([center, point_at(i, 1.0)], fill="#dbe4f0", width=2)
            label_point = point_at(i, 1.18)
            draw.multiline_text(label_point, str(item.get("dimension") or ""), font=f_small,
                                fill=text, anchor="mm", align="center", spacing=2)
        draw.polygon(values, fill="#c7d2fe", outline=indigo)
        draw.line(values + [values[0]], fill=indigo, width=5, joint="curve")
        for x, y in values:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=indigo, outline="#ffffff", width=3)
    else:
        draw.text(center, f"{cycle_word}暂无日志评分数据", font=f_body, fill=muted, anchor="mm")

    card((875, 245, 1345, 760))
    draw.text((915, 280), "维度评分", font=f_section, fill=text)
    y = 345
    for item in radar:
        score_value = float(item.get("score") or 0)
        max_value = float(item.get("max") or 0)
        ratio = max(0.0, min(1.0, score_value / max_value)) if max_value else 0
        label = f"{item.get('dimension', '')}  {_weekly_report_num(score_value)}/{_weekly_report_num(max_value)}"
        draw.text((915, y), label, font=f_body, fill=text)
        draw.rounded_rectangle((915, y + 34, 1305, y + 52), radius=9, fill="#e5e7eb")
        if ratio:
            draw.rounded_rectangle((915, y + 34, 915 + 390 * ratio, y + 52), radius=9, fill=indigo)
        y += 105
    if not radar:
        draw.text((915, 350), "暂无可展示的维度评分", font=f_body, fill=muted)

    card((55, 795, 790, 1005), fill="#eef2ff", outline="#c7d2fe")
    draw.text((90, 835), average_label, font=f_body, fill=muted)
    draw.text((90, 875), _weekly_report_num(report.get("avg_score")), font=f_score, fill=indigo)
    draw.text((420, 835), "评级", font=f_body, fill=muted)
    draw.text((420, 875), report.get("grade_cn") or "—", font=f_score,
              fill=green if report.get("grade") in ("A", "B") else amber)

    metrics = [
        ("日志篇数", f"{report.get('total') or 0} 篇"),
        ("岗位职责契合", f"{_weekly_report_num(report.get('role_fit'))}/20"),
        ("业绩导向", f"{_weekly_report_num(report.get('perf_focus'))}/20"),
        ("团队管理", f"{_weekly_report_num(report.get('mgmt_focus'))}/20"),
    ]
    x = 875
    for label, value in metrics:
        card((x, 795, x + 110, 1005))
        draw.text((x + 55, 835), label, font=f_small, fill=muted, anchor="ma")
        draw.text((x + 55, 910), value, font=f_metric, fill=indigo, anchor="ma")
        x += 118

    draw.text((55, 1050), "补充评估", font=f_section, fill=text)
    assess = report.get("assess") or {}
    assess_items = [("电商行业属性", "industry"), ("岗位要求契合", "role"),
                    ("岗位书写维度", "writing_reference"), ("日报书写展现", "writing")]
    x = 55
    for label, key in assess_items:
        item = assess.get(key) or {}
        score = item.get("score", 0)
        card((x, 1095, x + 320, 1265))
        draw.text((x + 24, 1120), label, font=f_body, fill=text)
        draw.text((x + 294, 1120), f"{_weekly_report_num(score)}/20", font=f_metric,
                  fill=green if float(score or 0) >= 15 else amber if float(score or 0) >= 10 else red, anchor="ra")
        _weekly_report_text(draw, item.get("comment") or "本周无日志，无法评估", (x + 24, 1170), f_small, muted, 272, max_lines=3)
        x += 335

    def list_box(box, heading, values, color):
        card(box)
        x0, y0, x1, y1 = box
        draw.text((x0 + 25, y0 + 22), heading, font=f_section, fill=color)
        current = y0 + 68
        items = values or ["暂无记录"]
        for value in items:
            current = _weekly_report_text(draw, "• " + str(value), (x0 + 25, current), f_small, text,
                                          x1 - x0 - 50, line_gap=5, max_lines=3) + 10
            if current > y1 - 28:
                break

    list_box((55, 1310, 675, 1585), f"{cycle_word}优点", report.get("strengths_list"), green)
    list_box((725, 1310, 1345, 1585), "需改进方向", report.get("improvements_list"), amber)
    list_box((55, 1615, 675, 1835), "整改建议", report.get("rectify"), red)
    card((725, 1615, 1345, 1835), fill="#eef2ff", outline="#c7d2fe")
    draw.text((750, 1640), "综合评估意见", font=f_section, fill=indigo)
    _weekly_report_text(draw, report.get("comment") or "暂无综合评估意见", (750, 1690), f_small, text, 570, line_gap=7, max_lines=6)
    draw.text((55, 1870), f"数据周期：{scope_label}  ·  本图片由管理人员日志评分报告自动生成", font=f_small, fill=muted)

    tmp_path = output_path.with_suffix(".tmp.png")
    image.save(tmp_path, format="PNG", optimize=True)
    tmp_path.replace(output_path)


def _weekly_ranking_report_file(week: str):
    """Return the persisted PNG path for a weekly management ranking board."""
    import re
    from pathlib import Path

    if not re.fullmatch(r"\d{4}-W\d{2}", week or ""):
        raise ValueError("周标签格式应为 YYYY-Www")
    folder = Path(__file__).resolve().parent / "generated_reports" / "weekly" / week
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "管理人员周度评分排名看板.png"


def _render_weekly_ranking_png(payload: dict, output_path):
    """Render a weekly or comprehensive ranking board as a downloadable PNG."""
    from PIL import Image, ImageDraw

    width = 1900
    row_height = 88
    header_height = 56
    top_height = 370
    footer_height = 70
    people = payload.get("people") or []
    height = top_height + header_height + row_height * len(people) + footer_height

    bg = "#f8fafc"
    text = "#1e293b"
    muted = "#64748b"
    indigo = "#4f46e5"
    green = "#059669"
    amber = "#d97706"
    red = "#dc2626"
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    f_title = _weekly_report_font(38, True)
    f_subtitle = _weekly_report_font(20)
    f_section = _weekly_report_font(23, True)
    f_card = _weekly_report_font(27, True)
    f_card_label = _weekly_report_font(16)
    f_header = _weekly_report_font(16, True)
    f_body = _weekly_report_font(17)
    f_body_bold = _weekly_report_font(18, True)
    f_small = _weekly_report_font(15)
    board_kind = payload.get("board_kind") or "周度"
    period_label = payload.get("period_label") or payload.get("week") or "—"
    is_weekly = board_kind == "周度"
    score_label = "周均分" if is_weekly else "综合评分"
    submitted_label = "本周提交人数" if is_weekly else "本周期提交人数"
    logs_label = "本周日志总数" if is_weekly else "本周期日志总数"

    def card(box, fill="#ffffff", outline="#e2e8f0", radius=16):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

    draw.text((55, 45), f"{board_kind}管理人员日报评分排名看板", font=f_title, fill=text)
    draw.text((58, 104),
              f"{payload.get('start', '—')} ~ {payload.get('end', '—')}  ·  {period_label}  ·  {score_label}降序",
              font=f_subtitle, fill=muted)

    submitted = [p for p in people if (p.get("log_count") or 0) > 0]
    total_logs = payload.get("total_logs") or 0
    avg = (sum(float((p.get("avg_score") if is_weekly else p.get("display_score")) or 0)
              for p in submitted) / len(submitted)) if submitted else 0
    ab_count = sum(1 for p in submitted if p.get("grade") in ("A", "B"))
    cards = [
        (submitted_label, f"{len(submitted)} / {len(people)}", indigo),
        (logs_label, f"{total_logs}", green),
        (f"全员{score_label}", f"{avg:.1f}", indigo),
        ("评级 A/B 人数", f"{ab_count} / {len(submitted)}", amber),
    ]
    card_width = 390
    for i, (label, value, color) in enumerate(cards):
        x = 55 + i * (card_width + 12)
        card((x, 155, x + card_width, 285))
        draw.text((x + 24, 180), label, font=f_card_label, fill=muted)
        draw.text((x + 24, 215), value, font=f_card, fill=color)

    draw.text((55, 323), "人员评分排名明细", font=f_section, fill=text)

    columns = [
        ("排名", 60), ("姓名", 110), ("岗位", 190), ("部门", 140), ("篇数", 65),
        (score_label, 95), ("评级", 90), ("行业", 85), ("岗位", 85), ("书写维度", 95), ("书写", 85),
        ("核心优点", 230), ("需改进", 230), ("整改建议", 235),
    ]
    x_positions = [55]
    for _, column_width in columns:
        x_positions.append(x_positions[-1] + column_width)
    table_top = top_height
    draw.rectangle((55, table_top, x_positions[-1], table_top + header_height), fill=indigo)
    for index, (label, _) in enumerate(columns):
        x0, x1 = x_positions[index], x_positions[index + 1]
        draw.text(((x0 + x1) / 2, table_top + 18), label, font=f_header, fill="#ffffff", anchor="mm")

    def assess_score(person, key):
        if not person.get("log_count"):
            return "—"
        item = (person.get("assess") or {}).get(key) or {}
        return _weekly_report_num(item.get("score")) if item.get("score") is not None else "—"

    def cell_text(value, x0, y0, x1, font=f_body, fill=text, max_lines=2, center=False):
        raw = str(value or "—")
        lines = _weekly_report_lines(draw, raw, font, max(20, x1 - x0 - 18))
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip("。；， ") + "…"
        line_height = 24 if font == f_body_bold else 22
        total_height = len(lines) * line_height
        y = y0 + max(10, (row_height - total_height) // 2)
        for line in lines:
            if center:
                draw.text(((x0 + x1) / 2, y), line, font=font, fill=fill, anchor="ma")
            else:
                draw.text((x0 + 9, y), line, font=font, fill=fill)
            y += line_height

    for row_index, person in enumerate(people):
        y0 = table_top + header_height + row_index * row_height
        y1 = y0 + row_height
        row_fill = "#ffffff" if row_index % 2 == 0 else "#f1f5f9"
        draw.rectangle((55, y0, x_positions[-1], y1), fill=row_fill)
        draw.line((55, y1, x_positions[-1], y1), fill="#e2e8f0", width=1)
        grade = person.get("grade_cn") or "—"
        grade_color = green if person.get("grade") in ("A", "B") else amber if person.get("grade") == "C" else red
        values = [
            (person.get("rank") or "—", f_body_bold, indigo, True),
            (person.get("name") or "—", f_body_bold, text, False),
            (person.get("title") or "—", f_body, text, False),
            (person.get("dept") or "—", f_body, text, False),
            (person.get("log_count") or 0, f_body, text, True),
            (person.get("display_score") if not is_weekly else person.get("avg_score"), f_body_bold, indigo, True),
            (grade, f_body_bold, grade_color, True),
            (assess_score(person, "industry"), f_body, text, True),
            (assess_score(person, "role"), f_body, text, True),
            (assess_score(person, "writing_reference"), f_body, text, True),
            (assess_score(person, "writing"), f_body, text, True),
            (person.get("strengths") or "—", f_small, green, False),
            (person.get("improvements") or "—", f_small, amber, False),
            ("；".join(person.get("rectify") or []) or "—", f_small, red, False),
        ]
        for index, (value, font, fill, center) in enumerate(values):
            cell_text(value, x_positions[index], y0, x_positions[index + 1], font, fill, max_lines=3 if index >= 10 else 2, center=center)

    footer_y = table_top + header_height + row_height * len(people) + 22
    draw.text((55, footer_y), f"数据来源：管理人员日报{board_kind}评估 · 图片由排名看板自动生成", font=f_small, fill=muted)

    tmp_path = output_path.with_suffix(".tmp.png")
    image.save(tmp_path, format="PNG", optimize=True)
    tmp_path.replace(output_path)


@app.get("/api/logs-weekly-person-image")
def logs_weekly_person_image(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                             name: str = Query(..., description="管理人员姓名"),
                             db: Session = Depends(get_db)):
    """生成并下载单个管理人员的周度日志评分 PNG 报告。"""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from manager_list import MANAGER_NAMES

    if name not in MANAGER_NAMES:
        raise HTTPException(status_code=404, detail="未找到该管理人员")
    report = logs_weekly(week=week, name=name, db=db)
    report_week = report.get("week") or week
    try:
        output_path = _weekly_report_file(report_week, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _render_weekly_report_png(report, output_path)
    filename = f"{name}_{report_week}_周度日志评分报告.png"
    return FileResponse(output_path, media_type="image/png", filename=filename)


@app.get("/api/logs-weekly-ranking-image")
def logs_weekly_ranking_image(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                              db: Session = Depends(get_db)):
    """生成并下载当前周管理人员评分排名看板 PNG。"""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    payload = logs_weekly(week=week, name="", db=db)
    report_week = payload.get("week") or week
    if not payload.get("people"):
        raise HTTPException(status_code=404, detail="当前周暂无管理人员评分排名")
    try:
        output_path = _weekly_ranking_report_file(report_week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _render_weekly_ranking_png(payload, output_path)
    filename = f"{report_week}_管理人员周度评分排名看板.png"
    return FileResponse(output_path, media_type="image/png", filename=filename)


@app.get("/api/logs-weekly-person-images-zip")
def logs_weekly_person_images_zip(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                                  db: Session = Depends(get_db)):
    """批量生成并下载当前周全部管理人员的独立 PNG 周报。"""
    import io
    import zipfile
    from urllib.parse import quote
    from fastapi import HTTPException
    from fastapi.responses import Response

    from manager_list import MANAGER_NAMES

    payload = logs_weekly(week=week, name="", db=db)
    report_week = payload.get("week") or week
    people = payload.get("people") or []
    if not people:
        raise HTTPException(status_code=404, detail="当前周暂无管理人员周报")

    archive = io.BytesIO()
    written = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for summary in people:
            name = summary.get("name")
            if not name or name not in MANAGER_NAMES:
                continue
            report = logs_weekly(week=report_week, name=name, db=db)
            output_path = _weekly_report_file(report_week, name)
            _render_weekly_report_png(report, output_path)
            bundle.write(output_path, arcname=f"{report_week}/{output_path.name}")
            written += 1

    if not written:
        raise HTTPException(status_code=404, detail="当前周没有可下载的管理人员周报")

    filename = f"{report_week}_管理人员周度日志评分报告.zip"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
    }
    return Response(content=archive.getvalue(), media_type="application/zip", headers=headers)


def _comprehensive_report_view(period: str, name: str, db: Session, month: Optional[str] = None) -> dict:
    """补充综合评估图片所需的周期文案。"""
    month_key = _normalize_logs_month(month)
    label = _logs_period_label(period, month_key)
    start, end = _logs_period_range(period, month_key)
    report = dict(logs_evaluation(name=name, period=period, month=month_key, db=db))
    report["report_kind"] = "综合评估"
    report["period_label"] = label
    report["scope_label"] = f"{label}（{start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')}）"
    return report


@app.get("/api/logs-comprehensive-person-image")
def logs_comprehensive_person_image(period: str = Query("month", description="month/quarter/half/year"),
                                    name: str = Query(..., description="管理人员姓名"),
                                    month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                                    db: Session = Depends(get_db)):
    """生成并下载单个管理人员当前综合评估周期 PNG 报告。"""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from manager_list import MANAGER_NAMES

    if name not in MANAGER_NAMES:
        raise HTTPException(status_code=404, detail="未找到该管理人员")
    try:
        month_key = _normalize_logs_month(month)
        report = _comprehensive_report_view(period, name, db, month_key)
        output_path = _comprehensive_report_file(period, name, month_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _render_weekly_report_png(report, output_path)
    filename = f"{name}_{report.get('period_label') or period}_综合评估报告.png"
    return FileResponse(output_path, media_type="image/png", filename=filename)


@app.get("/api/logs-comprehensive-ranking-image")
def logs_comprehensive_ranking_image(period: str = Query("month", description="month/quarter/half/year"),
                                     month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                                     db: Session = Depends(get_db)):
    """生成并下载当前综合评估周期管理人员排名看板 PNG。"""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    try:
        month_key = _normalize_logs_month(month)
        payload = _logs_comprehensive_payload(period, db, month_key)
        output_path = _comprehensive_ranking_report_file(period, month_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _render_weekly_ranking_png(payload, output_path)
    filename = f"{payload.get('period_label') or period}_管理人员综合评估排名看板.png"
    return FileResponse(output_path, media_type="image/png", filename=filename)


@app.get("/api/logs-comprehensive-person-images-zip")
def logs_comprehensive_person_images_zip(period: str = Query("month", description="month/quarter/half/year"),
                                         month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                                         db: Session = Depends(get_db)):
    """批量生成并下载当前综合评估周期每位管理人员的独立 PNG 报告。"""
    import io
    import zipfile
    from urllib.parse import quote
    from fastapi import HTTPException
    from fastapi.responses import Response
    from manager_list import MANAGER_NAMES

    try:
        month_key = _normalize_logs_month(month)
        _logs_period_label(period, month_key)
        payload = _logs_comprehensive_payload(period, db, month_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    people = payload.get("people") or []
    if not people:
        raise HTTPException(status_code=404, detail="当前综合评估周期暂无管理人员报告")

    archive = io.BytesIO()
    written = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for summary in people:
            name = summary.get("name")
            if not name or name not in MANAGER_NAMES:
                continue
            report = _comprehensive_report_view(period, name, db, month_key)
            output_path = _comprehensive_report_file(period, name, month_key)
            _render_weekly_report_png(report, output_path)
            bundle.write(output_path, arcname=f"{month_key or period}/{output_path.name}")
            written += 1
    if not written:
        raise HTTPException(status_code=404, detail="当前综合评估周期没有可下载的管理人员报告")

    filename = f"{payload.get('period_label') or period}_管理人员综合评估报告.zip"
    return Response(content=archive.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@app.get("/api/logs-comprehensive-export")
def logs_comprehensive_export(period: str = Query("month", description="month/quarter/half/year"),
                              month: Optional[str] = Query(None, description="评估月份 YYYY-MM；空=当前月份"),
                              db: Session = Depends(get_db)):
    """导出当前综合评估周期的排名汇总与个人维度明细 Excel。"""
    import io
    from fastapi.responses import Response
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from urllib.parse import quote

    try:
        month_key = _normalize_logs_month(month)
        payload = _logs_comprehensive_payload(period, db, month_key)
        period_label = payload["period_label"]
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "综合评估排名"
    headers = ["排名", "姓名", "岗位", "部门", "篇数", "日志均分", "综合评分", "评级",
               "电商行业属性/20", "岗位要求/20", "岗位书写维度/20", "日报书写展现/20",
               "岗位契合/20", "业绩导向/20", "团队管理/20", "岗位书写覆盖",
               "核心优点", "需改进", "综合点评"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4F46E5")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for person in payload["people"]:
        assess = person.get("assess") or {}
        ref = assess.get("writing_reference") or {}
        has_logs = bool(person.get("log_count"))
        score = lambda key: (assess.get(key) or {}).get("score", 0) if has_logs else "—"
        ws.append([
            person.get("rank") if has_logs else "—", person.get("name"), person.get("title"), person.get("dept"),
            person.get("log_count") or "—", person.get("avg_score") if has_logs else "—",
            person.get("comp_score") if has_logs else "—", person.get("grade") or "—",
            score("industry"), score("role"), score("writing_reference"), score("writing"),
            person.get("role_fit") if has_logs else "—", person.get("perf_focus") if has_logs else "—",
            person.get("mgmt_focus") if has_logs else "—", "、".join(ref.get("hit") or []) or "无",
            person.get("strengths") or "—", person.get("improvements") or "—", person.get("comment") or "—",
        ])
    widths = [6, 10, 16, 14, 7, 9, 9, 7, 12, 12, 14, 14, 10, 10, 10, 30, 34, 34, 44]
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + index)].width = width
    ws.freeze_panes = "A2"

    detail = wb.create_sheet("个人综合评估明细")
    detail_headers = ["姓名", "岗位", "部门", "篇数", "日志均分", "综合评分", "评级", "评估周期",
                      "电商行业属性/20", "岗位要求/20", "岗位书写维度/20", "日报书写展现/20",
                      "岗位书写模板", "模板核心要求", "已覆盖书写维度", "待补书写维度", "覆盖评语"]
    detail.append(detail_headers)
    for cell in detail[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="059669")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for person in payload["people"]:
        assess = person.get("assess") or {}
        ref = assess.get("writing_reference") or {}
        has_logs = bool(person.get("log_count"))
        score = lambda key: (assess.get(key) or {}).get("score", 0) if has_logs else "—"
        detail.append([
            person.get("name"), person.get("title"), person.get("dept"), person.get("log_count") or "—",
            person.get("avg_score") if has_logs else "—", person.get("comp_score") if has_logs else "—",
            person.get("grade") or "—", period_label, score("industry"), score("role"),
            score("writing_reference"), score("writing"), ref.get("template") or "—", ref.get("core") or "—",
            "、".join(ref.get("hit") or []) or "无", "、".join(ref.get("miss") or []) or "无",
            ref.get("comment") or "—",
        ])
    detail_widths = [10, 16, 14, 7, 9, 9, 7, 10, 12, 12, 14, 14, 22, 34, 34, 34, 48]
    for index, width in enumerate(detail_widths, 1):
        detail.column_dimensions[chr(64 + index)].width = width
    detail.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{period_label}_管理人员综合评估.xlsx"
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="comprehensive_{period}.xlsx"; filename*=UTF-8\'\'{quote(filename)}'})


@app.get("/api/logs-weekly-weeks")
def logs_weekly_weeks(db: Session = Depends(get_db)):
    """有日志的周列表（最新在前），供周选择器。"""
    return {"weeks": _logs_available_weeks(db), "current": _logs_current_week()}


@app.get("/api/logs-weekly-trend")
def logs_weekly_trend(name: str = Query(...), weeks: int = Query(8, ge=2, le=26),
                      db: Session = Depends(get_db)):
    """个人近 N 周评分趋势（整改效果跟踪）。"""
    from manager_list import MANAGER_NAMES, TITLE_MAP, get_role_keywords
    if name not in MANAGER_NAMES:
        raise HTTPException(status_code=404, detail="未找到该管理人员")
    from log_eval import (evaluate_role_fit, evaluate_industry_focus, evaluate_writing_reference,
                          comprehensive_eval,
                          _PERF_GROUPS, _MGMT_GROUPS)
    cur = _logs_current_week()
    trend = []
    for i in range(weeks - 1, -1, -1):
        wl = _logs_week_offset(cur, -i)
        start, end = _logs_week_bounds(wl)
        rows = (db.query(DailyLog)
                .filter(DailyLog.creator_name == name,
                        DailyLog.create_time >= start, DailyLog.create_time < end).all())
        n = len(rows)
        avg = round(sum(l.score_total or 0 for l in rows) / n, 1) if n else 0
        grade = ""
        if n:
            text = _logs_text(rows)
            title = TITLE_MAP.get(name, "")
            role = evaluate_role_fit(text, get_role_keywords(name, title))
            comp = comprehensive_eval(avg, role["role_fit"],
                                      evaluate_industry_focus(text, _PERF_GROUPS),
                                      evaluate_industry_focus(text, _MGMT_GROUPS),
                                      role["role_hit"], role["role_miss"],
                                      writing_ref=evaluate_writing_reference(text, title, name)["score"])
            grade = comp["grade"]
        trend.append({"week": wl, "log_count": n, "avg_score": avg, "grade": grade})
    return {"name": name, "trend": trend}


@app.get("/api/logs-weekly-export")
def logs_weekly_export(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                       db: Session = Depends(get_db)):
    """周报 Excel 导出（通晒用）：sheet1 管理人员汇总 + sheet2 个人周报明细。"""
    import io
    from fastapi.responses import Response
    payload = _logs_weekly_payload(week, db)
    week = payload["week"]
    people = payload["people"]

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "周报通晒汇总"
    headers = ["排名", "姓名", "岗位", "职级", "部门", "篇数", "周均分", "评级", "行业属性", "岗位要求", "岗位书写维度", "书写展现", "岗位契合", "业绩导向", "团队管理", "核心优点", "需改进", "整改建议", "综合点评"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4F46E5")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for p in people:
        asc = p.get("assess") or {}
        ws.append([
            p.get("rank") if p.get("log_count") else "—", p["name"], p["title"], p["level"], p["dept"],
            p["log_count"] or "—", p["avg_score"] or "—",
            p["grade"] or "—",
            (asc.get("industry") or {}).get("score", 0) if p.get("log_count") else "—",
            (asc.get("role") or {}).get("score", 0) if p.get("log_count") else "—",
            (asc.get("writing_reference") or {}).get("score", 0) if p.get("log_count") else "—",
            (asc.get("writing") or {}).get("score", 0) if p.get("log_count") else "—",
            p["role_fit"], p["perf_focus"], p["mgmt_focus"],
            p["strengths"], p["improvements"],
            "；".join(p["rectify"]) if p.get("rectify") else "",
            p["comment"],
        ])
    width_map = [6, 10, 14, 8, 12, 6, 8, 6, 8, 8, 10, 8, 9, 9, 9, 34, 34, 44, 44]
    for i, wd in enumerate(width_map, 1):
        ws.column_dimensions[chr(64 + i)].width = wd
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("个人周报明细")
    ws2.append(["姓名", "岗位", "职级", "部门", "篇数", "周均分", "评级", "行业属性/20", "岗位要求/20", "岗位书写维度/20", "书写展现/20",
                "完整度/25", "数据/20", "结构/15", "规划/20", "深度/20",
                "岗位职责覆盖", "业绩导向/20", "团队管理/20", "核心优点", "需改进", "整改建议", "综合点评"])
    for c in ws2[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="059669")
    for p in people:
        hits = "、".join(p.get("role_hit") or []) or "无"
        asc = p.get("assess") or {}
        ws2.append([p["name"], p["title"], p["level"], p["dept"], p["log_count"] or "—",
                    p["avg_score"] or "—", p["grade"] or "—",
                    (asc.get("industry") or {}).get("score", 0) if p.get("log_count") else "—",
                    (asc.get("role") or {}).get("score", 0) if p.get("log_count") else "—",
                    (asc.get("writing_reference") or {}).get("score", 0) if p.get("log_count") else "—",
                    (asc.get("writing") or {}).get("score", 0) if p.get("log_count") else "—",
                    p.get("avg_completeness", 0), p.get("avg_data", 0), p.get("avg_structure", 0),
                    p.get("avg_planning", 0), p.get("avg_depth", 0),
                    hits, p["perf_focus"], p["mgmt_focus"],
                    p["strengths"], p["improvements"],
                    "；".join(p.get("rectify") or []), p["comment"]])
    w2 = [10, 14, 8, 12, 6, 8, 6, 9, 9, 10, 9, 10, 8, 8, 8, 8, 26, 10, 10, 34, 34, 44, 44]
    for i, wd in enumerate(w2, 1):
        ws2.column_dimensions[chr(64 + i)].width = wd
    ws2.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from urllib.parse import quote
    fname = f"周报_{week}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"weekly_{week}.xlsx\"; filename*=UTF-8''{quote(fname)}"})


