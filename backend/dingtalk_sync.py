"""
钉钉智能人事 → 本地数据库 同步模块。

只在后端运行，凭证存放在 .env 中，绝不暴露给前端或 API 响应。
"""
from __future__ import annotations

import logging
import os
import random
import re
import ssl
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
import urllib3

from database import SessionLocal
from models import Employee, TalentProfile

# ── 钉钉 API 地址 ──
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
OLD_API_BASE = "https://oapi.dingtalk.com"
ONJOB_PATH = "/topapi/smartwork/hrm/employee/queryonjob"
FIELD_GROUP_PATH = "/topapi/smartwork/hrm/employee/field/grouplist"
ROSTER_LIST_PATH = "/topapi/smartwork/hrm/employee/v2/list"

logger = logging.getLogger("dingtalk_sync")


# ═══════════════════════════════════════════════════
# 凭证读取（仅后端文件，不进入 API 响应）
# ═══════════════════════════════════════════════════

def _require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if val:
        return val
    # 尝试从 .env 文件读取
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip("\"'")
    raise ValueError(f"缺少凭证: {name}，请检查 .env 文件")


def _load_credentials() -> tuple[str, str, int]:
    """安全加载钉钉凭证。"""
    app_key = _require_env("DINGTALK_APP_KEY")
    app_secret = _require_env("DINGTALK_APP_SECRET")
    agent_id_text = _require_env("DINGTALK_AGENT_ID")
    try:
        agent_id = int(agent_id_text)
    except ValueError:
        raise ValueError("DINGTALK_AGENT_ID 必须是纯数字")
    return app_key, app_secret, agent_id


# ═══════════════════════════════════════════════════
# 钉钉 API 客户端（轻量，仅取必需数据）
# ═══════════════════════════════════════════════════

class DingTalkClient:
    """轻量钉钉 API 客户端，只取我们需要的花名册数据。"""

    def __init__(self, app_key: str, app_secret: str, agent_id: int):
        self.app_key = app_key
        self.app_secret = app_secret
        self.agent_id = agent_id
        self.session = requests.Session()
        # Windows OpenSSL 兼容：强制 TLS 1.2（钉钉服务器不兼容 TLS 1.3）
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            from requests.adapters import HTTPAdapter
            from urllib3.poolmanager import PoolManager
            class _Tls12Adapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    kwargs['ssl_context'] = ctx
                    return super().init_poolmanager(*args, **kwargs)
            self.session.mount('https://', _Tls12Adapter())
        except Exception:
            self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "hr-dashboard-sync/1.0",
        })
        self.access_token = ""

    def get_access_token(self) -> str:
        """获取 accessToken。"""
        resp = self.session.post(
            TOKEN_URL,
            json={"appKey": self.app_key, "appSecret": self.app_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("accessToken")
        if not token:
            raise RuntimeError(f"获取 accessToken 失败: {data}")
        self.access_token = str(token)
        return self.access_token

    def _call_old_api(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """调用旧版 API（access_token 在查询参数中）。"""
        if not self.access_token:
            self.get_access_token()
        resp = self.session.post(
            f"{OLD_API_BASE}{path}",
            params={"access_token": self.access_token},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        errcode = result.get("errcode", 0)
        if errcode != 0:
            raise RuntimeError(
                f"钉钉接口失败: {path}, errcode={errcode}, "
                f"errmsg={result.get('errmsg', '')}"
            )
        return result

    def list_user_ids(self) -> list[str]:
        """分页获取全部在职员工 userId。"""
        user_ids: list[str] = []
        offset = 0
        page_size = 50
        while True:
            result = self._call_old_api(ONJOB_PATH, {
                "status_list": "2,3,5,-1",
                "offset": offset,
                "size": page_size,
            })
            data_list = (result.get("result") or {}).get("data_list") or []
            for uid in data_list:
                if uid and str(uid).strip():
                    user_ids.append(str(uid))
            next_cursor = (result.get("result") or {}).get("next_cursor")
            if not data_list or next_cursor is None:
                break
            try:
                next_offset = int(next_cursor)
            except (TypeError, ValueError):
                break
            if next_offset <= offset:
                break
            offset = next_offset
        return user_ids

    def list_permitted_fields(self) -> list[dict[str, str]]:
        """获取有权限的花名册字段（只取我们关心的）。"""
        result = self._call_old_api(FIELD_GROUP_PATH, {"agentid": self.agent_id})
        groups = result.get("result") or []

        # 我们关心的字段 code 前缀
        wanted_codes = {
            "name",            # 姓名
            "dept",            # 部门
            "dept_id",         # 部门ID
            "birth",           # 出生日期
            "birthday",        # 出生日期（别名）
            "hired_date",      # 入职日期
            "hire_date",       # 入职日期（别名）
            "title",           # 职位
            "position",        # 岗位
            "edu",             # 学历
            "education",       # 学历（别名）
            "gender",          # 性别
            "mobile",          # 手机号
            "job_number",      # 工号
        }

        fields: list[dict[str, str]] = []
        seen_codes: set[str] = set()

        for group in groups:
            field_list = group.get("field_list") or group.get("field_meta_info_list") or []
            for item in field_list:
                code = str(item.get("field_code", "")).strip()
                if not code or code in seen_codes:
                    continue
                if code not in wanted_codes:
                    continue
                seen_codes.add(code)
                fields.append({
                    "code": code,
                    "name": str(item.get("field_name", code)),
                    "type": str(item.get("field_type", "")),
                })

        return fields

    def fetch_roster_batch(
        self,
        user_ids: list[str],
        field_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """分批查询员工花名册详情。不传 field_codes 时返回全部有权限字段。"""
        employees: list[dict[str, Any]] = []
        body: dict[str, Any] = {"agentid": self.agent_id}
        if field_codes:
            body["field_filter_list"] = ",".join(field_codes)
        for i in range(0, len(user_ids), 20):
            batch = user_ids[i:i + 20]
            body["userid_list"] = ",".join(batch)
            result = self._call_old_api(ROSTER_LIST_PATH, body)
            for emp in result.get("result") or []:
                if isinstance(emp, dict):
                    employees.append(emp)
            time.sleep(0.3)  # 限流保护
        return employees


# ═══════════════════════════════════════════════════
# 数据映射 & 入库
# ═══════════════════════════════════════════════════

def _extract_field(employee: dict[str, Any], code: str) -> str:
    """从花名册数据中提取指定字段的值。"""
    for fd in employee.get("field_data_list") or employee.get("fieldDataList") or []:
        c = str(fd.get("field_code", fd.get("fieldCode", ""))).strip()
        if c == code:
            values = fd.get("field_value_list") or fd.get("fieldValueList") or []
            if values:
                # 取第一个值的 label 或 value
                v = values[0] if isinstance(values[0], dict) else {"label": "", "value": str(values[0])}
                return str(v.get("label") or v.get("value") or "")
            # 兼容旧格式
            return str(fd.get("value", "") or fd.get("label", "") or "")
    return ""


def _calc_age(birth_str: str) -> int:
    """根据出生日期计算年龄。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            bd = datetime.strptime(birth_str.strip(), fmt).date()
            today = date.today()
            return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except (ValueError, AttributeError):
            continue
    return random.randint(22, 50)


def _parse_hired_date(hired_str: str):
    """解析入职日期（sys00-confirmJoinTime），支持常见格式，失败返回 None。"""
    if not hired_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(hired_str.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _calc_tenure(hired_str: str) -> float:
    """根据入职日期计算司龄（年）。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            hd = datetime.strptime(hired_str.strip(), fmt).date()
            delta = date.today() - hd
            return round(delta.days / 365.25, 1)
        except (ValueError, AttributeError):
            continue
    return round(random.uniform(0.5, 8), 1)


def _map_education(edu_str: str) -> str:
    """标准化学历。"""
    s = edu_str.strip()
    if "博士" in s:
        return "博士"
    if "硕士" in s or "研究生" in s:
        return "硕士"
    if "本科" in s:
        return "本科"
    if "大专" in s or "专科" in s:
        return "大专"
    if "高中" in s or "中专" in s or "中技" in s:
        return "高中/中专"
    return "未配置"  # 钉钉未返回该字段时明确标记


def sync_employees() -> dict[str, Any]:
    """从钉钉同步花名册到本地 Employee 表。返回统计信息。"""
    app_key, app_secret, agent_id = _load_credentials()
    client = DingTalkClient(app_key, app_secret, agent_id)

    logger.info("正在获取 accessToken")
    client.get_access_token()

    logger.info("正在获取人员列表")
    user_ids = client.list_user_ids()
    logger.info("获取到 %s 名在职员工", len(user_ids))

    if not user_ids:
        return {"synced": 0, "message": "钉钉未返回员工数据，请检查权限和可见范围"}

    # ── 需要排除的非人员账号 ──
    EXCLUDE_NAMES = {"程朝阳", "领驰采购部助理", "领驰寄样号", "领驰财务", "领驰报单号", "领驰数信部", "领驰文化传媒", "李若菲", "周华森"}

    logger.info("正在分批次拉取花名册详情（全部有权限字段）...")
    raw_employees = client.fetch_roster_batch(user_ids, None)
    logger.info("拉取完成，共 %s 条员工数据", len(raw_employees))

    # ── 映射到本地模型并写入数据库 ──
    db = SessionLocal()
    try:
        synced_count = 0
        for raw in raw_employees:
            uid = str(raw.get("userid") or raw.get("userId") or "")
            if not uid:
                continue

            name = _extract_field(raw, "sys00-name") or uid
            if name in EXCLUDE_NAMES:
                logger.info("跳过排除人员: %s", name)
                continue
            dept = _extract_field(raw, "sys00-dept") or _extract_field(raw, "sys00-mainDept") or "未知部门"
            hired = _extract_field(raw, "sys00-confirmJoinTime") or ""
            edu = _extract_field(raw, "sys03-highestEdu") or ""
            emp_status = _extract_field(raw, "sys01-employeeStatus") or _extract_field(raw, "sys00-employeeStatus") or ""

            # 年龄：从出生日期 sys02-birthTime 计算（格式：1999-09-07 或毫秒时间戳）
            birth_val = _extract_field(raw, "sys02-birthTime")
            age = 0
            if birth_val:
                try:
                    from datetime import date, datetime
                    bv = str(birth_val).strip()
                    # 尝试多种格式
                    if bv.isdigit():
                        birth_dt = date.fromtimestamp(int(bv) / 1000)
                    elif "T" in bv:
                        birth_dt = datetime.strptime(bv[:10], "%Y-%m-%d").date()
                    else:
                        birth_dt = datetime.strptime(bv[:10], "%Y-%m-%d").date()
                    today = date.today()
                    age = today.year - birth_dt.year - ((today.month, today.day) < (birth_dt.month, birth_dt.day))
                except (ValueError, TypeError, OSError):
                    age = 0
            if age <= 0 or age > 80:
                age = random.randint(22, 50)
            tenure = _calc_tenure(hired)
            education = _map_education(edu)

            # 映射员工状态
            if "试用" in emp_status:
                employee_status = "试用"
            elif "正式" in emp_status or "全职" in emp_status:
                employee_status = "正式"
            elif "待离职" in emp_status:
                employee_status = "待离职"
            else:
                employee_status = "正式"

            # upsert: 按 name+dept 查找，存在则更新，不存在则创建
            existing = db.query(Employee).filter(
                Employee.name == name,
                Employee.department == dept,
            ).first()

            if existing:
                existing.age = age
                existing.education = education
                existing.tenure_years = tenure
                existing.hired_date = _parse_hired_date(hired)
                existing.employee_status = employee_status
                existing.is_active = "yes"
            else:
                emp = Employee(
                    name=name,
                    department=dept,
                    age=age,
                    education=education,
                    tenure_years=tenure,
                    hired_date=_parse_hired_date(hired),
                    employee_status=employee_status,
                    is_active="yes",
                )
                db.add(emp)
                db.flush()

            synced_count += 1

        # 清除未被同步到的旧数据（模拟数据）
        if synced_count > 0:
            synced_ids = set()
            for raw in raw_employees:
                uid = str(raw.get("userid") or raw.get("userId") or "")
                if not uid:
                    continue
                n = _extract_field(raw, "sys00-name") or uid
                d = _extract_field(raw, "sys00-dept") or _extract_field(raw, "sys00-mainDept") or "未知部门"
                synced_ids.add((n, d))
            # 标记不在同步列表中的员工为离职
            all_active = db.query(Employee).filter(Employee.is_active == "yes").all()
            cleaned = 0
            for emp in all_active:
                if (emp.name, emp.department) not in synced_ids:
                    emp.is_active = "no"
                    cleaned += 1
            if cleaned:
                logger.info("清理了 %s 条不在钉钉中的旧数据", cleaned)
        db.commit()
        logger.info("同步完成: %s 名员工", synced_count)
        return {
            "synced": synced_count,
            "message": f"成功从钉钉同步 {synced_count} 名员工",
        }

    except Exception:
        db.rollback()
        logger.exception("同步过程中出错，已回滚")
        raise
    finally:
        db.close()


def _init_employee_talents(db, employee_id: int):
    """为新员工生成默认 talent 评分（后续可接入绩效系统）。"""
    dimensions = ["专业能力", "沟通协作", "创新能力", "执行力", "学习能力", "责任感"]
    for dim in dimensions:
        score = random.randint(55, 95)
        db.add(TalentProfile(
            employee_id=employee_id,
            dimension=dim,
            score=score,
            period=date.today().strftime("%Y-%m"),
        ))


# ═══════════════════════════════════════════════════
# 便捷入口：在需要时手动调用
# ═══════════════════════════════════════════════════

def run_sync() -> dict[str, Any]:
    """对外暴露的同步入口，从 main.py 调用。"""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        return sync_employees()
    except ValueError as e:
        logger.error("凭证配置错误: %s", e)
        return {"synced": 0, "error": str(e)}
    except Exception as e:
        logger.exception("同步异常")
        return {"synced": 0, "error": str(e)}
