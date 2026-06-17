"""徳島県を3次メッシュでグリッド化し、地理的特徴量を集計する。

特徴量: 標高(elev) / 傾斜(slope) / 起伏(relief) /
        森林率(forest) / 建物用地率(building) / 農地率(agri) /
        最近隣河川距離(dist_river)
出力: data/processed/grid_features.geojson
"""
from __future__ import annotations

import glob

import geopandas as gpd
import jismesh.utils as ju
import numpy as np
import pandas as pd
from shapely.geometry import box

import config as C
import gsi_dem


def _load_boundary() -> gpd.GeoDataFrame:
    shp = sorted(glob.glob(str(C.RAW / "N03" / "**" / "*.shp"), recursive=True))
    if not shp:
        raise FileNotFoundError("N03 shapefile が見つかりません。download_ksj を先に実行してください。")
    gdf = gpd.read_file(shp[0])
    if gdf.crs is None:
        gdf = gdf.set_crs(C.CRS_WGS84)
    boundary = gdf.to_crs(C.CRS_WGS84).union_all()
    return gpd.GeoDataFrame(geometry=[boundary], crs=C.CRS_WGS84)


def _build_grid(boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = boundary.total_bounds
    dlat, dlon = 1 / 120, 1 / 80  # 3次メッシュのサイズ
    lats = np.arange(miny, maxy + dlat, dlat)
    lons = np.arange(minx, maxx + dlon, dlon)
    lon_g, lat_g = np.meshgrid(lons, lats)
    codes = ju.to_meshcode(lat_g.ravel(), lon_g.ravel(), C.MESH_LEVEL)
    codes = pd.unique(codes.astype(np.int64))
    sw_lat, sw_lon = ju.to_meshpoint(codes, 0, 0)
    ne_lat, ne_lon = ju.to_meshpoint(codes, 1, 1)
    geom = [box(a, b, c, d) for a, b, c, d in zip(sw_lon, sw_lat, ne_lon, ne_lat)]
    grid = gpd.GeoDataFrame(
        {"meshcode": codes.astype(str)}, geometry=geom, crs=C.CRS_WGS84
    )
    # 県内（重心が県境内）のメッシュのみ残す
    cent = grid.geometry.centroid
    inside = cent.within(boundary.geometry.iloc[0])
    grid = grid[inside].reset_index(drop=True)
    print(f"  グリッド: {len(grid)} メッシュ（3次, ≒1km）")
    return grid


def _terrain_features(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    dem = gsi_dem.sample_dem(C.BBOX, C.DEM_ZOOM)
    if dem.empty:
        print("  !! DEM が取得できませんでした")
        return pd.DataFrame(columns=["meshcode", "elev", "slope", "relief"])
    dem["meshcode"] = ju.to_meshcode(
        dem["lat"].to_numpy(), dem["lon"].to_numpy(), C.MESH_LEVEL
    ).astype(str)
    agg = dem.groupby("meshcode").agg(
        elev=("elev", "mean"),
        slope=("slope", "mean"),
        relief=("elev", "std"),
    ).reset_index()
    agg["relief"] = agg["relief"].fillna(0.0)
    print(f"  地形特徴量: {len(agg)} メッシュ")
    return agg


def _norm_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d+)")[0].str.zfill(4)


def _landuse_features(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    shps = sorted(glob.glob(str(C.RAW / "L03-b" / "**" / "*.shp"), recursive=True))
    if not shps:
        print("  !! L03-b が見つかりません。土地利用特徴量はスキップ")
        return pd.DataFrame(columns=["meshcode", "forest", "building", "agri"])
    known = C.LANDUSE_FOREST | C.LANDUSE_BUILDING | C.LANDUSE_AGRI | {
        "0600", "0901", "0902", "1000", "1100", "1400", "1500", "1600"
    }
    parts = []
    for shp in shps:
        gdf = gpd.read_file(shp, bbox=C.BBOX)
        if gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(C.CRS_WGS84)
        gdf = gdf.to_crs(C.CRS_WGS84)
        # 土地利用コードの列を自動検出
        code_col = None
        for col in gdf.columns:
            if col == "geometry":
                continue
            vals = _norm_code(gdf[col].dropna().astype(str).head(200))
            if vals.isin(known).mean() > 0.8:
                code_col = col
                break
        if code_col is None:
            print(f"    !! 土地利用コード列を特定できず: {shp}")
            continue
        cent = gdf.geometry.representative_point()
        sub = pd.DataFrame({
            "code": _norm_code(gdf[code_col]),
            "meshcode": ju.to_meshcode(
                cent.y.to_numpy(), cent.x.to_numpy(), C.MESH_LEVEL
            ).astype(str),
        })
        parts.append(sub)
    if not parts:
        return pd.DataFrame(columns=["meshcode", "forest", "building", "agri"])
    lu = pd.concat(parts, ignore_index=True)
    lu = lu[lu["meshcode"].isin(set(grid["meshcode"]))]
    grp = lu.groupby("meshcode")
    total = grp.size()
    forest = grp["code"].apply(lambda s: s.isin(C.LANDUSE_FOREST).sum())
    building = grp["code"].apply(lambda s: s.isin(C.LANDUSE_BUILDING).sum())
    agri = grp["code"].apply(lambda s: s.isin(C.LANDUSE_AGRI).sum())
    out = pd.DataFrame({
        "forest": forest / total,
        "building": building / total,
        "agri": agri / total,
    }).reset_index()
    print(f"  土地利用特徴量: {len(out)} メッシュ")
    return out


def _river_distance(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    shps = sorted(glob.glob(str(C.RAW / "W05" / "**" / "*.shp"), recursive=True))
    line_shps = [s for s in shps if "Stream" in s or "stream" in s] or shps
    if not line_shps:
        print("  !! W05 が見つかりません。河川距離はスキップ")
        return pd.DataFrame(columns=["meshcode", "dist_river"])
    rivers = pd.concat(
        [gpd.read_file(s) for s in line_shps], ignore_index=True
    )
    rivers = gpd.GeoDataFrame(rivers, geometry="geometry", crs=line_shps and None)
    if rivers.crs is None:
        rivers = rivers.set_crs(C.CRS_WGS84)
    rivers = rivers[rivers.geometry.type.isin(["LineString", "MultiLineString"])]
    rivers_m = rivers.to_crs(C.CRS_METRIC)
    cent = grid.copy()
    cent["geometry"] = cent.geometry.centroid
    cent_m = cent.to_crs(C.CRS_METRIC)
    joined = gpd.sjoin_nearest(
        cent_m[["meshcode", "geometry"]], rivers_m[["geometry"]],
        distance_col="dist_river",
    )
    out = joined.groupby("meshcode")["dist_river"].min().reset_index()
    print(f"  河川距離: {len(out)} メッシュ")
    return out


def main() -> int:
    print("[build_features]")
    boundary = _load_boundary()
    grid = _build_grid(boundary)
    for feat in (_terrain_features(grid), _landuse_features(grid), _river_distance(grid)):
        if not feat.empty:
            grid = grid.merge(feat, on="meshcode", how="left")
    # 欠損補完
    for col, fill in [
        ("elev", 0.0), ("slope", 0.0), ("relief", 0.0),
        ("forest", 0.0), ("building", 0.0), ("agri", 0.0),
    ]:
        if col in grid:
            grid[col] = grid[col].fillna(fill)
    if "dist_river" in grid:
        grid["dist_river"] = grid["dist_river"].fillna(grid["dist_river"].max())
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    out = C.PROCESSED / "grid_features.geojson"
    grid.to_file(out, driver="GeoJSON")
    print(f"  -> {out} ({len(grid)} メッシュ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
