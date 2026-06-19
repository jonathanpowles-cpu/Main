from dataclasses import dataclass, field
from models.enums import Side


@dataclass
class Airfield:
    id: str
    name: str
    side: Side
    lat: float
    lon: float
    airfield_type: str
    group: str
    hangars: int = 3
    dispersal_pens: int = 12
    runway_condition: float = 1.0
    facilities_condition: float = 1.0
    repair_capacity: int = 3
    fuel_storage_tons: float = 100.0
    fuel_current_tons: float = 100.0
    ammo_storage_tons: float = 50.0
    ammo_current_tons: float = 50.0
    aa_guns: int = 4
    squadron_ids: list = field(default_factory=list)
    under_attack: bool = False
    damage_log: list = field(default_factory=list)

    def is_operational(self) -> bool:
        return self.runway_condition > 0.3 and self.facilities_condition > 0.2

    def can_launch(self) -> bool:
        return (
            self.runway_condition > 0.5
            and self.fuel_current_tons > 1.0
            and self.ammo_current_tons > 0.5
        )

    def repair(self, hours: float):
        repair_rate = 0.02 * hours
        self.runway_condition = min(1.0, self.runway_condition + repair_rate * 1.5)
        self.facilities_condition = min(1.0, self.facilities_condition + repair_rate)

    def receive_damage(self, severity: float):
        self.runway_condition = max(0.0, self.runway_condition - severity * 0.4)
        self.facilities_condition = max(0.0, self.facilities_condition - severity * 0.3)
        hangars_hit = int(severity * self.hangars * 0.3)
        self.hangars = max(0, self.hangars - hangars_hit)

    def resupply(self, fuel_tons: float, ammo_tons: float):
        self.fuel_current_tons = min(self.fuel_storage_tons, self.fuel_current_tons + fuel_tons)
        self.ammo_current_tons = min(self.ammo_storage_tons, self.ammo_current_tons + ammo_tons)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "side": self.side.value,
            "lat": self.lat,
            "lon": self.lon,
            "type": self.airfield_type,
            "group": self.group,
            "runway_condition": round(self.runway_condition, 2),
            "facilities_condition": round(self.facilities_condition, 2),
            "fuel_pct": round(self.fuel_current_tons / max(1, self.fuel_storage_tons), 2),
            "ammo_pct": round(self.ammo_current_tons / max(1, self.ammo_storage_tons), 2),
            "is_operational": self.is_operational(),
            "can_launch": self.can_launch(),
            "squadron_ids": self.squadron_ids,
            "under_attack": self.under_attack,
            "aa_guns": self.aa_guns,
        }
