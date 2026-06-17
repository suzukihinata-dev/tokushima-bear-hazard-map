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
import jismesh.utils as ju
import numpy as np
import pandas as pd

import config as C

FEATURES = ["elev", "slope", "relief", "forest", "building", "agri", "dist_river"]
BANDWIDTH = 1.0  # Gaussian カーネルのバンド幅


def _feature_matrix(grid: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = grid[FEATURES].to_numpy(dtype=float).copy()
    # 河川距離は裾の長い分布なので対数化
    j = FEATURES.index("dist_river")
    X[:, j] = np.log1p(X[:, j])
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


def _assign_presence(grid: gpd.GeoDataFrame, sightings: pd.DataFrame) -> np.ndarray:
    codes = ju.to_meshcode(
        sightings["lat"].to_numpy(), sightings["lon"].to_numpy(), C.MESH_LEVEL
    ).astype(str)
    code_to_idx = {c: i for i, c in enumerate(grid["meshcode"])}
    idx = sorted({code_to_idx[c] for c in codes if c in code_to_idx})
    return np.array(idx, dtype=int)


def _loo_check(Z: np.ndarray, pres_idx: np.ndarray, cov_inv: np.ndarray) -> float:
    """leave-one-out: 各出没メッシュが全体で上位何%に入るかの平均。"""
    pcts = []
    for k in range(len(pres_idx)):
        others = Z[np.delete(pres_idx, k)]
        s = _similarity(Z, others, cov_inv, BANDWIDTH)
        rank = (s < s[pres_idx[k]]).mean()  # 自分より低いスコアの割合
        pcts.append(rank)
    return float(np.mean(pcts)) if pcts else float("nan")


def main() -> int:
    print("[score]")
    grid = gpd.read_file(C.PROCESSED / "grid_features.geojson")
    sightings = pd.read_csv(C.SIGHTINGS_CSV)

    Z, _, _ = _feature_matrix(grid)
    cov_inv = _cov_inv(Z)
    pres_idx = _assign_presence(grid, sightings)
    print(f"  出没メッシュ数: {len(pres_idx)} / 全メッシュ {len(grid)}")

    raw = _similarity(Z, Z[pres_idx], cov_inv, BANDWIDTH)
    score = (raw - raw.min()) / (raw.max() - raw.min() + 1e-12)
    grid["score"] = np.round(score, 4)

    loo = _loo_check(Z, pres_idx, cov_inv)
    print(f"  leave-one-out 平均パーセンタイル: {loo*100:.1f}% (高いほど良い)")

    # 出力（軽量化のため小数桁を抑える）
    for col in FEATURES:
        grid[col] = grid[col].round(2)
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    grid.to_file(C.PROCESSED / "grid_scores.geojson", driver="GeoJSON")

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
