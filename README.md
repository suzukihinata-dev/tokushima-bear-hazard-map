# 徳島県 クマ出没ハザードマップ

徳島県のツキノワグマ出没記録（約20件）をもとに、**地形・土地利用などの地理的特徴が
既知の出没地点と「似ている」場所** を類似度スコア化し、県全域の相対リスクを
ヒートマップとして可視化する Web マップです。

出没データが少数のため単純な点密度では危険箇所を表現できません。そこで
**presence-only の特徴空間類似度モデル**（マハラノビス距離 + Gaussian カーネル）を用い、
「過去の出没地点と地理的に類似した場所ほど高リスク」と推定します。

👉 公開マップ（GitHub Pages）: *リポジトリの Settings → Pages 有効化後に表示される URL*

> ⚠️ 本マップは少数データに基づく統計的推定です。スコアが低い場所の安全を保証するものではありません。

## 特徴量とデータソース
| 特徴量 | 内容 | データ |
|--------|------|--------|
| elev | 平均標高 | 国土地理院 標高タイル(DEM10B) |
| slope | 平均傾斜 | 同上（DEMから算出） |
| relief | 起伏（メッシュ内標高の標準偏差） | 同上 |
| forest | 森林率 | 国土数値情報 土地利用細分メッシュ L03-b |
| building | 建物用地率 | 同上 |
| agri | 農地率 | 同上 |
| dist_river | 最近隣河川までの距離 | 国土数値情報 河川データ W05 |

グリッド: 標準地域メッシュ3次（≒1km）／対象: 徳島県（都道府県コード36）。
県境ポリゴンは国土数値情報 行政区域 N03 を使用。

## ディレクトリ構成
```
.
├── requirements/requirements.md   要件定義書
├── data/
│   ├── sightings.csv              出没記録（手動ジオコーディング済み）
│   ├── raw/                       KSJ/DEM 生データ（.gitignore, 自動取得）
│   └── processed/                 中間・成果物 GeoJSON
├── src/
│   ├── config.py                 共通設定（範囲・URL・パス）
│   ├── download_ksj.py           国土数値情報の取得・解凍
│   ├── gsi_dem.py                標高タイル取得・標高/傾斜算出
│   ├── build_features.py         3次メッシュ生成・特徴量集計
│   ├── score.py                  類似度ハザードスコア算出
│   └── pipeline.py               一括実行
└── docs/                          Web マップ（GitHub Pages 配信対象）
    ├── index.html / app.js / style.css
    └── data/                      grid_scores.geojson / sightings.geojson
```

## セットアップと実行
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 生データ取得 → 特徴量集計 → スコア算出 → docs/data へ出力
python src/pipeline.py
# データ取得済みなら（再計算のみ）
python src/pipeline.py --no-download
```

### Web マップをローカルで確認
```bash
python -m http.server 8000 --directory docs
# ブラウザで http://localhost:8000 を開く
```

## 手法（スコアリング）
1. 各メッシュの特徴ベクトル `x = [elev, slope, relief, forest, building, agri, log(dist_river)]`
2. 全メッシュ統計で z-score 標準化
3. 全メッシュから正則化付き共分散 Σ を推定
4. 各メッシュのスコア `= mean_i exp( −0.5 · d_M(x, pᵢ)² / h² )`
   （pᵢ: 出没メッシュ、d_M: マハラノビス距離、h: バンド幅）
5. 0–1 に正規化して GeoJSON へ
- 妥当性確認: leave-one-out による出没メッシュの平均パーセンタイル（実行時にログ出力）

## データの手動ダウンロード（自動取得が失敗した場合）
国土数値情報ダウンロードサイト <https://nlftp.mlit.go.jp/ksj/> から徳島県(36)の
行政区域(N03)・河川(W05)・土地利用細分メッシュ(L03-b, 1次メッシュ 5033/5034/5133/5134) を
取得し、`data/raw/<識別子>/` 配下に解凍してから `python src/pipeline.py --no-download` を実行してください。

## 出典・ライセンス
- 国土数値情報（行政区域・河川・土地利用細分メッシュ）／国土交通省
- 地理院タイル（標高タイル・淡色地図）／国土地理院
- 出没記録は公開情報をもとに手動整理。位置は地名・ランドマークからの近似値（`geo_confidence` に精度を記載）。
