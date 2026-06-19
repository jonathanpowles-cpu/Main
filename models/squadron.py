from dataclasses import dataclass, field
from models.enums import Side, SquadronState, MissionType, TacticalDoctrine


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
    commanding_officer_id: str | None = None
    tactical_doctrine: TacticalDoctrine = TacticalDoctrine.VIC_THREE

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

    def average_experience(self, pilot_lookup: dict) -> float:
        available = [
            pilot_lookup[pid] for pid in self.pilot_ids
            if pid in pilot_lookup and pilot_lookup[pid].is_available()
        ]
        if not available:
            return 0.5
        return sum(p.experience for p in available) / len(available)

    def co_leadership_bonus(self, pilot_lookup: dict) -> float:
        if not self.commanding_officer_id:
            return 0.0
        co = pilot_lookup.get(self.commanding_officer_id)
        if not co or not co.is_available():
            return 0.0
        return co.traits.leadership * 0.15

    def doctrine_modifier(self) -> dict:
        """Returns combat modifiers based on tactical doctrine."""
        return DOCTRINE_MODIFIERS.get(self.tactical_doctrine, {})

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
            "commanding_officer_id": self.commanding_officer_id,
            "tactical_doctrine": self.tactical_doctrine.value,
        }
        if aircraft_lookup and pilot_lookup:
            result["operational_aircraft"] = self.operational_aircraft(aircraft_lookup)
            result["available_pilots"] = self.available_pilots(pilot_lookup)
            result["sortie_strength"] = self.sortie_strength(aircraft_lookup, pilot_lookup)
            result["can_scramble"] = self.can_scramble(aircraft_lookup, pilot_lookup)
            if self.commanding_officer_id and self.commanding_officer_id in pilot_lookup:
                co = pilot_lookup[self.commanding_officer_id]
                result["commanding_officer"] = co.rank_and_name()
        return result


DOCTRINE_MODIFIERS = {
    TacticalDoctrine.VIC_THREE: {
        "mutual_support": 0.3,
        "bounce_defense": 0.2,
        "flexibility": 0.3,
        "formation_cohesion": 0.7,
        "search_effectiveness": 0.4,
    },
    TacticalDoctrine.FINGER_FOUR: {
        "mutual_support": 0.7,
        "bounce_defense": 0.6,
        "flexibility": 0.7,
        "formation_cohesion": 0.6,
        "search_effectiveness": 0.7,
    },
    TacticalDoctrine.BIG_WING: {
        "mutual_support": 0.8,
        "bounce_defense": 0.5,
        "flexibility": 0.3,
        "formation_cohesion": 0.4,
        "search_effectiveness": 0.3,
        "mass_bonus": 0.4,
    },
    TacticalDoctrine.PAIR_ROTTE: {
        "mutual_support": 0.8,
        "bounce_defense": 0.7,
        "flexibility": 0.8,
        "formation_cohesion": 0.7,
        "search_effectiveness": 0.7,
    },
    TacticalDoctrine.SCHWARM: {
        "mutual_support": 0.9,
        "bounce_defense": 0.8,
        "flexibility": 0.8,
        "formation_cohesion": 0.8,
        "search_effectiveness": 0.8,
    },
    TacticalDoctrine.FREIE_JAGD: {
        "mutual_support": 0.5,
        "bounce_defense": 0.6,
        "flexibility": 0.9,
        "formation_cohesion": 0.3,
        "search_effectiveness": 0.9,
        "initiative_bonus": 0.3,
    },
    TacticalDoctrine.CLOSE_ESCORT: {
        "mutual_support": 0.9,
        "bounce_defense": 0.4,
        "flexibility": 0.2,
        "formation_cohesion": 0.8,
        "search_effectiveness": 0.3,
        "escort_effectiveness": 0.9,
    },
}
