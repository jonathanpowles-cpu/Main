from dataclasses import dataclass, field
from models.enums import PilotStatus, Rank, CommandRole, Medal, Side


MEDAL_THRESHOLDS_RAF = [
    (5, Medal.DFC, "Distinguished Flying Cross"),
    (10, Medal.BAR_TO_DFC, "Bar to DFC"),
    (15, Medal.DSO, "Distinguished Service Order"),
]

MEDAL_THRESHOLDS_LW = [
    (1, Medal.IRON_CROSS_2, "Iron Cross 2nd Class"),
    (5, Medal.IRON_CROSS_1, "Iron Cross 1st Class"),
    (20, Medal.RITTERKREUZ, "Knight's Cross"),
    (40, Medal.RITTERKREUZ_EICHENLAUB, "Knight's Cross with Oak Leaves"),
]

PROMOTION_THRESHOLDS_RAF = [
    (3, Rank.FLYING_OFFICER),
    (8, Rank.FLIGHT_LIEUTENANT),
    (15, Rank.SQUADRON_LEADER),
]

PROMOTION_THRESHOLDS_LW = [
    (3, Rank.OBERLEUTNANT),
    (10, Rank.HAUPTMANN),
    (20, Rank.MAJOR),
]


@dataclass
class PilotTraits:
    aggression: float = 0.5
    situational_awareness: float = 0.5
    gunnery: float = 0.5
    leadership: float = 0.5
    tactical_sense: float = 0.5
    coolness: float = 0.5
    stamina: float = 0.5

    def to_dict(self) -> dict:
        return {
            "aggression": round(self.aggression, 2),
            "situational_awareness": round(self.situational_awareness, 2),
            "gunnery": round(self.gunnery, 2),
            "leadership": round(self.leadership, 2),
            "tactical_sense": round(self.tactical_sense, 2),
            "coolness": round(self.coolness, 2),
            "stamina": round(self.stamina, 2),
        }


@dataclass
class Pilot:
    id: str
    name: str
    squadron_id: str
    nationality: str
    experience: float
    side: Side = Side.RAF
    rank: Rank = Rank.PILOT_OFFICER
    command_role: CommandRole = CommandRole.PILOT
    medals: list = field(default_factory=list)
    traits: PilotTraits = field(default_factory=PilotTraits)
    historical: bool = False
    historical_notes: str = ""
    fatigue: float = 0.0
    morale: float = 1.0
    status: PilotStatus = PilotStatus.AVAILABLE
    kills: int = 0
    sorties: int = 0
    hours_since_rest: float = 0.0
    wounds_severity: float = 0.0
    recovery_hours: int = 0
    is_ace: bool = False
    missions_log: list = field(default_factory=list)

    def is_available(self) -> bool:
        return self.status == PilotStatus.AVAILABLE

    def effective_skill(self) -> float:
        fatigue_penalty = self.fatigue * 0.3
        morale_bonus = (self.morale - 0.5) * 0.2
        return max(0.1, min(1.0, self.experience - fatigue_penalty + morale_bonus))

    def combat_gunnery(self) -> float:
        base = self.traits.gunnery * 0.6 + self.experience * 0.4
        fatigue_mod = 1.0 - self.fatigue * 0.2
        return max(0.1, min(1.0, base * fatigue_mod))

    def combat_awareness(self) -> float:
        base = self.traits.situational_awareness * 0.5 + self.experience * 0.3 + self.traits.coolness * 0.2
        fatigue_mod = 1.0 - self.fatigue * 0.25
        return max(0.1, min(1.0, base * fatigue_mod))

    def combat_energy_mgmt(self) -> float:
        return self.traits.tactical_sense * 0.6 + self.experience * 0.4

    def combat_aggression(self) -> float:
        base = self.traits.aggression
        if self.fatigue > 0.7:
            base *= 0.6
        if self.morale < 0.3:
            base *= 0.5
        return max(0.1, min(1.0, base))

    def add_fatigue(self, hours: float):
        self.hours_since_rest += hours
        stamina_mod = 1.0 - self.traits.stamina * 0.3
        self.fatigue = min(1.0, self.fatigue + hours * 0.05 * stamina_mod)

    def rest(self, hours: float):
        self.fatigue = max(0.0, self.fatigue - hours * 0.08)
        if hours >= 8:
            self.hours_since_rest = 0

    def log_mission(self, mission_type: str, date_str: str, kills: int = 0, result: str = ""):
        entry = {
            "date": date_str,
            "type": mission_type,
            "kills": kills,
            "result": result,
            "sortie_num": self.sorties,
        }
        self.missions_log.append(entry)
        if len(self.missions_log) > 50:
            self.missions_log = self.missions_log[-50:]

    def check_promotions_and_medals(self) -> list[str]:
        """Check if pilot has earned new medals or promotions. Returns event messages."""
        events = []

        if self.side == Side.RAF:
            thresholds = MEDAL_THRESHOLDS_RAF
            promo_thresholds = PROMOTION_THRESHOLDS_RAF
        else:
            thresholds = MEDAL_THRESHOLDS_LW
            promo_thresholds = PROMOTION_THRESHOLDS_LW

        for kill_req, medal, medal_name in thresholds:
            if self.kills >= kill_req and medal not in self.medals:
                self.medals.append(medal)
                events.append(f"{self.rank_and_name()} awarded {medal_name} ({self.kills} kills)")

        for kill_req, new_rank in promo_thresholds:
            if self.kills >= kill_req and self.command_role == CommandRole.PILOT:
                current_rank_order = self._rank_order()
                new_rank_order = self._rank_order_for(new_rank)
                if new_rank_order > current_rank_order:
                    old_rank = self.rank
                    self.rank = new_rank
                    events.append(f"{self.name} promoted from {old_rank.value} to {new_rank.value}")

        if self.kills >= 5 and not self.is_ace:
            self.is_ace = True
            events.append(f"{self.rank_and_name()} becomes an ace with {self.kills} kills!")

        return events

    def rank_and_name(self) -> str:
        rank_display = self.rank.value.replace("_", " ").title()
        return f"{rank_display} {self.name}"

    def _rank_order(self) -> int:
        return self._rank_order_for(self.rank)

    @staticmethod
    def _rank_order_for(rank: Rank) -> int:
        order = {
            Rank.SERGEANT: 1, Rank.FLIGHT_SERGEANT: 2, Rank.WARRANT_OFFICER: 3,
            Rank.FELDWEBEL: 1, Rank.OBERFELDWEBEL: 2,
            Rank.PILOT_OFFICER: 4, Rank.LEUTNANT: 4,
            Rank.FLYING_OFFICER: 5, Rank.OBERLEUTNANT: 5,
            Rank.FLIGHT_LIEUTENANT: 6, Rank.HAUPTMANN: 6,
            Rank.SQUADRON_LEADER: 7, Rank.MAJOR: 7,
            Rank.WING_COMMANDER: 8, Rank.OBERSTLEUTNANT: 8,
            Rank.GROUP_CAPTAIN: 9, Rank.OBERST: 9,
            Rank.AIR_COMMODORE: 10, Rank.GENERALMAJOR: 10,
            Rank.AIR_VICE_MARSHAL: 11, Rank.GENERALLEUTNANT: 11,
            Rank.AIR_MARSHAL: 12, Rank.GENERAL_DER_FLIEGER: 12,
            Rank.AIR_CHIEF_MARSHAL: 13, Rank.GENERALFELDMARSCHALL: 13,
        }
        return order.get(rank, 4)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "squadron_id": self.squadron_id,
            "side": self.side.value,
            "nationality": self.nationality,
            "rank": self.rank.value,
            "command_role": self.command_role.value,
            "experience": round(self.experience, 2),
            "fatigue": round(self.fatigue, 2),
            "morale": round(self.morale, 2),
            "status": self.status.value,
            "kills": self.kills,
            "sorties": self.sorties,
            "is_ace": self.is_ace,
            "historical": self.historical,
            "historical_notes": self.historical_notes,
            "medals": [m.value for m in self.medals],
            "traits": self.traits.to_dict(),
            "missions_log": self.missions_log[-10:],
        }
