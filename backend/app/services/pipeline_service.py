from __future__ import annotations

import asyncio
import io
import json
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.app.services.runtime_config_service import runtime_config_service
from backend.app.state.task_store import task_store
from backend.app.ws.log_ws import log_hub


class TaskStoppedError(RuntimeError):
    pass


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
    STAGES = [
        {"key": "video_extract", "label": "视频抽帧", "order": 1},
        {"key": "preflight_raw", "label": "原始数据预检查", "order": 2},
        {"key": "colmap", "label": "COLMAP 重建", "order": 3},
        {"key": "convert", "label": "数据转换", "order": 4},
        {"key": "preflight_processed", "label": "训练前复检", "order": 5},
        {"key": "train", "label": "模型训练", "order": 6},
        {"key": "render", "label": "离线渲染", "order": 7},
        {"key": "metrics", "label": "指标评测", "order": 8},
        {"key": "viewer", "label": "启动查看器", "order": 9},
    ]

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]

    def run_task(self, task_id: str) -> None:
        task = task_store.get(task_id)
        if task is None:
            return

        payload = task.payload["model"]
        capture = _StreamCapture(task_id)

        try:
            task_store.mark_started(task_id, stage="准备配置")
            config_paths = runtime_config_service.build(task_id, payload)

            runtime_dir = self._guess_runtime_dir(config_paths)
            task_store.update(
                task_id,
                status="running",
                current_stage="准备配置",
                message="已生成运行时配置",
                runtime_dir=runtime_dir,
            )

            with redirect_stdout(capture), redirect_stderr(capture):
                self._run_pipeline(task_id, config_paths)

            capture.flush()

            result = self._build_result(payload.scene.scene_name, config_paths)
            metrics_summary = result.get("metrics_summary", {})
            result_files = result.get("result_files", {})

            final_status = "success"
            final_message = "任务执行完成"

            if payload.pipeline.run_train and not payload.pipeline.run_render and not payload.pipeline.run_metrics:
                final_message = "训练阶段执行完成"

            task_store.update_metrics_summary(task_id, metrics_summary)
            task_store.update_result_files(task_id, result_files)
            task_store.mark_finished(
                task_id,
                status=final_status,
                message=final_message,
                error=None,
            )
            task_store.update(
                task_id,
                current_stage="已完成",
                result=result,
            )

        except TaskStoppedError as exc:
            capture.flush()
            task_store.append_log(task_id, "任务已停止")
            task_store.mark_finished(
                task_id,
                status="stopped",
                message="任务已停止",
                error=str(exc),
            )
            task_store.update(
                task_id,
                current_stage="已停止",
                error=str(exc),
            )

        except Exception as exc:  # noqa: BLE001
            capture.flush()
            error_type = self._classify_error(exc)
            error_text = "{0}\n{1}".format(exc, traceback.format_exc())
            task_store.append_log(task_id, error_text)
            task_store.mark_finished(
                task_id,
                status="failed",
                message="任务执行失败",
                error=str(exc),
            )
            task_store.update(
                task_id,
                current_stage="执行失败",
                error=str(exc),
                last_error_type=error_type,
            )

    def _run_pipeline(self, task_id: str, config_paths: Dict[str, str]) -> None:
        task = task_store.get(task_id)
        if task is None:
            raise RuntimeError("任务不存在")

        payload = task.payload["model"]
        flags = payload.pipeline
        system_path = config_paths["system"]

        if flags.input_mode == "video" and flags.run_video_extract:
            self._execute_stage(
                task_id=task_id,
                stage_key="video_extract",
                action=lambda: self._run_video(system_path, config_paths["video"]),
            )

        if flags.run_preflight:
            self._execute_stage(
                task_id=task_id,
                stage_key="preflight_raw",
                action=lambda: self._run_preflight(system_path, config_paths["preflight"]),
            )

        if flags.run_colmap:
            self._execute_stage(
                task_id=task_id,
                stage_key="colmap",
                action=lambda: self._run_colmap(system_path, config_paths["colmap"]),
            )

        if flags.run_convert:
            self._execute_stage(
                task_id=task_id,
                stage_key="convert",
                action=lambda: self._run_convert(system_path, config_paths["convert"]),
            )

        if flags.run_preflight:
            self._execute_stage(
                task_id=task_id,
                stage_key="preflight_processed",
                action=lambda: self._run_preflight(system_path, config_paths["preflight"]),
            )

        if flags.run_train:
            self._execute_stage(
                task_id=task_id,
                stage_key="train",
                action=lambda: self._run_train(system_path, config_paths["train"]),
            )

        if flags.run_render:
            self._execute_stage(
                task_id=task_id,
                stage_key="render",
                action=lambda: self._run_render(system_path, config_paths["render"]),
            )

        if flags.run_metrics:
            self._execute_stage(
                task_id=task_id,
                stage_key="metrics",
                action=lambda: self._run_metrics(system_path, config_paths["metrics"]),
            )

        if flags.launch_viewer:
            self._execute_stage(
                task_id=task_id,
                stage_key="viewer",
                action=lambda: self._run_viewer(system_path, config_paths["viewer"]),
            )

    def _execute_stage(
        self,
        task_id: str,
        stage_key: str,
        action: Callable[[], None],
    ) -> None:
        task = task_store.get(task_id)
        if task is None:
            raise RuntimeError("任务不存在")

        stage = self._stage_meta(stage_key)
        self._ensure_not_stopped(task_id)

        task_store.start_stage(
            task_id,
            stage_key=stage["key"],
            stage_label=stage["label"],
            order=stage["order"],
        )
        task_store.update(
            task_id,
            current_stage=stage["label"],
            message="正在执行：{0}".format(stage["label"]),
        )
        task_store.append_log(task_id, "===== {0} =====".format(stage["label"]))

        try:
            action()
            task_store.finish_stage(
                task_id,
                stage_key=stage["key"],
                status="success",
            )
            self._ensure_not_stopped(task_id)
        except TaskStoppedError:
            task_store.finish_stage(
                task_id,
                stage_key=stage["key"],
                status="stopped",
                error_type="user_stop",
                error_message="任务已停止",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            task_store.finish_stage(
                task_id,
                stage_key=stage["key"],
                status="failed",
                error_type=self._classify_error(exc),
                error_message=str(exc),
            )
            raise

    def _ensure_not_stopped(self, task_id: str) -> None:
        task = task_store.get(task_id)
        if task is None:
            raise RuntimeError("任务不存在")

        if task.stop_requested:
            raise TaskStoppedError("已收到停止请求")

    def _stage_meta(self, stage_key: str) -> Dict[str, Any]:
        for item in self.STAGES:
            if item["key"] == stage_key:
                return item
        raise KeyError("未知阶段：{0}".format(stage_key))

    def _classify_error(self, exc: Exception) -> str:
        message = str(exc).lower()

        if isinstance(exc, TaskStoppedError):
            return "user_stop"

        if "not found" in message or "不存在" in message or "找不到" in message:
            return "environment_error"

        if "cuda" in message or "显存" in message or "memory" in message:
            return "runtime_error"

        if "yaml" in message or "config" in message or "配置" in message:
            return "config_error"

        if "colmap" in message or "ffmpeg" in message or "magick" in message:
            return "tool_error"

        return "runtime_error"

    def _guess_runtime_dir(self, config_paths: Dict[str, str]) -> Optional[str]:
        system_path = config_paths.get("system")
        if not system_path:
            return None
        return str(Path(system_path).resolve().parent)

    def _build_result(self, scene_name: str, config_paths: Dict[str, str]) -> Dict[str, Any]:
        engine_root = self.project_root / "engine"
        output_dir = engine_root / "outputs" / scene_name
        log_dir = engine_root / "logs" / scene_name
        processed_dir = engine_root / "datasets" / "processed" / scene_name

        metrics_json = output_dir / "metrics.json"
        report_json = output_dir / "report.json"
        summary_csv = output_dir / "summary.csv"
        summary_txt = output_dir / "summary.txt"

        preview_images = self._collect_preview_images(output_dir)
        metrics_summary = self._read_json(metrics_json)
        report_summary = self._read_json(report_json)

        result_files = {
            "metrics_json": str(metrics_json) if metrics_json.exists() else "",
            "report_json": str(report_json) if report_json.exists() else "",
            "summary_csv": str(summary_csv) if summary_csv.exists() else "",
            "summary_txt": str(summary_txt) if summary_txt.exists() else "",
        }

        task = task_store.get(config_paths.get("task_id", ""))  # 兼容占位，不依赖
        stage_history = []
        if task is not None:
            stage_history = task.stage_history

        result = {
            "scene_name": scene_name,
            "output_dir": str(output_dir),
            "log_dir": str(log_dir),
            "processed_dir": str(processed_dir),
            "runtime_dir": self._guess_runtime_dir(config_paths) or "",
            "metrics_summary": metrics_summary,
            "report_summary": report_summary,
            "result_files": result_files,
            "preview_images": preview_images,
            "stage_history": stage_history,
        }
        return result

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _collect_preview_images(self, output_dir: Path) -> List[str]:
        if not output_dir.exists():
            return []

        image_files = []
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            image_files.extend(output_dir.rglob(pattern))

        image_files = sorted(image_files)[:6]
        return [str(item) for item in image_files]

    @staticmethod
    def _run_video(system_path: str, video_path: str) -> None:
        from engine.core.video_service import VideoService

        VideoService(
            system_config_path=system_path,
            video_config_path=video_path,
        ).run()

    @staticmethod
    def _run_preflight(system_path: str, preflight_path: str) -> None:
        from engine.core.preflight_service import PreflightService

        PreflightService(
            system_config_path=system_path,
            preflight_config_path=preflight_path,
        ).run()

    @staticmethod
    def _run_colmap(system_path: str, colmap_path: str) -> None:
        from engine.core.colmap_service import ColmapService

        ColmapService(
            system_config_path=system_path,
            colmap_config_path=colmap_path,
        ).run()

    @staticmethod
    def _run_convert(system_path: str, convert_path: str) -> None:
        from engine.core.convert_service import ConvertService

        ConvertService(
            system_config_path=system_path,
            convert_config_path=convert_path,
        ).run()

    @staticmethod
    def _run_train(system_path: str, train_path: str) -> None:
        from engine.core.train_service import TrainerService

        TrainerService(
            system_config_path=system_path,
            train_config_path=train_path,
        ).run()

    @staticmethod
    def _run_render(system_path: str, render_path: str) -> None:
        from engine.core.render_service import RenderService

        RenderService(
            system_config_path=system_path,
            render_config_path=render_path,
        ).run()

    @staticmethod
    def _run_metrics(system_path: str, metrics_path: str) -> None:
        from engine.core.metrics_service import MetricsService

        MetricsService(
            system_config_path=system_path,
            metrics_config_path=metrics_path,
        ).run()

    @staticmethod
    def _run_viewer(system_path: str, viewer_path: str) -> None:
        from engine.core.viewer_service import ViewerService

        ViewerService(
            system_config_path=system_path,
            viewer_config_path=viewer_path,
        ).run()


pipeline_service = PipelineService()