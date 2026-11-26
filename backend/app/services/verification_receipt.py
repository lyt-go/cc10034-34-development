"""预算核查回执模块服务：只读为主，纠正提交由 alert_review 统一处理。"""
from __future__ import annotations

from app.services.base import BaseModuleService


class VerificationReceiptService(BaseModuleService):
    MODULE = "verification_receipt"
    ENTITY = "预算核查回执"
    OPERATION_TERM = "核查"
    LIST_FIELDS = [
        "回执编号", "告警编号", "关联告警编号", "预算编号", "数据集名称",
        "告警上报笔数", "重复上报笔数", "告警金额合计", "认定扣费笔数",
        "认定扣费金额", "匹配流水编号", "排除流水编号", "核实应退金额", "核查结论",
    ]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["待提交纠正", "纠正审核中", "纠正已采纳", "纠正已拒绝"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []
