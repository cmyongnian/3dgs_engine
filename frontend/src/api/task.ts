import { 请求 } from './client'
import type {
  创建任务请求,
  任务动作响应,
  任务列表响应,
  任务响应,
  结果响应,
  任务日志响应,
} from '../types/task'

export function 创建任务(payload: 创建任务请求) {
  return 请求<任务响应>('/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function 创建并启动任务(payload: 创建任务请求) {
  return 请求<任务响应>('/tasks/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function 启动任务(taskId: string) {
  return 请求<任务响应>(`/tasks/${taskId}/start`, {
    method: 'POST',
  })
}

export function 停止任务(taskId: string) {
  return 请求<任务动作响应>(`/tasks/${taskId}/stop`, {
    method: 'POST',
  })
}

export function 立即停止任务(taskId: string) {
  return 请求<任务动作响应>(`/tasks/${taskId}/force-stop`, {
    method: 'POST',
  })
}

export function 重试任务(taskId: string) {
  return 请求<任务动作响应>(`/tasks/${taskId}/retry`, {
    method: 'POST',
  })
}

export function 删除任务(taskId: string) {
  return 请求<任务动作响应>(`/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export function 获取任务(taskId: string) {
  return 请求<任务响应>(`/tasks/${taskId}`)
}

export function 获取结果(taskId: string) {
  return 请求<结果响应>(`/results/${taskId}`)
}

export function 获取任务日志(taskId: string) {
  return 请求<任务日志响应>(`/tasks/${taskId}/logs`)
}

export async function 获取任务列表() {
  const data = await 请求<任务列表响应>('/tasks')
  return data.items ?? []
}