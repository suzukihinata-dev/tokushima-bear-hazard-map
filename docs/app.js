// 徳島県 クマ出没ハザードマップ
"use strict";

// 国土地理院 淡色地図
const map = L.map("map", { preferCanvas: true }).setView([33.87, 134.15], 10);
L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
  attribution:
    "地図: <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
  maxZoom: 18,
}).addTo(map);

const hazardVisualPane = map.createPane("hazard-visual-pane");
hazardVisualPane.style.zIndex = "340";
hazardVisualPane.style.pointerEvents = "none";

const hazardHitPane = map.createPane("hazard-hit-pane");
hazardHitPane.style.zIndex = "345";

const hazardHitRenderer = L.svg({ pane: "hazard-hit-pane", padding: 0.25 });
const HAZARD_OVERLAY_MAX_SCALE = 20;
const HAZARD_OVERLAY_MIN_SCALE = 14;
const HAZARD_SMOOTH_RADIUS = 2;
const HAZARD_SMOOTH_SIGMA = 1.1;
const HAZARD_DISPLAY_GAMMA = 0.7;

const HAZARD_STOPS = [
  [0.0, [44, 123, 182]],
  [0.25, [171, 217, 233]],
  [0.5, [255, 241, 170]],
  [0.75, [243, 127, 77]],
  [1.0, [150, 0, 28]],
];

function hazardRgb(s) {
  const score = Math.pow(Math.max(0, Math.min(1, s)), HAZARD_DISPLAY_GAMMA);
  for (let i = 1; i < HAZARD_STOPS.length; i++) {
    if (score <= HAZARD_STOPS[i][0]) {
      const [a, ca] = HAZARD_STOPS[i - 1];
      const [b, cb] = HAZARD_STOPS[i];
      const t = (score - a) / (b - a);
      return ca.map((v, k) => Math.round(v + t * (cb[k] - v)));
    }
  }
  return [150, 0, 28];
}

// スコア(0-1) -> 色（青→赤）
function hazardColor(s) {
  const [r, g, b] = hazardRgb(s);
  return `rgb(${r},${g},${b})`;
}

const HAZARD_PALETTE = Array.from({ length: 256 }, (_, index) => {
  const score = index / 255;
  return {
    rgb: hazardRgb(score),
    alpha: Math.round(255 * (0.22 + 0.72 * Math.pow(score, HAZARD_DISPLAY_GAMMA))),
  };
});

// 痕跡種別 -> 色
const EVIDENCE_COLORS = {
  目撃: "#1f78b4",
  皮剥ぎ: "#b15928",
  足跡: "#6a3d9a",
  糞: "#7f6000",
  食痕: "#e31a1c",
  捕獲: "#33a02c",
  物的痕跡: "#555555",
};

const SEASON_COLORS = {
  spring: "#2ca25f",
  summer: "#3182bd",
  autumn: "#de6b1f",
  winter: "#756bb1",
};

const MONTH_SEASONS = {
  1: "winter",
  2: "winter",
  3: "spring",
  4: "spring",
  5: "spring",
  6: "summer",
  7: "summer",
  8: "summer",
  9: "autumn",
  10: "autumn",
  11: "autumn",
  12: "winter",
};

const seasonFilter = document.getElementById("season-filter");
const monthFilter = document.getElementById("month-filter");
const foodSeasonFilter = document.getElementById("food-season-filter");
const filterCount = document.getElementById("filter-count");

function updateMonthOptions() {
  const selectedSeason = seasonFilter.value;
  const selectedMonth = monthFilter.value;
  monthFilter.replaceChildren(new Option("すべて", "all"));

  for (let month = 1; month <= 12; month++) {
    if (selectedSeason !== "all" && MONTH_SEASONS[month] !== selectedSeason) {
      continue;
    }
    monthFilter.appendChild(new Option(`${month}月`, String(month)));
  }

  const stillAvailable = Array.from(monthFilter.options).some(
    (option) => option.value === selectedMonth
  );
  monthFilter.value = stillAvailable ? selectedMonth : "all";
}

updateMonthOptions();

function fmt(value, suffix = "", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "データなし";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function numOrNull(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function textOrNull(value) {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text) return null;
  if (["undefined", "null", "none", "nan", "na", "n/a"].includes(text.toLowerCase())) {
    return null;
  }
  return text;
}

function weatherHtml(p) {
  const rows = [
    `季節: ${p.season_label || "不明"} / ${p.activity_period_label || "不明"}`,
    `月齢指数: ${fmt(p.moon_phase, "", 2)}`,
  ];
  if (p.weather) rows.push(`天気: ${p.weather}`);
  if (p.temp_avg !== undefined && p.temp_avg !== null) rows.push(`平均気温: ${fmt(p.temp_avg, "℃")}`);
  if (p.precipitation !== undefined && p.precipitation !== null) {
    rows.push(`日降水量: ${fmt(p.precipitation, "mm")}`);
  }
  if (p.station) {
    const dist = p.weather_station_distance_km ? ` / 約${p.weather_station_distance_km}km` : "";
    rows.push(`観測所: ${p.station}${dist}`);
  }
  return `<div class="popup-meta">${rows.join("<br>")}</div>`;
}

function sightingMetaLine(p) {
  const details = [`<span class="popup-ev" style="background:${EVIDENCE_COLORS[p.evidence_type] || "#888"}">${p.evidence_type}</span>`];
  const observedElev = numOrNull(p.observed_elev);
  const geoConfidence = textOrNull(p.geo_confidence);
  if (observedElev !== null) {
    details.push(`<small>観測標高: ${fmt(observedElev, "m")}</small>`);
  } else if (geoConfidence) {
    details.push(`<small>位置精度: ${geoConfidence}</small>`);
  }
  return details.join(" ");
}

function landscapeHtml(p) {
  const rows = [];
  const risk = numOrNull(p.matched_score);
  const pointRiver = numOrNull(p.point_dist_river);
  const river = numOrNull(p.mesh_dist_river);
  const slope = numOrNull(p.mesh_slope);
  const steepRatio = numOrNull(p.mesh_steep_ratio);
  const forest = numOrNull(p.mesh_forest);
  const meshElev = numOrNull(p.mesh_elev);
  const elevGap = numOrNull(p.mesh_elev_gap_m);
  const centerDistance = numOrNull(p.mesh_center_distance_km);

  if (risk !== null) rows.push(`地点リスク: ${risk.toFixed(2)}`);
  if (pointRiver !== null) rows.push(`河川までの実距離: ${fmt(pointRiver, "m", 0)}`);
  else if (river !== null) rows.push(`最近隣河川: ${fmt(river, "m", 0)}`);
  if (slope !== null) rows.push(`周辺傾斜: ${fmt(slope, "°")}`);
  if (steepRatio !== null) rows.push(`急斜面率(30°以上): ${fmt(steepRatio * 100, "%", 0)}`);
  if (forest !== null) rows.push(`周辺森林率: ${fmt(forest * 100, "%", 0)}`);
  if (meshElev !== null) rows.push(`周辺メッシュ標高: ${fmt(meshElev, "m")}`);
  if (elevGap !== null) rows.push(`標高差: ${fmt(elevGap, "m")}`);
  if (centerDistance !== null) rows.push(`メッシュ中心距離: ${fmt(centerDistance, "km", 2)}`);

  return rows.length ? `<div class="popup-meta">${rows.join("<br>")}</div>` : "";
}

function buildHazardSurface(grid) {
  const cells = grid.features.map((feature) => {
    const ring = feature.geometry.coordinates[0];
    let west = Infinity;
    let east = -Infinity;
    let south = Infinity;
    let north = -Infinity;

    for (const [lon, lat] of ring) {
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }

    return {
      west,
      east,
      south,
      north,
      centerLon: (west + east) / 2,
      centerLat: (south + north) / 2,
      score: feature.properties.score,
    };
  });

  if (cells.length === 0) return null;

  const lonKeys = [...new Set(cells.map((cell) => cell.centerLon.toFixed(6)))].sort(
    (a, b) => Number(a) - Number(b)
  );
  const latKeys = [...new Set(cells.map((cell) => cell.centerLat.toFixed(6)))].sort(
    (a, b) => Number(a) - Number(b)
  );

  const centerLons = lonKeys.map(Number);
  const centerLats = latKeys.map(Number);
  const xIndex = new Map(lonKeys.map((key, index) => [key, index]));
  const yIndex = new Map(latKeys.map((key, index) => [key, index]));
  const scores = Array.from({ length: centerLats.length }, () => Array(centerLons.length).fill(null));
  const occupied = Array.from({ length: centerLats.length }, () => Array(centerLons.length).fill(false));

  for (const cell of cells) {
    const x = xIndex.get(cell.centerLon.toFixed(6));
    const y = yIndex.get(cell.centerLat.toFixed(6));
    scores[y][x] = cell.score;
    occupied[y][x] = true;
  }

  return {
    cols: centerLons.length,
    rows: centerLats.length,
    westMin: Math.min(...cells.map((cell) => cell.west)),
    eastMax: Math.max(...cells.map((cell) => cell.east)),
    southMin: Math.min(...cells.map((cell) => cell.south)),
    northMax: Math.max(...cells.map((cell) => cell.north)),
    cellWidth: cells[0].east - cells[0].west,
    cellHeight: cells[0].north - cells[0].south,
    centerLons,
    centerLats,
    scores,
    occupied,
  };
}

function boundaryPolygons(boundaryData) {
  const polygons = [];

  function collect(entry) {
    if (!entry) return;
    if (entry.type === "FeatureCollection") {
      for (const feature of entry.features) collect(feature);
      return;
    }
    if (entry.type === "Feature") {
      collect(entry.geometry);
      return;
    }
    if (entry.type === "GeometryCollection") {
      for (const geometry of entry.geometries) collect(geometry);
      return;
    }
    if (entry.type === "Polygon") {
      polygons.push(entry.coordinates);
      return;
    }
    if (entry.type === "MultiPolygon") {
      polygons.push(...entry.coordinates);
    }
  }

  collect(boundaryData);

  return polygons;
}

function traceBoundaryPath(ctx, polygons, surface, width, height) {
  const lonSpan = surface.eastMax - surface.westMin;
  const latSpan = surface.northMax - surface.southMin;
  if (!lonSpan || !latSpan) return;

  ctx.beginPath();
  for (const polygon of polygons) {
    for (const ring of polygon) {
      if (!ring.length) continue;
      ring.forEach(([lon, lat], index) => {
        const x = ((lon - surface.westMin) / lonSpan) * width;
        const y = ((surface.northMax - lat) / latSpan) * height;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
    }
  }
}

function hazardRasterScale(surface) {
  const longestEdge = Math.max(surface.cols, surface.rows);
  return Math.max(
    HAZARD_OVERLAY_MIN_SCALE,
    Math.min(HAZARD_OVERLAY_MAX_SCALE, Math.floor(1800 / longestEdge))
  );
}

function sampleHazardSurface(surface, gx, gy) {
  let weightSum = 0;
  let scoreSum = 0;
  let nearestDist2 = Infinity;
  const centerX = Math.round(gx);
  const centerY = Math.round(gy);

  for (let y = centerY - HAZARD_SMOOTH_RADIUS; y <= centerY + HAZARD_SMOOTH_RADIUS; y++) {
    if (y < 0 || y >= surface.rows) continue;
    for (let x = centerX - HAZARD_SMOOTH_RADIUS; x <= centerX + HAZARD_SMOOTH_RADIUS; x++) {
      if (x < 0 || x >= surface.cols) continue;
      const score = surface.scores[y][x];
      if (score === null) continue;

      const dx = gx - x;
      const dy = gy - y;
      const dist2 = dx * dx + dy * dy;
      nearestDist2 = Math.min(nearestDist2, dist2);

      const weight = Math.exp(-dist2 / (2 * HAZARD_SMOOTH_SIGMA * HAZARD_SMOOTH_SIGMA));
      weightSum += weight;
      scoreSum += score * weight;
    }
  }

  if (weightSum === 0 || nearestDist2 > 5.5) {
    return null;
  }

  return scoreSum / weightSum;
}

function renderHazardOverlay(surface, boundaryData) {
  const scale = hazardRasterScale(surface);
  const width = surface.cols * scale;
  const height = surface.rows * scale;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(width, height);
  const pixels = image.data;

  for (let py = 0; py < height; py++) {
    const gy = surface.rows - (py + 0.5) / scale - 0.5;
    for (let px = 0; px < width; px++) {
      const gx = (px + 0.5) / scale - 0.5;
      const score = sampleHazardSurface(surface, gx, gy);
      if (score === null) continue;

      const palette = HAZARD_PALETTE[Math.max(0, Math.min(255, Math.round(score * 255)))];
      const offset = (py * width + px) * 4;
      pixels[offset] = palette.rgb[0];
      pixels[offset + 1] = palette.rgb[1];
      pixels[offset + 2] = palette.rgb[2];
      pixels[offset + 3] = palette.alpha;
    }
  }

  ctx.putImageData(image, 0, 0);

  const blurredCanvas = document.createElement("canvas");
  blurredCanvas.width = width;
  blurredCanvas.height = height;
  const blurredCtx = blurredCanvas.getContext("2d");
  blurredCtx.filter = "blur(0.8px)";
  blurredCtx.drawImage(canvas, 0, 0);
  blurredCtx.filter = "none";

  const polygons = boundaryPolygons(boundaryData);
  if (polygons.length) {
    blurredCtx.globalCompositeOperation = "destination-in";
    blurredCtx.fillStyle = "#fff";
    traceBoundaryPath(blurredCtx, polygons, surface, width, height);
    blurredCtx.fill("evenodd");
    blurredCtx.globalCompositeOperation = "source-over";
  }

  const bounds = L.latLngBounds(
    [surface.southMin, surface.westMin],
    [surface.northMax, surface.eastMax]
  );

  return L.imageOverlay(blurredCanvas.toDataURL("image/png"), bounds, {
    pane: "hazard-visual-pane",
    interactive: false,
    opacity: 1,
  });
}

// --- ハザード層 ---
const hazardVisualLayer = L.layerGroup();

const hazardHitLayer = L.geoJSON(null, {
  renderer: hazardHitRenderer,
  style: () => ({
    stroke: false,
    fill: true,
    fillOpacity: 0,
    opacity: 0,
  }),
  onEachFeature: (f, layer) => {
    const p = f.properties;
    layer.bindPopup(
      `<b>ハザードスコア: ${p.score.toFixed(2)}</b><br>` +
        `標高: ${p.elev} m / 傾斜: ${p.slope}°<br>` +
        `森林率: ${(p.forest * 100).toFixed(0)}% / 建物用地率: ${(p.building * 100).toFixed(0)}%<br>` +
        `最近隣河川: ${Math.round(p.dist_river)} m`
    );
  },
});

const hazardLayer = L.layerGroup([hazardVisualLayer, hazardHitLayer]);

// --- 出没点層 ---
const sightingLayer = L.geoJSON(null, {
  pointToLayer: (f, latlng) =>
    L.circleMarker(latlng, {
      radius: 7,
      color: SEASON_COLORS[f.properties.season] || "#222",
      weight: 1,
      fillColor: EVIDENCE_COLORS[f.properties.evidence_type] || "#888",
      fillOpacity: 0.9,
    }),
  onEachFeature: (f, layer) => {
    const p = f.properties;
    layer.bindPopup(
      `<div class="popup-date">${p.date}</div>` +
        `<div class="popup-place">${p.place}</div>` +
        `<div>${p.situation}</div>` +
        `<div style="margin-top:4px">${sightingMetaLine(p)}</div>` +
        landscapeHtml(p) +
        weatherHtml(p)
    );
  },
});

let allSightings = null;

function filteredSightings() {
  if (!allSightings) return null;
  const season = seasonFilter.value;
  const month = monthFilter.value;
  const normalizedMonth =
    month !== "all" && season !== "all" && MONTH_SEASONS[Number(month)] !== season
      ? "all"
      : month;
  const foodOnly = foodSeasonFilter.checked;
  return {
    ...allSightings,
    features: allSightings.features.filter((f) => {
      const p = f.properties;
      if (season !== "all" && p.season !== season) return false;
      if (normalizedMonth !== "all" && String(p.month) !== normalizedMonth) return false;
      if (foodOnly && !p.is_food_season) return false;
      return true;
    }),
  };
}

function renderSightings() {
  const data = filteredSightings();
  if (!data) return;
  sightingLayer.clearLayers();
  sightingLayer.addData(data);
  filterCount.textContent = `出没地点: ${data.features.length} / ${allSightings.features.length}`;
}

for (const control of [seasonFilter, monthFilter, foodSeasonFilter]) {
  control.addEventListener("change", () => {
    if (control === seasonFilter) updateMonthOptions();
    renderSightings();
  });
}

// --- データ読み込み ---
Promise.all([
  fetch("data/grid_scores.geojson").then((r) => r.json()),
  fetch("data/sightings.geojson").then((r) => r.json()),
  fetch("data/pref_boundary.geojson").then((r) => r.json()),
]).then(([grid, sightings, boundary]) => {
  allSightings = sightings;
  hazardVisualLayer.clearLayers();
  const surface = buildHazardSurface(grid);
  if (surface) {
    hazardVisualLayer.addLayer(renderHazardOverlay(surface, boundary));
  }
  hazardHitLayer.addData(grid);
  hazardLayer.addTo(map);
  renderSightings();
  sightingLayer.addTo(map);
  map.fitBounds(sightingLayer.getBounds().pad(0.4));
});

// --- レイヤ切替 ---
L.control
  .layers(null, { ハザードグラデーション: hazardLayer, 出没地点: sightingLayer }, { collapsed: false })
  .addTo(map);

// --- 凡例 ---
const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  let html =
    "<h4>ハザードスコア（相対リスク）</h4>" +
    '<div class="bar"></div>' +
    '<div class="scale"><span>低 0</span><span>高 1</span></div>' +
    '<h4 style="margin-top:8px">季節（点の枠線）</h4>' +
    '<div class="row"><span class="dot" style="background:#fff;border-color:#2ca25f"></span>春</div>' +
    '<div class="row"><span class="dot" style="background:#fff;border-color:#3182bd"></span>夏</div>' +
    '<div class="row"><span class="dot" style="background:#fff;border-color:#de6b1f"></span>秋</div>' +
    '<div class="row"><span class="dot" style="background:#fff;border-color:#756bb1"></span>冬</div>' +
    '<h4 style="margin-top:8px">出没痕跡の種別</h4>';
  for (const [k, v] of Object.entries(EVIDENCE_COLORS)) {
    html += `<div class="row"><span class="dot" style="background:${v}"></span>${k}</div>`;
  }
  div.innerHTML = html;
  return div;
};
legend.addTo(map);
