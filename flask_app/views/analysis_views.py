import numpy as np
import pandas as pd
import re
import requests
from urllib.parse import urlparse
import sqlite3
from sklearn.metrics.pairwise import cosine_similarity
from flask import Blueprint, url_for, render_template, request, flash, g
from werkzeug.utils import redirect
from flask_app import api_key, User, candidate_games, candidate_vector, tag_to_id, get_user_data_from_web
from flask_app.forms import QueryForm, UserForm
from datetime import datetime




bp = Blueprint('analysis', __name__, url_prefix='/analysis')



def is_valid_url(url):
    truth_value = url.startswith("https://steamcommunity.com/") and \
        (urlparse(url).path.startswith("/profile") or \
        urlparse(url).path.startswith("/id"))
    return truth_value


def is_valid_query(query):
    if re.search("[:/?]", query):
        return False
    return True


def transform_custumurl_to_steam_id_64(custumurl):
    url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={api_key}&vanityurl={custumurl}"
    response = requests.get(url)
    if response.status_code != 200:
        flash("요청 실패. 서버 에러거나 호스트의 API 키가 차단되었습니다. 잠시 후 다시 시도해주세요.")
        return 0
    data = response.json()
    if data["response"]["success"] != 1:
        flash("잘못된 custumurl입니다. 다시 한번 확인해주세요.")
        return 0
    return data["response"]["steamid"]


def get_steam_id_64_from_url(url):
    path = urlparse(url).path
    if path.startswith("/profile"):
        return path[10:].replace("/", "")
    else:
        custumurl = path[4:].replace("/", "")
        return transform_custumurl_to_steam_id_64(custumurl)


def get_user_id_from_query(query: str) -> str:
    if is_valid_url(query):
        user_id = get_steam_id_64_from_url(query)
    else:
        if is_valid_query(query) is False:
            flash("invalid query")
            return 0
        if query.isdigit() is False:
            user_id = transform_custumurl_to_steam_id_64(query)
        else:
            userdata = get_user_data_from_web(query)
            if userdata:
                user_id = userdata[0]
            else:
                user_id = transform_custumurl_to_steam_id_64(query)
    return user_id





def get_feature_vector_from_web(appid: int) -> 'np.ndarray[np.bool]':
    url = f"http://steamspy.com/api.php?request=appdetails&appid={appid}"
    response = requests.get(url)
    if response.status_code == 200 and response.json() is not None:
        tags = response.json().get("tags")
        genres = response.json().get("genre")
        tag_ids = []
        if tags is not None:
            for tag in tags:
                if tag in tag_to_id:
                    tag_ids.append(tag_to_id[tag])
        if type(genres) == str and genres:
            genres = [i.strip() for i in genres.split(",")]
            for genre in genres:
                if genre in tag_to_id:
                    tag_ids.append(tag_to_id[genre])
        tag_ids = list(set(tag_ids))
        arr = np.array([1 if i in tag_ids else 0 for i in range(1, 340)])
        return arr


def get_feature_vector_from_db(appid):
    with sqlite3.connect("flask_app.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM game_genre_vector_all g WHERE g.appid=?", [int(appid)])
        arr = cur.fetchone()
    if arr:
        return np.array(arr[1:])


def insert_vector(arr):
    with sqlite3.connect('flask_app.db') as conn:
        arr = list(map(int, arr))
        cur = conn.cursor()
        l = ",".join(["?"]*340)
        cur.execute(f"INSERT OR IGNORE INTO game_genre_vector_all VALUES ({l})", arr)
        conn.commit()


def find_sim_game(appid: int, mask: 'np.ndarray[np.bool]', top_n=10, base="weighted_rating"):
    candidate_vector_user = candidate_vector[~mask]
    candidate_games_user = candidate_games[~mask]
    vector = get_feature_vector_from_db(appid)
    if vector is None:
        print("새 vector 추가", appid)
        vector = get_feature_vector_from_web(appid)
        if all(vector == np.zeros_like(vector)):
            return []
        insert_vector([appid, *vector])
    vector = vector.reshape(1, -1)
    tag_sim_idxs= cosine_similarity(vector, candidate_vector_user).argsort().reshape(-1)[::-1]
    similar_games = candidate_games_user.iloc[tag_sim_idxs][:top_n*3].sort_values(by=base, ascending=False)

    return similar_games[:top_n].index


def get_recommend_result(game_count: int, games: 'list[(int, int, int)]') -> dict:
    games_index_mask = candidate_vector.index.isin([i[0] for i in games])
    played_games = [i for i in games if i[1]]
    played_game_count = len(played_games)
    played_games_by_playtime = [i[0] for i in sorted(played_games, key=lambda x: -x[1])][:20]
    played_games_by_recent = [i[0] for i in sorted(played_games, key=lambda x: -x[2])][:20]
    if played_game_count >= 5:
        X_playtime = np.random.choice(played_games_by_playtime, 5, replace=False)
        X_recent = np.random.choice(played_games_by_recent, 5, replace=False)
    elif game_count < 5:
        X_playtime = [i[0] for i in games]
        X_recent = X_playtime.copy()
    else:
        cnt = 5 - played_game_count
        if game_count - played_game_count >= cnt * 2:
            tmp1 = np.random.choice([i[0] for i in games if not i[1]], cnt*2, replace=False)
            X_playtime = [*played_games_by_playtime, *tmp1[:cnt]]
            X_recent = [*played_games_by_recent, *tmp1[cnt:]]
        else:
            X_playtime = np.random.choice(games, 5, False)
            X_recent = np.random.choice(games, 5, False)
    
    y_playtime_rating = []
    y_playtime_ccu = []
    for appid in X_playtime:
        y_playtime_rating.extend(find_sim_game(appid, games_index_mask))
        y_playtime_ccu.extend(find_sim_game(appid, games_index_mask, base="ccu"))
    y_playtime_rating = list(set(y_playtime_rating))
    y_playtime_ccu = list(set(y_playtime_ccu))
    y_playtime_rating = np.random.choice(y_playtime_rating, 6, False)
    y_playtime_ccu = np.random.choice(y_playtime_ccu, 6, False)

    y_recent_rating = []
    y_recent_ccu = []
    for appid in X_recent:
        y_recent_rating.extend(find_sim_game(appid, games_index_mask))
        y_recent_ccu.extend(find_sim_game(appid, games_index_mask, base="ccu"))
    y_recent_rating = list(set(y_recent_rating))
    y_recent_ccu = list(set(y_recent_ccu))
    y_recent_rating = np.random.choice(y_recent_rating, 6, False)
    y_recent_ccu = np.random.choice(y_recent_ccu, 6, False)

    recommend_result = {
        "y_playtime_rating":list(map(int, y_playtime_rating)),
        "y_playtime_ccu":list(map(int, y_playtime_ccu)),
        "y_recent_rating":list(map(int, y_recent_rating)),
        "y_recent_ccu":list(map(int, y_recent_ccu))
    }
    return recommend_result


def check_update_time_limit(user: User):
    date_now = datetime.now()
    with sqlite3.connect("flask_app.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT update_date from user_vector_data where user_id=?;", [user.id])
        update_date = cur.fetchone()[0]
    if not update_date:
        return 2
    update_date= datetime.strptime(update_date, r'%Y-%m-%d %H:%M:%S.%f')
    diff = (date_now - update_date).total_seconds()
    if diff > 3600:
        return 1
    return 0
    
    


def store_user_vector_data(user: User, data: dict):
    checked = check_update_time_limit(user)
    if not checked:
        flash("새로고침은 1시간에 한번씩만 가능합니다.")
        return
    game_count = data["game_count"]
    games = data["games"]
    played_game_count = sum([1 for i in games if i["playtime_forever"]])
    appids = [i["appid"] for i in games]
    playtimes = [i["playtime_forever"] for i in games]
    playtimes = dict((i["appid"],i["playtime_forever"]) for i in games)
    total_playtime = sum(playtimes.values())
    with sqlite3.connect("flask_app.db") as conn:
        cur = conn.cursor()
        l = str(tuple(appids))
        cur.execute(f"select * from game_genre_vector_all where appid in {l}")
        vector = cur.fetchall()
        diff = set(appids).difference(set(i[0] for i in vector))
        for appid_diff in diff:
            vv = get_feature_vector_from_web(appid_diff)
            if not all(vv == np.zeros_like(vv)):
                vv = [appid_diff, *vv]
                insert_vector(vv)
                vector.append(vv)
                diff.discard(appid_diff)
    total_vector = pd.DataFrame(vector).set_index(0)
    total_vector_bycount = total_vector.sum()
    total_vector_bycount_string = ";".join(total_vector_bycount.astype(str))
    recent_games = [i for i in data["games"] if "playtime_2weeks" in i]
    recent_appids = [i["appid"] for i in recent_games]
    recent_playtimes = dict((i["appid"],i["playtime_2weeks"]) for i in recent_games)
    recent_playtime = sum(recent_playtimes.values())
    recent_vector = total_vector.loc[recent_appids].copy()
    recent_vector_bycount = recent_vector.sum()
    recent_vector_bycount_string = ";".join(recent_vector_bycount.astype(str))
    for idx in playtimes:
        if idx in diff:
            continue
        total_vector.loc[idx] *= playtimes[idx]
    for idx in recent_playtimes:
        if idx in diff:
            continue
        recent_vector.loc[idx] *= playtimes[idx]
    total_vector_bytime = total_vector.sum()
    total_vector_bytime_string = ";".join(total_vector_bytime.astype(str))
    recent_vector_bytime = recent_vector.sum()
    recent_vector_bytime_string = ";".join(recent_vector_bytime.astype(str))
    update_date = datetime.now()
    cols = [
        user.id,
        game_count,
        played_game_count,
        total_playtime,
        recent_playtime,
        total_vector_bycount_string,
        total_vector_bytime_string,
        recent_vector_bycount_string,
        recent_vector_bytime_string,
        update_date
    ]
    with sqlite3.connect("flask_app.db") as conn:
        cur = conn.cursor()
        if checked == 1:
            cols = [*cols[1:], cols[0]]
            cur.execute(
                """
                UPDATE user_vector_data
                SET
                    game_count=?,
                    played_game_count=?,
                    total_playtime=?,
                    recent_playtime=?,
                    total_vector_bycount=?,
                    total_vector_bytime=?,
                    recent_vector_bycount=?,
                    recent_vector_bytime=?,
                    update_date=?
                WHERE user_id=?
                """,
                cols
            )
        elif checked == 0:
            cur.execute(
                f"""
                INSERT INTO user_vector_data
                VALUES ({",".join(["?"]*len(cols))})
                """,
                cols
            )
        conn.commit()


    


@bp.route('/')
def main():
    query_form = QueryForm()
    user_form = UserForm()
    image_appid = np.random.choice(candidate_games.index, 1)[0]
    return render_template('analysis/analysis_form.html', query_form=query_form, user_form=user_form, image_appid=image_appid)



@bp.route('/query', methods=('POST',))
def query():
    query_form = QueryForm()
    user_form = UserForm()
    image_appid = np.random.choice(candidate_games.index, 1)[0]
    if request.method == 'POST' and query_form.validate_on_submit():
        query = query_form.query.data
        user = User(get_user_id_from_query(query))
        if user.username == None:
            return redirect(url_for('analysis.main'))
        data = user.get_owned_games()
        if data == None:
            return redirect(url_for('analysis.main'))
        game_count = data["game_count"]
        if not game_count:
            flash("게임이 없습니다! 분석이 불가능합니다.")
            return redirect(url_for('analysis.main'))
        return redirect(url_for('analysis.result', user_id=user.id))
    return render_template('analysis/analysis_form.html', query_form=query_form, user_form=user_form, image_appid=image_appid)


@bp.route('/user', methods=('POST',))
def user():
    query_form = QueryForm()
    user_form = UserForm()
    image_appid = np.random.choice(candidate_games.index, 1)[0]
    if request.method == 'POST' and user_form.validate_on_submit():
        user: User = g.user
        if user.username == None:
            return redirect(url_for('analysis.main'))
        data = user.get_owned_games()
        if data == None:
            return redirect(url_for('analysis.main'))
        game_count = data["game_count"]
        if not game_count:
            flash("게임이 없습니다! 분석이 불가능합니다.")
            return redirect(url_for('analysis.main'))   
        return redirect(url_for('analysis.result', user_id=user.id))
    return render_template('analysis/analysis_form.html', query_form=query_form, user_form=user_form, image_appid=image_appid)


@bp.route('/result', methods=('GET', 'POST'))
def result():
    user_id = request.args.get("user_id")
    # if not user_id:
    #     return redirect(url_for('analysis.main'))
    user = User(user_id)
    if user.username == None:
        return redirect(url_for('analysis.main'))
    data = user.get_owned_games()
    if data == None:
        return redirect(url_for('analysis.main'))
    game_count = data["game_count"]
    if not game_count:
        flash("게임이 없습니다! 분석이 불가능합니다.")
        return redirect(url_for('analysis.main'))   
    games = [(game["appid"], game["playtime_forever"], game["rtime_last_played"]) for game in data["games"]]
    result = get_recommend_result(game_count, games)
    total_playtime = sum(i[1] for i in games)
    last_epoch_time = max(i[2] for i in games)
    last_played_date = datetime.fromtimestamp(last_epoch_time)
    
    return render_template("analysis/analysis_result.html",
        result=result,
        user=user,
        games=games,
        total_playtime=total_playtime,
        last_played_date=last_played_date,
        game_count=game_count)