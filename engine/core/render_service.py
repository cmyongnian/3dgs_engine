from pathlib import Path
import subprocess
import sys
from typing import Optional

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import (
    popen_registered,
    process_registry,
    raise_if_force_stopped,
)


class RenderService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        render_config_path="configs/render.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        render_config_path = Path(render_config_path)
        if not render_config_path.is_absolute():
            render_config_path = self.pm.project_root / render_config_path

        self.render_cfg = load_yaml(str(render_config_path))["render"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def run(self):
        raise_if_force_stopped(self.task_id)

        scene_name = self.render_cfg["scene_name"]
        model_path = self._resolve_user_path(self.render_cfg["model_path"])

        iteration = self.render_cfg.get("iteration", -1)
        skip_train = self.render_cfg.get("skip_train", True)
        skip_test = self.render_cfg.get("skip_test", False)
        quiet = self.render_cfg.get("quiet", False)

        if not model_path.exists():
            raise FileNotFoundError(f"模型目录不存在: {model_path}")

        render_script = (self.pm.gs_repo / "render.py").resolve()
        if not render_script.exists():
            raise FileNotFoundError(f"官方 render.py 不存在: {render_script}")

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "render.log"
        logger = setup_logger(str(log_file))

        cmd = [
            sys.executable,
            str(render_script),
            "-m",
            str(model_path),
            "--iteration",
            str(iteration),
        ]

        if skip_train:
            cmd.append("--skip_train")

        if skip_test:
            cmd.append("--skip_test")

        if quiet:
            cmd.append("--quiet")

        logger.info("开始渲染")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("3DGS 仓库目录: %s", self.pm.gs_repo)
        logger.info("场景名称: %s", scene_name)
        logger.info("模型目录: %s", model_path)
        logger.info("执行命令: %s", " ".join(cmd))

        print(f"开始渲染: {scene_name}")
        print(f"模型目录: {model_path}")
        print("执行命令:", " ".join(cmd))

        process = None

        try:
            process = popen_registered(
                self.task_id,
                cmd,
                cwd=str(self.pm.gs_repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            if process.stdout:
                for line in process.stdout:
                    raise_if_force_stopped(self.task_id)

                    line = line.rstrip()
                    if line:
                        print(line)
                        logger.info(line)

            process.wait()

            raise_if_force_stopped(self.task_id)

            if process.returncode == 0:
                logger.info("渲染完成")
                print("渲染完成")
            else:
                logger.error("渲染失败，返回码: %s", process.returncode)
                raise RuntimeError(f"渲染失败，返回码: {process.returncode}")

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)