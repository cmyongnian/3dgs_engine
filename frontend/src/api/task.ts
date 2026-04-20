import { 请求 } from './client'
import type { 创建任务请求, 任务响应 } from '../types/task'

export function 创建任务(payload: 创建任务请求) {
  return 请求<任务响应>('/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function 启动任务(taskId: string) {
  return 请求<任务响应>(`/tasks/${taskId}/start`, {
    method: 'POST',
  })
}

export function 获取任务(taskId: string) {
  return 请求<任务响应>(`/tasks/${taskId}`)
}

export function 获取结果(taskId: string) {
  return 请求<{ task_id: string; status: string; scene_name: string; result: Record<string, string>; error?: string | null }>(`/results/${taskId}`)
}
