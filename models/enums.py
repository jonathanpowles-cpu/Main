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


class Rank(Enum):
    # RAF ranks
    PILOT_OFFICER = "pilot_officer"
    FLYING_OFFICER = "flying_officer"
    FLIGHT_LIEUTENANT = "flight_lieutenant"
    SQUADRON_LEADER = "squadron_leader"
    WING_COMMANDER = "wing_commander"
    GROUP_CAPTAIN = "group_captain"
    AIR_COMMODORE = "air_commodore"
    AIR_VICE_MARSHAL = "air_vice_marshal"
    AIR_MARSHAL = "air_marshal"
    AIR_CHIEF_MARSHAL = "air_chief_marshal"
    # Luftwaffe ranks
    LEUTNANT = "leutnant"
    OBERLEUTNANT = "oberleutnant"
    HAUPTMANN = "hauptmann"
    MAJOR = "major"
    OBERSTLEUTNANT = "oberstleutnant"
    OBERST = "oberst"
    GENERALMAJOR = "generalmajor"
    GENERALLEUTNANT = "generalleutnant"
    GENERAL_DER_FLIEGER = "general_der_flieger"
    GENERALFELDMARSCHALL = "generalfeldmarschall"
    # Shared
    SERGEANT = "sergeant"
    FLIGHT_SERGEANT = "flight_sergeant"
    WARRANT_OFFICER = "warrant_officer"
    FELDWEBEL = "feldwebel"
    OBERFELDWEBEL = "oberfeldwebel"


class CommandRole(Enum):
    FIGHTER_COMMAND_AOC = "fighter_command_aoc"
    GROUP_COMMANDER = "group_commander"
    SECTOR_CONTROLLER = "sector_controller"
    WING_LEADER = "wing_leader"
    SQUADRON_CO = "squadron_co"
    FLIGHT_COMMANDER = "flight_commander"
    SECTION_LEADER = "section_leader"
    LUFTFLOTTE_COMMANDER = "luftflotte_commander"
    GESCHWADER_KOMMODORE = "geschwader_kommodore"
    GRUPPE_KOMMANDEUR = "gruppe_kommandeur"
    STAFFEL_KAPITAN = "staffel_kapitan"
    PILOT = "pilot"


class Medal(Enum):
    # RAF
    DFC = "distinguished_flying_cross"
    DSO = "distinguished_service_order"
    DFM = "distinguished_flying_medal"
    BAR_TO_DFC = "bar_to_dfc"
    VC = "victoria_cross"
    # Luftwaffe
    IRON_CROSS_2 = "iron_cross_2nd_class"
    IRON_CROSS_1 = "iron_cross_1st_class"
    RITTERKREUZ = "ritterkreuz"
    RITTERKREUZ_EICHENLAUB = "ritterkreuz_with_oak_leaves"
    RITTERKREUZ_SCHWERTERN = "ritterkreuz_with_swords"
    # Shared
    MENTIONED_IN_DESPATCHES = "mentioned_in_despatches"


class EngagementType(Enum):
    BOUNCE = "bounce"
    HEAD_ON = "head_on"
    TURNING_FIGHT = "turning_fight"
    BOOM_AND_ZOOM = "boom_and_zoom"
    DEFENSIVE = "defensive"
    STERN_CHASE = "stern_chase"


class TacticalDoctrine(Enum):
    VIC_THREE = "vic_three"
    FINGER_FOUR = "finger_four"
    BIG_WING = "big_wing"
    PAIR_ROTTE = "pair_rotte"
    SCHWARM = "schwarm"
    FREIE_JAGD = "freie_jagd"
    CLOSE_ESCORT = "close_escort"
