"""presence-only 特徴空間類似度モデルでハザードスコアを算出する。

各メッシュの特徴ベクトルを標準化し、出没メッシュ集合との
マハラノビス距離に基づく Gaussian カーネルの平均をスコアとする。
「既知の出没地点と地理的に似た場所」ほど高得点になる。

入力 : data/processed/grid_features.geojson, data/sightings.csv
出力 : data/processed/grid_scores.geojson, data/processed/sightings.geojson
"""
from __future__ import annotations

import shutil

import geopandas as gpd
import numpy as np
import pandas as pd

import config as C
from sightings_utils import (
    extract_geo_confidence_label,
    extract_observed_elev,
    match_sightings_to_grid,
    point_river_distances,
)
import weather_features

FEATURES = [
    "elev",
    "slope",
    "slope_p90",
    "steep_ratio",
    "relief",
    "forest",
    "building",
    "agri",
    "dist_river",
]
BANDWIDTH = 1.0  # Gaussian カーネルのバンド幅


def _normalize_sightings(sightings: pd.DataFrame) -> pd.DataFrame:
    out = sightings.copy()
    out["observed_elev"] = out.apply(extract_observed_elev, axis=1)
    if "geo_confidence" in out.columns:
        labels = out.apply(extract_geo_confidence_label, axis=1)
        if labels.notna().any():
            out["geo_confidence"] = labels
        else:
            out = out.drop(columns=["geo_confidence"])
    return out


def _transform_features(X: np.ndarray) -> np.ndarray:
    out = X.astype(float).copy()
    out[:, FEATURES.index("dist_river")] = np.log1p(out[:, FEATURES.index("dist_river")])
    return out


def _feature_matrix(grid: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = _transform_features(grid[FEATURES].to_numpy(dtype=float))
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    return Z, mu, sd


def _cov_inv(Z: np.ndarray) -> np.ndarray:
    cov = np.cov(Z, rowvar=False)
    cov += np.eye(cov.shape[0]) * 1e-3  # 正則化（特異行列回避）
    return np.linalg.inv(cov)


def _similarity(Z: np.ndarray, P: np.ndarray, cov_inv: np.ndarray, h: float) -> np.ndarray:
    """各行 Z について presence 集合 P との Gaussian カーネル平均を返す。"""
    scores = np.zeros(len(Z))
    for p in P:
        d = Z - p
        m2 = np.einsum("ij,jk,ik->i", d, cov_inv, d)  # マハラノビス距離^2
        scores += np.exp(-0.5 * m2 / (h * h))
    return scores / len(P)


def _match_presence_samples(
    grid: gpd.GeoDataFrame,
    sightings: pd.DataFrame,
    mu: np.ndarray,
    sd: np.ndarray,
) -> tuple[np.ndarray, pd.DataFrame, dict[str, float]]:
    grid_raw = grid[FEATURES].to_numpy(dtype=float)
    matches = match_sightings_to_grid(grid, sightings, C.MESH_LEVEL)

    samples: list[np.ndarray] = []

    for row_idx, match in matches.iterrows():
        observed_elev = sightings.iloc[row_idx]["observed_elev"]
        best_idx = int(match["matched_idx"])
        sample = grid_raw[best_idx].copy()
        if pd.notna(observed_elev):
            sample[FEATURES.index("elev")] = float(observed_elev)
        samples.append(sample)

    P = _transform_features(np.vstack(samples))
    P = (P - mu) / sd
    diagnostics = {
        "sample_count": float(len(samples)),
        "unique_meshes": float(matches["matched_meshcode"].nunique()),
        "adjusted_count": float(matches["mesh_adjusted"].sum()),
        "mean_move_km": float(matches["mesh_center_distance_km"].mean()),
        "mean_elev_gap_m": float(matches["elev_gap_m"].dropna().mean())
        if matches["elev_gap_m"].notna().any()
        else float("nan"),
    }
    return P, matches, diagnostics


def _loo_check(Z: np.ndarray, P: np.ndarray, matched_idx: np.ndarray, cov_inv: np.ndarray) -> float:
    """leave-one-out: 各出没メッシュが全体で上位何%に入るかの平均。"""
    if len(P) <= 1:
        return float("nan")
    pcts = []
    for k in range(len(P)):
        others = np.delete(P, k, axis=0)
        s = _similarity(Z, others, cov_inv, BANDWIDTH)
        rank = (s < s[matched_idx[k]]).mean()  # 自分より低いスコアの割合
        pcts.append(rank)
    return float(np.mean(pcts)) if pcts else float("nan")


def main() -> int:
    print("[score]")
    grid = gpd.read_file(C.PROCESSED / "grid_features.geojson")
    sightings = pd.read_csv(C.SIGHTINGS_CSV)
    sightings = weather_features.enrich_sightings(sightings)
    sightings = _normalize_sightings(sightings)
    sightings["point_dist_river"] = point_river_distances(sightings)

    Z, mu, sd = _feature_matrix(grid)
    cov_inv = _cov_inv(Z)
    P, matches, diag = _match_presence_samples(grid, sightings, mu, sd)
    matched_idx = matches["matched_idx"].to_numpy(dtype=int)
    print(
        "  出没サンプル:"
        f" {int(diag['sample_count'])}件 / {int(diag['unique_meshes'])}メッシュ"
        f" / 標高補正で再割当 {int(diag['adjusted_count'])}件"
    )
    print(f"  平均メッシュ中心距離: {diag['mean_move_km']:.2f} km")
    if not np.isnan(diag["mean_elev_gap_m"]):
        print(f"  割当メッシュ平均との差標高: {diag['mean_elev_gap_m']:.1f} m")

    raw = _similarity(Z, P, cov_inv, BANDWIDTH)
    score = (raw - raw.min()) / (raw.max() - raw.min() + 1e-12)
    grid["score"] = np.round(score, 4)

    loo = _loo_check(Z, P, matched_idx, cov_inv)
    print(f"  leave-one-out 平均パーセンタイル: {loo*100:.1f}% (高いほど良い)")

    # 出力（軽量化のため小数桁を抑える）
    for col in FEATURES:
        grid[col] = grid[col].round(2)
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    grid.to_file(C.PROCESSED / "grid_scores.geojson", driver="GeoJSON")

    matched_grid = grid.iloc[matched_idx].reset_index(drop=True)
    sightings = sightings.reset_index(drop=True).copy()
    sightings["matched_meshcode"] = matches["matched_meshcode"].to_numpy()
    sightings["matched_score"] = np.round(score[matched_idx], 4)
    sightings["mesh_adjusted"] = matches["mesh_adjusted"].to_numpy()
    sightings["mesh_center_distance_km"] = matches["mesh_center_distance_km"].round(2).to_numpy()
    sightings["mesh_elev_gap_m"] = matches["elev_gap_m"].round(1).to_numpy()
    sightings["point_dist_river"] = sightings["point_dist_river"].round(1)
    context_columns = {
        "mesh_elev": "elev",
        "mesh_slope": "slope",
        "mesh_slope_p90": "slope_p90",
        "mesh_steep_ratio": "steep_ratio",
        "mesh_relief": "relief",
        "mesh_forest": "forest",
        "mesh_building": "building",
        "mesh_agri": "agri",
        "mesh_dist_river": "dist_river",
    }
    for out_col, grid_col in context_columns.items():
        sightings[out_col] = matched_grid[grid_col].round(2).to_numpy()

    sg = gpd.GeoDataFrame(
        sightings,
        geometry=gpd.points_from_xy(sightings["lon"], sightings["lat"]),
        crs=C.CRS_WGS84,
    )
    sg.to_file(C.PROCESSED / "sightings.geojson", driver="GeoJSON")

    # Webマップ用にコピー（GitHub Pages は docs/ を配信）
    C.DOCS_DATA.mkdir(parents=True, exist_ok=True)
    for name in ("grid_scores.geojson", "sightings.geojson"):
        shutil.copy(C.PROCESSED / name, C.DOCS_DATA / name)
    print("  -> grid_scores.geojson / sightings.geojson (+ docs/data)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
