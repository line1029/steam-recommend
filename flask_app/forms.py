from flask_wtf import FlaskForm
from wtforms import StringField, HiddenField
from wtforms import validators

class QueryForm(FlaskForm):
    query = StringField('query', validators=[validators.DataRequired()])

class UserForm(FlaskForm):
    user_query = HiddenField('user_query', validators=[validators.DataRequired()])