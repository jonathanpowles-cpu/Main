import math
import random

from models.enums import (
    Side, AircraftRole, AircraftStatus, GamePhase, MissionType, TargetType,
    WeatherCondition, SquadronState,
)
from models.game_state import GameState
from simulation.weather import is_flyable, FLYING_SUITABILITY


def generate_luftwaffe_raids(game: GameState) -> list[dict]:
    """Generate AI-controlled Luftwaffe raids based on current phase and conditions."""
    if not is_flyable(game.weather):
        return []

    tod = game.get_time_of_day()
    if tod.value in ("night", "dawn", "dusk"):
        return []

    flying_suitability = FLYING_SUITABILITY.get(game.weather, 0.5)
    raid_probability = flying_suitability * _phase_raid_intensity(game.phase)

    if random.random() > raid_probability:
        return []

    num_raids = _determine_raid_count(game)
    raids = []

    for _ in range(num_raids):
        raid = _plan_single_raid(game)
        if raid:
            raids.append(raid)

    return raids


def generate_raf_intercepts(game: GameState) -> list[dict]:
    """Generate AI-controlled RAF intercepts for detected raids."""
    intercepts = []

    for raid in game.active_raids:
        if raid.get("detected", False):
            available_squadrons = _find_available_interceptors(game, raid)
            if available_squadrons:
                num_to_scramble = min(len(available_squadrons), random.randint(1, 4))
                selected = random.sample(available_squadrons, num_to_scramble)
                intercept = {
                    "raid_id": raid["id"],
                    "squadron_ids": [s.id for s in selected],
                    "aircraft_ids": [],
                }
                for sqn in selected:
                    sqn.state = SquadronState.AIRBORNE
                    sqn.current_mission = MissionType.INTERCEPT
                    for ac_id in sqn.aircraft_ids:
                        ac = game.aircraft.get(ac_id)
                        if ac and ac.is_available():
                            ac.status = AircraftStatus.AIRBORNE
                            intercept["aircraft_ids"].append(ac_id)
                    game.raf_stats["sorties_flown"] += len(intercept["aircraft_ids"])
                intercepts.append(intercept)

    return intercepts


def _phase_raid_intensity(phase: GamePhase) -> float:
    return {
        GamePhase.KANALKAMPF: 0.4,
        GamePhase.ADLERANGRIFF: 0.7,
        GamePhase.AIRFIELD_ATTACKS: 0.8,
        GamePhase.LONDON_BLITZ: 0.6,
    }.get(phase, 0.5)


def _determine_raid_count(game: GameState) -> int:
    base = {
        GamePhase.KANALKAMPF: (1, 3),
        GamePhase.ADLERANGRIFF: (2, 6),
        GamePhase.AIRFIELD_ATTACKS: (3, 8),
        GamePhase.LONDON_BLITZ: (2, 5),
    }.get(game.phase, (1, 3))

    return random.randint(*base)


def _plan_single_raid(game: GameState) -> dict | None:
    target = _select_target(game)
    if not target:
        return None

    bomber_units = [
        s for s in game.squadrons.values()
        if s.side == Side.LUFTWAFFE
        and game.aircraft_types.get(s.aircraft_type, None)
        and game.aircraft_types[s.aircraft_type].role in (
            AircraftRole.BOMBER, AircraftRole.DIVE_BOMBER,
        )
        and s.state in (SquadronState.READY, SquadronState.STANDBY)
    ]

    if not bomber_units:
        return None

    selected_bombers = random.sample(bomber_units, min(len(bomber_units), random.randint(1, 3)))

    escort_units = [
        s for s in game.squadrons.values()
        if s.side == Side.LUFTWAFFE
        and game.aircraft_types.get(s.aircraft_type, None)
        and game.aircraft_types[s.aircraft_type].role == AircraftRole.FIGHTER
        and s.state in (SquadronState.READY, SquadronState.STANDBY)
    ]

    num_escorts = min(len(escort_units), max(1, len(selected_bombers)))
    selected_escorts = random.sample(escort_units, num_escorts) if escort_units else []

    max_bombers_per_unit = {
        GamePhase.KANALKAMPF: 20,
        GamePhase.ADLERANGRIFF: 40,
        GamePhase.AIRFIELD_ATTACKS: 50,
        GamePhase.LONDON_BLITZ: 60,
    }.get(game.phase, 30)

    max_escorts_per_unit = {
        GamePhase.KANALKAMPF: 15,
        GamePhase.ADLERANGRIFF: 30,
        GamePhase.AIRFIELD_ATTACKS: 35,
        GamePhase.LONDON_BLITZ: 40,
    }.get(game.phase, 25)

    bomber_ac_ids = []
    for unit in selected_bombers:
        unit.state = SquadronState.AIRBORNE
        unit.current_mission = MissionType.BOMBING
        unit.mission_target = target["id"]
        count = 0
        for ac_id in unit.aircraft_ids:
            if count >= max_bombers_per_unit:
                break
            ac = game.aircraft.get(ac_id)
            if ac and ac.is_available():
                ac.status = AircraftStatus.AIRBORNE
                bomber_ac_ids.append(ac_id)
                count += 1
        game.luftwaffe_stats["sorties_flown"] += count

    escort_ac_ids = []
    for unit in selected_escorts:
        unit.state = SquadronState.AIRBORNE
        unit.current_mission = MissionType.ESCORT
        count = 0
        for ac_id in unit.aircraft_ids:
            if count >= max_escorts_per_unit:
                break
            ac = game.aircraft.get(ac_id)
            if ac and ac.is_available():
                ac.status = AircraftStatus.AIRBORNE
                escort_ac_ids.append(ac_id)
                count += 1

    if not bomber_ac_ids:
        return None

    raid = {
        "id": f"raid_{game.turn_number}_{random.randint(1000, 9999)}",
        "target_id": target["id"],
        "target_type": target["type"],
        "target_name": target["name"],
        "bomber_unit_ids": [u.id for u in selected_bombers],
        "escort_unit_ids": [u.id for u in selected_escorts],
        "bomber_aircraft_ids": bomber_ac_ids,
        "escort_aircraft_ids": escort_ac_ids,
        "altitude_ft": random.choice([12000, 15000, 18000, 20000, 25000]),
        "detected": False,
        "intercepted": False,
        "resolved": False,
        "phase": "forming",
        "lat": 50.5 + random.uniform(-0.5, 0.5),
        "lon": 1.5 + random.uniform(-0.5, 0.5),
    }

    return raid


def _select_target(game: GameState) -> dict | None:
    targets = []

    if game.phase == GamePhase.KANALKAMPF:
        targets.append({"id": "convoy", "type": "convoy", "name": "Channel Convoy", "priority": 5})
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.airfield_type == "forward_base":
                targets.append({"id": af_id, "type": "airfield", "name": af.name, "priority": 3})
        for rs_id, rs in game.radar_stations.items():
            if rs.operational:
                targets.append({"id": rs_id, "type": "radar_station", "name": rs.name, "priority": 2})

    elif game.phase == GamePhase.ADLERANGRIFF:
        for rs_id, rs in game.radar_stations.items():
            if rs.operational:
                targets.append({"id": rs_id, "type": "radar_station", "name": rs.name, "priority": 6})
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.group in ("11_group", "10_group"):
                p = 7 if af.airfield_type == "sector_station" else 4
                targets.append({"id": af_id, "type": "airfield", "name": af.name, "priority": p})

    elif game.phase == GamePhase.AIRFIELD_ATTACKS:
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF:
                p = 8 if af.airfield_type == "sector_station" else 5
                if af.group == "11_group":
                    p += 2
                targets.append({"id": af_id, "type": "airfield", "name": af.name, "priority": p})

    elif game.phase == GamePhase.LONDON_BLITZ:
        targets.append({"id": "london", "type": "city", "name": "London", "priority": 8})
        targets.append({"id": "london_docks", "type": "port", "name": "London Docks", "priority": 7})
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.group == "11_group":
                targets.append({"id": af_id, "type": "airfield", "name": af.name, "priority": 3})

    if not targets:
        return None

    weights = [t["priority"] for t in targets]
    return random.choices(targets, weights=weights, k=1)[0]


def _find_available_interceptors(game: GameState, raid: dict) -> list:
    available = []
    for sqn in game.squadrons.values():
        if sqn.side != Side.RAF:
            continue
        ac_type = game.aircraft_types.get(sqn.aircraft_type)
        if not ac_type or ac_type.role not in (AircraftRole.FIGHTER, AircraftRole.NIGHT_FIGHTER):
            continue
        if not sqn.can_scramble(game.aircraft, game.pilots):
            continue
        if sqn.group in ("11_group", "10_group"):
            available.append(sqn)
        elif sqn.group == "12_group" and random.random() < 0.3:
            available.append(sqn)
    return available


def detect_raids(game: GameState):
    """Use radar and observer corps to detect incoming raids."""
    for raid in game.active_raids:
        if raid.get("detected"):
            continue

        raid_alt = raid.get("altitude_ft", 15000)
        raid_lat = raid.get("lat", 50.5)
        raid_lon = raid.get("lon", 1.5)

        for station in game.radar_stations.values():
            if not station.operational:
                continue
            distance = _approx_distance(station.lat, station.lon, raid_lat, raid_lon)
            if station.can_detect(raid_alt, distance):
                raid["detected"] = True
                raid["detected_by"] = station.id
                size_estimate = len(raid.get("bomber_aircraft_ids", []))
                noise = random.uniform(0.7, 1.5)
                raid["estimated_size"] = int(size_estimate * noise)
                game.add_event(
                    "radar_detection",
                    f"Radar at {station.name} detects raid of ~{raid['estimated_size']} aircraft heading for {raid['target_name']}",
                    side="raf",
                )
                break


def _approx_distance(lat1, lon1, lat2, lon2) -> float:
    """Approximate distance in miles between two lat/lon points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return c * 3959
