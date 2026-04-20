from __future__ import annotations

import asyncio
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from backend.app.services.runtime_config_service import runtime_config_service
from backend.app.state.task_store import task_store
from backend.app.ws.log_ws import log_hub


class _StreamCapture(io.TextIOBase):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.buffer = ""

    def write(self, text: str) -> int:
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                task_store.append_log(self.task_id, line)
                try:
                    asyncio.run(log_hub.broadcast(self.task_id, line))
                except RuntimeError:
                    pass
        return len(text)

    def flush(self) -> None:
        if self.buffer.strip():
            line = self.buffer.strip()
            task_store.append_log(self.task_id, line)
            try:
                asyncio.run(log_hub.broadcast(self.task_id, line))
            except RuntimeError:
                pass
            self.buffer = ""


class PipelineService:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]

    def run_task(self, task_id: str) -> None:
        task = task_store.get(task_id)
        if task is None:
            return

        payload = task.payload["model"]
        config_paths = runtime_config_service.build(task_id, payload)
        task_store.update(task_id, status="running", current_stage="准备配置", message="已生成运行时配置")

        capture = _StreamCapture(task_id)
        try:
            with redirect_stdout(capture), redirect_stderr(capture):
                self._run_pipeline(task_id, config_paths)
            capture.flush()
            result = self._build_result(payload.scene.scene_name)
            task_store.update(
                task_id,
                status="success",
                current_stage="已完成",
                message="任务执行完成",
                result=result,
            )
        except Exception as exc:  # noqa: BLE001
            capture.flush()
            error_text = f"{exc}\n{traceback.format_exc()}"
            task_store.append_log(task_id, error_text)
            task_store.update(
                task_id,
                status="failed",
                current_stage="执行失败",
                message="任务执行失败",
                error=str(exc),
            )

    def _run_pipeline(self, task_id: str, config_paths: dict[str, str]) -> None:
        task = task_store.get(task_id)
        if task is None:
            raise RuntimeError("任务不存在")

        payload = task.payload["model"]
        flags = payload.pipeline
        system_path = config_paths["system"]

        if flags.input_mode == "video" and flags.run_video_extract:
            self._set_stage(task_id, "视频抽帧")
            from engine.core.video_service import VideoService

            VideoService(system_config_path=system_path, video_config_path=config_paths["video"]).run()

        if flags.run_preflight:
            self._set_stage(task_id, "原始数据预检查")
            from engine.core.preflight_service import PreflightService

            PreflightService(system_config_path=system_path, preflight_config_path=config_paths["preflight"]).run()

        if flags.run_colmap:
            self._set_stage(task_id, "COLMAP 重建")
            from engine.core.colmap_service import ColmapService

            ColmapService(system_config_path=system_path, colmap_config_path=config_paths["colmap"]).run()

        if flags.run_convert:
            self._set_stage(task_id, "数据转换")
            from engine.core.convert_service import ConvertService

            ConvertService(system_config_path=system_path, convert_config_path=config_paths["convert"]).run()

        if flags.run_preflight:
            self._set_stage(task_id, "训练前复检")
            from engine.core.preflight_service import PreflightService

            PreflightService(system_config_path=system_path, preflight_config_path=config_paths["preflight"]).run()

        if flags.run_train:
            self._set_stage(task_id, "模型训练")
            from engine.core.train_service import TrainerService

            TrainerService(system_config_path=system_path, train_config_path=config_paths["train"]).run()

        if flags.run_render:
            self._set_stage(task_id, "离线渲染")
            from engine.core.render_service import RenderService

            RenderService(system_config_path=system_path, render_config_path=config_paths["render"]).run()

        if flags.run_metrics:
            self._set_stage(task_id, "指标评测")
            from engine.core.metrics_service import MetricsService

            MetricsService(system_config_path=system_path, metrics_config_path=config_paths["metrics"]).run()

        if flags.launch_viewer:
            self._set_stage(task_id, "启动查看器")
            from engine.core.viewer_service import ViewerService

            ViewerService(system_config_path=system_path, viewer_config_path=config_paths["viewer"]).run()

    @staticmethod
    def _set_stage(task_id: str, stage: str) -> None:
        task_store.update(task_id, current_stage=stage, message=f"正在执行：{stage}")
        task_store.append_log(task_id, f"===== {stage} =====")

    def _build_result(self, scene_name: str) -> dict[str, str]:
        engine_root = self.project_root / "engine"
        output_dir = engine_root / "outputs" / scene_name
        log_dir = engine_root / "logs" / scene_name
        processed_dir = engine_root / "datasets" / "processed" / scene_name
        return {
            "scene_name": scene_name,
            "output_dir": str(output_dir),
            "log_dir": str(log_dir),
            "processed_dir": str(processed_dir),
        }


pipeline_service = PipelineService()
