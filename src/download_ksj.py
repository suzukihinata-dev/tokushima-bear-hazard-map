"""国土数値情報（KSJ）の必要データをダウンロード・解凍する。

取得済みファイルがあればスキップする（再実行に優しい）。
配布サイトの仕様変更などで失敗した場合は、READMEの手動DL手順を参照。
"""
from __future__ import annotations

import sys
import zipfile

import requests

import config as C


def _download(url: str, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (cached): {dest.name}")
        return dest
    print(f"  GET {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                f.write(chunk)
    print(f"  saved {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
    return dest


def _extract(zip_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)


def main() -> int:
    ok = True
    for ident, rel_paths in C.KSJ_DATASETS.items():
        print(f"[{ident}]")
        ds_dir = C.RAW / ident
        for rel in rel_paths:
            url = C.KSJ_BASE + rel
            name = rel.split("/")[-1]
            zip_path = ds_dir / name
            try:
                _download(url, zip_path)
                _extract(zip_path, ds_dir / name.replace(".zip", ""))
            except Exception as e:  # noqa: BLE001
                ok = False
                print(f"  !! 失敗: {name}: {e}", file=sys.stderr)
    print("KSJ download:", "OK" if ok else "一部失敗（READMEの手動DL手順参照）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
