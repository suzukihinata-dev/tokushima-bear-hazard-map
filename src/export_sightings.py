"""出没記録を Web マップ用 GeoJSON に変換する軽量ユーティリティ。"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import geopandas as gpd
import pandas as pd

import config as C
from sightings_utils import (
    extract_geo_confidence_label,
    extract_observed_elev,
    match_sightings_to_grid,
    point_river_distances,
)

ROOT = Path(__file__).resolve().parent.parent
SIGHTINGS_CSV = ROOT / "data" / "sightings.csv"
WEATHER_DAILY_CSV = ROOT / "data" / "weather_daily.csv"
OUT = ROOT / "docs" / "data" / "sightings.geojson"

SEASON_LABELS = {
    "spring": "春",
    "summer": "夏",
    "autumn": "秋",
    "winter": "冬",
}

ACTIVITY_LABELS = {
    "post_hibernation": "冬眠明け・春の移動期",
    "breeding": "繁殖期・行動圏拡大期",
    "hyperphagia": "秋の採食集中期",
    "denning": "冬眠期・低活動期",
}

WEATHER_COLUMNS = [
    "station",
    "station_lat",
    "station_lon",
    "weather",
    "temp_avg",
    "temp_max",
    "temp_min",
    "precipitation",
    "snowfall",
    "sunshine",
    "wind_speed",
]

GRID_CONTEXT_COLUMNS = {
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


def _season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def _activity_period(month: int) -> str:
    if month in (3, 4, 5):
        return "post_hibernation"
    if month in (6, 7, 8):
        return "breeding"
    if month in (9, 10, 11):
        return "hyperphagia"
    return "denning"


def _moon_phase_index(day: date) -> float:
    known_new_moon = date(2000, 1, 6)
    synodic_month = 29.53058867
    return ((day - known_new_moon).days % synodic_month) / synodic_month


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = radians(lat1)
    p2 = radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * radius * atan2(sqrt(a), sqrt(1 - a))


def _coerce(value: str):
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def _sighting_grid_context(sightings: list[dict]) -> list[dict]:
    grid_path = C.PROCESSED / "grid_scores.geojson"
    if not sightings or not grid_path.exists():
        return [{} for _ in sightings]

    grid = gpd.read_file(grid_path)
    df = pd.DataFrame(sightings)
    df["observed_elev"] = df.apply(extract_observed_elev, axis=1)
    df["point_dist_river"] = point_river_distances(df)
    matches = match_sightings_to_grid(grid, df, C.MESH_LEVEL)
    matched_idx = matches["matched_idx"].to_numpy(dtype=int)
    matched_grid = grid.iloc[matched_idx].reset_index(drop=True)

    contexts = []
    for idx in range(len(df)):
        ctx = {
            "matched_meshcode": matches.at[idx, "matched_meshcode"],
            "matched_score": round(float(matched_grid.at[idx, "score"]), 4),
            "mesh_adjusted": bool(matches.at[idx, "mesh_adjusted"]),
            "mesh_center_distance_km": round(float(matches.at[idx, "mesh_center_distance_km"]), 2),
        }
        elev_gap = matches.at[idx, "elev_gap_m"]
        if pd.notna(elev_gap):
            ctx["mesh_elev_gap_m"] = round(float(elev_gap), 1)
        point_dist_river = df.at[idx, "point_dist_river"]
        if pd.notna(point_dist_river):
            ctx["point_dist_river"] = round(float(point_dist_river), 1)
        for out_col, grid_col in GRID_CONTEXT_COLUMNS.items():
            ctx[out_col] = round(float(matched_grid.at[idx, grid_col]), 2)
        contexts.append(ctx)
    return contexts


def _weather_for_sighting(sighting: dict, weather_rows: list[dict]) -> dict:
    rows = [r for r in weather_rows if r.get("date") == sighting["date"]]
    if not rows:
        return {}

    if all("station_lat" in r and "station_lon" in r for r in rows):
        lat = float(sighting["lat"])
        lon = float(sighting["lon"])
        rows = [
            (
                _haversine_km(lat, lon, float(r["station_lat"]), float(r["station_lon"])),
                r,
            )
            for r in rows
            if r.get("station_lat") and r.get("station_lon")
        ]
        if not rows:
            return {}
        distance, row = min(rows, key=lambda item: item[0])
        out = {k: _coerce(row[k]) for k in WEATHER_COLUMNS if k in row}
        out["weather_station_distance_km"] = round(distance, 2)
        return out

    row = rows[0]
    return {k: _coerce(row[k]) for k in WEATHER_COLUMNS if k in row}


def main() -> int:
    sightings = _read_csv(SIGHTINGS_CSV)
    weather_rows = _read_csv(WEATHER_DAILY_CSV)
    grid_contexts = _sighting_grid_context(sightings)
    features = []

    for row, grid_context in zip(sightings, grid_contexts, strict=False):
        day = datetime.strptime(row["date"], "%Y-%m-%d").date()
        month = day.month
        season = _season(month)
        activity = _activity_period(month)
        props = {k: _coerce(v) for k, v in row.items()}
        observed_elev = extract_observed_elev(props)
        if observed_elev is not None:
            props["observed_elev"] = round(observed_elev, 1)
        geo_confidence = extract_geo_confidence_label(props)
        if geo_confidence is not None:
            props["geo_confidence"] = geo_confidence
        else:
            props.pop("geo_confidence", None)
        props.update(
            {
                "year": day.year,
                "month": month,
                "day_of_year": day.timetuple().tm_yday,
                "season": season,
                "season_label": SEASON_LABELS[season],
                "activity_period": activity,
                "activity_period_label": ACTIVITY_LABELS[activity],
                "is_food_season": month in (9, 10, 11),
                "is_denning_season": month in (12, 1, 2),
                "moon_phase": round(_moon_phase_index(day), 3),
            }
        )
        props.update(grid_context)
        props.update(_weather_for_sighting(row, weather_rows))
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "Point",
                    "coordinates": [props["lon"], props["lat"]],
                },
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "sightings",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
                },
                "features": features,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  -> {OUT} ({len(features)} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
