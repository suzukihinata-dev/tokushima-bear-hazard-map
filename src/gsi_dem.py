"""国土地理院 標高タイル(DEM10B)を取得し、ピクセル単位の標高・傾斜を返す。

各タイルは 256x256 の標高値テキスト（"e" は欠測=海域）。
GDAL/ラスタライブラリ不要で扱える。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import requests

import config as C

TILE = 256


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _tile_pixel_lonlat(x: int, y: int, z: int) -> tuple[np.ndarray, np.ndarray]:
    """タイル(x,y,z)の各ピクセル中心の経度・緯度グリッド(256x256)を返す。"""
    n = 2 ** z
    # 列(経度)：西→東
    px = x + (np.arange(TILE) + 0.5) / TILE
    lon = px / n * 360.0 - 180.0
    # 行(緯度)：北→南
    py = y + (np.arange(TILE) + 0.5) / TILE
    lat_r = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * py / n)))
    lat = np.degrees(lat_r)
    lon_grid, lat_grid = np.meshgrid(lon, lat)
    return lon_grid, lat_grid


def _fetch_tile(x: int, y: int, z: int) -> np.ndarray | None:
    cache = C.RAW / "dem" / f"{z}_{x}_{y}.txt"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        text = cache.read_text()
    else:
        url = C.GSI_DEM_URL.format(z=z, x=x, y=y)
        r = requests.get(url, timeout=60)
        if r.status_code != 200 or not r.text.strip():
            cache.write_text("")  # 欠測タイルも記録して再取得を防ぐ
            return None
        text = r.text
        cache.write_text(text)
    if not text.strip():
        return None
    arr = np.array(
        [[np.nan if v == "e" else float(v) for v in line.split(",")]
         for line in text.strip().splitlines()],
        dtype=float,
    )
    if arr.shape != (TILE, TILE):
        return None
    return arr


def _slope_deg(elev: np.ndarray, px_size_m: float) -> np.ndarray:
    """標高グリッドから各ピクセルの傾斜（度）を算出。"""
    gy, gx = np.gradient(elev, px_size_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def sample_dem(bbox: tuple[float, float, float, float], z: int) -> pd.DataFrame:
    """bbox内のDEMピクセルを (lat, lon, elev, slope) の DataFrame で返す。"""
    lon_min, lat_min, lon_max, lat_max = bbox
    x0, y0 = _lonlat_to_tile(lon_min, lat_max, z)  # 北西
    x1, y1 = _lonlat_to_tile(lon_max, lat_min, z)  # 南東
    frames = []
    n_tiles = (x1 - x0 + 1) * (y1 - y0 + 1)
    print(f"  DEM タイル取得: z={z}, {n_tiles} 枚")
    done = 0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            done += 1
            elev = _fetch_tile(x, y, z)
            if elev is None:
                continue
            lon_g, lat_g = _tile_pixel_lonlat(x, y, z)
            lat_c = float(np.nanmean(lat_g))
            px_size = 156543.03392 * math.cos(math.radians(lat_c)) / (2 ** z)
            slope = _slope_deg(elev, px_size)
            m = np.isfinite(elev)
            frames.append(pd.DataFrame({
                "lat": lat_g[m], "lon": lon_g[m],
                "elev": elev[m], "slope": slope[m],
            }))
            if done % 25 == 0:
                print(f"    {done}/{n_tiles}")
    if not frames:
        return pd.DataFrame(columns=["lat", "lon", "elev", "slope"])
    return pd.concat(frames, ignore_index=True)
