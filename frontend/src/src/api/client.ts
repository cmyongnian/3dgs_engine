const STORAGE_KEY = '3dgs-platform-settings'

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

function 获取API地址() {
  const settings = 读取运行时设置()
  return settings.apiBaseUrl?.trim() || import.meta.env.VITE_API_BASE_URL || '/api'
}

function getWebSocketBase() {
  const settings = 读取运行时设置()

  if (settings.wsBaseUrl?.trim()) {
    return settings.wsBaseUrl.trim()
  }

  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

export async function 请求<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${获取API地址()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    try {
      const data = await response.json()
      throw new Error(data.detail || `请求失败：${response.status}`)
    } catch {
      const text = await response.text().catch(() => '')
      throw new Error(text || `请求失败：${response.status}`)
    }
  }

  return (await response.json()) as T
}

export const 日志地址 = (taskId: string) =>
  `${getWebSocketBase()}/api/ws/logs/${taskId}`
