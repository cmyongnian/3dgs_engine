from pathlib import Path
import json
from typing import Any, Dict, Optional, List, Tuple

import yaml
from fastapi import APIRouter, HTTPException

from backend.app.services.task_service import task_service

router = APIRouter()

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
    if not path or not path.exists() or not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_read_yaml(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists() or not path.is_file():
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
    if direct.exists() and direct.is_file():
        return direct

    try:
        for p in base_dir.rglob(filename):
            if p.is_file():
                return p
    except Exception:
        return None

    return None


def _find_preview_images(*base_dirs: Optional[Path]) -> List[str]:
    candidates = []

    for base_dir in base_dirs:
        if not base_dir or not base_dir.exists():
            continue

        preferred_dirs = [
            base_dir / "renders",
            base_dir / "render",
            base_dir / "preview",
            base_dir / "previews",
        ]

        current_candidates = []

        for d in preferred_dirs:
            if d.exists() and d.is_dir():
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    current_candidates.extend(sorted(d.glob(ext)))

        if not current_candidates:
            try:
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    current_candidates.extend(sorted(base_dir.rglob(ext)))
            except Exception:
                current_candidates = []

        candidates.extend(current_candidates)

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


def _pick_value(*sources: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue

        for key in keys:
            if key in source and source[key] not in (None, ""):
                return source[key]

        for nested_key in ("metrics_summary", "metrics", "summary", "result"):
            nested = source.get(nested_key)
            if isinstance(nested, dict):
                for key in keys:
                    if key in nested and nested[key] not in (None, ""):
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

    model_paths = report_cfg.get("model_paths") or metrics_cfg.get("model_paths") or []
    first_model_path = model_paths[0] if model_paths else None

    output_dir = _resolve_engine_path(
        train_cfg.get("model_output")
        or report_cfg.get("report_dir")
        or first_model_path
    )
    report_dir = _resolve_engine_path(
        report_cfg.get("report_dir")
        or first_model_path
    )
    log_dir = _resolve_engine_path(
        report_cfg.get("log_dir")
        or metrics_cfg.get("log_dir")
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
        "report_dir": report_dir,
        "log_dir": log_dir,
        "processed_dir": processed_dir,
        "source_dir": source_dir,
    }


@router.get("/{task_id}")
def get_result(task_id: str):
    task = task_service.get_task(task_id)
    task_data = _task_to_dict(task)
    runtime_meta = _infer_from_runtime(task_id)

    if not task_data and not runtime_meta:
        raise HTTPException(status_code=404, detail="任务不存在，且未找到运行时目录")

    stored_result = task_data.get("result", {}) or {}
    stored_metrics = task_data.get("metrics_summary", {}) or {}
    stored_files = task_data.get("result_files", {}) or {}

    scene_name = (
        task_data.get("scene_name")
        or runtime_meta.get("scene_name")
        or task_id
    )

    output_dir = (
        _resolve_engine_path(stored_result.get("output_dir"))
        or runtime_meta.get("output_dir")
    )
    report_dir = (
        _resolve_engine_path(stored_result.get("report_dir"))
        or runtime_meta.get("report_dir")
        or output_dir
    )
    processed_dir = (
        _resolve_engine_path(stored_result.get("processed_dir"))
        or runtime_meta.get("processed_dir")
    )
    source_dir = (
        _resolve_engine_path(stored_result.get("source_dir"))
        or runtime_meta.get("source_dir")
    )
    raw_image_dir = _resolve_engine_path(stored_result.get("raw_image_dir"))
    runtime_dir = (
        _resolve_project_path(stored_result.get("runtime_dir"))
        or runtime_meta.get("runtime_dir")
    )
    log_dir = (
        _resolve_engine_path(stored_result.get("log_dir"))
        or runtime_meta.get("log_dir")
        or (ENGINE_ROOT / "logs" / scene_name).resolve()
    )

    search_dirs = [report_dir, output_dir]

    metrics_json = None
    report_json = None
    report_md = None
    summary_csv = None
    summary_txt = None

    for base_dir in search_dirs:
        metrics_json = metrics_json or _find_file(base_dir, "metrics.json")
        report_json = report_json or _find_file(base_dir, "report.json")
        report_md = report_md or _find_file(base_dir, "report.md")
        summary_csv = summary_csv or _find_file(base_dir, "summary.csv")
        summary_txt = summary_txt or _find_file(base_dir, "summary.txt")

    metrics_data = _safe_read_json(metrics_json)
    report_data = _safe_read_json(report_json)

    result_files = {
        "metrics_json": stored_files.get("metrics_json") or _existing_str(metrics_json),
        "report_json": stored_files.get("report_json") or _existing_str(report_json),
        "report_md": stored_files.get("report_md") or _existing_str(report_md),
        "summary_csv": stored_files.get("summary_csv") or _existing_str(summary_csv),
        "summary_txt": stored_files.get("summary_txt") or _existing_str(summary_txt),
    }

    metrics_summary = {
        "psnr": stored_metrics.get("psnr") or _pick_value(metrics_data, report_data, stored_result, keys=("psnr", "PSNR")),
        "ssim": stored_metrics.get("ssim") or _pick_value(metrics_data, report_data, stored_result, keys=("ssim", "SSIM")),
        "lpips": stored_metrics.get("lpips") or _pick_value(metrics_data, report_data, stored_result, keys=("lpips", "LPIPS")),
        "mse": stored_metrics.get("mse") or _pick_value(metrics_data, report_data, stored_result, keys=("mse", "MSE")),
        "mae": stored_metrics.get("mae") or _pick_value(metrics_data, report_data, stored_result, keys=("mae", "MAE")),
        "gaussian_count": stored_metrics.get("gaussian_count") or _pick_value(metrics_data, report_data, stored_result, keys=("gaussian_count", "num_gaussians")),
        "latest_iteration": stored_metrics.get("latest_iteration") or _pick_value(metrics_data, report_data, stored_result, keys=("latest_iteration", "iteration")),
        "generated_at": stored_metrics.get("generated_at") or _pick_value(metrics_data, report_data, stored_result, keys=("generated_at", "created_at")),
    }

    preview_images = stored_result.get("preview_images") or _find_preview_images(report_dir, output_dir)

    result_payload = {
        "output_dir": _existing_str(output_dir) or (str(output_dir) if output_dir else None),
        "report_dir": _existing_str(report_dir) or (str(report_dir) if report_dir else None),
        "log_dir": _existing_str(log_dir) or (str(log_dir) if log_dir else None),
        "processed_dir": _existing_str(processed_dir) or (str(processed_dir) if processed_dir else None),
        "runtime_dir": _existing_str(runtime_dir) or (str(runtime_dir) if runtime_dir else None),
        "source_dir": _existing_str(source_dir) or (str(source_dir) if source_dir else None),
        "raw_image_dir": _existing_str(raw_image_dir) or (str(raw_image_dir) if raw_image_dir else None),
        "preview_images": preview_images,
    }

    inferred_status = "success" if any(result_files.values()) else (task_data.get("status") or "unknown")

    return {
        "task_id": task_data.get("task_id", task_id),
        "scene_name": scene_name,
        "status": inferred_status,
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