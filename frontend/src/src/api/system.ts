import { 请求 } from './client'
import type { 健康检查响应, 布局检查响应 } from '../types/settings'

export function 获取系统健康() {
  return 请求<健康检查响应>('/system/health')
}

export function 获取系统布局() {
  return 请求<布局检查响应>('/system/layout')
}
