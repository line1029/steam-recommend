import os
from flask import Flask, request, render_template, flash
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests
import config


class User:
    def __init__(self, id=0):
        self.id = id
        self.username = None
        self.profileurl = None
        self.avatar = None
        self.visibility = None
        self.avatarfull = None
        if id:
            response = requests.get(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={id}").json()
            if response is not None and "response" in response and "players" in response["response"] and response["response"]["players"]:
                userdata = response["response"]["players"][0]
                self.id = userdata["steamid"]
                self.username = userdata["personaname"]
                self.profileurl = userdata["profileurl"]
                self.avatar = userdata["avatar"]
                self.avatarmedium = userdata["avatarmedium"]
                self.avatarfull = userdata["avatarfull"]
                self.visibility = userdata["communityvisibilitystate"]
            else:
                flash("invalid query or couldn't get response")


load_dotenv()
api_key = os.environ.get("steam_web_api_token")
db = SQLAlchemy()
migrate = Migrate()

def page_not_found(e):
    return render_template('404.html'), 404


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    # ORM
    db.init_app(app)
    migrate.init_app(app, db)
    from . import models
    
    from .views import main_views, auth_views, analysis_views
    app.register_blueprint(main_views.bp)
    app.register_blueprint(analysis_views.bp)
    app.register_blueprint(auth_views.bp)

    # 오류페이지
    app.register_error_handler(404, page_not_found)

    return app


