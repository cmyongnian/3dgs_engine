from pathlib import Path
import subprocess
import sys
from typing import Optional

from PIL import Image, UnidentifiedImageError

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import (
    popen_registered,
    process_registry,
    raise_if_force_stopped,
)


class TrainerService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        train_config_path="configs/train.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

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

    def _find_latest_checkpoint(self, model_output: Path):
        candidates = sorted(model_output.glob("chkpnt*.pth"))

        if not candidates:
            return None

        def extract_iter(p: Path):
            name = p.stem
            num = "".join(ch for ch in name if ch.isdigit())
            return int(num) if num else -1

        candidates = sorted(candidates, key=extract_iter)
        return candidates[-1]

    def _collect_images(self, image_dir: Path):
        raise_if_force_stopped(self.task_id)

        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

        return sorted(
            [
                p
                for p in image_dir.iterdir()
                if p.is_file() and p.suffix.lower() in image_exts
            ]
        )

    def _validate_training_images(self, source_path: Path):
        raise_if_force_stopped(self.task_id)

        image_dir = source_path / "images"

        if not image_dir.exists():
            raise FileNotFoundError(f"训练输入 images 目录不存在: {image_dir}")

        image_files = self._collect_images(image_dir)

        if not image_files:
            raise RuntimeError(f"训练输入 images 目录中没有找到图片: {image_dir}")

        bad_files = []

        for img_path in image_files:
            raise_if_force_stopped(self.task_id)

            try:
                with Image.open(img_path) as img:
                    img.verify()

                with Image.open(img_path) as img:
                    img.load()
                    _ = img.size

            except (UnidentifiedImageError, OSError, ValueError) as e:
                bad_files.append(f"{img_path.name}: {e}")

        if bad_files:
            msg = "\n".join(bad_files[:20])
            raise RuntimeError(
                f"训练输入中发现损坏或不可读取图片，共 {len(bad_files)} 张：\n{msg}"
            )

    def _validate_sparse(self, source_path: Path):
        raise_if_force_stopped(self.task_id)

        sparse_zero = source_path / "sparse" / "0"

        if not sparse_zero.exists():
            raise FileNotFoundError(f"训练输入 sparse/0 目录不存在: {sparse_zero}")

        has_bin = all(
            (sparse_zero / name).exists()
            for name in ["cameras.bin", "images.bin", "points3D.bin"]
        )

        has_txt = all(
            (sparse_zero / name).exists()
            for name in ["cameras.txt", "images.txt", "points3D.txt"]
        )

        if not has_bin and not has_txt:
            raise RuntimeError(
                f"训练输入 sparse/0 中未找到 COLMAP 模型文件: {sparse_zero}"
            )

    def run(self):
        raise_if_force_stopped(self.task_id)

        scene_name = self.train_cfg["scene_name"]
        source_path = self._resolve_user_path(self.train_cfg["source_path"])
        model_output = self._resolve_user_path(self.train_cfg["model_output"])

        active_profile_name, profile = self._get_active_profile()

        eval_flag = profile.get("eval", True)
        iterations = profile.get("iterations", 30000)
        save_iterations = profile.get("save_iterations", [])
        test_iterations = profile.get("test_iterations", [])
        checkpoint_iterations = profile.get("checkpoint_iterations", [])
        start_checkpoint = profile.get("start_checkpoint", "")
        resume_from_latest = profile.get("resume_from_latest", False)
        quiet = profile.get("quiet", False)

        extra_args = profile.get("extra_args", {})
        data_device = extra_args.get("data_device", None)
        resolution = extra_args.get("resolution", None)
        densify_grad_threshold = extra_args.get("densify_grad_threshold", None)
        densification_interval = extra_args.get("densification_interval", None)
        densify_until_iter = extra_args.get("densify_until_iter", None)

        if not source_path.exists():
            raise FileNotFoundError(f"训练输入目录不存在: {source_path}")

        self._validate_training_images(source_path)
        self._validate_sparse(source_path)

        model_output.mkdir(parents=True, exist_ok=True)

        resolved_start_checkpoint = None

        if start_checkpoint:
            resolved_start_checkpoint = self._resolve_user_path(start_checkpoint)

            if not resolved_start_checkpoint.exists():
                raise FileNotFoundError(
                    f"start_checkpoint 不存在: {resolved_start_checkpoint}"
                )

        elif resume_from_latest:
            latest_ckpt = self._find_latest_checkpoint(model_output)

            if latest_ckpt is None:
                print("未找到可恢复的 checkpoint，将从头开始训练。")
            else:
                resolved_start_checkpoint = latest_ckpt
                print(f"检测到最新 checkpoint: {resolved_start_checkpoint}")

        raise_if_force_stopped(self.task_id)

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
            "-s",
            str(source_path),
            "-m",
            str(model_output),
            "--iterations",
            str(iterations),
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

        if checkpoint_iterations:
            cmd.append("--checkpoint_iterations")
            cmd.extend([str(x) for x in checkpoint_iterations])

        if resolved_start_checkpoint is not None:
            cmd.extend(["--start_checkpoint", str(resolved_start_checkpoint)])

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
        logger.info("3DGS 仓库目录: %s", self.pm.gs_repo)
        logger.info("场景名称: %s", scene_name)
        logger.info("当前训练模式: %s", active_profile_name)
        logger.info("训练输入目录: %s", source_path)
        logger.info("模型输出目录: %s", model_output)
        logger.info("执行命令: %s", " ".join(cmd))
        logger.info("checkpoint 保存步数: %s", checkpoint_iterations)
        logger.info(
            "恢复训练起点: %s",
            resolved_start_checkpoint if resolved_start_checkpoint else "无",
        )

        print("开始训练")
        print(f"当前训练模式: {active_profile_name}")
        print(f"训练输入目录: {source_path}")
        print(f"模型输出目录: {model_output}")
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
                logger.info("训练完成")
                print("训练完成")
            else:
                logger.error("训练失败，返回码: %s", process.returncode)
                raise RuntimeError(f"训练失败，返回码: {process.returncode}")

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)