import asyncio
import io
import json
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from backend.app.services.runtime_config_service import runtime_config_service
from backend.app.state.task_store import task_store
from backend.app.ws.log_ws import log_hub
from engine.core.process_utils import ImmediateStopRequested, process_registry


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
        {"key": "augmentation", "label": "数据增强", "order": 3},
        {"key": "colmap", "label": "COLMAP 重建", "order": 4},
        {"key": "colmap_quality", "label": "COLMAP 质量分析", "order": 5},
        {"key": "convert", "label": "数据转换", "order": 6},
        {"key": "preflight_processed", "label": "训练前复检", "order": 7},
        {"key": "train", "label": "模型训练", "order": 8},
        {"key": "render", "label": "离线渲染", "order": 9},
        {"key": "metrics", "label": "指标评测", "order": 10},
        {"key": "report", "label": "结果报告", "order": 11},
        {"key": "viewer", "label": "启动查看器", "order": 12},
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

            result = self._build_result(
                task_id=task_id,
                scene_name=payload.scene.scene_name,
                config_paths=config_paths,
            )

            metrics_summary = result.get("metrics_summary", {})
            result_files = result.get("result_files", {})

            task_store.update_metrics_summary(task_id, metrics_summary)
            task_store.update_result_files(task_id, result_files)

            task_store.mark_finished(
                task_id,
                status="success",
                message="任务执行完成",
                error=None,
            )

            task_store.update(
                task_id,
                current_stage="已完成",
                result=result,
            )

            process_registry.clear_task(task_id)

        except (TaskStoppedError, ImmediateStopRequested) as exc:
            capture.flush()

            if isinstance(exc, ImmediateStopRequested):
                stop_message = "任务已立即停止"
            else:
                stop_message = "任务已停止"

            task_store.append_log(task_id, stop_message)

            task_store.mark_finished(
                task_id,
                status="stopped",
                message=stop_message,
                error=str(exc),
            )

            task_store.update(
                task_id,
                current_stage="已停止",
                error=str(exc),
            )

            process_registry.clear_task(task_id)

        except Exception as exc:
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

            process_registry.clear_task(task_id)

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
                action=lambda: self._run_video(
                    task_id,
                    system_path,
                    config_paths["video"],
                ),
            )

        if flags.run_preflight:
            self._execute_stage(
                task_id=task_id,
                stage_key="preflight_raw",
                action=lambda: self._run_preflight(
                    system_path,
                    config_paths["preflight"],
                ),
            )
        if getattr(flags, "run_augmentation", True):
          self._execute_stage(
             task_id=task_id,
             stage_key="augmentation",
             action=lambda: self._run_augmentation(
                task_id,
                system_path,
                config_paths["augmentation"],
             ),
            )
        if flags.run_colmap:
            self._execute_stage(
                task_id=task_id,
                stage_key="colmap",
                action=lambda: self._run_colmap(
                    task_id,
                    system_path,
                    config_paths["colmap"],
                ),
            )

            self._execute_stage(
                task_id=task_id,
                stage_key="colmap_quality",
                action=lambda: self._run_colmap_quality(
                    system_path,
                    config_paths["colmap"],
                ),
            )

        if flags.run_convert:
            self._execute_stage(
                task_id=task_id,
                stage_key="convert",
                action=lambda: self._run_convert(
                    task_id,
                    system_path,
                    config_paths["convert"],
                ),
            )

        if flags.run_preflight:
            self._execute_stage(
                task_id=task_id,
                stage_key="preflight_processed",
                action=lambda: self._run_preflight(
                    system_path,
                    config_paths["preflight"],
                ),
            )

        if flags.run_train:
            self._execute_stage(
                task_id=task_id,
                stage_key="train",
                action=lambda: self._run_train(
                    task_id,
                    system_path,
                    config_paths["train"],
                ),
            )

        if flags.run_render:
            self._execute_stage(
                task_id=task_id,
                stage_key="render",
                action=lambda: self._run_render(
                    task_id,
                    system_path,
                    config_paths["render"],
                ),
            )

        if flags.run_metrics:
            self._execute_stage(
                task_id=task_id,
                stage_key="metrics",
                action=lambda: self._run_metrics(
                    task_id,
                    system_path,
                    config_paths["metrics"],
                ),
            )

        if flags.run_train or flags.run_render or flags.run_metrics:
            self._execute_stage(
                task_id=task_id,
                stage_key="report",
                action=lambda: self._run_report(
                    system_path,
                    config_paths["report"],
                ),
            )

        if flags.launch_viewer:
            self._execute_stage(
                task_id=task_id,
                stage_key="viewer",
                action=lambda: self._run_viewer(
                    task_id,
                    system_path,
                    config_paths["viewer"],
                ),
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

        except (TaskStoppedError, ImmediateStopRequested) as exc:
            task_store.finish_stage(
                task_id,
                stage_key=stage["key"],
                status="stopped",
                error_type=(
                    "user_force_stop"
                    if isinstance(exc, ImmediateStopRequested)
                    else "user_stop"
                ),
                error_message=str(exc) or "任务已停止",
            )

            raise

        except Exception as exc:
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

        if getattr(task, "force_stop_requested", False):
            raise TaskStoppedError("已收到立即停止请求")

        if task.stop_requested:
            raise TaskStoppedError("已收到停止请求")

    def _stage_meta(self, stage_key: str) -> Dict[str, Any]:
        for item in self.STAGES:
            if item["key"] == stage_key:
                return item

        raise KeyError("未知阶段：{0}".format(stage_key))

    def _classify_error(self, exc: Exception) -> str:
        message = str(exc).lower()

        if isinstance(exc, ImmediateStopRequested):
            return "user_force_stop"

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

    def _read_yaml(self, path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}

        yaml_path = Path(path)

        if not yaml_path.exists():
            return {}

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if isinstance(data, dict):
                return data

        except Exception:
            return {}

        return {}

    def _engine_root(self) -> Path:
        return (self.project_root / "engine").resolve()

    def _resolve_engine_path(self, value: Any) -> Optional[Path]:
        if value is None or value == "":
            return None

        path = Path(str(value))

        if path.is_absolute():
            return path.resolve()

        return (self._engine_root() / path).resolve()

    def _find_file_recursively(self, base_dir: Optional[Path], filename: str) -> Optional[Path]:
        if not base_dir or not base_dir.exists() or not base_dir.is_dir():
            return None

        direct = base_dir / filename

        if direct.exists() and direct.is_file():
            return direct

        try:
            for item in base_dir.rglob(filename):
                if item.is_file():
                    return item
        except Exception:
            return None

        return None

    def _first_existing_file(self, filename: str, *base_dirs: Optional[Path]) -> Optional[Path]:
        for base_dir in base_dirs:
            found = self._find_file_recursively(base_dir, filename)

            if found is not None:
                return found

        return None

    def _merge_metrics(self, *sources: Dict[str, Any]) -> Dict[str, Any]:
        keys = [
            "psnr",
            "ssim",
            "lpips",
            "mse",
            "mae",
            "gaussian_count",
            "latest_iteration",
            "generated_at",
            "metrics_source_file",
        ]
        result: Dict[str, Any] = {}

        for source in sources:
            if not isinstance(source, dict):
                continue

            candidates = [source]

            for nested_key in ("metrics_summary", "metrics", "summary", "result"):
                nested = source.get(nested_key)
                if isinstance(nested, dict):
                    candidates.append(nested)

            for candidate in candidates:
                for key in keys:
                    value = candidate.get(key)
                    if value is not None and value != "" and key not in result:
                        result[key] = value

                alias_pairs = {
                    "psnr": "PSNR",
                    "ssim": "SSIM",
                    "lpips": "LPIPS",
                    "mse": "MSE",
                    "mae": "MAE",
                    "gaussian_count": "num_gaussians",
                    "latest_iteration": "iteration",
                }

                for target, alias in alias_pairs.items():
                    value = candidate.get(alias)
                    if value is not None and value != "" and target not in result:
                        result[target] = value

        return result

    def _resolve_output_dir(self, config_paths: Dict[str, str], scene_name: str) -> Path:
        train_data = self._read_yaml(config_paths.get("train"))
        train_cfg = train_data.get("train", {}) if isinstance(train_data, dict) else {}

        model_output = train_cfg.get("model_output", "")
        resolved = self._resolve_engine_path(model_output)

        if resolved is not None:
            return resolved

        metrics_data = self._read_yaml(config_paths.get("metrics"))
        metrics_cfg = metrics_data.get("metrics", {}) if isinstance(metrics_data, dict) else {}

        model_paths = metrics_cfg.get("model_paths", [])

        if model_paths:
            resolved = self._resolve_engine_path(model_paths[0])
            if resolved is not None:
                return resolved

        report_data = self._read_yaml(config_paths.get("report"))
        report_cfg = report_data.get("report", {}) if isinstance(report_data, dict) else {}

        report_dir = report_cfg.get("report_dir", "")
        resolved = self._resolve_engine_path(report_dir)

        if resolved is not None:
            return resolved

        return (self._engine_root() / "outputs" / scene_name).resolve()

    def _resolve_report_dir(self, config_paths: Dict[str, str], scene_name: str) -> Path:
        report_data = self._read_yaml(config_paths.get("report"))
        report_cfg = report_data.get("report", {}) if isinstance(report_data, dict) else {}

        report_dir = report_cfg.get("report_dir", "")
        resolved = self._resolve_engine_path(report_dir)

        if resolved is not None:
            return resolved

        return self._resolve_output_dir(config_paths, scene_name)

    def _resolve_log_dir(self, config_paths: Dict[str, str], scene_name: str) -> Path:
        report_data = self._read_yaml(config_paths.get("report"))
        report_cfg = report_data.get("report", {}) if isinstance(report_data, dict) else {}

        log_dir = report_cfg.get("log_dir", "")
        resolved = self._resolve_engine_path(log_dir)

        if resolved is not None:
            return resolved

        metrics_data = self._read_yaml(config_paths.get("metrics"))
        metrics_cfg = metrics_data.get("metrics", {}) if isinstance(metrics_data, dict) else {}

        metrics_log_dir = metrics_cfg.get("log_dir", "")
        resolved = self._resolve_engine_path(metrics_log_dir)

        if resolved is not None:
            return resolved

        return (self._engine_root() / "logs" / scene_name).resolve()

    def _resolve_processed_dir(self, config_paths: Dict[str, str], scene_name: str) -> Path:
        report_data = self._read_yaml(config_paths.get("report"))
        report_cfg = report_data.get("report", {}) if isinstance(report_data, dict) else {}

        processed_scene_path = report_cfg.get("processed_scene_path", "")
        resolved = self._resolve_engine_path(processed_scene_path)

        if resolved is not None:
            return resolved

        metrics_data = self._read_yaml(config_paths.get("metrics"))
        metrics_cfg = metrics_data.get("metrics", {}) if isinstance(metrics_data, dict) else {}

        metrics_processed_dir = metrics_cfg.get("processed_scene_path", "")
        resolved = self._resolve_engine_path(metrics_processed_dir)

        if resolved is not None:
            return resolved

        return (self._engine_root() / "datasets" / "processed" / scene_name).resolve()

    def _resolve_source_dir(self, config_paths: Dict[str, str]) -> Optional[Path]:
        train_data = self._read_yaml(config_paths.get("train"))
        train_cfg = train_data.get("train", {}) if isinstance(train_data, dict) else {}
        return self._resolve_engine_path(train_cfg.get("source_path", ""))

    def _resolve_raw_image_dir(self, config_paths: Dict[str, str]) -> Optional[Path]:
        colmap_data = self._read_yaml(config_paths.get("colmap"))
        colmap_cfg = colmap_data.get("colmap", {}) if isinstance(colmap_data, dict) else {}
        return self._resolve_engine_path(
            colmap_cfg.get("raw_image_path") or colmap_cfg.get("image_path") or ""
        )

    def _build_result(
        self,
        task_id: str,
        scene_name: str,
        config_paths: Dict[str, str],
    ) -> Dict[str, Any]:
        output_dir = self._resolve_output_dir(config_paths, scene_name)
        report_dir = self._resolve_report_dir(config_paths, scene_name)
        log_dir = self._resolve_log_dir(config_paths, scene_name)
        processed_dir = self._resolve_processed_dir(config_paths, scene_name)
        source_dir = self._resolve_source_dir(config_paths)
        raw_image_dir = self._resolve_raw_image_dir(config_paths)
        runtime_dir = self._guess_runtime_dir(config_paths) or ""

        search_dirs = [report_dir, output_dir, processed_dir, log_dir]

        metrics_json = self._first_existing_file("metrics.json", report_dir, output_dir)
        report_json = self._first_existing_file("report.json", report_dir, output_dir)
        report_md = self._first_existing_file("report.md", report_dir, output_dir)
        summary_csv = self._first_existing_file("summary.csv", report_dir, output_dir)
        summary_txt = self._first_existing_file("summary.txt", report_dir, output_dir)
        colmap_quality_json = self._first_existing_file("colmap_quality.json", *search_dirs)
        colmap_quality_txt = self._first_existing_file("colmap_quality.txt", *search_dirs)

        metrics_data = self._read_json(metrics_json)
        report_summary = self._read_json(report_json)
        colmap_quality = self._read_json(colmap_quality_json) if colmap_quality_json else {}

        metrics_summary = self._merge_metrics(metrics_data, report_summary)

        if colmap_quality:
            metrics_summary = dict(metrics_summary or {})
            metrics_summary["colmap_registration_rate"] = colmap_quality.get(
                "registration_rate_percent"
            )
            metrics_summary["colmap_registered_images"] = colmap_quality.get(
                "registered_image_count"
            )
            metrics_summary["colmap_input_images"] = colmap_quality.get(
                "input_image_count"
            )
            metrics_summary["colmap_point3d_count"] = colmap_quality.get("point3d_count")
            metrics_summary["colmap_camera_count"] = colmap_quality.get("camera_count")
            metrics_summary["colmap_mean_track_length"] = colmap_quality.get(
                "mean_track_length"
            )
            metrics_summary["colmap_mean_reprojection_error"] = colmap_quality.get(
                "mean_reprojection_error"
            )
            metrics_summary["colmap_quality_level"] = colmap_quality.get("quality_level")

        preview_images = []

        if isinstance(report_summary, dict):
            report_images = report_summary.get("preview_images")
            if isinstance(report_images, list):
                preview_images = [str(item) for item in report_images if item]

        if not preview_images:
            preview_images = self._collect_preview_images(output_dir)

        result_files = {
            "metrics_json": str(metrics_json) if metrics_json and metrics_json.exists() else "",
            "report_json": str(report_json) if report_json and report_json.exists() else "",
            "report_md": str(report_md) if report_md and report_md.exists() else "",
            "summary_csv": str(summary_csv) if summary_csv and summary_csv.exists() else "",
            "summary_txt": str(summary_txt) if summary_txt and summary_txt.exists() else "",
            "colmap_quality_json": (
                str(colmap_quality_json)
                if colmap_quality_json and colmap_quality_json.exists()
                else ""
            ),
            "colmap_quality_txt": (
                str(colmap_quality_txt)
                if colmap_quality_txt and colmap_quality_txt.exists()
                else ""
            ),
        }

        task = task_store.get(task_id)
        stage_history = task.stage_history if task is not None else []

        return {
            "scene_name": scene_name,
            "output_dir": str(output_dir),
            "report_dir": str(report_dir),
            "log_dir": str(log_dir),
            "processed_dir": str(processed_dir),
            "source_dir": str(source_dir) if source_dir else "",
            "raw_image_dir": str(raw_image_dir) if raw_image_dir else "",
            "runtime_dir": runtime_dir,
            "metrics_summary": metrics_summary,
            "report_summary": report_summary,
            "result_files": result_files,
            "preview_images": preview_images,
            "colmap_quality": colmap_quality,
            "stage_history": stage_history,
        }

    def _find_existing_file(self, *paths: Path) -> Optional[Path]:
        for path in paths:
            if path and path.exists() and path.is_file():
                return path

        return None

    def _read_json(self, path: Optional[Path]) -> Dict[str, Any]:
        if not path or not path.exists():
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _collect_preview_images(self, output_dir: Path) -> List[str]:
        if not output_dir.exists():
            return []

        image_files = []

        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            image_files.extend(output_dir.rglob(pattern))

        image_files = sorted(dict.fromkeys(image_files))[:8]

        return [str(item) for item in image_files]

    @staticmethod
    def _run_video(task_id: str, system_path: str, video_path: str) -> None:
        from engine.core.video_service import VideoService

        VideoService(
            system_config_path=system_path,
            video_config_path=video_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_preflight(system_path: str, preflight_path: str) -> None:
        from engine.core.preflight_service import PreflightService

        PreflightService(
            system_config_path=system_path,
            preflight_config_path=preflight_path,
        ).run()

    @staticmethod
    def _run_augmentation(task_id: str, system_path: str, augmentation_path: str) -> None:
        from engine.core.augmentation_service import AugmentationService

        AugmentationService(
            system_config_path=system_path,
            augmentation_config_path=augmentation_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_colmap(task_id: str, system_path: str, colmap_path: str) -> None:
        from engine.core.colmap_service import ColmapService

        ColmapService(
            system_config_path=system_path,
            colmap_config_path=colmap_path,
            task_id=task_id,
        ).run()
        
    @staticmethod
    def _run_colmap_quality(system_path: str, colmap_path: str) -> None:
        from engine.core.colmap_quality_service import ColmapQualityService

        ColmapQualityService(
            system_config_path=system_path,
            colmap_config_path=colmap_path,
        ).run()

    @staticmethod
    def _run_convert(task_id: str, system_path: str, convert_path: str) -> None:
        from engine.core.convert_service import ConvertService

        ConvertService(
            system_config_path=system_path,
            convert_config_path=convert_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_train(task_id: str, system_path: str, train_path: str) -> None:
        from engine.core.train_service import TrainerService

        TrainerService(
            system_config_path=system_path,
            train_config_path=train_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_render(task_id: str, system_path: str, render_path: str) -> None:
        from engine.core.render_service import RenderService

        RenderService(
            system_config_path=system_path,
            render_config_path=render_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_metrics(task_id: str, system_path: str, metrics_path: str) -> None:
        from engine.core.metrics_service import MetricsService

        MetricsService(
            system_config_path=system_path,
            metrics_config_path=metrics_path,
            task_id=task_id,
        ).run()

    @staticmethod
    def _run_report(system_path: str, report_path: str) -> None:
        from engine.core.report_service import ReportService

        ReportService(
            system_config_path=system_path,
            report_config_path=report_path,
        ).run()

    @staticmethod
    def _run_viewer(task_id: str, system_path: str, viewer_path: str) -> None:
        from engine.core.viewer_service import ViewerService

        ViewerService(
            system_config_path=system_path,
            viewer_config_path=viewer_path,
            task_id=task_id,
        ).run()


pipeline_service = PipelineService()