# 四国本島 クマ出没ハザードマップ

四国本島を対象に、過去のツキノワグマ出没地点と地形・土地利用が似ている場所を推定し、相対的なハザードスコアをグラデーションで表示するWebマップです。

## 公開マップ

- Vercel: [https://bear-bice.vercel.app/](https://bear-bice.vercel.app/)
- GitHub Pages: GitHubリポジトリの `Settings` → `Pages` で、`main` ブランチの `/docs` を公開元に設定

ソースコード: [suzukihinata-dev/tokushima-bear-hazard-map](https://github.com/suzukihinata-dev/tokushima-bear-hazard-map)

表示範囲は四国本島です。徳島・香川・愛媛・高知の行政区域をもとに本島の境界を作成し、周辺の島しょ部は対象外にしています。

GitHub Pagesの公開元をリポジトリルート（`/`）にした場合も、ルートの `index.html` から `docs/` へ移動して同じマップを表示します。

本マップのスコアは、過去の出没地点と地理的特徴が似ている度合いを表す**相対的な推定値**です。発生確率や安全を保証するものではなく、低いスコアの場所が安全であることを意味しません。

## 主な機能

- 四国本島全域のハザードスコアを、青から赤へのグラデーションで表示
- 地図を拡大・縮小しても、グラデーションレイヤーと地図の位置を同期して表示
- ハザード領域をクリックして、ハザードスコア、標高、傾斜、森林率、建物用地率、河川までの距離を確認（利用可能な項目のみ表示）
- 出没地点を、季節・月・秋の採食期で絞り込み
- 出没地点のポップアップで、日時、場所、状況、痕跡種別、観測標高、河川までの実距離を確認（河川データがある場合）
- 任意で日別気象データを追加し、出没地点のポップアップに表示

## 現在の入力データ

現在の `data/sightings.csv` には、徳島県を中心とした45件の記録が入っています。記録期間は2004年から2026年です。今後、四国各県の出没データを追加できる構成にしています。

出没記録の必須列は次のとおりです。

```csv
id,date,place,situation,evidence_type,lat,lon
```

標高を利用する場合は、今後追加するデータでは `observed_elev` 列を推奨します。

```csv
id,date,place,situation,evidence_type,lat,lon,observed_elev
1,2026-05-19,勝浦郡上勝町,皮剥ぎ痕を発見,皮剥ぎ,33.930,134.315,1076.4
```

過去データとの互換性のため、`geo_confidence` に数値が入っている場合も標高として扱います。ただし、`geo_confidence` という列名は位置精度を意味するため、新しいデータでは `observed_elev` を使用してください。`geo_confidence` に `high`、`medium`、`low` などの文字列を入れた場合は、位置精度の説明として表示されます。

## 分析に使用する特徴量

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

## スコアリングの概要

1. 四国本島の標準地域メッシュ3次（約1km）を解析単位として作成します。
2. 各メッシュについて、標高、傾斜、農地率、河川距離、広域位置を特徴量化します。スコア計算には `elev`、`slope_p90`、`agri`、`log(dist_river)`、`x_km`、`y_km` を使用します。
3. 特徴量を標準化し、過去の出没地点に近い特徴を持つメッシュほど高くなるGaussianカーネルでスコアを計算します。
4. 年次減衰を適用し、最近年の記録をやや重視します。
5. `observed_elev` または数値の `geo_confidence` がある出没地点は、位置と標高の整合性を使って対応メッシュを補正します。
6. スコアを表示用に0〜1へ整え、Webマップでは低リスクを青、高リスクを赤として連続的に表示します。

現在のモデルは、生息環境の特徴だけでなく `x_km` / `y_km` による出没分布の位置的な傾向も使用しています。そのため、因果関係を示すものではなく、現在のデータに対する類似度マップです。実行時には、出没地点を1件ずつ除外するleave-one-out検証の平均パーセンタイルもログに出力します。

気象データは現在、ハザードスコアの計算には使用せず、出没地点の説明情報として表示します。

## ディレクトリ構成

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
│   └── data/                     Vercel配信用のGeoJSON
├── requirements.txt              Python依存パッケージ
└── vercel.json                   Vercelの静的配信設定
```

Vercelではビルド処理を行わず、`docs/` 以下を静的ファイルとして配信します。解析結果を更新した場合は、生成された `docs/data/` のファイルもコミットして公開データを更新します。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 全工程を実行

国土数値情報と標高データを取得し、特徴量・スコア・Webマップ用GeoJSONを生成します。

```bash
python src/pipeline.py
```

### ダウンロード済みデータで再計算

`data/raw/` に必要なデータがある場合は、ダウンロードを省略できます。

```bash
python src/pipeline.py --no-download
```

### 出没地点だけを再出力

季節・河川距離・標高などの出没地点ポップアップ情報を更新する場合に使用します。

```bash
python src/export_sightings.py
```

### ローカルで確認

```bash
python -m http.server 8000 --directory docs
```

ブラウザで [http://localhost:8000](http://localhost:8000) を開いてください。`docs/` を直接開くのではなく、HTTPサーバー経由で確認します。

## 気象データの追加

必要な場合だけ `data/weather_daily.csv` を作成します。`date` は必須で、その他の列は任意です。

```csv
date,station,station_lat,station_lon,weather,temp_avg,temp_max,temp_min,precipitation,snowfall,sunshine,wind_speed
2025-07-13,木頭,33.82,134.20,晴,25.3,30.1,21.2,0.0,0.0,8.4,1.8
```

`station_lat` と `station_lon` がある場合は、同じ日付の観測所から出没地点に最も近い観測所の値を結合します。座標がない場合は、日付だけで結合します。

## データ取得に失敗した場合

[国土数値情報ダウンロードサイト](https://nlftp.mlit.go.jp/ksj/) から、四国4県（36・37・38・39）の次のデータを取得し、`data/raw/` 配下に解凍してください。

- 行政区域（N03）
- 河川（W05）
- 土地利用細分メッシュ（L03-b）

その後、次のコマンドを実行します。

```bash
python src/pipeline.py --no-download
```

## 出典・利用上の注意

- [国土数値情報](https://nlftp.mlit.go.jp/ksj/)（行政区域・河川・土地利用細分メッシュ）／国土交通省
- [地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)（標高タイル・淡色地図）／国土地理院
- 出没記録は公開情報をもとに整理したデータです。個々の記録の正確性・網羅性を保証するものではありません。

データ提供元の利用規約・出典表示条件に従って利用してください。

## 注意事項

- 本マップは防災機関・自治体などが提供する公式の危険区域情報ではありません。
- 出没記録が少なく、目撃されやすさや調査地点の偏りが含まれる可能性があります。
- 約1kmメッシュの相対評価であり、個別の道路・登山道・集落単位の危険度を直接示すものではありません。
- 画面上の赤色は、入力データに基づく相対的な類似度が高いことを示します。実際の出没を予測する確率ではありません。
