"""
钉钉多维表(Bitable) → 招聘数据库 同步模块。

读取「面试记录-2026」表的未隐藏字段，写入本地 recruitment 数据库。
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from database import SessionLocal
from models import Candidate, Position, Recruiter

logger = logging.getLogger("dingtalk_bitable")

TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
BITABLE_BASE = "https://api.dingtalk.com/v1.0/notable"

# ── 凭证读取 ──
_BITABLE_CREDS = {
    "app_key": "dingeqrywskv5obkaygs",
    "app_secret": "osQiznunErI27T9pn9zpiSBiN4uO0tR4S5Gfyf2hmCIIQqoKcL7pYbci9p4D4U4Q",
    "corp_id": "ding71718385c5b64dd5acaaa37764f94726",
    "app_id": "ZgpG2NdyVXKlg9pBUPyv1eMrWMwvDqPk",
    "table_name": "人事招聘源数据",
    "operator_id": "qlyRmOiSyhCiiqmlNmfykOeQiEiE",
}


class DingTalkBitableClient:
    """钉钉多维表 API 客户端。"""

    def __init__(self):
        self.app_key = _BITABLE_CREDS["app_key"]
        self.app_secret = _BITABLE_CREDS["app_secret"]
        self.app_id = _BITABLE_CREDS["app_id"]
        self.operator_id = _BITABLE_CREDS.get("operator_id", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "hr-dashboard-bitable/1.0",
        })
        self.access_token = ""

    def get_access_token(self) -> str:
        """获取 accessToken（新版 OAuth2）。"""
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
        self.session.headers.update({"x-acs-dingtalk-access-token": self.access_token})
        return self.access_token

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """发送请求到多维表 API，自动附加 operatorId。"""
        if not self.access_token:
            self.get_access_token()
        url = f"{BITABLE_BASE}{path}"
        # 自动添加 operatorId 参数
        params = kwargs.pop("params", {})
        if self.operator_id and "operatorId" not in params:
            params["operatorId"] = self.operator_id
        kwargs["params"] = params
        resp = self.session.request(method, url, timeout=30, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            return {}
        if data.get("code") not in (0, None, ""):
            err_msg = data.get("message", "")
            code = data.get("code", "")
            if "InvalidVersion" in str(code):
                raise RuntimeError(
                    f"多维表API不可用 (code={code})。可能原因：\n"
                    f"1. 该钉钉企业未开通「多维表」功能（需企业管理员在钉钉后台启用）\n"
                    f"2. 应用 ({self.app_key}) 未添加多维表API权限\n"
                    f"请在钉钉开发者后台 → 应用 → 权限管理 → 搜索「多维表」并授权。\n"
                    f"如已授权但仍不可用，请确认企业是否已开通多维表功能。"
                )
            if any(k in str(code) for k in ["Forbidden", "AccessDenied", "PermissionDenied"]):
                raise RuntimeError(
                    f"应用未开通多维表API权限 (code={code})。请在钉钉开发者后台为应用 "
                    f"({self.app_key}) 申请「多维表」相关权限。详情: {err_msg}"
                )
            raise RuntimeError(f"多维表接口失败: {code} - {err_msg}")
        resp.raise_for_status()
        return data.get("data") or data

    def list_tables(self) -> list[dict[str, Any]]:
        """获取多维表中的所有数据表（sheets）。"""
        result = self._request("GET", f"/bases/{self.app_id}/sheets")
        # notable API 返回 {"value": [{"name":..., "id":...}, ...]}
        return result.get("value", result if isinstance(result, list) else [])

    def get_table_id(self, table_name: str) -> str | None:
        """根据数据表名获取 sheetId（同名时取记录数最大的）。"""
        tables = self.list_tables()
        matches = [t for t in tables if t.get("name") == table_name]
        if not matches:
            if tables:
                logger.info("可用的数据表: %s", [t.get("name") for t in tables])
            return None
        # 同名时：遍历各表快速估算记录数，取最大者
        if len(matches) == 1:
            return matches[0].get("id")
        # 快速检测每张表是否有数据（取1条判断）
        best_id = None
        best_records = 0
        for mt in matches:
            mid = mt.get("id", "")
            if not mid:
                continue
            try:
                result = self.list_records(mid, page_size=1)
                has = result.get("hasMore", False) or len(result.get("records", [])) > 0
                # 获取实际记录数估算（hasMore 表示>1页，即>100条）
                if has and result.get("nextToken"):
                    # 至少有两页，取第二页进一步判断
                    result2 = self.list_records(mid, page_token=result.get("nextToken"), page_size=1)
                    if result2.get("nextToken"):
                        best_id, best_records = mid, 9999  # 很多页
                    else:
                        best_id, best_records = mid, 200
                elif has:
                    best_id, best_records = mid, 100
                elif best_id is None:
                    best_id, best_records = mid, 1
            except Exception:
                continue
        logger.info("同名表 %s 多个(%d个)，选择 %s (估算~%d条)", table_name, len(matches), best_id, best_records)
        return best_id or matches[0].get("id")

    def list_fields(self, sheet_id: str) -> list[dict[str, Any]]:
        """获取数据表的字段定义。"""
        result = self._request("GET", f"/bases/{self.app_id}/sheets/{sheet_id}/fields")
        if isinstance(result, list):
            return result
        return result.get("value", result.get("fields", result.get("items", [])))

    def list_records(
        self,
        sheet_id: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """分页读取数据表记录。"""
        body: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            body["nextToken"] = page_token
        result = self._request("POST", f"/bases/{self.app_id}/sheets/{sheet_id}/records/list", json=body)
        return result


def inspect_bitable() -> dict[str, Any]:
    """检查多维表结构：表信息、字段列表。"""
    client = DingTalkBitableClient()
    try:
        client.get_access_token()
    except Exception as e:
        return {"error": f"钉钉认证失败: {e}", "tables": [], "fields": {}}

    result = {"tables": [], "fields": {}, "records_count": 0, "error": None}

    try:
        tables = client.list_tables()
        if isinstance(tables, dict):
            tables = tables.get("tables", [])
        result["tables"] = [{"name": t.get("name"), "id": t.get("id")} for t in tables]
        logger.info("数据表列表: %s", result["tables"])

        # 找到目标表
        target_table_id = client.get_table_id(_BITABLE_CREDS["table_name"])
        if not target_table_id:
            result["error"] = f"未找到数据表: {_BITABLE_CREDS['table_name']}"
            return result

        # 获取字段
        fields = client.list_fields(target_table_id)
        visible_fields = [f for f in fields if not f.get("property", {}).get("hidden", False)]
        hidden_fields = [f for f in fields if f.get("property", {}).get("hidden", False)]

        result["fields"] = {
            "total": len(fields),
            "visible": [
                {"name": f.get("name"), "type": f.get("type"), "id": f.get("id")}
                for f in visible_fields
            ],
            "hidden": [
                {"name": f.get("name"), "type": f.get("type"), "id": f.get("id")}
                for f in hidden_fields
            ],
        }
        logger.info("可见字段: %s", [f["name"] for f in result["fields"]["visible"]])
        logger.info("隐藏字段: %s", [f["name"] for f in result["fields"]["hidden"]])

        return result

    except Exception as e:
        result["error"] = str(e)
        logger.exception("检查多维表失败")
        return result


def sync_recruitment_data() -> dict[str, Any]:
    """从多维表同步招聘数据到本地库。"""
    client = DingTalkBitableClient()
    client.get_access_token()

    sheet_id = client.get_table_id(_BITABLE_CREDS["table_name"])
    if not sheet_id:
        return {"synced": 0, "error": f"未找到数据表: {_BITABLE_CREDS['table_name']}"}

    logger.info("使用数据表: %s", sheet_id)

    # 获取字段定义（未隐藏字段）
    fields = client.list_fields(sheet_id)
    visible_fields = [f for f in fields if not f.get("property", {}).get("hidden", False)]
    visible_field_names = {f.get("name") for f in visible_fields}
    logger.info("可见字段(%d个): %s", len(visible_field_names), sorted(visible_field_names))

    # 分页读取所有记录
    all_records: list[dict[str, Any]] = []
    page_token = None
    while True:
        result = client.list_records(sheet_id, page_size=500, page_token=page_token)
        records = result.get("records", result.get("value", []))
        if isinstance(result, list):
            records = result
            all_records.extend(records)
            break
        all_records.extend(records)
        has_more = result.get("hasMore", False)
        page_token = result.get("nextToken")
        if not has_more or not page_token:
            break
        time.sleep(0.3)

    logger.info("共读取 %s 条面试记录", len(all_records))

    # ── 字段名映射（钉钉→本地）──
    def _field(rec: dict, name: str):
        """安全获取字段值。"""
        return (rec.get("fields") or rec).get(name, "")

    def _parse_ts(val):
        """将毫秒时间戳转为 date。"""
        if not val:
            return None
        try:
            from datetime import datetime as dt
            return dt.fromtimestamp(int(val) / 1000).date()
        except (ValueError, TypeError):
            return None

    def _extract_name(val):
        """从 {'name': '...', 'id': '...'} 提取 name。"""
        if isinstance(val, dict):
            return val.get("name", "")
        return str(val) if val else ""

    def _map_pass(val):
        """映射面试结果。"""
        name = _extract_name(val)
        if name == "通过":
            return "pass"
        if name in ("pass", "不通过"):
            return "fail"
        return None

    # ── 写入数据库（单事务原子提交：先校验拉取结果非空，再清空+写入一次commit）──
    # 防呆保护：钉钉返回0条时中止同步，避免清空本地已有数据
    if not all_records:
        logger.error("⚠️ 钉钉多维表返回 0 条记录，已中止同步以保护现有数据")
        return {"synced": 0, "error": "钉钉多维表返回 0 条记录，已中止同步以保护现有数据"}

    db = SessionLocal()
    try:
        # 清空旧数据（重新同步，防止重复）— 与下方写入同处一个事务，进程中断会自动回滚，不会留下空库
        db.query(Candidate).delete()
        db.query(Position).delete()
        db.query(Recruiter).delete()

        synced = 0
        for rec in all_records:
            fields_data = rec.get("fields", rec)
            if not fields_data:
                continue

            name = _field(rec, "姓名") or ""
            if not name:
                continue

            candidate = Candidate()
            candidate.name = str(name)
            candidate.status = _determine_status(fields_data)

            dept_name = str(_field(rec, "一级部门") or _field(rec, "部门") or "")
            pos_name = _extract_name(_field(rec, "岗位名称")) or _extract_name(_field(rec, "岗位")) or ""

            # 日期字段
            attended = _parse_date(_field(rec, "到面日期"))
            candidate.interview_attended_date = attended
            candidate.resume_received_date = attended  # 用到面日期作为简历接收日期（漏斗统计用）

            # 试岗日期 = 入职日期（新表字段替换，text类型如"2026-03-09"）
            onboard = _parse_date(_field(rec, "试岗日期"))
            if onboard:
                candidate.onboard_date = onboard
                # 有试岗日期的视为已到岗
                candidate.status = "已到岗"

            # 面试结果
            candidate.first_round_pass = _map_pass(_field(rec, "初试结果"))
            candidate.second_round_pass = _map_pass(_field(rec, "复试结果"))

            # Offer 已发送 = 复试结果="通过"（用户口径：已发送=复试通过）
            # 发送日期优先用试岗日期，否则用真实到面日期（多维表无复试日期字段）
            if candidate.second_round_pass == "pass":
                candidate.offer_sent_date = onboard or attended

            # 放弃Offer原因 → 记录原因与状态（offer接收状态以"是否试岗"为准）
            reject_reason = _extract_name(_field(rec, "放弃offer原因"))
            if reject_reason:
                candidate.decline_reason = reject_reason
                if not candidate.offer_accepted:
                    candidate.status = "放弃Offer"

            # 是否试岗 → Offer 接收状态（用户口径：是=已接收，否=已拒绝）
            is_probation = _extract_name(_field(rec, "是否试岗"))
            if is_probation == "是":
                candidate.offer_accepted = "accepted"
                if not candidate.status or candidate.status == "简历初筛":
                    candidate.status = "已接收"
            elif is_probation == "否":
                candidate.offer_accepted = "rejected"
                if not candidate.status or candidate.status in ("简历初筛", "初试通过", "复试通过"):
                    candidate.status = "已拒绝"

            # 试岗结果=入职 → 满7天
            prob_result = _extract_name(_field(rec, "试岗结果"))
            if prob_result == "入职":
                candidate.retention_7day = "yes"
                if not candidate.status or candidate.status in ("简历初筛", "已接收"):
                    candidate.status = "已到岗"

            # 岗位
            if pos_name:
                pos = db.query(Position).filter(Position.name == pos_name).first()
                if not pos:
                    pos = Position(name=pos_name, department=dept_name or "未知", headcount=1)
                    db.add(pos)
                    db.flush()
                candidate.position_id = pos.id

            # 招聘人员（过滤非人员条目）
            recruiter_name = str(_field(rec, "招聘人员") or _field(rec, "招聘邀约人") or "")
            if (recruiter_name 
                and "内推" not in recruiter_name 
                and "/" not in recruiter_name
                and recruiter_name not in ("", "无", "暂无")):
                rec_inst = db.query(Recruiter).filter(Recruiter.name == recruiter_name).first()
                if not rec_inst:
                    # 从花名册获取招聘人员的真实部门
                    from models import Employee
                    emp = db.query(Employee).filter(Employee.name == recruiter_name).first()
                    rec_dept = emp.department if emp else "招聘部"
                    rec_inst = Recruiter(name=recruiter_name, department=rec_dept)
                    db.add(rec_inst)
                    db.flush()
                candidate.recruiter_id = rec_inst.id

            db.add(candidate)
            synced += 1

        db.commit()
        logger.info("同步完成: %s 条记录（已清空旧数据）", synced)

        # ── 已到岗 = 面试记录筛选结果 与 试岗记录表 姓名交集 ──
        try:
            _sync_onboarded_status(db, client)
        except Exception as e:
            logger.warning("已到岗同步失败（不影响主流程）: %s", e)

        return {
            "synced": synced,
            "message": f"成功同步 {synced} 条面试记录",
            "fields": list(visible_field_names),
        }

    except Exception:
        db.rollback()
        logger.exception("同步失败")
        raise
    finally:
        db.close()


def _sync_onboarded_status(db, client):
    """
    已到岗/满7天 兜底标记（新表「人事招聘源数据」已合并试岗数据）。

    主循环已处理：
      - 试岗日期 → onboard_date + 已到岗
      - 试岗结果=入职 → retention_7day + 已到岗
    此处仅对数据库中的候选人做交叉兜底（无外部表依赖）。
    """
    from datetime import date
    from models import Candidate

    today = date.today()

    # 1. 满7天：有 onboard_date 且 retention_7day 已标记的无需重复处理
    #    这里处理主循环遗漏的情况：初试通过+复试通过+已接收Offer，但试岗结果缺失
    matched = db.query(Candidate).filter(
        Candidate.interview_attended_date >= date(today.year, today.month, 1),
        Candidate.interview_attended_date <= date(today.year, today.month, 31),
        Candidate.first_round_pass == "pass",
        Candidate.second_round_pass == "pass",
        Candidate.offer_accepted == "accepted",
        Candidate.onboard_date.is_(None),
    ).all()

    if matched:
        for c in matched:
            c.status = "已到岗"
        db.commit()
        logger.info("已到岗兜底: %s 人", len(matched))


def _determine_status(fields: dict) -> str:
    """根据字段判断当前状态。"""
    from datetime import date
    # 优先检查试岗日期（替代入职日期）
    if fields.get("试岗日期"):
        return "已到岗"
    # 是否有放弃原因
    reject = str(fields.get("放弃offer原因", "") or "")
    if reject:
        return "放弃Offer"
    # 检查面试结果
    def _result_name(val):
        if isinstance(val, dict):
            return val.get("name", "")
        return str(val) if val else ""
    # 是否试岗（用户口径：是=已接收，否=已拒绝）
    is_probation = _result_name(fields.get("是否试岗", ""))
    if is_probation == "是":
        return "已接收"
    if is_probation == "否":
        return "已拒绝"
    first = _result_name(fields.get("初试结果", ""))
    second = _result_name(fields.get("复试结果", ""))
    if second == "通过":
        return "复试通过"
    if second in ("pass", "不通过"):
        return "复试未通过"
    if first == "通过":
        return "初试通过"
    if first in ("pass", "不通过"):
        return "初试未通过"
    return "简历初筛"


def _parse_date(val: Any):
    """将多维表日期值转为 Python date。"""
    from datetime import date
    if val is None:
        return None
    if isinstance(val, (int, float)):
        # 毫秒时间戳
        from datetime import datetime as dt
        return dt.fromtimestamp(val / 1000).date()
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
            try:
                from datetime import datetime as dt
                return dt.strptime(val.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
    return None


def _map_pass_result(val: Any) -> str | None:
    """映射面试结果到 pass/fail。"""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("通过", "pass", "Pass", "PASS", "是", "yes", "YES", "Y"):
        return "pass"
    if s in ("不通过", "fail", "Fail", "FAIL", "否", "no", "NO", "N"):
        return "fail"
    return None


def _map_accept_result(val: Any) -> str | None:
    """映射Offer结果。"""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("已接收", "接受", "accepted", "Accepted", "是", "yes"):
        return "accepted"
    if s in ("已拒绝", "拒绝", "rejected", "Rejected", "否", "no"):
        return "rejected"
    return None


def run_inspect() -> dict[str, Any]:
    """排查多维表结构（供 API 调用）。"""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        return inspect_bitable()
    except Exception as e:
        logger.exception("检查异常")
        return {"error": str(e)}


def run_sync() -> dict[str, Any]:
    """执行同步（供 API 调用）。"""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        return sync_recruitment_data()
    except Exception as e:
        logger.exception("同步异常")
        return {"synced": 0, "error": str(e)}
