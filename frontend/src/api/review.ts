/** 告警核查域接口：核查回执、纠正请求、退款冲突裁决、余额变动事件。 */
import { request } from './client'

export type Row = Record<string, any>

export type Board = {
  budgets: Row[]
  alerts: Row[]
  txns: Row[]
  receipts: Row[]
  corrections: Row[]
  events: Row[]
}

async function postJson<T = Row>(path: string, body: unknown = {}): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.message || `接口返回 ${response.status}`)
  }
  return data as T
}

export async function fetchBoard(): Promise<Board> {
  const response = await request('/api/alert-check/board')
  if (!response.ok) throw new Error('告警核查看板读取失败')
  return (await response.json()) as Board
}

export async function fetchBudgetDetail(id: number | string): Promise<Row> {
  const response = await request(`/api/alert-check/budgets/${id}/detail`)
  if (!response.ok) throw new Error('预算详情读取失败')
  return (await response.json()) as Row
}

export function buildScenario(payload: Row = {}) {
  return postJson('/api/alert-check/scenario', payload)
}

export function generateReceipt(alertId: number, verifiedRefund?: string) {
  return postJson(`/api/alert-check/alerts/${alertId}/receipt`, {
    verified_refund: verifiedRefund || undefined,
  })
}

export function submitCorrection(receiptId: number, payload: Row) {
  return postJson(`/api/alert-check/receipts/${receiptId}/correction`, payload)
}

export function acceptCorrection(id: number) {
  return postJson(`/api/alert-check/corrections/${id}/accept`)
}

export function rejectCorrection(id: number) {
  return postJson(`/api/alert-check/corrections/${id}/reject`)
}

export function sendRefund(payload: Row) {
  return postJson('/api/alert-check/refunds', payload)
}

export function approveRefundTxn(id: number) {
  return postJson(`/api/alert-check/txns/${id}/approve`)
}

export function rejectRefundTxn(id: number) {
  return postJson(`/api/alert-check/txns/${id}/reject`)
}
