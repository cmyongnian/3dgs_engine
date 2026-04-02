from pathlib import Path
import json
import csv
import re

from core.config import load_yaml
from core.paths import PathManager
from core.logger import setup_logger


class ReportService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        report_config_path="configs/report.yaml",
    ):
        self.pm = PathManager(system_config_path)

        report_config_path = Path(report_config_path)
        if not report_config_path.is_absolute():
            report_config_path = self.pm.project_root / report_config_path

        self.report_cfg = load_yaml(str(report_config_path))["report"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _find_latest_iteration_dir(self, model_path: Path):
        point_cloud_dir = model_path / "point_cloud"
        if not point_cloud_dir.exists():
            return None, None

        iteration_dirs = []
        for p in point_cloud_dir.iterdir():
            if p.is_dir() and p.name.startswith("iteration_"):
                m = re.search(r"iteration_(\d+)", p.name)
                if m:
                    iteration_dirs.append((int(m.group(1)), p))

        if not iteration_dirs:
            return None, None

        iteration_dirs.sort(key=lambda x: x[0])
        latest_iter, latest_dir = iteration_dirs[-1]
        return latest_iter, latest_dir

    def _count_gaussians_from_ply(self, ply_path: Path):
        if not ply_path.exists():
            return None

        with open(ply_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("element vertex"):
                    parts = line.split()
                    if len(parts) == 3:
                        return int(parts[2])
                if line == "end_header":
                    break
        return None

    def _find_metrics_file(self, model_path: Path):
        candidates = [
            model_path / "results.json",
            model_path / "metrics.json",
            model_path / "eval_results.json",
        ]

        for p in candidates:
            if p.exists():
                return p

        json_files = list(model_path.glob("*.json"))
        for p in json_files:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                text = json.dumps(data).lower()
                if "psnr" in text or "ssim" in text or "lpips" in text:
                    return p
            except Exception:
                continue

        return None

    def _extract_metrics(self, data: dict):
        """
        尽量兼容不同 json 结构，返回 psnr / ssim / lpips
        """
        def try_get(d, key_candidates):
            for k, v in d.items():
                if isinstance(k, str):
                    lk = k.lower()
                    for cand in key_candidates:
                        if cand in lk and isinstance(v, (int, float)):
                            return float(v)
            return None

        # 情况1：顶层直接就是指标
        psnr = try_get(data, ["psnr"])
        ssim = try_get(data, ["ssim"])
        lpips = try_get(data, ["lpips"])
        if psnr is not None or ssim is not None or lpips is not None:
            return psnr, ssim, lpips

        # 情况2：顶层下面再套一层方法名
        for _, v in data.items():
            if isinstance(v, dict):
                psnr = try_get(v, ["psnr"])
                ssim = try_get(v, ["ssim"])
                lpips = try_get(v, ["lpips"])
                if psnr is not None or ssim is not None or lpips is not None:
                    return psnr, ssim, lpips

        return None, None, None

    def run(self):
        scene_name = self.report_cfg["scene_name"]
        model_paths = self.report_cfg.get("model_paths", [])
        report_dir = self._resolve_user_path(self.report_cfg["report_dir"])

        report_dir.mkdir(parents=True, exist_ok=True)

        log_file = report_dir / "report.log"
        logger = setup_logger(str(log_file))

        logger.info("开始生成实验结果汇总")
        logger.info("场景名称: %s", scene_name)

        rows = []

        for model_path_str in model_paths:
            model_path = self._resolve_user_path(model_path_str)
            model_name = model_path.name

            logger.info("处理模型目录: %s", model_path)

            latest_iter, latest_iter_dir = self._find_latest_iteration_dir(model_path)

            gaussian_count = None
            if latest_iter_dir is not None:
                ply_path = latest_iter_dir / "point_cloud.ply"
                gaussian_count = self._count_gaussians_from_ply(ply_path)

            psnr, ssim, lpips = None, None, None
            metrics_file = self._find_metrics_file(model_path)
            if metrics_file is not None:
                try:
                    with open(metrics_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    psnr, ssim, lpips = self._extract_metrics(data)
                except Exception as e:
                    logger.warning("读取指标文件失败 %s: %s", metrics_file, e)

            row = {
                "model_name": model_name,
                "model_path": str(model_path),
                "latest_iteration": latest_iter,
                "psnr": psnr,
                "ssim": ssim,
                "lpips": lpips,
                "gaussian_count": gaussian_count,
            }
            rows.append(row)

        csv_file = report_dir / "summary.csv"
        txt_file = report_dir / "summary.txt"

        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "model_name",
                    "model_path",
                    "latest_iteration",
                    "psnr",
                    "ssim",
                    "lpips",
                    "gaussian_count",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        lines = []
        lines.append("========== 实验结果汇总 ==========")
        lines.append(f"场景名称: {scene_name}")
        lines.append("")

        for row in rows:
            lines.append(f"模型名称: {row['model_name']}")
            lines.append(f"模型路径: {row['model_path']}")
            lines.append(f"最新迭代数: {row['latest_iteration']}")
            lines.append(f"PSNR: {row['psnr']}")
            lines.append(f"SSIM: {row['ssim']}")
            lines.append(f"LPIPS: {row['lpips']}")
            lines.append(f"高斯点数: {row['gaussian_count']}")
            lines.append("")

        report_text = "\n".join(lines)

        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(report_text)

        print(report_text)
        logger.info(report_text)
        logger.info("实验结果汇总完成，CSV: %s", csv_file)
        logger.info("实验结果汇总完成，TXT: %s", txt_file)

        print(f"\n实验结果汇总完成，CSV: {csv_file}")
        print(f"实验结果汇总完成，TXT: {txt_file}")