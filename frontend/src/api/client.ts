const 基础地址 = 'http://127.0.0.1:8000/api'

export async function 请求<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${基础地址}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

export const 日志地址 = (taskId: string) => `ws://127.0.0.1:8000/api/ws/logs/${taskId}`
