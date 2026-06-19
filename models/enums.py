from enum import Enum


class Side(Enum):
    RAF = "raf"
    LUFTWAFFE = "luftwaffe"


class AircraftRole(Enum):
    FIGHTER = "fighter"
    HEAVY_FIGHTER = "heavy_fighter"
    NIGHT_FIGHTER = "night_fighter"
    BOMBER = "bomber"
    DIVE_BOMBER = "dive_bomber"


class AircraftStatus(Enum):
    READY = "ready"
    AIRBORNE = "airborne"
    DAMAGED = "damaged"
    DESTROYED = "destroyed"
    REPAIRING = "repairing"


class PilotStatus(Enum):
    AVAILABLE = "available"
    FLYING = "flying"
    RESTING = "resting"
    WOUNDED = "wounded"
    KILLED = "killed"
    CAPTURED = "captured"
    HOSPITALIZED = "hospitalized"


class SquadronState(Enum):
    STANDBY = "standby"
    READY = "ready"
    AIRBORNE = "airborne"
    STOOD_DOWN = "stood_down"
    REARMING = "rearming"
    RELOCATING = "relocating"


class MissionType(Enum):
    PATROL = "patrol"
    INTERCEPT = "intercept"
    ESCORT = "escort"
    BOMBING = "bombing"
    DIVE_BOMBING = "dive_bombing"
    RECON = "recon"
    SWEEP = "sweep"
    FREE_HUNT = "free_hunt"


class TargetType(Enum):
    AIRFIELD = "airfield"
    RADAR_STATION = "radar_station"
    PORT = "port"
    FACTORY = "factory"
    CITY = "city"
    CONVOY = "convoy"
    SECTOR_STATION = "sector_station"


class WeatherCondition(Enum):
    CLEAR = "clear"
    FAIR = "fair"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    OVERCAST = "overcast"
    RAIN = "rain"
    FOG = "fog"
    STORM = "storm"


class TimeOfDay(Enum):
    DAWN = "dawn"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    DUSK = "dusk"
    NIGHT = "night"


class GamePhase(Enum):
    KANALKAMPF = "kanalkampf"
    ADLERANGRIFF = "adlerangriff"
    AIRFIELD_ATTACKS = "airfield_attacks"
    LONDON_BLITZ = "london_blitz"
