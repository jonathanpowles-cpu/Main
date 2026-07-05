import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from models.enums import (
    Side, AircraftStatus, PilotStatus, SquadronState, GamePhase, MissionType,
)
from models.game_state import GameState
from simulation.weather import advance_weather, get_visibility, is_flyable
from simulation.combat import resolve_interception, resolve_bombing
from simulation.ai import (
    generate_luftwaffe_raids, generate_raf_intercepts, detect_raids,
    move_raids, check_patrol_intercepts, PATROL_SECTORS as AI_PATROL_SECTORS,
)

SAVES_DIR = Path(__file__).parent.parent / "saves"

RAF_WIN_AIRFIELDS = 12
RAF_WIN_RADAR = 8
LW_WIN_AIRFIELDS_DESTROYED = 15
LW_WIN_PILOTS_KILLED = 300

# Human-readable names for patrol sectors
PATROL_SECTOR_NAMES = {
    k: k.replace("_", " ").title()
    for k in AI_PATROL_SECTORS
}


class GameEngine:
    def __init__(self):
        self.game = GameState()
        self.game.load_data()
        self.game.add_event(
            "game_start",
            "10 July 1940 — The Battle of Britain begins. Luftwaffe launches initial attacks on Channel convoys and coastal targets.",
            side="both",
        )

    def advance_turn(self, player_orders: dict = None) -> dict:
        """Advance the game by one time step."""
        if self.game.game_over:
            return {
                "turn": self.game.turn_number,
                "summary": self.game.summary(),
                "events": self.game.event_log[-20:],
                "active_raids": self.game.active_raids,
                "new_detection": False,
                "victory": self.game.winner,
            }

        self.game.turn_number += 1

        self._update_weather()
        self._update_phase()
        self._process_repairs()
        self._process_pilot_recovery()
        self._resupply()
        self._aircraft_production()

        if player_orders:
            self._process_player_orders(player_orders)

        # Generate new Luftwaffe raids
        raids = generate_luftwaffe_raids(self.game)
        for raid in raids:
            self.game.active_raids.append(raid)
            if self.game.player_side == Side.RAF:
                self.game.add_event(
                    "raid_forming",
                    f"Luftwaffe forming: {len(raid['bomber_aircraft_ids'])} bombers "
                    f"+ {len(raid['escort_aircraft_ids'])} escorts → {raid['target_name']}",
                    side="luftwaffe",
                )

        # Advance raid positions toward targets
        move_raids(self.game)

        # Detect raids with radar — capture newly detected
        previously_detected = {r["id"] for r in self.game.active_raids if r.get("detected")}
        detect_raids(self.game)
        newly_detected = [
            r for r in self.game.active_raids
            if r.get("detected") and r["id"] not in previously_detected
        ]
        new_detection = len(newly_detected) > 0

        # Patrol squadrons auto-intercept raids in their sector
        check_patrol_intercepts(self.game)

        # AI intercepts (when player is Luftwaffe)
        if self.game.player_side == Side.LUFTWAFFE:
            intercepts = generate_raf_intercepts(self.game)
            for intercept in intercepts:
                self._resolve_intercept(intercept)

        # Resolve raids that have reached their target
        self._resolve_raids()

        # Return airborne aircraft to base
        self._return_aircraft()

        # Update strategic balance gauge
        self.game.strategic_balance = self._compute_strategic_balance()

        # Check victory conditions
        if not self.game.game_over:
            v = self._check_victory()
            if v:
                self.game.game_over = True
                self.game.winner = v["winner"]
                self.game.victory_reason = v["reason"]
                self.game.add_event("game_over", v["reason"], side=v["winner"])

        self.game.current_date += timedelta(hours=self.game.time_scale_hours)

        return {
            "turn": self.game.turn_number,
            "summary": self.game.summary(),
            "events": self.game.event_log[-20:],
            "active_raids": self.game.active_raids,
            "new_detection": new_detection,
            "newly_detected": [r["target_name"] for r in newly_detected],
            "victory": self.game.winner if self.game.game_over else None,
        }

    def scramble_squadron(self, squadron_id: str, raid_id: str = None) -> dict:
        sqn = self.game.squadrons.get(squadron_id)
        if not sqn:
            return {"success": False, "message": "Squadron not found"}
        if not sqn.can_scramble(self.game.aircraft, self.game.pilots):
            return {"success": False, "message": "Squadron cannot scramble — insufficient ready aircraft or pilots"}

        sqn.state = SquadronState.AIRBORNE
        sqn.current_mission = MissionType.INTERCEPT
        sqn.patrol_sector = None  # clear patrol when scrambled
        aircraft_launched = []
        for ac_id in sqn.aircraft_ids:
            ac = self.game.aircraft.get(ac_id)
            if ac and ac.is_available():
                ac.status = AircraftStatus.AIRBORNE
                aircraft_launched.append(ac_id)

        self.game.raf_stats["sorties_flown"] += len(aircraft_launched)

        if raid_id:
            target_raid = next((r for r in self.game.active_raids if r["id"] == raid_id), None)
            if target_raid and target_raid.get("phase") in ("en_route", "attacking"):
                sqn.mission_target = raid_id
                results = resolve_interception(self.game, aircraft_launched, target_raid)
                target_raid["intercepted"] = True
                self.game.add_event(
                    "interception",
                    f"{sqn.name} intercepts raid on {target_raid['target_name']}: "
                    f"{len(results['lw_losses'])} enemy destroyed, "
                    f"{len(results['raf_losses'])} fighters lost",
                    side="raf",
                    details={"raf_losses": len(results["raf_losses"]), "lw_losses": len(results["lw_losses"])},
                )
                return {"success": True, "message": "Squadron scrambled and intercepting", "results": results}

        self.game.add_event(
            "scramble",
            f"{sqn.name} scrambled with {len(aircraft_launched)} aircraft",
            side="raf",
        )
        return {"success": True, "message": f"Squadron scrambled with {len(aircraft_launched)} aircraft"}

    def launch_raid(self, bomber_ids: list[str], escort_ids: list[str],
                    target_id: str, target_type: str) -> dict:
        target_lat, target_lon = self._get_target_latlon(target_id, target_type)

        bomber_ac_ids = []
        for unit_id in bomber_ids:
            sqn = self.game.squadrons.get(unit_id)
            if sqn and sqn.state in (SquadronState.READY, SquadronState.STANDBY):
                sqn.state = SquadronState.AIRBORNE
                sqn.current_mission = MissionType.BOMBING
                sqn.mission_target = target_id
                for ac_id in sqn.aircraft_ids:
                    ac = self.game.aircraft.get(ac_id)
                    if ac and ac.is_available():
                        ac.status = AircraftStatus.AIRBORNE
                        bomber_ac_ids.append(ac_id)

        escort_ac_ids = []
        for unit_id in escort_ids:
            sqn = self.game.squadrons.get(unit_id)
            if sqn and sqn.state in (SquadronState.READY, SquadronState.STANDBY):
                sqn.state = SquadronState.AIRBORNE
                sqn.current_mission = MissionType.ESCORT
                for ac_id in sqn.aircraft_ids:
                    ac = self.game.aircraft.get(ac_id)
                    if ac and ac.is_available():
                        ac.status = AircraftStatus.AIRBORNE
                        escort_ac_ids.append(ac_id)

        target_name = target_id
        if target_id in self.game.airfields:
            target_name = self.game.airfields[target_id].name
        elif target_id in self.game.radar_stations:
            target_name = self.game.radar_stations[target_id].name
        elif target_id in self.game.industrial_targets:
            target_name = self.game.industrial_targets[target_id].name

        start_lat, start_lon = 50.8, 2.3
        if target_lat and target_lat > 53.0:
            start_lat, start_lon = 58.0, 8.0

        raid = {
            "id": f"raid_{self.game.turn_number}_{random.randint(1000, 9999)}",
            "target_id": target_id,
            "target_type": target_type,
            "target_name": target_name,
            "target_lat": target_lat,
            "target_lon": target_lon,
            "bomber_unit_ids": bomber_ids,
            "escort_unit_ids": escort_ids,
            "bomber_aircraft_ids": bomber_ac_ids,
            "escort_aircraft_ids": escort_ac_ids,
            "altitude_ft": 15000,
            "detected": False,
            "intercepted": False,
            "resolved": False,
            "phase": "forming",
            "player_ordered": True,
            "lat": start_lat,
            "lon": start_lon,
        }

        self.game.active_raids.append(raid)
        self.game.luftwaffe_stats["sorties_flown"] += len(bomber_ac_ids) + len(escort_ac_ids)
        self.game.add_event(
            "raid_launched",
            f"Raid launched: {len(bomber_ac_ids)} bombers + {len(escort_ac_ids)} escorts → {target_name}",
            side="luftwaffe",
        )
        return {"success": True, "raid_id": raid["id"], "bombers": len(bomber_ac_ids), "escorts": len(escort_ac_ids)}

    def assign_patrol(self, squadron_id: str, sector: str) -> dict:
        sqn = self.game.squadrons.get(squadron_id)
        if not sqn or sqn.side != Side.RAF:
            return {"success": False, "message": "RAF squadron not found"}
        if sector and sector not in AI_PATROL_SECTORS:
            return {"success": False, "message": f"Unknown patrol sector: {sector}"}

        sqn.patrol_sector = sector if sector else None
        if sector and sqn.state in (SquadronState.READY, SquadronState.STANDBY):
            sqn.state = SquadronState.PATROLLING
        elif not sector and sqn.state == SquadronState.PATROLLING:
            sqn.state = SquadronState.READY

        label = PATROL_SECTOR_NAMES.get(sector, sector) if sector else "none"
        self.game.add_event(
            "patrol_assigned",
            f"{sqn.name} patrol sector set to: {label}",
            side="raf",
        )
        return {"success": True, "message": f"{sqn.name} → patrol {label}"}

    def save_game(self, slot: int = 1) -> dict:
        SAVES_DIR.mkdir(exist_ok=True)
        data = self.game.to_save_dict()
        path = SAVES_DIR / f"slot{slot}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return {
            "success": True,
            "slot": slot,
            "saved_date": data["current_date"],
            "message": f"Saved to slot {slot}",
        }

    def load_game(self, slot: int = 1) -> dict:
        path = SAVES_DIR / f"slot{slot}.json"
        if not path.exists():
            return {"success": False, "error": f"No save found in slot {slot}"}
        with open(path) as f:
            data = json.load(f)
        self.game = GameState.load_from_save(data)
        return {"success": True, "state": self.get_state()}

    def list_saves(self) -> list[dict]:
        saves = []
        for i in range(1, 4):
            path = SAVES_DIR / f"slot{i}.json"
            if path.exists():
                try:
                    with open(path) as f:
                        d = json.load(f)
                    saves.append({
                        "slot": i,
                        "date": d.get("current_date", "?")[:10],
                        "turn": d.get("turn_number", 0),
                        "side": d.get("player_side", "?"),
                    })
                except Exception:
                    saves.append({"slot": i, "date": "corrupt", "turn": 0, "side": "?"})
            else:
                saves.append({"slot": i, "date": None, "turn": 0, "side": None})
        return saves

    def _get_target_latlon(self, target_id: str, target_type: str) -> tuple[float, float]:
        CITY_POS = {
            "london": (51.505, -0.12),
            "london_docks": (51.507, -0.06),
            "convoy": (51.0, 1.5),
        }
        if target_type == "airfield" and target_id in self.game.airfields:
            af = self.game.airfields[target_id]
            return af.lat, af.lon
        if target_type == "radar_station" and target_id in self.game.radar_stations:
            rs = self.game.radar_stations[target_id]
            return rs.lat, rs.lon
        if target_type == "industrial" and target_id in self.game.industrial_targets:
            it = self.game.industrial_targets[target_id]
            return it.lat, it.lon
        return CITY_POS.get(target_id, (51.3, -0.1))

    def _update_weather(self):
        self.game.weather = advance_weather(self.game.weather)
        self.game.visibility = get_visibility(self.game.weather)

    def _update_phase(self):
        day = (self.game.current_date.month - 7) * 30 + self.game.current_date.day
        if day < 25:
            self.game.phase = GamePhase.KANALKAMPF
        elif day < 50:
            self.game.phase = GamePhase.ADLERANGRIFF
        elif day < 85:
            self.game.phase = GamePhase.AIRFIELD_ATTACKS
        else:
            self.game.phase = GamePhase.LONDON_BLITZ

    def _process_repairs(self):
        hours = self.game.time_scale_hours
        for ac in self.game.aircraft.values():
            if ac.status == AircraftStatus.DAMAGED:
                ac.status = AircraftStatus.REPAIRING
            if ac.status == AircraftStatus.REPAIRING:
                ac.repair_hours_remaining -= hours
                if ac.repair_hours_remaining <= 0:
                    ac.status = AircraftStatus.READY
                    ac.damage = 0.0
                    ac.fuel_remaining = 1.0
                    ac.ammo_remaining = 1.0

        for af in self.game.airfields.values():
            if af.side == Side.RAF:
                af.repair(hours)

        for rs in self.game.radar_stations.values():
            if not rs.operational or rs.condition < 1.0:
                rs.repair(hours)

        for it in self.game.industrial_targets.values():
            it.repair(hours)

    def _process_pilot_recovery(self):
        hours = self.game.time_scale_hours
        for pilot in self.game.pilots.values():
            if pilot.status == PilotStatus.RESTING:
                pilot.rest(hours)
                if pilot.fatigue < 0.2:
                    pilot.status = PilotStatus.AVAILABLE
            elif pilot.status == PilotStatus.WOUNDED:
                pilot.recovery_hours -= hours
                if pilot.recovery_hours <= 0:
                    pilot.status = PilotStatus.AVAILABLE
                    pilot.wounds_severity = 0
            elif pilot.status == PilotStatus.HOSPITALIZED:
                pilot.recovery_hours -= hours
                if pilot.recovery_hours <= 0:
                    pilot.status = PilotStatus.AVAILABLE

    def _resupply(self):
        for af in self.game.airfields.values():
            if af.side == Side.RAF:
                af.resupply(
                    self.game.time_scale_hours * 2,
                    self.game.time_scale_hours * 1,
                )

    def _aircraft_production(self):
        if self.game.current_date.hour == 6 and self.game.time_scale_hours <= 24:
            # Factory damage penalty: average condition of all aircraft factories
            factory_penalty = 1.0
            if self.game.industrial_targets:
                factories = [
                    it for it in self.game.industrial_targets.values()
                    if it.target_type == "aircraft_factory"
                ]
                if factories:
                    avg_cond = sum(it.condition for it in factories) / len(factories)
                    if avg_cond < 0.8:
                        factory_penalty = max(0.4, avg_cond)

            for ac_type_id, ac_type in self.game.aircraft_types.items():
                if ac_type.side == Side.RAF and ac_type.role.value == "fighter":
                    daily = (ac_type.production_per_week / 7.0) * factory_penalty
                    new_ac = int(daily)
                    if random.random() < (daily - new_ac):
                        new_ac += 1
                    if new_ac > 0:
                        raf_sqns = [
                            s for s in self.game.squadrons.values()
                            if s.side == Side.RAF and s.aircraft_type == ac_type_id
                        ]
                        if raf_sqns:
                            neediest = min(raf_sqns, key=lambda s: s.operational_aircraft(self.game.aircraft))
                            for _ in range(new_ac):
                                from models.aircraft import Aircraft
                                ac_id = f"{neediest.id}_prod_{self.game.turn_number}_{random.randint(100,999)}"
                                ac = Aircraft(id=ac_id, aircraft_type=ac_type_id, squadron_id=neediest.id)
                                self.game.aircraft[ac_id] = ac
                                neediest.aircraft_ids.append(ac_id)
                                self.game.raf_stats["fighters_produced"] += 1

    def _process_player_orders(self, orders: dict):
        if orders.get("time_scale"):
            self.game.time_scale_hours = float(orders["time_scale"])

    def _resolve_intercept(self, intercept: dict):
        target_raid = next((r for r in self.game.active_raids if r["id"] == intercept["raid_id"]), None)
        if not target_raid:
            return
        results = resolve_interception(self.game, intercept["aircraft_ids"], target_raid)
        target_raid["intercepted"] = True
        sqn_names = [
            self.game.squadrons[sid].name
            for sid in intercept["squadron_ids"]
            if sid in self.game.squadrons
        ]
        self.game.add_event(
            "interception",
            f"{', '.join(sqn_names)} intercept raid on {target_raid['target_name']}: "
            f"{len(results['lw_losses'])} enemy destroyed, {len(results['raf_losses'])} fighters lost",
            side="raf",
            details={"raf_losses": len(results["raf_losses"]), "lw_losses": len(results["lw_losses"])},
        )

    def _resolve_raids(self):
        """Only resolve raids that have reached their target (phase == 'attacking')."""
        for raid in self.game.active_raids:
            if raid.get("resolved") or raid.get("phase") != "attacking":
                continue

            disruption = raid.get("bombs_jettisoned_pct", 0.0)
            if raid.get("raid_disrupted"):
                disruption = max(disruption, 0.5)

            ttype = raid["target_type"]
            if ttype in ("airfield", "radar_station"):
                results = resolve_bombing(self.game, raid, disruption)
                self.game.lw_bombs_total_tons += results.get("bombs_tons", 0)
                if results["damage_inflicted"] > 0:
                    self.game.lw_bombs_effective_tons += results.get("bombs_tons", 0)
                    self.game.add_event(
                        "bombing",
                        f"Bombing of {raid['target_name']}: {results['bombs_tons']:.1f} tons, "
                        f"damage {results['damage_inflicted']:.0%}",
                        side="luftwaffe",
                        details=results,
                    )
            elif ttype == "industrial":
                it = self.game.industrial_targets.get(raid["target_id"])
                if it:
                    disruption = raid.get("bombs_jettisoned_pct", 0.0)
                    if raid.get("raid_disrupted"):
                        disruption = max(disruption, 0.5)
                    bombers = len(raid.get("bomber_aircraft_ids", []))
                    effectiveness = (1.0 - disruption) * max(0.3, self.game.visibility)
                    damage = min(0.55, bombers * 0.012 * effectiveness * random.uniform(0.6, 1.4))
                    it.condition = max(0.0, it.condition - damage)
                    it.times_bombed += 1
                    tons = bombers * 1.8 * effectiveness
                    self.game.lw_bombs_total_tons += tons
                    self.game.lw_bombs_effective_tons += tons
                    self.game.luftwaffe_stats["bombs_dropped_tons"] = (
                        self.game.luftwaffe_stats.get("bombs_dropped_tons", 0) + tons
                    )
                    self.game.add_event(
                        "bombing",
                        f"{it.name} bombed: {damage:.0%} damage inflicted "
                        f"({it.condition:.0%} condition remaining). {tons:.0f} tons dropped.",
                        side="luftwaffe",
                    )
                    if it.target_type == "aircraft_factory" and it.condition < 0.5:
                        self.game.add_event(
                            "industrial_damage",
                            f"WARNING: {it.name} is severely damaged — fighter production disrupted.",
                            side="raf",
                        )
            elif ttype in ("city", "port"):
                tons = len(raid.get("bomber_aircraft_ids", [])) * 2.0
                self.game.lw_bombs_total_tons += tons
                self.game.lw_bombs_effective_tons += tons * self.game.visibility
                self.game.luftwaffe_stats["bombs_dropped_tons"] = (
                    self.game.luftwaffe_stats.get("bombs_dropped_tons", 0) + tons
                )
                self.game.add_event(
                    "bombing",
                    f"Bombing of {raid['target_name']}: ~{tons:.0f} tons dropped",
                    side="luftwaffe",
                )

            raid["resolved"] = True

        self.game.active_raids = [r for r in self.game.active_raids if not r.get("resolved")]

    def _return_aircraft(self):
        # Squadrons still committed to en_route raids stay airborne
        committed = set()
        for raid in self.game.active_raids:
            if not raid.get("resolved"):
                for sid in raid.get("bomber_unit_ids", []) + raid.get("escort_unit_ids", []):
                    committed.add(sid)

        for sqn in self.game.squadrons.values():
            if sqn.state == SquadronState.AIRBORNE and sqn.id in committed:
                continue

            if sqn.state == SquadronState.AIRBORNE:
                sqn.state = SquadronState.REARMING
                sqn.rearm_hours_remaining = 1.0
                sqn.current_mission = None
                sqn.mission_target = None
                for ac_id in sqn.aircraft_ids:
                    ac = self.game.aircraft.get(ac_id)
                    if ac and ac.status == AircraftStatus.AIRBORNE:
                        ac.status = AircraftStatus.READY
                        ac.fuel_remaining = 1.0
                        ac.ammo_remaining = 1.0
                        ac.sorties_flown += 1
                for pid in sqn.pilot_ids:
                    pilot = self.game.pilots.get(pid)
                    if pilot and pilot.status == PilotStatus.FLYING:
                        pilot.status = PilotStatus.AVAILABLE
                        pilot.add_fatigue(1.5)
                        pilot.sorties += 1

            elif sqn.state == SquadronState.REARMING:
                sqn.rearm_hours_remaining -= self.game.time_scale_hours
                if sqn.rearm_hours_remaining <= 0:
                    sqn.state = SquadronState.PATROLLING if sqn.patrol_sector else SquadronState.READY
                    sqn.rearm_hours_remaining = 0

    def _compute_strategic_balance(self) -> float:
        """0 = LW winning, 1 = RAF winning."""
        score = 0.5
        raf_afs = [a for a in self.game.airfields.values() if a.side == Side.RAF]
        if raf_afs:
            op_ratio = sum(1 for a in raf_afs if a.is_operational()) / len(raf_afs)
            score += (op_ratio - 0.7) * 0.3
        total_rs = len(self.game.radar_stations)
        if total_rs:
            rs_ratio = sum(1 for r in self.game.radar_stations.values() if r.operational) / total_rs
            score += (rs_ratio - 0.7) * 0.15
        raf_killed = self.game.raf_stats.get("pilots_killed", 0)
        score -= min(0.2, raf_killed / 300 * 0.2)
        lw_attrition = (
            self.game.luftwaffe_stats.get("pilots_killed", 0)
            + self.game.luftwaffe_stats.get("pilots_captured", 0)
        )
        score += min(0.1, lw_attrition / 500 * 0.1)
        return round(max(0.0, min(1.0, score)), 3)

    def _check_victory(self) -> dict | None:
        if self.game.turn_number < 5:
            return None
        g = self.game
        raf_afs = [a for a in g.airfields.values() if a.side == Side.RAF]
        op_af = sum(1 for a in raf_afs if a.is_operational())
        destroyed = len(raf_afs) - op_af
        op_rs = sum(1 for r in g.radar_stations.values() if r.operational)
        raf_killed = g.raf_stats.get("pilots_killed", 0)

        if destroyed >= LW_WIN_AIRFIELDS_DESTROYED:
            return {
                "winner": "luftwaffe",
                "reason": f"Luftwaffe has rendered {destroyed} RAF airfields non-operational — Fighter Command is paralysed.",
            }
        if raf_killed >= LW_WIN_PILOTS_KILLED:
            return {
                "winner": "luftwaffe",
                "reason": f"RAF Fighter Command has lost {raf_killed} pilots — reserves exhausted, resistance collapses.",
            }
        if g.current_date >= datetime(1940, 10, 31):
            if op_af >= RAF_WIN_AIRFIELDS and op_rs >= RAF_WIN_RADAR:
                return {
                    "winner": "raf",
                    "reason": f"RAF Fighter Command survives to 31 October with {op_af} airfields and {op_rs} radar stations intact. The Battle of Britain is won!",
                }
            else:
                return {
                    "winner": "luftwaffe",
                    "reason": f"By 31 October RAF retains only {op_af} airfields and {op_rs} radar stations — too weakened to claim strategic victory.",
                }
        return None

    def get_state(self) -> dict:
        summary = self.game.summary()
        squadrons = {sid: sqn.to_dict(self.game.aircraft, self.game.pilots)
                     for sid, sqn in self.game.squadrons.items()}
        airfields = {aid: af.to_dict() for aid, af in self.game.airfields.items()}
        radar = {rid: rs.to_dict() for rid, rs in self.game.radar_stations.items()}
        aces = sorted(
            [p for p in self.game.pilots.values() if p.kills > 0],
            key=lambda p: p.kills, reverse=True,
        )[:20]
        industrial = {tid: it.to_dict() for tid, it in self.game.industrial_targets.items()}
        return {
            "summary": summary,
            "squadrons": squadrons,
            "airfields": airfields,
            "radar_stations": radar,
            "industrial_targets": industrial,
            "active_raids": self.game.active_raids,
            "events": self.game.event_log[-50:],
            "aircraft_types": {
                k: {
                    "name": v.name, "side": v.side.value, "role": v.role.value,
                    "speed_mph": v.speed_mph, "firepower": v.firepower,
                    "agility": v.agility, "durability": v.durability,
                }
                for k, v in self.game.aircraft_types.items()
            },
            "top_pilots": [p.to_dict() for p in aces],
            "patrol_sectors": PATROL_SECTOR_NAMES,
        }

    def set_player_side(self, side: str):
        self.game.player_side = Side(side)

    def set_time_scale(self, hours: float):
        self.game.time_scale_hours = hours
