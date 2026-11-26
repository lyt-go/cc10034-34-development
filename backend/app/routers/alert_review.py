"""告警核查编排接口：告警×流水对照、回执、纠正受理、退款冲突裁决。

路由层保持薄：所有状态变更与冲突裁决都在 app.services.alert_review 内完成。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import alert_review as svc

router = APIRouter(prefix="/api/alert-check", tags=["告警核查"])


class JsonBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

    def as_kwargs(self) -> dict[str, Any]:
        # 同时兼容直接平铺字段和 {values: {...}} 两种请求体。
        return self.values or {k: v for k, v in self.model_dump().items() if k != "values"}


def _body_values(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    if isinstance(payload.get("values"), dict):
        merged = dict(payload["values"])
        for key in ("verified_refund", "operator"):
            if key in payload:
                merged.setdefault(key, payload[key])
        return merged
    return payload


@router.get("/board")
def get_board() -> dict[str, Any]:
    """告警核查页聚合数据：预算、告警、流水、回执、纠正、余额事件一次返回。"""
    return svc.board()


@router.get("/budgets/{budget_id}/detail")
def get_budget_detail(budget_id: int) -> dict[str, Any]:
    detail = svc.budget_detail(budget_id)
    if detail is None:
        return {"ok": False, "message": f"隐私预算 {budget_id} 不存在"}
    return {"ok": True, **detail}


@router.post("/scenario")
def build_scenario(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造演练场景：0.30 扣费、重复告警、异数据集诱饵流水、可选 0.10 待定退款。"""
    result = svc.build_scenario(_body_values(payload))
    return {"ok": True, "message": "演练场景已构造", "scenario": result, **result}


@router.post("/alerts/{alert_id}/receipt")
def create_receipt(alert_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = _body_values(payload)
    receipt, message = svc.generate_receipt(
        alert_id,
        verified_refund=body.get("verified_refund") or body.get("核实应退金额"),
        operator=str(body.get("operator") or "值班员"),
    )
    return {"ok": receipt is not None, "message": message, "receipt": receipt}


@router.post("/receipts/{receipt_id}/correction")
def submit_correction(receipt_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = _body_values(payload)
    correction, message = svc.submit_correction(receipt_id, body)
    return {"ok": correction is not None, "message": message, "correction": correction}


@router.post("/corrections/{correction_id}/accept")
def accept_correction(correction_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    operator = "隐私预算值班员"
    if payload and payload.get("operator"):
        operator = str(payload["operator"])
    correction, message = svc.accept_correction(correction_id, operator)
    return {"ok": correction is not None, "message": message, "correction": correction}


@router.post("/corrections/{correction_id}/reject")
def reject_correction(correction_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    operator = "隐私预算值班员"
    if payload and payload.get("operator"):
        operator = str(payload["operator"])
    correction, message = svc.reject_correction(correction_id, operator)
    return {"ok": correction is not None, "message": message, "correction": correction}


@router.post("/refunds")
def send_refund(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """原查询入口送来同一原因的退款（通常先处于待定）。"""
    txn, message, created = svc.request_refund(_body_values(payload))
    return {"ok": txn is not None, "message": message, "txn": txn, "created_pending": created}


@router.post("/txns/{txn_id}/approve")
def approve_txn_refund(txn_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    operator = "隐私预算值班员"
    if payload and payload.get("operator"):
        operator = str(payload["operator"])
    txn, message = svc.approve_refund(txn_id, operator)
    return {"ok": txn is not None, "message": message, "txn": txn}


@router.post("/txns/{txn_id}/reject")
def reject_txn_refund(txn_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    operator = "隐私预算值班员"
    if payload and payload.get("operator"):
        operator = str(payload["operator"])
    txn, message = svc.reject_refund(txn_id, operator)
    return {"ok": txn is not None, "message": message, "txn": txn}
