# 3DGS 三维重建平台

本项目面向 3D Gaussian Splatting 三维重建流程，采用前后端分离架构实现任务管理、流程调度与结果展示。系统由算法引擎、后端服务和前端界面三部分组成，支持数据预检查、视频抽帧、COLMAP 重建、数据转换、模型训练、离线渲染、指标评测和结果查看等功能。

## 项目结构

```text
3dgs_engine/
├─ backend/   # FastAPI 后端，负责任务调度、状态查询、日志服务与接口封装
├─ frontend/  # React + TypeScript 前端，负责参数配置、任务运行与结果展示
├─ engine/    # 三维重建流程引擎与相关配置、数据目录、第三方依赖
└─ scripts/   # 辅助脚本
```

## 系统功能

- 任务创建与启动
- 运行时配置生成
- 任务状态查询与任务列表获取
- WebSocket 日志推送
- 三维重建流程调度
- 结果信息展示
- 系统健康检查与目录结构检查

## 处理流程

1. 数据预检查
2. 视频抽帧（可选）
3. COLMAP 重建
4. 数据转换
5. 模型训练
6. 离线渲染
7. 指标评测
8. 查看器启动（可选）

## 环境要求

### 后端

- Python 3.10 及以上
- FastAPI
- Uvicorn

安装依赖：

```bash
pip install -r backend/requirements.txt
```

启动服务：

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

- Node.js 18 及以上
- npm 9 及以上

安装与启动：

```bash
cd frontend
npm install
npm run dev
```

## 引擎说明

`engine/` 目录保留了三维重建相关流程实现，主要包括：

- `engine.core.preflight_service.PreflightService`
- `engine.core.video_service.VideoService`
- `engine.core.colmap_service.ColmapService`
- `engine.core.convert_service.ConvertService`
- `engine.core.train_service.TrainerService`
- `engine.core.render_service.RenderService`
- `engine.core.metrics_service.MetricsService`
- `engine.core.viewer_service.ViewerService`

## 接口概览

### 任务接口

- `POST /api/tasks/create`：创建任务
- `POST /api/tasks/{task_id}/start`：启动任务
- `GET /api/tasks/{task_id}`：获取任务状态
- `GET /api/tasks/{task_id}/result`：获取任务结果
- `GET /api/tasks`：获取任务列表
- `GET /api/ws/logs/{task_id}`：获取任务日志流

### 系统接口

- `GET /api/system/health`：服务健康检查
- `GET /api/system/layout`：项目目录结构检查

## 使用建议

- 首次使用时，先在“系统设置”中配置默认目录与工具路径。
- 创建任务前，建议确认输入模式、数据路径和输出目录。
- 运行任务后，可在任务运行页查看阶段进度与实时日志。
- 任务完成后，可在结果页查看输出目录与结果信息。

## 许可协议

本项目采用仓库中 `LICENSE` 文件所示协议。
