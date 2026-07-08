# 四国本島 クマ出没ハザードマップ

現在は徳島県のツキノワグマ出没記録（約20件）をもとに、**地形・土地利用などの地理的特徴が
既知の出没地点と「似ている」場所** を類似度スコア化し、四国本島全域の相対リスクを
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
| slope_p90 | 傾斜の90パーセンタイル | 同上（DEMから算出） |
| steep_ratio | 30度以上の急斜面ピクセル率 | 同上（DEMから算出） |
| relief | 起伏（メッシュ内標高の標準偏差） | 同上 |
| forest | 森林率 | 国土数値情報 土地利用細分メッシュ L03-b |
| building | 建物用地率 | 同上 |
| agri | 農地率 | 同上 |
| dist_river | 最近隣河川までの距離 | 国土数値情報 河川データ W05 |
| x_km / y_km | メッシュ中心の投影座標（km） | メッシュ形状から算出 |

出没地点には日付から `year` / `month` / `season` / `activity_period` /
`is_food_season` / `is_denning_season` / `moon_phase` を付与します。
また、`observed_elev` 列、または数値として入った `geo_confidence` 列がある場合は、
それを**出没地点の観測標高**として扱い、近傍メッシュの中から標高整合が最も高い
メッシュへ陽性サンプルを補正します。
出没点の説明情報としては、国土数値情報 W05 河川データから**点そのものから河川までの厳密距離**
も計算してポップアップに表示します。
任意で `data/weather_daily.csv` を置くと、同日の気象データも出没地点に結合され、
Webマップのポップアップに表示されます。

グリッド: 標準地域メッシュ3次（≒1km）／対象: 四国本島。
境界ポリゴンは国土数値情報 行政区域 N03 の徳島・香川・愛媛・高知を統合し、
最大ポリゴンを四国本島として採用します。

## ディレクトリ構成
```
.
├── requirements/requirements.md   要件定義書
├── data/
│   ├── sightings.csv              出没記録（手動ジオコーディング済み）
│   ├── weather_daily.csv          任意: 日別気象データ（手動配置）
│   ├── raw/                       KSJ/DEM 生データ（.gitignore, 自動取得）
│   └── processed/                 中間・成果物 GeoJSON
├── src/
│   ├── config.py                 共通設定（範囲・URL・パス）
│   ├── download_ksj.py           国土数値情報の取得・解凍
│   ├── gsi_dem.py                標高タイル取得・標高/傾斜算出
│   ├── build_features.py         3次メッシュ生成・特徴量集計
│   ├── score.py                  類似度ハザードスコア算出
│   ├── export_sightings.py       出没点GeoJSONのみ再生成
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

# 出没点の季節・天気属性だけを更新する場合
python src/export_sightings.py
```

### Web マップをローカルで確認
```bash
python -m http.server 8000 --directory docs
# ブラウザで http://localhost:8000 を開く
```

## 手法（スコアリング）
1. 各メッシュから、交差検証で効いた縮約特徴量
   `x = [elev, slope_p90, agri, log(dist_river), x_km, y_km]`
   を使用する
2. 全メッシュ統計で z-score 標準化
3. 各出没点を近傍メッシュへ仮対応させ、観測標高がある場合は標高差と距離の両方で
   最も整合するメッシュへ補正する
4. 各メッシュのスコア `= weighted_mean_i exp( −0.5 · ||x - pᵢ||² / h² )`
   （pᵢ: 出没サンプル、h: バンド幅）
5. サンプル重みは `YEAR_WEIGHT_DECAY=0.5` による年次減衰をかけ、最近年の出没をやや重視する
6. 0–1 に正規化して GeoJSON へ
- 妥当性確認: leave-one-out による出没メッシュの平均パーセンタイル（実行時にログ出力）

注:
現在の高精度化は、地形・土地利用に加えて `x_km / y_km` の広域位置コンテキストも使っています。
したがって、純粋な「生息地条件だけの類似度」ではなく、現時点の出没分布傾向も反映したスコアです。

## 天気・季節データの追加
`data/weather_daily.csv` は以下の列に対応しています。`date` は必須で、それ以外は任意です。

```csv
date,station,station_lat,station_lon,weather,temp_avg,temp_max,temp_min,precipitation,snowfall,sunshine,wind_speed
2025-07-13,木頭,33.82,134.20,晴,25.3,30.1,21.2,0.0,0.0,8.4,1.8
```

`station_lat` と `station_lon` がある場合は、同じ日付の観測値から出没地点に最も近い観測所を採用します。
ない場合は `date` だけで結合します。気象値はハザードスコアにはまだ入れず、まず出没点の説明情報として重ねています。

## データの手動ダウンロード（自動取得が失敗した場合）
国土数値情報ダウンロードサイト <https://nlftp.mlit.go.jp/ksj/> から四国4県（36/37/38/39）の
行政区域(N03)・河川(W05)・土地利用細分メッシュ(L03-b, 四国本島を覆う1次メッシュ群) を
取得し、`data/raw/<識別子>/` 配下に解凍してから `python src/pipeline.py --no-download` を実行してください。

## 出典・ライセンス
- 国土数値情報（行政区域・河川・土地利用細分メッシュ）／国土交通省
- 地理院タイル（標高タイル・淡色地図）／国土地理院
- 出没記録は公開情報をもとに手動整理。標高情報がある場合は `observed_elev` として、
  互換入力では数値の `geo_confidence` として扱えます。
