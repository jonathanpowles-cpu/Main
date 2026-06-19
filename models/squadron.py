from dataclasses import dataclass, field
from models.enums import Side, SquadronState, MissionType


@dataclass
class Squadron:
    id: str
    number: int
    name: str
    side: Side
    aircraft_type: str
    group: str
    home_base: str
    current_base: str
    aircraft_ids: list = field(default_factory=list)
    pilot_ids: list = field(default_factory=list)
    state: SquadronState = SquadronState.READY
    experience_level: str = "average"
    nationality: str = "british"
    morale: float = 0.8
    current_mission: MissionType | None = None
    mission_target: str | None = None
    rearm_hours_remaining: float = 0.0

    def operational_aircraft(self, aircraft_lookup: dict) -> int:
        return sum(
            1 for aid in self.aircraft_ids
            if aid in aircraft_lookup and aircraft_lookup[aid].is_available()
        )

    def available_pilots(self, pilot_lookup: dict) -> int:
        return sum(
            1 for pid in self.pilot_ids
            if pid in pilot_lookup and pilot_lookup[pid].is_available()
        )

    def sortie_strength(self, aircraft_lookup: dict, pilot_lookup: dict) -> int:
        return min(
            self.operational_aircraft(aircraft_lookup),
            self.available_pilots(pilot_lookup),
        )

    def can_scramble(self, aircraft_lookup: dict, pilot_lookup: dict) -> bool:
        return (
            self.state in (SquadronState.READY, SquadronState.STANDBY)
            and self.sortie_strength(aircraft_lookup, pilot_lookup) >= 3
        )

    def to_dict(self, aircraft_lookup: dict = None, pilot_lookup: dict = None) -> dict:
        result = {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "side": self.side.value,
            "aircraft_type": self.aircraft_type,
            "group": self.group,
            "home_base": self.home_base,
            "current_base": self.current_base,
            "state": self.state.value,
            "experience_level": self.experience_level,
            "nationality": self.nationality,
            "morale": round(self.morale, 2),
            "aircraft_count": len(self.aircraft_ids),
            "pilot_count": len(self.pilot_ids),
        }
        if aircraft_lookup and pilot_lookup:
            result["operational_aircraft"] = self.operational_aircraft(aircraft_lookup)
            result["available_pilots"] = self.available_pilots(pilot_lookup)
            result["sortie_strength"] = self.sortie_strength(aircraft_lookup, pilot_lookup)
            result["can_scramble"] = self.can_scramble(aircraft_lookup, pilot_lookup)
        return result
