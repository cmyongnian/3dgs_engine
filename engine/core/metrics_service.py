from pathlib import Path
import subprocess
import sys

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class MetricsService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        metrics_config_path="configs/metrics.yaml"
    ):
        self.pm = PathManager(system_config_path)

        metrics_config_path = Path(metrics_config_path)
        if not metrics_config_path.is_absolute():
            metrics_config_path = self.pm.project_root / metrics_config_path

        self.metrics_cfg = load_yaml(str(metrics_config_path))["metrics"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def run(self):
        scene_name = self.metrics_cfg["scene_name"]
        model_paths = self.metrics_cfg.get("model_paths", [])
        quiet = self.metrics_cfg.get("quiet", False)

        if not model_paths:
            raise ValueError("metrics.yaml 中 model_paths 不能为空")

        resolved_model_paths = [self._resolve_user_path(p) for p in model_paths]

        for p in resolved_model_paths:
            if not p.exists():
                raise FileNotFoundError(f"模型目录不存在: {p}")

        metrics_script = (self.pm.gs_repo / "metrics.py").resolve()
        if not metrics_script.exists():
            raise FileNotFoundError(f"官方 metrics.py 不存在: {metrics_script}")

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "metrics.log"
        logger = setup_logger(str(log_file))

        cmd = [
            sys.executable,
            str(metrics_script),
            "-m",
        ]
        cmd.extend([str(p) for p in resolved_model_paths])

        if quiet:
            cmd.append("--quiet")

        logger.info("开始评测")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("3DGS仓库目录: %s", self.pm.gs_repo)
        logger.info("场景名称: %s", scene_name)
        logger.info("模型目录列表: %s", ", ".join([str(p) for p in resolved_model_paths]))
        logger.info("执行命令: %s", " ".join(cmd))

        print(f"开始评测: {scene_name}")
        for p in resolved_model_paths:
            print(f"模型目录: {p}")

        process = subprocess.Popen(
            cmd,
            cwd=str(self.pm.gs_repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in process.stdout:
            line = line.rstrip()
            print(line)
            logger.info(line)

        process.wait()

        if process.returncode == 0:
            logger.info("评测完成")
            print("评测完成")
        else:
            logger.error("评测失败，返回码: %s", process.returncode)
            raise RuntimeError(f"评测失败，返回码: {process.returncode}")