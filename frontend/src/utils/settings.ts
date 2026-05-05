import type { 创建任务请求 } from '../types/task'
import type { 系统设置 } from '../types/settings'

const 存储键 = '3dgs-platform-settings'

export const 默认系统设置: 系统设置 = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api',
  wsBaseUrl: import.meta.env.VITE_WS_BASE_URL ?? '',
  systemPaths: {
    gs_repo: 'third_party/gaussian-splatting',
    raw_data: 'datasets/raw',
    processed_data: 'datasets/processed',
    outputs: 'outputs',
    logs: 'logs',
    videos_data: 'datasets/videos',
  },
  tools: {
    colmapExecutable: 'third_party/colmap/COLMAP.bat',
    magickExecutable: '',
    ffmpegExecutable: 'ffmpeg',
    viewerRoot: 'third_party/viewer/bin',
  },
  sceneDefaults: {
    defaultSceneName: 'video_scene_01',
    inputMode: 'images',
    autoFillPaths: true,
  },
  pipelineDefaults: {
    input_mode: 'images',
    run_preflight: true,
    run_video_extract: false,

    // 新增：是否执行数据增强
    // 该步骤位于 COLMAP 之前
    run_augmentation: true,

    run_colmap: true,
    run_convert: true,
    run_train: true,
    run_render: true,
    run_metrics: true,
    launch_viewer: false,
  },
  trainDefaults: {
    activeProfile: 'low_vram',
    iterations: 30000,
    resolution: 4,
    eval: true,
    quiet: false,
    dataDevice: 'cpu',
    densifyGradThreshold: 0.001,
    densificationInterval: 200,
    densifyUntilIter: 3000,
    saveIterations: '7000,30000',
    testIterations: '-1',
    checkpointIterations: '2000,15000,30000',
    startCheckpoint: '',
    resumeFromLatest: false,
  },
}

function 深合并<T>(base: T, patch: Partial<T>): T {
  const result = (Array.isArray(base)
    ? [...(base as unknown as unknown[])]
    : { ...(base as Record<string, unknown>) }) as Record<string, unknown>

  for (const [key, value] of Object.entries(patch)) {
    const baseValue = (base as Record<string, unknown>)[key]

    if (
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      baseValue &&
      typeof baseValue === 'object' &&
      !Array.isArray(baseValue)
    ) {
      result[key] = 深合并(
        baseValue as Record<string, unknown>,
        value as Record<string, unknown>,
      )
    } else if (value !== undefined) {
      result[key] = value
    }
  }

  return result as T
}

export function 读取系统设置(): 系统设置 {
  if (typeof window === 'undefined') return 默认系统设置

  try {
    const raw = window.localStorage.getItem(存储键)
    if (!raw) return 默认系统设置
    const parsed = JSON.parse(raw) as Partial<系统设置>
    return 深合并(默认系统设置, parsed)
  } catch {
    return 默认系统设置
  }
}

export function 保存系统设置(settings: 系统设置) {
  window.localStorage.setItem(存储键, JSON.stringify(settings))
}

export function 重置系统设置() {
  window.localStorage.removeItem(存储键)
}

export function 解析数字数组(text: string): number[] {
  return text
    .split(/[，,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map(Number)
    .filter((item) => Number.isFinite(item))
}

function 组合路径(base: string, name: string, tail = '') {
  const safeBase = base.replace(/[\\/]+$/, '')
  const safeTail = tail.replace(/^[\\/]+/, '')

  if (!safeTail) return `${safeBase}/${name}`
  return `${safeBase}/${name}/${safeTail}`
}

export function 生成默认任务请求(settings: 系统设置): 创建任务请求 {
  const 场景名 = settings.sceneDefaults.defaultSceneName || 'video_scene_01'
  const 输入模式 = settings.sceneDefaults.inputMode

  return {
    scene: {
      scene_name: 场景名,
      raw_image_path: 组合路径(settings.systemPaths.raw_data, 场景名, 'images'),
      processed_scene_path: 组合路径(settings.systemPaths.processed_data, 场景名),
      source_path: 组合路径(settings.systemPaths.processed_data, 场景名, 'gs_input'),
      model_output: 组合路径(settings.systemPaths.outputs, 场景名),
      video_path: `${settings.systemPaths.videos_data.replace(/[\\/]+$/, '')}/${场景名}.mp4`,
      colmap_executable: settings.tools.colmapExecutable,
      magick_executable: settings.tools.magickExecutable,
      ffmpeg_executable: settings.tools.ffmpegExecutable,
      viewer_root: settings.tools.viewerRoot,
    },
    system_paths: { ...settings.systemPaths },
    pipeline: {
      ...settings.pipelineDefaults,
      input_mode: 输入模式,
    },
    train: {
      active_profile: settings.trainDefaults.activeProfile,
      eval: settings.trainDefaults.eval,
      iterations: settings.trainDefaults.iterations,
      save_iterations: 解析数字数组(settings.trainDefaults.saveIterations),
      test_iterations: 解析数字数组(settings.trainDefaults.testIterations),
      checkpoint_iterations: 解析数字数组(settings.trainDefaults.checkpointIterations),
      start_checkpoint: settings.trainDefaults.startCheckpoint,
      resume_from_latest: settings.trainDefaults.resumeFromLatest,
      quiet: settings.trainDefaults.quiet,
      extra_args: {
        data_device: settings.trainDefaults.dataDevice,
        resolution: settings.trainDefaults.resolution,
        densify_grad_threshold: settings.trainDefaults.densifyGradThreshold,
        densification_interval: settings.trainDefaults.densificationInterval,
        densify_until_iter: settings.trainDefaults.densifyUntilIter,
      },
    },
  }
}

export function 根据场景名更新路径(
  表单: 创建任务请求,
  settings: 系统设置,
  sceneName: string,
): 创建任务请求 {
  const name = sceneName.trim() || settings.sceneDefaults.defaultSceneName || 'video_scene_01'

  return {
    ...表单,
    scene: {
      ...表单.scene,
      scene_name: sceneName,
      raw_image_path: 组合路径(settings.systemPaths.raw_data, name, 'images'),
      processed_scene_path: 组合路径(settings.systemPaths.processed_data, name),
      source_path: 组合路径(settings.systemPaths.processed_data, name, 'gs_input'),
      model_output: 组合路径(settings.systemPaths.outputs, name),
      video_path: `${settings.systemPaths.videos_data.replace(/[\\/]+$/, '')}/${name}.mp4`,
      colmap_executable: settings.tools.colmapExecutable,
      magick_executable: settings.tools.magickExecutable,
      ffmpeg_executable: settings.tools.ffmpegExecutable,
      viewer_root: settings.tools.viewerRoot,
    },
    system_paths: {
      ...settings.systemPaths,
    },
  }
}