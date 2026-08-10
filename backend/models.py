"""数据库模型 — 仅在此区域改动"""
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import date, datetime
import enum

from database import Base


class Recruiter(Base):
    """招聘人员"""
    __tablename__ = "recruiters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, comment="姓名")
    department = Column(String(100), default="招聘部", comment="部门")
    created_at = Column(DateTime, default=datetime.now)

    positions = relationship("Position", back_populates="recruiter")


class Position(Base):
    """招聘岗位"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="岗位名称")
    department = Column(String(100), comment="需求部门")
    headcount = Column(Integer, default=1, comment="招聘人数")
    hired_count = Column(Integer, default=0, comment="已入职人数")
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"), comment="负责招聘人员ID")
    created_at = Column(DateTime, default=datetime.now)

    recruiter = relationship("Recruiter", back_populates="positions")
    candidates = relationship("Candidate", back_populates="position")


class Employee(Base):
    """在职员工 — 人员结构分析"""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, comment="姓名")
    department = Column(String(100), comment="所属部门")
    age = Column(Integer, comment="年龄")
    education = Column(String(20), comment="学历: 高中/中专, 大专, 本科, 硕士, 博士")
    tenure_years = Column(Float, default=0, comment="司龄（年）")
    hired_date = Column(Date, nullable=True, comment="入职日期（花名册 sys00-confirmJoinTime）")
    is_active = Column(String(5), default="yes", comment="是否在职: yes/no")
    employee_status = Column(String(20), default="正式", comment="员工状态: 正式/试用/待离职/已离职")
    created_at = Column(DateTime, default=datetime.now)

    talents = relationship("TalentProfile", back_populates="employee")


class TalentProfile(Base):
    """人才评估档案 — 雷达图各维度评分"""
    __tablename__ = "talent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), comment="员工ID")
    dimension = Column(String(30), comment="评估维度: 专业能力/沟通协作/创新能力/执行力/学习能力/责任感")
    score = Column(Integer, default=70, comment="评分 0-100")
    period = Column(String(7), default="2026-07", comment="评估周期 YYYY-MM")
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", back_populates="talents")


class HrEfficiency(Base):
    """月度人效数据 — 营收、成本、人员效率"""
    __tablename__ = "hr_efficiency"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(7), nullable=False, unique=True, comment="月份 YYYY-MM")
    revenue = Column(Float, default=0, comment="营业收入（万元）")
    net_profit = Column(Float, default=0, comment="净利润（万元）")
    total_labor_cost = Column(Float, default=0, comment="人力总成本（万元）")
    headcount = Column(Integer, default=0, comment="在岗人数")


class MemberScore(Base):
    """成员个人人才评分 — 人才雷达图各维度（每人一个打分入口）"""
    __tablename__ = "member_scores"

    id = Column(Integer, primary_key=True, index=True)
    department = Column(String(100), nullable=False, comment="部门")
    member_name = Column(String(50), nullable=False, comment="成员姓名")
    dimension = Column(String(30), nullable=False, comment="评估维度: 电商=数据驱动与选品力/店群品效管理/渠道拓展与策略贡献/运营人效/抗压与执行; 采购=谈判议价/交付保障/库存管理/供应商开发/跨部门协同; 客服=销售转化/售后处理/响应效率/用户洞察/情绪韧性; 人力行政部招聘组=业务理解/招聘交付力/人才配置与储备/制度流程与用工风控/服务意识与协同; 人力行政部行政组=业务理解/行政后勤管理/制度流程建设/成本管控/服务意识与协同; 产品=人才质量/组织活力/创新成长/执行力/团队协作; 其他=财务产出/运营效率/人才质量/执行力/创新成长")
    score = Column(Integer, nullable=False, default=0, comment="评分 0-100")
    updated_at = Column(String(30), comment="更新时间 YYYY-MM-DD HH:MM:SS")

    __table_args__ = (
        UniqueConstraint("department", "member_name", "dimension", name="uq_member_score_dim"),
    )


class Candidate(Base):
    """候选人 — 记录招聘全流程"""
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), comment="姓名")
    position_id = Column(Integer, ForeignKey("positions.id"), comment="应聘岗位ID")
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"), comment="负责招聘人员ID")
    
    # 招聘流程状态
    status = Column(String(30), default="简历初筛", comment="当前状态")
    # 简历初筛 → 邀约面试 → 初试 → 复试 → 发Offer → 已接收 → 已到岗 → 满7天
    # 各环节也可记录"已淘汰"、"已拒绝"等终止状态

    # 各环节时间戳
    resume_received_date = Column(Date, comment="收到简历日期")
    interview_invited_date = Column(Date, comment="邀约面试日期")
    interview_attended_date = Column(Date, comment="到面日期")
    first_round_date = Column(Date, comment="初试日期")
    first_round_pass = Column(String(10), comment="初试是否通过: pass/fail")
    second_round_date = Column(Date, comment="复试日期")
    second_round_pass = Column(String(10), comment="复试是否通过: pass/fail")
    offer_sent_date = Column(Date, comment="发送Offer日期")
    offer_accepted = Column(String(10), comment="Offer是否接受: accepted/rejected/pending")
    onboard_date = Column(Date, comment="到岗日期")
    retention_7day = Column(String(10), comment="满7天: yes/no/pending")
    decline_reason = Column(String(500), comment="放弃Offer原因", default="")
    
    created_at = Column(DateTime, default=datetime.now)

    position = relationship("Position", back_populates="candidates")
