from flask import Flask


def create_app():
    app = Flask(__name__)
    app.secret_key = "battle-of-britain-1940"

    from app.routes import bp
    app.register_blueprint(bp)

    return app
