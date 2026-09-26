<template>
  <section class="page" data-module="task-detail">
    <header class="page-head">
      <div>
        <h2>检测任务单详情</h2>
        <p class="page-desc">状态口径与列表页一致：待分配 → 已分配 → 检测中 → 已完成 → 已复核，动作按钮按当前状态给出。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="errorMessage" class="page-foot">
      <span class="error-text">{{ errorMessage }}</span>
      <button class="btn" type="button" @click="loadDetail">重新加载</button>
    </div>

    <template v-else-if="entry">
      <div class="detail-actions">
        <button
          v-for="action in entry.允许动作 ?? []"
          :key="action"
          class="btn primary"
          type="button"
          :disabled="busyAction === action"
          @click="runAction(action)"
        >
          {{ busyAction === action ? '提交中…' : action }}
        </button>
        <span v-if="!(entry.允许动作 ?? []).length" class="page-desc">
          当前状态「{{ entry.任务状态 }}」下无可执行动作
        </span>
      </div>

      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field" class="detail-item">
          <span>{{ field }}</span>
          <strong>{{ entry[field] ?? '—' }}</strong>
        </div>
        <div class="detail-item">
          <span>数据版本</span>
          <strong>v{{ entry.version ?? 0 }}</strong>
        </div>
      </dl>

      <footer class="page-foot">
        <span v-if="entry.规则版本" class="notice-text">{{ entry.规则版本 }}（历史数据仍可查看）</span>
        <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

interface TaskDetail {
  id: number
  任务编号: string
  所属样品?: string | null
  检测项目?: string | null
  检测标准?: string | null
  指定检测员?: string | null
  截止日期?: string | null
  优先级?: string | null
  任务状态: string
  version?: number
  规则版本?: string
  允许动作?: string[]
  [key: string]: string | number | string[] | null | undefined
}

const ENDPOINT = '/api/task'
const detailFields = ["任务编号", "所属样品", "检测项目", "检测标准", "指定检测员", "截止日期", "优先级", "任务状态"]

const route = useRoute()
const router = useRouter()
const entry = ref<TaskDetail | null>(null)
const errorMessage = ref('')
const noticeMessage = ref('')
const busyAction = ref('')

function goBack() {
  void router.push({ name: 'task' })
}

async function loadDetail() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${String(route.params.id)}`)
    if (response.status === 404) {
      throw new Error('检测任务单不存在或已归档')
    }
    if (!response.ok) {
      throw new Error('检测任务单详情读取失败')
    }
    entry.value = (await response.json()) as TaskDetail
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务详情读取失败'
  }
}

async function runAction(action: string) {
  if (!entry.value) {
    return
  }
  errorMessage.value = ''
  noticeMessage.value = ''
  busyAction.value = action
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action, expected_version: entry.value.version ?? 0 },
      }),
    })
    const payload = (await response.json().catch(() => ({}))) as {
      ok?: boolean
      message?: string
    }
    // 409 冲突：状态已被他人推进或重复提交，详情重新拉取后按钮刷新，可再次操作
    noticeMessage.value = payload.message || ''
    await loadDetail()
    if (!response.ok || payload.ok === false) {
      errorMessage.value = payload.message || '动作未生效，请按最新状态重试'
      noticeMessage.value = ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务操作失败'
  } finally {
    busyAction.value = ''
  }
}

onMounted(loadDetail)
</script>
