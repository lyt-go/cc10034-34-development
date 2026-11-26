<template>
  <div v-if="open" class="modal-backdrop" data-testid="budget-detail-modal" @click.self="emit('close')">
    <div class="modal budget-detail-modal" role="dialog" :data-budget-id="budgetId ?? ''" aria-label="隐私预算详情与纠正受理">
      <div class="modal-title-row">
        <h3>隐私预算详情 · 纠正请求受理</h3>
        <button class="btn ghost" type="button" data-testid="budget-detail-close" @click="emit('close')">关闭</button>
      </div>

      <p v-if="message" class="action-message" :class="{ error: !messageOk }" role="status" data-testid="budget-action-message">
        {{ message }}
      </p>
      <p v-if="loading" class="muted-text">加载中…</p>

      <template v-if="detail">
        <section class="budget-summary" data-testid="budget-summary">
          <div><span class="muted-text">预算编号</span><b data-testid="budget-no">{{ s.预算编号 }}</b></div>
          <div><span class="muted-text">数据集</span><b>{{ s.数据集名称 }}</b></div>
          <div class="metric"><span class="muted-text">总预算 Epsilon</span><strong data-testid="budget-total">{{ s.总预算Epsilon }}</strong></div>
          <div class="metric"><span class="muted-text">已消耗（当前余额口径）</span><strong data-testid="budget-consumed">{{ s.已消耗Epsilon }}</strong></div>
          <div class="metric"><span class="muted-text">剩余 Epsilon</span><strong class="ok-text" data-testid="budget-remaining">{{ s.剩余Epsilon }}</strong></div>
        </section>

        <!-- 纠正请求：接受 / 拒绝 -->
        <section data-testid="budget-corrections">
          <h4>纠正请求（依据预算核查回执）</h4>
          <p v-if="!detail.corrections.length" class="muted-text">该预算下暂无纠正请求。</p>
          <article
            v-for="c in detail.corrections"
            :key="c.id"
            class="conflict-card"
            :class="{ highlight: highlightCorrection === c.id }"
            :data-testid="`budget-correction-${c.id}`"
            :data-state="c.state"
            :data-disposition="c.disposition_code"
          >
            <p class="card-line">
              <b class="mono">{{ c.纠正编号 }}</b>
              <span>申请退款 <b data-testid="budget-correction-amount">{{ c.申请退款金额 }}</b></span>
              <span class="badge" :class="badgeClass(c.state)" data-testid="budget-correction-status">{{ c.状态 }}</span>
              <span v-if="c.冲突状态" class="badge warn" data-testid="budget-conflict-badge">{{ c.冲突状态 }}</span>
            </p>
            <p class="muted-text">回执 {{ c.回执编号 }} ｜ 凭证 <span class="mono">{{ c.业务凭证号 }}</span> ｜ 原因 {{ c.退款原因 }}</p>
            <p data-testid="budget-disposition">{{ c.处置说明 }}</p>
            <p>最终支付流水：<b class="mono" data-testid="budget-payer">{{ c.支付流水编号 || '尚未支付' }}</b></p>
            <p data-testid="budget-balance-impact">
              本操作实际改变余额：
              <b :class="c.balance_changed ? 'ok-text' : 'muted-text'">
                {{ c.balance_changed ? `是，已消耗 Epsilon 变动 ${c.实际余额变动}` : '否（本次余额变动 0.00）' }}
              </b>
            </p>
            <div v-if="c.state === 'pending'" class="btn-row">
              <button
                class="btn primary"
                type="button"
                :data-testid="`accept-correction-${c.id}`"
                :disabled="acting"
                @click="onAccept(c.id)"
              >接受纠正（裁决冲突并退款）</button>
              <button
                class="btn"
                type="button"
                :data-testid="`reject-correction-${c.id}`"
                :disabled="acting"
                @click="onReject(c.id)"
              >拒绝纠正</button>
            </div>
          </article>
        </section>

        <!-- 待定退款：可直接核准/驳回（交错提交的另一入口） -->
        <section data-testid="budget-refunds">
          <h4>退款流水与冲突拦截</h4>
          <table class="data-table">
            <thead><tr><th>流水编号</th><th>来源</th><th>金额</th><th>原因</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="t in refundTxns" :key="t.id" :data-testid="`budget-txn-${t.id}`" :data-state="t.state">
                <td class="mono">{{ t.流水编号 }}</td>
                <td>{{ t.来源 }}</td>
                <td>{{ t.金额 }}</td>
                <td>{{ t.退款原因 }}</td>
                <td><span class="badge" :class="txnBadge(t.state)" data-testid="budget-txn-status">{{ t.状态 }}</span></td>
                <td class="row-actions">
                  <button
                    v-if="t.state === 'pending'"
                    class="link ok-text"
                    type="button"
                    :data-testid="`approve-refund-${t.id}`"
                    :disabled="acting"
                    @click="onApprove(t.id)"
                  >核准退款</button>
                  <button
                    v-if="t.state === 'pending'"
                    class="link bad-text"
                    type="button"
                    :data-testid="`reject-refund-${t.id}`"
                    :disabled="acting"
                    @click="onRejectTxn(t.id)"
                  >驳回</button>
                  <span v-else class="muted-text">—</span>
                </td>
              </tr>
              <tr v-if="!refundTxns.length"><td colspan="6" class="empty-state">暂无退款流水。</td></tr>
            </tbody>
          </table>
        </section>

        <!-- 余额变动时间线 -->
        <section data-testid="budget-events">
          <h4>余额变动明细（哪次操作实际改变余额）</h4>
          <ul class="event-timeline" data-testid="budget-balance-timeline">
            <li v-for="e in detail.events" :key="e.id" :data-testid="`budget-event-row-${e.id}`">
              <span class="muted-text">{{ e.发生时间 }}</span>
              <b data-testid="budget-event-op">{{ e.操作 }}</b>
              <span class="mono">{{ e.流水编号 }}</span>
              <span class="ok-text strong" data-testid="budget-event-delta">{{ e.变动Epsilon }}</span>
              <span class="muted-text">变动后已消耗 {{ e.变动后已消耗Epsilon }}</span>
            </li>
            <li v-if="!detail.events.length" class="muted-text" data-testid="budget-no-event">
              暂无余额变动：待定退款与纠正提交均不动余额，只有核准支付才会改变。
            </li>
          </ul>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  acceptCorrection,
  approveRefundTxn,
  fetchBudgetDetail,
  rejectCorrection,
  rejectRefundTxn,
  type Row,
} from '@/api/review'

const props = defineProps<{ open: boolean; budgetId: number | string | null; highlightCorrection?: number | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const detail = ref<Row | null>(null)
const loading = ref(false)
const acting = ref(false)
const message = ref('')
const messageOk = ref(true)

const s = computed<Row>(() => detail.value?.summary ?? {})
const refundTxns = computed<Row[]>(() =>
  (detail.value?.txns ?? []).filter((t: Row) => t.流水类型 === '退款'),
)
const highlightCorrection = computed(() => props.highlightCorrection ?? null)

function badgeClass(state: string): string {
  if (state === 'accepted' || state === 'posted') return 'ok'
  if (state === 'rejected') return 'bad'
  if (state === 'blocked') return 'bad'
  return 'warn'
}
function txnBadge(state: string): string {
  if (state === 'posted') return 'ok'
  if (state === 'pending') return 'warn'
  if (state === 'blocked' || state === 'rejected') return 'bad'
  return 'muted'
}

async function load() {
  if (props.budgetId === null || props.budgetId === '') return
  loading.value = true
  message.value = ''
  try {
    const data = await fetchBudgetDetail(props.budgetId)
    if (data.ok === false) throw new Error(data.message || '预算详情不存在')
    detail.value = data
  } catch (error) {
    detail.value = null
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '详情加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.budgetId],
  ([isOpen]) => {
    if (isOpen) void load()
  },
  { immediate: true },
)

async function runAction(fn: (id: number) => Promise<Row>, id: number, okPrefix: string) {
  acting.value = true
  message.value = ''
  try {
    const result = await fn(id)
    messageOk.value = result.ok !== false
    message.value = result.message || `${okPrefix}完成`
    await load()
    emit('changed')
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    acting.value = false
  }
}

function onAccept(id: number) {
  return runAction(acceptCorrection, id, '纠正已受理')
}
function onReject(id: number) {
  return runAction(rejectCorrection, id, '纠正已拒绝')
}
function onApprove(id: number) {
  return runAction(approveRefundTxn, id, '退款已核准')
}
function onRejectTxn(id: number) {
  return runAction(rejectRefundTxn, id, '退款已驳回')
}
</script>

<style scoped>
.budget-detail-modal { width: min(880px, 100%); }
.modal-title-row { display: flex; align-items: center; justify-content: space-between; }
.action-message { background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
.action-message.error { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
.budget-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; background: #f8fafc; border: 1px solid #eef2f7; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.budget-summary > div { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.metric strong { font-size: 18px; }
.muted-text { color: var(--muted); font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.strong { font-weight: 700; }
.ok-text { color: #15803d; }
.bad-text { color: #b42318; }
.btn-row { display: flex; gap: 8px; margin-top: 6px; }
.card-line { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.conflict-card { border: 1px solid #fde68a; background: #fffbeb; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; font-size: 13px; }
.conflict-card.highlight { box-shadow: 0 0 0 3px rgb(37 99 235 / 25%); border-color: var(--brand); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #e2e8f0; color: #334155; }
.badge.ok { background: #dcfce7; color: #166534; }
.badge.warn { background: #fef3c7; color: #92400e; }
.badge.bad { background: #fee2e2; color: #991b1b; }
.event-timeline { list-style: none; padding-left: 0; }
.event-timeline li { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; border-left: 3px solid var(--brand); padding: 4px 0 4px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 0 6px 6px 0; font-size: 13px; }
h4 { margin: 12px 0 6px; font-size: 14px; }
</style>
