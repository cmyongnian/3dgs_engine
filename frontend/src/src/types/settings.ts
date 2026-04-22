import type { 创建任务请求, 系统路径配置 } from './task'

export interface 系统设置 {
  apiBaseUrl: string
  wsBaseUrl: string
  systemPaths: 系统路径配置
  tools: {
    colmapExecutable: string
    magickExecutable: string
    ffmpegExecutable: string
    viewerRoot: string
  }
  sceneDefaults: {
    defaultSceneName: string
    inputMode: 创建任务请求['pipeline']['input_mode']
    autoFillPaths: boolean
  }
  pipelineDefaults: 创建任务请求['pipeline']
  trainDefaults: {
    activeProfile: string
    iterations: number
    resolution: number
    eval: boolean
    quiet: boolean
    dataDevice: string
    densifyGradThreshold: number
    densificationInterval: number
    densifyUntilIter: number
    saveIterations: string
    testIterations: string
    checkpointIterations: string
    startCheckpoint: string
    resumeFromLatest: boolean
  }
}

export interface 健康检查响应 {
  status: string
}

export interface 布局检查响应 {
  project_root: string
  engine_exists: boolean
  backend_exists: boolean
  frontend_exists: boolean
  engine_dirs: Record<string, boolean>
}
