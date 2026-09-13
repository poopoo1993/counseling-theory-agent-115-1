"""不需連線或 Secrets 的專案自我檢查。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.theory_library import SCHOOLS  # noqa: E402


def main() -> int:
    errors: list[str] = []
    if len(SCHOOLS) != 11:
        errors.append(f"學派數應為 11，目前為 {len(SCHOOLS)}")
    for school_id, school in SCHOOLS.items():
        techniques = school.get("techniques", [])
        ids = [t.get("id") for t in techniques]
        defaults = school.get("experience_default", [])
        if len(techniques) != 5:
            errors.append(f"{school_id} 技巧數不是 5")
        if len(set(ids)) != 5:
            errors.append(f"{school_id} 技巧 ID 重複")
        if len(defaults) != 3 or not set(defaults).issubset(set(ids)):
            errors.append(f"{school_id} 預設體驗技巧設定錯誤")
    required = [
        ROOT / "app.py",
        ROOT / "requirements.txt",
        ROOT / ".streamlit" / "secrets.toml.example",
        ROOT / "src" / "data_store.py",
        ROOT / "src" / "prompts.py",
    ]
    for path in required:
        if not path.exists():
            errors.append(f"缺少檔案：{path.relative_to(ROOT)}")
    if errors:
        print("檢查失敗：")
        for item in errors:
            print(f"- {item}")
        return 1
    print("專案檢查通過：11 學派、每學派 5 技巧、體驗預設 3 技巧與必要檔案均正確。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
