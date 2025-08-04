import json
import os
from pathlib import Path

# ------------------------------------------------------------------
# 数据持久化：存储路径设置
# ------------------------------------------------------------------
SAVE_PATH = Path(os.environ.get("HOME", ".")) / "todo.json"

def load_tasks() -> list[dict]:
    if SAVE_PATH.exists():
        try:
            return json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_tasks(tasks: list[dict]) -> None:
    SAVE_PATH.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")