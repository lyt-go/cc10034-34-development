"""预算告警核查领域服务。

核心规则（状态流转只允许在本层发生）：

1. 重复上报的同一笔费用只认定一次：同「告警指纹/业务凭证号」的多张告警
   是重复告警；流水按「业务凭证号」去重，告警金额合计不会被当成多次扣款。
2. 数据集隔离：只有与告警属于同一数据集的流水才能用于核销；同金额但来自
   其他数据集的流水只作为「已排除候选」展示。
3. 同一业务凭证 + 同一退款原因的退款只允许实际支付一次。查询入口送来的
   「待定退款」与核查页提交的「纠正请求」在隐私预算页交汇，无论以何种顺序
   交错提交，结算幂等都保证：至多一笔退款流水入账、余额只变动一次，后来的
   请求会被标记为重复并指明最终支付流水。
"""
from __future__ import annotations

import threading
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.store import store

# 所有结算共用一把进程内锁，避免「核查提交 / 查询退款 / 预算页核准」交错时
# 出现读-判-写竞争导致退两次。
_SETTLE_LOCK = threading.RLock()

DEFAULT_REASON = "查询重试误扣费"


# ————————————————————————————————————————————
# 基础工具
# ————————————————————————————————————————————

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("T", " ")
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def to_cents(value: Any) -> int:
    """把 0.1 / "0.10" / Decimal 安全转成整数分，避免浮点误差。"""
    if value is None or value == "":
        return 0
    return int((Decimal(str(value)) * 100).to_integral_value())


def amount_text(cents: int) -> str:
    return f"{cents / 100:.2f}"


def eps_text(cents: int) -> str:
    """与种子数据风格保持一致：1.0 / 0.3 / 0.2（去掉多余的 0）。"""
    text = f"{cents / 100:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def next_id(table: str) -> int:
    rows = store.rows(table)
    return max((int(row.get("id", 0) or 0) for row in rows), default=0) + 1


def new_no(prefix: str, table: str) -> str:
    return f"{prefix}-{next_id(table):04d}"


def _budget_by_id(budget_id: Any) -> dict[str, Any] | None:
    if budget_id is None or budget_id == "":
        return None
    try:
        return store.find("privacy_budget", int(budget_id))
    except (TypeError, ValueError):
        return None


def _resolve_budget(payload: dict[str, Any]) -> dict[str, Any] | None:
    budget = _budget_by_id(payload.get("privacy_budget_id") or payload.get("budget_id"))
    if budget is not None:
        return budget
    code = str(payload.get("预算编号") or "").strip()
    if code:
        for row in store.rows("privacy_budget"):
            if str(row.get("预算编号")) == code:
                return row
    return None


def refund_key(voucher: Any, reason: Any) -> tuple[str, str]:
    return str(voucher or "").strip(), str(reason or DEFAULT_REASON).strip() or DEFAULT_REASON


# ————————————————————————————————————————————
# 余额与事件
# ————————————————————————————————————————————

def append_event(
    *,
    budget: dict[str, Any] | None,
    operation: str,
    txn_no: str,
    delta_cents: int,
    detail: str,
    correction_no: str = "",
    refund_no: str = "",
) -> dict[str, Any]:
    event = {
        "id": next_id("balance_event"),
        "发生时间": now_text(),
        "privacy_budget_id": int(budget["id"]) if budget is not None else None,
        "预算编号": budget.get("预算编号", "") if budget is not None else "",
        "操作": operation,
        "流水编号": txn_no,
        "变动方向": "退款冲减已消耗" if delta_cents < 0 else ("扣费增加已消耗" if delta_cents > 0 else "无变动"),
        "变动金额": amount_text(abs(delta_cents)) if delta_cents else "0.00",
        "变动Epsilon": ("-" if delta_cents < 0 else "+" if delta_cents > 0 else "") + amount_text(abs(delta_cents)),
        "delta_cents": delta_cents,
        "纠正编号": correction_no,
        "退款流水编号": refund_no or txn_no,
        "说明": detail,
        "变动后已消耗Epsilon": str(budget.get("已消耗Epsilon", "")) if budget is not None else "",
    }
    store.rows("balance_event").append(event)
    return event


def _post_refund_txn(
    txn: dict[str, Any],
    *,
    operation: str,
    operator: str,
    correction_no: str = "",
) -> dict[str, Any]:
    """把一笔待定退款真正入账：这是唯一允许改动预算余额的地方。"""
    with _SETTLE_LOCK:
        if txn.get("state") == "posted":
            return txn
        cents = to_cents(txn.get("金额"))
        budget = _budget_by_id(txn.get("privacy_budget_id"))
        after_text = ""
        if budget is not None:
            current = to_cents(budget.get("已消耗Epsilon"))
            # 已消耗只允许被冲减到 0，不能退成负数。
            new_value = max(0, current - cents)
            budget["已消耗Epsilon"] = eps_text(new_value)
            after_text = budget["已消耗Epsilon"]
        txn["state"] = "posted"
        txn["状态"] = "已退款"
        txn["pending"] = False
        txn["入账时间"] = now_text()
        txn["核准人"] = operator
        event = append_event(
            budget=budget,
            operation=operation,
            txn_no=str(txn.get("流水编号", "")),
            delta_cents=-cents,
            detail=f"{operator}执行「{operation}」，流水 {txn.get('流水编号')} 退款 {amount_text(cents)} 入账，已消耗变为 {after_text or '—'}",
            correction_no=correction_no,
            refund_no=str(txn.get("流水编号", "")),
        )
        txn["balance_event_id"] = event["id"]
        return txn


# ————————————————————————————————————————————
# 流水查询 / 退款申请（原查询入口）
# ————————————————————————————————————————————

def _refunds_for_key(voucher: str, reason: str) -> list[dict[str, Any]]:
    v, r = refund_key(voucher, reason)
    return [
        t for t in store.rows("budget_txn")
        if t.get("流水类型") == "退款"
        and refund_key(t.get("业务凭证号"), t.get("退款原因")) == (v, r)
    ]


def find_posted_refund(voucher: str, reason: str) -> dict[str, Any] | None:
    for txn in _refunds_for_key(voucher, reason):
        if txn.get("state") == "posted":
            return txn
    return None


def find_pending_refunds(voucher: str, reason: str) -> list[dict[str, Any]]:
    return [t for t in _refunds_for_key(voucher, reason) if t.get("state") == "pending"]


def request_refund(values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
    """原查询入口送来同一原因的退款。

    返回 (流水, 说明, 是否真正新建了待定退款)。若同因退款已经支付，则新申请
    直接记为「重复退款已拦截」，绝不产生第二笔可支付流水。
    """
    with _SETTLE_LOCK:
        amount_cents = to_cents(values.get("金额") or values.get("refund_amount"))
        if amount_cents <= 0:
            return None, "退款金额必须大于 0", False
        budget = _resolve_budget(values)
        voucher = str(values.get("业务凭证号") or values.get("voucher") or "").strip()
        query_no = str(values.get("查询编号") or values.get("query_no") or "").strip()
        if not voucher and query_no:
            voucher = f"CHG-{query_no.removeprefix('DIFF-')}"
        reason = str(values.get("退款原因") or values.get("reason") or DEFAULT_REASON).strip()
        dataset = str(values.get("数据集名称") or (budget or {}).get("数据集名称") or "").strip()
        budget_code = str((budget or {}).get("预算编号") or values.get("预算编号") or "").strip()

        v, r = refund_key(voucher, reason)

        posted = find_posted_refund(v, r)
        if posted is not None:
            blocked = _create_refund_txn(
                budget=budget, budget_code=budget_code, dataset=dataset,
                voucher=v, query_no=query_no, reason=r, cents=amount_cents,
                source=str(values.get("来源") or "原查询入口"),
                state="blocked", status="重复退款已拦截",
                txn_no=str(values.get("流水编号") or "") or None,
                remark=f"同一原因退款已由流水 {posted.get('流水编号')} 支付，本申请被拦截，未改变余额",
            )
            return blocked, (
                f"退款冲突：同一凭证/原因的退款已由 {posted.get('流水编号')} 支付，"
                f"本次申请按重复退款拦截，余额不再变动。"
            ), False

        pending = find_pending_refunds(v, r)
        if pending:
            return pending[0], (
                f"同一原因已有待定退款 {pending[0].get('流水编号')}，未重复建单；"
                f"余额尚未变动，可在隐私预算页核准或在纠正受理时合并。"
            ), False

        txn = _create_refund_txn(
            budget=budget, budget_code=budget_code, dataset=dataset,
            voucher=v, query_no=query_no, reason=r, cents=amount_cents,
            source=str(values.get("来源") or "原查询入口"),
            state="pending", status="待定退款",
            txn_no=str(values.get("流水编号") or "") or None,
            remark=values.get("备注") or "查询入口送来的待定退款，等待隐私预算页核准",
        )
        return txn, f"原查询入口退款 {txn['流水编号']} 已送达，状态待定，尚未改变余额。", True


def _create_refund_txn(
    *,
    budget: dict[str, Any] | None,
    budget_code: str,
    dataset: str,
    voucher: str,
    query_no: str,
    reason: str,
    cents: int,
    source: str,
    state: str,
    status: str,
    remark: str,
    txn_no: str | None = None,
) -> dict[str, Any]:
    txn = {
        "id": next_id("budget_txn"),
        "status": status,
        "pending": state == "pending",
        "abnormal": state == "blocked",
        "流水编号": txn_no or new_no("RFD", "budget_txn"),
        "预算编号": budget_code or (budget or {}).get("预算编号", ""),
        "privacy_budget_id": int(budget["id"]) if budget is not None else None,
        "数据集名称": dataset,
        "业务凭证号": voucher,
        "查询编号": query_no,
        "流水类型": "退款",
        "金额": amount_text(cents),
        "退款原因": reason,
        "来源": source,
        "状态": status,
        "state": state,
        "关联流水": voucher,
        "发生时间": now_text(),
        "备注": remark,
    }
    store.rows("budget_txn").append(txn)
    return txn


def approve_refund(txn_id: int, operator: str = "隐私预算值班员") -> tuple[dict[str, Any] | None, str]:
    """隐私预算页直接核准一笔待定退款（交错提交的另一种先后顺序）。"""
    with _SETTLE_LOCK:
        txn = store.find("budget_txn", txn_id)
        if txn is None or txn.get("流水类型") != "退款":
            return None, "退款流水不存在"
        if txn.get("state") == "posted":
            return txn, f"流水 {txn.get('流水编号')} 已退款入账，请勿重复操作"
        if txn.get("state") == "blocked":
            return txn, f"流水 {txn.get('流水编号')} 是重复退款拦截记录，不能支付"
        if txn.get("state") == "rejected":
            return txn, f"流水 {txn.get('流水编号')} 已被驳回，不能核准"
        v, r = refund_key(txn.get("业务凭证号"), txn.get("退款原因"))
        posted = find_posted_refund(v, r)
        if posted is not None:
            txn["state"] = "blocked"
            txn["状态"] = "重复退款已拦截"
            txn["pending"] = False
            txn["备注"] = f"核准前发现同因退款已由 {posted.get('流水编号')} 支付，转为拦截"
            return txn, f"该原因退款已由 {posted.get('流水编号')} 支付，本笔转为重复拦截，未再改变余额"
        _post_refund_txn(txn, operation="隐私预算页核准查询退款", operator=operator)
        # 同步关闭同 key 的其他待定单，避免退两次。
        for other in find_pending_refunds(v, r):
            if other["id"] != txn["id"]:
                other["state"] = "blocked"
                other["状态"] = "重复退款已拦截"
                other["pending"] = False
                other["备注"] = f"同因退款已由 {txn.get('流水编号')} 支付，本单拦截"
        return txn, f"退款流水 {txn.get('流水编号')} 已核准支付，余额发生一次变动"


def reject_refund(txn_id: int, operator: str = "隐私预算值班员") -> tuple[dict[str, Any] | None, str]:
    txn = store.find("budget_txn", txn_id)
    if txn is None or txn.get("流水类型") != "退款":
        return None, "退款流水不存在"
    if txn.get("state") != "pending":
        return txn, f"流水当前状态为「{txn.get('状态')}」，无需驳回"
    txn["state"] = "rejected"
    txn["状态"] = "已驳回"
    txn["pending"] = False
    txn["核准人"] = operator
    txn["备注"] = f"{operator}驳回该待定退款"
    return txn, f"退款流水 {txn.get('流水编号')} 已驳回，余额未变动"


# ————————————————————————————————————————————
# 服务端核查：告警 × 流水 → 预算核查回执
# ————————————————————————————————————————————

def _alert_group(alert: dict[str, Any]) -> list[dict[str, Any]]:
    fingerprint = str(alert.get("告警指纹") or "").strip()
    voucher = str(alert.get("关联凭证号") or "").strip()
    group: list[dict[str, Any]] = []
    for row in store.rows("budget_alert"):
        if fingerprint and str(row.get("告警指纹") or "") == fingerprint:
            group.append(row)
        elif voucher and str(row.get("关联凭证号") or "") == voucher and not fingerprint:
            group.append(row)
    return group or [alert]


def generate_receipt(
    alert_id: int,
    *,
    verified_refund: Any = None,
    operator: str = "值班员",
) -> tuple[dict[str, Any] | None, str]:
    with _SETTLE_LOCK:
        alert = store.find("budget_alert", alert_id)
        if alert is None:
            return None, f"预算告警 {alert_id} 不存在"

        group = _alert_group(alert)
        voucher = str(alert.get("关联凭证号") or "")
        dataset = str(alert.get("数据集名称") or "")
        alert_amount_cents = to_cents(alert.get("告警金额"))

        # 候选扣费流水分两层：
        # 1) 凭证号一致 —— 同一笔费用的硬标识（重复登记按凭证去重）；
        # 2) 金额一致 —— 仅用于暴露「同金额但异数据集」的诱饵/近似流水。
        charge_txns = [t for t in store.rows("budget_txn") if t.get("流水类型") == "扣费"]
        voucher_hits = [
            t for t in charge_txns
            if voucher and str(t.get("业务凭证号") or "") == voucher
        ]

        def same_dataset(t: dict[str, Any]) -> bool:
            return str(t.get("数据集名称") or "") == dataset

        matched_raw = [t for t in voucher_hits if same_dataset(t)]

        # 同一业务凭证号的扣费流水即使被重复登记，也只认定一次。
        dedup: dict[str, dict[str, Any]] = {}
        duplicate_charge_txns: list[dict[str, Any]] = []
        for txn in matched_raw:
            key = str(txn.get("业务凭证号") or txn.get("id"))
            if key in dedup:
                duplicate_charge_txns.append(txn)
            else:
                dedup[key] = txn
        matched = list(dedup.values())
        match_basis = "凭证号＋数据集"

        # 没有凭证级匹配时，才回退到「同数据集＋同金额」，且只取最近一笔，
        # 避免把历史上多笔同额扣费误累加成本条告警的扣款。
        ambiguity_note = ""
        if not matched and alert_amount_cents:
            amount_hits = [
                t for t in charge_txns
                if same_dataset(t) and to_cents(t.get("金额")) == alert_amount_cents
            ]
            amount_hits.sort(key=lambda t: int(t.get("id", 0)), reverse=True)
            if amount_hits:
                matched = amount_hits[:1]
                match_basis = "数据集＋金额（未提供凭证号，就近匹配）"
                if len(amount_hits) > 1:
                    ambiguity_note = f"同数据集存在 {len(amount_hits)} 笔同额扣费，已只取最近一笔，建议补凭证号复核"

        matched_ids = {int(t["id"]) for t in matched}

        alert_time = _parse_time(alert.get("上报时间"))

        def plausible_lookalike(t: dict[str, Any]) -> bool:
            """同金额近似流水还要时间相近，避免把历史同额流水都拉进本次核查。"""
            txn_time = _parse_time(t.get("发生时间"))
            if alert_time is None or txn_time is None:
                return True
            return abs((alert_time - txn_time).total_seconds()) <= 2 * 3600

        # 异数据集候选：同凭证跨数据集（硬排除，不受时间限制）＋
        # 同金额且时间相近的异数据集近似流水。
        excluded = [
            t for t in charge_txns
            if int(t["id"]) not in matched_ids
            and not same_dataset(t)
            and (
                (voucher and str(t.get("业务凭证号") or "") == voucher)
                or (
                    alert_amount_cents
                    and to_cents(t.get("金额")) == alert_amount_cents
                    and plausible_lookalike(t)
                )
            )
        ]
        lookalike = [
            t for t in excluded
            if not (voucher and str(t.get("业务凭证号") or "") == voucher)
        ]
        cross_dataset_same_key = [
            t for t in excluded
            if voucher and str(t.get("业务凭证号") or "") == voucher
        ]
        matched_charge = matched[0] if matched else None
        recognized_cents = sum(to_cents(t.get("金额")) for t in matched)
        reported_cents = sum(to_cents(a.get("告警金额")) for a in group)

        pending = find_pending_refunds(voucher, str(alert.get("告警原因") or DEFAULT_REASON))
        posted = find_posted_refund(voucher, str(alert.get("告警原因") or DEFAULT_REASON))

        receipt = {
            "id": next_id("verification_receipt"),
            "status": "待提交纠正",
            "pending": True,
            "abnormal": False,
            "回执编号": new_no("RCPT", "verification_receipt"),
            "alert_id": int(alert["id"]),
            "告警编号": alert.get("告警编号"),
            "关联告警编号": "、".join(str(a.get("告警编号")) for a in group),
            "重复告警编号": "、".join(
                str(a.get("告警编号")) for a in group if a.get("重复标记") == "重复上报"
            ) or ("、".join(str(a.get("告警编号")) for a in group[1:]) if len(group) > 1 else ""),
            "预算编号": alert.get("预算编号"),
            "privacy_budget_id": alert.get("privacy_budget_id"),
            "数据集名称": dataset,
            "关联凭证号": voucher,
            "告警上报笔数": len(group),
            "重复上报笔数": max(0, len(group) - 1),
            "告警金额合计": amount_text(reported_cents),
            "认定扣费笔数": len(matched),
            "认定扣费金额": amount_text(recognized_cents),
            "重复扣费流水笔数": len(duplicate_charge_txns),
            "匹配流水编号": "、".join(str(t.get("流水编号")) for t in matched),
            "matched_txn_ids": [t["id"] for t in matched],
            "候选流水编号": "、".join(str(t.get("流水编号")) for t in voucher_hits),
            "排除流水编号": "、".join(str(t.get("流水编号")) for t in excluded),
            "excluded_txn_ids": [t["id"] for t in excluded],
            "lookalike_txn_ids": [t["id"] for t in lookalike],
            "cross_dataset_same_key_ids": [t["id"] for t in cross_dataset_same_key],
            "数据集核对结论": (
                f"仅同数据集「{dataset}」流水可核销；"
                + (f"流水 {'、'.join(str(t.get('流水编号')) for t in excluded)} 数据集不一致，已排除，不得用于核销"
                   if excluded else "未发现跨数据集候选流水")
            ),
            "重复核对结论": (
                f"{len(group)} 张告警指向同一笔费用，去重后认定 {len(matched)} 笔扣费 / "
                f"{amount_text(recognized_cents)}，重复上报不得计为两次扣款"
            ),
            "核实应退金额": amount_text(to_cents(verified_refund)) if verified_refund not in (None, "") else "",
            "匹配依据": match_basis,
            "ambiguity_note": ambiguity_note,
            "existing_pending_refund_no": pending[0]["流水编号"] if pending else "",
            "existing_posted_refund_no": posted["流水编号"] if posted else "",
            "核查人": operator,
            "核查时间": now_text(),
            "state": "open",
        }
        if not matched:
            receipt["核查结论"] = "未找到同数据集的匹配扣费流水，暂不能核销，需人工继续核查"
            receipt["abnormal"] = True
        else:
            receipt["核查结论"] = (
                f"告警属实但存在重复上报：{len(group)} 张告警只对应 1 笔 "
                f"{amount_text(recognized_cents)} 扣费（{matched_charge.get('流水编号')}，依据{match_basis}）"
                + (f"；另有 {len(excluded)} 笔异数据集同额/同凭证流水已排除" if excluded else "")
                + (f"；{ambiguity_note}" if ambiguity_note else "")
            )
        store.rows("verification_receipt").append(receipt)

        # 告警与回执互链、状态推进。
        for row in group:
            row["status"] = "已核查"
            row["状态"] = "已核查"
            row["pending"] = False
            row["回执编号"] = receipt["回执编号"]
        alert["last_receipt_id"] = receipt["id"]

        return receipt, f"预算核查回执 {receipt['回执编号']} 已生成：{receipt['核查结论']}"


# ————————————————————————————————————————————
# 纠正请求：核查页提交 → 隐私预算页接受/拒绝
# ————————————————————————————————————————————

def submit_correction(
    receipt_id: int,
    values: dict[str, Any],
    *,
    operator: str = "值班员",
) -> tuple[dict[str, Any] | None, str]:
    with _SETTLE_LOCK:
        receipt = store.find("verification_receipt", receipt_id)
        if receipt is None:
            return None, f"核查回执 {receipt_id} 不存在"
        if receipt.get("state") in ("accepted", "rejected"):
            return None, f"回执 {receipt.get('回执编号')} 的纠正请求已结案，不能重复提交"

        amount_cents = to_cents(values.get("申请退款金额") or values.get("amount") or receipt.get("核实应退金额"))
        if amount_cents <= 0:
            return None, "请填写经核实的、大于 0 的应退金额"
        recognized_cents = to_cents(receipt.get("认定扣费金额"))
        if recognized_cents and amount_cents > recognized_cents:
            return None, f"应退金额 {amount_text(amount_cents)} 不能超过认定扣费 {amount_text(recognized_cents)}"

        reason = str(values.get("退款原因") or values.get("reason") or DEFAULT_REASON).strip()
        v, r = refund_key(receipt.get("关联凭证号"), reason)
        pending = find_pending_refunds(v, r)
        posted = find_posted_refund(v, r)

        correction = {
            "id": next_id("correction_request"),
            "status": "待受理",
            "状态": "待受理",
            "pending": True,
            "abnormal": bool(pending or posted),
            "纠正编号": new_no("COR", "correction_request"),
            "receipt_id": int(receipt["id"]),
            "回执编号": receipt.get("回执编号"),
            "alert_id": receipt.get("alert_id"),
            "告警编号": receipt.get("告警编号"),
            "预算编号": receipt.get("预算编号"),
            "privacy_budget_id": receipt.get("privacy_budget_id"),
            "数据集名称": receipt.get("数据集名称"),
            "业务凭证号": v,
            "退款原因": r,
            "申请退款金额": amount_text(amount_cents),
            "amount_cents": amount_cents,
            "提交人": operator,
            "提交时间": now_text(),
            "受理人": "",
            "受理时间": "",
            "state": "pending",
            "disposition_code": "await_budget_accept",
            "冲突状态": "",
            "冲突退款编号": "",
            "支付流水编号": "",
            "实际余额变动": "0.00",
            "balance_changed": False,
            "处置说明": "纠正请求已送达隐私预算页，等待接受或拒绝；提交动作本身不动余额。",
        }

        if posted is not None:
            correction["冲突状态"] = "同因退款已支付"
            correction["冲突退款编号"] = posted.get("流水编号", "")
            correction["支付流水编号"] = posted.get("流水编号", "")
            correction["disposition_code"] = "will_mark_already_paid"
            correction["处置说明"] = (
                f"提交时发现同一原因退款已由流水 {posted.get('流水编号')} 支付并改变余额；"
                f"隐私预算页接受纠正后只会补登结论，不会再次退款。"
            )
        elif pending:
            correction["冲突状态"] = "发现原查询入口的待定退款"
            correction["冲突退款编号"] = pending[0].get("流水编号", "")
            correction["disposition_code"] = "will_merge_pending"
            correction["处置说明"] = (
                f"提交时发现原查询入口已送来同一原因的待定退款 {pending[0].get('流水编号')}；"
                f"隐私预算页接受纠正时将直接核准该流水支付，纠正单不另建退款，避免退两次。"
            )

        store.rows("correction_request").append(correction)
        receipt["state"] = "correction_submitted"
        receipt["status"] = "纠正审核中"
        receipt["pending"] = True
        receipt["纠正编号"] = correction["纠正编号"]
        receipt["核实应退金额"] = amount_text(amount_cents)
        return correction, f"纠正请求 {correction['纠正编号']} 已提交至隐私预算页" + (
            f"，并检测到退款冲突：{correction['冲突状态']}" if correction["冲突状态"] else ""
        )


def accept_correction(correction_id: int, operator: str = "隐私预算值班员") -> tuple[dict[str, Any] | None, str]:
    """隐私预算页「接受」纠正：在这里裁决退款冲突并保证只支付一次。"""
    with _SETTLE_LOCK:
        correction = store.find("correction_request", correction_id)
        if correction is None:
            return None, f"纠正请求 {correction_id} 不存在"
        if correction.get("state") == "accepted":
            return correction, f"纠正请求 {correction.get('纠正编号')} 已受理，请勿重复操作"
        if correction.get("state") == "rejected":
            return correction, f"纠正请求 {correction.get('纠正编号')} 已被拒绝，不能再接受"

        v, r = refund_key(correction.get("业务凭证号"), correction.get("退款原因"))
        amount_cents = to_cents(correction.get("申请退款金额"))

        # 顺序一：查询入口退款已被核准 / 已先行支付 —— 纠正只确认结论，不动余额。
        posted = find_posted_refund(v, r)
        if posted is not None:
            correction.update({
                "state": "accepted",
                "status": "已采纳-退款已由其他操作支付",
                "状态": "已采纳-退款已由其他操作支付",
                "pending": False,
                "受理人": operator,
                "受理时间": now_text(),
                "disposition_code": "already_paid",
                "支付流水编号": posted.get("流水编号", ""),
                "实际余额变动": "0.00",
                "balance_changed": False,
                "处置说明": (
                    f"接受纠正，但同一原因的退款此前已由操作「隐私预算页核准查询退款」"
                    f"经流水 {posted.get('流水编号')} 支付，余额当时已变动；"
                    f"本次受理不再次出款、不再次改变余额。"
                ),
            })
            _close_receipt(correction, accepted=True)
            return correction, "退款此前已支付，本次受理仅确认纠正结论，余额未再变动"

        # 顺序二：存在查询入口送来的待定退款 —— 合并，由那笔流水最终支付。
        pending = find_pending_refunds(v, r)
        if pending:
            payer = pending[0]
            _post_refund_txn(
                payer,
                operation="接受纠正并核准查询入口退款",
                operator=operator,
                correction_no=str(correction.get("纠正编号", "")),
            )
            for extra in pending[1:]:
                extra["state"] = "blocked"
                extra["状态"] = "重复退款已拦截"
                extra["pending"] = False
                extra["备注"] = f"同因退款统一由 {payer.get('流水编号')} 支付，本单拦截"
            correction.update({
                "state": "accepted",
                "status": "已采纳-合并待定退款并支付",
                "状态": "已采纳-合并待定退款并支付",
                "pending": False,
                "受理人": operator,
                "受理时间": now_text(),
                "disposition_code": "merged_existing_pending",
                "冲突状态": "已合并：核准原查询入口待定退款",
                "冲突退款编号": payer.get("流水编号", ""),
                "支付流水编号": payer.get("流水编号", ""),
                "实际余额变动": f"-{amount_text(to_cents(payer.get('金额')))}",
                "balance_changed": True,
                "处置说明": (
                    f"纠正请求进入「已采纳并退款」处置：不新建第二笔退款，直接核准原查询入口"
                    f"同一原因的待定退款 {payer.get('流水编号')}，由该流水最终支付 "
                    f"{payer.get('金额')}，余额仅变动这一次。"
                ),
            })
            _close_receipt(correction, accepted=True)
            return correction, f"纠正已采纳，待定退款 {payer.get('流水编号')} 已支付，余额发生一次变动"

        # 顺序三：没有任何同因退款 —— 由纠正单生成唯一一笔退款流水并支付。
        budget = _budget_by_id(correction.get("privacy_budget_id"))
        payer = _create_refund_txn(
            budget=budget,
            budget_code=str(correction.get("预算编号") or ""),
            dataset=str(correction.get("数据集名称") or ""),
            voucher=v,
            query_no="",
            reason=r,
            cents=amount_cents,
            source="核查纠正",
            state="pending",
            status="待定退款",
            remark=f"由纠正请求 {correction.get('纠正编号')} 生成",
        )
        _post_refund_txn(
            payer,
            operation="接受纠正并支付退款",
            operator=operator,
            correction_no=str(correction.get("纠正编号", "")),
        )
        correction.update({
            "state": "accepted",
            "status": "已采纳-已发起退款",
            "状态": "已采纳-已发起退款",
            "pending": False,
            "受理人": operator,
            "受理时间": now_text(),
            "disposition_code": "paid_by_correction_refund",
            "支付流水编号": payer.get("流水编号", ""),
            "实际余额变动": f"-{amount_text(amount_cents)}",
            "balance_changed": True,
            "处置说明": (
                f"纠正请求进入「已采纳并退款」处置：生成退款流水 {payer.get('流水编号')} "
                f"并立即支付 {amount_text(amount_cents)}，余额变动一次；"
                f"此后若原查询入口再送同因退款，将按重复退款拦截。"
            ),
        })
        _close_receipt(correction, accepted=True)
        return correction, f"纠正已采纳，退款流水 {payer.get('流水编号')} 已支付"


def reject_correction(correction_id: int, operator: str = "隐私预算值班员") -> tuple[dict[str, Any] | None, str]:
    correction = store.find("correction_request", correction_id)
    if correction is None:
        return None, f"纠正请求 {correction_id} 不存在"
    if correction.get("state") != "pending":
        return correction, f"纠正请求当前为「{correction.get('状态')}」，不能拒绝"
    pending = find_pending_refunds(
        str(correction.get("业务凭证号")), str(correction.get("退款原因"))
    )
    note = (
        f"；原查询入口待定退款 {pending[0].get('流水编号')} 保持待定，可另行核准或驳回"
        if pending else ""
    )
    correction.update({
        "state": "rejected",
        "status": "已拒绝",
        "状态": "已拒绝",
        "pending": False,
        "受理人": operator,
        "受理时间": now_text(),
        "disposition_code": "rejected",
        "实际余额变动": "0.00",
        "balance_changed": False,
        "处置说明": f"隐私预算页拒绝该纠正请求，未生成支付、未改变余额{note}。",
    })
    receipt = store.find("verification_receipt", int(correction.get("receipt_id") or 0))
    if receipt is not None:
        receipt["state"] = "rejected"
        receipt["status"] = "纠正已拒绝"
    return correction, f"纠正请求 {correction.get('纠正编号')} 已拒绝，余额未变动{note}"


def _close_receipt(correction: dict[str, Any], *, accepted: bool) -> None:
    receipt = store.find("verification_receipt", int(correction.get("receipt_id") or 0))
    if receipt is None:
        return
    receipt["state"] = "accepted" if accepted else "rejected"
    receipt["status"] = "纠正已采纳" if accepted else "纠正已拒绝"
    receipt["pending"] = False


# ————————————————————————————————————————————
# 场景构造：0.30 扣费 + 重复告警 + 可选的 0.10 迟到退款
# ————————————————————————————————————————————

def build_scenario(options: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造一组全新的演练数据，返回全部 id，方便接口级交错测试。"""
    options = options or {}
    with _SETTLE_LOCK:
        charge_cents = to_cents(options.get("charge_amount") or options.get("charge") or "0.3")
        refund_cents = to_cents(options.get("refund_amount") or options.get("refund") or "0.1")
        duplicate_count = int(options.get("duplicate_count", 2) or 2)
        with_pending_refund = options.get("with_pending_refund", True)
        reason = str(options.get("reason") or DEFAULT_REASON)
        stamp = datetime.now().strftime("%H%M%S")
        serial = next_id("privacy_budget")
        suffix = f"{serial:02d}{stamp}"
        # 每次构造使用独立数据集名，避免与历史演练的同额流水相互干扰；
        # 仍保留中文数据集前缀，方便页面与断言识别。
        dataset = str(options.get("dataset") or f"营销触达效果数据集·演练{suffix}")
        decoy_dataset = str(options.get("other_dataset") or f"门店客流数据集·演练{suffix}")
        budget_code = f"PRIV-E2E-{suffix}"
        voucher = f"CHG-E2E-{suffix}"
        query_no = f"DIFF-E2E-{suffix}"

        budget = {
            "id": next_id("privacy_budget"),
            "status": "预警",
            "pending": True,
            "abnormal": True,
            "预算编号": budget_code,
            "数据集名称": dataset,
            "总预算Epsilon": "1.0",
            "已消耗Epsilon": eps_text(charge_cents),
            "消耗记录": f"{query_no} 查询扣费{amount_text(charge_cents)}",
            "预算周期": "月度",
            "重置时间": "2026-12-01",
            "超额策略": "拒绝新查询",
        }
        store.rows("privacy_budget").append(budget)

        charge = {
            "id": next_id("budget_txn"),
            "status": "已扣费", "pending": False, "abnormal": False,
            "流水编号": new_no("TXN", "budget_txn"),
            "预算编号": budget_code, "privacy_budget_id": budget["id"],
            "数据集名称": dataset, "业务凭证号": voucher, "查询编号": query_no,
            "流水类型": "扣费", "金额": amount_text(charge_cents), "退款原因": "",
            "来源": "差分查询", "状态": "已扣费", "state": "charged",
            "关联流水": "", "发生时间": now_text(), "备注": "演练扣费",
        }
        store.rows("budget_txn").append(charge)

        decoy = {
            "id": next_id("budget_txn"),
            "status": "已扣费", "pending": False, "abnormal": False,
            "流水编号": new_no("TXN", "budget_txn"),
            "预算编号": f"PRIV-OTHER-{serial:02d}", "privacy_budget_id": None,
            "数据集名称": decoy_dataset, "业务凭证号": f"{voucher}-OTHER",
            "查询编号": f"{query_no}-O",
            "流水类型": "扣费", "金额": amount_text(charge_cents), "退款原因": "",
            "来源": "差分查询", "状态": "已扣费", "state": "charged",
            "关联流水": "", "发生时间": now_text(),
            "备注": "同金额异数据集诱饵流水，核查时必须排除",
        }
        store.rows("budget_txn").append(decoy)

        alert_ids: list[int] = []
        first_alert_id: int | None = None
        for index in range(max(1, duplicate_count)):
            alert = {
                "id": next_id("budget_alert"),
                "status": "待核查", "pending": True, "abnormal": True,
                "告警编号": f"BALM-E2E-{serial:02d}{stamp}-{index + 1}",
                "预算编号": budget_code, "privacy_budget_id": budget["id"],
                "数据集名称": dataset, "关联凭证号": voucher,
                "告警指纹": f"FP-{voucher}",
                "告警金额": amount_text(charge_cents), "告警原因": reason,
                "告警级别": "P1-预算异常",
                "上报来源": "异常检测" if index == 0 else "异常检测-重复推送",
                "上报时间": now_text(),
                "重复标记": "首次上报" if index == 0 else "重复上报",
                "回执编号": "",
            }
            store.rows("budget_alert").append(alert)
            alert_ids.append(alert["id"])
            if first_alert_id is None:
                first_alert_id = alert["id"]

        refund = None
        if with_pending_refund:
            refund = _create_refund_txn(
                budget=budget, budget_code=budget_code, dataset=dataset,
                voucher=voucher, query_no=query_no, reason=reason,
                cents=refund_cents, source="原查询入口",
                state="pending", status="待定退款",
                remark="演练：迟到的待定退款，尚未改变余额",
            )

        return {
            "budget_id": budget["id"],
            "budget_no": budget_code,
            "voucher": voucher,
            "query_no": query_no,
            "reason": reason,
            "charge_txn_id": charge["id"],
            "charge_txn_no": charge["流水编号"],
            "decoy_txn_id": decoy["id"],
            "alert_ids": alert_ids,
            "first_alert_id": first_alert_id,
            "pending_refund_id": refund["id"] if refund else None,
            "pending_refund_no": refund["流水编号"] if refund else None,
        }


# ————————————————————————————————————————————
# 聚合查询
# ————————————————————————————————————————————

def budget_summary(budget: dict[str, Any]) -> dict[str, Any]:
    total = to_cents(budget.get("总预算Epsilon"))
    consumed = to_cents(budget.get("已消耗Epsilon"))
    return {
        "id": budget.get("id"),
        "预算编号": budget.get("预算编号"),
        "数据集名称": budget.get("数据集名称"),
        "status": budget.get("status"),
        "total_cents": total,
        "consumed_cents": consumed,
        "remaining_cents": max(0, total - consumed),
        "总预算Epsilon": budget.get("总预算Epsilon"),
        "已消耗Epsilon": budget.get("已消耗Epsilon"),
        "剩余Epsilon": eps_text(max(0, total - consumed)),
    }


def board() -> dict[str, Any]:
    budgets = [budget_summary(b) for b in store.rows("privacy_budget")]
    return {
        "budgets": budgets,
        "alerts": list(store.rows("budget_alert")),
        "txns": list(store.rows("budget_txn")),
        "receipts": list(store.rows("verification_receipt")),
        "corrections": list(store.rows("correction_request")),
        "events": list(store.rows("balance_event")),
    }


def budget_detail(budget_pk: int) -> dict[str, Any] | None:
    budget = store.find("privacy_budget", budget_pk)
    if budget is None:
        return None
    code = str(budget.get("预算编号") or "")
    txns = [
        t for t in store.rows("budget_txn")
        if t.get("privacy_budget_id") == budget_pk or t.get("预算编号") == code
    ]
    corrections = [
        c for c in store.rows("correction_request")
        if c.get("privacy_budget_id") == budget_pk or c.get("预算编号") == code
    ]
    receipts = [
        r for r in store.rows("verification_receipt")
        if r.get("privacy_budget_id") == budget_pk or r.get("预算编号") == code
    ]
    events = [
        e for e in store.rows("balance_event")
        if e.get("privacy_budget_id") == budget_pk or e.get("预算编号") == code
    ]
    return {
        "budget": budget,
        "summary": budget_summary(budget),
        "txns": txns,
        "corrections": corrections,
        "receipts": receipts,
        "events": events,
    }
