from pathlib import Path
import json
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Tuple

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import (
    popen_registered,
    process_registry,
    raise_if_force_stopped,
)


class ColmapService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        colmap_config_path="configs/colmap.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        colmap_config_path = Path(colmap_config_path)
        if not colmap_config_path.is_absolute():
            colmap_config_path = self.pm.project_root / colmap_config_path

        self.colmap_cfg = load_yaml(str(colmap_config_path))["colmap"]

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

    def _as_bool(self, value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value

        if value is None:
            return default

        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "y", "on"}:
                return True
            if text in {"0", "false", "no", "n", "off"}:
                return False

        return bool(value)

    def _check_image_folder(self, image_path: Path):
        raise_if_force_stopped(self.task_id)

        if not image_path.exists():
            raise FileNotFoundError(f"原始图像目录不存在: {image_path}")

        if not image_path.is_dir():
            raise NotADirectoryError(f"image_path 不是文件夹: {image_path}")

        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        images = [p for p in image_path.iterdir() if p.suffix.lower() in image_exts]

        if len(images) == 0:
            raise RuntimeError(f"原始图像目录中没有找到图片: {image_path}")

    def _has_sparse_model_files(self, sparse_dir: Path) -> bool:
        if not sparse_dir.exists() or not sparse_dir.is_dir():
            return False

        bin_ok = all(
            (sparse_dir / name).exists()
            for name in ["cameras.bin", "images.bin", "points3D.bin"]
        )

        txt_ok = all(
            (sparse_dir / name).exists()
            for name in ["cameras.txt", "images.txt", "points3D.txt"]
        )

        return bin_ok or txt_ok

    def _locate_reusable_colmap(self, base_path: Path) -> Tuple[Path, Path]:
        """定位可复用的 database.db 和 sparse 模型目录。

        支持用户填写：
        1. 旧任务 processed 目录，例如 datasets/processed/liren/2b8a7d427d63
        2. 旧任务 gs_input 目录，例如 datasets/processed/liren/2b8a7d427d63/gs_input
        3. distorted 目录，例如 .../gs_input/distorted
        4. sparse/0 目录本身。
        """

        candidates = [
            (base_path / "database.db", base_path / "sparse" / "0"),
            (base_path / "database.db", base_path / "sparse"),
            (base_path / "distorted" / "database.db", base_path / "distorted" / "sparse" / "0"),
            (base_path / "distorted" / "database.db", base_path / "distorted" / "sparse"),
        ]

        if base_path.name == "0" and base_path.parent.name == "sparse":
            candidates.append((base_path.parent.parent / "database.db", base_path))

        if base_path.name == "sparse":
            candidates.append((base_path.parent / "database.db", base_path / "0"))
            candidates.append((base_path.parent / "database.db", base_path))

        for db_path, sparse_dir in candidates:
            if db_path.exists() and self._has_sparse_model_files(sparse_dir):
                return db_path, sparse_dir

        raise FileNotFoundError(
            "未在复用目录中找到有效的 COLMAP 结果。\n"
            f"复用目录: {base_path}\n"
            "需要至少包含 database.db 和 sparse/0 下的 cameras/images/points3D 文件。"
        )

    def _copy_reused_colmap(
        self,
        reuse_workspace_path: Path,
        workspace_path: Path,
        logger,
    ) -> None:
        raise_if_force_stopped(self.task_id)

        if not reuse_workspace_path.exists():
            raise FileNotFoundError(f"COLMAP 复用目录不存在: {reuse_workspace_path}")

        src_db, src_sparse = self._locate_reusable_colmap(reuse_workspace_path)

        workspace_path.mkdir(parents=True, exist_ok=True)

        dst_db = workspace_path / "database.db"
        dst_sparse = workspace_path / "sparse" / "0"

        same_database = src_db.resolve() == dst_db.resolve()
        same_sparse = src_sparse.resolve() == dst_sparse.resolve()

        if same_database and same_sparse:
            logger.info("复用目录与当前任务目录相同，无需复制")
            print("复用目录与当前任务目录相同，无需复制")
            return

        if dst_db.exists():
            dst_db.unlink()

        dst_sparse.parent.mkdir(parents=True, exist_ok=True)

        if dst_sparse.exists():
            shutil.rmtree(dst_sparse)

        raise_if_force_stopped(self.task_id)
        shutil.copy2(src_db, dst_db)

        raise_if_force_stopped(self.task_id)
        shutil.copytree(src_sparse, dst_sparse)

        meta = {
            "reuse_enabled": True,
            "reused_at": datetime.now().isoformat(timespec="seconds"),
            "source_workspace": str(reuse_workspace_path),
            "source_database": str(src_db),
            "source_sparse": str(src_sparse),
            "target_workspace": str(workspace_path),
            "target_database": str(dst_db),
            "target_sparse": str(dst_sparse),
            "note": "当前任务复用了已有 COLMAP 稀疏重建结果，未重新执行 automatic_reconstructor。",
        }

        meta_path = workspace_path / "colmap_reuse_meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("已复制复用 COLMAP database: %s -> %s", src_db, dst_db)
        logger.info("已复制复用 COLMAP sparse: %s -> %s", src_sparse, dst_sparse)

        print("已复用已有 COLMAP 结果")
        print("来源目录:", reuse_workspace_path)
        print("当前任务目录:", workspace_path)
        print("已复制 database.db 和 sparse/0")

    def run(self):
        raise_if_force_stopped(self.task_id)

        scene_name = self.colmap_cfg["scene_name"]
        image_path = self._resolve_user_path(self.colmap_cfg["image_path"])
        workspace_path = self._resolve_user_path(self.colmap_cfg["workspace_path"])
        colmap_executable = self._resolve_executable(
            self.colmap_cfg.get("colmap_executable", "colmap")
        )
        use_gpu = self.colmap_cfg.get("use_gpu", True)

        reuse_enabled = self._as_bool(
            self.colmap_cfg.get("reuse_enabled", False),
            False,
        )
        reuse_workspace_raw = str(self.colmap_cfg.get("reuse_workspace_path", "") or "").strip()

        self._check_image_folder(image_path)

        workspace_path.mkdir(parents=True, exist_ok=True)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "colmap.log"
        logger = setup_logger(str(log_file))

        logger.info("开始 COLMAP 阶段")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("场景名称: %s", scene_name)
        logger.info("原始图像目录: %s", image_path)
        logger.info("工作目录: %s", workspace_path)

        print("开始 COLMAP 阶段")
        print("项目根目录:", self.pm.project_root)
        print("场景名称:", scene_name)
        print("原始图像目录:", image_path)
        print("工作目录:", workspace_path)

        if reuse_enabled:
            if not reuse_workspace_raw:
                raise RuntimeError("已开启 COLMAP 复用，但没有选择或填写复用目录。")

            reuse_workspace_path = self._resolve_user_path(reuse_workspace_raw)

            logger.info("已开启 COLMAP 复用，本次不执行 automatic_reconstructor")
            logger.info("复用目录: %s", reuse_workspace_path)

            print("已开启 COLMAP 复用，本次不执行 automatic_reconstructor")
            print("复用目录:", reuse_workspace_path)

            self._copy_reused_colmap(
                reuse_workspace_path=reuse_workspace_path,
                workspace_path=workspace_path,
                logger=logger,
            )

            logger.info("COLMAP 复用完成")
            print("COLMAP 复用完成")
            return

        cmd = [
            str(colmap_executable),
            "automatic_reconstructor",
            "--workspace_path",
            str(workspace_path),
            "--image_path",
            str(image_path),
            "--use_gpu",
            "1" if use_gpu else "0",
        ]

        logger.info("开始 COLMAP 重建")
        logger.info("COLMAP 可执行程序: %s", colmap_executable)
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始 COLMAP 重建")
        print("COLMAP 可执行程序:", colmap_executable)
        print("执行命令:", " ".join(cmd))

        process = None

        try:
            process = popen_registered(
                self.task_id,
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"找不到 COLMAP 可执行程序: {colmap_executable}\n"
                f"请检查 configs/colmap.yaml 里的 colmap_executable 配置。"
            )

        try:
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
                logger.info("COLMAP 重建完成")
                print("COLMAP 重建完成")
            else:
                logger.error("COLMAP 重建失败，返回码: %s", process.returncode)
                raise RuntimeError(f"COLMAP 重建失败，返回码: {process.returncode}")

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)
