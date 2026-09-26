"""检测任务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "task"
REQUIRED_FIELDS = ["任务编号", "所属样品", "检测项目"]
STATUS_ORDER = ["待分配", "已分配", "检测中", "已完成", "已复核"]
DEFAULT_STATUS = STATUS_ORDER[0]

# 状态机唯一口径：动作 -> 允许的来源状态 + 目标状态。
# 列表、详情、动作接口都从这一份规则取结论，同一记录在任何入口结论一致。
ACTION_RULES: dict[str, dict[str, Any]] = {
    "分配任务": {"from": ("待分配",), "to": "已分配"},
    "开始检测": {"from": ("已分配",), "to": "检测中"},
    "提交复核": {"from": ("检测中", "已完成"), "to": "已复核"},
}
NEGATIVE_ACTIONS: list[str] = []

# run_action 的结论类别，路由层只负责把它映射成 HTTP 状态码，不做业务判断
OUTCOME_OK = "ok"                # 已执行
OUTCOME_DUPLICATE = "duplicate"  # 重复提交：已在目标状态，幂等忽略
OUTCOME_CONFLICT = "conflict"    # 状态冲突：当前状态不允许该动作，记录未改动
OUTCOME_MISSING = "missing"      # 记录不存在
OUTCOME_INVALID = "invalid"      # 动作为空或不在可执行范围


def normalize_status(value: Any) -> str:
    """空值或历史脏值统一归到状态机起点，旧数据按新规则复核后仍可查看。"""
    text = str(value or "").strip()
    return text if text in STATUS_ORDER else DEFAULT_STATUS


class TaskService:
    def _serialize(self, entry: dict[str, Any]) -> dict[str, Any]:
        """对外输出前统一口径：状态归一、展示字段与 status 同步、给出当前可执行动作。"""
        row = dict(entry)
        status = normalize_status(row.get("status"))
        row["status"] = status
        row["任务状态"] = status
        row["pending"] = status != STATUS_ORDER[-1]
        row["available_actions"] = [
            action for action, rule in ACTION_RULES.items() if status in rule["from"]
        ]
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._serialize(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row["status"] == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        errors: list[str] = []
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            errors.append(f"缺少必填字段：{'、'.join(missing)}")
        code = str(values.get("任务编号") or "").strip()
        if code and any(
            str(row.get("任务编号") or "").strip() == code for row in store.rows(MODULE)
        ):
            errors.append(f"任务编号「{code}」已存在，请勿重复登记")
        if errors:
            return None, errors
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = DEFAULT_STATUS
        entry["任务状态"] = DEFAULT_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._serialize(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, str]:
        """按固定优先级判定：记录存在 -> 动作合法 -> 状态归一 -> 重复提交 -> 状态冲突 -> 执行。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测任务单 {entry_id} 不存在或已归档", OUTCOME_MISSING
        if not action:
            return None, "动作不能为空，请指定要执行的操作", OUTCOME_INVALID
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测任务可执行范围", OUTCOME_INVALID
        rule = ACTION_RULES[action]
        target = rule["to"]
        status = normalize_status(entry.get("status"))
        if status == target:
            return self._serialize(entry), f"检测任务单已处于「{target}」，重复提交已忽略", OUTCOME_DUPLICATE
        if status not in rule["from"]:
            available = "、".join(self._serialize(entry)["available_actions"]) or "无"
            return None, f"当前状态「{status}」不允许执行「{action}」（可执行：{available}），记录未改动", OUTCOME_CONFLICT
        entry["status"] = target
        entry["任务状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._serialize(entry), f"检测任务单已{action}", OUTCOME_OK
