const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

function getWebSocketBase() {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

export async function 请求<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

export const 日志地址 = (taskId: string) => `${getWebSocketBase()}/api/ws/logs/${taskId}`