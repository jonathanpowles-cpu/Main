from dataclasses import dataclass, field
from models.enums import AircraftRole, AircraftStatus, Side


@dataclass
class AircraftType:
    id: str
    name: str
    side: Side
    role: AircraftRole
    speed_mph: int
    climb_rate_fpm: int
    service_ceiling_ft: int
    range_miles: int
    armament: str
    firepower: int
    agility: int
    durability: int
    fuel_capacity_gallons: float
    fuel_burn_per_hour: float
    crew: int
    production_per_week: float
    bomb_load_lbs: int = 0
    dive_bombing_accuracy: int = 0


@dataclass
class Aircraft:
    id: str
    aircraft_type: str
    squadron_id: str
    status: AircraftStatus = AircraftStatus.READY
    damage: float = 0.0
    fuel_remaining: float = 1.0
    ammo_remaining: float = 1.0
    sorties_flown: int = 0
    kills: int = 0
    repair_hours_remaining: int = 0

    def is_available(self) -> bool:
        return self.status == AircraftStatus.READY

    def needs_repair(self) -> bool:
        return self.status in (AircraftStatus.DAMAGED, AircraftStatus.REPAIRING)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "aircraft_type": self.aircraft_type,
            "squadron_id": self.squadron_id,
            "status": self.status.value,
            "damage": self.damage,
            "fuel_remaining": self.fuel_remaining,
            "ammo_remaining": self.ammo_remaining,
            "sorties_flown": self.sorties_flown,
            "kills": self.kills,
        }
