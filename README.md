# 3DGS 平台前后端分离重构版

这个目录不是空壳建议，而是一版按你当前仓库结构整理好的目标工程：

- `engine/`：保留你原来的算法与流程引擎
- `backend/`：FastAPI 后端，负责任务、配置生成、状态查询、日志流
- `frontend/`：React + TypeScript 前端，负责参数配置、任务运行、结果展示

## 最终目录

```text
3dgs_engine/
├─ backend/
├─ frontend/
└─ engine/
```

## 迁移原则

1. 把你当前仓库中的 `app`、`core`、`configs`、`datasets`、`docs`、`logs`、`outputs`、`third_party`、`scrips` 整体移动到 `engine/`。
2. 把 `scrips` 统一改名为 `scripts`。
3. 把原来所有 `from core...` 改为 `from engine.core...`。
4. 把原来所有 `from app...` 改为 `from engine.app...`。
5. 以后命令行调试走 `python -m engine.app.pipeline_main` 这类入口；平台使用走 `backend + frontend`。

## 直接使用方法

### 方式一：把这个目录当成目标结构手动迁移
对照 `MIGRATION_MAP.md` 和 `scripts/apply_split_refactor.py` 修改你的原仓库。

### 方式二：把当前仓库内容复制到这个目录，再运行迁移脚本
```bash
python scripts/apply_split_refactor.py /你的仓库路径
```

## 后端启动

```bash
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

## 当前这版已经包含

- 任务创建
- 一键流水线启动
- 任务状态轮询
- WebSocket 日志推送
- 结果页骨架
- 运行时 YAML 配置自动生成

## 你需要接入的位置

如果你已经把原项目迁移到 `engine/`，这版后端会优先调用：

- `engine.core.preflight_service.PreflightService`
- `engine.core.video_service.VideoService`
- `engine.core.colmap_service.ColmapService`
- `engine.core.convert_service.ConvertService`
- `engine.core.train_service.TrainerService`
- `engine.core.render_service.RenderService`
- `engine.core.metrics_service.MetricsService`
- `engine.core.viewer_service.ViewerService`

如果其中个别文件暂时还没迁移完整，后端会在对应阶段报出明确错误，方便继续补齐。
