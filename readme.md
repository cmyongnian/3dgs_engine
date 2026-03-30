# 3DGS Platform

基于 **3D Gaussian Splatting (3DGS)** 的三维场景重建平台。  
本项目以官方 `gaussian-splatting` 开源实现为核心，围绕 **COLMAP → 数据转换 → 训练 → 渲染 → 指标评测 → Viewer 可视化** 的完整流程进行工程化封装，实现从多视角图像输入到三维场景重建与实时查看的完整平台。

---

## 1. 项目简介

本项目面向“基于高斯溅射的三维场景重建系统设计与实现”这一目标，构建了一套完整的 3DGS 平台。平台支持：

- 原始图像输入
- COLMAP 稀疏/自动重建
- 官方 `convert.py` 数据转换
- 3DGS 模型训练
- 离线渲染
- 指标评测（SSIM / PSNR / LPIPS）
- 官方 Viewer 实时查看
- 一键流水线调度

平台采用模块化设计，便于后续扩展 GUI、批量实验、训练恢复、低显存优化等功能。

---

## 2. 主要功能

### 2.1 数据处理
- 支持从原始多视角图像目录读取数据
- 支持调用 COLMAP 完成重建
- 支持将 COLMAP 输出接入官方 `convert.py`
- 自动生成 3DGS 可训练数据目录

### 2.2 模型训练
- 调用官方 `train.py` 进行高斯溅射训练
- 支持通过配置文件管理训练参数
- 支持低显存训练模式
- 自动记录训练日志

### 2.3 渲染与评测
- 调用官方 `render.py` 生成渲染图像
- 调用官方 `metrics.py` 计算 SSIM、PSNR、LPIPS
- 自动保存评测结果与日志

### 2.4 可视化
- 接入官方 Real-Time Viewer
- 支持训练完成后加载模型实时浏览
- 可作为平台流程最后一步自动启动

### 2.5 流水线调度
- 支持按配置执行：
  - COLMAP
  - convert.py
  - train
  - render
  - metrics
  - viewer

---

## 3. 项目结构

```text
3dgs_platform/
├── app/                         # 各模块运行入口
│   ├── main.py                  # 训练入口
│   ├── render_main.py           # 渲染入口
│   ├── metrics_main.py          # 评测入口
│   ├── viewer_main.py           # Viewer入口
│   ├── pipeline_main.py         # 一键流水线入口
│   ├── colmap_main.py           # COLMAP入口
│   └── convert_main.py          # convert.py入口
│
├── core/                        # 核心服务层
│   ├── config.py
│   ├── paths.py
│   ├── logger.py
│   ├── train_service.py
│   ├── render_service.py
│   ├── metrics_service.py
│   ├── viewer_service.py
│   ├── pipeline_service.py
│   ├── colmap_service.py
│   └── convert_service.py
│
├── configs/                     # 配置文件
│   ├── system.yaml
│   ├── train.yaml
│   ├── render.yaml
│   ├── metrics.yaml
│   ├── viewer.yaml
│   ├── pipeline.yaml
│   ├── colmap.yaml
│   └── convert.yaml
│
├── datasets/
│   ├── raw/                     # 原始图像
│   └── processed/               # COLMAP与转换后的数据
│
├── outputs/                     # 模型、渲染结果、评测结果
├── logs/                        # 日志
├── docs/                        # 设计文档
└── third_party/
    ├── gaussian-splatting/      # 官方3DGS仓库
    ├── colmap/                  # COLMAP程序
    └── viewers/                 # 官方viewer程序



    python -m app.colmap_main
  python -m app.convert_main
  python -m app.main
  python -m app.main
  python -m app.viewer_main
  python -m app.pipeline_main