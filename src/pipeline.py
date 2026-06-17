"""前処理パイプライン一括実行。

  1. download_ksj : 国土数値情報の取得・解凍
  2. build_features: 3次メッシュ生成・特徴量集計
  3. score        : 類似度ハザードスコア算出・成果物GeoJSON出力

使い方:
  python src/pipeline.py            # 全工程
  python src/pipeline.py --no-download   # ダウンロードをスキップ
"""
from __future__ import annotations

import argparse

import build_features
import download_ksj
import score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="KSJダウンロードをスキップ")
    args = ap.parse_args()

    if not args.no_download:
        download_ksj.main()
    rc = build_features.main()
    if rc != 0:
        return rc
    return score.main()


if __name__ == "__main__":
    raise SystemExit(main())
