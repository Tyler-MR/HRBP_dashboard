"""Pydantic 数据模型 — 仅在此区域改动"""
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import date, datetime


# ========== 看板概览数据 ==========
class OverviewStats(BaseModel):
    total_resumes: int = 0          # 总简历数
    total_invited: int = 0          # 总邀约量
    total_interviews: int = 0       # 总到面数
    first_round_passes: int = 0     # 初试通过数
    second_round_passes: int = 0    # 复试通过数
    offers_sent: int = 0            # 发Offer数
    offers_accepted: int = 0        # 接收Offer数
    onboarded: int = 0              # 到岗人数
    retention_7day: int = 0         # 满7天人数
    active_positions: int = 0       # 在招岗位数


# ========== 漏斗数据 ==========
class FunnelStage(BaseModel):
    name: str
    value: int
    rate: Optional[float] = None    # 上一环节到本环节的转化率


class FunnelData(BaseModel):
    stages: List[FunnelStage]


# ========== 岗位明细（用户指定的全部数据列）==========
class PositionStat(BaseModel):
    id: int
    name: str                           # 招聘岗位
    department: str                     # 需求部门
    headcount: int                      # 编制人数
    到面: int                           # 到面量（interview_attended_date）
    初试: int                           # 初试通过（first_round_pass=="pass"）
    复试: int                           # 复试通过（second_round_pass=="pass"）
    复试通过率: float = 0.0
    offer接受: int                      # 是否入职=是
    offer接受率: float = 0.0
    试岗: int                           # 试岗记录表中结果=试岗中
    入职: int                           # 试岗记录表结果=入职
    入职率: float = 0.0
    recruiter_name: Optional[str] = None
    fill_rate: float = 0.0              # 编制完成率


# ========== Offer状态 ==========
class OfferStatusItem(BaseModel):
    status: str    # sent / accepted / rejected
    count: int


class OfferStatusData(BaseModel):
    items: List[OfferStatusItem]


# ========== 招聘人员产出 ==========
class RecruiterOutput(BaseModel):
    id: int
    name: str
    department: str = ""
    resumes_handled: int
    interviews_arranged: int
    hires: int
    offer_accept_rate: float


# ========== 复试通过及Offer复盘明细 ==========
class OfferReviewItem(BaseModel):
    department: str
    position: str
    second_round_passes: int
    offers_accepted: int
    offers_declined: int
    in_progress: int
    in_progress_note: str = ""
    decline_reason: str = ""


# ========== 招聘达成进度一览 ==========
class ProgressItem(BaseModel):
    department: str
    position: str
    target_interview: int = 0          # 月初目标面试通过人数
    actual_interview: int = 0          # 6月实际面试通过人数
    target_onboarding: int = 0         # 月初目标到岗人数
    actual_probation: int = 0          # 6月实际试岗人数
    probationing: int = 0              # 试岗中人数
    retention_7day: int = 0            # 满7天留存人数
    names: str = ""                    # 人员姓名备注
    cancelled: bool = False            # 是否取消招聘


class ProgressSummary(BaseModel):
    target_interview: int = 0
    actual_interview: int = 0
    target_onboarding: int = 0
    actual_probation: int = 0
    probationing: int = 0
    retention_7day: int = 0
    interview_rate: float = 0.0        # 面试通过达成率
    probation_rate: float = 0.0        # 试岗达成率


# ========== 人员结构（新增） ==========
class AgeDistribution(BaseModel):
    range: str        # 年龄段，如 "20-25"
    count: int

class EducationDistribution(BaseModel):
    level: str        # 学历，如 "本科"
    count: int

class TenureDistribution(BaseModel):
    range: str        # 司龄段，如 "1-3年"
    count: int

class DeptHeadcount(BaseModel):
    department: str
    count: int
    percentage: float = 0.0

class EduFilterOption(BaseModel):
    level: str
    total: int

class MonthlyStaffTrend(BaseModel):
    month: str                      # "YYYY-MM"
    hires: int = 0                  # 当月入职人数
    headcount: int = 0              # 月末在岗人数（近似：当月前入职且当前在职）

class HrStaffStats(BaseModel):
    total_active: int = 0
    probation_count: int = 0        # 试用期人数
    regular_count: int = 0           # 转正人数
    age_distribution: List[AgeDistribution] = []
    education_distribution: List[EducationDistribution] = []
    tenure_distribution: List[TenureDistribution] = []
    dept_headcount: List[DeptHeadcount] = []
    available_educations: List[EduFilterOption] = []  # 可选学历筛选列表
    month: str = ""                  # 统计月份 YYYY-MM
    monthly_trend: List[MonthlyStaffTrend] = []        # 近12个月入职/在岗趋势


# ========== 人效数据（新增） ==========
class HrEfficiencyMonthly(BaseModel):
    month: str                                # "2024-01" / "2024-Q1" / "2024-H1" / "2024"
    label: str = ""                           # 展示标签（同 month，前端直接用）
    revenue: float = 0                        # 营业收入（万元）
    net_profit: float = 0                     # 净利润（万元）
    total_labor_cost: float = 0               # 人力总成本（万元）
    headcount: float = 0                      # 在岗人数（聚合期为均值，可为小数）
    revenue_per_employee: float = 0           # 人均收入
    cost_per_employee: float = 0              # 人均成本
    profit_per_employee: float = 0            # 人均净利润
    cost_efficiency: float = 0                # 成本效能


class HrEfficiencySummary(BaseModel):
    total_revenue: float = 0                  # 年度营收合计
    total_net_profit: float = 0               # 年度净利润合计
    total_labor_cost: float = 0               # 年度人力总成本
    avg_headcount: float = 0                  # 年均在岗人数
    avg_revenue_per_employee: float = 0       # 年度人均收入
    avg_cost_per_employee: float = 0          # 年度人均成本
    avg_profit_per_employee: float = 0        # 年度人均净利润
    avg_cost_efficiency: float = 0            # 年度平均成本效能


class HrEfficiencyResponse(BaseModel):
    monthly: List[HrEfficiencyMonthly] = []
    summary: Optional[HrEfficiencySummary] = None


# ========== 离职分析 ==========
class AttritionOverview(BaseModel):
    total_leavers: int = 0           # 离职总人数
    voluntary: int = 0               # 主动离职
    involuntary: int = 0             # 被动离职
    attrition_rate: float = 0.0      # 离职率
    headcount: int = 0               # 期初在岗人数


class AttritionByDept(BaseModel):
    department: str
    leavers: int
    headcount: int
    rate: float = 0.0


class AttritionByReason(BaseModel):
    reason: str
    count: int
    percentage: float = 0.0


class AttritionMonthly(BaseModel):
    month: str        # "2024-01"
    leavers: int
    rate: float = 0.0


class AttritionByTenure(BaseModel):
    range: str        # "7天内", "1个月内" ...
    count: int
    percentage: float = 0.0


class AttritionResponse(BaseModel):
    overview: AttritionOverview
    by_dept: List[AttritionByDept] = []
    by_reason: List[AttritionByReason] = []
    by_tenure: List[AttritionByTenure] = []
    monthly_trend: List[AttritionMonthly] = []
    view_type: str = "monthly"
    label: str = ""
    updated_at: str = ""


# ========== 部门人效 ==========
class DeptMetric(BaseModel):
    name: str                          # 指标名称
    value: float                       # 数值
    unit: str                          # 单位
    target: Optional[float] = None     # 目标值
    trend: str = "stable"              # up / down / stable
    group: Optional[str] = None        # 维度分组（产品团队：产品部/设计部，前端按此分两行展示）


class MemberMetric(BaseModel):
    name: str
    value: float
    unit: str = ""


class DeptMember(BaseModel):
    name: str
    position: str
    score: float = 0.0                 # 个人综合评分（已评分为当前维度 5 维合计，未评分=数据源原始分）
    score_max: float = 100.0           # 评分满分（已评分=单维满分×5：10分制=50/100分制=500；未评分=100 百分制）
    metrics: List[MemberMetric] = []
    evaluation: str = ""               # 部门负责人评语


class SubjectiveEval(BaseModel):
    dimension: str                     # 评价维度
    score: float                       # 0-100
    comment: str = ""
    trend: str = "stable"
    group: str = ""                    # 维度分组（如人力行政部=招聘组/行政组），无分组为空


class DeptEfficiency(BaseModel):
    department: str
    team_size: int
    metrics: List[DeptMetric] = []
    score: Optional[float] = None
    members: List[DeptMember] = []
    subjective: List[SubjectiveEval] = []
    source: Optional[str] = None          # 数据源标识: "mysql"=淘宝BI实时数据
    source_error: Optional[str] = None    # 数据源异常提示（如 MySQL 连接失败已重试）


class DeptEfficiencyResponse(BaseModel):
    items: List[DeptEfficiency] = []
    updated_at: str = ""


# ========== 成员个人人才雷达图（每人一个打分入口） ==========
class RadarDimInfo(BaseModel):
    dimension: str                          # 维度名
    max: int = 100                          # 满分（电商团队=10，其余=100）
    standard: str = ""                      # 该维度评分标准说明


class MemberScoreItem(BaseModel):
    name: str                                  # 成员姓名
    position: str = ""                         # 岗位
    scores: Dict[str, Optional[int]] = {}      # 维度 -> 分数（电商团队 0-10，其余 0-100；None=未评分）
    updated_at: str = ""                       # 最近评分时间


class MemberRadarResponse(BaseModel):
    department: str = ""
    items: List[MemberScoreItem] = []
    dims: List[RadarDimInfo] = []              # 维度元信息（满分 + 评分标准）


class MemberScoreSave(BaseModel):
    department: str                            # 部门
    member: str                                # 成员姓名
    scores: Dict[str, int]                     # 维度 -> 分数（10分制部门 0-10，其余 0-100）
    position: str = ""                         # 成员岗位（产品团队区分 产品负责人/设计人员）


# ========== 看板完整响应 ==========
class DashboardResponse(BaseModel):
    overview: OverviewStats
    funnel: FunnelData
    positions: List[PositionStat]
    offer_status: OfferStatusData
    recruiters: List[RecruiterOutput]
    offer_review: List[OfferReviewItem] = []
    progress_items: List[ProgressItem] = []
    progress_summary: Optional[ProgressSummary] = None
    hr_staff: HrStaffStats = None
    updated_at: str


# ========== 人才雷达图 ==========
class TalentDimension(BaseModel):
    dimension: str    # 维度名称
    score: int        # 0-100

class TalentRadarData(BaseModel):
    employee_id: int
    name: str
    department: str
    position: str = ""
    dimensions: List[TalentDimension] = []

class DeptTalentScore(BaseModel):
    department: str
    employee_count: int
    avg_professional: float = 0      # 专业能力均分
    avg_communication: float = 0     # 沟通协作均分
    avg_innovation: float = 0        # 创新能力均分
    avg_execution: float = 0         # 执行力均分
    avg_learning: float = 0          # 学习能力均分
    avg_responsibility: float = 0    # 责任感均分
    overall_score: float = 0         # 综合评分
    grade: str = "B"                 # S/A/B/C
    rank: int = 0                    # 排名

class TalentAnalysisResponse(BaseModel):
    employees: List[TalentRadarData] = []
    departments: List[DeptTalentScore] = []
    updated_at: str = ""
