"""告警核查 / 预算核查回执 / 纠正请求退款冲突的领域测试。

覆盖题面三条铁律：
1. 重复上报的同一笔费用只算一次扣款；
2. 不同数据集的流水不能核销本条告警；
3. 同一原因退款无论怎样交错提交，最多支付一次，余额只变动一次。
"""
from __future__ import annotations

from app.services import alert_review as ar
from app.store import store


def _fresh_group(**opts):
    scenario = ar.build_scenario(opts)
    receipt, message = ar.generate_receipt(scenario["first_alert_id"])
    assert receipt is not None, message
    return scenario, receipt


class TestReconciliation:
    def test_seed_has_duplicate_alerts_and_late_pending_refund(self):
        alerts = store.rows("budget_alert")
        assert len(alerts) >= 2
        assert alerts[0]["告警指纹"] == alerts[1]["告警指纹"]
        pending = [t for t in store.rows("budget_txn") if t.get("state") == "pending"]
        assert any(t["金额"] == "0.10" and t["业务凭证号"] == "CHG-2611-030" for t in pending)

    def test_duplicate_alerts_count_single_charge(self):
        s, receipt = _fresh_group()
        assert receipt["告警上报笔数"] == 2
        assert receipt["重复上报笔数"] == 1
        assert receipt["认定扣费笔数"] == 1
        assert receipt["认定扣费金额"] == "0.30"
        # 两张告警各报 0.3，含重复的金额合计是 0.6，但认定扣款不是。
        assert receipt["告警金额合计"] == "0.60"
        assert receipt["matched_txn_ids"] == [s["charge_txn_id"]]

    def test_cross_dataset_txn_excluded(self):
        s, receipt = _fresh_group()
        assert s["decoy_txn_id"] in receipt["excluded_txn_ids"]
        assert s["decoy_txn_id"] not in receipt["matched_txn_ids"]
        decoy = store.find("budget_txn", s["decoy_txn_id"])
        assert decoy is not None
        # 排除流水绝不能出现在认定金额里。
        matched_sum = sum(
            ar.to_cents(t["金额"]) for t in store.rows("budget_txn")
            if t["id"] in receipt["matched_txn_ids"]
        )
        assert matched_sum == 30

    def test_duplicate_charge_rows_same_voucher_dedup(self):
        s = ar.build_scenario({"with_pending_refund": False})
        # 再登记一条同凭证扣费流水（重复入账上报）。
        store.rows("budget_txn").append({
            "id": ar.next_id("budget_txn"), "流水类型": "扣费", "state": "charged",
            "业务凭证号": s["voucher"], "数据集名称": ar.store.find(
                "privacy_budget", s["budget_id"])["数据集名称"],
            "金额": "0.30", "流水编号": "TXN-DUP-" + s["voucher"],
        })
        receipt, _ = ar.generate_receipt(s["first_alert_id"])
        assert receipt["认定扣费笔数"] == 1
        assert receipt["认定扣费金额"] == "0.30"
        assert receipt["重复扣费流水笔数"] == 1

    def test_refund_cannot_exceed_recognized_charge(self):
        _, receipt = _fresh_group(with_pending_refund=False)
        correction, message = ar.submit_correction(
            receipt["id"], {"申请退款金额": "0.9"})
        assert correction is None
        assert "不能超过" in message


class TestRefundConflict:
    def test_pending_refund_merged_on_accept_single_balance_change(self):
        s, receipt = _fresh_group(with_pending_refund=True)
        budget_id = s["budget_id"]
        before = store.find("privacy_budget", budget_id)["已消耗Epsilon"]
        assert before == "0.3"

        correction, _ = ar.submit_correction(receipt["id"], {"申请退款金额": "0.1"})
        assert correction["disposition_code"] == "will_merge_pending"
        # 提交纠正不动余额。
        assert store.find("privacy_budget", budget_id)["已消耗Epsilon"] == "0.3"

        correction, message = ar.accept_correction(correction["id"])
        assert correction["state"] == "accepted"
        assert correction["disposition_code"] == "merged_existing_pending"
        assert correction["支付流水编号"] == s["pending_refund_no"]
        assert correction["balance_changed"] is True
        assert store.find("privacy_budget", budget_id)["已消耗Epsilon"] == "0.2"

        events = [e for e in store.rows("balance_event") if e["privacy_budget_id"] == budget_id]
        assert len(events) == 1
        assert events[0]["delta_cents"] == -10

        # 原查询入口再送同一原因退款 -> 拦截，余额不变。
        txn, message, created = ar.request_refund({
            "privacy_budget_id": budget_id, "业务凭证号": s["voucher"],
            "金额": "0.1", "退款原因": s["reason"], "查询编号": s["query_no"],
        })
        assert created is False
        assert txn["state"] == "blocked"
        assert s["pending_refund_no"] in message
        assert store.find("privacy_budget", budget_id)["已消耗Epsilon"] == "0.2"
        events = [e for e in store.rows("balance_event") if e["privacy_budget_id"] == budget_id]
        assert len(events) == 1

        # 重复受理幂等。
        again, _ = ar.accept_correction(correction["id"])
        assert again["id"] == correction["id"]
        assert len([e for e in store.rows("balance_event")
                    if e["privacy_budget_id"] == budget_id]) == 1

    def test_approve_refund_first_then_correction_marks_already_paid(self):
        s, receipt = _fresh_group(with_pending_refund=True)
        correction, _ = ar.submit_correction(receipt["id"], {"申请退款金额": "0.1"})

        txn, _ = ar.approve_refund(s["pending_refund_id"])
        assert txn["state"] == "posted"
        assert store.find("privacy_budget", s["budget_id"])["已消耗Epsilon"] == "0.2"

        correction, _ = ar.accept_correction(correction["id"])
        assert correction["disposition_code"] == "already_paid"
        assert correction["balance_changed"] is False
        assert correction["支付流水编号"] == s["pending_refund_no"]
        events = [e for e in store.rows("balance_event")
                  if e["privacy_budget_id"] == s["budget_id"]]
        assert len(events) == 1
        assert events[0]["操作"] == "隐私预算页核准查询退款"

    def test_correction_paid_first_then_late_query_refund_blocked(self):
        s, receipt = _fresh_group(with_pending_refund=False)
        correction, _ = ar.submit_correction(receipt["id"], {"申请退款金额": "0.1"})
        correction, _ = ar.accept_correction(correction["id"])
        assert correction["disposition_code"] == "paid_by_correction_refund"
        payer = correction["支付流水编号"]
        assert payer

        txn, message, created = ar.request_refund({
            "privacy_budget_id": s["budget_id"], "业务凭证号": s["voucher"],
            "金额": "0.1", "退款原因": s["reason"],
        })
        assert created is False and txn["state"] == "blocked"
        assert store.find("privacy_budget", s["budget_id"])["已消耗Epsilon"] == "0.2"
        events = [e for e in store.rows("balance_event")
                  if e["privacy_budget_id"] == s["budget_id"]]
        assert len(events) == 1

    def test_reject_correction_keeps_pending_refund_and_balance(self):
        s, receipt = _fresh_group(with_pending_refund=True)
        correction, _ = ar.submit_correction(receipt["id"], {"申请退款金额": "0.1"})
        correction, _ = ar.reject_correction(correction["id"])
        assert correction["state"] == "rejected"
        pending = store.find("budget_txn", s["pending_refund_id"])
        assert pending["state"] == "pending"
        assert store.find("privacy_budget", s["budget_id"])["已消耗Epsilon"] == "0.3"
        assert not [e for e in store.rows("balance_event")
                    if e["privacy_budget_id"] == s["budget_id"]]

    def test_direct_approve_is_idempotent_and_blocks_duplicates(self):
        s = ar.build_scenario({"with_pending_refund": True})
        first, _ = ar.approve_refund(s["pending_refund_id"])
        assert first["state"] == "posted"
        # 同 key 的第二笔待定单（人为构造）核准时应被拦截而不是支付。
        other = ar._create_refund_txn(
            budget=store.find("privacy_budget", s["budget_id"]),
            budget_code=s["budget_no"], dataset="x", voucher=s["voucher"],
            query_no="", reason=s["reason"], cents=10, source="原查询入口",
            state="pending", status="待定退款", remark="第二笔",
        )
        txn, _ = ar.approve_refund(other["id"])
        assert txn["state"] == "blocked"
        assert store.find("privacy_budget", s["budget_id"])["已消耗Epsilon"] == "0.2"
