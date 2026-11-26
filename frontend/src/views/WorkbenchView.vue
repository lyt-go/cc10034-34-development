<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button
          v-if="meta.key === 'anomaly_detect'"
          class="btn primary"
          type="button"
          data-testid="entry-alert-check"
          aria-label="告警核查：预算告警真实扣费对照"
          @click="goAlertCheck"
        >
          告警核查
        </button>
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-testid="`row-${row.id}`"
          :data-status="String(row.status)"
          :class="{ 'clickable-row': meta.key === 'privacy_budget' }"
          @click="meta.key === 'privacy_budget' && openBudgetDetail(Number(row.id))"
        >
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions" @click.stop>
            <button
              v-if="meta.key === 'privacy_budget'"
              class="link"
              type="button"
              :data-testid="`budget-detail-${row.id}`"
              @click="openBudgetDetail(Number(row.id))"
            >
              详情/纠正受理
            </button>
            <button
              v-if="meta.key === 'differential_sql'"
              class="link"
              type="button"
              :data-testid="`request-refund-${row.id}`"
              @click="openRefundModal(row)"
            >
              申请退款
            </button>
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <BudgetDetailModal
      v-if="meta.key === 'privacy_budget'"
      :open="budgetDetailOpen"
      :budget-id="budgetDetailId"
      :highlight-correction="highlightCorrection"
      @close="budgetDetailOpen = false"
      @changed="reload"
    />

    <div v-if="refundModalOpen" class="modal-backdrop" data-testid="refund-modal" @click.self="refundModalOpen = false">
      <form class="modal" data-testid="refund-form" @submit.prevent="submitRefundRequest">
        <h3>原查询入口 · 申请退款（同一原因只退一次）</h3>
        <p class="page-desc">
          退款先以「待定退款」进入预算流水，不立即改变余额；若同凭证同原因已有支付，服务端会按重复退款拦截。
        </p>
        <label class="create-field">
          <span>退款金额</span>
          <input v-model="refundForm.amount" data-testid="refund-amount" inputmode="decimal" placeholder="0.1" required />
        </label>
        <label class="create-field">
          <span>退款原因（须与告警/纠正原因一致）</span>
          <input v-model="refundForm.reason" data-testid="refund-reason" required />
        </label>
        <label class="create-field">
          <span>关联扣费凭证号</span>
          <input v-model="refundForm.voucher" data-testid="refund-voucher" placeholder="CHG-..." />
        </label>
        <label class="create-field">
          <span>关联查询编号</span>
          <input v-model="refundForm.queryNo" data-testid="refund-query-no" />
        </label>
        <label class="create-field">
          <span>入账预算</span>
          <select v-model="refundForm.budgetId" data-testid="refund-budget">
            <option value="">按预算编号/数据集匹配</option>
            <option v-for="b in budgetOptions" :key="b.id" :value="String(b.id)">
              {{ b.预算编号 }} ｜ {{ b.数据集名称 }}
            </option>
          </select>
        </label>
        <p v-if="refundMessage" class="error-text" :class="{ 'ok-text': refundOk }" data-testid="refund-message" role="status">
          {{ refundMessage }}
        </p>
        <div class="page-actions">
          <button class="btn" type="button" @click="refundModalOpen = false">取消</button>
          <button class="btn primary" data-testid="submit-refund" type="submit" :disabled="refundSubmitting">
            {{ refundSubmitting ? '提交中…' : '提交退款申请（待定）' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createEntry,
  downloadEntries,
  listEntries,
  runAction as applyAction,
} from '@/api/backend-service'
import { fetchBoard, sendRefund } from '@/api/review'
import BudgetDetailModal from '@/features/BudgetDetailModal.vue'
import { MODULE_BY_KEY } from '@/data/modules'
import type { EntryRow, ModuleMeta } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const route = useRoute()
const router = useRouter()
// 未在前端登记的 key 也不能白屏：给一份最小元数据，列表错误会显示在页脚。
const meta: ModuleMeta = MODULE_BY_KEY.get(props.moduleKey) ?? {
  key: props.moduleKey,
  name: '业务资源',
  entity: '记录',
  desc: '通用业务资源视图。',
  fields: [],
  statuses: [],
  actions: [],
  actionTargets: {},
  metrics: ['记录总数', '处理中', '已完成'],
}

function goAlertCheck() {
  void router.push('/alert_check')
}
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

// ————— 隐私预算详情 / 纠正受理 —————
const budgetDetailOpen = ref(false)
const budgetDetailId = ref<number | string | null>(null)
const highlightCorrection = ref<number | null>(null)

function openBudgetDetail(id: number, correctionId?: number | null) {
  budgetDetailId.value = id
  highlightCorrection.value = correctionId ?? null
  budgetDetailOpen.value = true
}

// ————— 差分查询（原查询入口）申请退款 —————
const refundModalOpen = ref(false)
const refundSubmitting = ref(false)
const refundMessage = ref('')
const refundOk = ref(true)
const budgetOptions = ref<EntryRow[]>([])
const refundForm = ref({
  amount: '',
  reason: '查询重试误扣费',
  voucher: '',
  queryNo: '',
  budgetId: '',
})

async function ensureBudgetOptions() {
  if (budgetOptions.value.length) return
  try {
    const board = await fetchBoard()
    budgetOptions.value = board.budgets as unknown as EntryRow[]
  } catch {
    budgetOptions.value = []
  }
}

function openRefundModal(row?: EntryRow) {
  refundMessage.value = ''
  refundForm.value = {
    amount: typeof route.query.amount === 'string' ? route.query.amount : '',
    reason: typeof route.query.reason === 'string' ? route.query.reason : '查询重试误扣费',
    voucher: typeof route.query.refundFor === 'string' ? route.query.refundFor : '',
    queryNo: row ? String(row['查询编号'] ?? '') : '',
    budgetId: typeof route.query.budget === 'string' ? route.query.budget : '',
  }
  void ensureBudgetOptions()
  refundModalOpen.value = true
}

async function submitRefundRequest() {
  refundSubmitting.value = true
  refundMessage.value = ''
  try {
    const selectedBudget = budgetOptions.value.find((b) => String(b.id) === refundForm.value.budgetId)
    const result = await sendRefund({
      金额: refundForm.value.amount,
      退款原因: refundForm.value.reason,
      业务凭证号: refundForm.value.voucher,
      查询编号: refundForm.value.queryNo,
      privacy_budget_id: refundForm.value.budgetId || undefined,
      预算编号: selectedBudget?.['预算编号'],
      数据集名称: selectedBudget?.['数据集名称'],
      来源: '原查询入口',
    })
    refundOk.value = result.ok !== false
    refundMessage.value = result.message || '退款申请已送达'
    if (result.ok) {
      // 保留弹窗展示处置结果；同步刷新背景列表与预算选项。
      await reload()
      void ensureBudgetOptions()
    }
  } catch (error) {
    refundOk.value = false
    refundMessage.value = error instanceof Error ? error.message : '退款申请失败'
  } finally {
    refundSubmitting.value = false
  }
}

onMounted(async () => {
  await reload()
  // 支持从告警核查页带参跳转：自动打开预算详情/纠正定位，或查询入口退款弹窗。
  if (meta.key === 'privacy_budget') {
    const budgetParam = route.query.budget ?? route.query.detail
    if (budgetParam) {
      const correctionParam = route.query.correction
      openBudgetDetail(
        Number(budgetParam),
        correctionParam ? Number(correctionParam) : null,
      )
    }
  }
  if (meta.key === 'differential_sql' && route.query.refundFor) {
    openRefundModal()
  }
})
</script>

<style scoped>
.clickable-row { cursor: pointer; }
.clickable-row:hover { background: #f8fafc; }
</style>
