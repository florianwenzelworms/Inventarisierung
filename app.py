from flask import Flask, render_template, flash, redirect, url_for, request, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from datetime import datetime, timezone
from forms import LoginForm
import json
import base64
import ldap3

app = Flask(__name__)
app.config["SECRET_KEY"] = 'e79b9847144221ba4e85df9dd483a3e5'
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///Inventarisierung.db"
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)

# LDAP Settings
LDAP_USER = "anmelde_dom\\readad"
LDAP_PASS = "***REMOVED***"
LDAP_SERVER = "ldap://2.1.10.245"
AD_DOMAIN = "ANMELDE_DOM"
SEARCH_BASE = "CN=Users,DC=stadt,DC=worms"


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.cn = ''
        self.mail = ''
        self.department = ''
        self.groups = []


@login_manager.user_loader
def load_user(uid):
    user = User(uid)
    if user:
        user.cn, user.mail, user.department, user.groups = get_user_data(uid)
    return user


def authenticate_ldap(username, password):
    """
    Check authentication of user against AD with LDAP
    :param username: Username
    :param password: Password
    :return: True is authentication is successful, else False
    """
    server = ldap3.Server(LDAP_SERVER, use_ssl=True, get_info=ldap3.ALL)

    try:
        with ldap3.Connection(server,
                              user=f'{AD_DOMAIN}\\{username}',
                              password=password,
                              authentication=ldap3.SIMPLE,
                              check_names=True,
                              raise_exceptions=True) as conn:
            if conn.bind():
                print("Authentication successful")
                user = User(username)
                return user
    except Exception as e:
        print(f"LDAP authentication failed: {e}")
    return False


def get_user_data(username):
    server = ldap3.Server(LDAP_SERVER, use_ssl=True, get_info=ldap3.ALL)
    with ldap3.Connection(server,
                          user=LDAP_USER,
                          password=LDAP_PASS,
                          auto_bind=True) as conn:
        if conn.bind():
            if conn.search('DC=stadt,DC=worms', "(&(sAMAccountName=" + username + "))",
                               ldap3.SUBTREE,
                               attributes=['mail', 'memberOf', 'department', 'cn']):
                cn = conn.entries[0]['cn']
                mail = conn.entries[0]['mail']
                department = conn.entries[0]['department']
                groups = [group.split(',')[0].split('=')[1] for group in conn.entries[0]['memberOf']]
                return cn, mail, department, groups
    return ""


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.JSON, nullable=False)
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
        user = authenticate_ldap(form.username.data, form.password.data)
        if user:
            login_user(user, remember=True)
            flash("Eingeloggt als " + user.id + "!", "success")
            return redirect(url_for('home'))
        else:
            flash("Falsches Passwort oder Benutzername", "danger")
    return render_template("login.html", title="login", form=form)


@app.route("/logout", methods=["GET"])
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/save", methods=["POST", "PUT"])
def save():
    if current_user.is_authenticated:
        if request.method == 'POST':
            content = json.loads(request.data)
            db.session.add(Entry(data=content, user=current_user.id))
            db.session.commit()
            return "Success", 200
        elif request.method == 'PUT':
            entries = db.session.query(Entry).filter(Entry.user == current_user.id).all()
            for entry in entries:
                print(entry.id)
            return "Success", 200
        else:
            print("no POST or PUT")
    else:
        print("no authenticated user")





if __name__ == '__main__':
    # No SSL
    # app.run(host='0.0.0.0', port=3000, debug=True)

    # With SSL active, for testing purposes on iPad for ex.
    app.run(host='0.0.0.0', port=3000, debug=True, ssl_context="adhoc")



# Old part for converting base64 string to image
# for data in content:
#     if "Text" in data.keys():
#         print(data["Text"])
#     else:
#         filename = "temp/"+data["code"]+".png"
#         try:
#             with open(filename, "wb") as fh:
#                 # Change imagevalue to string and split the b64 coding, then decode with b64, safe to image
#                 fh.write(base64.b64decode((str(data["img"]).split(",")[1].encode("ascii")), validate=True))
#         except Exception as e:
#             print(e)
