import random
from datetime import timedelta

from models.enums import (
    Side, AircraftStatus, PilotStatus, SquadronState, GamePhase,
    MissionType, WeatherCondition,
)
from models.game_state import GameState
from simulation.weather import advance_weather, get_visibility, is_flyable
from simulation.combat import resolve_interception, resolve_bombing
from simulation.ai import generate_luftwaffe_raids, generate_raf_intercepts, detect_raids


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
        self.game.turn_number += 1
        turn_events = []

        self._update_weather()

        self._update_phase()

        self._process_repairs()
        self._process_pilot_recovery()
        self._resupply()
        self._aircraft_production()

        if player_orders:
            turn_events.extend(self._process_player_orders(player_orders))

        if self.game.player_side == Side.RAF:
            raids = generate_luftwaffe_raids(self.game)
            for raid in raids:
                self.game.active_raids.append(raid)
                self.game.add_event(
                    "raid_launched",
                    f"Luftwaffe raid forming: {len(raid['bomber_aircraft_ids'])} bombers "
                    f"with {len(raid['escort_aircraft_ids'])} escorts targeting {raid['target_name']}",
                    side="luftwaffe",
                )
        else:
            raids = generate_luftwaffe_raids(self.game)
            for raid in raids:
                self.game.active_raids.append(raid)

        detect_raids(self.game)

        if self.game.player_side == Side.LUFTWAFFE:
            intercepts = generate_raf_intercepts(self.game)
            for intercept in intercepts:
                self._resolve_intercept(intercept)

        self._resolve_raids()

        self._return_aircraft()

        self.game.current_date += timedelta(hours=self.game.time_scale_hours)

        return {
            "turn": self.game.turn_number,
            "summary": self.game.summary(),
            "events": self.game.event_log[-20:],
            "active_raids": self.game.active_raids,
        }

    def scramble_squadron(self, squadron_id: str, raid_id: str = None) -> dict:
        """Player command to scramble a squadron."""
        sqn = self.game.squadrons.get(squadron_id)
        if not sqn:
            return {"success": False, "message": "Squadron not found"}
        if not sqn.can_scramble(self.game.aircraft, self.game.pilots):
            return {"success": False, "message": "Squadron cannot scramble — insufficient ready aircraft or pilots"}

        sqn.state = SquadronState.AIRBORNE
        sqn.current_mission = MissionType.INTERCEPT
        aircraft_launched = []
        for ac_id in sqn.aircraft_ids:
            ac = self.game.aircraft.get(ac_id)
            if ac and ac.is_available():
                ac.status = AircraftStatus.AIRBORNE
                aircraft_launched.append(ac_id)

        self.game.raf_stats["sorties_flown"] += len(aircraft_launched)

        if raid_id:
            target_raid = None
            for raid in self.game.active_raids:
                if raid["id"] == raid_id:
                    target_raid = raid
                    break
            if target_raid:
                sqn.mission_target = raid_id
                results = resolve_interception(self.game, aircraft_launched, target_raid)
                target_raid["intercepted"] = True
                self.game.add_event(
                    "interception",
                    f"{sqn.name} intercepts raid on {target_raid['target_name']}: "
                    f"{len(results['lw_losses'])} enemy destroyed, "
                    f"{len(results['raf_losses'])} fighters lost",
                    side="raf",
                    details=results,
                )
                return {"success": True, "message": f"Squadron scrambled and intercepting", "results": results}

        self.game.add_event(
            "scramble",
            f"{sqn.name} scrambled with {len(aircraft_launched)} aircraft",
            side="raf",
        )
        return {"success": True, "message": f"Squadron scrambled with {len(aircraft_launched)} aircraft"}

    def launch_raid(self, bomber_ids: list[str], escort_ids: list[str],
                    target_id: str, target_type: str) -> dict:
        """Player command to launch a Luftwaffe raid."""
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

        raid = {
            "id": f"raid_{self.game.turn_number}_{random.randint(1000, 9999)}",
            "target_id": target_id,
            "target_type": target_type,
            "target_name": target_name,
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
            "lat": 50.5,
            "lon": 1.5,
        }

        self.game.active_raids.append(raid)
        self.game.luftwaffe_stats["sorties_flown"] += len(bomber_ac_ids) + len(escort_ac_ids)

        self.game.add_event(
            "raid_launched",
            f"Raid launched: {len(bomber_ac_ids)} bombers with {len(escort_ac_ids)} escorts targeting {target_name}",
            side="luftwaffe",
        )

        return {"success": True, "raid_id": raid["id"], "bombers": len(bomber_ac_ids), "escorts": len(escort_ac_ids)}

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
            for ac_type_id, ac_type in self.game.aircraft_types.items():
                if ac_type.side == Side.RAF and ac_type.role.value in ("fighter",):
                    daily_production = ac_type.production_per_week / 7.0
                    new_aircraft = int(daily_production)
                    if random.random() < (daily_production - new_aircraft):
                        new_aircraft += 1

                    if new_aircraft > 0:
                        raf_sqns = [
                            s for s in self.game.squadrons.values()
                            if s.side == Side.RAF and s.aircraft_type == ac_type_id
                        ]
                        if raf_sqns:
                            neediest = min(
                                raf_sqns,
                                key=lambda s: s.operational_aircraft(self.game.aircraft),
                            )
                            for _ in range(new_aircraft):
                                ac_id = f"{neediest.id}_ac_prod_{self.game.turn_number}_{random.randint(100,999)}"
                                from models.aircraft import Aircraft
                                ac = Aircraft(id=ac_id, aircraft_type=ac_type_id, squadron_id=neediest.id)
                                self.game.aircraft[ac_id] = ac
                                neediest.aircraft_ids.append(ac_id)
                                self.game.raf_stats["fighters_produced"] += 1

    def _process_player_orders(self, orders: dict) -> list[dict]:
        events = []
        if orders.get("time_scale"):
            self.game.time_scale_hours = float(orders["time_scale"])
        return events

    def _resolve_intercept(self, intercept: dict):
        raid_id = intercept["raid_id"]
        target_raid = None
        for raid in self.game.active_raids:
            if raid["id"] == raid_id:
                target_raid = raid
                break
        if not target_raid:
            return

        results = resolve_interception(self.game, intercept["aircraft_ids"], target_raid)
        target_raid["intercepted"] = True

        sqn_names = []
        for sid in intercept["squadron_ids"]:
            sqn = self.game.squadrons.get(sid)
            if sqn:
                sqn_names.append(sqn.name)

        self.game.add_event(
            "interception",
            f"{', '.join(sqn_names)} intercept raid on {target_raid['target_name']}: "
            f"{len(results['lw_losses'])} enemy destroyed, {len(results['raf_losses'])} fighters lost",
            side="raf",
            details={
                "raf_losses": len(results["raf_losses"]),
                "lw_losses": len(results["lw_losses"]),
            },
        )

    def _resolve_raids(self):
        for raid in self.game.active_raids:
            if raid.get("resolved"):
                continue

            disruption = raid.get("bombs_jettisoned_pct", 0.0)
            if raid.get("raid_disrupted"):
                disruption = max(disruption, 0.5)

            if raid["target_type"] in ("airfield", "radar_station"):
                results = resolve_bombing(self.game, raid, disruption)
                if results["damage_inflicted"] > 0:
                    self.game.add_event(
                        "bombing",
                        f"Bombing of {raid['target_name']}: {results['bombs_tons']:.1f} tons dropped, "
                        f"damage severity {results['damage_inflicted']:.0%}",
                        side="luftwaffe",
                        details=results,
                    )

            raid["resolved"] = True

        self.game.active_raids = [r for r in self.game.active_raids if not r.get("resolved")]

    def _return_aircraft(self):
        for sqn in self.game.squadrons.values():
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
                    sqn.state = SquadronState.READY
                    sqn.rearm_hours_remaining = 0

    def get_state(self) -> dict:
        """Get full game state for the UI."""
        summary = self.game.summary()

        squadrons = {}
        for sid, sqn in self.game.squadrons.items():
            squadrons[sid] = sqn.to_dict(self.game.aircraft, self.game.pilots)

        airfields = {}
        for aid, af in self.game.airfields.items():
            airfields[aid] = af.to_dict()

        radar = {}
        for rid, rs in self.game.radar_stations.items():
            radar[rid] = rs.to_dict()

        aces = sorted(
            [p for p in self.game.pilots.values() if p.kills > 0],
            key=lambda p: p.kills, reverse=True,
        )[:20]

        return {
            "summary": summary,
            "squadrons": squadrons,
            "airfields": airfields,
            "radar_stations": radar,
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
        }

    def set_player_side(self, side: str):
        self.game.player_side = Side(side)

    def set_time_scale(self, hours: float):
        self.game.time_scale_hours = hours
