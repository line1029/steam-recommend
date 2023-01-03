from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms import validators

class QueryForm(FlaskForm):
    query = StringField('query', validators=[validators.DataRequired()])