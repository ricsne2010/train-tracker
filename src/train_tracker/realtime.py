"""Trip updates (predicted times and delays) and service alerts from GTFS-Realtime, plus what they mean for
one train: its next stop, when it gets there and how late it's running."""
import re
import time

SKIPPED = 1
PAST_GRACE_S = 30          # a stop counts as "next" until this long after its predicted time


def trip_state(tu, entity_id=None) -> dict:
    """The parts of one TripUpdate we use."""
    stops = []
    for u in tu.stop_time_update:
        if u.schedule_relationship == SKIPPED:
            continue
        arr = u.arrival.time if u.HasField("arrival") and u.arrival.time else None
        dep = u.departure.time if u.HasField("departure") and u.departure.time else None
        if u.HasField("arrival") and u.arrival.HasField("delay"):
            delay = u.arrival.delay
        elif u.HasField("departure") and u.departure.HasField("delay"):
            delay = u.departure.delay
        else:
            delay = None
        stops.append((u.stop_id, arr, dep, delay))
    return {
        "trip_id": tu.trip.trip_id or None,
        "entity": entity_id,      # Metro-North keys these by train number, which is its vehicles' trip_id
        "sched": None,            # the timetable's trip_id, when it differs (filled in once matched to a train)
        "route_id": tu.trip.route_id or None,
        "start_date": tu.trip.start_date or None,
        "vehicle_id": tu.vehicle.id or None,
        "delay": tu.delay if tu.HasField("delay") else None,
        "stops": stops,
    }


def stop_delay(trip, stop, static, now):
    """How late (seconds, negative = early) a train is at one of its stop entries, or None if unknown."""
    stop_id, arr, dep, delay = stop
    if delay is not None:
        return delay
    t = arr or dep
    tid = trip.get("sched") or trip.get("trip_id")
    if t and static and tid:
        sched = static.scheduled(tid, stop_id, trip.get("start_date"), near=t)
        if sched is not None and abs(t - sched) < 12 * 3600:
            return int(t - sched)
    return trip.get("delay")


def progress(trip, static, now=None) -> dict:
    """{"next_stop", "next_time", "delay"} for a train from its trip update (empty if nothing is known)."""
    now = now or time.time()
    out = {}
    nxt = next((s for s in trip["stops"] if (s[1] or s[2]) and (s[1] or s[2]) >= now - PAST_GRACE_S), None)
    if nxt:
        out["next_stop"] = static.stop_name(nxt[0]) if static else nxt[0]
        out["next_time"] = int(nxt[1] or nxt[2])
        d = stop_delay(trip, nxt, static, now)
    else:
        # SEPTA sends one entry with no stop, just the delay; others may only have passed stops left
        d = trip.get("delay")
        if d is None:
            d = next((s[3] for s in reversed(trip["stops"]) if s[3] is not None), None)
    if d is not None:
        out["delay"] = int(d)
    return out


def _text(ts):
    """A TranslatedString in English if there's an English version, else the first one."""
    if not ts.translation:
        return None
    best = next((t for t in ts.translation if (t.language or "en").lower().startswith("en")), ts.translation[0])
    return best.text.strip() or None


EFFECTS = {1: "No service", 2: "Reduced service", 3: "Significant delays", 4: "Detour", 5: "Additional service",
           6: "Modified service", 7: "Other effect", 9: "Stop moved", 10: "No effect", 11: "Accessibility issue"}


def parse_alert(ent, now=None) -> dict | None:
    """One active service alert, or None if it isn't active now or says nothing."""
    now = now or time.time()
    a = ent.alert
    periods = [(p.start or 0, p.end or 0) for p in a.active_period]
    if periods and not any(s <= now and (not e or now < e) for s, e in periods):
        return None
    header = _text(a.header_text)
    desc = _text(a.description_text)
    if not header and not desc:
        return None
    if desc and not header:
        # Amtrak sends only a description: its first sentence makes the headline
        first = re.split(r"(?<=[.!?])\s+", desc, maxsplit=1)
        header, desc = first[0], (first[1].strip() if len(first) > 1 else None)
    elif desc and header and desc.lower().startswith(header.lower()):
        # Amtrak repeats the headline at the start of the description, which reads better than its ALL CAPS one
        header, desc = desc[:len(header)], desc[len(header):].strip() or None
    starts = [s for s, _ in periods if s]
    ends = [e for _, e in periods if e]
    return {
        "id": ent.id,
        "header": header,
        "description": desc,
        "url": _text(a.url),
        "effect": EFFECTS.get(a.effect) if a.HasField("effect") else None,
        "start": min(starts) if starts else None,
        "end": max(ends) if ends else None,
        "routes": sorted({e.route_id for e in a.informed_entity if e.route_id}),
        "stops": sorted({e.stop_id for e in a.informed_entity if e.stop_id}),
        "trips": sorted({e.trip.trip_id for e in a.informed_entity if e.HasField("trip") and e.trip.trip_id}),
        "agency_wide": any(e.agency_id and not (e.route_id or e.stop_id or e.HasField("trip"))
                           for e in a.informed_entity) or not a.informed_entity,
    }
