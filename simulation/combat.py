import math
import random

from models.enums import (
    AircraftRole, AircraftStatus, PilotStatus, Side,
)
from models.game_state import GameState


def resolve_interception(game: GameState, interceptors: list[str], raid: dict) -> dict:
    """Resolve combat between intercepting fighters and a raid formation."""
    results = {
        "raf_losses": [], "raf_damaged": [],
        "lw_losses": [], "lw_damaged": [],
        "kills_by_pilot": {},
        "raid_disrupted": False,
        "bombs_jettisoned_pct": 0.0,
    }

    raid_fighter_ids = raid.get("escort_aircraft_ids", [])
    raid_bomber_ids = raid.get("bomber_aircraft_ids", [])
    all_raid_ids = raid_fighter_ids + raid_bomber_ids

    if not interceptors or not all_raid_ids:
        return results

    interceptor_aircraft = [game.aircraft[a] for a in interceptors if a in game.aircraft]
    escort_aircraft = [game.aircraft[a] for a in raid_fighter_ids if a in game.aircraft]
    bomber_aircraft = [game.aircraft[a] for a in raid_bomber_ids if a in game.aircraft]

    interceptor_aircraft = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
    escort_aircraft = [a for a in escort_aircraft if a.status == AircraftStatus.AIRBORNE]
    bomber_aircraft = [a for a in bomber_aircraft if a.status == AircraftStatus.AIRBORNE]

    num_rounds = random.randint(3, 8)

    for round_num in range(num_rounds):
        if not interceptor_aircraft:
            break

        if escort_aircraft:
            _resolve_fighter_combat(game, interceptor_aircraft, escort_aircraft, results)

        surviving_interceptors = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
        if surviving_interceptors and bomber_aircraft:
            _resolve_bomber_attack(game, surviving_interceptors, bomber_aircraft, results)

        interceptor_aircraft = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
        escort_aircraft = [a for a in escort_aircraft if a.status == AircraftStatus.AIRBORNE]
        bomber_aircraft = [a for a in bomber_aircraft if a.status == AircraftStatus.AIRBORNE]

    original_bombers = len(raid_bomber_ids)
    surviving_bombers = len(bomber_aircraft)
    if original_bombers > 0:
        loss_ratio = 1 - (surviving_bombers / original_bombers)
        if loss_ratio > 0.3:
            results["raid_disrupted"] = True
            results["bombs_jettisoned_pct"] = min(0.8, loss_ratio * 1.5)
        elif loss_ratio > 0.1:
            results["bombs_jettisoned_pct"] = loss_ratio * 0.5

    return results


def _resolve_fighter_combat(game, attackers, defenders, results):
    """Resolve one round of fighter vs fighter combat."""
    engagements = min(len(attackers), len(defenders))
    shuffled_attackers = random.sample(attackers, len(attackers))
    shuffled_defenders = random.sample(defenders, len(defenders))

    for i in range(engagements):
        attacker = shuffled_attackers[i]
        defender = shuffled_defenders[i]

        atk_type = game.aircraft_types.get(attacker.aircraft_type)
        def_type = game.aircraft_types.get(defender.aircraft_type)
        if not atk_type or not def_type:
            continue

        atk_pilot = _get_pilot_for_aircraft(game, attacker)
        def_pilot = _get_pilot_for_aircraft(game, defender)

        atk_skill = atk_pilot.effective_skill() if atk_pilot else 0.5
        def_skill = def_pilot.effective_skill() if def_pilot else 0.5

        atk_score = (
            atk_type.firepower * 0.3
            + atk_type.agility * 0.3
            + atk_skill * 4.0
            + random.gauss(0, 1.5)
        )
        def_score = (
            def_type.firepower * 0.3
            + def_type.agility * 0.3
            + def_skill * 4.0
            + random.gauss(0, 1.5)
        )

        ammo_factor = attacker.ammo_remaining * 0.3
        atk_score += ammo_factor

        diff = atk_score - def_score

        if diff > 3.0:
            _apply_damage(game, defender, def_pilot, severity=random.uniform(0.5, 1.0), results=results)
            if atk_pilot:
                atk_pilot.kills += 1
                results["kills_by_pilot"][atk_pilot.id] = results["kills_by_pilot"].get(atk_pilot.id, 0) + 1
                if atk_pilot.kills >= 5:
                    atk_pilot.is_ace = True
        elif diff > 1.5:
            _apply_damage(game, defender, def_pilot, severity=random.uniform(0.1, 0.5), results=results)
        elif diff < -3.0:
            _apply_damage(game, attacker, atk_pilot, severity=random.uniform(0.5, 1.0), results=results)
            if def_pilot:
                def_pilot.kills += 1
                results["kills_by_pilot"][def_pilot.id] = results["kills_by_pilot"].get(def_pilot.id, 0) + 1
                if def_pilot.kills >= 5:
                    def_pilot.is_ace = True
        elif diff < -1.5:
            _apply_damage(game, attacker, atk_pilot, severity=random.uniform(0.1, 0.5), results=results)

        attacker.ammo_remaining = max(0, attacker.ammo_remaining - random.uniform(0.05, 0.15))
        defender.ammo_remaining = max(0, defender.ammo_remaining - random.uniform(0.05, 0.15))


def _resolve_bomber_attack(game, fighters, bombers, results):
    """Resolve fighters attacking bombers."""
    attacks = min(len(fighters), len(bombers))
    shuffled_fighters = random.sample(fighters, len(fighters))
    shuffled_bombers = random.sample(bombers, len(bombers))

    for i in range(attacks):
        fighter = shuffled_fighters[i]
        bomber = shuffled_bombers[i]

        f_type = game.aircraft_types.get(fighter.aircraft_type)
        b_type = game.aircraft_types.get(bomber.aircraft_type)
        if not f_type or not b_type:
            continue

        f_pilot = _get_pilot_for_aircraft(game, fighter)
        f_skill = f_pilot.effective_skill() if f_pilot else 0.5

        attack_score = (
            f_type.firepower * 0.4
            + f_skill * 4.0
            + fighter.ammo_remaining * 2.0
            + random.gauss(0, 1.0)
        )

        defense_score = (
            b_type.firepower * 0.5
            + b_type.durability * 0.5
            + random.gauss(0, 1.0)
        )

        diff = attack_score - defense_score

        if diff > 2.0:
            severity = min(1.0, random.uniform(0.3, 0.8) * (diff / 5.0))
            b_pilot = _get_pilot_for_aircraft(game, bomber)
            _apply_damage(game, bomber, b_pilot, severity, results)
            if severity > 0.7 and f_pilot:
                f_pilot.kills += 1
                results["kills_by_pilot"][f_pilot.id] = results["kills_by_pilot"].get(f_pilot.id, 0) + 1
                if f_pilot.kills >= 5:
                    f_pilot.is_ace = True

        if random.random() < 0.08:
            severity = random.uniform(0.1, 0.4)
            _apply_damage(game, fighter, f_pilot, severity, results)

        fighter.ammo_remaining = max(0, fighter.ammo_remaining - random.uniform(0.1, 0.25))


def _apply_damage(game, aircraft, pilot, severity, results):
    """Apply damage to an aircraft and potentially its pilot."""
    ac_type = game.aircraft_types.get(aircraft.aircraft_type)
    durability = ac_type.durability if ac_type else 5
    effective_severity = severity * (10 - durability) / 10.0

    aircraft.damage += effective_severity
    side = "raf" if aircraft.squadron_id in {
        s.id for s in game.squadrons.values() if s.side == Side.RAF
    } else "lw"

    if aircraft.damage >= 1.0:
        aircraft.status = AircraftStatus.DESTROYED
        if side == "raf":
            results["raf_losses"].append(aircraft.id)
            game.raf_stats["fighters_lost"] += 1
        else:
            results["lw_losses"].append(aircraft.id)
            role = ac_type.role if ac_type else None
            if role in (AircraftRole.BOMBER, AircraftRole.DIVE_BOMBER):
                game.luftwaffe_stats["bombers_lost"] += 1
            else:
                game.luftwaffe_stats["fighters_lost"] += 1

        if pilot:
            over_england = side == "lw"
            bail_chance = 0.7 if severity < 0.9 else 0.4
            if random.random() < bail_chance:
                if over_england and side == "lw":
                    pilot.status = PilotStatus.CAPTURED
                    game.luftwaffe_stats["pilots_captured"] += 1
                elif random.random() < 0.3:
                    pilot.status = PilotStatus.WOUNDED
                    pilot.wounds_severity = random.uniform(0.2, 0.8)
                    pilot.recovery_hours = int(pilot.wounds_severity * 200)
                    if side == "raf":
                        game.raf_stats["pilots_wounded"] += 1
                else:
                    pilot.status = PilotStatus.AVAILABLE
            else:
                pilot.status = PilotStatus.KILLED
                if side == "raf":
                    game.raf_stats["pilots_killed"] += 1
                else:
                    game.luftwaffe_stats["pilots_killed"] += 1
    elif aircraft.damage >= 0.5:
        aircraft.status = AircraftStatus.DAMAGED
        aircraft.repair_hours_remaining = int(severity * 48)
        if side == "raf":
            results["raf_damaged"].append(aircraft.id)
            game.raf_stats["fighters_damaged"] += 1
        else:
            results["lw_damaged"].append(aircraft.id)
            if ac_type and ac_type.role in (AircraftRole.BOMBER, AircraftRole.DIVE_BOMBER):
                game.luftwaffe_stats["bombers_damaged"] += 1
            else:
                game.luftwaffe_stats["fighters_damaged"] += 1


def resolve_bombing(game: GameState, raid: dict, disruption_pct: float) -> dict:
    """Resolve bombing damage on a target."""
    target_id = raid.get("target_id", "")
    target_type = raid.get("target_type", "")
    bomber_ids = raid.get("bomber_aircraft_ids", [])

    surviving_bombers = [
        game.aircraft[bid] for bid in bomber_ids
        if bid in game.aircraft and game.aircraft[bid].status == AircraftStatus.AIRBORNE
    ]

    total_bomb_load = 0
    for bomber in surviving_bombers:
        b_type = game.aircraft_types.get(bomber.aircraft_type)
        if b_type:
            total_bomb_load += b_type.bomb_load_lbs

    effective_load = total_bomb_load * (1.0 - disruption_pct)
    weather_mod = game.visibility
    effective_load *= weather_mod

    results = {
        "target_id": target_id,
        "target_type": target_type,
        "bombs_tons": effective_load / 2000,
        "damage_inflicted": 0.0,
    }

    if target_type == "airfield" and target_id in game.airfields:
        airfield = game.airfields[target_id]
        severity = min(1.0, effective_load / 20000)
        airfield.receive_damage(severity)
        results["damage_inflicted"] = severity

        for sqn_id in airfield.squadron_ids:
            sqn = game.squadrons.get(sqn_id)
            if not sqn:
                continue
            for ac_id in sqn.aircraft_ids:
                ac = game.aircraft.get(ac_id)
                if ac and ac.status == AircraftStatus.READY:
                    if random.random() < severity * 0.15:
                        ac.status = AircraftStatus.DESTROYED
                        game.raf_stats["fighters_lost"] += 1
                    elif random.random() < severity * 0.2:
                        ac.status = AircraftStatus.DAMAGED
                        ac.repair_hours_remaining = random.randint(8, 48)
                        game.raf_stats["fighters_damaged"] += 1

    elif target_type == "radar_station" and target_id in game.radar_stations:
        station = game.radar_stations[target_id]
        severity = min(1.0, effective_load / 5000)
        station.receive_damage(severity)
        results["damage_inflicted"] = severity

    return results


def _get_pilot_for_aircraft(game, aircraft):
    """Find the pilot flying this aircraft."""
    sqn = game.squadrons.get(aircraft.squadron_id)
    if not sqn:
        return None
    ac_index = None
    for i, ac_id in enumerate(sqn.aircraft_ids):
        if ac_id == aircraft.id:
            ac_index = i
            break
    if ac_index is not None and ac_index < len(sqn.pilot_ids):
        return game.pilots.get(sqn.pilot_ids[ac_index])
    return None
