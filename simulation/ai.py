import math
import random

from models.enums import (
    Side, AircraftRole, AircraftStatus, GamePhase, MissionType, TargetType,
    WeatherCondition, SquadronState,
)
from models.game_state import GameState
from simulation.weather import is_flyable, FLYING_SUITABILITY

# Patrol sectors: name -> (centre_lat, centre_lon, radius_miles)
PATROL_SECTORS = {
    "thames_estuary":   (51.5,  0.7,  30),
    "kent":             (51.2,  0.9,  35),
    "channel":          (50.7,  0.0,  40),
    "sussex":           (50.9, -0.2,  35),
    "portland":         (50.6, -2.5,  30),
    "north_sea":        (52.0,  1.5,  40),
    "midlands":         (52.5, -1.5,  45),
    "northern":         (53.5, -1.0,  50),
}

# LW starting positions (approx lat/lon of bases in France/Belgium/Norway)
LW_START_POSITIONS = [
    (50.8, 2.3),   # Pas-de-Calais area
    (50.6, 1.8),   # Abbeville area
    (49.7, 0.5),   # Rouen area
    (49.4, -0.4),  # Caen area
    (50.4, 3.0),   # Belgium
    (49.0, 2.5),   # Paris region (long-range)
    (58.0, 8.0),   # Norway (Luftflotte 5)
]

RAID_SPEED_MILES_PER_HOUR = 220.0  # bomber speed over ground


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
        if raid.get("detected", False) and raid.get("phase") in ("en_route", "attacking"):
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


def move_raids(game: GameState) -> list[str]:
    """Advance raid positions toward their targets. Returns list of newly-attacked target names."""
    attacked = []
    hours = game.time_scale_hours
    distance_per_turn = RAID_SPEED_MILES_PER_HOUR * hours

    for raid in game.active_raids:
        if raid.get("resolved"):
            continue

        phase = raid.get("phase", "forming")
        target_lat = raid.get("target_lat")
        target_lon = raid.get("target_lon")

        if target_lat is None or target_lon is None:
            # Resolve immediately — legacy raid without position data
            raid["phase"] = "attacking"
            continue

        if phase == "forming":
            # First turn: move from base toward channel
            raid["phase"] = "en_route"
            # Move partway toward target
            raid["lat"], raid["lon"] = _interpolate_position(
                raid["lat"], raid["lon"], target_lat, target_lon, 0.4
            )
        elif phase == "en_route":
            dist_remaining = _approx_distance(raid["lat"], raid["lon"], target_lat, target_lon)
            if dist_remaining <= distance_per_turn or dist_remaining < 25:
                raid["lat"] = target_lat
                raid["lon"] = target_lon
                raid["phase"] = "attacking"
                attacked.append(raid["target_name"])
            else:
                frac = min(1.0, distance_per_turn / max(1, dist_remaining))
                raid["lat"], raid["lon"] = _interpolate_position(
                    raid["lat"], raid["lon"], target_lat, target_lon, frac
                )
        # "attacking" stays in place until resolved

    return attacked


def detect_raids(game: GameState) -> list[str]:
    """Use radar and observer corps to detect incoming raids.
    Returns list of raid IDs newly detected this turn."""
    newly_detected = []

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
                newly_detected.append(raid["id"])
                break

    return newly_detected


def check_patrol_intercepts(game: GameState):
    """Patrolling squadrons automatically intercept raids entering their sector."""
    from simulation.combat import resolve_interception

    for sqn in game.squadrons.values():
        if sqn.side != Side.RAF:
            continue
        if sqn.state != SquadronState.PATROLLING or not sqn.patrol_sector:
            continue

        sector = PATROL_SECTORS.get(sqn.patrol_sector)
        if not sector:
            continue
        sec_lat, sec_lon, sec_radius = sector

        for raid in game.active_raids:
            if raid.get("resolved") or raid.get("intercepted"):
                continue
            if raid.get("phase") not in ("en_route", "attacking"):
                continue

            raid_lat = raid.get("lat", 0)
            raid_lon = raid.get("lon", 0)
            dist = _approx_distance(sec_lat, sec_lon, raid_lat, raid_lon)

            if dist <= sec_radius:
                ac_ids = [
                    ac_id for ac_id in sqn.aircraft_ids
                    if game.aircraft.get(ac_id) and game.aircraft[ac_id].is_available()
                ]
                if not ac_ids:
                    continue

                results = resolve_interception(game, ac_ids, raid)
                raid["intercepted"] = True
                game.add_event(
                    "interception",
                    f"{sqn.name} (on patrol over {sqn.patrol_sector.replace('_', ' ')}) intercepts raid on {raid['target_name']}: "
                    f"{len(results['lw_losses'])} enemy destroyed, {len(results['raf_losses'])} fighters lost",
                    side="raf",
                    details={"raf_losses": len(results["raf_losses"]), "lw_losses": len(results["lw_losses"])},
                )


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

    # Pick a starting position on the French/Belgian/Norwegian coast
    start_lat, start_lon = random.choice(LW_START_POSITIONS)
    # If Luftflotte 5 target (northern England), bias to Norway start
    target_lat = target.get("lat", 51.5)
    if target_lat and target_lat > 53.0:
        start_lat, start_lon = 58.0 + random.uniform(-1, 1), 8.0 + random.uniform(-2, 2)

    raid = {
        "id": f"raid_{game.turn_number}_{random.randint(1000, 9999)}",
        "target_id": target["id"],
        "target_type": target["type"],
        "target_name": target["name"],
        "target_lat": target.get("lat", 51.5),
        "target_lon": target.get("lon", -0.5),
        "bomber_unit_ids": [u.id for u in selected_bombers],
        "escort_unit_ids": [u.id for u in selected_escorts],
        "bomber_aircraft_ids": bomber_ac_ids,
        "escort_aircraft_ids": escort_ac_ids,
        "altitude_ft": random.choice([12000, 15000, 18000, 20000, 25000]),
        "detected": False,
        "intercepted": False,
        "resolved": False,
        "phase": "forming",
        "lat": start_lat,
        "lon": start_lon,
    }

    return raid


def _select_target(game: GameState) -> dict | None:
    targets = []

    def _af_target(af_id, af, priority):
        return {"id": af_id, "type": "airfield", "name": af.name,
                "priority": priority, "lat": af.lat, "lon": af.lon}

    def _rs_target(rs_id, rs, priority):
        return {"id": rs_id, "type": "radar_station", "name": rs.name,
                "priority": priority, "lat": rs.lat, "lon": rs.lon}

    if game.phase == GamePhase.KANALKAMPF:
        targets.append({"id": "convoy", "type": "convoy", "name": "Channel Convoy",
                        "priority": 5, "lat": 50.8, "lon": 0.5})
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.airfield_type == "forward_base":
                targets.append(_af_target(af_id, af, 3))
        for rs_id, rs in game.radar_stations.items():
            if rs.operational:
                targets.append(_rs_target(rs_id, rs, 2))

    elif game.phase == GamePhase.ADLERANGRIFF:
        for rs_id, rs in game.radar_stations.items():
            if rs.operational:
                targets.append(_rs_target(rs_id, rs, 6))
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.group in ("11_group", "10_group"):
                p = 7 if af.airfield_type == "sector_station" else 4
                targets.append(_af_target(af_id, af, p))

    elif game.phase == GamePhase.AIRFIELD_ATTACKS:
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF:
                p = 8 if af.airfield_type == "sector_station" else 5
                if af.group == "11_group":
                    p += 2
                targets.append(_af_target(af_id, af, p))

    elif game.phase == GamePhase.LONDON_BLITZ:
        targets.append({"id": "london", "type": "city", "name": "London",
                        "priority": 8, "lat": 51.5, "lon": -0.12})
        targets.append({"id": "london_docks", "type": "port", "name": "London Docks",
                        "priority": 7, "lat": 51.5, "lon": 0.0})
        for af_id, af in game.airfields.items():
            if af.side == Side.RAF and af.group == "11_group":
                targets.append(_af_target(af_id, af, 3))

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


def _interpolate_position(lat1, lon1, lat2, lon2, fraction):
    return (
        lat1 + (lat2 - lat1) * fraction,
        lon1 + (lon2 - lon1) * fraction,
    )


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
