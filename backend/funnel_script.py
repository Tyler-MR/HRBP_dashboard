# -*- coding: utf-8 -*-
"""
招聘漏斗数据筛选脚本
====================
数据提取路径: backend/recruitment.db（SQLAlchemy + Candidate 模型，与看板 API 完全同一路径，未改动）

漏斗筛选口径（2026-08 确认版）:
  阶段1 邀约面试  到面日期 ∈ 当月                                        -> resume_received_date
  阶段2 初试通过  到面日期 ∈ 当月 且 初试结果 = '通过'                    -> first_round_pass == 'pass'
  阶段3 复试通过  到面日期 ∈ 当月 且 复试结果 = '通过'                    -> second_round_pass == 'pass'
  阶段4 已接收    到面日期 ∈ 当月 且 是否试岗 = '是'                      -> offer_accepted == 'accepted'
  阶段5 已到岗    试岗日期 ∈ 当月                                        -> onboard_date
  阶段6 满7天     试岗日期 ∈ 当月 且 试岗结果 = '入职'                    -> retention_7day == 'yes'
所有阶段均按姓名去重统计: Candidate.name.distinct().count()
阶段1-4 按月过滤用「到面日期」; 阶段5-6 按月过滤用「试岗日期」(onboard_date)

钉钉多维表字段 -> 本地字段映射:
  到面日期 -> resume_received_date / interview_attended_date
  试岗日期 -> onboard_date (text 'YYYY-MM-DD')
  初试结果 -> first_round_pass ('pass'=通过, 'fail'=未通过)
  复试结果 -> second_round_pass (同上)
  是否试岗 -> offer_accepted ('accepted'=是, 'rejected'=否)
  试岗结果 -> retention_7day ('yes'=入职)

用法:
  python funnel_script.py 2026-07           # 输出 7 月漏斗各阶段人数与转化率
  python funnel_script.py 2026-07 --names   # 追加输出各阶段名单
"""
import calendar
import sys
from datetime import date

from sqlalchemy import func

from database import SessionLocal
from models import Candidate

STAGES = [
    ("邀约面试", "到面日期∈当月"),
    ("初试通过", "到面日期∈当月 且 初试结果=通过"),
    ("复试通过", "到面日期∈当月 且 复试结果=通过"),
    ("已接收", "到面日期∈当月 且 是否试岗=是"),
    ("已到岗", "试岗日期∈当月"),
    ("满7天", "试岗日期∈当月 且 试岗结果=入职"),
]


def month_boundary(month: str) -> tuple[date, date]:
    """'YYYY-MM' -> (当月首日, 当月末日)"""
    y, m = int(month[:4]), int(month[5:7])
    _, last = calendar.monthrange(y, m)
    return date(y, m, 1), date(y, m, last)


def compute_funnel(month: str) -> list[dict]:
    """按确认口径计算漏斗各阶段人数（含转化率），返回 stage 列表。"""
    ms, me = month_boundary(month)
    db = SessionLocal()
    try:
        # 阶段1-4 按到面日期过滤; 阶段5-6 按试岗日期过滤
        mf = (Candidate.resume_received_date >= ms) & (Candidate.resume_received_date <= me)
        omf = (Candidate.onboard_date >= ms) & (Candidate.onboard_date <= me)

        def cnt(cond):
            return db.query(Candidate.name).filter(cond).distinct().count()

        values = [
            cnt(mf),                                                    # 邀约面试
            cnt(mf & (Candidate.first_round_pass == "pass")),           # 初试通过
            cnt(mf & (Candidate.second_round_pass == "pass")),          # 复试通过
            cnt(mf & (Candidate.offer_accepted == "accepted")),         # 已接收
            cnt(omf & Candidate.onboard_date.isnot(None)),              # 已到岗
            cnt(omf & (Candidate.retention_7day == "yes")),             # 满7天
        ]
    finally:
        db.close()

    stages = []
    for i, (name, cond_cn) in enumerate(STAGES):
        prev = values[i - 1] if i > 0 else None
        rate = round(values[i] / prev * 100, 1) if prev else None
        stages.append({"name": name, "value": values[i], "rate": rate, "cond": cond_cn})
    return stages


def stage_names(month: str, idx: int) -> list[str]:
    """返回指定阶段(0-5)的姓名名单。"""
    ms, me = month_boundary(month)
    db = SessionLocal()
    try:
        mf = (Candidate.resume_received_date >= ms) & (Candidate.resume_received_date <= me)
        omf = (Candidate.onboard_date >= ms) & (Candidate.onboard_date <= me)
        conds = [
            mf,
            mf & (Candidate.first_round_pass == "pass"),
            mf & (Candidate.second_round_pass == "pass"),
            mf & (Candidate.offer_accepted == "accepted"),
            omf & Candidate.onboard_date.isnot(None),
            omf & (Candidate.retention_7day == "yes"),
        ]
        return [n for (n,) in db.query(Candidate.name).filter(conds[idx]).distinct().order_by(Candidate.name).all()]
    finally:
        db.close()


if __name__ == "__main__":
    month = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m")
    show_names = "--names" in sys.argv

    stages = compute_funnel(month)
    print(f"===== 招聘漏斗筛选结果: {month} =====")
    for i, s in enumerate(stages):
        rate = f"{s['rate']}%" if s["rate"] is not None else "基数"
        print(f"{s['name']:<5} {s['value']:>4} 人   转化率 {rate:>7}    ({s['cond']})")
        if show_names:
            names = stage_names(month, i)
            print(f"       名单({len(names)}): " + "、".join(names))
