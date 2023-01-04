import os
import requests
from flask import Blueprint, url_for, request, session, g
from werkzeug.utils import redirect
from pysteamsignin.steamsignin import SteamSignIn
from flask_app import api_key, User




bp = Blueprint('auth', __name__, url_prefix='/auth')



@bp.route('/')
def login():
    if g.user is None:
        steamLogin = SteamSignIn()
        # Flask expects an explicit return on the route.
        return steamLogin.RedirectUser(steamLogin.ConstructURL(f'{request.url_root}auth/processlogin'))

    return redirect(url_for("main.index"))


@bp.route('/processlogin')
def processlogin():
    returnData = request.values

    steamLogin = SteamSignIn()
    steamID = steamLogin.ValidateResults(returnData)

    # print('SteamID returned is: ', steamID)

    if steamID is not False:
        session["user_id"] = steamID
    else:
        print("login fail. something wrong?")
    return redirect(url_for("main.index"))

    # At this point, redirect the user to a friendly URL.


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = User(user_id)


@bp.route('/logout/')
def logout():
    session.clear()
    return redirect(url_for("main.index"))