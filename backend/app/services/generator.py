"""发电机业务规则：状态流转、字段校验、清单导出与历史检测记录批量导入。"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "generator"
# 清单与详情保持一致的列序，导出直接复用，避免漏列或同名列重复拼接。
FIELDS = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
REQUIRED_FIELDS = ["发电机编号", "所属机组"]
# 这几列在导入时按数值校验，禁止携带单位（例如 “32℃”“120MΩ”），否则该行单独报错。
NUMERIC_FIELDS = ["额定电压", "绝缘电阻", "轴承温度"]
STATUS_ORDER = ["待检测", "检测合格", "绝缘偏低", "已更换"]
ACTION_RULES = {"提交检测": "检测合格", "判定绝缘异常": "绝缘偏低", "更换发电机": "已更换"}
NEGATIVE_ACTIONS = ["判定绝缘异常"]
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d+)?|\.\d+)$")
_DATE_FMT = "%Y-%m-%d"


class GeneratorService:
    """service 是模块级单例，导入去重指纹挂在实例上即可跨请求保留。"""

    def __init__(self) -> None:
        self._import_fingerprints: set[str] = set()

    def _filtered_rows(self, *, keyword: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("发电机编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 同一台发电机（编号相同）只保留一行，避免清单和导出里出现重复行。
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            code = str(row.get("发电机编号", ""))
            if code in seen:
                continue
            seen.add(code)
            deduped.append(row)
        return deduped

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_entries(self, *, keyword: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """导出当前筛选条件下的全量记录，按 FIELDS 投影，列与详情页完全一致且不重复。"""
        return [self._project(row) for row in self._filtered_rows(keyword=keyword, status=status)]

    def _project(self, row: dict[str, Any]) -> dict[str, Any]:
        projected = {field: row.get(field) for field in FIELDS}
        if not projected.get("发电机状态"):
            projected["发电机状态"] = row.get("status")
        return projected

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"发电机 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于发电机可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        # 同步对外展示的「发电机状态」列，保证清单/详情/导出三处口径一致。
        entry["发电机状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"发电机已{action}"

    # ------------------------------------------------------------------
    # 历史检测记录批量导入
    # ------------------------------------------------------------------
    def import_history(self, content: str) -> dict[str, Any]:
        """逐行校验导入：成功行立即入库，失败行带原因单列；整批不再因个别坏行被拦。"""
        normalized = (content or "").lstrip("﻿").strip()
        if not normalized:
            return self._import_summary(
                ok=False,
                message="导入文件为空，未导入任何记录",
            )

        # 同一文件（内容一致）重复导入只记一次。
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if fingerprint in self._import_fingerprints:
            return self._import_summary(
                ok=True,
                duplicated=True,
                message="该文件已导入过，重复导入只记一次，本次未新增记录",
            )

        reader = csv.reader(io.StringIO(normalized))
        try:
            header = next(reader)
        except StopIteration:
            return self._import_summary(ok=False, message="导入文件为空，未导入任何记录")
        header = [name.strip() for name in header]
        if "发电机编号" not in header:
            return self._import_summary(
                ok=False,
                message="导入文件缺少「发电机编号」列，请使用与导出清单一致的表头后重试",
            )
        index = {name: pos for pos, name in enumerate(header) if name}

        rows = store.rows(MODULE)
        existing_codes = {str(row.get("发电机编号", "")).strip() for row in rows}
        seen_codes: set[str] = set()
        imported: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        parsed = 0

        def cell(line: list[str], field: str) -> str:
            pos = index.get(field)
            if pos is None or pos >= len(line):
                return ""
            return str(line[pos] or "").strip()

        for line_no, raw_line in enumerate(reader, start=2):
            line = [value.strip() for value in raw_line]
            if not any(line):
                continue  # 跳过空行，不计入解析行数
            parsed += 1
            code = cell(line, "发电机编号")
            reasons: list[str] = []

            for field in REQUIRED_FIELDS:
                if not cell(line, field):
                    reasons.append(f"缺少必填字段「{field}」")
            for field in NUMERIC_FIELDS:
                value = cell(line, field)
                if value and not _NUMBER_RE.match(value):
                    reasons.append(f"「{field}」必须是纯数值，不能携带单位或文字（当前值：{value}）")
            check_date = cell(line, "上次检测日")
            if check_date:
                try:
                    datetime.strptime(check_date, _DATE_FMT)
                except ValueError:
                    reasons.append(f"「上次检测日」需为 YYYY-MM-DD 日期格式（当前值：{check_date}）")
            status_text = cell(line, "发电机状态")
            if status_text and status_text not in STATUS_ORDER:
                reasons.append(f"「发电机状态」只能是：{'、'.join(STATUS_ORDER)}（当前值：{status_text}）")
            if code:
                if code in existing_codes:
                    reasons.append(f"发电机编号「{code}」已存在，不能重复导入")
                elif code in seen_codes:
                    reasons.append(f"发电机编号「{code}」在同一文件中重复出现")

            if reasons:
                failures.append({"line": line_no, "发电机编号": code or None, "reason": "；".join(reasons)})
                continue

            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            for field in FIELDS:
                entry[field] = cell(line, field)
            entry["status"] = status_text or STATUS_ORDER[0]
            entry["发电机状态"] = entry["status"]
            entry["pending"] = entry["status"] != STATUS_ORDER[-1]
            entry["abnormal"] = entry["status"] == STATUS_ORDER[2]
            rows.append(entry)
            seen_codes.add(code)
            imported.append(entry)

        # 只要有成功入库的行才登记指纹；全是坏行时允许修好后再次提交同一文件。
        if imported:
            self._import_fingerprints.add(fingerprint)

        if imported and failures:
            message = f"已导入 {len(imported)} 条，{len(failures)} 条格式不符已单独列出，成功部分已保留"
            ok = True
        elif imported:
            message = f"全部 {len(imported)} 条历史检测记录导入成功"
            ok = True
        else:
            message = f"{len(failures)} 条记录均未通过校验，未导入任何数据"
            ok = False
        return self._import_summary(
            ok=ok,
            total=parsed,
            imported=len(imported),
            failures=failures,
            message=message,
            items=imported,
        )

    @staticmethod
    def _import_summary(
        *,
        ok: bool,
        message: str,
        duplicated: bool = False,
        total: int = 0,
        imported: int = 0,
        failures: list[dict[str, Any]] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "duplicated": duplicated,
            "total": total,
            "imported": imported,
            "failed": len(failures or []),
            "message": message,
            "failures": failures or [],
            "items": items or [],
        }
