import os

BASE_DIR = os.path.dirname(__file__)

SQLALCHEMY_DATABASE_URI = 'sqlite:///{}'.format(os.path.join(BASE_DIR, 'flask_app.db'))
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = "AI_16_Fighting"