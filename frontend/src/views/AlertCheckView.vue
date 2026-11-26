<template>
  <section class="page alert-check-page" data-testid="alert-check-page">
    <header class="page-head">
      <div>
        <h2>告警核查 · 预算扣费对照</h2>
        <p class="page-desc">
          服务端将当前预算告警与实际预算流水对照，形成<strong>预算核查回执</strong>；
          核查员据此提交<strong>纠正请求</strong>，由隐私预算页接受或拒绝。重复告警只认定一笔扣费，
          异数据集流水不得核销，同一原因退款只支付一次。
        </p>
      </div>
      <div class="page-actions wrap">
        <RouterLink class="btn" to="/anomaly_detect" data-testid="back-anomaly">返回异常检测</RouterLink>
        <RouterLink class="btn" to="/privacy_budget" data-testid="goto-budget">前往隐私预算页受理</RouterLink>
        <button
          class="btn primary"
          type="button"
          data-testid="build-scenario"
          :disabled="building"
          @click="buildDefaultScenario(true)"
        >
          {{ building ? '构造中…' : '构造演练：0.30扣费＋重复告警＋0.10迟到退款' }}
        </button>
        <button
          class="btn ghost"
          type="button"
          data-testid="build-scenario-no-refund"
          :disabled="building"
          @click="buildDefaultScenario(false)"
        >
          构造场景（退款稍后送达）
        </button>
      </div>
    </header>

    <div class="rule-banner" data-testid="rule-banner">
      <span>核查铁律：</span>
      <span>① 同一笔费用的重复告警只计一次扣款；</span>
      <span>② 不同数据集的流水不能核销本条告警；</span>
      <span>③ 同一凭证＋同一原因的退款至多支付一次，余额只变动一次。</span>
    </div>

    <p v-if="message" class="action-message" :class="{ error: !messageOk }" role="status" data-testid="review-message">
      {{ message }}
    </p>

    <!-- 1. 当前告警 -->
    <section class="review-card" data-testid="alert-list">
      <div class="card-head">
        <h3>1. 当前预算告警</h3>
        <button class="btn ghost" type="button" data-testid="reload-board" @click="reload">刷新</button>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>告警编号</th><th>数据集</th><th>关联凭证</th><th>告警金额</th>
            <th>重复识别</th><th>状态</th><th>核查动作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="alert in sortedAlerts"
            :key="alert.id"
            :data-testid="`alert-row-${alert.id}`"
            :data-voucher="alert.关联凭证号"
            :data-duplicate="alert.重复标记"
          >
            <td>{{ alert.告警编号 }}</td>
            <td>{{ alert.数据集名称 }}</td>
            <td class="mono">{{ alert.关联凭证号 }}</td>
            <td>{{ alert.告警金额 }}</td>
            <td>
              <span class="badge" :class="isDuplicate(alert) ? 'warn' : 'muted'" data-testid="duplicate-badge">
                {{ duplicateText(alert) }}
              </span>
            </td>
            <td>{{ alert.status }}</td>
            <td class="row-actions">
              <button
                class="link"
                type="button"
                :data-testid="`generate-receipt-${alert.id}`"
                :disabled="acting"
                @click="onGenerateReceipt(alert.id)"
              >生成核查回执</button>
              <button class="link" type="button" :data-testid="`alert-detail-${alert.id}`" @click="openVoucher(alert.关联凭证号, null)">
                详情
              </button>
            </td>
          </tr>
          <tr v-if="!alerts.length"><td colspan="7" class="empty-state">暂无预算告警，可点击右上角构造演练场景</td></tr>
        </tbody>
      </table>
    </section>

    <!-- 2. 核查回执 + 纠正提交 -->
    <section class="review-card" data-testid="receipt-list">
      <div class="card-head"><h3>2. 预算核查回执（服务端对照告警与真实流水生成）</h3></div>
      <div v-for="receipt in sortedReceipts" :key="receipt.id" class="receipt-card" :data-testid="`receipt-card-${receipt.id}`">
        <div class="receipt-head">
          <strong data-testid="receipt-no">{{ receipt.回执编号 }}</strong>
          <span class="badge" :class="receipt.abnormal ? 'warn' : 'ok'">{{ receipt.status }}</span>
          <span class="muted-text">{{ receipt.核查时间 }} · {{ receipt.核查人 }}</span>
        </div>
        <p class="receipt-conclusion" data-testid="receipt-conclusion">{{ receipt.核查结论 }}</p>

        <div class="metric-grid">
          <div class="metric"><span>告警上报</span><strong data-testid="receipt-report-count">{{ receipt.告警上报笔数 }} 笔</strong></div>
          <div class="metric"><span>重复上报</span><strong class="warn-text" data-testid="receipt-duplicate-count">{{ receipt.重复上报笔数 }} 笔</strong></div>
          <div class="metric"><span>告警金额合计(含重复)</span><strong>{{ receipt.告警金额合计 }}</strong></div>
          <div class="metric"><span>去重后认定扣费</span><strong class="ok-text" data-testid="receipt-recognized-amount">{{ receipt.认定扣费金额 }}（{{ receipt.认定扣费笔数 }}笔）</strong></div>
        </div>

        <div class="match-grid">
          <div class="match-box ok">
            <h4>可核销流水（同数据集·按凭证去重）</h4>
            <p data-testid="matched-txns"><span class="mono">{{ receipt.匹配流水编号 || '未匹配到' }}</span></p>
          </div>
          <div class="match-box bad">
            <h4>异数据集流水（禁止用于核销）</h4>
            <p data-testid="excluded-txns"><span class="mono">{{ receipt.排除流水编号 || '无' }}</span></p>
            <p class="muted-text" data-testid="dataset-check">{{ receipt.数据集核对结论 }}</p>
          </div>
        </div>
        <p class="muted-text" data-testid="duplicate-conclusion">{{ receipt.重复核对结论 }}</p>

        <template v-for="linked in correctionsForReceipt(receipt)" :key="linked.id">
        <div class="correction-summary" :data-testid="`receipt-correction-${receipt.id}`">
          <span>纠正请求 <b>{{ linked.纠正编号 }}</b>：</span>
          <span class="badge" :class="badgeClass(linked.state)" data-testid="receipt-correction-status">{{ linked.状态 }}</span>
          <span v-if="linked.冲突状态" class="badge warn" data-testid="receipt-conflict">{{ linked.冲突状态 }}</span>
          <span v-if="linked.支付流水编号">最终支付流水：<b class="mono" data-testid="receipt-payer">{{ linked.支付流水编号 }}</b></span>
          <RouterLink
            class="link"
            :to="budgetLink(linked)"
            :data-testid="`goto-accept-${linked.id}`"
          >去隐私预算页受理/查看 →</RouterLink>
          <button class="link" type="button" :data-testid="`correction-detail-${linked.id}`" @click="openVoucher(receipt.关联凭证号, linked.id)">
            核查详情
          </button>
        </div>
        </template>

        <div v-if="!correctionFor(receipt)" class="correction-form">
          <label>
            <span>核实应退金额</span>
            <input
              :data-testid="`verified-amount-${receipt.id}`"
              v-model="amountDrafts[receipt.id]"
              class="amount-input"
              placeholder="0.10"
              inputmode="decimal"
            />
          </label>
          <label class="reason-label">
            <span>退款原因（与原查询入口一致）</span>
            <input :data-testid="`correction-reason-${receipt.id}`" v-model="reasonDrafts[receipt.id]" />
          </label>
          <button
            class="btn primary"
            type="button"
            :data-testid="`submit-correction-${receipt.id}`"
            :disabled="acting"
            @click="onSubmitCorrection(receipt.id)"
          >提交纠正请求（送隐私预算页）</button>
          <button
            class="btn ghost"
            type="button"
            :data-testid="`simulate-query-refund-${receipt.id}`"
            :disabled="acting"
            @click="onSimulateQueryRefund(receipt)"
          >模拟原查询入口送来同因0.10待定退款</button>
          <RouterLink
            class="btn ghost"
            :to="queryEntryLink(receipt)"
            :data-testid="`query-entry-link-${receipt.id}`"
          >去差分查询页申请退款</RouterLink>
        </div>
      </div>
      <p v-if="!receipts.length" class="empty-state">尚未生成回执，请先在上方告警行点击「生成核查回执」。</p>
    </section>

    <!-- 3. 纠正请求总览 -->
    <section class="review-card" data-testid="correction-list">
      <div class="card-head"><h3>3. 纠正请求处置总览</h3></div>
      <table class="data-table">
        <thead>
          <tr>
            <th>纠正编号</th><th>申请退款</th><th>冲突识别</th><th>进入何种处置</th>
            <th>最终支付流水</th><th>余额实际变动</th><th>状态</th><th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in sortedCorrections"
            :key="c.id"
            :data-testid="`correction-row-${c.id}`"
            :data-state="c.state"
            :data-disposition="c.disposition_code"
          >
            <td class="mono">{{ c.纠正编号 }}</td>
            <td>{{ c.申请退款金额 }}</td>
            <td data-testid="correction-conflict-cell">{{ c.冲突状态 || '无冲突' }}</td>
            <td class="disposition-cell" data-testid="correction-disposition">{{ c.状态 }}<br /><span class="muted-text">{{ c.处置说明 }}</span></td>
            <td class="mono" data-testid="correction-payer">{{ c.支付流水编号 || '—' }}</td>
            <td :class="c.balance_changed ? 'ok-text strong' : 'muted-text'" data-testid="correction-delta">
              {{ c.balance_changed ? c.实际余额变动 : '本次操作0变动' }}
            </td>
            <td><span class="badge" :class="badgeClass(c.state)">{{ c.state === 'accepted' ? '已受理' : c.state === 'rejected' ? '已拒绝' : '待受理' }}</span></td>
            <td class="row-actions">
              <button class="link" type="button" :data-testid="`open-detail-${c.id}`" @click="openVoucher(c.业务凭证号, c.id)">核查详情</button>
              <RouterLink class="link" :to="budgetLink(c)" :data-testid="`budget-detail-link-${c.id}`">预算页详情</RouterLink>
            </td>
          </tr>
          <tr v-if="!corrections.length"><td colspan="8" class="empty-state">还没有纠正请求。</td></tr>
        </tbody>
      </table>
    </section>

    <!-- 4. 预算流水 -->
    <section class="review-card" data-testid="txn-list">
      <div class="card-head"><h3>预算流水（真实扣费 / 退款台账）</h3></div>
      <table class="data-table">
        <thead>
          <tr><th>流水编号</th><th>类型</th><th>金额</th><th>数据集</th><th>凭证</th><th>来源</th><th>原因</th><th>状态</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in txns" :key="t.id" :data-testid="`txn-row-${t.id}`" :data-state="t.state">
            <td class="mono">{{ t.流水编号 }}</td>
            <td>{{ t.流水类型 }}</td>
            <td data-testid="txn-amount">{{ t.金额 }}</td>
            <td>{{ t.数据集名称 }}</td>
            <td class="mono">{{ t.业务凭证号 }}</td>
            <td>{{ t.来源 }}</td>
            <td>{{ t.退款原因 || '—' }}</td>
            <td><span class="badge" :class="txnBadge(t.state)" data-testid="txn-status">{{ t.状态 }}</span></td>
            <td class="muted-text">{{ t.备注 }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 全链路详情弹窗 -->
    <div v-if="detailVisible" class="modal-backdrop" data-testid="check-detail-modal" @click.self="detailVisible = false">
      <div class="modal detail-modal" role="dialog" aria-label="告警核查全链路详情">
        <h3>核查全链路详情 <span v-if="detailVoucher" class="mono muted-text">{{ detailVoucher }}</span></h3>

        <section data-testid="detail-alerts">
          <h4>告警与去重</h4>
          <ul>
            <li v-for="a in detailAlerts" :key="a.id" :data-testid="`detail-alert-${a.id}`">
              {{ a.告警编号 }} ｜ {{ a.告警金额 }} ｜ {{ a.上报时间 }} ｜
              <span class="badge" :class="isDuplicate(a) ? 'warn' : 'muted'">{{ a.重复标记 }}</span>
            </li>
          </ul>
          <p class="ok-text" data-testid="detail-duplicate-rule">{{ detailReceipt?.重复核对结论 || '生成回执后展示去重结论' }}</p>
        </section>

        <section v-if="detailReceipt" data-testid="detail-receipt">
          <h4>预算核查回执 {{ detailReceipt.回执编号 }}</h4>
          <p data-testid="detail-conclusion">{{ detailReceipt.核查结论 }}</p>
          <div class="match-grid">
            <div class="match-box ok"><h4>最终核销扣费流水</h4><p class="mono" data-testid="detail-matched">{{ detailReceipt.匹配流水编号 }}</p></div>
            <div class="match-box bad"><h4>异数据集排除流水</h4><p class="mono" data-testid="detail-excluded">{{ detailReceipt.排除流水编号 || '无' }}</p></div>
          </div>
        </section>

        <section data-testid="detail-conflict-section">
          <h4>退款冲突如何解决</h4>
          <div v-if="!detailCorrections.length" class="muted-text" data-testid="detail-no-correction">纠正请求尚未提交。</div>
          <div v-for="c in detailCorrections" :key="c.id" class="conflict-card" :data-testid="`detail-correction-${c.id}`" :data-state="c.state">
            <p><b class="mono">{{ c.纠正编号 }}</b>
              <span class="badge" :class="badgeClass(c.state)" data-testid="detail-disposition-badge">{{ c.状态 }}</span>
              <span v-if="c.冲突状态" class="badge warn">{{ c.冲突状态 }}</span>
            </p>
            <p data-testid="detail-disposition">{{ c.处置说明 }}</p>
            <p>最终支付流水：<b class="mono" data-testid="detail-payer">{{ c.支付流水编号 || '尚未产生支付' }}</b></p>
            <p data-testid="detail-balance-impact">
              该操作实际改变余额：
              <b :class="c.balance_changed ? 'ok-text' : 'muted-text'">
                {{ c.balance_changed ? `是，已消耗 Epsilon 变动 ${c.实际余额变动}` : '否（本次余额变动 0.00）' }}
              </b>
            </p>
            <RouterLink class="link" :to="budgetLink(c)">在隐私预算页详情中受理/核对 →</RouterLink>
          </div>
        </section>

        <section data-testid="detail-txns">
          <h4>本笔费用相关流水</h4>
          <ul>
            <li v-for="t in detailTxns" :key="t.id" :data-testid="`detail-txn-${t.id}`" :data-state="t.state">
              <span class="mono">{{ t.流水编号 }}</span> ｜ {{ t.流水类型 }} {{ t.金额 }} ｜ {{ t.数据集名称 }} ｜
              <span class="badge" :class="txnBadge(t.state)">{{ t.状态 }}</span>
            </li>
          </ul>
        </section>

        <section data-testid="detail-events">
          <h4>余额变动时间线（哪次操作真正改了余额）</h4>
          <ul class="event-timeline" data-testid="balance-timeline">
            <li v-for="e in detailEvents" :key="e.id" :data-testid="`timeline-event-row-${e.id}`">
              <span class="muted-text">{{ e.发生时间 }}</span>
              <b>{{ e.操作 }}</b>
              <span class="mono">{{ e.流水编号 }}</span>
              <span :class="e.delta_cents < 0 ? 'ok-text strong' : ''" data-testid="event-delta">{{ e.变动Epsilon }}</span>
              <span class="muted-text">变动后已消耗 {{ e.变动后已消耗Epsilon }}</span>
            </li>
            <li v-if="!detailEvents.length" class="muted-text">暂无余额变动：待定退款与纠正提交都不会改余额，只有实际核准支付才会。</li>
          </ul>
        </section>

        <div class="page-actions right">
          <button class="btn primary" type="button" data-testid="detail-close" @click="detailVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  buildScenario,
  fetchBoard,
  generateReceipt,
  sendRefund,
  submitCorrection,
  type Board,
  type Row,
} from '@/api/review'

const route = useRoute()
const board = ref<Board>({ budgets: [], alerts: [], txns: [], receipts: [], corrections: [], events: [] })
const loading = ref(false)
const acting = ref(false)
const building = ref(false)
const message = ref('')
const messageOk = ref(true)

const amountDrafts = reactive<Record<number, string>>({})
const reasonDrafts = reactive<Record<number, string>>({})

const detailVisible = ref(false)
const detailVoucher = ref('')
const detailCorrectionId = ref<number | null>(null)

const alerts = computed(() => board.value.alerts)
const txns = computed(() => board.value.txns)
const receipts = computed(() => board.value.receipts)
const corrections = computed(() => board.value.corrections)

const sortedAlerts = computed(() => [...alerts.value].sort((a, b) => Number(b.id) - Number(a.id)))
const sortedReceipts = computed(() => [...receipts.value].sort((a, b) => Number(b.id) - Number(a.id)))
const sortedCorrections = computed(() => [...corrections.value].sort((a, b) => Number(b.id) - Number(a.id)))

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function reload() {
  loading.value = true
  try {
    board.value = await fetchBoard()
    for (const r of board.value.receipts) {
      if (amountDrafts[r.id] === undefined) amountDrafts[r.id] = r.核实应退金额 || '0.10'
      if (reasonDrafts[r.id] === undefined) reasonDrafts[r.id] = '查询重试误扣费'
    }
  } catch (error) {
    flash(error instanceof Error ? error.message : '看板加载失败', false)
  } finally {
    loading.value = false
  }
}

function isDuplicate(alert: Row): boolean {
  return String(alert.重复标记 || '').includes('重复')
}

function duplicateText(alert: Row): string {
  const same = alerts.value.filter((a) => a.告警指纹 && a.告警指纹 === alert.告警指纹).length
  if (isDuplicate(alert)) return `重复上报（同指纹共${same}张，只计1笔）`
  return same > 1 ? `首次上报（同指纹共${same}张）` : '唯一告警'
}

function badgeClass(state: string): string {
  if (state === 'accepted') return 'ok'
  if (state === 'rejected') return 'bad'
  return 'warn'
}

function txnBadge(state: string): string {
  if (state === 'posted') return 'ok'
  if (state === 'pending') return 'warn'
  if (state === 'blocked' || state === 'rejected') return 'bad'
  return 'muted'
}

function correctionFor(receipt: Row): Row | undefined {
  return corrections.value.find((c) => Number(c.receipt_id) === Number(receipt.id))
}

function correctionsForReceipt(receipt: Row): Row[] {
  const found = correctionFor(receipt)
  return found ? [found] : []
}

function budgetPkFor(receiptOrCorrection: Row): number | string {
  return receiptOrCorrection.privacy_budget_id ?? receiptOrCorrection.budget_id ?? ''
}

function budgetLink(c: Row): string {
  const q = new URLSearchParams()
  const pk = c.privacy_budget_id ?? ''
  if (pk !== '' && pk !== null && pk !== undefined) q.set('budget', String(pk))
  q.set('correction', String(c.id))
  return `/privacy_budget?${q.toString()}`
}

function queryEntryLink(receipt: Row): string {
  const q = new URLSearchParams({
    refundFor: String(receipt.关联凭证号 || ''),
    amount: amountDrafts[receipt.id] || receipt.核实应退金额 || '0.10',
    reason: reasonDrafts[receipt.id] || '查询重试误扣费',
  })
  if (receipt.privacy_budget_id) q.set('budget', String(receipt.privacy_budget_id))
  return `/differential_sql?${q.toString()}`
}

async function onGenerateReceipt(alertId: number) {
  acting.value = true
  try {
    const result = await generateReceipt(alertId, '0.10')
    flash(result.message, result.ok)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '生成回执失败', false)
  } finally {
    acting.value = false
  }
}

async function onSubmitCorrection(receiptId: number) {
  const amount = (amountDrafts[receiptId] || '').trim()
  if (!amount || Number(amount) <= 0) {
    flash('请填写经核实的应退金额（如 0.1）', false)
    return
  }
  acting.value = true
  try {
    const result = await submitCorrection(receiptId, {
      申请退款金额: amount,
      退款原因: (reasonDrafts[receiptId] || '').trim() || '查询重试误扣费',
    })
    flash(result.message, result.ok)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '提交纠正失败', false)
  } finally {
    acting.value = false
  }
}

async function onSimulateQueryRefund(receipt: Row) {
  acting.value = true
  try {
    const result = await sendRefund({
      privacy_budget_id: receipt.privacy_budget_id,
      预算编号: receipt.预算编号,
      数据集名称: receipt.数据集名称,
      业务凭证号: receipt.关联凭证号,
      查询编号: '',
      金额: amountDrafts[receipt.id] || '0.10',
      退款原因: reasonDrafts[receipt.id] || '查询重试误扣费',
      来源: '原查询入口',
    })
    flash(result.message, result.ok)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '退款送达失败', false)
  } finally {
    acting.value = false
  }
}

async function buildDefaultScenario(withRefund: boolean) {
  building.value = true
  try {
    const result = await buildScenario({ with_pending_refund: withRefund })
    flash(withRefund
      ? `已构造场景：预算 ${result.budget_no}，扣费 0.30、${result.alert_ids.length} 张重复告警、异数据集诱饵流水，以及待定退款 ${result.pending_refund_no}`
      : `已构造场景：预算 ${result.budget_no}，扣费 0.30 与重复告警；可在核查过程中再送达退款`, result.ok)
    await reload()
    if (result.voucher) openVoucher(String(result.voucher), null)
  } catch (error) {
    flash(error instanceof Error ? error.message : '场景构造失败', false)
  } finally {
    building.value = false
  }
}

// ————— 详情弹窗的派生数据 —————
function openVoucher(voucher: string, correctionId: number | null) {
  detailVoucher.value = voucher
  detailCorrectionId.value = correctionId
  detailVisible.value = true
}

const detailAlerts = computed(() =>
  alerts.value.filter((a) => a.关联凭证号 === detailVoucher.value || a.告警指纹 === `FP-${detailVoucher.value}`),
)

const detailReceipt = computed<Row | undefined>(() => {
  const mine = receipts.value.filter((r) => r.关联凭证号 === detailVoucher.value)
  if (detailCorrectionId.value) {
    const c = corrections.value.find((x) => x.id === detailCorrectionId.value)
    const byCorrection = mine.find((r) => Number(r.id) === Number(c?.receipt_id))
    if (byCorrection) return byCorrection
  }
  return mine.sort((a, b) => Number(b.id) - Number(a.id))[0]
})

const detailCorrections = computed(() => {
  const list = corrections.value.filter((c) => c.业务凭证号 === detailVoucher.value)
  if (detailCorrectionId.value) {
    return [...list].sort((a) => (Number(a.id) === detailCorrectionId.value ? -1 : 1))
  }
  return list.sort((a, b) => Number(b.id) - Number(a.id))
})

const detailTxns = computed(() => {
  const ids = new Set<number>()
  const r = detailReceipt.value
  if (r) {
    ;[...(r.matched_txn_ids || []), ...(r.excluded_txn_ids || [])].forEach((id: number) => ids.add(Number(id)))
  }
  return txns.value.filter((t) => ids.has(Number(t.id)) || t.业务凭证号 === detailVoucher.value)
})

const detailEvents = computed(() => {
  const pk = detailAlerts.value[0]?.privacy_budget_id ?? detailReceipt.value?.privacy_budget_id
  if (pk === undefined || pk === null) return []
  return board.value.events
    .filter((e) => Number(e.privacy_budget_id) === Number(pk))
    .sort((a, b) => Number(a.id) - Number(b.id))
})

onMounted(async () => {
  await reload()
  const correctionParam = route.query.correction
  const receiptParam = route.query.receipt
  const voucherParam = route.query.voucher
  if (correctionParam) {
    const c = corrections.value.find((x) => String(x.id) === String(correctionParam))
    if (c) openVoucher(c.业务凭证号, c.id)
  } else if (receiptParam) {
    const r = receipts.value.find((x) => String(x.id) === String(receiptParam))
    if (r) openVoucher(r.关联凭证号, null)
  } else if (voucherParam) {
    openVoucher(String(voucherParam), null)
  }
})
</script>

<style scoped>
.alert-check-page { padding-bottom: 40px; }
.page-actions.wrap { flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.rule-banner { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; border-radius: 8px; padding: 8px 12px; font-size: 13px; display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.action-message { background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
.action-message.error { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
.review-card { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-head h3, .review-card h3 { margin: 0 0 10px; font-size: 15px; }
.receipt-card { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; background: #fcfdff; }
.receipt-head { display: flex; align-items: center; gap: 10px; }
.receipt-conclusion { font-size: 13px; margin: 8px 0; }
.muted-text { color: var(--muted); font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.strong { font-weight: 700; }
.ok-text { color: #15803d; }
.warn-text { color: #b45309; }
.bad-text { color: #b42318; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0; }
.metric { background: #f8fafc; border: 1px solid #eef2f7; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 4px; }
.metric span { font-size: 12px; color: var(--muted); }
.match-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.match-box { border-radius: 8px; padding: 8px 10px; font-size: 13px; }
.match-box h4 { margin: 0 0 6px; font-size: 13px; }
.match-box.ok { background: #f0fdf4; border: 1px solid #bbf7d0; }
.match-box.bad { background: #fef2f2; border: 1px solid #fecaca; }
.correction-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px; border-top: 1px dashed var(--border); padding-top: 10px; margin-top: 10px; }
.correction-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.amount-input { width: 120px; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; }
.reason-label { flex: 1; min-width: 220px; }
.reason-label input { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; }
.correction-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; border-top: 1px dashed var(--border); padding-top: 10px; margin-top: 10px; font-size: 13px; }
.disposition-cell { max-width: 360px; font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #e2e8f0; color: #334155; }
.badge.ok { background: #dcfce7; color: #166534; }
.badge.warn { background: #fef3c7; color: #92400e; }
.badge.bad { background: #fee2e2; color: #991b1b; }
.badge.muted { background: #f1f5f9; color: #64748b; }
.detail-modal { width: min(820px, 100%); }
.detail-modal section { margin-bottom: 14px; }
.detail-modal h4 { margin: 0 0 6px; font-size: 14px; }
.detail-modal ul { margin: 0; padding-left: 18px; font-size: 13px; display: flex; flex-direction: column; gap: 4px; }
.conflict-card { border: 1px solid #fde68a; background: #fffbeb; border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; font-size: 13px; }
.event-timeline { list-style: none !important; padding-left: 0 !important; }
.event-timeline li { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; border-left: 3px solid var(--brand); padding: 4px 0 4px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 0 6px 6px 0; }
.page-actions.right { justify-content: flex-end; display: flex; }
</style>
