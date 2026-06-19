import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from models.enums import (
    Side, AircraftRole, AircraftStatus, PilotStatus, SquadronState, GamePhase,
    WeatherCondition, TimeOfDay,
)
from models.aircraft import Aircraft, AircraftType
from models.pilot import Pilot
from models.squadron import Squadron
from models.airfield import Airfield
from models.radar import RadarStation

DATA_DIR = Path(__file__).parent.parent / "data"

BRITISH_FIRST_NAMES = [
    "James", "John", "William", "George", "Robert", "Thomas", "Edward",
    "Richard", "Charles", "Henry", "Arthur", "Frederick", "Harold", "Albert",
    "Alfred", "Ernest", "Frank", "Herbert", "Walter", "Leonard", "Stanley",
    "Norman", "Ronald", "Douglas", "Kenneth", "Eric", "Donald", "Peter",
    "David", "Brian", "Derek", "Keith", "Alan", "Colin", "Geoffrey",
    "Gordon", "Ian", "Michael", "Patrick", "Nigel", "Philip", "Raymond",
    "Roger", "Roy", "Trevor", "Graham", "Terence", "Hugh", "Neville",
]

BRITISH_SURNAMES = [
    "Smith", "Jones", "Brown", "Wilson", "Taylor", "Johnson", "White",
    "Thompson", "Robinson", "Walker", "Hall", "Wright", "Clark", "Harris",
    "Lewis", "Young", "King", "Turner", "Hill", "Scott", "Green", "Baker",
    "Adams", "Nelson", "Mitchell", "Roberts", "Campbell", "Phillips", "Evans",
    "Parker", "Collins", "Stewart", "Morris", "Murphy", "Cook", "Morgan",
    "Bell", "Cooper", "Richardson", "Cox", "Ward", "Watson", "Brooks",
    "Spencer", "Grant", "Douglas", "Hamilton", "Blair", "Crawford", "Murray",
]

POLISH_NAMES = [
    "Witold Urbanowicz", "Jan Zumbach", "Miroslaw Feric", "Zdzislaw Henneberg",
    "Witold Lokucijewski", "Ludwik Paszkiewicz", "Bogdan Grzeszczak",
    "Wojciech Januszewicz", "Stefan Witorzenć", "Walerian Żak",
]

CZECH_NAMES = [
    "Josef František", "Alois Vašátko", "František Peřina", "Josef Stehlík",
    "Otakar Korec", "Miroslav Jiroudek", "Bohuslav Kimlička",
]

GERMAN_FIRST_NAMES = [
    "Hans", "Karl", "Wilhelm", "Heinrich", "Werner", "Friedrich", "Otto",
    "Walter", "Erich", "Kurt", "Heinz", "Helmut", "Gerhard", "Herbert",
    "Günther", "Rudolf", "Siegfried", "Wolfgang", "Horst", "Manfred",
    "Klaus", "Dieter", "Rolf", "Ernst", "Franz", "Josef", "Max",
    "Erwin", "Joachim", "Bernhard",
]

GERMAN_SURNAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Koch", "Richter", "Klein", "Wolf",
    "Schröder", "Neumann", "Braun", "Zimmermann", "Krüger", "Hartmann",
    "Lange", "Werner", "Krause", "Lehmann", "König", "Huber", "Kaiser",
    "Fuchs", "Scholz", "Möller",
]


def _generate_pilot_name(nationality: str) -> str:
    if nationality == "polish":
        return random.choice(POLISH_NAMES).split()[-1] + ", " + random.choice(BRITISH_FIRST_NAMES)
    elif nationality == "czech":
        return random.choice(CZECH_NAMES).split()[-1] + ", " + random.choice(BRITISH_FIRST_NAMES)
    elif nationality == "german":
        return f"{random.choice(GERMAN_SURNAMES)}, {random.choice(GERMAN_FIRST_NAMES)}"
    else:
        return f"{random.choice(BRITISH_SURNAMES)}, {random.choice(BRITISH_FIRST_NAMES)}"


class GameState:
    def __init__(self):
        self.current_date: datetime = datetime(1940, 7, 10, 6, 0)
        self.turn_number: int = 0
        self.phase: GamePhase = GamePhase.KANALKAMPF
        self.player_side: Side = Side.RAF
        self.time_scale_hours: float = 1.0

        self.aircraft_types: dict[str, AircraftType] = {}
        self.aircraft: dict[str, Aircraft] = {}
        self.pilots: dict[str, Pilot] = {}
        self.squadrons: dict[str, Squadron] = {}
        self.airfields: dict[str, Airfield] = {}
        self.radar_stations: dict[str, RadarStation] = {}

        self.active_raids: list[dict] = []
        self.event_log: list[dict] = []

        self.raf_stats = {
            "fighters_lost": 0, "fighters_damaged": 0,
            "pilots_killed": 0, "pilots_wounded": 0,
            "bombers_destroyed": 0, "fighters_produced": 0,
            "sorties_flown": 0,
        }
        self.luftwaffe_stats = {
            "fighters_lost": 0, "bombers_lost": 0,
            "fighters_damaged": 0, "bombers_damaged": 0,
            "pilots_killed": 0, "pilots_captured": 0,
            "bombs_dropped_tons": 0, "sorties_flown": 0,
        }

        self.weather: WeatherCondition = WeatherCondition.FAIR
        self.visibility: float = 1.0

    def load_data(self):
        self._load_aircraft_types()
        self._load_airfields()
        self._load_radar_stations()
        self._load_raf_squadrons()
        self._load_luftwaffe_units()

    def _load_aircraft_types(self):
        with open(DATA_DIR / "aircraft_types.json") as f:
            data = json.load(f)
        for type_id, info in data.items():
            self.aircraft_types[type_id] = AircraftType(
                id=type_id,
                name=info["name"],
                side=Side(info["side"]),
                role=AircraftRole(info["role"]),
                speed_mph=info["speed_mph"],
                climb_rate_fpm=info["climb_rate_fpm"],
                service_ceiling_ft=info["service_ceiling_ft"],
                range_miles=info["range_miles"],
                armament=info["armament"],
                firepower=info["firepower"],
                agility=info["agility"],
                durability=info["durability"],
                fuel_capacity_gallons=info["fuel_capacity_gallons"],
                fuel_burn_per_hour=info["fuel_burn_per_hour"],
                crew=info["crew"],
                production_per_week=info["production_per_week"],
                bomb_load_lbs=info.get("bomb_load_lbs", 0),
                dive_bombing_accuracy=info.get("dive_bombing_accuracy", 0),
            )

    def _load_airfields(self):
        with open(DATA_DIR / "airfields.json") as f:
            data = json.load(f)
        for af_id, info in data.items():
            self.airfields[af_id] = Airfield(
                id=af_id,
                name=info["name"],
                side=Side(info["side"]),
                lat=info["lat"],
                lon=info["lon"],
                airfield_type=info["type"],
                group=info["group"],
                hangars=info.get("hangars", 3),
                dispersal_pens=info.get("dispersal_pens", 12),
                fuel_storage_tons=info.get("fuel_storage_tons", 100),
                fuel_current_tons=info.get("fuel_storage_tons", 100),
                ammo_storage_tons=info.get("ammo_storage_tons", 50),
                ammo_current_tons=info.get("ammo_storage_tons", 50),
                aa_guns=info.get("aa_guns", 4),
            )

    def _load_radar_stations(self):
        with open(DATA_DIR / "radar_stations.json") as f:
            data = json.load(f)
        for rs_id, info in data.items():
            self.radar_stations[rs_id] = RadarStation(
                id=rs_id,
                name=info["name"],
                lat=info["lat"],
                lon=info["lon"],
                station_type=info["type"],
                range_miles=info["range_miles"],
                min_altitude_ft=info["min_altitude_ft"],
            )

    def _load_raf_squadrons(self):
        with open(DATA_DIR / "raf_squadrons.json") as f:
            data = json.load(f)
        for sqn_id, info in data.items():
            base_id = info["home_base"]
            sqn = Squadron(
                id=sqn_id,
                number=info["number"],
                name=info["name"],
                side=Side.RAF,
                aircraft_type=info["aircraft_type"],
                group=info["group"],
                home_base=base_id,
                current_base=base_id,
                experience_level=info.get("experience", "average"),
                nationality=info.get("nationality", "british"),
                morale=0.8,
            )
            exp_map = {"veteran": 0.9, "experienced": 0.7, "average": 0.5, "green": 0.3}
            exp_base = exp_map.get(sqn.experience_level, 0.5)

            ac_count = info.get("aircraft_strength", 16)
            for i in range(ac_count):
                ac_id = f"{sqn_id}_ac_{i}"
                ac = Aircraft(id=ac_id, aircraft_type=info["aircraft_type"], squadron_id=sqn_id)
                if i >= 12:
                    ac.status = AircraftStatus.REPAIRING
                    ac.repair_hours_remaining = random.randint(4, 24)
                self.aircraft[ac_id] = ac
                sqn.aircraft_ids.append(ac_id)

            pilot_count = info.get("pilot_strength", 18)
            for i in range(pilot_count):
                p_id = f"{sqn_id}_pilot_{i}"
                nat = info.get("nationality", "british")
                name = _generate_pilot_name(nat)
                exp = max(0.1, min(1.0, exp_base + random.gauss(0, 0.15)))
                pilot = Pilot(
                    id=p_id, name=name, squadron_id=sqn_id,
                    nationality=nat, experience=exp,
                )
                if i == 0:
                    pilot.experience = min(1.0, exp_base + 0.2)
                self.pilots[p_id] = pilot
                sqn.pilot_ids.append(p_id)

            self.squadrons[sqn_id] = sqn
            if base_id in self.airfields:
                self.airfields[base_id].squadron_ids.append(sqn_id)

    def _load_luftwaffe_units(self):
        with open(DATA_DIR / "luftwaffe_units.json") as f:
            data = json.load(f)
        for unit_id, info in data.items():
            sqn = Squadron(
                id=unit_id,
                number=0,
                name=info["name"],
                side=Side.LUFTWAFFE,
                aircraft_type=info["aircraft_type"],
                group=info["luftflotte"],
                home_base=info.get("base_region", "france"),
                current_base=info.get("base_region", "france"),
                experience_level="experienced",
                nationality="german",
                morale=0.85,
            )

            ac_count = info.get("aircraft_strength", 90)
            serviceability = info.get("serviceability_rate", 0.75)
            for i in range(ac_count):
                ac_id = f"{unit_id}_ac_{i}"
                ac = Aircraft(id=ac_id, aircraft_type=info["aircraft_type"], squadron_id=unit_id)
                if random.random() > serviceability:
                    ac.status = AircraftStatus.REPAIRING
                    ac.repair_hours_remaining = random.randint(4, 48)
                self.aircraft[ac_id] = ac
                sqn.aircraft_ids.append(ac_id)

            crew_per_ac = self.aircraft_types.get(info["aircraft_type"])
            crew_size = crew_per_ac.crew if crew_per_ac else 1
            pilot_count = int(ac_count * 1.2 * crew_size)
            for i in range(pilot_count):
                p_id = f"{unit_id}_pilot_{i}"
                name = _generate_pilot_name("german")
                exp = max(0.1, min(1.0, 0.7 + random.gauss(0, 0.15)))
                pilot = Pilot(
                    id=p_id, name=name, squadron_id=unit_id,
                    nationality="german", experience=exp,
                )
                self.pilots[p_id] = pilot
                sqn.pilot_ids.append(p_id)

            self.squadrons[unit_id] = sqn

    def get_time_of_day(self) -> TimeOfDay:
        hour = self.current_date.hour
        if hour < 5:
            return TimeOfDay.NIGHT
        elif hour < 7:
            return TimeOfDay.DAWN
        elif hour < 11:
            return TimeOfDay.MORNING
        elif hour < 14:
            return TimeOfDay.MIDDAY
        elif hour < 17:
            return TimeOfDay.AFTERNOON
        elif hour < 20:
            return TimeOfDay.EVENING
        elif hour < 22:
            return TimeOfDay.DUSK
        return TimeOfDay.NIGHT

    def add_event(self, event_type: str, message: str, side: str = "", details: dict = None):
        self.event_log.append({
            "turn": self.turn_number,
            "time": self.current_date.strftime("%Y-%m-%d %H:%M"),
            "type": event_type,
            "message": message,
            "side": side,
            "details": details or {},
        })

    def get_side_squadrons(self, side: Side) -> list[Squadron]:
        return [s for s in self.squadrons.values() if s.side == side]

    def get_group_squadrons(self, group: str) -> list[Squadron]:
        return [s for s in self.squadrons.values() if s.group == group]

    def summary(self) -> dict:
        raf_sqns = self.get_side_squadrons(Side.RAF)
        lw_sqns = self.get_side_squadrons(Side.LUFTWAFFE)

        raf_ac_ready = sum(
            1 for a in self.aircraft.values()
            if a.squadron_id in {s.id for s in raf_sqns} and a.is_available()
        )
        raf_ac_total = sum(len(s.aircraft_ids) for s in raf_sqns)
        lw_ac_ready = sum(
            1 for a in self.aircraft.values()
            if a.squadron_id in {s.id for s in lw_sqns} and a.is_available()
        )
        lw_ac_total = sum(len(s.aircraft_ids) for s in lw_sqns)

        raf_pilots_avail = sum(
            1 for p in self.pilots.values()
            if p.squadron_id in {s.id for s in raf_sqns} and p.is_available()
        )
        lw_pilots_avail = sum(
            1 for p in self.pilots.values()
            if p.squadron_id in {s.id for s in lw_sqns} and p.is_available()
        )

        radar_operational = sum(1 for r in self.radar_stations.values() if r.operational)
        airfields_operational = sum(
            1 for a in self.airfields.values()
            if a.side == Side.RAF and a.is_operational()
        )

        return {
            "date": self.current_date.strftime("%d %B %Y"),
            "time": self.current_date.strftime("%H:%M"),
            "turn": self.turn_number,
            "phase": self.phase.value,
            "time_of_day": self.get_time_of_day().value,
            "weather": self.weather.value,
            "player_side": self.player_side.value,
            "raf": {
                "squadrons": len(raf_sqns),
                "aircraft_ready": raf_ac_ready,
                "aircraft_total": raf_ac_total,
                "pilots_available": raf_pilots_avail,
                "radar_stations": radar_operational,
                "airfields_operational": airfields_operational,
                "stats": self.raf_stats,
            },
            "luftwaffe": {
                "squadrons": len(lw_sqns),
                "aircraft_ready": lw_ac_ready,
                "aircraft_total": lw_ac_total,
                "pilots_available": lw_pilots_avail,
                "stats": self.luftwaffe_stats,
            },
            "active_raids": len(self.active_raids),
        }
