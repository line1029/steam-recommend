import os
from flask import Flask, render_template, flash
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests
from config import development
import sqlite3
import joblib
import pandas as pd
from datetime import datetime

load_dotenv()
api_key = os.environ.get("steam_web_api_token")


def delete_user_data():
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_data")
        conn.commit()


# delete all user data at app start
delete_user_data()


def get_user_data_from_db(user_id: int):
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_data WHERE user_id=?", [user_id])
        userdata = cur.fetchone()
    return userdata


def check_update_time_limit(timestamp: str):
    update_date= datetime.strptime(timestamp, r'%Y-%m-%d %H:%M:%S.%f')
    date_now = datetime.now()
    diff = (date_now - update_date).total_seconds()
    if diff > 300:
        return True
    return False


def insert_user_data(userdata):
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute(f"""
        INSERT INTO user_data
        VALUES ({", ".join(["?"]*8)})
        """,
        userdata
        )
        conn.commit()


def update_user_data(userdata):
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute("""
        UPDATE user_data
        SET
            username=?,
            profileurl=?,
            avatar=?,
            avatarmedium=?,
            avatarfull=?,
            visibility=?,
            update_date=?
        WHERE user_id=?
        """,
        (*userdata[1:], userdata[0])
        )
        conn.commit()


def get_user_data_from_web(user_id):
    response = requests.get(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={user_id}").json()
    if response is not None and "response" in response and "players" in response["response"] and response["response"]["players"]:
        userdata = response["response"]["players"][0]
        return (userdata["steamid"],
                userdata["personaname"],
                userdata["profileurl"],
                userdata["avatar"],
                userdata["avatarmedium"],
                userdata["avatarfull"],
                userdata["communityvisibilitystate"],
                datetime.now())


class User:
    def __init__(self, id=0):
        self.id = id
        self.username = None
        self.profileurl = None
        self.avatar = None
        self.avatarmedium = None
        self.avatarfull = None
        self.visibility = None
        self.updatedate = None
        
        if id==0:
            return
        userdata = get_user_data_from_db(id)
        if not userdata:
            userdata = get_user_data_from_web(id)
            if not userdata:
                flash("invalid query or couldn't get response")        
            else:
                insert_user_data(userdata)
        elif check_update_time_limit(userdata[-1]):
            userdata = get_user_data_from_web(id)
            if not userdata:
                flash("couldn't get response")        
            else:
                update_user_data(userdata)
        if userdata:
            self.id, self.username, self.profileurl, self.avatar, self.avatarmedium, self.avatarfull, self.visibility, self.updatedate = userdata

    
    def get_owned_games(self):
        if self.visibility != 3:
            flash("없는 프로필이거나 프로필이 비공개 상태입니다. 다시 한번 확인해주세요.")
            return
        url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        params = {
            "key":api_key,
            "steamid":self.id,
            "include_played_free_games":True
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            flash("요청 실패. 서버 에러거나 호스트의 API 키가 차단되었습니다. 잠시 후 다시 시도해주세요.")
            return
        data = response.json()["response"]
        if not data:
            flash("아무 게임도 없거나 세부 정보가 공개되어있지 않습니다. 세부 정보를 공개상태로 바꿔주세요.")
            return
        return data
                







def select_all_candidate_vector():
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM game_genre_vector g")
        data = cur.fetchall()
    return pd.DataFrame(data).set_index(0)


def select_all_candidate_games():
    with sqlite3.connect('flask_app.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM game g")
        data = cur.fetchall()
        cur.execute("PRAGMA table_info(game);")
        cols = [i[1] for i in cur.fetchall()]
    return pd.DataFrame(data, columns=cols).set_index(cols[0])


candidate_games = select_all_candidate_games()
candidate_vector = select_all_candidate_vector()
id_to_tag = joblib.load("id_to_tag.pkl")
tag_to_id = joblib.load("tag_to_id.pkl")



db = SQLAlchemy()
migrate = Migrate()

def page_not_found(e):
    return render_template('404.html'), 404


def create_app():
    app = Flask(__name__)
    app.config.from_object(development)

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


