"""预算告警模块服务：告警列表/详情走通用骨架，核查动作委托给 alert_review。"""
from __future__ import annotations

from typing import Any

from app.services.alert_review import generate_receipt
from app.services.base import BaseModuleService


class BudgetAlertService(BaseModuleService):
    MODULE = "budget_alert"
    ENTITY = "预算告警"
    OPERATION_TERM = "核查"
    LIST_FIELDS = [
        "告警编号", "预算编号", "数据集名称", "关联凭证号", "告警指纹", "告警金额",
        "告警原因", "告警级别", "上报来源", "上报时间", "重复标记", "回执编号",
    ]
    REQUIRED_FIELDS = ["告警编号", "数据集名称", "告警金额"]
    STATUS_ORDER = ["待核查", "已核查", "已关闭"]
    ACTION_RULES = {"关闭告警": "已关闭"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action in ("生成核查回执", "核查", "立即核查", "生成回执"):
            receipt, message = generate_receipt(entry_id)
            alert = self.get_entry(entry_id)
            if receipt is not None and alert is not None:
                alert["last_receipt"] = receipt
            return alert, message
        return super().run_action(entry_id, action)
