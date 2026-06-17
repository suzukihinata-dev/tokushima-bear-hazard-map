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

# --- 対象範囲（徳島県） ---
PREF_CODE = "36"
# 徳島県を覆う1次メッシュ
PRIMARY_MESHES = ["5033", "5034", "5133", "5134"]
# 県全体の外接矩形 (lon_min, lat_min, lon_max, lat_max)
BBOX = (133.55, 33.45, 134.90, 34.35)

# 解析グリッドのメッシュ次数（3 = 3次メッシュ ≒ 1km）
MESH_LEVEL = 3

# DEM タイルのズーム（大きいほど高解像度・タイル数増）
DEM_ZOOM = 12

# --- データソース ---
KSJ_BASE = "https://nlftp.mlit.go.jp/ksj/gml/data/"
# 国土地理院 標高タイル（DEM10B, テキスト形式）
GSI_DEM_URL = "https://cyberjapandata.gsi.go.jp/xyz/dem/{z}/{x}/{y}.txt"

# 国土数値情報 ダウンロード対象（identifier -> zip相対パスのリスト）
KSJ_DATASETS: dict[str, list[str]] = {
    # 行政区域（県境ポリゴン）
    "N03": ["N03/N03-2024/N03-20240101_36_GML.zip"],
    # 河川データ
    "W05": ["W05/W05-06/W05-06_36_GML.zip"],
    # 森林地域（参考）
    "A45": ["A45/A45-19/A45-19_36_GML.zip"],
    # 土地利用細分メッシュ（徳島の1次メッシュ4枚, 平成28年/世界測地系jgd）
    "L03-b": [f"L03-b/L03-b-16/L03-b-16_{m}-jgd_GML.zip" for m in PRIMARY_MESHES],
}

# 土地利用細分メッシュ 土地利用コード
LANDUSE_FOREST = {"0500"}
LANDUSE_BUILDING = {"0700"}
LANDUSE_AGRI = {"0100", "0200"}

# 距離計算用の投影座標系（UTM zone 53N, 徳島を含む）
CRS_METRIC = "EPSG:32653"
CRS_WGS84 = "EPSG:4326"
