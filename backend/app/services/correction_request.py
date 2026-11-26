"""纠正请求模块服务：接受/拒绝委托给 alert_review 的冲突裁决与幂等结算。"""
from __future__ import annotations

from typing import Any

from app.services.alert_review import accept_correction, reject_correction
from app.services.base import BaseModuleService


class CorrectionRequestService(BaseModuleService):
    MODULE = "correction_request"
    ENTITY = "纠正请求"
    OPERATION_TERM = "受理"
    LIST_FIELDS = [
        "纠正编号", "回执编号", "告警编号", "预算编号", "数据集名称",
        "业务凭证号", "退款原因", "申请退款金额", "状态", "冲突状态",
        "冲突退款编号", "支付流水编号", "实际余额变动", "处置说明",
        "提交人", "提交时间", "受理人", "受理时间",
    ]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["待受理", "已采纳-合并待定退款并支付", "已采纳-已发起退款",
                    "已采纳-退款已由其他操作支付", "已拒绝"]
    # 通用动作口：中文动作名直接对应隐私预算页的接受/拒绝。
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = ["拒绝", "拒绝纠正"]

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action in ("接受", "接受纠正", "采纳", "采纳纠正", "接受纠正请求"):
            return accept_correction(entry_id)
        if action in ("拒绝", "拒绝纠正", "驳回纠正"):
            return reject_correction(entry_id)
        return super().run_action(entry_id, action)
