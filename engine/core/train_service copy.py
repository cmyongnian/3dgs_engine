from pathlib import Path
import subprocess
import sys

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class TrainerService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        train_config_path="configs/train.yaml"
    ):
        self.pm = PathManager(system_config_path)

        train_config_path = Path(train_config_path)
        if not train_config_path.is_absolute():
            train_config_path = self.pm.project_root / train_config_path

        self.train_cfg = load_yaml(str(train_config_path))["train"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _get_active_profile(self):
        active_profile = self.train_cfg.get("active_profile", None)
        profiles = self.train_cfg.get("profiles", {})

        if active_profile is None:
            raise ValueError("train.yaml 缺少 active_profile 配置")

        if active_profile not in profiles:
            raise ValueError(f"未找到训练模式: {active_profile}")

        return active_profile, profiles[active_profile]

    def run(self):
        scene_name = self.train_cfg["scene_name"]
        source_path = self._resolve_user_path(self.train_cfg["source_path"])
        model_output = self._resolve_user_path(self.train_cfg["model_output"])

        active_profile_name, profile = self._get_active_profile()

        eval_flag = profile.get("eval", True)
        iterations = profile.get("iterations", 30000)
        save_iterations = profile.get("save_iterations", [])
        test_iterations = profile.get("test_iterations", [])
        quiet = profile.get("quiet", False)

        extra_args = profile.get("extra_args", {})
        data_device = extra_args.get("data_device", None)
        resolution = extra_args.get("resolution", None)
        densify_grad_threshold = extra_args.get("densify_grad_threshold", None)
        densification_interval = extra_args.get("densification_interval", None)
        densify_until_iter = extra_args.get("densify_until_iter", None)

        if not source_path.exists():
            raise FileNotFoundError(f"训练输入目录不存在: {source_path}")

        model_output.mkdir(parents=True, exist_ok=True)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"train_{active_profile_name}.log"
        logger = setup_logger(str(log_file))

        train_script = (self.pm.gs_repo / "train.py").resolve()
        if not train_script.exists():
            raise FileNotFoundError(f"官方 train.py 不存在: {train_script}")

        cmd = [
            sys.executable,
            str(train_script),
            "-s", str(source_path),
            "-m", str(model_output),
            "--iterations", str(iterations),
        ]

        if eval_flag:
            cmd.append("--eval")

        if quiet:
            cmd.append("--quiet")

        if save_iterations:
            cmd.append("--save_iterations")
            cmd.extend([str(x) for x in save_iterations])

        if test_iterations:
            cmd.append("--test_iterations")
            cmd.extend([str(x) for x in test_iterations])

        if data_device is not None:
            cmd.extend(["--data_device", str(data_device)])

        if resolution is not None:
            cmd.extend(["-r", str(resolution)])

        if densify_grad_threshold is not None:
            cmd.extend(["--densify_grad_threshold", str(densify_grad_threshold)])

        if densification_interval is not None:
            cmd.extend(["--densification_interval", str(densification_interval)])

        if densify_until_iter is not None:
            cmd.extend(["--densify_until_iter", str(densify_until_iter)])

        logger.info("开始训练")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("3DGS仓库目录: %s", self.pm.gs_repo)
        logger.info("场景名称: %s", scene_name)
        logger.info("当前训练模式: %s", active_profile_name)
        logger.info("训练输入目录: %s", source_path)
        logger.info("模型输出目录: %s", model_output)
        logger.info("执行命令: %s", " ".join(cmd))

        print(f"当前训练模式: {active_profile_name}")
        print(f"训练输入目录: {source_path}")
        print(f"模型输出目录: {model_output}")

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
            logger.info("训练完成")
            print("训练完成")
        else:
            logger.error("训练失败，返回码: %s", process.returncode)
            raise RuntimeError(f"训练失败，返回码: {process.returncode}")