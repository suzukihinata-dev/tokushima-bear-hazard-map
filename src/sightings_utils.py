"""sightings.csv の任意列と位置ベース文脈を扱うヘルパー。"""
from __future__ import annotations

import glob
from math import cos, radians
from typing import Any, Mapping

import geopandas as gpd
import jismesh.utils as ju
import numpy as np
import pandas as pd

import config as C

ELEVATION_KEYS = ("observed_elev", "elevation", "sighting_elev", "geo_confidence")
INVALID_TEXT_VALUES = {"undefined", "null", "none", "nan", "na", "n/a"}
MATCH_SEARCH_KM = 2.5
MATCH_NEIGHBORS = 12
DISTANCE_MATCH_SCALE_KM = 0.8
ELEVATION_MATCH_SCALE_M = 180.0


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_observed_elev(row: Mapping[str, Any]) -> float | None:
    """出没地点の観測標高を返す。数値化できない場合は None。"""
    for key in ELEVATION_KEYS:
        if key not in row:
            continue
        value = _to_float(row.get(key))
        if value is None:
            continue
        if -500.0 <= value <= 5000.0:
            return value
    return None


def extract_geo_confidence_label(row: Mapping[str, Any]) -> str | None:
    """従来の位置精度ラベル(high/medium/low 等)だけを返す。"""
    value = row.get("geo_confidence")
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if text.lower() in INVALID_TEXT_VALUES:
        return None
    try:
        float(text)
        return None
    except ValueError:
        return text


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    radius = 6371.0
    p1 = radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * radius * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def match_sightings_to_grid(
    grid: gpd.GeoDataFrame,
    sightings: pd.DataFrame,
    mesh_level: int,
) -> pd.DataFrame:
    """各出没点を距離と標高整合性で最も妥当なメッシュへ対応付ける。"""
    if sightings.empty:
        return pd.DataFrame(
            columns=[
                "matched_idx",
                "matched_meshcode",
                "base_meshcode",
                "mesh_adjusted",
                "mesh_center_distance_km",
                "elev_gap_m",
            ]
        )

    bounds = grid.geometry.bounds
    grid_lats = ((bounds["miny"] + bounds["maxy"]) / 2).to_numpy(dtype=float)
    grid_lons = ((bounds["minx"] + bounds["maxx"]) / 2).to_numpy(dtype=float)
    grid_elev = grid["elev"].to_numpy(dtype=float) if "elev" in grid.columns else None
    code_to_idx = {str(code): i for i, code in enumerate(grid["meshcode"])}
    sighting_lats = pd.to_numeric(sightings["lat"], errors="coerce")
    sighting_lons = pd.to_numeric(sightings["lon"], errors="coerce")
    base_codes = ju.to_meshcode(
        sighting_lats.to_numpy(), sighting_lons.to_numpy(), mesh_level
    ).astype(str)

    rows: list[dict[str, Any]] = []
    for row, base_code in zip(sightings.itertuples(index=False), base_codes, strict=False):
        lat = float(row.lat)
        lon = float(row.lon)
        observed_elev = getattr(row, "observed_elev", None)
        observed_elev = float(observed_elev) if pd.notna(observed_elev) else None

        distances = haversine_km(lat, lon, grid_lats, grid_lons)
        nearest = np.argsort(distances)[:MATCH_NEIGHBORS]
        local = np.flatnonzero(distances <= MATCH_SEARCH_KM)
        candidates = np.unique(np.concatenate([nearest, local]))
        if not len(candidates):
            candidates = np.array([int(np.argmin(distances))], dtype=int)

        elev_gap = np.nan
        if observed_elev is not None and grid_elev is not None:
            costs = (
                (distances[candidates] / DISTANCE_MATCH_SCALE_KM) ** 2
                + ((grid_elev[candidates] - observed_elev) / ELEVATION_MATCH_SCALE_M) ** 2
            )
            best_idx = int(candidates[np.argmin(costs)])
            elev_gap = abs(grid_elev[best_idx] - observed_elev)
        else:
            best_idx = int(candidates[np.argmin(distances[candidates])])

        base_idx = code_to_idx.get(base_code)
        rows.append(
            {
                "matched_idx": best_idx,
                "matched_meshcode": str(grid.iloc[best_idx]["meshcode"]),
                "base_meshcode": base_code,
                "mesh_adjusted": base_idx != best_idx,
                "mesh_center_distance_km": float(distances[best_idx]),
                "elev_gap_m": float(elev_gap) if pd.notna(elev_gap) else np.nan,
            }
        )

    return pd.DataFrame(rows)


def load_rivers() -> gpd.GeoDataFrame:
    shps = sorted(glob.glob(str(C.RAW / "W05" / "**" / "*.shp"), recursive=True))
    line_shps = [s for s in shps if "Stream" in s or "stream" in s] or shps
    if not line_shps:
        return gpd.GeoDataFrame(geometry=[], crs=C.CRS_WGS84)

    rivers = pd.concat([gpd.read_file(s) for s in line_shps], ignore_index=True)
    rivers = gpd.GeoDataFrame(rivers, geometry="geometry", crs=line_shps and None)
    if rivers.crs is None:
        rivers = rivers.set_crs(C.CRS_WGS84)
    rivers = rivers[rivers.geometry.type.isin(["LineString", "MultiLineString"])]
    return rivers.to_crs(C.CRS_METRIC)


def point_river_distances(sightings: pd.DataFrame) -> pd.Series:
    """各出没点から最近隣河川までの厳密距離(m)を返す。"""
    if sightings.empty:
        return pd.Series(dtype=float)

    rivers = load_rivers()
    if rivers.empty:
        return pd.Series(np.nan, index=sightings.index, dtype=float)

    lons = pd.to_numeric(sightings["lon"], errors="coerce")
    lats = pd.to_numeric(sightings["lat"], errors="coerce")
    points = gpd.GeoDataFrame(
        {"row_id": sightings.index},
        geometry=gpd.points_from_xy(lons, lats),
        crs=C.CRS_WGS84,
    ).to_crs(C.CRS_METRIC)
    joined = gpd.sjoin_nearest(points, rivers[["geometry"]], distance_col="point_dist_river")
    dist = joined.groupby("row_id")["point_dist_river"].min()
    return dist.reindex(sightings.index)
