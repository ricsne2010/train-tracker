// Track network built from NARN lines: snap trains onto the track, walk along it, and
// build top-down outlines of locomotives and cars that follow the curves.
"use strict";

const M_PER_DEG_LAT = 110574;
const mPerDegLon = (lat) => 111320 * Math.cos((lat * Math.PI) / 180);

function distM(a, b) {
  const kx = mPerDegLon((a[1] + b[1]) / 2);
  return Math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * M_PER_DEG_LAT);
}

function bearingDeg(a, b) {
  const kx = mPerDegLon((a[1] + b[1]) / 2);
  const deg = (Math.atan2((b[0] - a[0]) * kx, (b[1] - a[1]) * M_PER_DEG_LAT) * 180) / Math.PI;
  return (deg + 360) % 360;
}

function angleDiff(a, b) {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];

class TrackNet {
  constructor(fc) {
    this.lines = [];            // arrays of [lon, lat]
    this.tracks = [];           // number of parallel tracks on each line (NARN TRACKS)
    this.cell = 0.01;           // grid cell size in degrees (~1 km)
    this.grid = new Map();      // "cx,cy" -> [[line, seg], ...]
    this.nodes = new Map();     // "lon,lat" of a line end -> [{ line, end: 0 | 1 }]
    for (const f of fc.features) {
      const g = f.geometry;
      if (!g) continue;
      const parts = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
      const n = Math.max(1, Math.min(3, (f.properties && f.properties.t) || 1));
      for (const coords of parts) if (coords.length >= 2) this.addLine(coords, n);
    }
  }

  addLine(coords, tracks = 1) {
    const id = this.lines.length;
    this.lines.push(coords);
    this.tracks.push(tracks);
    for (let i = 0; i < coords.length - 1; i++) {
      const [x1, y1] = coords[i], [x2, y2] = coords[i + 1];
      for (let cx = Math.floor(Math.min(x1, x2) / this.cell); cx <= Math.floor(Math.max(x1, x2) / this.cell); cx++) {
        for (let cy = Math.floor(Math.min(y1, y2) / this.cell); cy <= Math.floor(Math.max(y1, y2) / this.cell); cy++) {
          const k = `${cx},${cy}`;
          if (!this.grid.has(k)) this.grid.set(k, []);
          this.grid.get(k).push([id, i]);
        }
      }
    }
    for (const end of [0, 1]) {
      const k = String(coords[end ? coords.length - 1 : 0]);
      if (!this.nodes.has(k)) this.nodes.set(k, []);
      this.nodes.get(k).push({ line: id, end });
    }
  }

  // Nearest point on any track within maxM metres: { line, seg, t, d } or null.
  nearest(lon, lat, maxM = 150) {
    const kx = mPerDegLon(lat), cx0 = Math.floor(lon / this.cell), cy0 = Math.floor(lat / this.cell);
    let best = null;
    for (let cx = cx0 - 1; cx <= cx0 + 1; cx++) {
      for (let cy = cy0 - 1; cy <= cy0 + 1; cy++) {
        for (const [line, seg] of this.grid.get(`${cx},${cy}`) || []) {
          const a = this.lines[line][seg], b = this.lines[line][seg + 1];
          const ax = (a[0] - lon) * kx, ay = (a[1] - lat) * M_PER_DEG_LAT;
          const bx = (b[0] - lon) * kx, by = (b[1] - lat) * M_PER_DEG_LAT;
          const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
          const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
          const d = Math.hypot(ax + dx * t, ay + dy * t);
          if (d <= maxM && (!best || d < best.d)) best = { line, seg, t, d };
        }
      }
    }
    return best;
  }

  point(pos) {
    const c = this.lines[pos.line];
    return lerp(c[pos.seg], c[pos.seg + 1], pos.t);
  }

  // Bearing of the track at pos, facing along the line's coordinate order (dir +1) or against it (-1).
  bearing(pos, dir) {
    const c = this.lines[pos.line];
    const b = bearingDeg(c[pos.seg], c[pos.seg + 1]);
    return dir > 0 ? b : (b + 180) % 360;
  }

  // Walk `meters` from pos in direction dir, following the track through junctions
  // (taking the straightest continuation). Returns { path, end, dir }; end is null if
  // the track ran out and the path was extended in a straight line.
  walk(pos, dir, meters) {
    let { line, seg, t } = pos;
    let cur = this.point(pos), heading = this.bearing(pos, dir);
    const path = [cur];
    let remaining = meters;
    for (let guard = 0; guard < 5000 && remaining > 0; guard++) {
      const c = this.lines[line];
      const nxt = dir > 0 ? c[seg + 1] : c[seg];
      const L = distM(cur, nxt);
      if (L >= remaining) {
        const f = L ? remaining / L : 0;
        cur = lerp(cur, nxt, f);
        t = dir > 0 ? t + f * (1 - t) : t * (1 - f);
        path.push(cur);
        return { path, end: { line, seg, t }, dir };
      }
      remaining -= L;
      if (L > 0) heading = bearingDeg(cur, nxt);
      cur = nxt;
      path.push(cur);
      if (dir > 0 && seg + 1 < c.length - 1) { seg++; t = 0; continue; }
      if (dir < 0 && seg > 0) { seg--; t = 1; continue; }

      // End of this line: continue on the straightest line meeting at this node.
      let pick = null, pickDiff = 60;
      for (const n of this.nodes.get(String(nxt)) || []) {
        if (n.line === line) continue;
        const cc = this.lines[n.line];
        const out = n.end === 0 ? bearingDeg(cc[0], cc[1]) : bearingDeg(cc[cc.length - 1], cc[cc.length - 2]);
        const diff = angleDiff(out, heading);
        if (diff < pickDiff) { pick = n; pickDiff = diff; }
      }
      if (!pick) break;
      line = pick.line;
      const cc = this.lines[line];
      if (pick.end === 0) { dir = 1; seg = 0; t = 0; } else { dir = -1; seg = cc.length - 2; t = 1; }
    }
    if (remaining > 0) {   // ran off the mapped track: carry on straight
      const r = (heading * Math.PI) / 180;
      path.push([cur[0] + (Math.sin(r) * remaining) / mPerDegLon(cur[1]), cur[1] + (Math.cos(r) * remaining) / M_PER_DEG_LAT]);
    }
    return { path, end: null, dir };
  }
}

// Shift a path sideways by `meters` (positive = to the left of the direction it runs).
function offsetPath(path, meters) {
  if (!meters) return path;
  return path.map((p, i) => {
    const a = path[Math.max(0, i - 1)], b = path[Math.min(path.length - 1, i + 1)];
    const kx = mPerDegLon(p[1]);
    const tx = (b[0] - a[0]) * kx, ty = (b[1] - a[1]) * M_PER_DEG_LAT, len = Math.hypot(tx, ty) || 1;
    return [p[0] + (-ty / len) * meters / kx, p[1] + (tx / len) * meters / M_PER_DEG_LAT];
  });
}

// Sub-path of `path` between distances s0 and s1 from its start.
function slicePath(path, cum, s0, s1) {
  const out = [];
  for (let i = 0; i < path.length - 1; i++) {
    const a = cum[i], b = cum[i + 1];
    if (b < s0) continue;
    if (a > s1) break;
    const seg = b - a || 1;
    if (!out.length) out.push(lerp(path[i], path[i + 1], Math.max(0, (s0 - a) / seg)));
    if (b < s1) out.push(path[i + 1]);
    else { out.push(lerp(path[i], path[i + 1], (s1 - a) / seg)); break; }
  }
  return out.length >= 2 ? out : null;
}

// Closed polygon ring around a centreline, `width` metres wide.
function outline(line, width) {
  const left = [], right = [], h = width / 2;
  for (let i = 0; i < line.length; i++) {
    const a = line[Math.max(0, i - 1)], b = line[Math.min(line.length - 1, i + 1)];
    const kx = mPerDegLon(line[i][1]);
    let tx = (b[0] - a[0]) * kx, ty = (b[1] - a[1]) * M_PER_DEG_LAT;
    const len = Math.hypot(tx, ty) || 1;
    tx /= len; ty /= len;
    const nx = -ty * h, ny = tx * h;   // left normal in metres
    left.push([line[i][0] + nx / kx, line[i][1] + ny / M_PER_DEG_LAT]);
    right.push([line[i][0] - nx / kx, line[i][1] - ny / M_PER_DEG_LAT]);
  }
  return [[...left, ...right.reverse(), left[0]]];
}

// Polygons for a whole train: `path` runs from the front of the train backwards.
// spec is a list of vehicles { kind: "loco" | "car" | "cab", len }.
function consistFeatures(path, spec, width, props) {
  const cum = [0];
  for (let i = 1; i < path.length; i++) cum.push(cum[i - 1] + distM(path[i - 1], path[i]));
  const out = [], GAP = 1.2;
  const poly = (coords, part, z) =>
    out.push({ type: "Feature", geometry: { type: "Polygon", coordinates: coords }, properties: { ...props, part, z } });
  let s = 0;
  spec.forEach((veh, i) => {
    const body = slicePath(path, cum, s, s + veh.len);
    if (!body) return;
    poly(outline(body, width), veh.kind === "car" ? "car" : "loco", 1);
    if (veh.kind === "car") {
      const stripe = slicePath(path, cum, s + 1.5, s + veh.len - 1.5);
      if (stripe) poly(outline(stripe, width * 0.22), "stripe", 2);
    } else {
      // roof hatch along the middle of a locomotive / cab car
      const hatch = slicePath(path, cum, s + veh.len * 0.3, s + veh.len * 0.75);
      if (hatch) poly(outline(hatch, width * 0.45), "hatch", 2);
    }
    // windshield at the leading end of the train, and at the tail of a push-pull cab car
    const front = i === 0, rearCab = i === spec.length - 1 && veh.kind !== "car";
    if (front) { const w = slicePath(path, cum, s + 0.3, s + 1.6); if (w) poly(outline(w, width * 0.72), "glass", 3); }
    if (rearCab && !front) { const w = slicePath(path, cum, s + veh.len - 1.6, s + veh.len - 0.3); if (w) poly(outline(w, width * 0.72), "glass", 3); }
    s += veh.len + GAP;
  });
  return out;
}

// Typical (not live) consist for a train, from its agency and route name.
const LONG_DISTANCE = /Limited|Chief|Zephyr|Builder|Starlight|Eagle|City of New Orleans|Crescent|Silver|Palmetto|Cardinal|Auto Train|Floridian|Meteor|Sunset/i;
function consistSpec(v) {
  const loco = (len = 21) => ({ kind: "loco", len });
  const cars = (n, len = 26) => Array.from({ length: n }, () => ({ kind: "car", len }));
  const cab = { kind: "cab", len: 26 };
  if (v.agency === "Amtrak") {
    const r = v.route || "";
    if (/Acela/i.test(r)) return [loco(21), ...cars(6), loco(21)];
    if (LONG_DISTANCE.test(r)) return [loco(22), loco(22), ...cars(9, 26)];
    return [loco(22), ...cars(6)];
  }
  if (v.agency === "LIRR") return [cab, ...cars(8), cab];
  if (v.agency === "Metro-North") return [cab, ...cars(6), cab];
  if (v.cars >= 2) return [cab, ...cars(v.cars - 2), cab];   // live car count (SEPTA)
  if (v.agency === "SEPTA Regional Rail") return [cab, ...cars(4), cab];
  return [loco(20), ...cars(5), cab];   // push-pull commuter sets
}

window.TrackNet = TrackNet;
window.consistFeatures = consistFeatures;
window.offsetPath = offsetPath;
window.consistSpec = consistSpec;
window.trackGeo = { distM, bearingDeg, angleDiff };
