"""生成历史数据校验清单，供打开的页面检查新发布版本。"""
import hashlib
import json
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def main():
    files = {name: hashlib.sha256((SITE / name).read_bytes()).hexdigest()
             for name in ("data.js", "broad.js", "minute-history.json", "etf-margin.json",
                          "leverage.json", "themes.json", "market-status.json", "funds.json",
                          "fund-facts.json", "data-quality.json", "rotation.json")}
    version = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    manifest = {"version": version, "files": files}
    (SITE / "history-manifest.json").write_bytes(
        (json.dumps(manifest, separators=(",", ":")) + "\n").encode())
    print(f"历史数据版本 {version[:12]}")


if __name__ == "__main__":
    main()
