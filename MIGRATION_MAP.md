# 迁移映射表

## 根目录迁移

```text
原仓库根目录                    目标目录
app/                        ->  engine/app/
core/                       ->  engine/core/
configs/                    ->  engine/configs/
datasets/                   ->  engine/datasets/
docs/                       ->  engine/docs/
logs/                       ->  engine/logs/
outputs/                    ->  engine/outputs/
third_party/                ->  engine/third_party/
scrips/                     ->  engine/scripts/
```

## 导入修改规则

### 原入口层

```python
from core.pipeline_service import PipelineService
```

改成：

```python
from engine.core.pipeline_service import PipelineService
```

### 原服务层内部

```python
from core.config import load_yaml
from core.paths import PathManager
```

改成：

```python
from engine.core.config import load_yaml
from engine.core.paths import PathManager
```

## 运行命令修改

### 原来

```bash
python -m app.pipeline_main
python -m app.render_main
python -m app.metrics_main
python -m app.viewer_main
```

### 迁移后

```bash
python -m engine.app.pipeline_main
python -m engine.app.render_main
python -m engine.app.metrics_main
python -m engine.app.viewer_main
```

## 最重要的原因

你原项目当前已经把入口层和服务层拆开，最适合做标准前后端分离的方式不是推倒重写，而是把现有工程整体沉到 `engine/`，再在上面增加 `backend/` 和 `frontend/`。
