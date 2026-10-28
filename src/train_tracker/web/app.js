// US Train Tracker frontend: NARN track lines + live trains pushed over WebSocket.
"use strict";

const AGENCY_COLORS = {
  "Amtrak": "#1f6feb",
  "MBTA Commuter Rail": "#80276c",
  "LIRR": "#0f8a5f",
  "Metro-North": "#d1352b",
  "SEPTA Regional Rail": "#4b6ea8",
  "Metra": "#e07b00",
  "Caltrain": "#b5121b",
  "Metrolink": "#2f6b3a",
  "NJ Transit Rail": "#7a4fbf",
};
const TRACK_COLORS = ["match", ["get", "p"], "A", "#5b8def", "C", "#3fb68b", "#9aa3b2"];
const dark = matchMedia("(prefers-color-scheme: dark)").matches;

const vehicles = new Map();         // key -> vehicle
let feeds = [];
const hidden = new Set(JSON.parse(safeGet("hiddenAgencies") || "[]"));

function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }

const map = new maplibregl.Map({
  container: "map",
  style: `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`,
  center: [-96, 38.5],
  zoom: 3.6,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

const FALLBACK_COLOR = "#888888";

// One pre-coloured arrow per agency (rotated by bearing on the map), outlined for contrast.
function arrowImage(color) {
  const s = 32, c = document.createElement("canvas");
  c.width = c.height = s;
  const g = c.getContext("2d");
  g.beginPath();
  g.moveTo(s / 2, 3); g.lineTo(s - 7, s - 5); g.lineTo(s / 2, s - 11); g.lineTo(7, s - 5);
  g.closePath();
  g.lineJoin = "round"; g.lineWidth = 3; g.strokeStyle = dark ? "#0f1218" : "#ffffff"; g.stroke();
  g.fillStyle = color; g.fill();
  return g.getImageData(0, 0, s, s);
}

map.on("load", () => {
  for (const color of new Set([...Object.values(AGENCY_COLORS), FALLBACK_COLOR])) {
    map.addImage(`arrow-${color}`, arrowImage(color));
  }

  map.addSource("track", { type: "geojson", data: "data/narn_passenger.geojson" });
  map.addLayer({
    id: "track", type: "line", source: "track",
    paint: {
      "line-color": TRACK_COLORS,
      "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1, 8, 2, 13, 3.5],
      "line-opacity": 0.85,
    },
  });

  map.addSource("trains", { type: "geojson", data: emptyFC() });
  const color = ["get", "agencyColor"];
  map.addLayer({   // trains without a bearing: a dot
    id: "trains-dot", type: "circle", source: "trains", filter: ["!", ["has", "bearing"]],
    paint: {
      "circle-color": color,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3.5, 10, 7],
      "circle-stroke-color": dark ? "#0f1218" : "#fff", "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({   // trains with a bearing: a rotated arrow
    id: "trains-arrow", type: "symbol", source: "trains", filter: ["has", "bearing"],
    layout: {
      "icon-image": ["concat", "arrow-", color], "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map",
      "icon-allow-overlap": true, "icon-ignore-placement": true,
      "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 10, 0.85],
    },
  });
  map.addLayer({
    id: "trains-label", type: "symbol", source: "trains", minzoom: 6,
    layout: {
      "text-field": ["coalesce", ["get", "train"], ""], "text-size": 11,
      "text-offset": [0, 1.3], "text-anchor": "top", "text-font": ["Noto Sans Regular"],
    },
    paint: { "text-color": dark ? "#e6e9ef" : "#1d2330", "text-halo-color": dark ? "#0f1218" : "#fff", "text-halo-width": 1.2 },
  });

  for (const id of ["trains-dot", "trains-arrow"]) {
    map.on("click", id, (e) => showPopup(e.features[0].properties.key));
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
  }
  render();
});

function emptyFC() { return { type: "FeatureCollection", features: [] }; }

function visible(v) { return !hidden.has(v.agency); }

function render() {
  const src = map.getSource && map.getSource("trains");
  if (src) {
    const features = [];
    for (const v of vehicles.values()) {
      if (!visible(v)) continue;
      const props = { ...v, agencyColor: AGENCY_COLORS[v.agency] || FALLBACK_COLOR };
      features.push({ type: "Feature", geometry: { type: "Point", coordinates: [v.lon, v.lat] }, properties: props });
    }
    src.setData({ type: "FeatureCollection", features });
  }
  renderPanel();
  if (openKey) refreshPopup();
}

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
    if (primary.disabled) note = primary.disabled;
    else if (fallback) note = "primary feed down, showing Amtraker fallback";
    else if (primary.last_error) note = primary.last_error;

    const li = document.createElement("li");
    li.innerHTML = `<span class="dot ${state}" title="${state}"></span>
      <label><input type="checkbox" ${hidden.has(agency) || primary.disabled ? "" : "checked"} ${primary.disabled ? "disabled" : ""}>
      <span class="swatch" style="background:${AGENCY_COLORS[agency] || "#888"}"></span>
      <span>${esc(agency)}${note ? `<span class="note">${esc(note)}</span>` : ""}</span></label>
      <span class="n">${counts[agency] || 0}</span>`;
    li.querySelector("input").addEventListener("change", (e) => {
      e.target.checked ? hidden.delete(agency) : hidden.add(agency);
      safeSet("hiddenAgencies", JSON.stringify([...hidden]));
      render();
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
      map.flyTo({ center: [v.lon, v.lat], zoom: Math.max(map.getZoom(), 10) });
      showPopup(v.key);
      render();
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
    ["Updated", `${ago(v.timestamp)} ago`],
  ].filter(([, x]) => x);
  return `<div class="pop"><h3>${esc(v.agency)} ${v.train ? "#" + esc(v.train) : ""}</h3>
    <dl>${rows.map(([k, x]) => `<dt>${k}</dt><dd>${esc(String(x))}</dd>`).join("")}</dl></div>`;
}

function showPopup(key) {
  const v = vehicles.get(key);
  if (!v) return;
  if (popup) popup.remove();
  openKey = key;
  popup = new maplibregl.Popup({ closeButton: true, offset: 10 })
    .setLngLat([v.lon, v.lat]).setHTML(popupHtml(v)).addTo(map);
  popup.on("close", () => { if (openKey === key) openKey = null; });
}

function refreshPopup() {
  const v = vehicles.get(openKey);
  if (!v) { popup && popup.remove(); openKey = null; return; }
  popup.setLngLat([v.lon, v.lat]).setHTML(popupHtml(v));
}

function ago(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 90 ? `${s}s` : `${Math.round(s / 60)}m`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

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
    } else if (msg.type === "update") {
      for (const k of msg.remove) vehicles.delete(k);
      for (const v of msg.upsert) vehicles.set(v.key, v);
    }
    feeds = msg.feeds || feeds;
    lastUpdate = msg.t;
    render();
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
