"""检测任务业务规则：状态流转、字段校验与筛选口径都收在这里。

统一口径（列表与详情共用，不允许各自再判断一次）：
  状态序列：待分配 → 已分配 → 检测中 → 已完成 → 已复核
  待分配：只可「分配任务」
  已分配：只可「开始检测」
  检测中：只可「提交复核」（提交后进入待复核结论的「已完成」，不再直接跳到「已复核」）
  已完成：只可「复核通过」（复核人确认后到达终态「已复核」）
  已复核：终态，无动作
其他状态/空值一律归一化后再判断；重复提交幂等放行；状态版本冲突返回 409 可重试。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "task"
REQUIRED_FIELDS = ["任务编号", "所属样品", "检测项目"]
STATUS_ORDER = ["待分配", "已分配", "检测中", "已完成", "已复核"]
FIRST_STATUS = STATUS_ORDER[0]
TERMINAL_STATUS = STATUS_ORDER[-1]
DISPLAY_STATUS_FIELD = "任务状态"

# 动作 → 目标状态：严格按状态序列前进一步，不允许跳级或回退
ACTION_RULES = {
    "分配任务": "已分配",
    "开始检测": "检测中",
    "提交复核": "已完成",
    "复核通过": "已复核",
}
NEGATIVE_ACTIONS: list[str] = []


class TaskConflict(Exception):
    """状态前置条件不满足：非法流转、重复提交或版本冲突，HTTP 层统一转成 409。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def allowed_actions(status: str | None) -> list[str]:
    """按当前状态给出可执行动作；终态与未知状态返回空列表。"""
    index = STATUS_ORDER.index(status) if status in STATUS_ORDER else -1
    if index < 0 or index >= len(STATUS_ORDER) - 1:
        return []
    target = STATUS_ORDER[index + 1]
    return [action for action, next_status in ACTION_RULES.items() if next_status == target]


class TaskService:
    def __init__(self) -> None:
        # 旧数据按新规则复核（归一化）一次，记录仍保留、仍可查看
        for row in store.rows(MODULE):
            self._normalize(row)

    # ---------- 归一化：空值 / 冲突字段 / 旧数据统一口径 ----------
    def _canonical_status(self, entry: dict[str, Any]) -> tuple[str, bool]:
        """返回（规范状态, 是否发生过修正）。

        优先级：英文 status 合法 > 展示列「任务状态」合法 > 首态「待分配」。
        """
        raw_status = entry.get("status")
        status = str(raw_status).strip() if raw_status is not None else ""
        if status in STATUS_ORDER:
            return status, False
        legacy = entry.get(DISPLAY_STATUS_FIELD)
        legacy_status = str(legacy).strip() if legacy is not None else ""
        if legacy_status in STATUS_ORDER:
            return legacy_status, True
        return FIRST_STATUS, True

    def _normalize(self, entry: dict[str, Any]) -> dict[str, Any]:
        if entry.get("_normalized"):
            return entry
        status, repaired = self._canonical_status(entry)
        entry["status"] = status
        entry[DISPLAY_STATUS_FIELD] = status
        # pending 由规范状态推导，只在终态为 False；旧数据里的相反取值一并纠正
        entry["pending"] = status != TERMINAL_STATUS
        if not isinstance(entry.get("abnormal"), bool):
            entry["abnormal"] = False
        if repaired:
            entry["规则版本"] = "已按新状态规则复核"
        entry["_normalized"] = True
        return entry

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表/详情统一出口：内部字段不出参，允许动作随状态给出。"""
        data = dict(entry)
        status = str(data.get("status") or "")
        data[DISPLAY_STATUS_FIELD] = status if status in STATUS_ORDER else FIRST_STATUS
        data["允许动作"] = allowed_actions(status)
        data.pop("_normalized", None)
        return data

    # ---------- 查询 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._normalize(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._present(row) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._present(self._normalize(entry))

    def stats(self, *, today: str | None = None) -> dict[str, int]:
        rows = [self._normalize(dict(row)) for row in store.rows(MODULE)]
        overdue = 0
        if today:
            overdue = sum(
                1
                for row in rows
                if row["status"] != TERMINAL_STATUS
                and str(row.get("截止日期") or "").strip()
                and str(row.get("截止日期")).strip() < today
            )
        return {
            "待分配任务": sum(1 for row in rows if row["status"] == "待分配"),
            "检测中任务": sum(1 for row in rows if row["status"] == "检测中"),
            "逾期任务": overdue,
        }

    # ---------- 写入 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 允许登记时带上非必填的业务列
        for field in ("检测标准", "指定检测员", "截止日期", "优先级"):
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = FIRST_STATUS
        entry[DISPLAY_STATUS_FIELD] = FIRST_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        entry["version"] = 1
        entry["_normalized"] = True
        rows.append(entry)
        return self._present(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        expected_version: int | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测任务单 {entry_id} 不存在或已归档"
        entry = self._normalize(entry)
        action = (action or "").strip()
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测任务可执行范围"

        current_version = int(entry.get("version") or 0)
        if expected_version is not None and int(expected_version) != current_version:
            # 版本冲突：拒绝本次覆盖，调用方按最新状态刷新后可再次操作
            raise TaskConflict(
                "version_conflict",
                f"任务单状态已被其他操作更新（当前版本 {current_version}），请刷新后重试",
            )

        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current == target:
            # 重复提交：幂等处理，不重复流转，提示后页面刷新即可继续
            return self._present(entry), f"任务单已是「{target}」，无需重复{action}"

        allowed = allowed_actions(current)
        if action not in allowed:
            tip = f"当前为「{current}」，可执行：{'、'.join(allowed)}" if allowed else f"当前为「{current}」，已无可执行动作"
            raise TaskConflict(
                "illegal_transition",
                f"「{current}」状态下不能{action}；{tip}",
            )

        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target != TERMINAL_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS or bool(entry.get("abnormal"))
        entry["version"] = current_version + 1
        return self._present(entry), f"检测任务单已{action}，当前状态：{target}"
