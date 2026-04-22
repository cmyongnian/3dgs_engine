from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import csv
import json

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class ReportService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        report_config_path="configs/report.yaml"
    ):
        self.pm = PathManager(system_config_path)

        report_path = Path(report_config_path)
        if not report_path.is_absolute():
            report_path = self.pm.project_root / report_path

        self.report_cfg = {}
        if report_path.exists():
            loaded = load_yaml(str(report_path))
            self.report_cfg = loaded.get("report", {})
        self.report_config_path = report_path

    def _resolve_user_path(self, p: str) -> Path:
        path = Path(p)
        if path.is_absolute():
            return path
        return (self.pm.project_root / path).resolve()

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _collect_preview_images(self, model_path: Path) -> List[str]:
        image_files = []
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            image_files.extend(model_path.rglob(pattern))
        image_files = sorted(set(image_files))[:6]
        return [str(p) for p in image_files]

    def _find_latest_iteration_dir(self, model_path: Path) -> Tuple[Optional[int], Optional[Path]]:
        point_cloud_dir = model_path / "point_cloud"
        if not point_cloud_dir.exists():
            return None, None

        candidates = []
        for item in point_cloud_dir.iterdir():
            if item.is_dir() and item.name.startswith("iteration_"):
                try:
                    num = int(item.name.split("iteration_")[-1])
                    candidates.append((num, item))
                except Exception:
                    continue

        if not candidates:
            return None, None

        candidates.sort(key=lambda x: x[0])
        return candidates[-1]

    def _count_gaussians(self, model_path: Path) -> Optional[int]:
        latest_iteration, latest_dir = self._find_latest_iteration_dir(model_path)
        if latest_iteration is None or latest_dir is None:
            return None

        ply_path = latest_dir / "point_cloud.ply"
        if not ply_path.exists():
            return None

        try:
            with open(ply_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("element vertex"):
                        parts = line.split()
                        if len(parts) == 3:
                            return int(parts[2])
                    if line == "end_header":
                        break
        except Exception:
            return None

        return None

    def _count_files(self, folder: Path, patterns: List[str]) -> int:
        if not folder.exists():
            return 0

        total = 0
        for pattern in patterns:
            total += len(list(folder.rglob(pattern)))
        return total

    def _build_single_report(
        self,
        scene_name: str,
        model_path: Path,
        processed_scene_path: Optional[Path],
        log_dir: Optional[Path],
        report_dir: Optional[Path],
    ) -> Dict[str, Any]:
        metrics_json = model_path / "metrics.json"
        metrics_summary = self._read_json(metrics_json)

        latest_iteration, _ = self._find_latest_iteration_dir(model_path)
        gaussian_count = self._count_gaussians(model_path)
        preview_images = self._collect_preview_images(model_path)

        image_count = 0
        if processed_scene_path is not None:
            image_count = self._count_files(
                processed_scene_path,
                ["*.png", "*.jpg", "*.jpeg", "*.webp"]
            )

        log_file = None
        if log_dir is not None:
            candidates = sorted(log_dir.glob("*.log"))
            if candidates:
                log_file = str(candidates[-1])

        report = {
            "scene_name": scene_name,
            "model_path": str(model_path),
            "processed_scene_path": str(processed_scene_path) if processed_scene_path else "",
            "log_dir": str(log_dir) if log_dir else "",
            "report_dir": str(report_dir) if report_dir else "",
            "metrics_json": str(metrics_json) if metrics_json.exists() else "",
            "latest_iteration": latest_iteration,
            "gaussian_count": gaussian_count,
            "image_count": image_count,
            "preview_images": preview_images,
            "metrics_summary": {
                "psnr": metrics_summary.get("psnr"),
                "ssim": metrics_summary.get("ssim"),
                "lpips": metrics_summary.get("lpips"),
                "mse": metrics_summary.get("mse"),
                "mae": metrics_summary.get("mae"),
            },
            "log_file": log_file or "",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        return report

    def _write_report_json(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "report.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def _write_report_md(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "report.md"
        metrics = data.get("metrics_summary", {})

        lines = [
            "# 三维重建任务报告",
            "",
            "## 基本信息",
            "",
            "- 场景名称：{0}".format(data.get("scene_name", "")),
            "- 模型目录：{0}".format(data.get("model_path", "")),
            "- 处理数据目录：{0}".format(data.get("processed_scene_path", "")),
            "- 日志目录：{0}".format(data.get("log_dir", "")),
            "- 生成时间：{0}".format(data.get("generated_at", "")),
            "",
            "## 模型信息",
            "",
            "- 最新迭代：{0}".format(data.get("latest_iteration")),
            "- Gaussian 数量：{0}".format(data.get("gaussian_count")),
            "- 图像数量：{0}".format(data.get("image_count")),
            "",
            "## 评价指标",
            "",
            "- PSNR：{0}".format(metrics.get("psnr")),
            "- SSIM：{0}".format(metrics.get("ssim")),
            "- LPIPS：{0}".format(metrics.get("lpips")),
            "- MSE：{0}".format(metrics.get("mse")),
            "- MAE：{0}".format(metrics.get("mae")),
            "",
            "## 结果文件",
            "",
            "- metrics.json：{0}".format(data.get("metrics_json", "")),
            "- 日志文件：{0}".format(data.get("log_file", "")),
        ]

        preview_images = data.get("preview_images", [])
        if preview_images:
            lines.extend(["", "## 预览图像", ""])
            for item in preview_images:
                lines.append("- {0}".format(item))

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _write_summary_csv(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "summary.csv"
        metrics = data.get("metrics_summary", {})

        rows = [
            ["scene_name", data.get("scene_name", "")],
            ["model_path", data.get("model_path", "")],
            ["processed_scene_path", data.get("processed_scene_path", "")],
            ["log_dir", data.get("log_dir", "")],
            ["latest_iteration", data.get("latest_iteration")],
            ["gaussian_count", data.get("gaussian_count")],
            ["image_count", data.get("image_count")],
            ["psnr", metrics.get("psnr")],
            ["ssim", metrics.get("ssim")],
            ["lpips", metrics.get("lpips")],
            ["mse", metrics.get("mse")],
            ["mae", metrics.get("mae")],
            ["metrics_json", data.get("metrics_json", "")],
            ["log_file", data.get("log_file", "")],
            ["generated_at", data.get("generated_at", "")],
        ]

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "value"])
            writer.writerows(rows)
        return path

    def _write_summary_txt(self, target_dir: Path, data: Dict[str, Any]) -> Path:
        path = target_dir / "summary.txt"
        metrics = data.get("metrics_summary", {})

        lines = [
            "场景名称: {0}".format(data.get("scene_name", "")),
            "模型目录: {0}".format(data.get("model_path", "")),
            "处理数据目录: {0}".format(data.get("processed_scene_path", "")),
            "日志目录: {0}".format(data.get("log_dir", "")),
            "最新迭代: {0}".format(data.get("latest_iteration")),
            "Gaussian 数量: {0}".format(data.get("gaussian_count")),
            "图像数量: {0}".format(data.get("image_count")),
            "PSNR: {0}".format(metrics.get("psnr")),
            "SSIM: {0}".format(metrics.get("ssim")),
            "LPIPS: {0}".format(metrics.get("lpips")),
            "MSE: {0}".format(metrics.get("mse")),
            "MAE: {0}".format(metrics.get("mae")),
            "metrics.json: {0}".format(data.get("metrics_json", "")),
            "日志文件: {0}".format(data.get("log_file", "")),
            "生成时间: {0}".format(data.get("generated_at", "")),
        ]

        preview_images = data.get("preview_images", [])
        if preview_images:
            lines.append("预览图像:")
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

        resolved_model_paths = [self._resolve_user_path(p) for p in model_paths_cfg]
        processed_scene_path = (
            self._resolve_user_path(processed_scene_path_cfg)
            if processed_scene_path_cfg
            else None
        )
        log_dir = self._resolve_user_path(log_dir_cfg) if log_dir_cfg else None
        report_dir = self._resolve_user_path(report_dir_cfg) if report_dir_cfg else None

        if not scene_name:
            scene_name = resolved_model_paths[0].name

        if log_dir is None:
            log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "report.log"
        logger = setup_logger(str(log_file))

        logger.info("开始生成报告")
        logger.info("场景名称: %s", scene_name)
        logger.info("模型目录列表: %s", ", ".join([str(p) for p in resolved_model_paths]))

        if not quiet:
            print("开始生成报告: {0}".format(scene_name))

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

            logger.info("已写入 report.json: %s", report_json)
            logger.info("已写入 report.md: %s", report_md)
            logger.info("已写入 summary.csv: %s", summary_csv)
            logger.info("已写入 summary.txt: %s", summary_txt)

            if not quiet:
                print("已写入 report.json: {0}".format(report_json))
                print("已写入 report.md: {0}".format(report_md))
                print("已写入 summary.csv: {0}".format(summary_csv))
                print("已写入 summary.txt: {0}".format(summary_txt))

        logger.info("报告生成完成")
        if not quiet:
            print("报告生成完成")