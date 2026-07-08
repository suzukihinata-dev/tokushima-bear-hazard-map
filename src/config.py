"""共通設定（パス・対象範囲・データソースURL）。"""
from __future__ import annotations

from pathlib import Path

# --- パス ---
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
DOCS = ROOT / "docs"
DOCS_DATA = DOCS / "data"
SIGHTINGS_CSV = DATA / "sightings.csv"
WEATHER_DAILY_CSV = DATA / "weather_daily.csv"

# --- 対象範囲（四国本島） ---
TARGET_REGION = "四国本島"
PREF_CODES = ["36", "37", "38", "39"]
# 四国本島を覆う1次メッシュ（配布のある landuse メッシュのみ）
PRIMARY_MESHES = [
    "4932", "4933", "4934",
    "5032", "5033", "5034", "5035",
    "5132", "5133", "5134", "5135",
    "5232", "5233", "5234", "5235",
]
# 四国本島全体を覆う外接矩形 (lon_min, lat_min, lon_max, lat_max)
BBOX = (132.0, 32.6, 134.9, 34.5)

# 解析グリッドのメッシュ次数（3 = 3次メッシュ ≒ 1km）
MESH_LEVEL = 3

# DEM タイルのズーム（大きいほど高解像度・タイル数増）
# 四国全域では z=12 だと取得タイル数が過大になるため 10 に抑える。
DEM_ZOOM = 10

# --- データソース ---
KSJ_BASE = "https://nlftp.mlit.go.jp/ksj/gml/data/"
# 国土地理院 標高タイル（DEM10B, テキスト形式）
GSI_DEM_URL = "https://cyberjapandata.gsi.go.jp/xyz/dem/{z}/{x}/{y}.txt"

# 国土数値情報 ダウンロード対象（identifier -> zip相対パスのリスト）
KSJ_DATASETS: dict[str, list[str]] = {
    # 行政区域（四国4県を統合して本島境界を抽出）
    "N03": [f"N03/N03-2024/N03-20240101_{code}_GML.zip" for code in PREF_CODES],
    # 河川データ
    "W05": [f"W05/W05-06/W05-06_{code}_GML.zip" for code in PREF_CODES],
    # 土地利用細分メッシュ（四国本島を覆う1次メッシュ, 平成28年/世界測地系jgd）
    "L03-b": [f"L03-b/L03-b-16/L03-b-16_{m}-jgd_GML.zip" for m in PRIMARY_MESHES],
}

# 土地利用細分メッシュ 土地利用コード
LANDUSE_FOREST = {"0500"}
LANDUSE_BUILDING = {"0700"}
LANDUSE_AGRI = {"0100", "0200"}

# 距離計算用の投影座標系（UTM zone 53N, 四国本島の大半を含む）
CRS_METRIC = "EPSG:32653"
CRS_WGS84 = "EPSG:4326"
