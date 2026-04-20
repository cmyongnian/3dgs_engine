from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = [ROOT / "engine" / "app", ROOT / "engine" / "core"]

REPLACEMENTS = [
    ("from core.", "from engine.core."),
    ("from core import", "from engine.core import"),
    ("import core.", "import engine.core."),
    ("from app.", "from engine.app."),
    ("from app import", "from engine.app import"),
    ("import app.", "import engine.app."),
]

def main():
    changed_files = []

    for base_dir in TARGET_DIRS:
        if not base_dir.exists():
            continue

        for py_file in base_dir.rglob("*.py"):
            old_text = py_file.read_text(encoding="utf-8")
            new_text = old_text

            for old, new in REPLACEMENTS:
                new_text = new_text.replace(old, new)

            if new_text != old_text:
                py_file.write_text(new_text, encoding="utf-8", newline="\n")
                changed_files.append(py_file.relative_to(ROOT))

    print(f"已修改 {len(changed_files)} 个文件：")
    for item in changed_files:
        print(f" - {item}")

if __name__ == "__main__":
    main()