"""发电机接口：维护发电机，覆盖提交检测、判定绝缘异常、更换发电机、清单导出与历史记录导入。"""
from __future__ import annotations

import csv
import io
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, ImportPayload, ImportResult, PageResult
from app.services.generator import FIELDS, GeneratorService

router = APIRouter(prefix="/api/generator", tags=["发电机"])

service = GeneratorService()

STATUSES = ["待检测", "检测合格", "绝缘偏低", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按发电机编号检索"),
    status: str | None = Query(default=None, description="待检测、检测合格、绝缘偏低、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按发电机编号与状态过滤发电机列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="与列表页一致的编号检索条件"),
    status: str | None = Query(default=None, description="与列表页一致的状态过滤条件"),
) -> StreamingResponse:
    """按当前过滤条件导出全量清单（不分页），列与发电机详情页一致、不重复。"""
    items = service.export_entries(keyword=keyword, status=status)
    buffer = io.StringIO()
    buffer.write("﻿")  # Excel 识别 UTF-8，避免中文表头乱码
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(item)
    buffer.seek(0)
    filename = f"发电机清单_{date.today():%Y%m%d}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/import", response_model=ImportResult)
def import_history(payload: ImportPayload) -> ImportResult:
    """批量导入历史检测记录：逐行校验，坏行单独列出并说明原因，成功行保留入库。"""
    result = service.import_history(payload.content)
    return ImportResult(**result)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条发电机明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"发电机 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条发电机，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="发电机已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条发电机执行提交检测、判定绝缘异常、更换发电机；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
