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


@bp.route("/api/new_game", methods=["POST"])
def new_game():
    global engine
    data = request.json or {}
    engine = GameEngine()
    side = data.get("side", "raf")
    engine.set_player_side(side)
    return jsonify(engine.get_state())
