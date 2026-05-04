from pathlib import Path
import shutil
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


class ConvertService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        convert_config_path="configs/convert.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        convert_config_path = Path(convert_config_path)
        if not convert_config_path.is_absolute():
            convert_config_path = self.pm.project_root / convert_config_path

        self.convert_cfg = load_yaml(str(convert_config_path))["convert"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _resolve_executable(self, exe: str) -> str:
        if not exe:
            return ""
        exe_path = Path(exe)
        if exe_path.is_absolute():
            return str(exe_path)
        if any(sep in exe for sep in ["/", "\\"]):
            return str((self.pm.project_root / exe_path).resolve())
        return exe

    def _copy_images(self, src_dir: Path, dst_dir: Path):
        raise_if_force_stopped(self.task_id)

        dst_dir.mkdir(parents=True, exist_ok=True)
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        copied = 0

        for p in src_dir.iterdir():
            raise_if_force_stopped(self.task_id)

            if p.is_file() and p.suffix.lower() in image_exts:
                shutil.copy2(p, dst_dir / p.name)
                copied += 1

        if copied == 0:
            raise RuntimeError(f"没有从原始目录复制到任何图片: {src_dir}")

    def _prepare_distorted(self, colmap_workspace: Path, distorted_dir: Path):
        raise_if_force_stopped(self.task_id)

        distorted_dir.mkdir(parents=True, exist_ok=True)

        db_src = colmap_workspace / "database.db"
        sparse_src = colmap_workspace / "sparse" / "0"

        if not db_src.exists():
            raise FileNotFoundError(f"未找到 COLMAP database.db: {db_src}")
        if not sparse_src.exists():
            raise FileNotFoundError(f"未找到 COLMAP sparse/0: {sparse_src}")

        shutil.copy2(db_src, distorted_dir / "database.db")

        sparse_dst_root = distorted_dir / "sparse"
        sparse_dst_root.mkdir(parents=True, exist_ok=True)

        sparse_dst = sparse_dst_root / "0"
        if sparse_dst.exists():
            shutil.rmtree(sparse_dst)

        raise_if_force_stopped(self.task_id)
        shutil.copytree(sparse_src, sparse_dst)

    def _clean_previous_outputs(self, gs_input_path: Path):
        raise_if_force_stopped(self.task_id)

        to_remove = [
            gs_input_path / "input",
            gs_input_path / "distorted",
            gs_input_path / "images",
            gs_input_path / "sparse",
            gs_input_path / "images_2",
            gs_input_path / "images_4",
            gs_input_path / "images_8",
        ]

        for p in to_remove:
            raise_if_force_stopped(self.task_id)

            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

    def _validate_generated_images(self, image_dir: Path):
        raise_if_force_stopped(self.task_id)

        if not image_dir.exists():
            raise FileNotFoundError(f"convert 输出的 images 目录不存在: {image_dir}")

        bad_files = []
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

        for img_path in sorted(image_dir.iterdir()):
            raise_if_force_stopped(self.task_id)

            if not img_path.is_file() or img_path.suffix.lower() not in image_exts:
                continue

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
                f"convert 生成的训练图片存在损坏文件，共 {len(bad_files)} 张：\n{msg}"
            )

    def _ensure_sparse_layout(self, gs_input_path: Path, distorted_dir: Path, logger):
        raise_if_force_stopped(self.task_id)

        expected_sparse = gs_input_path / "sparse" / "0"
        if expected_sparse.exists():
            return

        fallback_sparse = distorted_dir / "sparse" / "0"
        if fallback_sparse.exists():
            sparse_root = gs_input_path / "sparse"
            sparse_root.mkdir(parents=True, exist_ok=True)

            if expected_sparse.exists():
                shutil.rmtree(expected_sparse)

            raise_if_force_stopped(self.task_id)
            shutil.copytree(fallback_sparse, expected_sparse)

            logger.warning("convert 后未直接生成 gs_input/sparse/0，已从 distorted/sparse/0 自动补齐")
            print("convert 后未直接生成 gs_input/sparse/0，已从 distorted/sparse/0 自动补齐")
            return

        raise FileNotFoundError(
            f"convert 后未找到训练所需的 sparse/0 目录：{expected_sparse}"
        )

    def _validate_generated_sparse(self, gs_input_path: Path):
        raise_if_force_stopped(self.task_id)

        sparse_root = gs_input_path / "sparse"
        sparse_zero = sparse_root / "0"

        if not sparse_root.exists():
            raise FileNotFoundError(f"convert 输出的 sparse 目录不存在: {sparse_root}")

        if not sparse_zero.exists():
            raise FileNotFoundError(f"convert 输出的 sparse/0 目录不存在: {sparse_zero}")

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
                f"sparse/0 中未找到 COLMAP 所需文件（bin 或 txt）：{sparse_zero}"
            )

    def run(self):
        raise_if_force_stopped(self.task_id)

        scene_name = self.convert_cfg["scene_name"]
        source_images = self._resolve_user_path(self.convert_cfg["source_images"])
        colmap_workspace = self._resolve_user_path(self.convert_cfg["colmap_workspace"])
        gs_input_path = self._resolve_user_path(self.convert_cfg["gs_input_path"])

        colmap_executable = self._resolve_executable(
            self.convert_cfg.get("colmap_executable", "")
        )
        magick_executable = self._resolve_executable(
            self.convert_cfg.get("magick_executable", "")
        )

        skip_matching = self.convert_cfg.get("skip_matching", True)
        resize = self.convert_cfg.get("resize", False)
        use_magick = self.convert_cfg.get("use_magick", False)

        gs_repo = self._resolve_user_path(
            self.convert_cfg.get("gs_repo", "third_party/gaussian-splatting")
        )
        convert_script = gs_repo / "convert.py"

        if not source_images.exists():
            raise FileNotFoundError(f"原始图片目录不存在: {source_images}")
        if not colmap_workspace.exists():
            raise FileNotFoundError(f"COLMAP workspace 不存在: {colmap_workspace}")
        if not convert_script.exists():
            raise FileNotFoundError(f"未找到官方 convert.py: {convert_script}")

        input_dir = gs_input_path / "input"
        distorted_dir = gs_input_path / "distorted"
        gs_input_path.mkdir(parents=True, exist_ok=True)

        self._clean_previous_outputs(gs_input_path)

        self._copy_images(source_images, input_dir)
        self._prepare_distorted(colmap_workspace, distorted_dir)

        raise_if_force_stopped(self.task_id)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "convert.log"
        logger = setup_logger(str(log_file))

        cmd = [
            sys.executable,
            str(convert_script),
            "-s",
            str(gs_input_path),
        ]

        if skip_matching:
            cmd.append("--skip_matching")

        if resize:
            cmd.append("--resize")

        if colmap_executable:
            cmd.extend(["--colmap_executable", str(colmap_executable)])

        if use_magick and magick_executable:
            cmd.extend(["--magick_executable", str(magick_executable)])

        logger.info("开始执行 convert.py")
        logger.info("场景名称: %s", scene_name)
        logger.info("原始图片目录: %s", source_images)
        logger.info("COLMAP workspace: %s", colmap_workspace)
        logger.info("3DGS 输入目录: %s", gs_input_path)
        logger.info("已清理旧的 convert 产物目录（input/distorted/images/sparse/images_2_4_8）")
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始执行 convert.py")
        print("3DGS 输入目录:", gs_input_path)
        print("执行命令:", " ".join(cmd))

        process = None

        try:
            process = popen_registered(
                self.task_id,
                cmd,
                cwd=str(gs_repo),
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
                generated_images_dir = gs_input_path / "images"

                self._ensure_sparse_layout(gs_input_path, distorted_dir, logger)
                self._validate_generated_images(generated_images_dir)
                self._validate_generated_sparse(gs_input_path)

                logger.info("convert.py 执行完成，训练图片与 sparse 结构校验通过")
                print("convert.py 执行完成，训练图片与 sparse 结构校验通过")
            else:
                logger.error("convert.py 执行失败，返回码: %s", process.returncode)
                raise RuntimeError(f"convert.py 执行失败，返回码: {process.returncode}")

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)