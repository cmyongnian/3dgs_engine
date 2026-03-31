from pathlib import Path

from core.video_service import VideoService
from core.colmap_service import ColmapService
from core.convert_service import ConvertService
from core.train_service import TrainerService
from core.render_service import RenderService
from core.metrics_service import MetricsService
from core.viewer_service import ViewerService
from core.config import load_yaml
from core.paths import PathManager


class PipelineService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        pipeline_config_path="configs/pipeline.yaml"
    ):
        self.system_config_path = system_config_path
        self.pm = PathManager(system_config_path)

        pipeline_config_path = Path(pipeline_config_path)
        if not pipeline_config_path.is_absolute():
            pipeline_config_path = self.pm.project_root / pipeline_config_path

        cfg = load_yaml(str(pipeline_config_path))["pipeline"]

        self.input_mode = cfg.get("input_mode", "images")
        self.run_video_extract_flag = cfg.get("run_video_extract", False)
        self.run_colmap_flag = cfg.get("run_colmap", False)
        self.run_convert_flag = cfg.get("run_convert", False)
        self.run_train_flag = cfg.get("run_train", True)
        self.run_render_flag = cfg.get("run_render", True)
        self.run_metrics_flag = cfg.get("run_metrics", True)
        self.launch_viewer_flag = cfg.get("launch_viewer", False)

    def run(self):
        print("===== 3DGS 平台一键流水线启动 =====")

        if self.input_mode == "video" and self.run_video_extract_flag:
            print(">>> 第一步：视频抽帧")
            video_service = VideoService(system_config_path=self.system_config_path)
            video_service.run()
            print(">>> 视频抽帧结束")

        if self.run_colmap_flag:
            print(">>> 第二步：COLMAP 重建")
            colmap_service = ColmapService(system_config_path=self.system_config_path)
            colmap_service.run()
            print(">>> COLMAP 重建结束")

        if self.run_convert_flag:
            print(">>> 第三步：执行 convert.py")
            convert_service = ConvertService(system_config_path=self.system_config_path)
            convert_service.run()
            print(">>> convert.py 执行结束")

        if self.run_train_flag:
            print(">>> 第四步：开始训练")
            trainer = TrainerService(system_config_path=self.system_config_path)
            trainer.run()
            print(">>> 训练结束")

        if self.run_render_flag:
            print(">>> 第五步：开始渲染")
            renderer = RenderService(system_config_path=self.system_config_path)
            renderer.run()
            print(">>> 渲染结束")

        if self.run_metrics_flag:
            print(">>> 第六步：开始评测")
            metrics = MetricsService(system_config_path=self.system_config_path)
            metrics.run()
            print(">>> 评测结束")

        if self.launch_viewer_flag:
            print(">>> 第七步：启动官方 Viewer")
            viewer = ViewerService(system_config_path=self.system_config_path)
            viewer.run()
            print(">>> Viewer 已启动")

        print("===== 一键流水线执行完成 =====")