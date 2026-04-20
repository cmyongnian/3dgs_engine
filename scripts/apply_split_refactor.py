from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path


MOVE_MAP = {
    'app': 'engine/app',
    'core': 'engine/core',
    'configs': 'engine/configs',
    'datasets': 'engine/datasets',
    'docs': 'engine/docs',
    'logs': 'engine/logs',
    'outputs': 'engine/outputs',
    'third_party': 'engine/third_party',
    'scrips': 'engine/scripts',
}


def replace_imports(root: Path) -> None:
    patterns = [
        (r'from\s+core(\.[\w_\.]+\s+import)', r'from engine.core\1'),
        (r'from\s+app(\.[\w_\.]+\s+import)', r'from engine.app\1'),
        (r'import\s+core(\.[\w_\.]+)?', lambda m: f"import engine.core{m.group(1) or ''}"),
        (r'import\s+app(\.[\w_\.]+)?', lambda m: f"import engine.app{m.group(1) or ''}"),
    ]

    for path in root.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        new_text = text
        for pattern, repl in patterns:
            new_text = re.sub(pattern, repl, new_text)
        if new_text != text:
            path.write_text(new_text, encoding='utf-8')
            print(f'已更新导入：{path}')


def touch_init_files(root: Path) -> None:
    for folder in [root / 'engine', root / 'engine' / 'app', root / 'engine' / 'core']:
        folder.mkdir(parents=True, exist_ok=True)
        init_file = folder / '__init__.py'
        if not init_file.exists():
            init_file.write_text('', encoding='utf-8')


def move_dirs(repo_root: Path) -> None:
    for old_name, new_name in MOVE_MAP.items():
        old_path = repo_root / old_name
        new_path = repo_root / new_name
        if not old_path.exists():
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            print(f'跳过已存在目录：{new_path}')
            continue
        shutil.move(str(old_path), str(new_path))
        print(f'已移动：{old_path} -> {new_path}')


def main() -> None:
    if len(sys.argv) < 2:
        print('用法：python scripts/apply_split_refactor.py 你的仓库路径')
        raise SystemExit(1)

    repo_root = Path(sys.argv[1]).resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f'仓库路径不存在：{repo_root}')

    move_dirs(repo_root)
    touch_init_files(repo_root)
    replace_imports(repo_root / 'engine')
    print('前后端分离基础迁移完成。接下来把 backend 和 frontend 复制进仓库根目录即可。')


if __name__ == '__main__':
    main()
