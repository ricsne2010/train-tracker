"""The one vehicle-position model every feed is normalized into."""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Vehicle:
    key: str                      # globally unique: "<feed id>:<vehicle id>"
    feed: str                     # feed id from feeds.json
    agency: str
    mode: str                     # "intercity" | "commuter"
    lat: float
    lon: float
    timestamp: int                # unix seconds of the position fix
    train: Optional[str] = None   # public train number, e.g. "508"
    route: Optional[str] = None   # human route name, e.g. "Cascades"
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    headsign: Optional[str] = None
    bearing: Optional[float] = None   # degrees clockwise from north
    speed_mph: Optional[float] = None
    status: Optional[str] = None      # STOPPED_AT | IN_TRANSIT_TO | INCOMING_AT
    stop: Optional[str] = None        # next / current stop name or code
    color: Optional[str] = None       # route colour hex without '#', if known

    def to_json(self):
        return {k: v for k, v in asdict(self).items() if v is not None}
