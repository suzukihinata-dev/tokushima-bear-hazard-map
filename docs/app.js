// 徳島県 クマ出没ハザードマップ
"use strict";

// 国土地理院 淡色地図
const map = L.map("map", { preferCanvas: true }).setView([33.87, 134.15], 10);
L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
  attribution:
    "地図: <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
  maxZoom: 18,
}).addTo(map);

// スコア(0-1) -> 色（青→赤）
function hazardColor(s) {
  const stops = [
    [0.0, [44, 123, 182]],
    [0.25, [171, 217, 233]],
    [0.5, [255, 255, 191]],
    [0.75, [253, 174, 97]],
    [1.0, [215, 25, 28]],
  ];
  for (let i = 1; i < stops.length; i++) {
    if (s <= stops[i][0]) {
      const [a, ca] = stops[i - 1];
      const [b, cb] = stops[i];
      const t = (s - a) / (b - a);
      const c = ca.map((v, k) => Math.round(v + t * (cb[k] - v)));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return "rgb(215,25,28)";
}

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

// --- ハザード層 ---
const hazardLayer = L.geoJSON(null, {
  style: (f) => ({
    stroke: false,
    fillColor: hazardColor(f.properties.score),
    // 低スコアは薄く、高スコアは濃く（ヒートマップらしさ）
    fillOpacity: 0.15 + 0.6 * f.properties.score,
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

// --- 出没点層 ---
const sightingLayer = L.geoJSON(null, {
  pointToLayer: (f, latlng) =>
    L.circleMarker(latlng, {
      radius: 7,
      color: "#222",
      weight: 1,
      fillColor: EVIDENCE_COLORS[f.properties.evidence_type] || "#888",
      fillOpacity: 0.9,
    }),
  onEachFeature: (f, layer) => {
    const p = f.properties;
    const col = EVIDENCE_COLORS[p.evidence_type] || "#888";
    layer.bindPopup(
      `<div class="popup-date">${p.date}</div>` +
        `<div class="popup-place">${p.place}</div>` +
        `<div>${p.situation}</div>` +
        `<div style="margin-top:4px"><span class="popup-ev" style="background:${col}">${p.evidence_type}</span> ` +
        `<small>位置精度: ${p.geo_confidence}</small></div>`
    );
  },
});

// --- データ読み込み ---
Promise.all([
  fetch("data/grid_scores.geojson").then((r) => r.json()),
  fetch("data/sightings.geojson").then((r) => r.json()),
]).then(([grid, sightings]) => {
  hazardLayer.addData(grid).addTo(map);
  sightingLayer.addData(sightings).addTo(map);
  map.fitBounds(sightingLayer.getBounds().pad(0.4));
});

// --- レイヤ切替 ---
L.control
  .layers(null, { ハザードヒートマップ: hazardLayer, 出没地点: sightingLayer }, { collapsed: false })
  .addTo(map);

// --- 凡例 ---
const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  let html =
    "<h4>ハザードスコア（相対リスク）</h4>" +
    '<div class="bar"></div>' +
    '<div class="scale"><span>低 0</span><span>高 1</span></div>' +
    '<h4 style="margin-top:8px">出没痕跡の種別</h4>';
  for (const [k, v] of Object.entries(EVIDENCE_COLORS)) {
    html += `<div class="row"><span class="dot" style="background:${v}"></span>${k}</div>`;
  }
  div.innerHTML = html;
  return div;
};
legend.addTo(map);
