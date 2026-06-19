from dataclasses import dataclass, field
from models.enums import AircraftRole, AircraftStatus, Side


@dataclass
class CombatProfile:
    turn_rate: int = 5
    roll_rate: int = 5
    dive_speed_mph: int = 400
    zoom_climb: int = 5
    high_alt_modifier: float = 0.7
    low_alt_modifier: float = 0.8
    optimal_alt_ft: int = 18000
    armament_type: str = "mg_battery"
    burst_mass_lbs_sec: float = 1.0
    ammo_seconds: float = 14
    lethal_burst_sec: float = 2.0
    convergence_range_yds: int = 250
    effective_range_yds: int = 300
    fuel_injection: bool = False
    cockpit_visibility: float = 0.6
    gun_platform_stability: float = 0.8
    structural_g_limit: float = 8.0
    bounce_vulnerability: float = 0.3
    formation_defense_bonus: float = 0.0

    def turning_fight_score(self) -> float:
        return self.turn_rate * 0.4 + self.roll_rate * 0.3 + self.gun_platform_stability * 3

    def boom_zoom_score(self) -> float:
        return self.dive_speed_mph / 50.0 + self.zoom_climb * 0.5 + self.burst_mass_lbs_sec * 0.5

    def lethality_per_pass(self) -> float:
        if self.lethal_burst_sec <= 0:
            return 0
        return self.burst_mass_lbs_sec / self.lethal_burst_sec

    def ammo_endurance_passes(self) -> int:
        if self.lethal_burst_sec <= 0:
            return 0
        return max(1, int(self.ammo_seconds / max(0.5, self.lethal_burst_sec)))


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
    combat: CombatProfile = field(default_factory=CombatProfile)


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
