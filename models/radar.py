from dataclasses import dataclass
from models.enums import Side


@dataclass
class RadarStation:
    id: str
    name: str
    lat: float
    lon: float
    station_type: str
    range_miles: float
    min_altitude_ft: int
    condition: float = 1.0
    operational: bool = True

    def detection_range(self) -> float:
        return self.range_miles * self.condition

    def can_detect(self, target_altitude_ft: int, distance_miles: float) -> bool:
        if not self.operational or self.condition <= 0:
            return False
        if target_altitude_ft < self.min_altitude_ft:
            return False
        return distance_miles <= self.detection_range()

    def receive_damage(self, severity: float):
        self.condition = max(0.0, self.condition - severity)
        if self.condition < 0.1:
            self.operational = False

    def repair(self, hours: float):
        self.condition = min(1.0, self.condition + hours * 0.04)
        if self.condition > 0.3:
            self.operational = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "type": self.station_type,
            "range_miles": round(self.detection_range(), 1),
            "max_range_miles": self.range_miles,
            "min_altitude_ft": self.min_altitude_ft,
            "condition": round(self.condition, 2),
            "operational": self.operational,
        }
