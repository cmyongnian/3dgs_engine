from __future__ import annotations

import json
import struct
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.core.config import load_yaml
from engine.core.logger import setup_logger
from engine.core.paths import PathManager


CAMERA_MODEL_NUM_PARAMS = {
    0: 3,    # SIMPLE_PINHOLE
    1: 4,    # PINHOLE
    2: 4,    # SIMPLE_RADIAL
    3: 5,    # RADIAL
    4: 8,    # OPENCV
    5: 8,    # OPENCV_FISHEYE
    6: 12,   # FULL_OPENCV
    7: 5,    # FOV
    8: 4,    # SIMPLE_RADIAL_FISHEYE
    9: 5,    # RADIAL_FISHEYE
    10: 12,  # THIN_PRISM_FISHEYE
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class ColmapQualityService:
    """COLMAP 稀疏重建质量分析模块。

    作用：
    1. 自动查找 COLMAP sparse 模型目录。
    2. 支持读取 COLMAP TXT 模型和 BIN 模型。
    3. 统计输入图像数量、注册图像数量、注册率、相机数量、稀疏点数量等指标。
    4. 生成 colmap_quality.json 和 colmap_quality.txt。
    5. 根据质量结果判断是否建议继续进入 3DGS 训练。
    """

    def __init__(
        self,
        system_config_path: str = "configs/system.yaml",
        colmap_config_path: str = "configs/colmap.yaml",
    ) -> None:
        self.pm = PathManager(system_config_path)

        config_path = Path(colmap_config_path)
        if not config_path.is_absolute():
            config_path = self.pm.project_root / config_path

        loaded = load_yaml(str(config_path))
        self.colmap_cfg = loaded.get("colmap", {})
        self.config_path = config_path

    def _resolve_user_path(self, value: Optional[str]) -> Optional[Path]:
        if not value:
            return None

        path = Path(str(value))
        if path.is_absolute():
            return path

        return (self.pm.project_root / path).resolve()

    def _count_input_images(self, image_dir: Optional[Path]) -> int:
        if not image_dir or not image_dir.exists() or not image_dir.is_dir():
            return 0

        try:
            return sum(
                1
                for path in image_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTS
            )
        except Exception:
            return 0

    def _candidate_sparse_dirs(
        self,
        workspace_path: Optional[Path],
        source_path: Optional[Path],
    ) -> List[Path]:
        candidates: List[Path] = []

        for base in [workspace_path, source_path]:
            if not base:
                continue

            candidates.extend(
                [
                    base / "sparse" / "0",
                    base / "sparse",
                    base / "distorted" / "sparse" / "0",
                    base / "distorted" / "sparse",
                ]
            )

        unique: List[Path] = []
        seen = set()

        for item in candidates:
            key = str(item.resolve()) if item.exists() else str(item)
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    def _model_files(self, sparse_dir: Path) -> Tuple[str, Dict[str, Path]]:
        txt_files = {
            "cameras": sparse_dir / "cameras.txt",
            "images": sparse_dir / "images.txt",
            "points3D": sparse_dir / "points3D.txt",
        }

        if all(path.exists() for path in txt_files.values()):
            return "txt", txt_files

        bin_files = {
            "cameras": sparse_dir / "cameras.bin",
            "images": sparse_dir / "images.bin",
            "points3D": sparse_dir / "points3D.bin",
        }

        if all(path.exists() for path in bin_files.values()):
            return "bin", bin_files

        merged = {**txt_files, **bin_files}
        return "missing", merged

    def _find_sparse_model(
        self,
        workspace_path: Optional[Path],
        source_path: Optional[Path],
    ) -> Tuple[Optional[Path], str, Dict[str, Path]]:
        fallback: Tuple[Optional[Path], str, Dict[str, Path]] = (None, "missing", {})

        for sparse_dir in self._candidate_sparse_dirs(workspace_path, source_path):
            model_format, files = self._model_files(sparse_dir)

            if model_format in {"txt", "bin"}:
                return sparse_dir, model_format, files

            if fallback[0] is None:
                fallback = (sparse_dir, model_format, files)

        return fallback

    @staticmethod
    def _is_int(value: str) -> bool:
        try:
            int(value)
            return True
        except Exception:
            return False

    def _parse_text_model(self, files: Dict[str, Path]) -> Dict[str, Any]:
        cameras = 0
        registered_images = 0
        total_points2d = 0
        matched_points2d = 0
        points3d = 0
        total_track_length = 0
        reprojection_errors: List[float] = []

        cameras_path = files.get("cameras")
        if cameras_path and cameras_path.exists():
            for line in cameras_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    cameras += 1

        images_path = files.get("images")
        if images_path and images_path.exists():
            lines = [
                line.strip()
                for line in images_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            i = 0
            while i < len(lines):
                parts = lines[i].split()

                # images.txt 中每张图像通常占两行：
                # 第一行：IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
                # 第二行：POINTS2D[]，格式为 X Y POINT3D_ID
                if len(parts) >= 10 and self._is_int(parts[0]):
                    registered_images += 1

                    if i + 1 < len(lines):
                        point_tokens = lines[i + 1].split()
                        total_points2d += len(point_tokens) // 3

                        for j in range(2, len(point_tokens), 3):
                            if j < len(point_tokens):
                                try:
                                    if int(float(point_tokens[j])) != -1:
                                        matched_points2d += 1
                                except Exception:
                                    pass

                    i += 2
                else:
                    i += 1

        points_path = files.get("points3D")
        if points_path and points_path.exists():
            for line in points_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) < 8:
                    continue

                points3d += 1

                try:
                    reprojection_errors.append(float(parts[7]))
                except Exception:
                    pass

                total_track_length += max(0, (len(parts) - 8) // 2)

        return {
            "camera_count": cameras,
            "registered_image_count": registered_images,
            "point3d_count": points3d,
            "total_points2d": total_points2d,
            "matched_points2d": matched_points2d,
            "mean_track_length": round(total_track_length / points3d, 4) if points3d else 0,
            "mean_reprojection_error": (
                round(sum(reprojection_errors) / len(reprojection_errors), 4)
                if reprojection_errors
                else None
            ),
        }

    def _read_c_string(self, f: Any) -> str:
        data = bytearray()

        while True:
            ch = f.read(1)
            if not ch or ch == b"\x00":
                break
            data.extend(ch)

        return data.decode("utf-8", errors="replace")

    def _parse_binary_model(self, files: Dict[str, Path]) -> Dict[str, Any]:
        cameras = 0
        registered_images = 0
        total_points2d = 0
        matched_points2d = 0
        points3d = 0
        total_track_length = 0
        reprojection_errors: List[float] = []

        cameras_path = files.get("cameras")
        if cameras_path and cameras_path.exists():
            with open(cameras_path, "rb") as f:
                count_raw = f.read(8)
                if len(count_raw) == 8:
                    cameras = struct.unpack("<Q", count_raw)[0]

                    for _ in range(cameras):
                        raw = f.read(24)
                        if len(raw) < 24:
                            break

                        _, model_id, _, _ = struct.unpack("<iiQQ", raw)
                        num_params = CAMERA_MODEL_NUM_PARAMS.get(model_id, 0)

                        if num_params:
                            f.read(8 * num_params)

        images_path = files.get("images")
        if images_path and images_path.exists():
            with open(images_path, "rb") as f:
                count_raw = f.read(8)
                if len(count_raw) == 8:
                    registered_images = struct.unpack("<Q", count_raw)[0]

                    for _ in range(registered_images):
                        # image_id: int
                        # qvec: 4 double
                        # tvec: 3 double
                        # camera_id: int
                        # 共 4 + 32 + 24 + 4 = 64 bytes
                        raw = f.read(64)
                        if len(raw) < 64:
                            break

                        self._read_c_string(f)

                        n_points_raw = f.read(8)
                        if len(n_points_raw) < 8:
                            break

                        n_points2d = struct.unpack("<Q", n_points_raw)[0]
                        total_points2d += int(n_points2d)

                        for _ in range(n_points2d):
                            point_raw = f.read(24)
                            if len(point_raw) < 24:
                                break

                            _, _, point3d_id = struct.unpack("<ddq", point_raw)
                            if point3d_id != -1:
                                matched_points2d += 1

        points_path = files.get("points3D")
        if points_path and points_path.exists():
            with open(points_path, "rb") as f:
                count_raw = f.read(8)
                if len(count_raw) == 8:
                    points3d = struct.unpack("<Q", count_raw)[0]

                    for _ in range(points3d):
                        # POINT3D_ID: uint64
                        # XYZ: 3 double
                        # RGB: 3 unsigned char
                        # ERROR: double
                        # 共 8 + 24 + 3 + 8 = 43 bytes
                        header = f.read(43)
                        if len(header) < 43:
                            break

                        error = struct.unpack("<d", header[-8:])[0]
                        reprojection_errors.append(float(error))

                        track_len_raw = f.read(8)
                        if len(track_len_raw) < 8:
                            break

                        track_length = struct.unpack("<Q", track_len_raw)[0]
                        total_track_length += int(track_length)

                        # 每个 track element: IMAGE_ID int32 + POINT2D_IDX int32 = 8 bytes
                        f.read(8 * track_length)

        return {
            "camera_count": cameras,
            "registered_image_count": registered_images,
            "point3d_count": points3d,
            "total_points2d": total_points2d,
            "matched_points2d": matched_points2d,
            "mean_track_length": round(total_track_length / points3d, 4) if points3d else 0,
            "mean_reprojection_error": (
                round(sum(reprojection_errors) / len(reprojection_errors), 4)
                if reprojection_errors
                else None
            ),
        }

    def _evaluate_quality(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        input_count = int(stats.get("input_image_count") or 0)
        registered_count = int(stats.get("registered_image_count") or 0)
        point_count = int(stats.get("point3d_count") or 0)
        model_format = stats.get("model_format")

        registration_rate = round(registered_count / input_count, 4) if input_count else 0
        stats["registration_rate"] = registration_rate
        stats["registration_rate_percent"] = round(registration_rate * 100, 2)

        suggestions: List[str] = []

        if model_format == "missing":
            return {
                "quality_level": "失败",
                "status": "failed",
                "can_continue": False,
                "suggestions": [
                    "未找到完整的 COLMAP sparse 模型文件，请检查 COLMAP 是否执行成功。"
                ],
            }

        if input_count <= 0:
            suggestions.append("未统计到输入图像数量，请检查 image_path 配置。")

        if registered_count <= 0:
            return {
                "quality_level": "失败",
                "status": "failed",
                "can_continue": False,
                "suggestions": [
                    "COLMAP 没有成功注册任何图像，无法进入 3DGS 训练。"
                ],
            }

        if registration_rate >= 0.8 and point_count >= 1000:
            quality_level = "良好"
            status = "pass"
            can_continue = True
            suggestions.append("图像注册率和稀疏点数量较好，可以进入 3DGS 训练。")
        elif registration_rate >= 0.5 and point_count >= 100:
            quality_level = "一般"
            status = "warning"
            can_continue = True
            suggestions.append(
                "重建结果可进入训练，但建议增加图像重叠度或拍摄数量以提升效果。"
            )
        else:
            quality_level = "较差"
            status = "warning"
            can_continue = True
            suggestions.append(
                "COLMAP 结果偏弱，后续 3DGS 训练效果可能不稳定。"
                "建议补充多视角图像、减少模糊图像并提高纹理覆盖。"
            )

        if point_count < 1000:
            suggestions.append("稀疏点数量偏少，可能影响相机位姿稳定性和训练质量。")

        if input_count and registration_rate < 0.8:
            suggestions.append(
                "图像注册率低于 80%，建议检查相邻图像重叠、曝光一致性和场景纹理。"
            )

        return {
            "quality_level": quality_level,
            "status": status,
            "can_continue": can_continue,
            "suggestions": suggestions,
        }

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _write_txt(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        suggestions = data.get("suggestions", []) or []

        lines = [
            "COLMAP 重建质量分析",
            "====================",
            f"场景名称: {data.get('scene_name', '')}",
            f"输入图像数量: {data.get('input_image_count', 0)}",
            f"注册图像数量: {data.get('registered_image_count', 0)}",
            f"图像注册率: {data.get('registration_rate_percent', 0)}%",
            f"相机数量: {data.get('camera_count', 0)}",
            f"稀疏点数量: {data.get('point3d_count', 0)}",
            f"平均观测数: {data.get('mean_track_length', 0)}",
            f"平均重投影误差: {data.get('mean_reprojection_error')}",
            f"模型格式: {data.get('model_format', '')}",
            f"质量等级: {data.get('quality_level', '')}",
            f"是否建议继续: {'是' if data.get('can_continue') else '否'}",
            "",
            "建议:",
        ]

        if suggestions:
            lines.extend([f"- {item}" for item in suggestions])
        else:
            lines.append("- 暂无")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def run(self) -> Dict[str, Any]:
        scene_name = self.colmap_cfg.get("scene_name", "unknown_scene")

        image_path = self._resolve_user_path(
            self.colmap_cfg.get("image_path") or self.colmap_cfg.get("raw_image_path")
        )

        workspace_path = self._resolve_user_path(
            self.colmap_cfg.get("workspace_path")
            or self.colmap_cfg.get("processed_scene_path")
        )

        source_path = self._resolve_user_path(self.colmap_cfg.get("source_path"))

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)

        logger = setup_logger(str(log_dir / "colmap_quality.log"))

        sparse_dir, model_format, files = self._find_sparse_model(
            workspace_path=workspace_path,
            source_path=source_path,
        )

        input_count = self._count_input_images(image_path)

        base_stats: Dict[str, Any] = {
            "scene_name": scene_name,
            "image_path": str(image_path) if image_path else "",
            "workspace_path": str(workspace_path) if workspace_path else "",
            "source_path": str(source_path) if source_path else "",
            "sparse_model_path": str(sparse_dir) if sparse_dir else "",
            "model_format": model_format,
            "input_image_count": input_count,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

        if model_format == "txt":
            parsed = self._parse_text_model(files)
        elif model_format == "bin":
            parsed = self._parse_binary_model(files)
        else:
            parsed = {
                "camera_count": 0,
                "registered_image_count": 0,
                "point3d_count": 0,
                "total_points2d": 0,
                "matched_points2d": 0,
                "mean_track_length": 0,
                "mean_reprojection_error": None,
            }

        result = {**base_stats, **parsed}
        result.update(self._evaluate_quality(result))

        output_dir = self.pm.scene_output(scene_name)
        output_dir.mkdir(parents=True, exist_ok=True)

        write_targets: List[Path] = []

        if workspace_path:
            write_targets.append(workspace_path)

        write_targets.append(output_dir)
        write_targets.append(log_dir)

        seen = set()

        for target_dir in write_targets:
            key = str(target_dir.resolve())

            if key in seen:
                continue

            seen.add(key)

            self._write_json(target_dir / "colmap_quality.json", result)
            self._write_txt(target_dir / "colmap_quality.txt", result)

        logger.info("COLMAP 质量分析完成: %s", result)

        print("COLMAP 质量分析完成")
        print("输入图像数量:", result.get("input_image_count", 0))
        print("注册图像数量:", result.get("registered_image_count", 0))
        print("图像注册率: {0}%".format(result.get("registration_rate_percent", 0)))
        print("稀疏点数量:", result.get("point3d_count", 0))
        print("质量等级:", result.get("quality_level", ""))

        if result.get("status") == "failed":
            raise RuntimeError(
                "COLMAP 质量分析失败：{0}".format(
                    "；".join(result.get("suggestions", []))
                )
            )

        return result