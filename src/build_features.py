"""四国4県の行政区域から四国本島だけを抽出し、3次メッシュ特徴量を集計する。

特徴量: 標高(elev) / 平均傾斜(slope) / 上位傾斜(slope_p90) /
        急斜面率(steep_ratio) / 起伏(relief) /
        森林率(forest) / 建物用地率(building) / 農地率(agri) /
        最近隣河川距離(dist_river) / メッシュ中心座標(x_km, y_km)
出力: data/processed/grid_features.geojson
"""
from __future__ import annotations

import glob

import geopandas as gpd
import jismesh.utils as ju
import numpy as np
import pandas as pd
from shapely.geometry import box
from shapely.prepared import prep

import config as C
import gsi_dem


def _iter_polygons(geometry) -> list:
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        polygons = []
        for part in geometry.geoms:
            polygons.extend(_iter_polygons(part))
        return polygons
    return []


def _load_boundary() -> gpd.GeoDataFrame:
    shp = sorted(glob.glob(str(C.RAW / "N03" / "**" / "*.shp"), recursive=True))
    if not shp:
        raise FileNotFoundError("N03 shapefile が見つかりません。download_ksj を先に実行してください。")
    frames = []
    for path in shp:
        gdf = gpd.read_file(path)
        if gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(C.CRS_WGS84)
        frames.append(gdf.to_crs(C.CRS_WGS84)[["geometry"]])
    if not frames:
        raise ValueError("N03 shapefile から境界を読み込めませんでした。")

    merged = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs=C.CRS_WGS84
    )
    dissolved = merged.geometry.union_all()
    polygons = _iter_polygons(dissolved)
    if not polygons:
        raise ValueError("境界ポリゴンを抽出できませんでした。")

    areas = gpd.GeoSeries(polygons, crs=C.CRS_WGS84).to_crs(C.CRS_METRIC).area
    mainland = polygons[int(areas.to_numpy().argmax())]
    return gpd.GeoDataFrame(geometry=[mainland], crs=C.CRS_WGS84)


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
    # 本島境界と交差するメッシュを残し、表示時は境界ポリゴンでクリップする。
    # これにより海岸や岬の先端が半セル分欠けるのを防ぐ。
    prepared_boundary = prep(boundary.geometry.iloc[0])
    inside = np.fromiter(
        (prepared_boundary.intersects(geom) for geom in grid.geometry),
        dtype=bool,
        count=len(grid),
    )
    grid = grid[inside].reset_index(drop=True)
    print(f"  グリッド: {len(grid)} メッシュ（3次, ≒1km）")
    return grid


def _terrain_features(grid: gpd.GeoDataFrame, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    dem = gsi_dem.sample_dem(bbox, C.DEM_ZOOM)
    if dem.empty:
        print("  !! DEM が取得できませんでした")
        return pd.DataFrame(
            columns=["meshcode", "elev", "slope", "slope_p90", "steep_ratio", "relief"]
        )
    dem["meshcode"] = ju.to_meshcode(
        dem["lat"].to_numpy(), dem["lon"].to_numpy(), C.MESH_LEVEL
    ).astype(str)
    agg = dem.groupby("meshcode").agg(
        elev=("elev", "mean"),
        slope=("slope", "mean"),
        slope_p90=("slope", lambda s: float(s.quantile(0.9))),
        steep_ratio=("slope", lambda s: float((s >= 30).mean())),
        relief=("elev", "std"),
    ).reset_index()
    agg["relief"] = agg["relief"].fillna(0.0)
    print(f"  地形特徴量: {len(agg)} メッシュ")
    return agg


def _norm_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d+)")[0].str.zfill(4)


def _landuse_features(
    grid: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float],
) -> pd.DataFrame:
    shps = sorted(glob.glob(str(C.RAW / "L03-b" / "**" / "*.shp"), recursive=True))
    if not shps:
        print("  !! L03-b が見つかりません。土地利用特徴量はスキップ")
        return pd.DataFrame(columns=["meshcode", "forest", "building", "agri"])
    known = C.LANDUSE_FOREST | C.LANDUSE_BUILDING | C.LANDUSE_AGRI | {
        "0600", "0901", "0902", "1000", "1100", "1400", "1500", "1600"
    }
    parts = []
    for shp in shps:
        gdf = gpd.read_file(shp, bbox=bbox)
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
    cent_m = grid.to_crs(C.CRS_METRIC).copy()
    cent_m["geometry"] = cent_m.geometry.centroid
    joined = gpd.sjoin_nearest(
        cent_m[["meshcode", "geometry"]], rivers_m[["geometry"]],
        distance_col="dist_river",
    )
    out = joined.groupby("meshcode")["dist_river"].min().reset_index()
    print(f"  河川距離: {len(out)} メッシュ")
    return out


def _spatial_context(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    grid_m = grid.to_crs(C.CRS_METRIC)
    cent = grid_m.geometry.centroid
    out = pd.DataFrame(
        {
            "meshcode": grid["meshcode"].to_numpy(),
            "x_km": cent.x.to_numpy(dtype=float) / 1000.0,
            "y_km": cent.y.to_numpy(dtype=float) / 1000.0,
        }
    )
    print(f"  空間文脈: {len(out)} メッシュ")
    return out


def main() -> int:
    print("[build_features]")
    boundary = _load_boundary()
    bbox = tuple(float(v) for v in boundary.total_bounds)
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    C.DOCS_DATA.mkdir(parents=True, exist_ok=True)
    boundary_out = C.PROCESSED / "pref_boundary.geojson"
    boundary.to_file(boundary_out, driver="GeoJSON")
    boundary.to_file(C.DOCS_DATA / "pref_boundary.geojson", driver="GeoJSON")
    print(f"  対象境界ポリゴン: {boundary_out}")
    grid = _build_grid(boundary)
    for feat in (
        _terrain_features(grid, bbox),
        _landuse_features(grid, bbox),
        _river_distance(grid),
        _spatial_context(grid),
    ):
        if not feat.empty:
            grid = grid.merge(feat, on="meshcode", how="left")
    # 欠損補完
    for col, fill in [
        ("elev", 0.0), ("slope", 0.0), ("slope_p90", 0.0), ("steep_ratio", 0.0), ("relief", 0.0),
        ("forest", 0.0), ("building", 0.0), ("agri", 0.0), ("x_km", 0.0), ("y_km", 0.0),
    ]:
        if col in grid:
            grid[col] = grid[col].fillna(fill)
    if "dist_river" in grid:
        grid["dist_river"] = grid["dist_river"].fillna(grid["dist_river"].max())
    out = C.PROCESSED / "grid_features.geojson"
    grid.to_file(out, driver="GeoJSON")
    print(f"  -> {out} ({len(grid)} メッシュ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
