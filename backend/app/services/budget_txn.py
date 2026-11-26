"""预算流水模块服务：退款核准/驳回委托给 alert_review 的幂等结算。"""
from __future__ import annotations

from typing import Any

from app.services.alert_review import approve_refund, reject_refund, request_refund
from app.services.base import BaseModuleService


class BudgetTxnService(BaseModuleService):
    MODULE = "budget_txn"
    ENTITY = "预算流水"
    OPERATION_TERM = "结算"
    LIST_FIELDS = [
        "流水编号", "预算编号", "数据集名称", "业务凭证号", "查询编号",
        "流水类型", "金额", "退款原因", "来源", "状态", "关联流水", "发生时间",
    ]
    REQUIRED_FIELDS = ["流水编号", "流水类型", "金额"]
    STATUS_ORDER = ["已扣费", "待定退款", "已退款", "已驳回", "重复退款已拦截"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = ["驳回退款"]

    def create_entry(self, values: dict[str, Any]):
        # 通用登记口：若登记的是退款，统一走退款申请的冲突识别。
        if str(values.get("流水类型", "")) == "退款":
            txn, message, created = request_refund(values)
            if txn is None:
                return None, [message]
            return txn, []
        return super().create_entry(values)

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action in ("核准退款", "批准退款", "同意退款", "退款入账"):
            return approve_refund(entry_id)
        if action in ("驳回退款", "拒绝退款"):
            return reject_refund(entry_id)
        return super().run_action(entry_id, action)
