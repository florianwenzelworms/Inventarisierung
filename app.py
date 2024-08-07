from flask import Flask, render_template, flash, redirect, url_for, request, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from datetime import datetime, timezone
from forms import LoginForm
import json
import base64

app = Flask(__name__)
app.config["SECRET_KEY"] = 'e79b9847144221ba4e85df9dd483a3e5'
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///Inventarisierung.db"
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).filter(User.id == user_id).first()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(), nullable=False)
    user = db.Column(db.String(60), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=datetime.now(timezone.utc))
    export = db.Column(db.Boolean, nullable=False, default=False)


@app.route('/', methods=["GET"])
def home():
    if current_user.is_authenticated:
        return render_template('main.html')
    else:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            flash("Eingeloggt als " + user.username + "!", "success")
            return redirect(url_for("home"))
        else:
            flash("Falsches Passwort oder Benutzername", "danger")
    return render_template("login.html", title="login", form=form)


@app.route("/logout", methods=["GET"])
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/save", methods=["POST"])
def save():
    if current_user.is_authenticated:
        if request.method == 'POST':
            content = json.loads(request.data)
            for data in content:
                if "Text" in data.keys():
                    print(data["Text"])
                else:
                    filename = "temp/"+data["code"]+".png"
                    try:
                        with open(filename, "wb") as fh:
                            # Change imagevalue to string and split the b64 coding, then decode with b64, safe to image
                            fh.write(base64.b64decode((str(data["img"]).split(",")[1].encode("ascii")), validate=True))
                    except Exception as e:
                        print(e)
            return "Success", 200
        else:
            print("no POST")
    else:
        print("no authenticated user")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
    #app.run(host='0.0.0.0', port=3000, debug=True, ssl_context="adhoc")
