"""FastAPI 主应用 — 仅在此区域改动（API 路由 + 模拟数据初始化）"""
import random
import calendar
import logging
import time
from datetime import date, timedelta, datetime
from typing import Optional, List, Dict, Any

import threading
from datetime import datetime as _dt
from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
from models import Recruiter, Position, Candidate, Employee, HrEfficiency, TalentProfile, MemberScore, DailyLog
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
    MemberScoreItem, MemberRadarResponse, MemberScoreSave, RadarDimInfo,
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
# 后台自动同步（每5分钟从钉钉拉取招聘数据）
# ═══════════════════════════════════════════════════

_sync_lock = threading.Lock()

def _auto_sync_loop():
    """后台线程：每5分钟自动同步一次招聘数据"""
    import time
    import random
    logger = logging.getLogger("auto_sync")
    while True:
        # 随机偏移 30-90 秒，避免触发时刻固定在整点撞上钉钉 QPS 限流
        time.sleep(300 + random.randint(30, 90))
        if not _sync_lock.acquire(blocking=False):
            logger.warning("上次同步尚未完成，跳过本次")
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

def _start_auto_sync():
    """在后台线程中启动自动同步"""
    thread = threading.Thread(target=_auto_sync_loop, daemon=True, name="auto-sync")
    thread.start()
    print("📌 后台自动同步已启动（每5分钟）")


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

def _apply_member_radar_scores(depts):
    """成员评分 = 个人人才雷达图**当前维度体系** 5 维合计分（用户口径：合计，非均值）。

    - 只聚合该成员当前维度（_member_radar_dims）下的评分，历史旧维度分（如默认
      \"人才质量/财务产出\"）不再计入，避免口径混杂与失真放大。
    - 已评分成员：score = Σ(5维分)，score_max = 单维满分×5（10分制→50，100分制→500）。
    - 未评分成员：保留数据源原始分（MySQL/钉钉真实人效分，score_max=100 百分制）。"""
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


# 部门人效整体 60s TTL 缓存（产品团队钉钉表另有自身缓存；此处把 MySQL/外部拉取也盖住，
# 前端 30s 轮询时避免每次请求都重连 MySQL 打 20s+）
_dept_metrics_cache: Dict[str, Any] = {"ts": {}, "data": {}}
_DEPT_METRICS_CACHE_TTL = 60


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
    """财务团队成员：花名册真实人员（部门=财务部，在职），不编造占位。"""
    return _roster_dept_members(["财务部"], "财务人员")


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

    month: 看板设定月份 YYYY-MM，仅产品团队（钉钉多维表）按此月统计；
           拼多多/淘宝仍自动取表内最新数据月。
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
    depts = [build_pdd_dept(), build_taobao_dept()]

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
                SubjectiveEval(dimension="谈判议价", score=84, comment="谈判能力强，成本控制到位", trend="up"),
                SubjectiveEval(dimension="交付保障", score=80, comment="到货交付稳定，准时率良好", trend="up"),
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
            # 雷达维度暂用默认5维，待用户指定财务部维度后替换
            subjective=[
                SubjectiveEval(dimension="财务产出", score=78, comment="资金运转良好，结算稳定", trend="up"),
                SubjectiveEval(dimension="运营效率", score=76, comment="单据处理高效，报销时效可控", trend="up"),
                SubjectiveEval(dimension="人才质量", score=74, comment="团队专业扎实，持证齐全", trend="stable"),
                SubjectiveEval(dimension="执行力", score=77, comment="报表税务准时，执行到位", trend="stable"),
                SubjectiveEval(dimension="创新成长", score=73, comment="财务数字化建设可加强", trend="stable"),
            ],
            # 成员=花名册真实人员（财务部在职），不编造占位
            members=fin_members),
    ]

    # 成员评分统一改为个人人才雷达图 5 维均值（未评分成员保留原分）
    depts = _apply_member_radar_scores(depts)

    resp = DeptEfficiencyResponse(items=depts, updated_at=now)
    _dept_metrics_cache["data"][cache_key] = resp
    _dept_metrics_cache["ts"][cache_key] = time.time()
    return resp

@app.get("/api/dept-efficiency", response_model=DeptEfficiencyResponse)
def get_dept_efficiency(month: Optional[str] = Query(None, description="看板设定月份 YYYY-MM，产品团队按此月统计")):
    """获取各部门人效数据"""
    return _dept_metrics_data(month)


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
# 电商团队（拼多多/淘宝）成员雷达维度：按用户要求与部门雷达一致
ECOMMERCE_MEMBER_RADAR_DIMS = ["数据驱动与选品力", "店群品效管理", "渠道拓展与策略贡献", "运营人效", "抗压与执行"]
# 采购团队成员雷达维度：按用户要求与部门雷达一致
PURCHASE_MEMBER_RADAR_DIMS = ["谈判议价", "交付保障", "库存管理", "供应商开发", "跨部门协同"]
PURCHASE_RADAR_STANDARDS = {
    "谈判议价": "针对原料、包材及OEM加工费的压价及账期争取能力。",
    "交付保障": "确保OEM工厂按时交货，应对爆单时的产能协调能力。",
    "库存管理": "家用清洁类目体积大，需极高周转，避免呆滞库存的能力。",
    "供应商开发": "寻找更具性价比的OEM工厂或源头原料商的能力。",
    "跨部门协同": "与运营（备货计划）、产品（打样）的配合度与主动性。",
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
# 产品负责人（产品团队-产品部）成员雷达维度：按用户要求，满分10分
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
# 设计人员（产品团队-设计部）成员雷达维度：按用户要求，满分10分
DESIGN_MEMBER_RADAR_DIMS = ["视觉转化力", "视觉创意力", "品牌视觉管理", "设计效率与规范", "跨部门协同"]
DESIGN_RADAR_STANDARDS = {
    "视觉转化力": "详情页/主图对\u201c清洁效果\u201d的视觉呈现及点击率/转化率优化能力。",
    "视觉创意力": "在信息流/短视频/直播间场景下，通过差异化视觉设计抓住用户眼球、提升停留时长的能力。",
    "品牌视觉管理": "在店群/多链接模式下，确保品牌视觉资产（VI/色调/调性）统一性，避免廉价感，提升品牌溢价的能力。",
    "设计效率与规范": "应对海量SKU需求时的作图速度，以及建立组件化/模板化设计体系以赋能团队的能力。",
    "跨部门协同": "与运营（卖点提炼）、产品（包装落地）、视频（素材配合）的高效沟通与协作能力。",
}

# 电商团队（拼多多/淘宝）成员雷达评分标准（用户口径，每项满分10分）
ECOMMERCE_RADAR_STANDARDS = {
    "数据驱动与选品力": "对拼多多/千川后台数据的解读能力及从测款到爆款的完整操盘能力，衡量数据洞察与打品结果的双重产出。",
    "店群品效管理": "黑标店群矩阵管理效率及单链接产出能力，衡量\u201c管店能力\u201d与\u201c单链接产出效率\u201d的综合表现。",
    "渠道拓展与策略贡献": "淘宝/天猫/达播/千川短视频的协同或独立开拓能力，以及输出可复用方法论推动团队效率提升的能力。",
    "运营人效": "个人负责的GMV（或毛利）与个人薪资成本的比值，直接衡量\u201c个人产出价值\u201d与\u201c投入产出比\u201d。",
    "抗压与执行": "应对大促、平台规则突变及高强度店群操作的韧性与执行力，衡量在高压环境下持续产出结果的能力。",
}
# 所有带评分标准的维度（电商5 + 设计5 + 采购5 + 产品5 + 客服5），有标准即 10 分制
_RADAR_STANDARDS = {**ECOMMERCE_RADAR_STANDARDS, **DESIGN_RADAR_STANDARDS, **PURCHASE_RADAR_STANDARDS,
                    **PRODUCT_RADAR_STANDARDS, **CUSTOMER_RADAR_STANDARDS}
# 评分标准按部门/岗位区分（"跨部门协同"等同名维度在不同岗位标准不同，避免 dict 合并覆盖）
_RADAR_STANDARDS_BY_ROLE = {
    "拼多多团队": ECOMMERCE_RADAR_STANDARDS,
    "淘宝团队": ECOMMERCE_RADAR_STANDARDS,
    "采购团队": PURCHASE_RADAR_STANDARDS,
    "客服团队": CUSTOMER_RADAR_STANDARDS,
    "产品负责人": PRODUCT_RADAR_STANDARDS,
    "设计人员": DESIGN_RADAR_STANDARDS,
}
# 成员雷达满分（部门级）：10 分制团队；人力/财务等仍 100 分制
_MEMBER_RADAR_MAX = {"拼多多团队": 10, "淘宝团队": 10, "采购团队": 10, "产品团队": 10, "客服团队": 10}


def _member_radar_max(department: str, member: str = None, position: str = "", dimension: str = None) -> int:
    """成员雷达满分：带评分标准的维度一律 10 分制（电商/采购/产品/设计），其余按部门。"""
    if dimension is not None and dimension in _RADAR_STANDARDS:
        return 10
    return _MEMBER_RADAR_MAX.get(department, 100)


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
        return PURCHASE_MEMBER_RADAR_DIMS
    if department == "客服团队":
        return CUSTOMER_MEMBER_RADAR_DIMS
    if department == "人力团队":
        # 真实花名册成员按岗位归组（钉钉 sys00-position：含"招聘"→招聘组，否则→行政组）
        # 兼容旧值"招聘人员"/"行政人员"及旧姓名映射
        if "招聘" in position or _HR_ADMIN_MEMBER_GROUP.get(member) == "招聘组":
            return HR_RECRUIT_DIMS
        return HR_ADMIN_DIMS
    return MEMBER_RADAR_DIMS


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
        last = max((r.updated_at for r in rows if r.member_name == m.name), default="")
        items.append(MemberScoreItem(name=m.name, position=m.position, scores=scores, updated_at=last))
        # 产品团队岗位名以花名册为准（设计/美工/产品储备主管等），按维度集取标准
        if department == "产品团队":
            std = DESIGN_RADAR_STANDARDS if dims == DESIGN_MEMBER_RADAR_DIMS else PRODUCT_RADAR_STANDARDS
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
    满分按部门/岗位/维度决定（电商团队、设计人员=10分，其余=100分）。"""
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

def _logs_period_range(period: str) -> tuple:
    """按粒度取「本周期至今」时间区间。"""
    now = datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        pass
    elif period == "quarter":
        start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "half":
        start = now.replace(month=(1 if now.month <= 6 else 7), day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


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
                 db: Session = Depends(get_db)):
    """管理人员日志评分排名（仅名单内 17 人，按人聚合平均分降序）。
    综合评估 = 五维日志质量 + 岗位职责契合 + 业绩导向 + 团队管理 → 综合评级 A/B/C/D + 综合点评。"""
    from collections import defaultdict
    from log_eval import (person_profile, evaluate_role_fit,
                          evaluate_industry_focus, comprehensive_eval,
                          _PERF_GROUPS, _MGMT_GROUPS)
    from manager_list import MANAGERS, MANAGER_NAMES, TITLE_MAP, ROLE_KEYWORDS

    start, end = _logs_period_range(period)
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
                           "grade": "", "grade_cn": "—", "comp_score": 0, "comment": "",
                           "strengths": "暂无日志", "improvements": "尚未提交日志",
                           "last_log_time": ""})
            continue
        n = len(key_logs)
        p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in key_logs) / n, 1)
                 for dim in ["completeness", "data", "structure", "planning", "depth"]}
        full_text = _logs_text(key_logs)
        role = evaluate_role_fit(full_text, ROLE_KEYWORDS.get(title, []))
        perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
        mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
        profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
        comp = comprehensive_eval(
            round(sum(l.score_total or 0 for l in key_logs) / n, 1),
            role["role_fit"], perf, mgmt,
            role["role_hit"], role["role_miss"],
            profile["top_dim"], profile["weak_dim"])
        latest = max(key_logs, key=lambda l: l.create_time)
        people.append({
            "name": name, "title": title, "dept": key_logs[0].dept_name or "",
            "log_count": n, "avg_score": round(sum(l.score_total or 0 for l in key_logs) / n, 1),
            **{f"avg_{dim}": p_avg[dim] for dim in ["completeness", "data", "structure", "planning", "depth"]},
            "role_fit": role["role_fit"], "role_hit": role["role_hit"], "role_miss": role["role_miss"],
            "perf_focus": perf, "mgmt_focus": mgmt,
            "grade": comp["grade"], "grade_cn": comp["grade_cn"],
            "comp_score": comp["comp_score"], "comment": comp["comment"],
            **profile,
            "last_log_time": latest.create_time.strftime("%Y-%m-%d"),
        })

    people.sort(key=lambda p: (-(p["log_count"] > 0), -p["avg_score"]))
    for i, p in enumerate(people, 1):
        p["rank"] = i if p["log_count"] > 0 else None
    return {
        "period": period,
        "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
        "total_logs": len(rows), "total_people": len(people),
        "people": people,
    }


@app.get("/api/logs-evaluation")
def logs_evaluation(name: str = Query(..., description="人员姓名"),
                    period: str = Query("month"),
                    db: Session = Depends(get_db)):
    """单人日志评估分析报告：五维雷达 + 岗位职责深度评估（含证据）+ 多条优缺点 + 综合评级 + 深度分析建议。"""
    from manager_list import MANAGER_NAMES, TITLE_MAP, ROLE_KEYWORDS, LEVEL_MAP
    from log_eval import (evaluate_role_fit, evaluate_industry_focus,
                          comprehensive_eval, person_profile, build_report_items,
                          build_deep_advice, data_dim_label,
                          _PERF_GROUPS, _MGMT_GROUPS)
    title = TITLE_MAP.get(name, "")
    if name not in MANAGER_NAMES:
        return {"name": name, "title": title, "period": period, "detail": [],
                "radar": [], "recent": [], "total": 0, "avg_score": 0, "role_fit": 0,
                "role_hit": [], "role_miss": [], "role_detail": [],
                "perf_focus": 0, "mgmt_focus": 0,
                "grade": "", "grade_cn": "", "comment": "",
                "strengths_list": [], "improvements_list": [],
                "deep_strengths": [], "deep_improvements": []}
    start, end = _logs_period_range(period)
    rows = (db.query(DailyLog)
            .filter(DailyLog.creator_name == name, DailyLog.create_time >= start, DailyLog.create_time <= end)
            .order_by(DailyLog.create_time).all())
    if not rows:
        return {"name": name, "title": title, "period": period, "detail": [],
                "radar": [], "recent": [], "total": 0, "avg_score": 0, "role_fit": 0,
                "role_hit": [], "role_miss": [], "role_detail": [],
                "perf_focus": 0, "mgmt_focus": 0,
                "grade": "", "grade_cn": "", "comment": "",
                "strengths_list": [], "improvements_list": [],
                "deep_strengths": [], "deep_improvements": []}
    n = len(rows)
    full_text = _logs_text(rows)
    role = evaluate_role_fit(full_text, ROLE_KEYWORDS.get(title, []))
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
    comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                              role["role_hit"], role["role_miss"],
                              profile["top_dim"], profile["weak_dim"])
    items = build_report_items(avg_score, role, perf, mgmt,
                               profile["strengths"], profile["improvements"])
    deep = build_deep_advice(title, ROLE_KEYWORDS.get(title, []), role["role_hit"],
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
    return {"name": name, "title": title, "period": period, "detail": detail, "radar": radar,
            "recent": recent, "total": n,
            "avg_score": avg_score,
            "role_fit": role["role_fit"], "role_hit": role["role_hit"],
            "role_miss": role["role_miss"], "role_detail": role["role_detail"],
            "perf_focus": perf, "mgmt_focus": mgmt,
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
    """单人周报聚合：五维均分 + 岗位职责 + 业绩/团队 + 综合评级 + 职级覆盖 + 整改建议。"""
    from log_eval import (person_profile, evaluate_role_fit, evaluate_industry_focus,
                          comprehensive_eval, evaluate_level_fit, build_rectify_suggestions,
                          _PERF_GROUPS, _MGMT_GROUPS)
    from manager_list import ROLE_KEYWORDS, LEVEL_MAP, LEVEL_REQ
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
                "level_covered": 0, "level_req": level_req, "last_log_time": ""}
    n = len(key_logs)
    p_avg = {dim: round(sum(getattr(l, "score_" + dim) or 0 for l in key_logs) / n, 1)
             for dim in ["completeness", "data", "structure", "planning", "depth"]}
    full_text = _logs_text(key_logs)
    role = evaluate_role_fit(full_text, ROLE_KEYWORDS.get(title, []))
    perf = evaluate_industry_focus(full_text, _PERF_GROUPS)
    mgmt = evaluate_industry_focus(full_text, _MGMT_GROUPS)
    profile = person_profile(p_avg, all_avg, role["role_hit"], role["role_miss"])
    avg_score = round(sum(l.score_total or 0 for l in key_logs) / n, 1)
    comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                              role["role_hit"], role["role_miss"],
                              profile["top_dim"], profile["weak_dim"])
    level_covered, uncov = evaluate_level_fit(full_text, level_req)
    rectify = build_rectify_suggestions(n, role["role_miss"], profile["weak_dim"],
                                        perf, mgmt, level, uncov)
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
                name: str = Query("", description="人员姓名，空=17人通晒汇总"),
                db: Session = Depends(get_db)):
    """周度日志评分报告：17 人通晒汇总 或 单人周报详情（含整改建议、周环比）。"""
    from manager_list import MANAGER_NAMES, TITLE_MAP, ROLE_KEYWORDS, LEVEL_MAP, LEVEL_REQ
    from log_eval import (evaluate_role_fit, evaluate_industry_focus, comprehensive_eval,
                          person_profile, build_report_items, evaluate_level_fit,
                          build_rectify_suggestions, data_dim_label, _PERF_GROUPS, _MGMT_GROUPS)
    payload = _logs_weekly_payload(week, db)
    week = payload["week"]

    if name:
        title = TITLE_MAP.get(name, "")
        if name not in MANAGER_NAMES:
            return {"name": name, "title": title, "week": week, "total": 0,
                    "avg_score": 0, "detail": [], "radar": [], "recent": [], "rectify": [],
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
                    "detail": [], "radar": [], "recent": [], "rectify": ["本周未提交日志，无法评估，建议恢复工作日日志提交"],
                    "prev_week": None, "role_detail": [], "role_fit": 0, "role_hit": [],
                    "role_miss": [], "perf_focus": 0, "mgmt_focus": 0,
                    "grade": "", "grade_cn": "", "comp_score": 0, "comment": "",
                    "strengths_list": [], "improvements_list": [],
                    "level": level, "level_covered": 0, "level_req": level_req,
                    "strengths": "暂无日志", "improvements": "尚未提交日志"}
        n = len(rows)
        full_text = _logs_text(rows)
        role = evaluate_role_fit(full_text, ROLE_KEYWORDS.get(title, []))
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
        comp = comprehensive_eval(avg_score, role["role_fit"], perf, mgmt,
                                  role["role_hit"], role["role_miss"],
                                  profile["top_dim"], profile["weak_dim"])
        items = build_report_items(avg_score, role, perf, mgmt,
                                   profile["strengths"], profile["improvements"])
        level_covered, uncov = evaluate_level_fit(full_text, level_req)
        rectify = build_rectify_suggestions(n, role["role_miss"], profile["weak_dim"],
                                            perf, mgmt, level, uncov)
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
            p_role = evaluate_role_fit(p_text, ROLE_KEYWORDS.get(title, []))
            p_comp = comprehensive_eval(p_avg_score, p_role["role_fit"],
                                        evaluate_industry_focus(p_text, _PERF_GROUPS),
                                        evaluate_industry_focus(p_text, _MGMT_GROUPS),
                                        p_role["role_hit"], p_role["role_miss"])
            prev = {"week": prev_label, "log_count": pn, "avg_score": p_avg_score,
                    "grade": p_comp["grade"], "grade_cn": p_comp["grade_cn"],
                    "delta": round(avg_score - p_avg_score, 1)}
        detail = [{"date": l.create_time.strftime("%Y-%m-%d"), "score": l.score_total or 0} for l in rows]
        radar = [
            {"dimension": "内容完整度", "score": p_avg["completeness"], "max": 25},
            {"dimension": data_dim_label(title), "score": p_avg["data"], "max": 20},
            {"dimension": "结构化程度", "score": p_avg["structure"], "max": 15},
            {"dimension": "规划性", "score": p_avg["planning"], "max": 20},
            {"dimension": "复盘深度", "score": p_avg["depth"], "max": 20},
        ]
        recent = [{"date": l.create_time.strftime("%Y-%m-%d"), "score": l.score_total or 0,
                   "strengths": l.strengths or "", "improvements": l.improvements or ""}
                  for l in rows[-3:]][::-1]
        return {"name": name, "title": title, "week": week, "total": n,
                "avg_score": avg_score, "detail": detail, "radar": radar, "recent": recent,
                "role_fit": role["role_fit"], "role_hit": role["role_hit"],
                "role_miss": role["role_miss"], "role_detail": role["role_detail"],
                "perf_focus": perf, "mgmt_focus": mgmt,
                "grade": comp["grade"], "grade_cn": comp["grade_cn"],
                "comp_score": comp["comp_score"], "comment": comp["comment"],
                "strengths_list": items["strengths_list"], "improvements_list": items["improvements_list"],
                "strengths": profile["strengths"], "improvements": profile["improvements"],
                "rectify": rectify, "prev_week": prev,
                "level": level, "level_covered": level_covered, "level_req": level_req}

    return {"week": week, "start": payload["start"], "end": payload["end"],
            "total_logs": payload["total_logs"], "people": payload["people"]}


@app.get("/api/logs-weekly-weeks")
def logs_weekly_weeks(db: Session = Depends(get_db)):
    """有日志的周列表（最新在前），供周选择器。"""
    return {"weeks": _logs_available_weeks(db), "current": _logs_current_week()}


@app.get("/api/logs-weekly-trend")
def logs_weekly_trend(name: str = Query(...), weeks: int = Query(8, ge=2, le=26),
                      db: Session = Depends(get_db)):
    """个人近 N 周评分趋势（整改效果跟踪）。"""
    from manager_list import TITLE_MAP, ROLE_KEYWORDS
    from log_eval import (evaluate_role_fit, evaluate_industry_focus, comprehensive_eval,
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
            role = evaluate_role_fit(text, ROLE_KEYWORDS.get(title, []))
            comp = comprehensive_eval(avg, role["role_fit"],
                                      evaluate_industry_focus(text, _PERF_GROUPS),
                                      evaluate_industry_focus(text, _MGMT_GROUPS),
                                      role["role_hit"], role["role_miss"])
            grade = comp["grade"]
        trend.append({"week": wl, "log_count": n, "avg_score": avg, "grade": grade})
    return {"name": name, "trend": trend}


@app.get("/api/logs-weekly-export")
def logs_weekly_export(week: str = Query("", description="周标签 YYYY-Www，空=最新周"),
                       db: Session = Depends(get_db)):
    """周报 Excel 导出（通晒用）：sheet1 17人通晒汇总 + sheet2 个人周报明细。"""
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
    headers = ["排名", "姓名", "岗位", "职级", "部门", "篇数", "周均分", "评级", "岗位契合", "业绩导向", "团队管理", "核心优点", "需改进", "整改建议", "综合点评"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4F46E5")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for p in people:
        ws.append([
            p.get("rank") if p.get("log_count") else "—", p["name"], p["title"], p["level"], p["dept"],
            p["log_count"] or "—", p["avg_score"] or "—",
            p["grade"] or "—", p["role_fit"], p["perf_focus"], p["mgmt_focus"],
            p["strengths"], p["improvements"],
            "；".join(p["rectify"]) if p.get("rectify") else "",
            p["comment"],
        ])
    width_map = [6, 10, 14, 8, 12, 6, 8, 6, 9, 9, 9, 34, 34, 44, 44]
    for i, wd in enumerate(width_map, 1):
        ws.column_dimensions[chr(64 + i)].width = wd
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("个人周报明细")
    ws2.append(["姓名", "岗位", "职级", "部门", "篇数", "周均分", "评级", "完整度/25", "数据/20", "结构/15", "规划/20", "深度/20",
                "岗位职责覆盖", "业绩导向/20", "团队管理/20", "核心优点", "需改进", "整改建议", "综合点评"])
    for c in ws2[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="059669")
    for p in people:
        hits = "、".join(p.get("role_hit") or []) or "无"
        ws2.append([p["name"], p["title"], p["level"], p["dept"], p["log_count"] or "—",
                    p["avg_score"] or "—", p["grade"] or "—",
                    p.get("avg_completeness", 0), p.get("avg_data", 0), p.get("avg_structure", 0),
                    p.get("avg_planning", 0), p.get("avg_depth", 0),
                    hits, p["perf_focus"], p["mgmt_focus"],
                    p["strengths"], p["improvements"],
                    "；".join(p.get("rectify") or []), p["comment"]])
    w2 = [10, 14, 8, 12, 6, 8, 6, 10, 8, 8, 8, 8, 26, 10, 10, 34, 34, 44, 44]
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


