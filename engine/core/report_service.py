from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import csv
import json
import re

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class ReportService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        report_config_path="configs/report.yaml",
    ):
        self.pm = PathManager(system_config_path)

        report_path = Path(report_config_path)
        if not report_path.is_absolute():
            report_path = self.pm.project_root / report_path

        self.report_config_path = report_path
        self.report_cfg: Dict[str, Any] = {}

        if report_path.exists():
            loaded = load_yaml(str(report_path))
            self.report_cfg = loaded.get("report", {}) or {}

    def _resolve_user_path(self, value: str) -> Path:
        path = Path(value)

        if path.is_absolute():
            return path

        return (self.pm.project_root / path).resolve()

    def _read_json(self, path: Optional[Path]) -> Dict[str, Any]:
        if path is None:
            return {}

        if not path.exists() or not path.is_file():
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return data if isinstance(data, dict) else {}

        except Exception:
            return {}

    def _find_existing_file(self, *paths: Optional[Path]) -> Optional[Path]:
        for path in paths:
            if path and path.exists() and path.is_file():
                return path

        return None

    def _find_file_recursively(
        self,
        base_dir: Optional[Path],
        filename: str,
    ) -> Optional[Path]:
        if base_dir is None:
            return None

        if not base_dir.exists() or not base_dir.is_dir():
            return None

        direct = base_dir / filename

        if direct.exists() and direct.is_file():
            return direct

        try:
            for path in base_dir.rglob(filename):
                if path.is_file():
                    return path

        except Exception:
            return None

        return None

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None

        try:
            return float(value)

        except Exception:
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None

        try:
            return int(value)

        except Exception:
            return None

    def _safe_percent(self, value: Any) -> Optional[float]:
        number = self._safe_float(value)

        if number is None:
            return None

        return round(number, 4)

    def _count_files(self, folder: Optional[Path], patterns: List[str]) -> int:
        if folder is None:
            return 0

        if not folder.exists() or not folder.is_dir():
            return 0

        total = 0

        for pattern in patterns:
            try:
                total += len(list(folder.rglob(pattern)))
            except Exception:
                continue

        return total

    def _find_latest_iteration_dir(
        self,
        model_path: Path,
    ) -> Tuple[Optional[int], Optional[Path]]:
        point_cloud_dir = model_path / "point_cloud"

        if not point_cloud_dir.exists() or not point_cloud_dir.is_dir():
            return None, None

        candidates: List[Tuple[int, Path]] = []

        for item in point_cloud_dir.iterdir():
            if not item.is_dir():
                continue

            match = re.search(r"iteration_(\d+)", item.name)

            if not match:
                continue

            try:
                candidates.append((int(match.group(1)), item))

            except Exception:
                continue

        if not candidates:
            return None, None

        candidates.sort(key=lambda x: x[0])
        return candidates[-1]

    def _count_gaussians_from_ply(self, ply_path: Path) -> Optional[int]:
        if not ply_path.exists() or not ply_path.is_file():
            return None

        try:
            with open(ply_path, "rb") as f:
                for raw_line in f:
                    try:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        continue

                    if line.startswith("element vertex"):
                        parts = line.split()

                        if len(parts) >= 3:
                            return int(parts[2])

                    if line == "end_header":
                        break

        except Exception:
            return None

        return None

    def _collect_preview_images(self, model_path: Path) -> List[str]:
        candidates: List[Path] = []

        preferred_dirs = [
            model_path / "test",
            model_path / "train",
            model_path / "renders",
            model_path / "render",
            model_path / "preview",
            model_path / "previews",
        ]

        image_patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp"]

        for folder in preferred_dirs:
            if not folder.exists() or not folder.is_dir():
                continue

            for pattern in image_patterns:
                try:
                    candidates.extend(folder.rglob(pattern))
                except Exception:
                    continue

        if not candidates:
            for pattern in image_patterns:
                try:
                    candidates.extend(model_path.rglob(pattern))
                except Exception:
                    continue

        unique: List[Path] = []
        seen = set()

        for path in sorted(candidates):
            text = str(path)

            if text in seen:
                continue

            seen.add(text)
            unique.append(path)

            if len(unique) >= 8:
                break

        return [str(path) for path in unique]

    def _collect_render_images(self, model_path: Path) -> Dict[str, Any]:
        image_patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp"]

        test_dir = model_path / "test"
        train_dir = model_path / "train"
        render_dir = model_path / "renders"

        test_count = self._count_files(test_dir, image_patterns)
        train_count = self._count_files(train_dir, image_patterns)
        direct_render_count = self._count_files(render_dir, image_patterns)

        total = test_count + train_count + direct_render_count

        if total == 0:
            total = self._count_files(model_path, image_patterns)

        preview_images = self._collect_preview_images(model_path)

        return {
            "test_render_image_count": test_count,
            "train_render_image_count": train_count,
            "direct_render_image_count": direct_render_count,
            "render_image_count": total,
            "preview_images": preview_images,
        }

    def _find_colmap_quality_files(
        self,
        model_path: Path,
        processed_scene_path: Optional[Path],
        log_dir: Optional[Path],
    ) -> Tuple[Optional[Path], Optional[Path]]:
        quality_json = self._find_existing_file(
            processed_scene_path / "colmap_quality.json" if processed_scene_path else None,
            model_path / "colmap_quality.json",
            log_dir / "colmap_quality.json" if log_dir else None,
        )

        quality_txt = self._find_existing_file(
            processed_scene_path / "colmap_quality.txt" if processed_scene_path else None,
            model_path / "colmap_quality.txt",
            log_dir / "colmap_quality.txt" if log_dir else None,
        )

        if quality_json is None:
            quality_json = (
                self._find_file_recursively(processed_scene_path, "colmap_quality.json")
                or self._find_file_recursively(model_path, "colmap_quality.json")
                or self._find_file_recursively(log_dir, "colmap_quality.json")
            )

        if quality_txt is None:
            quality_txt = (
                self._find_file_recursively(processed_scene_path, "colmap_quality.txt")
                or self._find_file_recursively(model_path, "colmap_quality.txt")
                or self._find_file_recursively(log_dir, "colmap_quality.txt")
            )

        return quality_json, quality_txt

    def _normalize_metrics_summary(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        metrics = raw.get("metrics_summary", raw)

        if not isinstance(metrics, dict):
            metrics = {}

        return {
            "psnr": self._safe_float(metrics.get("psnr") or metrics.get("PSNR")),
            "ssim": self._safe_float(metrics.get("ssim") or metrics.get("SSIM")),
            "lpips": self._safe_float(metrics.get("lpips") or metrics.get("LPIPS")),
            "mse": self._safe_float(metrics.get("mse") or metrics.get("MSE")),
            "mae": self._safe_float(metrics.get("mae") or metrics.get("MAE")),
            "gaussian_count": self._safe_int(
                metrics.get("gaussian_count") or metrics.get("num_gaussians")
            ),
            "latest_iteration": self._safe_int(
                metrics.get("latest_iteration") or metrics.get("iteration")
            ),
            "metrics_source_file": metrics.get("metrics_source_file", ""),
            "generated_at": metrics.get("generated_at", ""),
        }

    def _build_training_summary(self, model_path: Path) -> Dict[str, Any]:
        latest_iteration, latest_dir = self._find_latest_iteration_dir(model_path)

        ply_path = latest_dir / "point_cloud.ply" if latest_dir else None
        gaussian_count = self._count_gaussians_from_ply(ply_path) if ply_path else None

        checkpoint_files = sorted(model_path.glob("chkpnt*.pth"))

        return {
            "model_path": str(model_path),
            "latest_iteration": latest_iteration,
            "latest_iteration_dir": str(latest_dir) if latest_dir else "",
            "point_cloud_ply": str(ply_path) if ply_path and ply_path.exists() else "",
            "gaussian_count": gaussian_count,
            "checkpoint_count": len(checkpoint_files),
            "checkpoint_files": [str(path) for path in checkpoint_files],
            "has_point_cloud": bool(ply_path and ply_path.exists()),
        }

    def _build_data_summary(
        self,
        processed_scene_path: Optional[Path],
        source_path: Optional[Path],
    ) -> Dict[str, Any]:
        image_patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff"]

        processed_image_count = self._count_files(processed_scene_path, image_patterns)

        source_image_dir = source_path / "images" if source_path else None
        source_image_count = self._count_files(source_image_dir, image_patterns)

        sparse_zero = source_path / "sparse" / "0" if source_path else None

        has_sparse_bin = False
        has_sparse_txt = False

        if sparse_zero and sparse_zero.exists():
            has_sparse_bin = all(
                (sparse_zero / name).exists()
                for name in ["cameras.bin", "images.bin", "points3D.bin"]
            )

            has_sparse_txt = all(
                (sparse_zero / name).exists()
                for name in ["cameras.txt", "images.txt", "points3D.txt"]
            )

        return {
            "processed_scene_path": str(processed_scene_path) if processed_scene_path else "",
            "source_path": str(source_path) if source_path else "",
            "source_images_dir": str(source_image_dir) if source_image_dir else "",
            "processed_image_count": processed_image_count,
            "source_image_count": source_image_count,
            "sparse_zero_path": str(sparse_zero) if sparse_zero else "",
            "has_sparse_bin": has_sparse_bin,
            "has_sparse_txt": has_sparse_txt,
            "has_sparse_model": has_sparse_bin or has_sparse_txt,
        }

    def _build_quality_conclusion(
        self,
        colmap_quality: Dict[str, Any],
        training_summary: Dict[str, Any],
        render_summary: Dict[str, Any],
        metrics_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        suggestions: List[str] = []
        conclusions: List[str] = []

        registration_rate = self._safe_float(
            colmap_quality.get("registration_rate_percent")
            or colmap_quality.get("registration_rate")
        )

        registered_images = self._safe_int(colmap_quality.get("registered_image_count"))
        input_images = self._safe_int(colmap_quality.get("input_image_count"))
        point3d_count = self._safe_int(colmap_quality.get("point3d_count"))
        reprojection_error = self._safe_float(colmap_quality.get("mean_reprojection_error"))

        quality_level = str(colmap_quality.get("quality_level") or "")

        if registration_rate is not None:
            conclusions.append(
                "COLMAP 图像注册率为 {0:.2f}%。".format(registration_rate)
            )

            if registration_rate >= 90:
                conclusions.append("图像注册率较高，相机位姿估计整体可靠。")
            elif registration_rate >= 70:
                conclusions.append("图像注册率中等，后续训练可继续，但建议检查未注册图像。")
                suggestions.append("补充更多重叠视角图像，或删除模糊、重复、纹理不足的图像。")
            else:
                conclusions.append("图像注册率偏低，可能影响后续 3DGS 训练质量。")
                suggestions.append("重新采集图像或视频，提高相邻帧重叠率和场景纹理丰富度。")

        if input_images is not None and registered_images is not None:
            conclusions.append(
                "输入图像 {0} 张，成功注册 {1} 张。".format(input_images, registered_images)
            )

        if point3d_count is not None:
            conclusions.append("稀疏点云数量为 {0}。".format(point3d_count))

            if point3d_count < 10000:
                suggestions.append("稀疏点数量偏少，建议增加图像数量或提升图像清晰度。")

        if reprojection_error is not None:
            conclusions.append(
                "平均重投影误差为 {0:.4f}。".format(reprojection_error)
            )

            if reprojection_error > 2.0:
                suggestions.append("平均重投影误差偏高，建议检查相机运动模糊和动态物体干扰。")

        latest_iteration = training_summary.get("latest_iteration")
        gaussian_count = training_summary.get("gaussian_count")

        if latest_iteration:
            conclusions.append("3DGS 训练已生成 iteration_{0} 结果。".format(latest_iteration))
        else:
            suggestions.append("未检测到训练迭代结果，请检查训练阶段是否完整完成。")

        if gaussian_count:
            conclusions.append("模型包含 Gaussian 数量 {0}。".format(gaussian_count))

        render_count = render_summary.get("render_image_count")

        if render_count:
            conclusions.append("已生成渲染图像 {0} 张。".format(render_count))
        else:
            suggestions.append("未检测到渲染图像，若需要可开启离线渲染阶段。")

        psnr = self._safe_float(metrics_summary.get("psnr"))
        ssim = self._safe_float(metrics_summary.get("ssim"))
        lpips = self._safe_float(metrics_summary.get("lpips"))

        if psnr is not None:
            conclusions.append("PSNR 为 {0:.4f}。".format(psnr))

            if psnr < 20:
                suggestions.append("PSNR 偏低，可尝试增加训练迭代次数或提高输入图像质量。")

        if ssim is not None:
            conclusions.append("SSIM 为 {0:.4f}。".format(ssim))

        if lpips is not None:
            conclusions.append("LPIPS 为 {0:.4f}。".format(lpips))

        if quality_level:
            conclusions.append("COLMAP 质量等级为：{0}。".format(quality_level))

        if not suggestions:
            suggestions.append("当前重建流程整体正常，可继续进行结果展示、截图和论文实验分析。")

        return {
            "overall_conclusion": " ".join(conclusions) if conclusions else "当前报告已生成，但可用结果信息较少。",
            "suggestions": suggestions,
        }

    def _build_single_report(
        self,
        scene_name: str,
        model_path: Path,
        processed_scene_path: Optional[Path],
        log_dir: Optional[Path],
        report_dir: Path,
    ) -> Dict[str, Any]:
        metrics_json = self._find_existing_file(
            model_path / "metrics.json",
            report_dir / "metrics.json",
        )

        metrics_summary = self._normalize_metrics_summary(self._read_json(metrics_json))

        training_summary = self._build_training_summary(model_path)

        if metrics_summary.get("gaussian_count") is None:
            metrics_summary["gaussian_count"] = training_summary.get("gaussian_count")

        if metrics_summary.get("latest_iteration") is None:
            metrics_summary["latest_iteration"] = training_summary.get("latest_iteration")

        source_path = None

        if processed_scene_path is not None:
            candidate_source_path = processed_scene_path / "gs_input"

            if candidate_source_path.exists():
                source_path = candidate_source_path

        data_summary = self._build_data_summary(
            processed_scene_path=processed_scene_path,
            source_path=source_path,
        )

        render_summary = self._collect_render_images(model_path)

        colmap_quality_json, colmap_quality_txt = self._find_colmap_quality_files(
            model_path=model_path,
            processed_scene_path=processed_scene_path,
            log_dir=log_dir,
        )

        colmap_quality = self._read_json(colmap_quality_json)

        conclusion_data = self._build_quality_conclusion(
            colmap_quality=colmap_quality,
            training_summary=training_summary,
            render_summary=render_summary,
            metrics_summary=metrics_summary,
        )

        log_files: List[str] = []

        if log_dir and log_dir.exists():
            try:
                log_files = [str(path) for path in sorted(log_dir.glob("*.log"))]
            except Exception:
                log_files = []

        result_files = {
            "metrics_json": str(metrics_json) if metrics_json and metrics_json.exists() else "",
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
            "report_json": "",
            "report_md": "",
            "summary_csv": "",
            "summary_txt": "",
        }

        return {
            "scene_name": scene_name,
            "model_path": str(model_path),
            "processed_scene_path": str(processed_scene_path) if processed_scene_path else "",
            "log_dir": str(log_dir) if log_dir else "",
            "report_dir": str(report_dir),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data_summary": data_summary,
            "colmap_quality": colmap_quality,
            "training_summary": training_summary,
            "render_summary": render_summary,
            "metrics_summary": metrics_summary,
            "overall_conclusion": conclusion_data["overall_conclusion"],
            "suggestions": conclusion_data["suggestions"],
            "preview_images": render_summary.get("preview_images", []),
            "log_files": log_files,
            "result_files": result_files,
        }

    def _write_report_json(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "report.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path

    def _write_report_md(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "report.md"

        metrics = data.get("metrics_summary", {})
        colmap = data.get("colmap_quality", {})
        train = data.get("training_summary", {})
        render = data.get("render_summary", {})
        data_summary = data.get("data_summary", {})

        lines = [
            "# 3D Gaussian Splatting 三维重建任务报告",
            "",
            "## 1. 基本信息",
            "",
            "- 场景名称：{0}".format(data.get("scene_name", "")),
            "- 模型目录：{0}".format(data.get("model_path", "")),
            "- 处理数据目录：{0}".format(data.get("processed_scene_path", "")),
            "- 日志目录：{0}".format(data.get("log_dir", "")),
            "- 报告目录：{0}".format(data.get("report_dir", "")),
            "- 生成时间：{0}".format(data.get("generated_at", "")),
            "",
            "## 2. 数据与 sparse 结构",
            "",
            "- 处理后图像数量：{0}".format(data_summary.get("processed_image_count")),
            "- 训练输入图像数量：{0}".format(data_summary.get("source_image_count")),
            "- sparse/0 路径：{0}".format(data_summary.get("sparse_zero_path", "")),
            "- 是否存在 sparse 模型：{0}".format("是" if data_summary.get("has_sparse_model") else "否"),
            "",
            "## 3. COLMAP 重建质量",
            "",
            "- 输入图像数量：{0}".format(colmap.get("input_image_count")),
            "- 注册图像数量：{0}".format(colmap.get("registered_image_count")),
            "- 图像注册率：{0}%".format(colmap.get("registration_rate_percent")),
            "- 相机数量：{0}".format(colmap.get("camera_count")),
            "- 稀疏点数量：{0}".format(colmap.get("point3d_count")),
            "- 平均观测数：{0}".format(colmap.get("mean_track_length")),
            "- 平均重投影误差：{0}".format(colmap.get("mean_reprojection_error")),
            "- 质量等级：{0}".format(colmap.get("quality_level")),
            "- 是否建议继续：{0}".format("是" if colmap.get("can_continue") else "否"),
            "",
            "## 4. 训练结果",
            "",
            "- 最新迭代次数：{0}".format(train.get("latest_iteration")),
            "- Gaussian 数量：{0}".format(train.get("gaussian_count")),
            "- 点云文件：{0}".format(train.get("point_cloud_ply", "")),
            "- checkpoint 数量：{0}".format(train.get("checkpoint_count")),
            "",
            "## 5. 渲染结果",
            "",
            "- 渲染图像总数：{0}".format(render.get("render_image_count")),
            "- test 渲染图像数：{0}".format(render.get("test_render_image_count")),
            "- train 渲染图像数：{0}".format(render.get("train_render_image_count")),
            "",
            "## 6. 评价指标",
            "",
            "- PSNR：{0}".format(metrics.get("psnr")),
            "- SSIM：{0}".format(metrics.get("ssim")),
            "- LPIPS：{0}".format(metrics.get("lpips")),
            "- MSE：{0}".format(metrics.get("mse")),
            "- MAE：{0}".format(metrics.get("mae")),
            "",
            "## 7. 自动结论",
            "",
            data.get("overall_conclusion", ""),
            "",
            "## 8. 优化建议",
            "",
        ]

        suggestions = data.get("suggestions", [])

        if suggestions:
            for item in suggestions:
                lines.append("- {0}".format(item))
        else:
            lines.append("- 暂无额外建议。")

        preview_images = data.get("preview_images", [])

        if preview_images:
            lines.extend(["", "## 9. 预览图像", ""])

            for item in preview_images:
                lines.append("- {0}".format(item))

        result_files = data.get("result_files", {})

        lines.extend(
            [
                "",
                "## 10. 结果文件",
                "",
                "- metrics.json：{0}".format(result_files.get("metrics_json", "")),
                "- colmap_quality.json：{0}".format(result_files.get("colmap_quality_json", "")),
                "- colmap_quality.txt：{0}".format(result_files.get("colmap_quality_txt", "")),
                "- report.json：{0}".format(result_files.get("report_json", "")),
                "- report.md：{0}".format(result_files.get("report_md", "")),
                "- summary.csv：{0}".format(result_files.get("summary_csv", "")),
                "- summary.txt：{0}".format(result_files.get("summary_txt", "")),
            ]
        )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path

    def _write_summary_csv(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "summary.csv"

        metrics = data.get("metrics_summary", {})
        colmap = data.get("colmap_quality", {})
        train = data.get("training_summary", {})
        render = data.get("render_summary", {})

        rows = [
            ["scene_name", data.get("scene_name", "")],
            ["model_path", data.get("model_path", "")],
            ["processed_scene_path", data.get("processed_scene_path", "")],
            ["log_dir", data.get("log_dir", "")],
            ["generated_at", data.get("generated_at", "")],
            ["colmap_input_image_count", colmap.get("input_image_count")],
            ["colmap_registered_image_count", colmap.get("registered_image_count")],
            ["colmap_registration_rate_percent", colmap.get("registration_rate_percent")],
            ["colmap_camera_count", colmap.get("camera_count")],
            ["colmap_point3d_count", colmap.get("point3d_count")],
            ["colmap_mean_track_length", colmap.get("mean_track_length")],
            ["colmap_mean_reprojection_error", colmap.get("mean_reprojection_error")],
            ["colmap_quality_level", colmap.get("quality_level")],
            ["latest_iteration", train.get("latest_iteration")],
            ["gaussian_count", train.get("gaussian_count")],
            ["checkpoint_count", train.get("checkpoint_count")],
            ["render_image_count", render.get("render_image_count")],
            ["psnr", metrics.get("psnr")],
            ["ssim", metrics.get("ssim")],
            ["lpips", metrics.get("lpips")],
            ["mse", metrics.get("mse")],
            ["mae", metrics.get("mae")],
            ["overall_conclusion", data.get("overall_conclusion", "")],
            ["suggestions", "；".join(data.get("suggestions", []))],
        ]

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "value"])
            writer.writerows(rows)

        return path

    def _write_summary_txt(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "summary.txt"

        metrics = data.get("metrics_summary", {})
        colmap = data.get("colmap_quality", {})
        train = data.get("training_summary", {})
        render = data.get("render_summary", {})

        lines = [
            "场景名称: {0}".format(data.get("scene_name", "")),
            "模型目录: {0}".format(data.get("model_path", "")),
            "处理数据目录: {0}".format(data.get("processed_scene_path", "")),
            "日志目录: {0}".format(data.get("log_dir", "")),
            "生成时间: {0}".format(data.get("generated_at", "")),
            "",
            "[COLMAP 重建质量]",
            "输入图像数量: {0}".format(colmap.get("input_image_count")),
            "注册图像数量: {0}".format(colmap.get("registered_image_count")),
            "图像注册率: {0}%".format(colmap.get("registration_rate_percent")),
            "相机数量: {0}".format(colmap.get("camera_count")),
            "稀疏点数量: {0}".format(colmap.get("point3d_count")),
            "平均重投影误差: {0}".format(colmap.get("mean_reprojection_error")),
            "质量等级: {0}".format(colmap.get("quality_level")),
            "",
            "[训练结果]",
            "最新迭代次数: {0}".format(train.get("latest_iteration")),
            "Gaussian 数量: {0}".format(train.get("gaussian_count")),
            "checkpoint 数量: {0}".format(train.get("checkpoint_count")),
            "",
            "[渲染结果]",
            "渲染图像总数: {0}".format(render.get("render_image_count")),
            "",
            "[评价指标]",
            "PSNR: {0}".format(metrics.get("psnr")),
            "SSIM: {0}".format(metrics.get("ssim")),
            "LPIPS: {0}".format(metrics.get("lpips")),
            "MSE: {0}".format(metrics.get("mse")),
            "MAE: {0}".format(metrics.get("mae")),
            "",
            "[自动结论]",
            data.get("overall_conclusion", ""),
            "",
            "[优化建议]",
        ]

        suggestions = data.get("suggestions", [])

        if suggestions:
            for item in suggestions:
                lines.append("- {0}".format(item))
        else:
            lines.append("- 暂无额外建议。")

        preview_images = data.get("preview_images", [])

        if preview_images:
            lines.extend(["", "[预览图像]"])

            for item in preview_images:
                lines.append("- {0}".format(item))

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path

    def run(self):
        scene_name = self.report_cfg.get("scene_name", "")
        model_paths_cfg = self.report_cfg.get("model_paths", [])
        processed_scene_path_cfg = self.report_cfg.get("processed_scene_path", "")
        log_dir_cfg = self.report_cfg.get("log_dir", "")
        report_dir_cfg = self.report_cfg.get("report_dir", "")
        quiet = self.report_cfg.get("quiet", False)

        if not model_paths_cfg:
            raise ValueError("report.yaml 中 model_paths 不能为空")

        resolved_model_paths = [self._resolve_user_path(str(path)) for path in model_paths_cfg]

        processed_scene_path = (
            self._resolve_user_path(str(processed_scene_path_cfg))
            if processed_scene_path_cfg
            else None
        )

        log_dir = (
            self._resolve_user_path(str(log_dir_cfg))
            if log_dir_cfg
            else None
        )

        if not scene_name:
            scene_name = resolved_model_paths[0].name

        if log_dir is None:
            log_dir = self.pm.scene_log(scene_name)

        log_dir.mkdir(parents=True, exist_ok=True)

        report_dir = (
            self._resolve_user_path(str(report_dir_cfg))
            if report_dir_cfg
            else None
        )

        log_file = log_dir / "report.log"
        logger = setup_logger(str(log_file))

        logger.info("开始生成增强版结果报告")
        logger.info("场景名称: %s", scene_name)
        logger.info("模型目录列表: %s", ", ".join([str(path) for path in resolved_model_paths]))
        logger.info("处理数据目录: %s", processed_scene_path)
        logger.info("日志目录: %s", log_dir)

        if not quiet:
            print("开始生成增强版结果报告: {0}".format(scene_name))

        for model_path in resolved_model_paths:
            if not model_path.exists():
                raise FileNotFoundError("模型目录不存在: {0}".format(model_path))

            target_dir = report_dir if report_dir is not None else model_path
            target_dir.mkdir(parents=True, exist_ok=True)

            report_data = self._build_single_report(
                scene_name=scene_name,
                model_path=model_path,
                processed_scene_path=processed_scene_path,
                log_dir=log_dir,
                report_dir=target_dir,
            )

            report_json = self._write_report_json(target_dir, report_data)
            report_md = self._write_report_md(target_dir, report_data)
            summary_csv = self._write_summary_csv(target_dir, report_data)
            summary_txt = self._write_summary_txt(target_dir, report_data)

            report_data["result_files"]["report_json"] = str(report_json)
            report_data["result_files"]["report_md"] = str(report_md)
            report_data["result_files"]["summary_csv"] = str(summary_csv)
            report_data["result_files"]["summary_txt"] = str(summary_txt)

            report_json = self._write_report_json(target_dir, report_data)
            report_md = self._write_report_md(target_dir, report_data)
            summary_csv = self._write_summary_csv(target_dir, report_data)
            summary_txt = self._write_summary_txt(target_dir, report_data)

            logger.info("已写入 report.json: %s", report_json)
            logger.info("已写入 report.md: %s", report_md)
            logger.info("已写入 summary.csv: %s", summary_csv)
            logger.info("已写入 summary.txt: %s", summary_txt)

            if not quiet:
                print("已写入 report.json: {0}".format(report_json))
                print("已写入 report.md: {0}".format(report_md))
                print("已写入 summary.csv: {0}".format(summary_csv))
                print("已写入 summary.txt: {0}".format(summary_txt))

        logger.info("增强版结果报告生成完成")

        if not quiet:
            print("增强版结果报告生成完成")