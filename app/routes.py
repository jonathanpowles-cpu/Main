from flask import Blueprint, jsonify, render_template, request

from simulation.engine import GameEngine

bp = Blueprint("main", __name__)

engine = GameEngine()


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/state")
def get_state():
    return jsonify(engine.get_state())


@bp.route("/api/advance", methods=["POST"])
def advance_turn():
    orders = request.json or {}
    result = engine.advance_turn(orders)
    return jsonify(result)


@bp.route("/api/scramble", methods=["POST"])
def scramble():
    data = request.json
    squadron_id = data.get("squadron_id")
    raid_id = data.get("raid_id")
    result = engine.scramble_squadron(squadron_id, raid_id)
    return jsonify(result)


@bp.route("/api/launch_raid", methods=["POST"])
def launch_raid():
    data = request.json
    result = engine.launch_raid(
        bomber_ids=data.get("bomber_ids", []),
        escort_ids=data.get("escort_ids", []),
        target_id=data.get("target_id", ""),
        target_type=data.get("target_type", "airfield"),
    )
    return jsonify(result)


@bp.route("/api/set_side", methods=["POST"])
def set_side():
    data = request.json
    engine.set_player_side(data.get("side", "raf"))
    return jsonify({"success": True})


@bp.route("/api/set_time_scale", methods=["POST"])
def set_time_scale():
    data = request.json
    engine.set_time_scale(float(data.get("hours", 1)))
    return jsonify({"success": True})


@bp.route("/api/pilots")
def get_pilots():
    side = request.args.get("side", "")
    squadron_id = request.args.get("squadron", "")
    sort_by = request.args.get("sort", "kills")
    aces_only = request.args.get("aces", "false") == "true"

    pilots = list(engine.game.pilots.values())

    if side:
        from models.enums import Side
        pilots = [p for p in pilots if p.side == Side(side)]
    if squadron_id:
        pilots = [p for p in pilots if p.squadron_id == squadron_id]
    if aces_only:
        pilots = [p for p in pilots if p.is_ace]

    if sort_by == "kills":
        pilots.sort(key=lambda p: p.kills, reverse=True)
    elif sort_by == "sorties":
        pilots.sort(key=lambda p: p.sorties, reverse=True)
    elif sort_by == "experience":
        pilots.sort(key=lambda p: p.experience, reverse=True)
    elif sort_by == "name":
        pilots.sort(key=lambda p: p.name)

    limit = int(request.args.get("limit", 100))
    return jsonify([p.to_dict() for p in pilots[:limit]])


@bp.route("/api/pilot/<pilot_id>")
def get_pilot(pilot_id):
    pilot = engine.game.pilots.get(pilot_id)
    if not pilot:
        return jsonify({"error": "Pilot not found"}), 404
    sqn = engine.game.squadrons.get(pilot.squadron_id)
    data = pilot.to_dict()
    if sqn:
        data["squadron_name"] = sqn.name
        data["aircraft_type"] = sqn.aircraft_type
        ac_type = engine.game.aircraft_types.get(sqn.aircraft_type)
        if ac_type:
            data["aircraft_name"] = ac_type.name
    return jsonify(data)


@bp.route("/api/new_game", methods=["POST"])
def new_game():
    global engine
    data = request.json or {}
    engine = GameEngine()
    side = data.get("side", "raf")
    engine.set_player_side(side)
    return jsonify(engine.get_state())


@bp.route("/api/save", methods=["POST"])
def save_game():
    data = request.json or {}
    slot = int(data.get("slot", 1))
    return jsonify(engine.save_game(slot))


@bp.route("/api/load", methods=["POST"])
def load_game():
    data = request.json or {}
    slot = int(data.get("slot", 1))
    result = engine.load_game(slot)
    return jsonify(result)


@bp.route("/api/saves")
def list_saves():
    return jsonify(engine.list_saves())


@bp.route("/api/patrol", methods=["POST"])
def assign_patrol():
    data = request.json or {}
    result = engine.assign_patrol(
        squadron_id=data.get("squadron_id", ""),
        sector=data.get("sector", ""),
    )
    return jsonify(result)
