<template>
  <section class="page" data-module="generator">
    <header class="page-head">
      <div>
        <h2>发电机管理</h2>
        <p class="page-desc">维护发电机，围绕发电机编号、所属机组、额定电压、绝缘电阻做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记发电机</button>
        <button class="btn" type="button" @click="exportRows">导出发电机清单</button>
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '导入中…' : '导入历史检测记录' }}
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv,text/plain"
          class="hidden-file"
          @change="handleImportFile"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel">
      <div class="import-head">
        <strong>导入结果：{{ importResult.message }}</strong>
        <button class="link" type="button" @click="importResult = null">关闭</button>
      </div>
      <p v-if="importResult.total" class="import-summary">
        共解析 {{ importResult.total }} 行，成功 {{ importResult.imported }} 行，失败 {{ importResult.failed }} 行
      </p>
      <table v-if="importResult.failures.length" class="data-table import-failures">
        <thead>
          <tr>
            <th>文件行号</th>
            <th>发电机编号</th>
            <th>未通过原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="failure in importResult.failures" :key="failure.line">
            <td>第 {{ failure.line }} 行</td>
            <td>{{ failure.发电机编号 ?? '—' }}</td>
            <td class="error-text">{{ failure.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无发电机数据，可先登记发电机</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条发电机记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface ImportFailure {
  line: number
  发电机编号: string | null
  reason: string
}

interface ImportResultPayload {
  ok: boolean
  duplicated: boolean
  total: number
  imported: number
  failed: number
  message: string
  failures: ImportFailure[]
}

const ENDPOINT = '/api/generator'
const columns = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
const actions = ["提交检测", "判定绝缘异常", "更换发电机"]
const statuses = ["待检测", "检测合格", "绝缘偏低", "已更换"]
const stats = [{"label": "待检测发电机", "value": 0}, {"label": "绝缘偏低台数", "value": 0}, {"label": "本月检测数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResultPayload | null>(null)

// 列表与导出共用当前查询条件：前端按发电机编号检索，对应后端的 keyword 参数。
function currentQuery() {
  const params = new URLSearchParams()
  const keyword = filters.value['发电机编号']?.trim()
  if (keyword) {
    params.set('keyword', keyword)
  }
  return params
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  // 导出当前条件下的全部记录，与列表页筛选保持一致。
  const query = currentQuery().toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function triggerImport() {
  importResult.value = null
  fileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  importing.value = true
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    if (!response.ok) {
      throw new Error('历史检测记录导入失败，请稍后重试')
    }
    importResult.value = (await response.json()) as ImportResultPayload
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '历史检测记录导入失败'
  } finally {
    importing.value = false
  }
}

function openCreate() {
  errorMessage.value = '发电机登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('发电机动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = currentQuery().toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('发电机列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电机列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.hidden-file {
  display: none;
}
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.import-summary {
  margin: 6px 0;
  font-size: 12px;
  color: var(--muted);
}
.import-failures {
  margin-top: 8px;
}
</style>
