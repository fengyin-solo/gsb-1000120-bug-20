/** 检测任务接口小封装：列表页与详情页共用同一份动作口径与错误解读。 */
import { request } from '@/api/client'

export const TASK_ENDPOINT = '/api/task'

export type TaskRow = Record<string, string | number | null | string[] | undefined>

/** 后端按状态机给出的当前可执行动作；缺失时按空数组处理，页面不再自行猜测。 */
export function rowActions(row: TaskRow): string[] {
  const actions = row.available_actions
  return Array.isArray(actions) ? actions : []
}

/** 从错误响应里挑出后端写的可读说明（FastAPI 用 detail，业务结果用 message）。 */
export async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown; message?: unknown }
    if (typeof body.detail === 'string' && body.detail) return body.detail
    if (typeof body.message === 'string' && body.message) return body.message
  } catch {
    /* 响应体不是 JSON 时走兜底文案 */
  }
  return fallback
}

export interface ActionOutcome {
  ok: boolean
  message: string
}

/** 执行状态动作；冲突（409）等失败时记录未被改动，调用方刷新后可再次操作。 */
export async function runTaskAction(id: string | number, action: string): Promise<ActionOutcome> {
  const response = await request(`${TASK_ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  if (!response.ok) {
    return { ok: false, message: await readErrorMessage(response, '检测任务动作未生效，请稍后重试') }
  }
  const result = (await response.json()) as { message?: string }
  return { ok: true, message: result.message || `检测任务单已${action}` }
}
