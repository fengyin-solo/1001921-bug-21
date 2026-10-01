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
        <button class="btn" type="button" @click="triggerImport">批量导入检测记录</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.tsv,.txt,text/csv,text/plain"
          hidden
          @change="handleFileSelected"
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
      <label class="filter-item">
        <span>发电机编号</span>
        <input v-model="filters.keyword" placeholder="按发电机编号检索" />
      </label>
      <label class="filter-item">
        <span>所属机组</span>
        <input v-model="filters.unit" placeholder="按所属机组检索" />
      </label>
      <label class="filter-item">
        <span>额定电压</span>
        <input v-model="filters.voltage" placeholder="按额定电压检索" />
      </label>
      <label class="filter-item">
        <span>发电机状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel" :class="{ failed: importImported === 0 && !importResult.duplicate }">
      <div class="import-summary">
        <strong :class="importImported > 0 || importResult.duplicate ? '' : 'error-text'">{{ importResult.message }}</strong>
        <button class="link" type="button" @click="importResult = null">关闭提示</button>
      </div>
      <table v-if="importResult.failures.length" class="data-table import-failures">
        <thead>
          <tr>
            <th style="width: 80px">行号</th>
            <th style="width: 280px">未通过原因</th>
            <th>该行原始内容</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="failure in importResult.failures" :key="failure.line">
            <td>第 {{ failure.line }} 行</td>
            <td class="error-text">{{ failure.reason }}</td>
            <td>{{ formatFailureRow(failure.row) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="importResult.duplicate" class="page-desc">成功导入过的记录仍保留在清单中，本次没有重复写入。</p>
      <p v-else-if="importImported > 0" class="page-desc">已成功导入 {{ importImported }} 行并保留在清单中，可按上面的原因修正后重新导入失败行。</p>
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
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ImportFailure = { line: number; reason: string; row: Record<string, string> }
type ImportResultPayload = {
  message: string
  duplicate: boolean
  total: number
  imported: number
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
const fileInput = ref<HTMLInputElement | null>(null)
const importResult = ref<ImportResultPayload | null>(null)
const filters = ref({ keyword: '', unit: '', voltage: '', status: '' })

const importImported = computed(() => importResult.value?.imported ?? 0)

function currentQuery() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) {
      params.set(key, value.trim())
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = { keyword: '', unit: '', voltage: '', status: '' }
  void reload()
}

function exportRows() {
  // 导出与列表共用当前过滤条件，后端在该条件下返回全量记录
  const query = currentQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function triggerImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    if (!response.ok) {
      throw new Error('检测记录导入失败，请稍后重试')
    }
    importResult.value = await response.json()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测记录导入失败'
  }
}

function formatFailureRow(row: Record<string, string>) {
  const text = Object.entries(row)
    .filter(([, value]) => value !== '')
    .map(([key, value]) => `${key}: ${value}`)
    .join('，')
  return text || '（空行）'
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
  const query = currentQuery()
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
.import-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.import-panel.failed {
  border-left-color: #b42318;
}
.import-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.import-failures {
  margin-top: 8px;
}
</style>
