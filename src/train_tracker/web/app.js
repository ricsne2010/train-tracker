// US Train Tracker frontend: NARN track lines + live trains pushed over WebSocket.
// Zoomed out, trains are arrows; in the middle a small top-down train icon; zoomed in,
// each train is drawn to scale, car by car, following the real track.
"use strict";

// Bright, and clear of the blue (Amtrak) and green (commuter) track colours so trains stand out.
const AGENCY_COLORS = {
  "Amtrak": "#ff6a13",
  "MBTA Commuter Rail": "#b84dff",
  "LIRR": "#ffd60a",
  "Metro-North": "#ff2e4c",
  "SEPTA Regional Rail": "#00c2d1",
  "Metra": "#c6ff00",
  "Caltrain": "#ff4fa3",
  "Metrolink": "#9d7bff",
  "NJ Transit Rail": "#e040fb",
};
const FALLBACK_COLOR = "#888888";
const TRACK_COLORS = ["match", ["get", "p"], "A", "#5b8def", "C", "#3fb68b", "#9aa3b2"];
const TRACK_URL = "data/narn_passenger_v2.geojson";
const dark = matchMedia("(prefers-color-scheme: dark)").matches;

// Zoom tiers: arrows below SPRITE_Z, top-down icons up to CONSIST_Z, full trains above.
const SPRITE_Z = 9, CONSIST_Z = 15;
const WIDTH_EXAG = 1.6;              // widths are drawn 1.6x real so rails and cars stay readable
const CAR_WIDTH_M = 3.2, MIN_CAR_PX = 6;
const MAX_GLIDE_S = 90;              // dead-reckon at most this long past the last fix
const FREIGHT_Z = 9, CELL = 0.5;     // freight/other track: shown from this zoom, fetched in 0.5° squares

const PALETTE = dark
  ? { edge: "#07090d", car: "#9aa3ad", glass: "#0b1220", hatch: "#00000055", halo: "#0f1218", text: "#e6e9ef",
      ballast: "#3a3631", ties: "#51402f", rail: "#c2c9d2", freight: "#7d838d" }
  : { edge: "#1d2330", car: "#c9cfd6", glass: "#1b2430", hatch: "#00000040", halo: "#ffffff", text: "#1d2330",
      ballast: "#c4bcae", ties: "#7a5c45", rail: "#59616b", freight: "#8d939c" };

const vehicles = new Map();         // key -> vehicle from the server
const motion = new Map();           // key -> client-side motion state (snap, heading, speed)
let feeds = [];
let net = null;                     // TrackNet, once the track file has loaded
const hidden = new Set(JSON.parse(safeGet("hiddenAgencies") || "[]"));
// Line filters: which kinds of track to draw, and railroads (by NARN owner code) to hide.
const LINE_GROUPS = {
  amtrak:     { label: "Amtrak and intercity", source: "track", test: ["in", ["get", "p"], ["literal", ["A", "B", "I", "E"]]] },
  commuter:   { label: "Commuter rail", source: "track", test: ["in", ["get", "p"], ["literal", ["C", "B", "E"]]] },
  otherPass:  { label: "Transit, tourist and other", source: "track",
                test: ["!", ["in", ["get", "p"], ["literal", ["A", "B", "I", "E", "C"]]]] },
  main:       { label: "Main lines", source: "freight", test: ["==", ["get", "n"], "M"] },
  industrial: { label: "Industrial track", source: "freight", test: ["in", ["get", "n"], ["literal", ["I", "O"]]] },
  siding:     { label: "Passing sidings", source: "freight", test: ["==", ["get", "n"], "S"] },
  yard:       { label: "Yards", source: "freight", test: ["==", ["get", "n"], "Y"] },
};
function loadJSON(k, fallback) { try { return JSON.parse(safeGet(k)) ?? fallback; } catch { return fallback; } }
const lineOn = Object.fromEntries(Object.keys(LINE_GROUPS).map((g) => [g, true]));
Object.assign(lineOn, loadJSON("lineFilters", {}));
if (safeGet("showFreight") === "0" && !safeGet("lineFilters")) {   // carry over the old freight switch
  for (const g in LINE_GROUPS) if (LINE_GROUPS[g].source === "freight") lineOn[g] = false;
}
const hiddenOwners = new Set(loadJSON("hiddenOwners", []));
const freightWanted = () => Object.keys(LINE_GROUPS).some((g) => LINE_GROUPS[g].source === "freight" && lineOn[g]);

function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }

// Opening view: the lower 48 fitted into the part of the window the panel doesn't cover.
const US_BOUNDS = [[-124.8, 24.4], [-66.9, 49.4]];
function homePadding() {
  const pad = { top: 24, right: 56, bottom: 24, left: 24 };   // right: room for the zoom buttons
  const r = document.getElementById("panel").getBoundingClientRect();
  if (r.top > innerHeight / 3) pad.bottom = Math.max(24, innerHeight - r.top + 12);   // phone: panel along the bottom
  else pad.left = Math.max(24, r.right + 16);
  // never pad away more than most of the window, or there's nothing left to fit into
  pad.left = Math.min(pad.left, innerWidth * 0.6); pad.bottom = Math.min(pad.bottom, innerHeight * 0.6);
  return pad;
}

const map = new maplibregl.Map({
  container: "map",
  style: `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`,
  bounds: US_BOUNDS,
  fitBoundsOptions: { padding: homePadding() },
  maxZoom: 19.5,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
// Until the map is moved by hand, keep the US fitted as the window settles or is resized.
let movedByHand = false;
map.on("movestart", (e) => { if (e.originalEvent) movedByHand = true; });
addEventListener("resize", () => { if (!movedByHand) map.fitBounds(US_BOUNDS, { padding: homePadding(), animate: false }); });

// ---------- marker images ----------
function canvas(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"));
  return c.getContext("2d").getImageData(0, 0, w, h);
}

// Arrow for the zoomed-out view, outlined for contrast.
function arrowImage(color) {
  return canvas(32, 32, (g) => {
    g.beginPath();
    g.moveTo(16, 3); g.lineTo(25, 27); g.lineTo(16, 21); g.lineTo(7, 27);
    g.closePath();
    g.lineJoin = "round"; g.lineWidth = 4; g.strokeStyle = PALETTE.halo; g.stroke();
    g.fillStyle = color; g.fill();
    g.lineWidth = 1.5; g.strokeStyle = PALETTE.edge; g.stroke();
  });
}

// Top-down train for the middle zooms: locomotive at the top (front), three cars behind.
function spriteImage(color) {
  const W = 22, H = 100, w = 14, x = (W - w) / 2;
  return canvas(W * 2, H * 2, (g) => {
    g.scale(2, 2);
    const body = (y, h, fill) => {
      g.beginPath(); g.roundRect(x, y, w, h, 3);
      g.lineWidth = 3; g.strokeStyle = PALETTE.halo; g.stroke();
      g.fillStyle = fill; g.fill();
      g.lineWidth = 1; g.strokeStyle = PALETTE.edge; g.stroke();
    };
    body(3, 22, color);                                  // locomotive
    g.fillStyle = PALETTE.glass; g.beginPath(); g.roundRect(x + 2, 4.5, w - 4, 3.5, 1.5); g.fill();
    g.fillStyle = PALETTE.hatch; g.fillRect(x + 4, 12, w - 8, 9);
    for (let i = 0; i < 3; i++) {
      const y = 27 + i * 24;
      body(y, 22, PALETTE.car);
      g.fillStyle = color; g.fillRect(W / 2 - 1.5, y + 3, 3, 16);   // roof stripe
    }
  });
}

// ---------- map layers ----------
// Metres -> pixels at a given zoom (at ~38°N; close enough for line widths across the US).
const PX_PER_M = (z) => 2 ** z / 61680;
const metres = (m) => ["interpolate", ["exponential", 2], ["zoom"], 12, ["*", m, PX_PER_M(12)], 22, ["*", m, PX_PER_M(22)]];
const nTracks = ["max", 1, ["min", 3, ["coalesce", ["get", "t"], 1]]];

// Zoomed in: ballast bed, then ties and a pair of rails for each track, for one source.
function addDetailLayers(src) {
  map.addLayer({
    id: `${src}-ballast`, type: "line", source: src, minzoom: 13.5,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": PALETTE.ballast,
      "line-width": metres(["*", WIDTH_EXAG, ["+", 4.8, ["*", ["-", nTracks, 1], 4.3]]]),
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, 1],
    },
  });
  for (let i = 0; i < 3; i++) {
    const offset = metres(["*", WIDTH_EXAG * 4.3, ["-", i, ["/", ["-", nTracks, 1], 2]]]);
    const filter = [">", nTracks, i];
    map.addLayer({
      id: `${src}-ties-${i}`, type: "line", source: src, minzoom: 15.5, filter,
      layout: { "line-join": "round" },
      paint: { "line-color": PALETTE.ties, "line-width": metres(2.6 * WIDTH_EXAG), "line-offset": offset,
               "line-dasharray": [0.1, 0.14] },
    });
    map.addLayer({
      id: `${src}-rails-${i}`, type: "line", source: src, minzoom: 14.5, filter,
      layout: { "line-join": "round" },
      paint: { "line-color": PALETTE.rail, "line-offset": offset,
               "line-gap-width": metres(1.435 * WIDTH_EXAG),
               "line-width": ["interpolate", ["linear"], ["zoom"], 14.5, 0.6, 17, 1.2, 19, 2.2] },
    });
  }
}

map.on("load", () => {
  for (const color of new Set([...Object.values(AGENCY_COLORS), FALLBACK_COLOR])) {
    map.addImage(`arrow-${color}`, arrowImage(color));
    map.addImage(`sprite-${color}`, spriteImage(color), { pixelRatio: 2 });
  }

  // Freight and other track (loaded by area as you zoom in) sits under the passenger lines.
  map.addSource("freight", { type: "geojson", data: emptyFC() });
  map.addLayer({
    id: "freight", type: "line", source: "freight", minzoom: FREIGHT_Z - 0.5, maxzoom: 15.5,
    filter: ["match", ["get", "n"], ["M", "I"], true, false],
    paint: {
      "line-color": PALETTE.freight,
      "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 13, 2],
      "line-opacity": ["interpolate", ["linear"], ["zoom"], FREIGHT_Z - 0.5, 0, FREIGHT_Z, 0.9, 13.5, 0.9, 15.5, 0],
    },
  });
  map.addLayer({
    id: "freight-minor", type: "line", source: "freight", minzoom: 12, maxzoom: 15.5,
    filter: ["match", ["get", "n"], ["M", "I"], false, true],
    paint: {
      "line-color": PALETTE.freight, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 0.5, 14, 1.2],
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 12, 0, 12.5, 0.7, 13.5, 0.7, 15.5, 0],
    },
  });
  addDetailLayers("freight");

  map.addSource("track", { type: "geojson", data: emptyFC() });
  // Zoomed out: one coloured line per route (blue Amtrak, green commuter).
  map.addLayer({
    id: "track", type: "line", source: "track", maxzoom: 15.5,
    paint: {
      "line-color": TRACK_COLORS,
      "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1, 8, 2, 13, 3.5],
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0.85, 15.5, 0],
    },
  });
  addDetailLayers("track");
  for (const layer of map.getStyle().layers) {   // remember each track layer's own filter
    if (layer.source === "track" || layer.source === "freight") baseFilters.set(layer.id, layer.filter || null);
  }
  applyLineFilters();

  // Full trains (zoomed in), drawn as polygons that follow the track.
  map.addSource("consists", { type: "geojson", data: emptyFC() });
  const partColor = ["match", ["get", "part"],
    "car", PALETTE.car, "glass", PALETTE.glass, "hatch", PALETTE.hatch, ["get", "agencyColor"]];
  map.addLayer({
    id: "consist-fill", type: "fill", source: "consists", minzoom: CONSIST_Z - 0.5,
    layout: { "fill-sort-key": ["get", "z"] },
    paint: { "fill-color": partColor },
  });
  map.addLayer({
    id: "consist-edge", type: "line", source: "consists", minzoom: CONSIST_Z - 0.5,
    filter: ["in", ["get", "part"], ["literal", ["car", "loco"]]],
    paint: { "line-color": PALETTE.edge, "line-width": ["interpolate", ["linear"], ["zoom"], 15, 0.6, 19, 1.5] },
  });

  map.addSource("trains", { type: "geojson", data: emptyFC() });
  const color = ["get", "agencyColor"];
  const symbol = { "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-rotation-alignment": "map",
                   "icon-rotate": ["get", "hdg"] };
  map.addLayer({   // zoomed out, direction unknown: a dot
    id: "trains-dot", type: "circle", source: "trains", maxzoom: SPRITE_Z,
    filter: ["!", ["get", "dirKnown"]],
    paint: {
      "circle-color": color, "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3.5, 9, 6],
      "circle-stroke-color": PALETTE.edge, "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({   // zoomed out, direction known: an arrow
    id: "trains-arrow", type: "symbol", source: "trains", maxzoom: SPRITE_Z,
    filter: ["get", "dirKnown"],
    layout: { ...symbol, "icon-image": ["concat", "arrow-", color],
              "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 9, 0.8] },
  });
  map.addLayer({   // middle zooms, and trains off the mapped track when zoomed in: top-down icon
    id: "trains-sprite", type: "symbol", source: "trains", minzoom: SPRITE_Z,
    filter: ["all", ["has", "hdg"], ["!", ["get", "drawn"]]],
    layout: { ...symbol, "icon-image": ["concat", "sprite-", color],
              "icon-size": ["interpolate", ["linear"], ["zoom"], SPRITE_Z, 0.6, 12, 0.8, CONSIST_Z, 1] },
  });
  map.addLayer({   // middle zooms with no heading at all
    id: "trains-dot-mid", type: "circle", source: "trains", minzoom: SPRITE_Z,
    filter: ["all", ["!", ["has", "hdg"]], ["!", ["get", "drawn"]]],
    paint: { "circle-color": color, "circle-radius": 7, "circle-stroke-color": PALETTE.edge, "circle-stroke-width": 2 },
  });
  map.addLayer({
    id: "trains-label", type: "symbol", source: "trains", minzoom: 6,
    layout: {
      "text-field": ["coalesce", ["get", "train"], ""], "text-size": ["interpolate", ["linear"], ["zoom"], 6, 11, 16, 13],
      "text-offset": [0, 1.4], "text-anchor": "top", "text-font": ["Noto Sans Bold"],
      "text-allow-overlap": false,
    },
    paint: { "text-color": PALETTE.text, "text-halo-color": PALETTE.halo, "text-halo-width": 1.5 },
  });

  for (const id of TRAIN_LAYERS) {
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
  }
  map.on("click", (e) => {
    const pad = 6, box = [[e.point.x - pad, e.point.y - pad], [e.point.x + pad, e.point.y + pad]];
    const train = map.queryRenderedFeatures(box, { layers: TRAIN_LAYERS })[0];
    if (train) return showPopup(train.properties.key);
    const lines = map.queryRenderedFeatures(box, { layers: TRACK_LAYERS.filter((id) => map.getLayer(id)) });
    if (lines.length) showTrackPopup(e.lngLat, lines[0]);
  });

  loadTrack();
  render();
});

const TRAIN_LAYERS = ["trains-dot", "trains-arrow", "trains-sprite", "trains-dot-mid", "consist-fill"];
const TRACK_LAYERS = ["track", "track-ballast", "freight", "freight-minor", "freight-ballast"];

// ---------- freight and other track, fetched by area ----------
const cells = new Map();       // "cx,cy" -> features | "loading" | failure time
let freightTimer = null;

async function loadFreight() {
  if (!freightWanted() || map.getZoom() < FREIGHT_Z - 0.5) return;
  const b = map.getBounds(), c = map.getCenter();
  const want = [];
  for (let cx = Math.floor(b.getWest() / CELL); cx <= Math.floor(b.getEast() / CELL); cx++) {
    for (let cy = Math.floor(b.getSouth() / CELL); cy <= Math.floor(b.getNorth() / CELL); cy++) {
      const k = `${cx},${cy}`, st = cells.get(k);
      if (st === undefined || (typeof st === "number" && Date.now() - st > 60000)) want.push([cx, cy]);
    }
  }
  if (want.length > 80) return;
  // nearest squares first, four at a time
  want.sort((a, z) => Math.hypot((a[0] + 0.5) * CELL - c.lng, (a[1] + 0.5) * CELL - c.lat)
                    - Math.hypot((z[0] + 0.5) * CELL - c.lng, (z[1] + 0.5) * CELL - c.lat));
  for (const [cx, cy] of want) cells.set(`${cx},${cy}`, "loading");
  const queue = [...want];
  const worker = async () => {
    for (let job; (job = queue.shift()); ) {
      const [cx, cy] = job, k = `${cx},${cy}`;
      try {
        const r = await fetch(`api/lines/${cx}/${cy}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        cells.set(k, (await r.json()).features);
        rebuildFreight();
      } catch (e) {
        console.warn("freight lines", k, e);
        cells.set(k, Date.now());
      }
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
}

function rebuildFreight() {
  clearTimeout(freightTimer);
  freightTimer = setTimeout(() => {
    const seen = new Set(), features = [];
    for (const fs of cells.values()) {
      if (!Array.isArray(fs)) continue;
      for (const f of fs) {
        const id = f.properties.i;
        if (id != null && seen.has(id)) continue;   // a line crossing two squares comes back twice
        seen.add(id);
        features.push(f);
      }
    }
    map.getSource("freight").setData({ type: "FeatureCollection", features });
    renderOwners();
  }, 150);
}

map.on("moveend", loadFreight);

// ---------- line filters ----------
const baseFilters = new Map();   // layer id -> the layer's own filter (e.g. "has 2+ tracks")

function applyLineFilters() {
  if (!baseFilters.size) return;
  const ownerTest = hiddenOwners.size
    ? ["!", ["in", ["coalesce", ["get", "o"], ""], ["literal", [...hiddenOwners]]]] : null;
  const kindTest = (src) => {
    const tests = Object.entries(LINE_GROUPS).filter(([g, d]) => d.source === src && lineOn[g]).map(([, d]) => d.test);
    return tests.length ? ["any", ...tests] : ["==", 1, 0];
  };
  for (const [id, base] of baseFilters) {
    const src = map.getLayer(id).source;
    map.setFilter(id, ["all", ...[base, kindTest(src), ownerTest].filter(Boolean)]);
  }
  loadFreight();
  renderOwners();
}

function saveLineFilters() {
  safeSet("lineFilters", JSON.stringify(lineOn));
  safeSet("hiddenOwners", JSON.stringify([...hiddenOwners]));
  applyLineFilters();
}

function renderLineFilters() {
  for (const src of ["track", "freight"]) {
    const ul = document.getElementById(src === "track" ? "lines-passenger" : "lines-freight");
    ul.innerHTML = "";
    for (const [g, d] of Object.entries(LINE_GROUPS)) {
      if (d.source !== src) continue;
      const li = document.createElement("li");
      li.innerHTML = `<label><input type="checkbox" ${lineOn[g] ? "checked" : ""}> ${esc(d.label)}</label>`;
      li.querySelector("input").addEventListener("change", (e) => { lineOn[g] = e.target.checked; saveLineFilters(); });
      ul.appendChild(li);
    }
  }
}

const ownerName = (code) => OWNERS[code] ? `${OWNERS[code]} (${code})` : code;

// Railroads owning the track on screen (plus any hidden ones, so they can be turned back on).
let ownersTimer = null;
function renderOwners() {
  clearTimeout(ownersTimer);
  ownersTimer = setTimeout(() => {
    const counts = new Map();
    const layers = ["track", "freight", "freight-minor", "track-ballast", "freight-ballast"].filter((id) => map.getLayer(id));
    for (const f of map.queryRenderedFeatures({ layers })) {
      const o = f.properties.o;
      if (o) counts.set(o, (counts.get(o) || 0) + 1);
    }
    const shown = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([o]) => o);
    const list = [...new Set([...shown, ...[...hiddenOwners].sort()])];
    const ul = document.getElementById("owners");
    ul.innerHTML = list.length ? "" : `<li class="empty">No track in view</li>`;
    for (const o of list) {
      const li = document.createElement("li");
      li.innerHTML = `<label><input type="checkbox" ${hiddenOwners.has(o) ? "" : "checked"}> ${esc(ownerName(o))}</label>`;
      li.querySelector("input").addEventListener("change", (e) => {
        e.target.checked ? hiddenOwners.delete(o) : hiddenOwners.add(o);
        saveLineFilters();
      });
      ul.appendChild(li);
    }
  }, 300);
}
map.on("moveend", renderOwners);

document.getElementById("layers-reset").addEventListener("click", () => {
  for (const g in lineOn) lineOn[g] = true;
  hiddenOwners.clear();
  renderLineFilters();
  saveLineFilters();
});
renderLineFilters();

// ---------- track popup ----------
const NET_NAMES = { M: "Main line", I: "Major industrial lead", O: "Industrial track", S: "Passing siding", Y: "Yard track" };
const PASSENGER_NAMES = { A: "Amtrak", B: "Amtrak and commuter", C: "Commuter", E: "High-speed rail and commuter",
  I: "High-speed rail", R: "Rapid transit", T: "Tourist or museum", D: "Alaska Railroad" };
const OWNERS = { AMTK: "Amtrak", BNSF: "BNSF Railway", UP: "Union Pacific", CSXT: "CSX", NS: "Norfolk Southern",
  CN: "Canadian National", CPRS: "Canadian Pacific Kansas City", CPKC: "Canadian Pacific Kansas City",
  KCS: "Kansas City Southern", MNCW: "Metro-North", LI: "Long Island Rail Road", NJTR: "NJ Transit",
  SEPA: "SEPTA", MBTA: "MBTA", METX: "Metra", SCAX: "Metrolink", PCJPB: "Caltrain", NJT: "NJ Transit",
  FEC: "Florida East Coast Railway", SCRRA: "Metrolink", CSAO: "Conrail Shared Assets", NICD: "South Shore Line" };

function showTrackPopup(lngLat, f) {
  const p = f.properties;
  const kind = f.source === "track" ? `Passenger: ${PASSENGER_NAMES[p.p] || p.p}` : NET_NAMES[p.n] || "Track";
  const rows = [
    ["Owner", p.o ? ownerName(p.o) : null],
    ["Subdivision", p.s], ["Yard", p.y], ["Tracks", p.t > 1 ? p.t : null],
  ].filter(([, x]) => x);
  if (popup) popup.remove();
  openKey = null;
  popup = new maplibregl.Popup({ closeButton: true, offset: 6 }).setLngLat(lngLat)
    .setHTML(`<div class="pop"><h3>${esc(kind)}</h3>
      <dl>${rows.map(([k, x]) => `<dt>${k}</dt><dd>${esc(String(x))}</dd>`).join("")}</dl>
      <p class="fine">FRA North American Rail Network</p></div>`)
    .addTo(map);
}

async function loadTrack() {
  try {
    const r = await fetch(TRACK_URL);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const fc = await r.json();
    map.getSource("track").setData(fc);
    map.once("idle", renderOwners);   // list the railroads once the track has drawn
    net = new TrackNet(fc);
    for (const v of vehicles.values()) updateMotion(v, true);
    render();
  } catch (e) {
    console.warn("track not loaded yet:", e);
    setTimeout(loadTrack, 15000);
  } finally {
    splashReady("track");
  }
}

function emptyFC() { return { type: "FeatureCollection", features: [] }; }

function visible(v) { return !hidden.has(v.agency); }

// ---------- motion: snap to track, heading, gliding between fixes ----------
function updateMotion(v, force = false) {
  const prev = motion.get(v.key);
  if (prev && prev.fixTs === v.timestamp && !force) return;
  const st = { fixTs: v.timestamp, hdg: null, dirKnown: false, snap: null, dir: 1, speed: 0 };

  if (v.bearing != null) { st.hdg = v.bearing; st.dirKnown = true; }
  if (prev && prev.fixTs !== v.timestamp) {
    // no bearing or speed in the feed: work them out from the last two fixes
    const moved = trackGeo.distM([prev.lon, prev.lat], [v.lon, v.lat]);
    const dt = v.timestamp - prev.fixTs;
    if (moved > 30 && dt > 0) {
      if (!st.dirKnown) { st.hdg = trackGeo.bearingDeg([prev.lon, prev.lat], [v.lon, v.lat]); st.dirKnown = true; }
      st.derivedSpeed = moved / dt;
    } else if (!st.dirKnown && prev.dirKnown) {
      st.hdg = prev.hdg; st.dirKnown = true;      // standing still: keep the last known heading
    }
  } else if (prev && !st.dirKnown && prev.dirKnown) {
    st.hdg = prev.hdg; st.dirKnown = true;
  }

  if (v.status === "STOPPED_AT") st.speed = 0;
  else if (v.speed_mph != null) st.speed = v.speed_mph * 0.44704;
  else st.speed = Math.min(st.derivedSpeed || 0, 70);

  if (net) {
    st.snap = net.nearest(v.lon, v.lat, 150);
    if (st.snap && st.dirKnown) {
      st.dir = trackGeo.angleDiff(st.hdg, net.bearing(st.snap, 1)) <= 90 ? 1 : -1;
    }
  }
  st.lon = v.lon; st.lat = v.lat;
  motion.set(v.key, st);
}

// Where to draw a train right now: { lon, lat, hdg, head, dir } (head/dir only when on the track).
function displayState(v, now) {
  const st = motion.get(v.key);
  if (!st) return { lon: v.lon, lat: v.lat, hdg: v.bearing ?? null };
  if (!st.snap) return { lon: v.lon, lat: v.lat, hdg: st.hdg };
  let head = st.snap, dir = st.dir;
  const glide = Math.min(Math.max(0, now - v.timestamp), MAX_GLIDE_S) * st.speed;
  if (glide > 1 && st.dirKnown) {
    const w = net.walk(st.snap, st.dir, glide);
    if (w.end) { head = w.end; dir = w.dir; }
  }
  const [lon, lat] = net.point(head);
  return { lon, lat, hdg: net.bearing(head, dir), head, dir };
}

function carWidth() {
  const mpp = 1 / PX_PER_M(map.getZoom());
  return Math.max(CAR_WIDTH_M * WIDTH_EXAG, MIN_CAR_PX * mpp);
}

function render() {
  const trains = map.getSource && map.getSource("trains");
  if (trains) {
    const now = Date.now() / 1000;
    const zoomedIn = net && map.getZoom() >= CONSIST_Z - 0.5;
    const bounds = zoomedIn ? map.getBounds() : null;
    const width = zoomedIn ? carWidth() : 0;
    const features = [], consists = [];
    for (const v of vehicles.values()) {
      if (!visible(v)) continue;
      const d = displayState(v, now);
      const st = motion.get(v.key);
      const agencyColor = AGENCY_COLORS[v.agency] || FALLBACK_COLOR;
      let drawn = false;
      if (zoomedIn && d.head && bounds.contains([d.lon, d.lat])) {
        const spec = consistSpec(v);
        const length = spec.reduce((s, c) => s + c.len + 1.2, 0);
        // From the front, back along the track. On multi-track lines, run on the right-hand
        // track for the direction of travel (left of this backwards-running path).
        const n = net.tracks[d.head.line];
        const side = st && st.dirKnown ? ((n - 1) / 2) * 4.3 * WIDTH_EXAG : 0;
        const path = offsetPath(net.walk(d.head, -d.dir, length).path, side);
        consists.push(...consistFeatures(path, spec, width, { key: v.key, agencyColor }));
        drawn = true;
      }
      const props = { key: v.key, train: v.train || "", agencyColor, drawn,
                      dirKnown: !!(st ? st.dirKnown : v.bearing != null) };
      if (d.hdg != null) props.hdg = d.hdg;
      features.push({ type: "Feature", geometry: { type: "Point", coordinates: [d.lon, d.lat] }, properties: props });
      if (v.key === openKey && popup) popup.setLngLat([d.lon, d.lat]);
    }
    trains.setData({ type: "FeatureCollection", features });
    map.getSource("consists").setData({ type: "FeatureCollection", features: consists });
  }
}

// Glide once a second; redraw consists when the zoom changes their scale.
setInterval(render, 1000);
map.on("zoomend", render);
map.on("moveend", render);

// ---------- panel ----------
function feedState(f) {
  if (f.disabled) return "off";
  if (f.fallback_for && !f.count) return "off";
  if (f.last_error && !f.last_ok) return "bad";
  if (f.last_error) return "warn";
  return f.last_ok ? "ok" : "warn";
}

function renderPanel() {
  const counts = {};
  for (const v of vehicles.values()) counts[v.agency] = (counts[v.agency] || 0) + 1;
  const total = vehicles.size;
  document.getElementById("summary").textContent =
    `${total} train${total === 1 ? "" : "s"} live` + (lastUpdate ? ` · updated ${new Date(lastUpdate * 1000).toLocaleTimeString()}` : "");

  // one row per agency; an agency can have a primary and a fallback feed
  const byAgency = new Map();
  for (const f of feeds) {
    if (!byAgency.has(f.agency)) byAgency.set(f.agency, []);
    byAgency.get(f.agency).push(f);
  }
  const ul = document.getElementById("agencies");
  ul.innerHTML = "";
  for (const [agency, fs] of byAgency) {
    const primary = fs.find((f) => !f.fallback_for) || fs[0];
    const fallback = fs.find((f) => f.fallback_for && f.count);
    const state = fallback ? "warn" : feedState(primary);
    let note = "";
    if (primary.disabled) note = "needs an API key";
    else if (fallback) note = "primary feed down, showing Amtraker fallback";
    else if (primary.last_error) note = primary.last_error;

    const li = document.createElement("li");
    li.innerHTML = `<span class="dot ${state}" title="${state}"></span>
      <label><input type="checkbox" ${hidden.has(agency) || primary.disabled ? "" : "checked"} ${primary.disabled ? "disabled" : ""}>
      <span class="swatch" style="background:${AGENCY_COLORS[agency] || FALLBACK_COLOR}"></span>
      <span>${esc(agency)}${note ? `<span class="note">${esc(note)}${primary.disabled
        ? ` · <a href="settings.html#${esc(primary.id)}">add key</a>` : ""}</span>` : ""}</span></label>
      <span class="n">${counts[agency] || 0}</span>`;
    li.querySelector("input").addEventListener("change", (e) => {
      e.target.checked ? hidden.delete(agency) : hidden.add(agency);
      safeSet("hiddenAgencies", JSON.stringify([...hidden]));
      render();
      renderPanel();
    });
    ul.appendChild(li);
  }

  const credits = document.getElementById("creditlist");
  credits.innerHTML = [...new Set(feeds.filter((f) => !f.disabled && f.credit).map((f) => f.credit))]
    .map((c) => `<li>${esc(c)}</li>`).join("");
  renderResults();
}

const search = document.getElementById("search");
search.addEventListener("input", renderResults);

function renderResults() {
  const q = search.value.trim().toLowerCase();
  const ul = document.getElementById("results");
  ul.innerHTML = "";
  if (!q) return;
  const hits = [...vehicles.values()].filter((v) =>
    (v.train || "").toLowerCase().startsWith(q) || (v.route || "").toLowerCase().includes(q)).slice(0, 12);
  for (const v of hits) {
    const li = document.createElement("li");
    li.textContent = `${v.agency} ${v.train ? "#" + v.train : ""} ${v.route || ""}`;
    li.addEventListener("click", () => {
      hidden.delete(v.agency);
      const d = displayState(v, Date.now() / 1000);
      map.flyTo({ center: [d.lon, d.lat], zoom: Math.max(map.getZoom(), 15.5) });
      showPopup(v.key);
      render();
      renderPanel();
    });
    ul.appendChild(li);
  }
  if (!hits.length) ul.innerHTML = `<li style="cursor:default;color:var(--muted)">No matching trains</li>`;
}

// ---------- popup ----------
let popup = null, openKey = null;

function popupHtml(v) {
  const rows = [
    ["Route", v.route], ["To", v.headsign],
    [v.status === "STOPPED_AT" ? "At" : "Next", v.stop],
    ["Speed", v.speed_mph != null ? `${Math.round(v.speed_mph)} mph` : null],
    ["Cars", v.cars],
    ["Updated", `${ago(v.timestamp)} ago`],
  ].filter(([, x]) => x);
  return `<div class="pop"><h3>${esc(v.agency)} ${v.train ? "#" + esc(v.train) : ""}</h3>
    <dl>${rows.map(([k, x]) => `<dt>${k}</dt><dd>${esc(String(x))}</dd>`).join("")}</dl>
    <p class="fine">${v.cars ? "Car count is live from the feed." : "Train length and cars drawn are typical for this service, not live."}</p></div>`;
}

function showPopup(key) {
  const v = vehicles.get(key);
  if (!v) return;
  if (popup) popup.remove();
  openKey = key;
  const d = displayState(v, Date.now() / 1000);
  popup = new maplibregl.Popup({ closeButton: true, offset: 14 })
    .setLngLat([d.lon, d.lat]).setHTML(popupHtml(v)).addTo(map);
  popup.on("close", () => { if (openKey === key) openKey = null; });
}

function refreshPopup() {
  const v = vehicles.get(openKey);
  if (!v) { popup && popup.remove(); openKey = null; return; }
  popup.setHTML(popupHtml(v));
}

function ago(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 90 ? `${s}s` : `${Math.round(s / 60)}m`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

addMoreHint(document.getElementById("panel"));

// ---------- splash ----------
// Shown until the map, track and trains are in and the logo's lens flare has played (or on a click).
const splashWaiting = new Set(["map", "track", "trains", "intro"]);
function splashReady(what) {
  splashWaiting.delete(what);
  if (!splashWaiting.size) hideSplash();
}
function hideSplash() {
  const s = document.getElementById("splash");
  if (!s || s.classList.contains("gone")) return;
  s.classList.add("gone");
  setTimeout(() => { s.remove(); SplashFX.stop(); }, 700);
}
map.on("load", () => splashReady("map"));
SplashFX.play(document.getElementById("splash-logo"), "img/moon-pi-logo")
  .catch((e) => console.warn("splash:", e.message))
  .finally(() => splashReady("intro"));
setTimeout(hideSplash, 8000);   // never hold the map back for long
document.getElementById("splash").addEventListener("click", hideSplash);

// ---------- live connection ----------
let lastUpdate = null, retry = 1000;

function connect() {
  const conn = document.getElementById("conn");
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => { conn.className = "conn on"; conn.textContent = "live"; retry = 1000; };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "snapshot") {
      vehicles.clear();
      for (const v of msg.vehicles) vehicles.set(v.key, v);
      if (msg.version) document.getElementById("version").textContent = `v${msg.version}`;
      splashReady("trains");
    } else if (msg.type === "update") {
      for (const k of msg.remove) { vehicles.delete(k); motion.delete(k); }
      for (const v of msg.upsert) vehicles.set(v.key, v);
    }
    for (const v of vehicles.values()) updateMotion(v);
    feeds = msg.feeds || feeds;
    lastUpdate = msg.t;
    render();
    renderPanel();
    if (openKey) refreshPopup();
  };
  ws.onclose = () => {
    conn.className = "conn off"; conn.textContent = "reconnecting";
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 30000);
  };
}
connect();

document.getElementById("toggle").addEventListener("click", () =>
  document.getElementById("panel").classList.toggle("collapsed"));
