from dataclasses import dataclass


@dataclass
class IndustrialTarget:
    id: str
    name: str
    target_type: str  # aircraft_factory, shipyard, oil_storage, docks, railway, power_station, port
    lat: float
    lon: float
    city: str
    strategic_value: int  # 1-3
    description: str
    condition: float = 1.0   # 0=destroyed, 1=intact
    times_bombed: int = 0
    repair_rate_per_day: float = 0.05

    def repair(self, hours: float):
        if self.condition < 1.0:
            self.condition = min(1.0, self.condition + self.repair_rate_per_day * hours / 24)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target_type": self.target_type,
            "lat": self.lat,
            "lon": self.lon,
            "city": self.city,
            "strategic_value": self.strategic_value,
            "description": self.description,
            "condition": round(self.condition, 3),
            "times_bombed": self.times_bombed,
            "repair_rate_per_day": self.repair_rate_per_day,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IndustrialTarget":
        return cls(
            id=data["id"],
            name=data["name"],
            target_type=data["target_type"],
            lat=data["lat"],
            lon=data["lon"],
            city=data["city"],
            strategic_value=data["strategic_value"],
            description=data["description"],
            condition=data.get("condition", 1.0),
            times_bombed=data.get("times_bombed", 0),
            repair_rate_per_day=data.get("repair_rate_per_day", 0.05),
        )
