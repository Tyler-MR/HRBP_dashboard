# -*- coding: utf-8 -*-
"""
日志评分引擎（规则评分，满分100，口径透明可核对）

维度与满分：
  score_completeness  内容完整度 25分 — 非空字段数 / 模板字段数
  score_data          数据支撑度 20分 — 含数字信息（金额/数量/百分比/指标）的段落占比
  score_structure     结构化程度 15分 — 编号分点 / 多段落
  score_planning      规划性     20分 — 含明日/计划/安排/下一步等规划关键词
  score_depth         复盘深度   20分 — 字数梯度 + 反思/问题/改进/总结等复盘关键词

优点（strengths）    = 得分最高的维度 + 内容特征
需改进（improvements）= 得分最低的维度 + 缺失特征
"""
from __future__ import annotations

import json
import re
from typing import Any

# ── 正则特征 ──
_NUM_RE = re.compile(r'\d+(\.\d+)?\s*(%|元|万|单|条|人|家|个|件|分|次|笔|款|款号|单量|GMV)?')
# 业务数据词表（2026-08 扩充：原 13 词过窄，补全电商公司日志高频业务词，
# 解决"全员数据支撑度偏低"问题——退款/发货/订单/薪资等业务信息此前不被识别为数据）
_DATA_WORDS = (
    '数据', '金额', '业绩', '销量', '转化', '成交', '销售额', '利润', '投产', '接待', '询盘', '指标', '达成',
    # 业务高频词（新增）
    '退款', '发货', '订单', '薪资', '库存', '发票', '考勤', '客诉', '报表', '考核', '佣金', '核销', '消耗',
    '占比', '回款', '到账', '利润率', '毛利率', '访客', '流量', '点击', '收藏', '加购', '复购', '客单',
    '询价', '议价', '降本', '合格率', '抽检', '退货', '索赔', '售后', '理赔', '周转', '损耗', '预算',
    '费用', '结算', '排期', '上线', '通过率', '达成率', '完成率', '增长率', '同比', '环比', '招聘', '培训',
)
_PLAN_WORDS = ('明日', '明天', '计划', '安排', '下一步', '下周', '后续', '跟进', '预计', '待办', '目标')
_REVIEW_WORDS = ('总结', '复盘', '反思', '问题', '改进', '不足', '分析', '原因', '优化', '提升', '思考', '经验')

_STRUCT_RE = re.compile(r'(^\d+[.、．]\s?|^[-*•]\s?|^[一二三四五六七八九十]+[、.．]\s?)', re.M)

# 各维度满分
SCORE_MAX = {'completeness': 25, 'data': 20, 'structure': 15, 'planning': 20, 'depth': 20}

# 维度 → 档位措辞（单篇日志用，hi/mid/lo 按达标率 0.8/0.6 分档）
_WORDING = {
    'completeness': {'hi': '填写完整，执行到位', 'mid': '字段基本齐全', 'lo': '部分字段未填，注意完整'},
    'data':         {'hi': '数据详实，指标意识强', 'mid': '有一定数据佐证', 'lo': '量化不足，建议多用数据说话'},
    'structure':    {'hi': '条理清晰，分点规范', 'mid': '结构尚可', 'lo': '内容较散，建议分点书写'},
    'planning':     {'hi': '规划明确，安排清晰', 'mid': '有规划意识', 'lo': '缺少明日规划'},
    'depth':        {'hi': '复盘深入，有思考改进', 'mid': '有复盘意识', 'lo': '总结偏浅，建议加强复盘'},
}

# 聚合层（个人 vs 全员）：相对突出维度 → 优点措辞；相对落后维度 → 改进措辞
_STRONG_WORDING = {
    'completeness': '填写完整，执行到位',
    'data': '数据意识强，善于量化工作',
    'structure': '条理清晰，分点规范',
    'planning': '规划清晰，明日安排明确',
    'depth': '复盘深入，有改进思考',
}
_WEAK_WORDING = {
    'completeness': '完整度略低于全员，注意字段完整性',
    'data': '数据支撑不足，建议多用数据说话',
    'structure': '条理性偏弱，建议分点书写',
    'planning': '规划性偏弱，建议补充明日安排',
    'depth': '复盘深度不足，建议加强总结思考',
}


def _band(rate: float) -> str:
    return 'hi' if rate >= 0.8 else ('mid' if rate >= 0.6 else 'lo')


def _profile_from_scores(scores: dict) -> tuple[str, str]:
    """scores: {dim: (score, max)} → (strengths, improvements) 简短差异化。
    优点=达标率最高的维度，改进=达标率最低的维度，各一条。"""
    rate = {dim: s / m for dim, (s, m) in scores.items()}
    top = max(rate, key=rate.get)
    bottom = min(rate, key=rate.get)
    strengths = _WORDING[top][_band(rate[top])] if rate[top] >= 0.6 else '已按时提交'
    if rate[bottom] < 0.8:
        improvements = _WORDING[bottom][_band(rate[bottom])]
    else:
        improvements = '整体良好，保持稳定'
    return strengths, improvements


def person_profile(person_avg: dict, all_avg: dict,
                   role_hit: list | None = None, role_miss: list | None = None) -> dict:
    """聚合层：个人周期平均 vs 全员平均 + 岗位职责覆盖 → 排除同质化的简短优缺点。
    优点 = 相对全员最突出的维度 + 覆盖最好的职责类别；
    改进 = 相对全员最落后的维度 + 覆盖不足的职责类别。"""
    pr = {dim: (person_avg.get(dim, 0) or 0) / mx for dim, mx in SCORE_MAX.items()}
    ar = {dim: (all_avg.get(dim, 0) or 0) / mx for dim, mx in SCORE_MAX.items()}
    ratio = {dim: pr[dim] / max(ar[dim], 0.05) for dim in SCORE_MAX}

    # 维度部分
    top_r = max(ratio, key=ratio.get)               # 相对最突出维度
    if ratio[top_r] > 1.05 and pr[top_r] >= 0.6:
        top_dim = top_r
        dim_strong = _STRONG_WORDING[top_r]
    else:
        top_dim = max(pr, key=pr.get)               # 个人绝对最强维度
        dim_strong = _STRONG_WORDING[top_dim] if pr[top_dim] >= 0.6 else '已按时提交'
    bottom = min(ratio, key=ratio.get)              # 相对全员最落后维度
    weak_dim = bottom if ratio[bottom] < 0.95 else None
    dim_weak = _WEAK_WORDING[bottom] if weak_dim else None

    # 岗位职责部分
    hit = role_hit or []
    miss = role_miss or []
    if hit:
        strengths = f"{hit[0]}、{hit[1] if len(hit) > 1 else hit[0]}覆盖到位，{dim_strong}"
    else:
        strengths = f"{dim_strong}（岗位职责待补）"
    if miss and dim_weak:
        improvements = f"{miss[0]}覆盖不足，{dim_weak}"
    elif miss:
        improvements = f"{miss[0]}覆盖不足，建议补充该板块日志"
    elif dim_weak:
        improvements = dim_weak
    else:
        improvements = '整体良好，保持稳定'
    return {'strengths': strengths, 'improvements': improvements,
            'top_dim': top_dim, 'weak_dim': weak_dim}


def evaluate_role_fit(text: str, keywords: list) -> dict:
    """岗位职责契合度：日志全文命中职责类别的关键词 → 覆盖。
    返回 20 分制得分 + 命中/未命中类别列表 + 命中证据（代表句）。"""
    if not keywords:
        return {"role_fit": 0, "role_hit": [], "role_miss": [], "role_detail": []}
    t = _clean(text or "")
    tl = t.lower()
    hit, miss, detail = [], [], []
    for cat, words in keywords:
        covered = any(w.lower() in tl for w in words)
        evidence = _evidence(t, words) if covered else ""
        detail.append({"name": cat, "covered": covered, "evidence": evidence})
        (hit if covered else miss).append(cat)
    score = round(20 * len(hit) / len(keywords))
    return {"role_fit": score, "role_hit": hit, "role_miss": miss, "role_detail": detail}


def _evidence(text: str, words: list, span: int = 36) -> str:
    """在日志全文中找第一个命中词的句子片段（职责覆盖证据）。"""
    tl = text.lower()
    for w in words:
        idx = tl.find(w.lower())
        if idx >= 0:
            # 定位到句子边界
            start = text.rfind("\n", 0, idx) + 1
            end = text.find("\n", idx)
            if end == -1:
                end = len(text)
            sent = text[start:end].strip()
            if not sent:
                sent = text[max(0, idx - span // 2): idx + span]
            return (sent[: span * 2] + "…") if len(sent) > span * 2 else sent
    return ""


# ── 电商公司核心要求：业绩导向 / 团队管理（各 5 组词族，20 分制）──
_PERF_GROUPS = [  # 业绩导向（量/利/效/标/绩）
    ("销售规模", ["销售额", "销量", "订单量", "成交量", "gmv", "业绩"]),
    ("经营利润", ["利润", "毛利", "成本", "净利", "盈亏", "利润率"]),
    ("转化效能", ["转化率", "投产", "roi", "推广", "回报", "投产比"]),
    ("目标达成", ["目标", "达成", "完成率", "完成进度", "指标", "超标"]),
    ("客户运营", ["成交客户", "新客户", "新增客户", "复购", "客单价", "询盘", "回头客"]),
]
_MGMT_GROUPS = [  # 团队管理（队/培/配/考/员）
    ("团队组织", ["团队", "组员", "成员", "部门", "小组", "员工"]),
    ("培养辅导", ["培训", "带教", "辅导", "指导", "培养", "传授"]),
    ("分工排配", ["分工", "排班", "安排", "分配", "布置", "排期"]),
    ("考核评价", ["面谈", "考核", "评价", "评分", "绩效", "评估"]),
    ("人员管理", ["招聘", "入职", "离职", "出勤", "请假", "辞退"]),
]


def evaluate_industry_focus(text: str, groups: list) -> int:
    """电商行业要求维度：命中词族数 / 5 × 20。"""
    t = _clean(text or "").lower()
    if not t:
        return 0
    hits = sum(1 for _, words in groups if any(w.lower() in t for w in words))
    return round(20 * hits / len(groups))


# ── 综合评级与点评 ──
_DIM_CN = {
    'completeness': '内容完整度', 'data': '数据支撑度', 'structure': '结构化程度',
    'planning': '规划性', 'depth': '复盘深度',
}


def comprehensive_eval(avg_score: float, role_fit: int, perf: int, mgmt: int,
                       role_hit: list, role_miss: list, top_dim: str | None = None,
                       weak_dim: str | None = None, writing_ref: int = 0) -> dict:
    """综合评级 A/B/C/D + 综合点评（结合岗位职责与电商要求）。
    综合分 = 0.6×日志质量 + 0.15×岗位契合 + 0.075×业绩导向 +
    0.075×团队管理 + 0.1×岗位书写维度覆盖（均折算 100 分制）。
    岗位书写维度覆盖来自管理岗日志书写参考维度.xlsx，按岗位模板逐项命中计分。
    评级：A≥85 优秀 / B≥75 良好 / C≥65 合格 / D<65 待改进。"""
    comp = (0.6 * avg_score + 0.15 * role_fit * 5 + 0.075 * perf * 5 +
            0.075 * mgmt * 5 + 0.1 * writing_ref * 5)
    grade = 'A' if comp >= 85 else 'B' if comp >= 75 else 'C' if comp >= 65 else 'D'
    grade_cn = {'A': '优秀', 'B': '良好', 'C': '合格', 'D': '待改进'}[grade]

    parts = []
    if role_hit:
        parts.append(f"岗位职责覆盖良好（{'、'.join(role_hit[:3])}）")
    elif role_miss:
        parts.append(f"岗位职责覆盖不足，缺失{'、'.join(role_miss[:2])}板块")
    if perf >= 15:
        parts.append("业绩导向明确，经营成果意识强")
    elif perf < 10:
        parts.append("业绩数据体现不足，建议突出经营成果")
    if mgmt >= 15:
        parts.append("团队管理内容充实")
    elif mgmt < 10:
        parts.append("团队管理板块待加强")
    if writing_ref >= 15:
        parts.append("岗位日志书写参考维度覆盖充分")
    elif writing_ref < 10:
        parts.append("岗位日志书写参考维度覆盖不足")
    if weak_dim:
        parts.append(f"相对全员，{_DIM_CN.get(weak_dim, weak_dim)}是短板")
    comment = '；'.join(parts[:3]) if parts else '整体良好，保持稳定'

    return {"grade": grade, "grade_cn": grade_cn, "comment": comment, "comp_score": round(comp, 1)}


def build_report_items(avg_score: float, role: dict, perf: int, mgmt: int,
                       strengths_sum: str, improvements_sum: str,
                       writing_ref: int | None = None) -> dict:
    """个人分析报告：多条优缺点列表（岗位职责/维度/业绩/团队 四类来源）。"""
    hit, miss = role.get("role_hit") or [], role.get("role_miss") or []
    strengths_list, improvements_list = [], []
    if hit:
        strengths_list.append(f"岗位职责覆盖到位（{'、'.join(hit)}）")
    if strengths_sum:
        strengths_list.append(strengths_sum)
    if perf >= 15:
        strengths_list.append(f"业绩导向明确，经营成果意识强（{perf}/20）")
    if mgmt >= 15:
        strengths_list.append(f"团队管理内容充实（{mgmt}/20）")
    if writing_ref is not None and writing_ref >= 15:
        strengths_list.append(f"岗位日志书写参考维度覆盖充分（{writing_ref}/20）")
    if not strengths_list:
        strengths_list.append("日志按时提交，内容规范")

    if miss:
        improvements_list.append(f"岗位职责覆盖不足：{'、'.join(miss)}板块日志缺失")
    if improvements_sum:
        improvements_list.append(improvements_sum)
    if perf < 10:
        improvements_list.append(f"业绩数据体现不足（{perf}/20），建议突出经营成果")
    if mgmt < 10:
        improvements_list.append(f"团队管理板块待加强（{mgmt}/20）")
    if writing_ref is not None and writing_ref < 10:
        improvements_list.append(f"岗位日志书写参考维度覆盖不足（{writing_ref}/20），建议按岗位模板补齐关键板块")
    if not improvements_list:
        improvements_list.append("整体表现良好，可保持稳定输出")
    return {"strengths_list": strengths_list, "improvements_list": improvements_list}


# ── 周度报告：职级要求覆盖 + 整改建议（2026-08 新增，用于整改与通晒）──
def evaluate_level_fit(text: str, level_req: list) -> tuple:
    """职级要求覆盖 → (覆盖数, 未覆盖关键词列表)。结合岗位职级及要求审视日志内容。

    匹配规则（2026-08 修正）：全文包含关键词本身、或关键词的前 2 字 / 后 2 字
    （如「跨部门统筹」命中「统筹」即视为覆盖；「目标拆解」命中「目标」即覆盖）。
    日报为口语化表达，整词命中率系统性失真（此前全员 0/4），改为核心词匹配。
    """
    t = _clean(text or "").lower()
    if not level_req:
        return 0, []
    uncov = []
    for w in level_req:
        wl = w.lower()
        if wl in t or (len(wl) >= 2 and (wl[:2] in t or wl[-2:] in t)):
            continue
        uncov.append(w)
    return len(level_req) - len(uncov), uncov


def build_rectify_suggestions(log_count: int, role_miss: list, dim_weak: str | None,
                              perf: int, mgmt: int, level: str = "",
                              uncov_level: list | None = None, max_count: int = 4) -> list:
    """周度整改建议（规则引擎，无 LLM，按优先级取前 max_count 条）。

    优先级：职级要求缺失 > 岗位职责板块缺失 > 相对全员最弱维度 > 业绩/团队短板 > 提交频次。
    """
    sugs = []
    if level and uncov_level:
        sugs.append(f"按「{level}」岗位要求，日志需补充「{'、'.join(uncov_level[:2])}」等高阶管理内容（职级标准：{level}）")
    if role_miss:
        sugs.append(f"补充「{'、'.join(role_miss[:2])}」职责板块日志，每周日志应覆盖至少2-3项核心岗位职责")
    if dim_weak:
        sugs.append(f"强化《{_DIM_CN.get(dim_weak, dim_weak)}》：{_WEAK_WORDING.get(dim_weak, '')}")
    if perf < 10:
        sugs.append("突出业绩/经营成果数据：用销售额、转化率、投产比、利润等量化指标支撑工作")
    if mgmt < 10:
        sugs.append("补充团队管理内容：分工排配、培训辅导、考核面谈等团队动作写入日志")
    if log_count < 4:
        sugs.append(f"提升日志提交频次：本周仅 {log_count} 篇，建议工作日每日提交")
    if not sugs:
        sugs.append("各项表现良好，保持稳定输出，可在复盘深度上持续精进")
    return sugs[:max_count]


# ── 深度分析建议：结合电商行业属性 + 岗位特质（2026-08 新增）──
# 电商行业岗位族 → 核心量化指标（数据支撑/业绩导向类深度建议用）
_INDICATORS = {
    "电商运营": "GMV/销售额、投产比ROI、转化率、点击率、客单价、推广花费",
    "采购供应": "降本金额、议价幅度、库存周转天数、到货准时率、呆滞库存金额",
    "客服": "转化率、回复率、客诉率、售后处理时长、满意度",
    "财务": "预算偏差率、费用率、毛利/净利、回款率",
    "人力行政": "招聘完成率、到岗率、离职率、培训覆盖率",
    "产品": "上线达成率、稿件通过率、测试通过率",
    "数据分析": "指标口径覆盖率、看板/报表数、洞察落地数",
    "设计": "出稿量、通过率、返工率",
    "商务": "渠道/达人合作数、回款额、佣金率",
    "配方研发": "打样合格率、配方成本降幅、原料替换收益",
    "综合管理": "目标完成率、团队人效、培训场次、人员流失率",
}


def _family_of(title: str) -> str:
    """岗位 → 电商行业岗位族。"""
    if any(k in title for k in ["拼多多", "千川", "1688", "天猫", "淘天", "运营"]):
        return "电商运营"
    if "采购" in title:
        return "采购供应"
    if "客服" in title:
        return "客服"
    if "财务" in title:
        return "财务"
    if any(k in title for k in ["人事", "招聘", "行政"]):
        return "人力行政"
    if "产品" in title:
        return "产品"
    if "数据" in title:
        return "数据分析"
    if any(k in title for k in ["美工", "设计"]):
        return "设计"
    if "商务" in title:
        return "商务"
    if "配方" in title:
        return "配方研发"
    return "综合管理"


# 岗位族 → 专属数据指标词（数据支撑度维度按岗位特质判定，2026-08 用户口径）
_FAMILY_DATA_WORDS = {
    "电商运营": ["gmv", "销售额", "销量", "订单量", "成交", "转化", "投产", "roi", "花费", "推广", "客单",
                "点击", "流量", "收藏", "加购", "复购", "业绩", "目标", "达成", "直通车"],
    "采购供应": ["降本", "议价", "价格", "成本", "询价", "涨价", "库存", "备货", "周转", "呆滞", "缺货",
                "到货", "交期", "交付", "断货", "质量", "质检", "不合格", "退货", "索赔", "供应商"],
    "客服": ["接待", "会话", "咨询", "回复", "转化", "成交", "客诉", "投诉", "售后", "退款", "赔付",
            "纠纷", "复购", "客单", "满意度", "话术"],
    "财务": ["预算", "预测", "成本", "费用", "毛利", "净利", "利润", "盈亏", "回款", "发票", "报表",
            "核算", "同比", "税务", "账务", "佣金"],
    "人力行政": ["招聘", "面试", "入职", "到岗", "离职", "考勤", "薪资", "培训", "考核", "绩效", "编制",
                "仲裁", "合同", "人效", "评优"],
    "产品": ["上线", "通过", "测试", "质检", "需求", "立项", "打样", "交付", "达成", "渠道"],
    "数据分析": ["数据", "指标", "口径", "报表", "看板", "分析", "趋势", "对比", "归因", "工具", "脚本"],
    "设计": ["出稿", "通过", "返工", "交付", "稿件", "数量", "修改"],
    "商务": ["客户", "渠道", "达人", "主播", "回款", "佣金", "合同", "订单", "业绩", "询盘", "入驻"],
    "配方研发": ["打样", "成本", "原料", "替换", "合格", "测试", "实验", "配方", "工艺"],
    "综合管理": ["目标", "完成率", "人效", "培训", "人员", "指标", "业绩", "利润", "团队", "会议"],
}


def _data_words_for(title: str) -> tuple:
    """数据维度判定词表：通用词表 ∪ 岗位族专属词（结合岗位特质）。"""
    family = _family_of(title)
    extra = tuple(_FAMILY_DATA_WORDS.get(family, ()))
    return _DATA_WORDS + extra


def data_dim_label(title: str) -> str:
    """数据支撑度维度的岗位族命名（雷达展示）：如「运营数据支撑」。无岗位 → 通用名。"""
    if not title:
        return "数据支撑度"
    family = _family_of(title)
    return {
        "电商运营": "运营数据支撑", "采购供应": "采购数据支撑", "客服": "客服数据支撑",
        "财务": "财务数据支撑", "人力行政": "人力数据支撑", "产品": "产品数据支撑",
        "数据分析": "数据支撑", "设计": "设计数据支撑", "商务": "商务数据支撑",
        "配方研发": "研发数据支撑", "综合管理": "管理数据支撑",
    }.get(family, "数据支撑度")


# 维度短板 → 深度建议模板（{title} 岗位名 / {inds} 岗位族量化指标）
_DIM_DEEP = {
    "completeness": "「内容完整度」存在字段漏填，建议按模板逐项填写完整——日志是管理复盘与考核的依据，关键信息缺失会让工作成果无法被看见",
    "data": "「数据支撑度」不足：{title}的工作成果需要用数字说话，建议围绕 {inds} 等核心指标量化呈现，让每天的产出可衡量、可对比、可追溯",
    "structure": "「结构化程度」偏弱：建议按『今日完成｜数据表现｜问题复盘｜明日计划』四段分点书写，便于管理者快速抓取重点",
    "planning": "「规划性」不足：建议每日末尾明确『明日重点』与『待跟进事项』，形成日-周-月目标闭环，避免工作被动响应",
    "depth": "「复盘深度」偏浅：建议按『结果-原因-改进-计划』四步复盘，重点分析未达成项的原因与可落地的改进动作，而非简单罗列流水账",
}


def build_deep_advice(title: str, role_keywords: list, role_hit: list, role_miss: list,
                      dim_weak: str | None, perf: int, mgmt: int, level: str = "") -> dict:
    """深度分析建议：结合电商行业属性（量化指标/结果导向）+ 岗位特质（职责板块）。

    返回 {'deep_strengths': [...], 'deep_improvements': [...]}，改进建议按短板优先级生成。
    """
    family = _family_of(title)
    inds = _INDICATORS[family]
    imps, strs = [], []

    # ── 需改进：深度建议 ──
    if dim_weak:
        imps.append(_DIM_DEEP.get(dim_weak, "").format(title=title, inds=inds))
    miss_detail = [(cat, words) for cat, words in role_keywords if cat in role_miss]
    for cat, words in miss_detail[:2]:
        imps.append(
            f"「{cat}」板块日志缺失：{title}的职责要求涉及{'、'.join(words[:3])}，"
            f"建议记录该板块的推进动作与结果，避免核心职责出现盲区")
    if perf < 10:
        imps.append(
            f"业绩导向不足：电商行业以结果论英雄，{title}的日志缺乏经营成果数据，"
            f"建议重点呈现 {inds}，用数字证明产出与价值")
    if mgmt < 10 and level:
        imps.append(
            f"团队管理待加强：作为「{level}」，日志缺少团队动作（分工排配/培训带教/绩效面谈），"
            f"建议体现带团队的痕迹，而不仅是个人执行")
    if not imps:
        imps.append(f"当前无突出短板，建议在{title}的核心指标（{inds}）上持续精进，并向更高目标突破")

    # ── 优点：深度亮点 ──
    if role_hit:
        strs.append(f"岗位职责覆盖全面：在{title}岗位上扎实落地了{'、'.join(role_hit[:3])}，职责边界清晰、工作有章法")
    if perf >= 15:
        strs.append(f"业绩导向强：日志充分体现经营成果（{inds}方向），符合电商公司以结果论英雄的要求")
    if mgmt >= 15 and level:
        strs.append(f"团队管理到位：日志体现分工排配/培训辅导/考核评价等管理动作，具备「{level}」的管理视野")
    if not strs:
        strs.append(f"日志按时提交，在{title}岗位上保持稳定输出，可进一步向{family}核心指标深化")

    return {"deep_strengths": strs, "deep_improvements": imps}


# ══════════════════════════════════════════════════════════════════
# 周度报告三维评估（2026-08 用户口径）：电商行业属性 / 岗位要求 / 日报书写展现
# 各 20 分制 + 评语；纯增量展示，不改变综合评级公式（0.7质量+0.15契合+0.075业绩+0.075团队）
# ══════════════════════════════════════════════════════════════════

# ① 电商行业属性：岗位族 → 4 组核心经营指标词族（每组命中 5 分，共 20 分）
_IND_GROUPS = {
    "电商运营": [
        ("销售规模", ["销售额", "gmv", "销量", "订单量", "成交"]),
        ("投放投产", ["投产", "roi", "花费", "推广", "直通车"]),
        ("转化流量", ["转化率", "点击率", "流量", "加购", "收藏", "访客"]),
        ("经营结果", ["业绩", "利润", "目标", "达成", "增长率"]),
    ],
    "采购供应": [
        ("成本控制", ["议价", "降本", "成本", "价格", "询价"]),
        ("库存周转", ["库存", "周转", "呆滞", "备货", "缺货"]),
        ("交付保障", ["到货", "交期", "交付", "断货", "发货"]),
        ("质量管控", ["质检", "不合格", "退货", "索赔", "质量"]),
    ],
    "客服": [
        ("转化成交", ["转化", "成交", "复购", "客单", "下单"]),
        ("服务响应", ["接待", "会话", "回复", "咨询", "出勤"]),
        ("售后体验", ["售后", "退款", "客诉", "投诉", "满意度"]),
        ("质检话术", ["质检", "话术", "录音", "检查", "赔付"]),
    ],
    "财务": [
        ("预算执行", ["预算", "预测", "偏差", "执行"]),
        ("成本费用", ["成本", "费用", "核算", "分摊"]),
        ("经营分析", ["毛利", "净利", "利润", "盈亏", "同比"]),
        ("回款合规", ["回款", "发票", "税务", "佣金", "内控"]),
    ],
    "人力行政": [
        ("招聘交付", ["招聘", "面试", "入职", "到岗", "编制"]),
        ("绩效薪酬", ["绩效", "考核", "薪酬", "评优", "奖金"]),
        ("培训发展", ["培训", "培养", "晋升", "带教", "学习"]),
        ("用工风控", ["离职", "合同", "仲裁", "考勤", "用工"]),
    ],
    "产品": [
        ("产品交付", ["上线", "交付", "打样", "通过", "迭代"]),
        ("质量管控", ["质检", "合格", "检测", "标准", "抽检"]),
        ("需求规划", ["需求", "立项", "规划", "新品", "市场"]),
        ("供应链协同", ["供应商", "工厂", "生产", "交期"]),
    ],
    "数据分析": [
        ("指标体系", ["数据", "指标", "口径", "维度", "报表"]),
        ("分析洞察", ["分析", "洞察", "趋势", "归因", "波动"]),
        ("工具建设", ["工具", "自动化", "脚本", "看板", "模板"]),
        ("落地验证", ["落地", "效果", "验证", "反馈", "跟踪"]),
    ],
    "设计": [
        ("出稿交付", ["出稿", "稿件", "交付", "数量", "进度"]),
        ("质量通过", ["通过", "返工", "修改", "合格"]),
        ("需求响应", ["需求", "对接", "排期", "沟通"]),
        ("效率优化", ["效率", "模板", "批量", "优化"]),
    ],
    "商务": [
        ("渠道拓展", ["客户", "渠道", "达人", "主播", "入驻"]),
        ("业绩回款", ["业绩", "回款", "成交", "订单", "销售额"]),
        ("合作管理", ["合同", "佣金", "结算", "账期"]),
        ("商务推进", ["谈判", "跟进", "对接", "选品"]),
    ],
    "配方研发": [
        ("研发打样", ["打样", "测试", "实验", "小样", "研发"]),
        ("成本优化", ["成本", "原料", "降本", "替换"]),
        ("质量安全", ["质检", "安全", "合规", "成分", "检测"]),
        ("生产放大", ["工艺", "生产", "试产", "投产", "车间"]),
    ],
    "综合管理": [
        ("目标经营", ["目标", "完成率", "业绩", "利润", "指标"]),
        ("团队人效", ["人效", "团队", "人员", "培训", "梯队"]),
        ("统筹协调", ["协调", "资源", "跨部门", "会议", "统筹"]),
        ("复盘改进", ["复盘", "优化", "问题", "改进", "总结"]),
    ],
}

# ③ 日报书写展现：重点突出判定词（结论/成果类表述）
_HIGHLIGHT_WORDS = ("总结", "成果", "重点", "完成", "达成", "输出", "落地", "结果", "成效", "闭环")


def evaluate_industry_attrs(text: str, title: str) -> dict:
    """① 电商行业属性（20 分制）：日志是否贴合岗位族的行业核心经营指标。

    命中 4 组核心指标词族中 N 组 → N×5 分。返回 score/comment/family/hit。
    """
    t = _clean(text or "").lower()
    family = _family_of(title)
    groups = _IND_GROUPS.get(family, [])
    if not t or not groups:
        return {"score": 0, "comment": "本周无日志，无法评估行业属性", "family": family, "hit": []}
    hit = [g for g, words in groups if any(w.lower() in t for w in words)]
    score = 5 * len(hit)
    if score >= 15:
        comment = f"贴合电商行业经营口径：{family}核心指标（{'、'.join(hit)}）体现充分，工作成果量化清晰，符合以结果论英雄的行业要求"
    elif score >= 10:
        comment = f"体现部分{family}经营指标（{'、'.join(hit) if hit else '无'}），建议进一步突出 {_INDICATORS[family]} 等结果数据"
    else:
        comment = f"日志偏事务性记录，缺少{family}核心经营指标支撑，建议围绕 {_INDICATORS[family]} 量化呈现经营结果"
    return {"score": score, "comment": comment, "family": family, "hit": hit}


def evaluate_role_requirements(role: dict, title: str, level: str = "",
                               level_covered: int = 0, level_req: list | None = None) -> dict:
    """② 岗位要求契合（20 分制）：岗位职责覆盖 70% + 职级要求覆盖 30% 合成。

    role 来自 evaluate_role_fit()（含 role_fit 0-20、role_hit/role_miss）。
    """
    role_fit = role.get("role_fit") or 0
    hit = role.get("role_hit") or []
    miss = role.get("role_miss") or []
    req = level_req or []
    level_score = 20 * level_covered / max(len(req), 1) if req else 20
    score = round(0.7 * role_fit + 0.3 * level_score)
    if not hit and not req:
        score = 0
    if score >= 15:
        parts = [f"职责板块（{'、'.join(hit) if hit else '—'}）覆盖到位"]
        if level and req:
            parts.append(f"体现「{level}」要求（{level_covered}/{len(req)}）")
        comment = f"契合「{title}」岗位要求：{'；'.join(parts)}"
    elif score >= 10:
        gap = []
        if miss:
            gap.append(f"「{'、'.join(miss[:2])}」职责板块待补")
        if level and level_covered < len(req):
            gap.append(f"「{level}」要求覆盖不足（{level_covered}/{len(req)}）")
        comment = f"基本符合「{title}」岗位要求：{'；'.join(gap) if gap else '整体尚可，可再提升'}，建议补齐短板板块"
    else:
        comment = f"与「{title}」岗位要求存在差距：{'、'.join(miss[:2]) if miss else '职责内容'}覆盖不足，职级「{level or '—'}」要求未充分体现"
    return {"score": score, "comment": comment}


def evaluate_writing_show(p_avg: dict, text: str, log_count: int, title: str) -> dict:
    """③ 日报书写展现（20 分制）：结构条理 5 + 重点突出 5 + 信息密度 5 + 语言专业 5。"""
    t = _clean(text or "")
    tl = t.lower()
    family = _family_of(title)

    # 结构条理 5：取五维「结构化程度」折算（15 分制 → 5 分制）
    st = p_avg.get("structure") or 0
    structure = 5 if st >= 12 else 4 if st >= 8 else 3 if st >= 4 else 2

    # 重点突出 5：结论/成果类表述词命中数
    hl = sum(1 for w in _HIGHLIGHT_WORDS if w.lower() in tl)
    highlight = 5 if hl >= 3 else 4 if hl == 2 else 3 if hl == 1 else 2

    # 信息密度 5：每篇平均字数
    chars = len(t.replace("\n", "").replace(" ", ""))
    per = chars / max(log_count, 1)
    density = 5 if per >= 250 else 4 if per >= 150 else 3 if per >= 80 else 2

    # 语言专业 5：岗位族业务术语去重命中数
    terms = {w for w in _FAMILY_DATA_WORDS.get(family, ()) if w.lower() in tl}
    prof = 5 if len(terms) >= 5 else 4 if len(terms) >= 3 else 3 if len(terms) >= 1 else 2

    score = structure + highlight + density + prof
    if score >= 17:
        comment = "日报书写规范专业：结构清晰、重点突出、业务术语与数据运用得当，管理者可快速抓取工作脉络"
    elif score >= 13:
        comment = "日报书写较规范：条理基本清晰，可在重点提炼与结论表达上更精炼"
    elif score >= 9:
        comment = "日报书写一般：偏流水式记录，建议按『完成-数据-问题-计划』分点书写并提炼重点结论"
    else:
        comment = "日报书写待改进：内容较零散，建议结构化分点书写、突出成果与结论，避免大段堆砌"
    return {"score": score, "comment": comment,
            "items": {"structure": structure, "highlight": highlight,
                      "density": density, "professional": prof}}


def evaluate_writing_reference(text: str, title: str = "", name: str = "") -> dict:
    """岗位日志书写参考维度覆盖（20 分制）。

    参考模板来自管理岗日志书写参考维度.xlsx；每个岗位模板的维度等权，
    通过日志全文命中该维度的任一业务关键词判定覆盖，并返回命中证据供看板追溯。
    """
    from manager_list import get_log_writing_reference

    template = get_log_writing_reference(name=name, title=title)
    dimensions = template.get("dimensions") or []
    t = _clean(text or "")
    tl = t.lower()
    detail, hit, miss = [], [], []
    for dimension, words in dimensions:
        covered = bool(tl) and any(word.lower() in tl for word in words)
        item = {"name": dimension, "covered": covered,
                "evidence": _evidence(t, words) if covered else ""}
        detail.append(item)
        (hit if covered else miss).append(dimension)
    count = len(dimensions)
    score = round(20 * len(hit) / count) if count else 0
    if not t:
        comment = "周期内无日志，无法评估岗位书写参考维度"
    elif score >= 15:
        comment = f"已覆盖岗位书写参考维度 {len(hit)}/{count} 项，符合「{template['core']}」的管理要求"
    elif score >= 10:
        comment = f"已覆盖岗位书写参考维度 {len(hit)}/{count} 项，建议补充「{'、'.join(miss[:2])}」等板块"
    else:
        comment = f"仅覆盖岗位书写参考维度 {len(hit)}/{count} 项，建议按「{template['label']}」模板补齐「{'、'.join(miss[:3])}」"
    return {
        "score": score,
        "max": 20,
        "template": template["label"],
        "template_key": template["key"],
        "core": template["core"],
        "covered_count": len(hit),
        "dimension_count": count,
        "hit": hit,
        "miss": miss,
        "detail": detail,
        "comment": comment,
    }


def weekly_assessment(title: str, full_text: str, p_avg: dict, role: dict,
                      level: str = "", level_covered: int = 0,
                      level_req: list | None = None, log_count: int = 0,
                      name: str = "") -> dict:
    """周度四维评估组装：电商行业属性 / 岗位要求 / 参考维度覆盖 / 日报书写展现。"""
    return {
        "industry": evaluate_industry_attrs(full_text, title),
        "role": evaluate_role_requirements(role, title, level, level_covered, level_req),
        "writing_reference": evaluate_writing_reference(full_text, title, name),
        "writing": evaluate_writing_show(p_avg, full_text, log_count, title),
    }


def _clean(s: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s or '')


def _parse_contents(contents: Any) -> list[dict]:
    """contents 可能是 list[dict] 或 JSON 字符串。"""
    if isinstance(contents, str):
        try:
            return json.loads(contents) or []
        except Exception:
            return []
    return contents or []


def evaluate_log(template_name: str, contents: Any, title: str = "") -> dict:
    """对一份日志评分，返回各维度得分 + 优点/需改进。

    title 传入岗位名时，「数据支撑度」维度按岗位族专属词表判定（结合岗位特质），
    未传则用通用词表。返回结构与旧版一致（score_data 口径随岗位变化）。
    """
    data_words = _data_words_for(title) if title else _DATA_WORDS
    fields = _parse_contents(contents)
    # 非空字段（value 有实质内容）
    nonempty = [c for c in fields if _clean(c.get('value', '')).strip()]
    total_fields = len(fields) or 1

    # 1. 内容完整度 25
    score_completeness = round(25 * len(nonempty) / total_fields)

    # 汇总文本 + 各字段文本
    texts = [_clean(c.get('value', '')).strip() for c in nonempty]
    all_text = '\n'.join(texts)
    paragraphs = [p for p in re.split(r'\n+', all_text) if p.strip()]

    # 2. 数据支撑度 20：含数字信息（金额/数量/百分比/指标/区间）的段落占比
    def _is_data_para(p: str) -> bool:
        stripped = _STRUCT_RE.sub('', p)  # 去掉行首编号，避免把序号当数据
        if not re.search(r'\d', stripped):
            return False
        if re.search(r'\d+\.?\d*\s*[%万亿元月日号单笔人个件分次]', p):  # 数字+常见单位
            return True
        if any(w in p for w in data_words) and re.search(r'\d', p):  # 业务词+数字（岗位族专属词表）
            return True
        if re.search(r'\d{2,}', stripped):                   # 至少2位连续数字（非序号）
            return True
        if re.search(r'\d+[.．\-～~]\d+', stripped):          # 小数/区间数字（1.1、5-9、1.1～2.9）
            return True
        return False

    if paragraphs:
        data_paras = sum(1 for p in paragraphs if _is_data_para(p))
        score_data = round(20 * data_paras / len(paragraphs))
    else:
        score_data = 0

    # 3. 结构化程度 15：编号分点 / 多段落
    struct_hits = len(_STRUCT_RE.findall(all_text))
    if len(paragraphs) >= 4:
        score_structure = 15
    elif struct_hits >= 3 or len(paragraphs) >= 3:
        score_structure = 12
    elif struct_hits >= 1 or len(paragraphs) >= 2:
        score_structure = 8
    else:
        score_structure = 4

    # 4. 规划性 20：规划关键词（含明日计划类字段命中直接高分）
    plan_hits = sum(1 for w in _PLAN_WORDS if w in all_text)
    has_plan_field = any('计划' in c.get('key', '') or '安排' in c.get('key', '') for c in fields)
    if has_plan_field and any(_clean(c.get('value', '')).strip() for c in fields if '计划' in c.get('key', '') or '安排' in c.get('key', '')):
        score_planning = 20
    elif plan_hits >= 2:
        score_planning = 20
    elif plan_hits == 1:
        score_planning = 14
    else:
        score_planning = 5

    # 5. 复盘深度 20：字数梯度 + 复盘关键词
    chars = len(all_text.replace('\n', '').replace(' ', ''))
    review_hits = sum(1 for w in _REVIEW_WORDS if w in all_text)
    if chars >= 500:
        score_depth = 20
    elif chars >= 300:
        score_depth = 18 if review_hits >= 1 else 15
    elif chars >= 150:
        score_depth = 14 if review_hits >= 1 else 10
    elif chars >= 60:
        score_depth = 8 if review_hits >= 1 else 5
    else:
        score_depth = 2

    score_total = score_completeness + score_data + score_structure + score_planning + score_depth

    scores = {
        'completeness': (score_completeness, SCORE_MAX['completeness']),
        'data': (score_data, SCORE_MAX['data']),
        'structure': (score_structure, SCORE_MAX['structure']),
        'planning': (score_planning, SCORE_MAX['planning']),
        'depth': (score_depth, SCORE_MAX['depth']),
    }
    strengths, improvements = _profile_from_scores(scores)

    return {
        'score_total': min(score_total, 100),
        'score_completeness': score_completeness,
        'score_data': score_data,
        'score_structure': score_structure,
        'score_planning': score_planning,
        'score_depth': score_depth,
        'strengths': strengths,
        'improvements': improvements,
    }
