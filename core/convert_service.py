from pathlib import Path
import shutil
import subprocess
import sys

from core.config import load_yaml
from core.paths import PathManager
from core.logger import setup_logger


class ConvertService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        convert_config_path="configs/convert.yaml"
    ):
        self.pm = PathManager(system_config_path)

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
        dst_dir.mkdir(parents=True, exist_ok=True)

        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        copied = 0
        for p in src_dir.iterdir():
            if p.is_file() and p.suffix.lower() in image_exts:
                shutil.copy2(p, dst_dir / p.name)
                copied += 1

        if copied == 0:
            raise RuntimeError(f"没有从原始目录复制到任何图片: {src_dir}")

    def _prepare_distorted(self, colmap_workspace: Path, distorted_dir: Path):
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
        shutil.copytree(sparse_src, sparse_dst)

    def run(self):
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

        gs_repo = self._resolve_user_path(self.convert_cfg.get("gs_repo", "third_party/gaussian-splatting"))
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

        # 重新准备输入
        if input_dir.exists():
            shutil.rmtree(input_dir)
        if distorted_dir.exists():
            shutil.rmtree(distorted_dir)

        self._copy_images(source_images, input_dir)
        self._prepare_distorted(colmap_workspace, distorted_dir)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "convert.log"
        logger = setup_logger(str(log_file))

        cmd = [
            sys.executable,
            str(convert_script),
            "-s", str(gs_input_path),
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
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始执行 convert.py")
        print("3DGS 输入目录:", gs_input_path)
        print("执行命令:", " ".join(cmd))

        process = subprocess.Popen(
            cmd,
            cwd=str(gs_repo),
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
            logger.info("convert.py 执行完成")
            print("convert.py 执行完成")
        else:
            logger.error("convert.py 执行失败，返回码: %s", process.returncode)
            raise RuntimeError(f"convert.py 执行失败，返回码: {process.returncode}")