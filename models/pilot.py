from dataclasses import dataclass
from models.enums import PilotStatus


@dataclass
class Pilot:
    id: str
    name: str
    squadron_id: str
    nationality: str
    experience: float
    fatigue: float = 0.0
    morale: float = 1.0
    status: PilotStatus = PilotStatus.AVAILABLE
    kills: int = 0
    sorties: int = 0
    hours_since_rest: float = 0.0
    wounds_severity: float = 0.0
    recovery_hours: int = 0
    is_ace: bool = False

    def is_available(self) -> bool:
        return self.status == PilotStatus.AVAILABLE

    def effective_skill(self) -> float:
        fatigue_penalty = self.fatigue * 0.3
        morale_bonus = (self.morale - 0.5) * 0.2
        return max(0.1, min(1.0, self.experience - fatigue_penalty + morale_bonus))

    def add_fatigue(self, hours: float):
        self.hours_since_rest += hours
        self.fatigue = min(1.0, self.fatigue + hours * 0.05)

    def rest(self, hours: float):
        self.fatigue = max(0.0, self.fatigue - hours * 0.08)
        if hours >= 8:
            self.hours_since_rest = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "squadron_id": self.squadron_id,
            "nationality": self.nationality,
            "experience": round(self.experience, 2),
            "fatigue": round(self.fatigue, 2),
            "morale": round(self.morale, 2),
            "status": self.status.value,
            "kills": self.kills,
            "sorties": self.sorties,
            "is_ace": self.is_ace,
        }
