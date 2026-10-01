"""发电机业务规则：状态流转、字段校验、筛选口径与批量导入都收在这里。"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any

from app.store import store

MODULE = "generator"
# 与发电机详情页一致的字段顺序，导出清单只取这些列且不重复
DETAIL_FIELDS = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
REQUIRED_FIELDS = ["发电机编号", "所属机组", "额定电压"]
# 数量列必须是纯数字，写成“3 台”这类带单位的值只让该行失败
NUMERIC_FIELDS = ["数量"]
STATUS_ORDER = ["待检测", "检测合格", "绝缘偏低", "已更换"]
ACTION_RULES = {"提交检测": "检测合格", "判定绝缘异常": "绝缘偏低", "更换发电机": "已更换"}
NEGATIVE_ACTIONS = ["判定绝缘异常"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_DEDUP_KEY = "发电机编号"

# 已成功导入过的文件指纹：同一文件重复导入只记一次
_imported_files: set[str] = set()


class GeneratorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        unit: str | None = None,
        voltage: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status, unit=unit, voltage=voltage)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def export_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        unit: str | None = None,
        voltage: str | None = None,
    ) -> list[dict[str, Any]]:
        """当前过滤条件下的全量记录：按发电机编号去重，只保留详情页字段，且字段不重复。"""
        rows = self._filter_rows(keyword=keyword, status=status, unit=unit, voltage=voltage)
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = str(row.get(_DEDUP_KEY) or "").strip()
            if key in seen:
                continue
            seen.add(key)
            result.append({field: row.get(field) for field in DETAIL_FIELDS})
        return result

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = self._build_entry(values)
        entry["id"] = max((int(row.get("id", 0)) for row in rows), default=0) + 1
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
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"发电机已{action}"

    def import_rows(self, content: str, filename: str | None = None) -> dict[str, Any]:
        """逐行校验导入历史检测记录。

        合法的行立即落库并保留；不合法的行只把该行记为失败并说明原因，不影响其它行。
        同一文件（按内容指纹）重复导入时整体跳过，只记一次。
        """
        text = content[1:] if content.startswith("\ufeff") else content
        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if fingerprint in _imported_files:
            return {
                "ok": True,
                "duplicate": True,
                "filename": filename,
                "total": 0,
                "imported": 0,
                "failures": [],
                "entries": [],
                "message": "该文件已导入过，为避免重复记账本次未再写入任何记录",
            }

        if not text.strip():
            return {
                "ok": False,
                "duplicate": False,
                "filename": filename,
                "total": 0,
                "imported": 0,
                "failures": [],
                "entries": [],
                "message": "文件内容为空，没有可导入的检测记录",
            }

        reader = csv.reader(io.StringIO(text), delimiter=self._detect_delimiter(text))
        records = list(reader)
        header = [cell.strip() for cell in records[0]]
        missing_columns = [field for field in REQUIRED_FIELDS if field not in header]
        if missing_columns:
            return {
                "ok": False,
                "duplicate": False,
                "filename": filename,
                "total": 0,
                "imported": 0,
                "failures": [],
                "entries": [],
                "message": f"表头缺少必填列：{'、'.join(missing_columns)}",
            }

        rows = store.rows(MODULE)
        existing = {str(row.get(_DEDUP_KEY) or "").strip() for row in rows}
        seen: set[str] = set()
        entries: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = 0
        for offset, raw in enumerate(records[1:], start=2):
            values = {
                header[i]: (raw[i].strip() if i < len(raw) else "")
                for i in range(len(header))
            }
            if not any(str(value).strip() for value in values.values()):
                continue
            total += 1
            row_preview = {key: value for key, value in values.items() if key}
            reason = self._validate_row(values, existing | seen)
            if reason:
                failures.append({"line": offset, "reason": reason, "row": row_preview})
                continue
            entry = self._build_entry(values)
            entry["id"] = max(
                [int(row.get("id", 0)) for row in rows] + [item["id"] for item in entries],
                default=0,
            ) + 1
            rows.append(entry)
            entries.append(entry)
            seen.add(str(values.get(_DEDUP_KEY) or "").strip())

        if entries:
            _imported_files.add(fingerprint)
        message = self._build_import_message(total, len(entries), len(failures))
        return {
            "ok": bool(entries),
            "duplicate": False,
            "filename": filename,
            "total": total,
            "imported": len(entries),
            "failures": failures,
            "entries": [{field: item.get(field) for field in DETAIL_FIELDS} for item in entries],
            "message": message,
        }

    def _filter_rows(
        self,
        *,
        keyword: str | None,
        status: str | None,
        unit: str | None,
        voltage: str | None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("发电机编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if unit:
            rows = [row for row in rows if unit in str(row.get("所属机组", ""))]
        if voltage:
            rows = [row for row in rows if voltage in str(row.get("额定电压", ""))]
        return rows

    def _build_entry(self, values: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {field: values.get(field) for field in DETAIL_FIELDS}
        for field in NUMERIC_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = self._to_number(values[field])
        current_status = entry.get("发电机状态")
        status = current_status if current_status in STATUS_ORDER else STATUS_ORDER[0]
        entry["发电机状态"] = current_status or status
        entry["status"] = status
        entry["pending"] = status != STATUS_ORDER[-1]
        entry["abnormal"] = status == "绝缘偏低"
        return entry

    def _validate_row(self, values: dict[str, Any], taken_keys: set[str]) -> str:
        missing = [
            field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return f"缺少必填字段：{'、'.join(missing)}"
        key = str(values.get(_DEDUP_KEY) or "").strip()
        if key in taken_keys:
            return f"发电机编号「{key}」与库中或文件内的其它记录重复"
        for field in NUMERIC_FIELDS:
            raw = str(values.get(field) or "").strip()
            if raw and not _NUMBER_RE.match(raw):
                return f"「{field}」必须是纯数字（不带单位），当前值为「{raw}」"
        date_value = str(values.get("上次检测日") or "").strip()
        if date_value and not _DATE_RE.match(date_value):
            return f"「上次检测日」应为 YYYY-MM-DD 格式，当前值为「{date_value}」"
        return ""

    @staticmethod
    def _detect_delimiter(text: str) -> str:
        first_line = text.splitlines()[0]
        if "\t" in first_line:
            return "\t"
        if ";" in first_line:
            return ";"
        return ","

    @staticmethod
    def _to_number(raw: Any) -> int | float:
        number = float(str(raw).strip())
        return int(number) if number.is_integer() else number

    @staticmethod
    def _build_import_message(total: int, imported: int, failed: int) -> str:
        if imported and not failed:
            return f"共 {total} 行，成功导入 {imported} 行"
        if imported and failed:
            return f"共 {total} 行，成功导入 {imported} 行，{failed} 行未通过校验已单独列出"
        return f"共 {total} 行，全部未通过校验，未写入任何记录"
