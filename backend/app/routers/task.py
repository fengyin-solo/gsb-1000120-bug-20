"""检测任务接口：维护检测任务单，覆盖分配任务、开始检测、提交复核等动作。"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.task import TaskConflict, TaskService

router = APIRouter(prefix="/api/task", tags=["检测任务"])

service = TaskService()

LIST_FIELDS = ["任务编号", "所属样品", "检测项目", "检测标准", "指定检测员", "截止日期", "优先级", "任务状态"]
STATUSES = ["待分配", "已分配", "检测中", "已完成", "已复核"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待分配、已分配、检测中、已完成、已复核"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号与状态过滤检测任务列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def task_stats() -> dict[str, int]:
    """列表统计卡片口径：待分配、检测中、逾期（截止日期早于今天且未到终态）。"""
    return service.stats(today=date.today().isoformat())


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测任务清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "task", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测任务单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测任务单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测任务单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检测任务单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult | JSONResponse:
    """对单条检测任务单执行动作。

    非法流转 / 重复提交后的状态冲突 / 版本冲突统一返回 409，
    响应体仍带 {ok, message}，前端提示后刷新即可再次操作。
    """
    action = str(payload.values.get("action") or "").strip()
    raw_version = payload.values.get("expected_version")
    try:
        expected_version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        expected_version = None
    try:
        entry, message = service.run_action(entry_id, action, expected_version=expected_version)
    except TaskConflict as conflict:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "message": conflict.message, "code": conflict.code},
        )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
