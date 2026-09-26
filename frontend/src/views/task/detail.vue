<template>
  <section class="page" data-module="task">
    <header class="page-head">
      <div>
        <h2>检测任务单详情</h2>
        <p class="page-desc">状态与可执行动作和列表页同一份口径；历史数据按新规则复核后仍可查看。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/task">返回列表</RouterLink>
      </div>
    </header>

    <table v-if="detail" class="data-table">
      <tbody>
        <tr v-for="field in fields" :key="field">
          <th>{{ field }}</th>
          <td>{{ detail[field] ?? '—' }}</td>
        </tr>
        <tr>
          <th>可执行动作</th>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
              @click="runAction(action)"
            >
              {{ action }}
            </button>
            <span v-if="!actions.length" class="muted-text">当前状态下无可执行动作</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty-state">{{ errorMessage || '检测任务单加载中…' }}</p>

    <footer class="page-foot">
      <span>任务单号：{{ entryId }}</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="detail && errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import { TASK_ENDPOINT, readErrorMessage, rowActions, runTaskAction, type TaskRow } from '@/api/task'

const fields = ["任务编号", "所属样品", "检测项目", "检测标准", "指定检测员", "截止日期", "优先级", "任务状态"]

const route = useRoute()
const entryId = String(route.params.id ?? '')

const detail = ref<TaskRow | null>(null)
const acting = ref(false)
const noticeMessage = ref('')
const errorMessage = ref('')

const actions = computed(() => (detail.value ? rowActions(detail.value) : []))

async function runAction(action: string) {
  if (acting.value) return // 防重复提交：上一次动作未返回前不再发起
  acting.value = true
  noticeMessage.value = ''
  errorMessage.value = ''
  try {
    const outcome = await runTaskAction(entryId, action)
    if (outcome.ok) {
      noticeMessage.value = outcome.message
    } else {
      // 冲突等失败：记录未被改动，刷新拿到最新状态后可再次操作
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
  try {
    const response = await request(`${TASK_ENDPOINT}/${entryId}`)
    if (!response.ok) {
      detail.value = null
      errorMessage.value = await readErrorMessage(response, '检测任务单读取失败')
      return
    }
    detail.value = (await response.json()) as TaskRow
  } catch (error) {
    detail.value = null
    errorMessage.value = error instanceof Error ? error.message : '检测任务单读取失败'
  }
}

onMounted(reload)
</script>
