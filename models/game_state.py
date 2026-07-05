import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from models.enums import (
    Side, AircraftRole, AircraftStatus, PilotStatus, SquadronState, GamePhase,
    WeatherCondition, TimeOfDay, Rank, CommandRole, Medal, TacticalDoctrine,
)
from models.aircraft import Aircraft, AircraftType, CombatProfile
from models.pilot import Pilot, PilotTraits
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
        self.strategic_balance: float = 0.5  # 0=LW winning, 1=RAF winning
        self.game_over: bool = False
        self.winner: str = ""
        self.victory_reason: str = ""
        self.lw_bombs_total_tons: float = 0.0
        self.lw_bombs_effective_tons: float = 0.0

    def load_data(self):
        self._load_aircraft_types()
        self._load_airfields()
        self._load_radar_stations()
        self._load_historical_pilots()
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
                combat=self._load_combat_profile(info.get("combat", {})),
            )

    @staticmethod
    def _load_combat_profile(data: dict) -> CombatProfile:
        if not data:
            return CombatProfile()
        return CombatProfile(
            turn_rate=data.get("turn_rate", 5),
            roll_rate=data.get("roll_rate", 5),
            dive_speed_mph=data.get("dive_speed_mph", 400),
            zoom_climb=data.get("zoom_climb", 5),
            high_alt_modifier=data.get("high_alt_modifier", 0.7),
            low_alt_modifier=data.get("low_alt_modifier", 0.8),
            optimal_alt_ft=data.get("optimal_alt_ft", 18000),
            armament_type=data.get("armament_type", "mg_battery"),
            burst_mass_lbs_sec=data.get("burst_mass_lbs_sec", 1.0),
            ammo_seconds=data.get("ammo_seconds", 14),
            lethal_burst_sec=data.get("lethal_burst_sec", 2.0),
            convergence_range_yds=data.get("convergence_range_yds", 250),
            effective_range_yds=data.get("effective_range_yds", 300),
            fuel_injection=data.get("fuel_injection", False),
            cockpit_visibility=data.get("cockpit_visibility", 0.6),
            gun_platform_stability=data.get("gun_platform_stability", 0.8),
            structural_g_limit=data.get("structural_g_limit", 8.0),
            bounce_vulnerability=data.get("bounce_vulnerability", 0.3),
            formation_defense_bonus=data.get("formation_defense_bonus", 0.0),
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

    def _load_historical_pilots(self):
        hist_path = DATA_DIR / "historical_pilots.json"
        self._historical_pilot_data = {"raf": {}, "luftwaffe": {}}
        if not hist_path.exists():
            return
        with open(hist_path) as f:
            data = json.load(f)
        for side_key in ("raf", "luftwaffe"):
            side_data = data.get(side_key, {})
            for category in ("commanders", "squadron_leaders", "aces", "notable_pilots"):
                for entry in side_data.get(category, []):
                    unit = entry.get("unit", "")
                    if unit not in self._historical_pilot_data[side_key]:
                        self._historical_pilot_data[side_key][unit] = []
                    self._historical_pilot_data[side_key][unit].append(entry)

    def _create_historical_pilot(self, entry: dict, squadron_id: str, side: Side) -> Pilot:
        traits_data = entry.get("traits", {})
        traits = PilotTraits(
            aggression=traits_data.get("aggression", 0.5),
            situational_awareness=traits_data.get("situational_awareness", 0.5),
            gunnery=traits_data.get("gunnery", 0.5),
            leadership=traits_data.get("leadership", 0.5),
            tactical_sense=traits_data.get("tactical_sense", 0.5),
            coolness=traits_data.get("coolness", 0.5),
            stamina=traits_data.get("stamina", 0.5),
        )

        rank_str = entry.get("rank", "pilot_officer")
        try:
            rank = Rank(rank_str)
        except ValueError:
            rank = Rank.PILOT_OFFICER if side == Side.RAF else Rank.LEUTNANT

        role_str = entry.get("role", "pilot")
        try:
            command_role = CommandRole(role_str)
        except ValueError:
            command_role = CommandRole.PILOT

        kills = entry.get("kills_at_start", 0)

        pilot = Pilot(
            id=f"hist_{squadron_id}_{entry['name'].lower().replace(' ', '_')}",
            name=entry["name"],
            squadron_id=squadron_id,
            nationality=entry.get("nationality", "british"),
            experience=entry.get("experience", 0.7),
            side=side,
            rank=rank,
            command_role=command_role,
            traits=traits,
            historical=True,
            historical_notes=entry.get("historical_notes", ""),
            kills=kills,
            is_ace=kills >= 5,
        )
        return pilot

    def _generate_random_pilot(self, p_id: str, squadron_id: str, nationality: str,
                                exp_base: float, side: Side, is_co: bool = False) -> Pilot:
        name = _generate_pilot_name(nationality)
        exp = max(0.1, min(1.0, exp_base + random.gauss(0, 0.15)))
        if is_co:
            exp = min(1.0, exp_base + 0.2)

        trait_base = exp * 0.6 + 0.2
        traits = PilotTraits(
            aggression=max(0.1, min(1.0, trait_base + random.gauss(0, 0.15))),
            situational_awareness=max(0.1, min(1.0, trait_base + random.gauss(0, 0.15))),
            gunnery=max(0.1, min(1.0, trait_base + random.gauss(0, 0.15))),
            leadership=max(0.1, min(1.0, trait_base + random.gauss(0, 0.12))),
            tactical_sense=max(0.1, min(1.0, trait_base + random.gauss(0, 0.15))),
            coolness=max(0.1, min(1.0, trait_base + random.gauss(0, 0.15))),
            stamina=max(0.1, min(1.0, 0.5 + random.gauss(0, 0.15))),
        )

        if side == Side.RAF:
            if is_co:
                rank = Rank.SQUADRON_LEADER
                role = CommandRole.SQUADRON_CO
            elif exp > 0.7:
                rank = Rank.FLIGHT_LIEUTENANT
                role = CommandRole.FLIGHT_COMMANDER
            elif exp > 0.5:
                rank = Rank.FLYING_OFFICER
                role = CommandRole.PILOT
            else:
                rank = Rank.PILOT_OFFICER
                role = CommandRole.PILOT
        else:
            if is_co:
                rank = Rank.HAUPTMANN
                role = CommandRole.STAFFEL_KAPITAN
            elif exp > 0.7:
                rank = Rank.OBERLEUTNANT
                role = CommandRole.PILOT
            elif exp > 0.5:
                rank = Rank.LEUTNANT
                role = CommandRole.PILOT
            else:
                rank = Rank.FELDWEBEL
                role = CommandRole.PILOT

        return Pilot(
            id=p_id, name=name, squadron_id=squadron_id,
            nationality=nationality, experience=exp,
            side=side, rank=rank, command_role=role, traits=traits,
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

            historical_for_unit = self._historical_pilot_data.get("raf", {}).get(sqn_id, [])
            historical_placed = 0
            for entry in historical_for_unit:
                pilot = self._create_historical_pilot(entry, sqn_id, Side.RAF)
                self.pilots[pilot.id] = pilot
                sqn.pilot_ids.append(pilot.id)
                if pilot.command_role == CommandRole.SQUADRON_CO:
                    sqn.commanding_officer_id = pilot.id
                historical_placed += 1

            pilot_count = info.get("pilot_strength", 18)
            remaining = pilot_count - historical_placed
            for i in range(max(0, remaining)):
                p_id = f"{sqn_id}_pilot_{i}"
                nat = info.get("nationality", "british")
                is_co = (i == 0 and sqn.commanding_officer_id is None)
                pilot = self._generate_random_pilot(
                    p_id, sqn_id, nat, exp_base, Side.RAF, is_co=is_co,
                )
                if is_co:
                    sqn.commanding_officer_id = pilot.id
                self.pilots[p_id] = pilot
                sqn.pilot_ids.append(p_id)

            self.squadrons[sqn_id] = sqn
            if base_id in self.airfields:
                self.airfields[base_id].squadron_ids.append(sqn_id)

    def _load_luftwaffe_units(self):
        with open(DATA_DIR / "luftwaffe_units.json") as f:
            data = json.load(f)
        for unit_id, info in data.items():
            ac_type = self.aircraft_types.get(info["aircraft_type"])
            if ac_type and ac_type.role == AircraftRole.FIGHTER:
                doctrine = TacticalDoctrine.SCHWARM
            else:
                doctrine = TacticalDoctrine.CLOSE_ESCORT

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
                tactical_doctrine=doctrine,
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

            historical_for_unit = self._historical_pilot_data.get("luftwaffe", {}).get(unit_id, [])
            historical_placed = 0
            for entry in historical_for_unit:
                pilot = self._create_historical_pilot(entry, unit_id, Side.LUFTWAFFE)
                self.pilots[pilot.id] = pilot
                sqn.pilot_ids.append(pilot.id)
                if pilot.command_role in (CommandRole.GESCHWADER_KOMMODORE, CommandRole.GRUPPE_KOMMANDEUR):
                    sqn.commanding_officer_id = pilot.id
                historical_placed += 1

            crew_per_ac = self.aircraft_types.get(info["aircraft_type"])
            crew_size = crew_per_ac.crew if crew_per_ac else 1
            pilot_count = int(ac_count * 1.2 * crew_size)
            remaining = pilot_count - historical_placed
            for i in range(max(0, remaining)):
                p_id = f"{unit_id}_pilot_{i}"
                is_co = (i == 0 and sqn.commanding_officer_id is None)
                pilot = self._generate_random_pilot(
                    p_id, unit_id, "german", 0.7, Side.LUFTWAFFE, is_co=is_co,
                )
                if is_co:
                    sqn.commanding_officer_id = pilot.id
                self.pilots[p_id] = pilot
                sqn.pilot_ids.append(p_id)

            self.squadrons[unit_id] = sqn

    def to_save_dict(self) -> dict:
        return {
            "current_date": self.current_date.isoformat(),
            "turn_number": self.turn_number,
            "phase": self.phase.value,
            "player_side": self.player_side.value,
            "time_scale_hours": self.time_scale_hours,
            "weather": self.weather.value,
            "visibility": self.visibility,
            "aircraft": {k: v.to_dict() for k, v in self.aircraft.items()},
            "pilots": {k: v.to_dict() for k, v in self.pilots.items()},
            "squadrons": {k: v.to_save_dict() for k, v in self.squadrons.items()},
            "airfields": {k: v.to_dict() for k, v in self.airfields.items()},
            "radar_stations": {k: v.to_dict() for k, v in self.radar_stations.items()},
            "active_raids": self.active_raids,
            "event_log": self.event_log[-200:],
            "raf_stats": self.raf_stats,
            "luftwaffe_stats": self.luftwaffe_stats,
            "strategic_balance": self.strategic_balance,
            "game_over": self.game_over,
            "winner": self.winner,
            "victory_reason": self.victory_reason,
            "lw_bombs_total_tons": self.lw_bombs_total_tons,
            "lw_bombs_effective_tons": self.lw_bombs_effective_tons,
        }

    @classmethod
    def load_from_save(cls, data: dict) -> "GameState":
        gs = cls()
        gs._load_aircraft_types()

        gs.current_date = datetime.fromisoformat(data["current_date"])
        gs.turn_number = data["turn_number"]
        gs.phase = GamePhase(data["phase"])
        gs.player_side = Side(data["player_side"])
        gs.time_scale_hours = data["time_scale_hours"]
        gs.weather = WeatherCondition(data["weather"])
        gs.visibility = data["visibility"]
        gs.raf_stats = data["raf_stats"]
        gs.luftwaffe_stats = data["luftwaffe_stats"]
        gs.active_raids = data["active_raids"]
        gs.event_log = data["event_log"]
        gs.strategic_balance = data.get("strategic_balance", 0.5)
        gs.game_over = data.get("game_over", False)
        gs.winner = data.get("winner", "")
        gs.victory_reason = data.get("victory_reason", "")
        gs.lw_bombs_total_tons = data.get("lw_bombs_total_tons", 0.0)
        gs.lw_bombs_effective_tons = data.get("lw_bombs_effective_tons", 0.0)

        for ac_id, ac_data in data["aircraft"].items():
            gs.aircraft[ac_id] = Aircraft.from_dict(ac_data)
        for pid, p_data in data["pilots"].items():
            gs.pilots[pid] = Pilot.from_dict(p_data)
        for sqn_id, sqn_data in data["squadrons"].items():
            gs.squadrons[sqn_id] = Squadron.from_dict(sqn_data)
        for af_id, af_data in data["airfields"].items():
            gs.airfields[af_id] = Airfield.from_dict(af_data)
        for rs_id, rs_data in data["radar_stations"].items():
            gs.radar_stations[rs_id] = RadarStation.from_dict(rs_data)

        return gs

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
            "strategic_balance": round(self.strategic_balance, 3),
            "game_over": self.game_over,
            "winner": self.winner,
            "victory_reason": self.victory_reason,
        }
