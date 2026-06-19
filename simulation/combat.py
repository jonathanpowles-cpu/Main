import math
import random

from models.enums import (
    AircraftRole, AircraftStatus, PilotStatus, Side, EngagementType,
    TacticalDoctrine,
)
from models.game_state import GameState
from models.squadron import DOCTRINE_MODIFIERS


def resolve_interception(game: GameState, interceptors: list[str], raid: dict) -> dict:
    results = {
        "raf_losses": [], "raf_damaged": [],
        "lw_losses": [], "lw_damaged": [],
        "kills_by_pilot": {},
        "raid_disrupted": False,
        "bombs_jettisoned_pct": 0.0,
        "engagement_type": "",
        "combat_narrative": [],
    }

    raid_fighter_ids = raid.get("escort_aircraft_ids", [])
    raid_bomber_ids = raid.get("bomber_aircraft_ids", [])

    if not interceptors and not raid_fighter_ids and not raid_bomber_ids:
        return results

    interceptor_aircraft = [game.aircraft[a] for a in interceptors if a in game.aircraft]
    escort_aircraft = [game.aircraft[a] for a in raid_fighter_ids if a in game.aircraft]
    bomber_aircraft = [game.aircraft[a] for a in raid_bomber_ids if a in game.aircraft]

    interceptor_aircraft = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
    escort_aircraft = [a for a in escort_aircraft if a.status == AircraftStatus.AIRBORNE]
    bomber_aircraft = [a for a in bomber_aircraft if a.status == AircraftStatus.AIRBORNE]

    engagement = _determine_engagement_type(game, interceptor_aircraft, raid)
    results["engagement_type"] = engagement.value

    raid_altitude = raid.get("altitude_ft", 15000)

    num_rounds = random.randint(3, 8)
    for round_num in range(num_rounds):
        if not interceptor_aircraft:
            break

        if escort_aircraft:
            _resolve_fighter_combat(
                game, interceptor_aircraft, escort_aircraft, results,
                engagement, raid_altitude, round_num,
            )

        surviving_interceptors = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
        if surviving_interceptors and bomber_aircraft:
            _resolve_bomber_attack(
                game, surviving_interceptors, bomber_aircraft, results,
                raid_altitude,
            )

        interceptor_aircraft = [a for a in interceptor_aircraft if a.status == AircraftStatus.AIRBORNE]
        escort_aircraft = [a for a in escort_aircraft if a.status == AircraftStatus.AIRBORNE]
        bomber_aircraft = [a for a in bomber_aircraft if a.status == AircraftStatus.AIRBORNE]

        if _check_disengagement(interceptor_aircraft, game):
            results["combat_narrative"].append("Interceptors disengage — low ammo/fuel")
            break

    original_bombers = len(raid_bomber_ids)
    surviving_bombers = len(bomber_aircraft)
    if original_bombers > 0:
        loss_ratio = 1 - (surviving_bombers / original_bombers)
        if loss_ratio > 0.3:
            results["raid_disrupted"] = True
            results["bombs_jettisoned_pct"] = min(0.8, loss_ratio * 1.5)
        elif loss_ratio > 0.1:
            results["bombs_jettisoned_pct"] = loss_ratio * 0.5

    _check_medals_and_promotions(game, results)

    return results


def _determine_engagement_type(game, interceptors, raid) -> EngagementType:
    raid_altitude = raid.get("altitude_ft", 15000)

    avg_awareness = 0.5
    if interceptors:
        pilots = [_get_pilot_for_aircraft(game, a) for a in interceptors]
        pilots = [p for p in pilots if p]
        if pilots:
            avg_awareness = sum(p.combat_awareness() for p in pilots) / len(pilots)

    sqn_ids = set()
    for ac in interceptors:
        sqn = game.squadrons.get(ac.squadron_id)
        if sqn:
            sqn_ids.add(sqn.id)

    doctrine_mods = {}
    for sid in sqn_ids:
        sqn = game.squadrons.get(sid)
        if sqn:
            doctrine_mods = sqn.doctrine_modifier()
            break

    bounce_chance = avg_awareness * 0.4 + doctrine_mods.get("search_effectiveness", 0.5) * 0.3
    if raid_altitude > 20000:
        bounce_chance += 0.1

    roll = random.random()
    if roll < bounce_chance * 0.5:
        return EngagementType.BOUNCE
    elif roll < bounce_chance * 0.5 + 0.15:
        return EngagementType.HEAD_ON

    if interceptors:
        ac_type = game.aircraft_types.get(interceptors[0].aircraft_type)
        if ac_type and ac_type.combat.zoom_climb >= 8:
            if random.random() < 0.4:
                return EngagementType.BOOM_AND_ZOOM

    return EngagementType.TURNING_FIGHT


def _resolve_fighter_combat(game, attackers, defenders, results,
                            engagement, altitude_ft, round_num):
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

        atk_score = _compute_combat_score(
            atk_type, atk_pilot, attacker, engagement, altitude_ft, is_attacker=True,
        )
        def_score = _compute_combat_score(
            def_type, def_pilot, defender, engagement, altitude_ft, is_attacker=False,
        )

        atk_sqn = game.squadrons.get(attacker.squadron_id)
        def_sqn = game.squadrons.get(defender.squadron_id)
        if atk_sqn:
            doc = atk_sqn.doctrine_modifier()
            atk_score += doc.get("mutual_support", 0.5) * 1.0
            atk_score += atk_sqn.co_leadership_bonus(game.pilots) * 2.0
        if def_sqn:
            doc = def_sqn.doctrine_modifier()
            def_score += doc.get("mutual_support", 0.5) * 1.0
            def_score += def_sqn.co_leadership_bonus(game.pilots) * 2.0

        if round_num == 0 and engagement == EngagementType.BOUNCE:
            atk_score += 3.0
        elif round_num == 0 and engagement == EngagementType.HEAD_ON:
            atk_score += 0.5
            def_score += 0.5

        diff = atk_score - def_score + random.gauss(0, 1.2)

        if diff > 3.0:
            severity = random.uniform(0.5, 1.0)
            hit_chance = _compute_hit_chance(atk_type, atk_pilot, attacker)
            if random.random() < hit_chance:
                _apply_damage(game, defender, def_pilot, severity, results)
                if atk_pilot:
                    _record_kill(atk_pilot, results, severity > 0.7)
        elif diff > 1.5:
            hit_chance = _compute_hit_chance(atk_type, atk_pilot, attacker) * 0.6
            if random.random() < hit_chance:
                _apply_damage(game, defender, def_pilot, random.uniform(0.1, 0.5), results)
        elif diff < -3.0:
            severity = random.uniform(0.5, 1.0)
            hit_chance = _compute_hit_chance(def_type, def_pilot, defender)
            if random.random() < hit_chance:
                _apply_damage(game, attacker, atk_pilot, severity, results)
                if def_pilot:
                    _record_kill(def_pilot, results, severity > 0.7)
        elif diff < -1.5:
            hit_chance = _compute_hit_chance(def_type, def_pilot, defender) * 0.6
            if random.random() < hit_chance:
                _apply_damage(game, attacker, atk_pilot, random.uniform(0.1, 0.5), results)

        burst_cost = 1.0 / max(1, atk_type.combat.ammo_endurance_passes())
        attacker.ammo_remaining = max(0, attacker.ammo_remaining - burst_cost * random.uniform(0.8, 1.2))
        defender.ammo_remaining = max(0, defender.ammo_remaining - burst_cost * random.uniform(0.8, 1.2))


def _compute_combat_score(ac_type, pilot, aircraft, engagement, altitude_ft, is_attacker):
    cp = ac_type.combat

    if engagement == EngagementType.TURNING_FIGHT:
        aircraft_score = (
            cp.turn_rate * 0.35
            + cp.roll_rate * 0.2
            + cp.gun_platform_stability * 2.0
            + ac_type.agility * 0.2
        )
    elif engagement == EngagementType.BOOM_AND_ZOOM:
        aircraft_score = (
            cp.dive_speed_mph / 60.0
            + cp.zoom_climb * 0.4
            + cp.burst_mass_lbs_sec * 0.8
            + (1.0 if cp.fuel_injection else 0.0)
        )
    elif engagement == EngagementType.BOUNCE:
        if is_attacker:
            aircraft_score = (
                cp.dive_speed_mph / 60.0
                + cp.burst_mass_lbs_sec * 1.0
                + (1.0 - cp.cockpit_visibility) * 2.0
            )
        else:
            aircraft_score = (
                cp.cockpit_visibility * 3.0
                + cp.roll_rate * 0.3
                + cp.structural_g_limit * 0.2
            )
    elif engagement == EngagementType.HEAD_ON:
        aircraft_score = (
            cp.burst_mass_lbs_sec * 1.5
            + ac_type.durability * 0.3
            + cp.gun_platform_stability * 1.5
        )
    elif engagement == EngagementType.DEFENSIVE:
        aircraft_score = (
            cp.turn_rate * 0.3
            + cp.roll_rate * 0.3
            + ac_type.durability * 0.3
            + (1.0 if cp.fuel_injection else 0.0)
        )
    else:
        aircraft_score = (
            ac_type.firepower * 0.3
            + ac_type.agility * 0.3
            + cp.gun_platform_stability * 1.5
        )

    alt_ratio = altitude_ft / max(1, cp.optimal_alt_ft)
    if alt_ratio > 1.3:
        aircraft_score *= cp.high_alt_modifier
    elif alt_ratio < 0.7:
        aircraft_score *= cp.low_alt_modifier

    pilot_score = 0.0
    if pilot:
        if engagement == EngagementType.TURNING_FIGHT:
            pilot_score = (
                pilot.effective_skill() * 2.5
                + pilot.combat_energy_mgmt() * 1.0
                + pilot.combat_gunnery() * 1.0
            )
        elif engagement == EngagementType.BOOM_AND_ZOOM:
            pilot_score = (
                pilot.combat_energy_mgmt() * 2.0
                + pilot.combat_gunnery() * 1.5
                + pilot.combat_awareness() * 1.0
            )
        elif engagement == EngagementType.BOUNCE:
            if is_attacker:
                pilot_score = (
                    pilot.combat_gunnery() * 2.0
                    + pilot.combat_awareness() * 1.5
                    + pilot.combat_aggression() * 1.0
                )
            else:
                pilot_score = (
                    pilot.combat_awareness() * 3.0
                    + pilot.traits.coolness * 1.5
                )
        elif engagement == EngagementType.HEAD_ON:
            pilot_score = (
                pilot.traits.coolness * 2.0
                + pilot.combat_gunnery() * 2.0
                + pilot.combat_aggression() * 0.5
            )
        else:
            pilot_score = (
                pilot.effective_skill() * 2.0
                + pilot.combat_gunnery() * 1.0
                + pilot.combat_awareness() * 1.5
            )

    ammo_mod = aircraft.ammo_remaining
    if ammo_mod < 0.2:
        aircraft_score *= 0.5

    return aircraft_score + pilot_score


def _compute_hit_chance(ac_type, pilot, aircraft) -> float:
    cp = ac_type.combat
    base = cp.gun_platform_stability * 0.4 + cp.burst_mass_lbs_sec * 0.05
    if pilot:
        base += pilot.combat_gunnery() * 0.3
    base *= aircraft.ammo_remaining
    return max(0.1, min(0.95, base))


def _resolve_bomber_attack(game, fighters, bombers, results, altitude_ft):
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
        f_cp = f_type.combat
        b_cp = b_type.combat

        gunnery = f_pilot.combat_gunnery() if f_pilot else 0.5
        aggression = f_pilot.combat_aggression() if f_pilot else 0.5
        skill = f_pilot.effective_skill() if f_pilot else 0.5

        attack_score = (
            f_cp.burst_mass_lbs_sec * 1.2
            + gunnery * 3.0
            + skill * 2.0
            + aggression * 1.0
            + f_cp.gun_platform_stability * 1.5
        )

        formation_def = b_cp.formation_defense_bonus
        defense_score = (
            b_type.firepower * 0.5
            + b_type.durability * 0.4
            + formation_def * 3.0
            + random.gauss(0, 0.8)
        )

        if f_type.combat.armament_type == "mg_battery":
            attack_score *= 0.85
        elif f_type.combat.armament_type in ("cannon_mg_mix", "cannon_mg_heavy"):
            attack_score *= 1.3

        diff = attack_score - defense_score + random.gauss(0, 1.0)

        if diff > 2.0:
            severity = min(1.0, random.uniform(0.3, 0.8) * (diff / 5.0))
            hit_chance = _compute_hit_chance(f_type, f_pilot, fighter)
            if random.random() < hit_chance:
                b_pilot = _get_pilot_for_aircraft(game, bomber)
                _apply_damage(game, bomber, b_pilot, severity, results)
                if severity > 0.7 and f_pilot:
                    _record_kill(f_pilot, results, True)

        closing_range_risk = 0.05 + formation_def * 0.08
        if aggression > 0.7:
            closing_range_risk += 0.03
        if random.random() < closing_range_risk:
            severity = random.uniform(0.1, 0.4)
            _apply_damage(game, fighter, f_pilot, severity, results)

        burst_cost = 1.0 / max(1, f_cp.ammo_endurance_passes())
        fighter.ammo_remaining = max(0, fighter.ammo_remaining - burst_cost * random.uniform(1.0, 1.5))


def _apply_damage(game, aircraft, pilot, severity, results):
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
            if pilot.traits.coolness > 0.7:
                bail_chance += 0.1
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
                    pilot.morale = max(0.1, pilot.morale - 0.15)
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


def _record_kill(pilot, results, confirmed):
    if confirmed:
        pilot.kills += 1
        results["kills_by_pilot"][pilot.id] = results["kills_by_pilot"].get(pilot.id, 0) + 1
        if pilot.kills >= 5:
            pilot.is_ace = True


def _check_disengagement(aircraft_list, game) -> bool:
    if not aircraft_list:
        return True
    low_ammo = sum(1 for a in aircraft_list if a.ammo_remaining < 0.15)
    low_fuel = sum(1 for a in aircraft_list if a.fuel_remaining < 0.3)
    return (low_ammo + low_fuel) > len(aircraft_list) * 0.6


def _check_medals_and_promotions(game, results):
    for pilot_id in results.get("kills_by_pilot", {}):
        pilot = game.pilots.get(pilot_id)
        if pilot:
            events = pilot.check_promotions_and_medals()
            for msg in events:
                game.add_event("award", msg, side=pilot.side.value)


def resolve_bombing(game: GameState, raid: dict, disruption_pct: float) -> dict:
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
