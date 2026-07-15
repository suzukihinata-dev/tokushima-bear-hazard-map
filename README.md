# Shikoku Mainland Bear Sighting Hazard Map

A web map for the Shikoku mainland that estimates locations with geographic characteristics similar to past Japanese black bear sightings and displays the relative hazard score as a continuous gradient.

## Public Maps

- Vercel: [https://bear-bice.vercel.app/](https://bear-bice.vercel.app/)
- GitHub Pages: [https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/](https://suzukihinata-dev.github.io/tokushima-bear-hazard-map/)

Source repository: [suzukihinata-dev/tokushima-bear-hazard-map](https://github.com/suzukihinata-dev/tokushima-bear-hazard-map)

The map covers the Shikoku mainland. The boundary is created from the administrative areas of Tokushima, Kagawa, Ehime, and Kochi prefectures. Surrounding islands are excluded.

GitHub Pages serves the `/docs` directory from the `main` branch. If the repository root is selected as the Pages source instead, the root `index.html` redirects to `docs/` and opens the same map.

The score is a **relative statistical estimate** of similarity to past sighting locations. It is not a probability of bear occurrence and does not guarantee safety in low-score areas.

## Features

- Display the hazard score for the entire Shikoku mainland as a blue-to-red gradient
- Keep the gradient layer aligned with the base map while zooming and panning
- Click a hazard area to inspect the score, elevation, slope, forest ratio, building-land ratio, and distance to the nearest river when available
- Filter sighting locations by season, month, or autumn feeding season
- View the date, location, situation, evidence type, observed elevation, and exact distance to a river in a sighting popup when the data is available
- Optionally add daily weather data and display it in sighting popups

## Current Input Data

`data/sightings.csv` currently contains 45 records, mainly from Tokushima Prefecture, covering 2004 through 2026. The project is structured so that additional sightings from all four prefectures in Shikoku can be added later.

The basic sighting columns are:

```csv
id,date,place,situation,evidence_type,lat,lon
```

For elevation data, use the `observed_elev` column for new records.

```csv
id,date,place,situation,evidence_type,lat,lon,observed_elev
1,2026-05-19,勝浦郡上勝町,皮剥ぎ痕を発見,皮剥ぎ,33.930,134.315,1076.4
```

For backward compatibility, a numeric value in `geo_confidence` is also treated as observed elevation. Because `geo_confidence` normally means location accuracy, new data should use `observed_elev` instead. Text values such as `high`, `medium`, and `low` are retained and displayed as location-accuracy labels.

## Features Used for Analysis

| Feature | Description | Data source |
| --- | --- | --- |
| `elev` | Mean elevation within the mesh | [Geospatial Information Authority of Japan elevation tiles](https://maps.gsi.go.jp/development/elevation_s.html) (DEM) |
| `slope` | Mean slope | Calculated from the DEM |
| `slope_p90` | 90th percentile of slope | Calculated from the DEM |
| `steep_ratio` | Ratio of pixels with a slope of at least 30 degrees | Calculated from the DEM |
| `relief` | Standard deviation of elevation within the mesh | Calculated from the DEM |
| `forest` | Forest ratio | [National Land Numerical Information](https://nlftp.mlit.go.jp/ksj/), land-use subdivision mesh (L03-b) |
| `building` | Building-land ratio | National Land Numerical Information L03-b |
| `agri` | Agricultural-land ratio | National Land Numerical Information L03-b |
| `dist_river` | Distance from the mesh center to the nearest river | National Land Numerical Information, rivers (W05) |
| `x_km` / `y_km` | Projected coordinates of the mesh center | Calculated from the mesh geometry |

Sighting records are enriched with the season, month, activity period, autumn feeding season flag, denning season flag, and moon-phase index derived from the date. When river data is available, the exact distance from each sighting point to the nearest river is also calculated.

## Scoring Method

1. Create third-order standard regional meshes, approximately 1 km wide, across the Shikoku mainland.
2. Calculate elevation, slope, agricultural-land ratio, river distance, and broad-scale spatial context for each mesh. The score uses `elev`, `slope_p90`, `agri`, `log(dist_river)`, `x_km`, and `y_km`.
3. Standardize the features and calculate a Gaussian-kernel score. Meshes with features closer to known sighting locations receive higher scores.
4. Apply year-based decay so that more recent records receive somewhat greater weight.
5. When `observed_elev` or a numeric `geo_confidence` is available, match each sighting to a mesh using both geographic distance and elevation consistency.
6. Normalize the score for display to the 0–1 range. The map displays lower scores in blue and higher scores in red as a continuous gradient.

The current model uses both habitat-related features and the `x_km` / `y_km` spatial context of known sightings. It therefore represents similarity to the current data distribution, not a proven causal relationship. Each run also logs the mean percentile from a leave-one-out validation of the sighting locations.

Weather data is currently displayed as supplementary information for sightings and is not included in the hazard-score calculation.

## Directory Structure

```text
.
├── index.html                    Entry point for GitHub Pages root publishing
├── requirements/requirements.md   Requirements document
├── data/
│   ├── sightings.csv              Bear sighting records
│   ├── weather_daily.example.csv  Example weather-data input
│   ├── weather_daily.csv          Optional daily weather data
│   ├── raw/                       Raw KSJ and DEM data (not tracked by Git)
│   └── processed/                 Intermediate outputs (not tracked by Git)
├── src/
│   ├── config.py                 Target area, data sources, and path settings
│   ├── download_ksj.py           Download and extract National Land Numerical Information
│   ├── gsi_dem.py                Retrieve DEM data and calculate elevation and slope
│   ├── build_features.py         Build analysis meshes and aggregate features
│   ├── score.py                  Calculate hazard scores and export GeoJSON
│   ├── export_sightings.py       Regenerate the sighting GeoJSON
│   └── pipeline.py               Run the complete preprocessing pipeline
├── docs/
│   ├── index.html                Web-map HTML
│   ├── app.js                    Leaflet display logic
│   ├── style.css                 Web-map styles
│   └── data/                     GeoJSON served by Vercel and GitHub Pages
├── requirements.txt              Python dependencies
└── vercel.json                   Vercel static-deployment configuration
```

Vercel and GitHub Pages serve the `docs/` directory as static files without a build step. When analysis results are updated, commit the generated files in `docs/data/` so both public deployments use the updated data.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the Complete Pipeline

This downloads National Land Numerical Information and elevation data, then generates the features, scores, and GeoJSON files used by the web map.

```bash
python src/pipeline.py
```

### Recalculate with Downloaded Data

If the required files already exist under `data/raw/`, skip the download step:

```bash
python src/pipeline.py --no-download
```

### Regenerate Sighting Data Only

Use this command when updating seasonal, river-distance, elevation, or other sighting-popup information:

```bash
python src/export_sightings.py
```

### Run Locally

```bash
python -m http.server 8000 --directory docs
```

Open [http://localhost:8000](http://localhost:8000) in a browser. Use an HTTP server instead of opening files directly from the `docs/` directory.

## Adding Weather Data

Create `data/weather_daily.csv` only when weather information is needed. The `date` column is required; all other columns are optional.

```csv
date,station,station_lat,station_lon,weather,temp_avg,temp_max,temp_min,precipitation,snowfall,sunshine,wind_speed
2025-07-13,木頭,33.82,134.20,晴,25.3,30.1,21.2,0.0,0.0,8.4,1.8
```

When `station_lat` and `station_lon` are provided, the closest station to each sighting is selected from the records for the same date. Without station coordinates, records are joined by date only.

## If Automatic Data Download Fails

Download the following data for the four Shikoku prefectures (36, 37, 38, and 39) from the [National Land Numerical Information download site](https://nlftp.mlit.go.jp/ksj/), then extract it under `data/raw/`:

- Administrative areas (N03)
- Rivers (W05)
- Land-use subdivision mesh (L03-b)

Then run:

```bash
python src/pipeline.py --no-download
```

## Sources and Data Use

- [National Land Numerical Information](https://nlftp.mlit.go.jp/ksj/) (administrative areas, rivers, and land-use subdivision mesh), Ministry of Land, Infrastructure, Transport and Tourism, Japan
- [GSI Tiles](https://maps.gsi.go.jp/development/ichiran.html) (elevation and pale map tiles), Geospatial Information Authority of Japan
- Sighting records were organized from publicly available information. The accuracy and completeness of individual records are not guaranteed.

Follow the terms of use and attribution requirements of each data provider.

## Limitations

- This map is not an official hazard-area map provided by a disaster-management agency or local government.
- The number of sighting records is limited, and the data may contain biases in observation and survey locations.
- The map provides a relative assessment at approximately 1 km resolution; it does not directly represent risk for individual roads, trails, or settlements.
- Red areas indicate higher similarity to the input data. They do not represent the probability of an actual bear sighting.
