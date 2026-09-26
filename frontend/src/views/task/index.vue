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
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length" class="muted-text">无可执行动作</span>
            <RouterLink class="link" :to="`/task/${row.id}`">详情</RouterLink>
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

import { request } from '@/api/client'
import { TASK_ENDPOINT, readErrorMessage, rowActions, runTaskAction, type TaskRow } from '@/api/task'

const ENDPOINT = TASK_ENDPOINT
const columns = ["任务编号", "所属样品", "检测项目", "检测标准", "指定检测员", "截止日期", "优先级", "任务状态"]
const stats = [{"label": "待分配任务", "value": 0}, {"label": "检测中任务", "value": 0}, {"label": "逾期任务", "value": 0}]

const rows = ref<TaskRow[]>([])
const total = ref(0)
const acting = ref(false)
const noticeMessage = ref('')
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测任务单登记入口尚未接入审批流'
}

async function runAction(action: string, row: TaskRow) {
  if (acting.value) return // 防重复提交：上一次动作未返回前不再发起
  acting.value = true
  noticeMessage.value = ''
  errorMessage.value = ''
  try {
    const outcome = await runTaskAction(String(row.id ?? ''), action)
    if (outcome.ok) {
      noticeMessage.value = outcome.message
    } else {
      // 冲突等失败：记录未被改动，刷新拿到最新可执行动作后可再次操作
      errorMessage.value = outcome.message
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务操作失败'
  } finally {
    acting.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, '检测任务单列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务列表读取失败'
  }
}

onMounted(reload)
</script>
