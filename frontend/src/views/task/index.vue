<template>
  <section class="page" data-module="task">
    <header class="page-head">
      <div>
        <h2>检测任务管理</h2>
        <p class="page-desc">维护检测任务单，围绕任务编号、所属样品、检测项目、检测标准做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测任务单</button>
        <button class="btn" type="button" @click="exportRows">导出检测任务清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="keyword" placeholder="按任务编号检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '任务编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="row.允许动作?.length">
              <button
                v-for="action in row.允许动作"
                :key="action"
                class="link"
                type="button"
                :disabled="busyKey === `${row.id}:${action}`"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测任务数据，可先登记检测任务单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测任务记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

interface TaskRow {
  id: number
  任务编号: string
  任务状态: string
  version?: number
  允许动作?: string[]
  [key: string]: string | number | string[] | null | undefined
}

const ENDPOINT = '/api/task'
const columns = ["任务编号", "所属样品", "检测项目", "检测标准", "指定检测员", "截止日期", "优先级", "任务状态"]

const router = useRouter()
const rows = ref<TaskRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const busyKey = ref('')
const statCards = ref([
  { label: '待分配任务', value: 0 },
  { label: '检测中任务', value: 0 },
  { label: '逾期任务', value: 0 },
])

function resetFilters() {
  keyword.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测任务单登记入口尚未接入审批流'
}

function openDetail(row: TaskRow) {
  void router.push({ name: 'task-detail', params: { id: String(row.id) } })
}

async function runAction(action: string, row: TaskRow) {
  errorMessage.value = ''
  noticeMessage.value = ''
  busyKey.value = `${row.id}:${action}`
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action, expected_version: row.version ?? 0 },
      }),
    })
    const payload = (await response.json().catch(() => ({}))) as {
      ok?: boolean
      message?: string
    }
    if (!response.ok || payload.ok === false) {
      // 409 冲突（非法流转/重复点击/他人已先操作）：刷新列表拿到最新状态后可再次操作
      errorMessage.value = payload.message || '检测任务动作未生效，请刷新后重试'
      await reload()
      return
    }
    noticeMessage.value = payload.message || '检测任务动作已生效'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务操作失败'
  } finally {
    busyKey.value = ''
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const query = new URLSearchParams()
    if (keyword.value.trim()) {
      query.set('keyword', keyword.value.trim())
    }
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('检测任务单列表读取失败')
    }
    const payload = (await listResponse.json()) as { items?: TaskRow[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const stats = (await statsResponse.json()) as Record<string, number>
      statCards.value.forEach((card) => {
        card.value = stats[card.label] ?? 0
      })
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务列表读取失败'
  }
}

onMounted(reload)
</script>
