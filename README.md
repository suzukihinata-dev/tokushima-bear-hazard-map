# 四国本島 クマ出没ハザードマップ / Shikoku Mainland Bear Sighting Hazard Map

[日本語](#日本語) | [English](#english)

## 日本語

四国本島を対象に、過去のツキノワグマ出没地点と地形・土地利用が似ている場所を推定し、相対的なハザードスコアをグラデーションで表示するWebマップです。

### 公開マップ

- Vercel: [https://bear-bice.vercel.app/](https://bear-bice.vercel.app/)
- GitHub Pages: [https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/](https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/)

ソースコード: [suzukihinata-dev/tokushima-bear-hazard-map](https://github.com/suzukihinata-dev/tokushima-bear-hazard-map)

表示範囲は四国本島です。徳島・香川・愛媛・高知の行政区域をもとに本島の境界を作成し、周辺の島しょ部は対象外にしています。

GitHub Pagesは元リポジトリの `main` ブランチにある `/docs` を公開元として使用しています。公開元をリポジトリルート（`/`）にした場合も、ルートの `index.html` から `docs/` へ移動して同じマップを表示します。

本マップのスコアは、過去の出没地点と地理的特徴が似ている度合いを表す**相対的な推定値**です。発生確率や安全を保証するものではなく、低いスコアの場所が安全であることを意味しません。

### 主な機能

- 四国本島全域のハザードスコアを、青から赤へのグラデーションで表示
- 地図を拡大・縮小しても、グラデーションレイヤーと地図の位置を同期して表示
- ハザード領域をクリックして、ハザードスコア、標高、傾斜、森林率、建物用地率、河川までの距離を確認（利用可能な項目のみ表示）
- 出没地点を、季節・月・秋の採食期で絞り込み
- 出没地点のポップアップで、日時、場所、状況、痕跡種別、観測標高、河川までの実距離を確認（河川データがある場合）
- 任意で日別気象データを追加し、出没地点のポップアップに表示

### 現在の入力データ

現在の `data/sightings.csv` には、徳島県を中心とした45件の記録が入っています。記録期間は2004年から2026年です。今後、四国各県の出没データを追加できる構成にしています。

出没記録の基本列は次のとおりです。

```csv
id,date,place,situation,evidence_type,lat,lon
```

標高を利用する場合は、今後追加するデータでは `observed_elev` 列を推奨します。

```csv
id,date,place,situation,evidence_type,lat,lon,observed_elev
1,2026-05-19,勝浦郡上勝町,皮剥ぎ痕を発見,皮剥ぎ,33.930,134.315,1076.4
```

過去データとの互換性のため、`geo_confidence` に数値が入っている場合も標高として扱います。ただし、`geo_confidence` という列名は位置精度を意味するため、新しいデータでは `observed_elev` を使用してください。`geo_confidence` に `high`、`medium`、`low` などの文字列を入れた場合は、位置精度の説明として表示されます。

### 分析に使用する特徴量

| 特徴量 | 内容 | データソース |
| --- | --- | --- |
| `elev` | メッシュ内の平均標高 | [国土地理院の標高タイル](https://maps.gsi.go.jp/development/elevation_s.html)（DEM） |
| `slope` | 平均傾斜 | DEMから算出 |
| `slope_p90` | 傾斜の90パーセンタイル | DEMから算出 |
| `steep_ratio` | 30度以上の急斜面の割合 | DEMから算出 |
| `relief` | メッシュ内標高の標準偏差 | DEMから算出 |
| `forest` | 森林の割合 | [国土数値情報](https://nlftp.mlit.go.jp/ksj/) 土地利用細分メッシュ（L03-b） |
| `building` | 建物用地の割合 | 国土数値情報 L03-b |
| `agri` | 農地の割合 | 国土数値情報 L03-b |
| `dist_river` | メッシュ中心から最近隣河川までの距離 | 国土数値情報 河川（W05） |
| `x_km` / `y_km` | メッシュ中心の投影座標 | メッシュ形状から算出 |

出没地点には、日付から季節・月・活動期・秋の採食期・冬眠期・月齢指数を付与します。河川データがある場合は、各出没地点から河川までの厳密距離も計算します。

### スコアリングの概要

1. 四国本島の標準地域メッシュ3次（約1km）を解析単位として作成します。
2. 各メッシュについて、標高、傾斜、農地率、河川距離、広域位置を特徴量化します。スコア計算には `elev`、`slope_p90`、`agri`、`log(dist_river)`、`x_km`、`y_km` を使用します。
3. 特徴量を標準化し、過去の出没地点に近い特徴を持つメッシュほど高くなるGaussianカーネルでスコアを計算します。
4. 年次減衰を適用し、最近年の記録をやや重視します。
5. `observed_elev` または数値の `geo_confidence` がある出没地点は、位置と標高の整合性を使って対応メッシュを補正します。
6. スコアを表示用に0〜1へ整え、Webマップでは低リスクを青、高リスクを赤として連続的に表示します。

現在のモデルは、生息環境の特徴だけでなく `x_km` / `y_km` による出没分布の位置的な傾向も使用しています。そのため、因果関係を示すものではなく、現在のデータに対する類似度マップです。実行時には、出没地点を1件ずつ除外するleave-one-out検証の平均パーセンタイルもログに出力します。

気象データは現在、ハザードスコアの計算には使用せず、出没地点の説明情報として表示します。

### ディレクトリ構成

```text
.
├── index.html                    GitHub Pagesのルート公開用入口
├── requirements/requirements.md   要件定義書
├── data/
│   ├── sightings.csv              出没記録
│   ├── weather_daily.example.csv  気象データの入力例
│   ├── weather_daily.csv          任意。実際に使用する日別気象データ
│   ├── raw/                       国土数値情報・DEMの生データ（Git管理外）
│   └── processed/                 中間生成物（Git管理外）
├── src/
│   ├── config.py                 対象範囲・データソース・パスの設定
│   ├── download_ksj.py           国土数値情報の取得・解凍
│   ├── gsi_dem.py                DEM取得と標高・傾斜の計算
│   ├── build_features.py         解析メッシュと特徴量の生成
│   ├── score.py                  ハザードスコアの計算とGeoJSON出力
│   ├── export_sightings.py       出没地点GeoJSONの再生成
│   └── pipeline.py               前処理から出力までの一括実行
├── docs/
│   ├── index.html                WebマップのHTML
│   ├── app.js                    Leafletによる表示処理
│   ├── style.css                 Webマップのスタイル
│   └── data/                     Vercel・GitHub Pages配信用のGeoJSON
├── requirements.txt              Python依存パッケージ
└── vercel.json                   Vercelの静的配信設定
```

VercelとGitHub Pagesではビルド処理を行わず、`docs/` 以下を静的ファイルとして配信します。解析結果を更新した場合は、生成された `docs/data/` のファイルもコミットして両方の公開データを更新します。

### セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 全工程を実行

国土数値情報と標高データを取得し、特徴量・スコア・Webマップ用GeoJSONを生成します。

```bash
python src/pipeline.py
```

#### ダウンロード済みデータで再計算

`data/raw/` に必要なデータがある場合は、ダウンロードを省略できます。

```bash
python src/pipeline.py --no-download
```

#### 出没地点だけを再出力

季節・河川距離・標高などの出没地点ポップアップ情報を更新する場合に使用します。

```bash
python src/export_sightings.py
```

#### ローカルで確認

```bash
python -m http.server 8000 --directory docs
```

ブラウザで [http://localhost:8000](http://localhost:8000) を開いてください。`docs/` を直接開くのではなく、HTTPサーバー経由で確認します。

### 気象データの追加

必要な場合だけ `data/weather_daily.csv` を作成します。`date` は必須で、その他の列は任意です。

```csv
date,station,station_lat,station_lon,weather,temp_avg,temp_max,temp_min,precipitation,snowfall,sunshine,wind_speed
2025-07-13,木頭,33.82,134.20,晴,25.3,30.1,21.2,0.0,0.0,8.4,1.8
```

`station_lat` と `station_lon` がある場合は、同じ日付の観測所から出没地点に最も近い観測所の値を結合します。座標がない場合は、日付だけで結合します。

### データ取得に失敗した場合

[国土数値情報ダウンロードサイト](https://nlftp.mlit.go.jp/ksj/) から、四国4県（36・37・38・39）の次のデータを取得し、`data/raw/` 配下に解凍してください。

- 行政区域（N03）
- 河川（W05）
- 土地利用細分メッシュ（L03-b）

その後、次のコマンドを実行します。

```bash
python src/pipeline.py --no-download
```

### 出典・利用上の注意

- [国土数値情報](https://nlftp.mlit.go.jp/ksj/)（行政区域・河川・土地利用細分メッシュ）／国土交通省
- [地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)（標高タイル・淡色地図）／国土地理院
- 出没記録は公開情報をもとに整理したデータです。個々の記録の正確性・網羅性を保証するものではありません。

データ提供元の利用規約・出典表示条件に従って利用してください。

### 注意事項

- 本マップは防災機関・自治体などが提供する公式の危険区域情報ではありません。
- 出没記録が少なく、目撃されやすさや調査地点の偏りが含まれる可能性があります。
- 約1kmメッシュの相対評価であり、個別の道路・登山道・集落単位の危険度を直接示すものではありません。
- 画面上の赤色は、入力データに基づく相対的な類似度が高いことを示します。実際の出没を予測する確率ではありません。

## English

## Public Maps

- Vercel: [https://bear-bice.vercel.app/](https://bear-bice.vercel.app/)
- GitHub Pages: [https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/](https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/)

Source repository: [suzukihinata-dev/tokushima-bear-hazard-map](https://github.com/suzukihinata-dev/tokushima-bear-hazard-map)

The map covers the Shikoku mainland. The boundary is created from the administrative areas of Tokushima, Kagawa, Ehime, and Kochi prefectures. Surrounding islands are excluded.

GitHub Pages serves the `/docs` directory from the `main` branch. If the repository root is selected as the Pages source instead, the root `index.html` redirects to `docs/` and opens the same map.

The score is a **relative statistical estimate** of similarity to past sighting locations. It is not a probability of bear occurrence and does not guarantee safety in low-score areas.

## Features

- Display the hazard score for the entire Shikoku mainland as a blue-to-red gradient
- Keep the gradient layer aligned with the base map while zooming and panning
- Click a hazard area to inspect the score, elevation, slope, forest ratio, building-land ratio, and distance to the nearest river when available
- Filter sighting locations by season, month, or autumn feeding season
- View the date, location, situation, evidence type, observed elevation, and exact distance to a river in a sighting popup when the data is available
- Optionally add daily weather data and display it in sighting popups

## Current Input Data

`data/sightings.csv` currently contains 45 records, mainly from Tokushima Prefecture, covering 2004 through 2026. The project is structured so that additional sightings from all four prefectures in Shikoku can be added later.

The basic sighting columns are:

```csv
id,date,place,situation,evidence_type,lat,lon
```

For elevation data, use the `observed_elev` column for new records.

```csv
id,date,place,situation,evidence_type,lat,lon,observed_elev
1,2026-05-19,勝浦郡上勝町,皮剥ぎ痕を発見,皮剥ぎ,33.930,134.315,1076.4
```

For backward compatibility, a numeric value in `geo_confidence` is also treated as observed elevation. Because `geo_confidence` normally means location accuracy, new data should use `observed_elev` instead. Text values such as `high`, `medium`, and `low` are retained and displayed as location-accuracy labels.

## Features Used for Analysis

| Feature | Description | Data source |
| --- | --- | --- |
| `elev` | Mean elevation within the mesh | [Geospatial Information Authority of Japan elevation tiles](https://maps.gsi.go.jp/development/elevation_s.html) (DEM) |
| `slope` | Mean slope | Calculated from the DEM |
| `slope_p90` | 90th percentile of slope | Calculated from the DEM |
| `steep_ratio` | Ratio of pixels with a slope of at least 30 degrees | Calculated from the DEM |
| `relief` | Standard deviation of elevation within the mesh | Calculated from the DEM |
| `forest` | Forest ratio | [National Land Numerical Information](https://nlftp.mlit.go.jp/ksj/), land-use subdivision mesh (L03-b) |
| `building` | Building-land ratio | National Land Numerical Information L03-b |
| `agri` | Agricultural-land ratio | National Land Numerical Information L03-b |
| `dist_river` | Distance from the mesh center to the nearest river | National Land Numerical Information, rivers (W05) |
| `x_km` / `y_km` | Projected coordinates of the mesh center | Calculated from the mesh geometry |

Sighting records are enriched with the season, month, activity period, autumn feeding season flag, denning season flag, and moon-phase index derived from the date. When river data is available, the exact distance from each sighting point to the nearest river is also calculated.

## Scoring Method

1. Create third-order standard regional meshes, approximately 1 km wide, across the Shikoku mainland.
2. Calculate elevation, slope, agricultural-land ratio, river distance, and broad-scale spatial context for each mesh. The score uses `elev`, `slope_p90`, `agri`, `log(dist_river)`, `x_km`, and `y_km`.
3. Standardize the features and calculate a Gaussian-kernel score. Meshes with features closer to known sighting locations receive higher scores.
4. Apply year-based decay so that more recent records receive somewhat greater weight.
5. When `observed_elev` or a numeric `geo_confidence` is available, match each sighting to a mesh using both geographic distance and elevation consistency.
6. Normalize the score for display to the 0–1 range. The map displays lower scores in blue and higher scores in red as a continuous gradient.

The current model uses both habitat-related features and the `x_km` / `y_km` spatial context of known sightings. It therefore represents similarity to the current data distribution, not a proven causal relationship. Each run also logs the mean percentile from a leave-one-out validation of the sighting locations.

Weather data is currently displayed as supplementary information for sightings and is not included in the hazard-score calculation.

## Directory Structure

```text
.
├── index.html                    Entry point for GitHub Pages root publishing
├── requirements/requirements.md   Requirements document
├── data/
│   ├── sightings.csv              Bear sighting records
│   ├── weather_daily.example.csv  Example weather-data input
│   ├── weather_daily.csv          Optional daily weather data
│   ├── raw/                       Raw KSJ and DEM data (not tracked by Git)
│   └── processed/                 Intermediate outputs (not tracked by Git)
├── src/
│   ├── config.py                 Target area, data sources, and path settings
│   ├── download_ksj.py           Download and extract National Land Numerical Information
│   ├── gsi_dem.py                Retrieve DEM data and calculate elevation and slope
│   ├── build_features.py         Build analysis meshes and aggregate features
│   ├── score.py                  Calculate hazard scores and export GeoJSON
│   ├── export_sightings.py       Regenerate the sighting GeoJSON
│   └── pipeline.py               Run the complete preprocessing pipeline
├── docs/
│   ├── index.html                Web-map HTML
│   ├── app.js                    Leaflet display logic
│   ├── style.css                 Web-map styles
│   └── data/                     GeoJSON served by Vercel and GitHub Pages
├── requirements.txt              Python dependencies
└── vercel.json                   Vercel static-deployment configuration
```

Vercel and GitHub Pages serve the `docs/` directory as static files without a build step. When analysis results are updated, commit the generated files in `docs/data/` so both public deployments use the updated data.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the Complete Pipeline

This downloads National Land Numerical Information and elevation data, then generates the features, scores, and GeoJSON files used by the web map.

```bash
python src/pipeline.py
```

### Recalculate with Downloaded Data

If the required files already exist under `data/raw/`, skip the download step:

```bash
python src/pipeline.py --no-download
```

### Regenerate Sighting Data Only

Use this command when updating seasonal, river-distance, elevation, or other sighting-popup information:

```bash
python src/export_sightings.py
```

### Run Locally

```bash
python -m http.server 8000 --directory docs
```

Open [http://localhost:8000](http://localhost:8000) in a browser. Use an HTTP server instead of opening files directly from the `docs/` directory.

## Adding Weather Data

Create `data/weather_daily.csv` only when weather information is needed. The `date` column is required; all other columns are optional.

```csv
date,station,station_lat,station_lon,weather,temp_avg,temp_max,temp_min,precipitation,snowfall,sunshine,wind_speed
2025-07-13,木頭,33.82,134.20,晴,25.3,30.1,21.2,0.0,0.0,8.4,1.8
```

When `station_lat` and `station_lon` are provided, the closest station to each sighting is selected from the records for the same date. Without station coordinates, records are joined by date only.

## If Automatic Data Download Fails

Download the following data for the four Shikoku prefectures (36, 37, 38, and 39) from the [National Land Numerical Information download site](https://nlftp.mlit.go.jp/ksj/), then extract it under `data/raw/`:

- Administrative areas (N03)
- Rivers (W05)
- Land-use subdivision mesh (L03-b)

Then run:

```bash
python src/pipeline.py --no-download
```

## Sources and Data Use

- [National Land Numerical Information](https://nlftp.mlit.go.jp/ksj/) (administrative areas, rivers, and land-use subdivision mesh), Ministry of Land, Infrastructure, Transport and Tourism, Japan
- [GSI Tiles](https://maps.gsi.go.jp/development/ichiran.html) (elevation and pale map tiles), Geospatial Information Authority of Japan
- Sighting records were organized from publicly available information. The accuracy and completeness of individual records are not guaranteed.

Follow the terms of use and attribution requirements of each data provider.

## Limitations

- This map is not an official hazard-area map provided by a disaster-management agency or local government.
- The number of sighting records is limited, and the data may contain biases in observation and survey locations.
- The map provides a relative assessment at approximately 1 km resolution; it does not directly represent risk for individual roads, trails, or settlements.
- Red areas indicate higher similarity to the input data. They do not represent the probability of an actual bear sighting.
