from pathlib import Path
import json
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException

from backend.app.services.pipeline_service import pipeline_service

router = APIRouter(prefix="/results", tags=["结果"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENGINE_ROOT = PROJECT_ROOT / "engine"
BACKEND_RUNTIME_ROOT = PROJECT_ROOT / "backend" / "runtime"


def _task_to_dict(task: Any) -> Dict[str, Any]:
    if task is None:
        return {}
    if hasattr(task, "model_dump"):
        return task.model_dump()
    if hasattr(task, "dict"):
        return task.dict()
    if isinstance(task, dict):
        return task
    return {}


def _safe_read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _safe_read_yaml(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_engine_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    p = Path(str(value))
    if p.is_absolute():
        return p
    return (ENGINE_ROOT / p).resolve()


def _resolve_project_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    p = Path(str(value))
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


def _existing_str(path: Optional[Path]) -> Optional[str]:
    if path and path.exists():
        return str(path)
    return None


def _find_file(base_dir: Optional[Path], filename: str) -> Optional[Path]:
    if not base_dir or not base_dir.exists():
        return None

    direct = base_dir / filename
    if direct.exists():
        return direct

    try:
        for p in base_dir.rglob(filename):
            if p.is_file():
                return p
    except Exception:
        return None

    return None


def _find_preview_images(output_dir: Optional[Path]) -> list[str]:
    if not output_dir or not output_dir.exists():
        return []

    candidates = []

    preferred_dirs = [
        output_dir / "renders",
        output_dir / "render",
        output_dir / "preview",
        output_dir / "previews",
    ]

    for d in preferred_dirs:
        if d.exists() and d.is_dir():
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                candidates.extend(sorted(d.glob(ext)))

    if not candidates:
        try:
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                candidates.extend(sorted(output_dir.rglob(ext)))
        except Exception:
            return []

    seen = set()
    result = []
    for p in candidates:
        s = str(p)
        if s not in seen:
            seen.add(s)
            result.append(s)
        if len(result) >= 8:
            break

    return result


def _pick_value(metrics_data: Dict[str, Any], report_data: Dict[str, Any], *keys: str) -> Any:
    for source in (metrics_data, report_data):
        if not isinstance(source, dict):
            continue

        for key in keys:
            if key in source:
                return source[key]

        for nested_key in ("metrics_summary", "metrics", "summary", "result"):
            nested = source.get(nested_key)
            if isinstance(nested, dict):
                for key in keys:
                    if key in nested:
                        return nested[key]

    return None


def _infer_from_runtime(task_id: str) -> Dict[str, Any]:
    runtime_dir = (BACKEND_RUNTIME_ROOT / task_id).resolve()
    if not runtime_dir.exists():
        return {}

    train_yaml = _safe_read_yaml(runtime_dir / "train.yaml")
    report_yaml = _safe_read_yaml(runtime_dir / "report.yaml")
    metrics_yaml = _safe_read_yaml(runtime_dir / "metrics.yaml")

    train_cfg = train_yaml.get("train", {})
    report_cfg = report_yaml.get("report", {})
    metrics_cfg = metrics_yaml.get("metrics", {})

    scene_name = (
        train_cfg.get("scene_name")
        or report_cfg.get("scene_name")
        or metrics_cfg.get("scene_name")
        or task_id
    )

    output_dir = _resolve_engine_path(
        train_cfg.get("model_output")
        or report_cfg.get("report_dir")
        or metrics_cfg.get("render_dir")
    )

    processed_dir = _resolve_engine_path(
        report_cfg.get("processed_scene_path")
        or metrics_cfg.get("processed_scene_path")
    )

    source_dir = _resolve_engine_path(train_cfg.get("source_path"))

    return {
        "runtime_dir": runtime_dir,
        "scene_name": scene_name,
        "output_dir": output_dir,
        "processed_dir": processed_dir,
        "source_dir": source_dir,
    }


@router.get("/{task_id}")
def get_result(task_id: str):
    task = pipeline_service.get_task(task_id)
    task_data = _task_to_dict(task)

    runtime_meta = _infer_from_runtime(task_id)

    if not task_data and not runtime_meta:
        raise HTTPException(status_code=404, detail="任务不存在，且未找到运行时目录")

    scene = task_data.get("scene", {}) or {}
    runtime_files = task_data.get("runtime_files", {}) or {}

    scene_name = (
        task_data.get("scene_name")
        or scene.get("scene_name")
        or runtime_meta.get("scene_name")
        or task_id
    )

    output_dir = (
        _resolve_engine_path(scene.get("model_output"))
        or runtime_meta.get("output_dir")
    )
    processed_dir = (
        _resolve_engine_path(scene.get("processed_scene_path"))
        or runtime_meta.get("processed_dir")
    )
    source_dir = (
        _resolve_engine_path(scene.get("source_path"))
        or runtime_meta.get("source_dir")
    )
    raw_image_dir = _resolve_engine_path(scene.get("raw_image_path"))

    runtime_dir = (
        _resolve_project_path(runtime_files.get("runtime_dir"))
        or runtime_meta.get("runtime_dir")
    )
    log_dir = (ENGINE_ROOT / "logs" / scene_name).resolve()

    metrics_json = _find_file(output_dir, "metrics.json")
    report_json = _find_file(output_dir, "report.json")
    report_md = _find_file(output_dir, "report.md")
    summary_csv = _find_file(output_dir, "summary.csv")
    summary_txt = _find_file(output_dir, "summary.txt")

    metrics_data = _safe_read_json(metrics_json)
    report_data = _safe_read_json(report_json)

    result_files = {
        "metrics_json": _existing_str(metrics_json),
        "report_json": _existing_str(report_json),
        "report_md": _existing_str(report_md),
        "summary_csv": _existing_str(summary_csv),
        "summary_txt": _existing_str(summary_txt),
    }

    metrics_summary = {
        "psnr": _pick_value(metrics_data, report_data, "psnr", "PSNR"),
        "ssim": _pick_value(metrics_data, report_data, "ssim", "SSIM"),
        "lpips": _pick_value(metrics_data, report_data, "lpips", "LPIPS"),
        "mse": _pick_value(metrics_data, report_data, "mse", "MSE"),
        "mae": _pick_value(metrics_data, report_data, "mae", "MAE"),
        "gaussian_count": _pick_value(metrics_data, report_data, "gaussian_count", "num_gaussians"),
        "latest_iteration": _pick_value(metrics_data, report_data, "latest_iteration", "iteration"),
        "generated_at": _pick_value(metrics_data, report_data, "generated_at", "created_at"),
    }

    result_payload = {
        "output_dir": _existing_str(output_dir) or (str(output_dir) if output_dir else None),
        "log_dir": _existing_str(log_dir) or str(log_dir),
        "processed_dir": _existing_str(processed_dir) or (str(processed_dir) if processed_dir else None),
        "runtime_dir": _existing_str(runtime_dir) or (str(runtime_dir) if runtime_dir else None),
        "source_dir": _existing_str(source_dir) or (str(source_dir) if source_dir else None),
        "raw_image_dir": _existing_str(raw_image_dir) or (str(raw_image_dir) if raw_image_dir else None),
        "preview_images": _find_preview_images(output_dir),
    }

    inferred_status = "success" if any(result_files.values()) else "unknown"

    return {
        "task_id": task_data.get("task_id", task_id),
        "scene_name": scene_name,
        "status": task_data.get("status", inferred_status),
        "current_stage": task_data.get("current_stage", "结果查看"),
        "retry_count": task_data.get("retry_count", 0),
        "stop_requested": task_data.get("stop_requested", False),
        "message": task_data.get("message", "结果已从磁盘恢复"),
        "error": task_data.get("error"),
        "created_at": task_data.get("created_at"),
        "started_at": task_data.get("started_at"),
        "finished_at": task_data.get("finished_at"),
        "stage_history": task_data.get("stage_history", []),
        "metrics_summary": metrics_summary,
        "result_files": result_files,
        "result": result_payload,
    }