import type { 创建任务请求, 数据增强配置, 数据增强预设 } from '../types/task'
import type { 系统设置 } from '../types/settings'

const 存储键 = '3dgs-platform-settings'

function 复制增强配置(config: 数据增强配置): 数据增强配置 {
  return {
    ...config,
    clahe_tile_grid_size: [...config.clahe_tile_grid_size] as [number, number],
  }
}

export function 构建数据增强预设(preset: 数据增强预设): 数据增强配置 {
  const base: 数据增强配置 = {
    enabled: true,
    preset,
    output_subdir: 'augmented_images',
    overwrite: true,
    keep_original_if_failed: true,
    jpeg_quality: 95,
    gray_world: true,
    clahe: true,
    clahe_clip_limit: 2.0,
    clahe_tile_grid_size: [8, 8],
    auto_gamma: false,
    gamma_target_mean: 0.48,
    denoise: false,
    denoise_h: 3.0,
    sharpen: false,
    sharpen_amount: 0.2,
    max_long_edge: 0,
  }

  if (preset === 'off') {
    return {
      ...base,
      enabled: false,
      preset: 'off',
      gray_world: false,
      clahe: false,
      auto_gamma: false,
      denoise: false,
      sharpen: false,
    }
  }

  if (preset === 'low_light') {
    return {
      ...base,
      preset: 'low_light',
      clahe_clip_limit: 2.5,
      auto_gamma: true,
      gamma_target_mean: 0.52,
      denoise: true,
      denoise_h: 3.5,
      sharpen: false,
      sharpen_amount: 0.15,
    }
  }

  if (preset === 'detail') {
    return {
      ...base,
      preset: 'detail',
      clahe_clip_limit: 1.8,
      auto_gamma: false,
      denoise: false,
      sharpen: true,
      sharpen_amount: 0.25,
    }
  }

  if (preset === 'custom') {
    return {
      ...base,
      preset: 'custom',
    }
  }

  return {
    ...base,
    preset: 'safe',
  }
}

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
  processDefaults: {
    colmapUseGpu: true,
    videoTargetFps: 2,
  },
  pipelineDefaults: {
    input_mode: 'images',
    run_preflight: true,
    run_video_extract: false,
    run_data_quality: true,
    run_augmentation: true,
    run_colmap: true,
    run_convert: true,
    run_train: true,
    run_render: true,
    run_metrics: true,
    launch_viewer: false,
  },
  augmentationDefaults: 构建数据增强预设('safe'),
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

function 规范化系统设置(settings: 系统设置): 系统设置 {
  return {
    ...settings,
    processDefaults: {
      colmapUseGpu: Boolean(settings.processDefaults?.colmapUseGpu),
      videoTargetFps: Math.max(1, Number(settings.processDefaults?.videoTargetFps) || 2),
    },
    pipelineDefaults: {
      ...settings.pipelineDefaults,
      run_preflight: settings.pipelineDefaults.run_preflight !== false,
      run_data_quality: settings.pipelineDefaults.run_data_quality !== false,
      run_augmentation: Boolean(settings.pipelineDefaults.run_augmentation),
      run_colmap: Boolean(settings.pipelineDefaults.run_colmap),
    },
    augmentationDefaults: 复制增强配置({
      ...构建数据增强预设(settings.augmentationDefaults?.preset ?? 'safe'),
      ...settings.augmentationDefaults,
      clahe_tile_grid_size: [
        Number(settings.augmentationDefaults?.clahe_tile_grid_size?.[0]) || 8,
        Number(settings.augmentationDefaults?.clahe_tile_grid_size?.[1]) || 8,
      ],
      jpeg_quality: Math.min(100, Math.max(1, Number(settings.augmentationDefaults?.jpeg_quality) || 95)),
      max_long_edge: Math.max(0, Number(settings.augmentationDefaults?.max_long_edge) || 0),
    }),
  }
}

export function 读取系统设置(): 系统设置 {
  if (typeof window === 'undefined') return 默认系统设置

  try {
    const raw = window.localStorage.getItem(存储键)
    if (!raw) return 默认系统设置
    const parsed = JSON.parse(raw) as Partial<系统设置>
    return 规范化系统设置(深合并(默认系统设置, parsed))
  } catch {
    return 默认系统设置
  }
}

export function 保存系统设置(settings: 系统设置) {
  window.localStorage.setItem(存储键, JSON.stringify(规范化系统设置(settings)))
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
  const normalized = 规范化系统设置(settings)
  const 场景名 = normalized.sceneDefaults.defaultSceneName || 'video_scene_01'
  const 输入模式 = normalized.sceneDefaults.inputMode

  return {
    scene: {
      scene_name: 场景名,
      raw_image_path: 组合路径(normalized.systemPaths.raw_data, 场景名, 'images'),
      processed_scene_path: 组合路径(normalized.systemPaths.processed_data, 场景名),
      source_path: 组合路径(normalized.systemPaths.processed_data, 场景名, 'gs_input'),
      model_output: 组合路径(normalized.systemPaths.outputs, 场景名),
      video_path: `${normalized.systemPaths.videos_data.replace(/[\\/]+$/, '')}/${场景名}.mp4`,
      colmap_executable: normalized.tools.colmapExecutable,
      magick_executable: normalized.tools.magickExecutable,
      ffmpeg_executable: normalized.tools.ffmpegExecutable,
      viewer_root: normalized.tools.viewerRoot,
      colmap_use_gpu: normalized.processDefaults.colmapUseGpu,
      video_target_fps: normalized.processDefaults.videoTargetFps,
    },
    system_paths: { ...normalized.systemPaths },
    pipeline: {
      ...normalized.pipelineDefaults,
      input_mode: 输入模式,
      run_video_extract:
        输入模式 === 'video' ? true : normalized.pipelineDefaults.run_video_extract,
      run_augmentation:
        normalized.pipelineDefaults.run_augmentation && normalized.augmentationDefaults.enabled,
    },
    augmentation: 复制增强配置(normalized.augmentationDefaults),
    train: {
      active_profile: normalized.trainDefaults.activeProfile,
      eval: normalized.trainDefaults.eval,
      iterations: normalized.trainDefaults.iterations,
      save_iterations: 解析数字数组(normalized.trainDefaults.saveIterations),
      test_iterations: 解析数字数组(normalized.trainDefaults.testIterations),
      checkpoint_iterations: 解析数字数组(normalized.trainDefaults.checkpointIterations),
      start_checkpoint: normalized.trainDefaults.startCheckpoint,
      resume_from_latest: normalized.trainDefaults.resumeFromLatest,
      quiet: normalized.trainDefaults.quiet,
      extra_args: {
        data_device: normalized.trainDefaults.dataDevice,
        resolution: normalized.trainDefaults.resolution,
        densify_grad_threshold: normalized.trainDefaults.densifyGradThreshold,
        densification_interval: normalized.trainDefaults.densificationInterval,
        densify_until_iter: normalized.trainDefaults.densifyUntilIter,
      },
    },
  }
}

export function 根据场景名更新路径(
  表单: 创建任务请求,
  settings: 系统设置,
  sceneName: string,
): 创建任务请求 {
  const normalized = 规范化系统设置(settings)
  const name = sceneName.trim() || normalized.sceneDefaults.defaultSceneName || 'video_scene_01'

  return {
    ...表单,
    scene: {
      ...表单.scene,
      scene_name: sceneName,
      raw_image_path: 组合路径(normalized.systemPaths.raw_data, name, 'images'),
      processed_scene_path: 组合路径(normalized.systemPaths.processed_data, name),
      source_path: 组合路径(normalized.systemPaths.processed_data, name, 'gs_input'),
      model_output: 组合路径(normalized.systemPaths.outputs, name),
      video_path: `${normalized.systemPaths.videos_data.replace(/[\\/]+$/, '')}/${name}.mp4`,
      colmap_executable: normalized.tools.colmapExecutable,
      magick_executable: normalized.tools.magickExecutable,
      ffmpeg_executable: normalized.tools.ffmpegExecutable,
      viewer_root: normalized.tools.viewerRoot,
      colmap_use_gpu: normalized.processDefaults.colmapUseGpu,
      video_target_fps: normalized.processDefaults.videoTargetFps,
    },
    system_paths: {
      ...normalized.systemPaths,
    },
  }
}
