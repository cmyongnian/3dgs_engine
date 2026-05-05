const STORAGE_KEY = '3dgs-platform-settings'
const DEFAULT_API_BASE = '/api'
const DEFAULT_TIMEOUT_MS = 15000

interface RuntimeSettings {
  apiBaseUrl?: string
  wsBaseUrl?: string
}

function 读取运行时设置(): RuntimeSettings {
  if (typeof window === 'undefined') return {}

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as RuntimeSettings
  } catch {
    return {}
  }
}

function 规范化基地址(value?: string) {
  const trimmed = value?.trim()
  if (!trimmed) return DEFAULT_API_BASE
  return trimmed.replace(/\/+$/, '') || DEFAULT_API_BASE
}

function 获取API地址() {
  const settings = 读取运行时设置()
  return 规范化基地址(settings.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE)
}

function 拼接请求地址(path: string) {
  const base = 获取API地址()
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  return `${base}${cleanPath}`
}

function getWebSocketBase() {
  const settings = 读取运行时设置()

  if (settings.wsBaseUrl?.trim()) {
    return settings.wsBaseUrl.trim().replace(/\/+$/, '')
  }

  if (import.meta.env.VITE_WS_BASE_URL) {
    return String(import.meta.env.VITE_WS_BASE_URL).replace(/\/+$/, '')
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

async function 读取错误信息(response: Response) {
  const text = await response.text().catch(() => '')
  if (!text) return `请求失败：${response.status}`

  try {
    const data = JSON.parse(text) as { detail?: unknown; message?: unknown }
    const detail = data.detail ?? data.message
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item?.msg || JSON.stringify(item)).join('；')
    return JSON.stringify(data)
  } catch {
    return text
  }
}

export async function 请求<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  try {
    const response = await fetch(拼接请求地址(path), {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    })

    if (!response.ok) {
      throw new Error(await 读取错误信息(response))
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(
        `请求超时：${DEFAULT_TIMEOUT_MS / 1000} 秒内后端没有响应。请确认后端已启动，且系统设置里的 API 基地址为 /api 或 http://127.0.0.1:8000/api。`,
      )
    }

    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

export const 日志地址 = (taskId: string) =>
  `${getWebSocketBase()}/api/ws/logs/${taskId}`
