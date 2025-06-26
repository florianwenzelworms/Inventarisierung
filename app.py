from flask import Flask, render_template, flash, redirect, url_for, request, send_file, make_response, jsonify
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from flask_mail import Mail
from forms import LoginForm
import ldap3
from credentials import *
from sqlalchemy.orm.attributes import flag_modified
import topdesk
import json
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
login_manager = LoginManager(app)

mail_settings = {
    "MAIL_SERVER": MAIL_SERVER,
    "MAIL_PORT": MAIL_PORT,
    "MAIL_USE_TLS": MAIL_USE_TLS,
    "MAIL_USE_SSL": MAIL_USE_SSL,
    "MAIL_USERNAME": MAIL_USERNAME,
    "MAIL_PASSWORD": MAIL_PASSWORD
}
app.config.update(mail_settings)
mail = Mail(app)

# LDAP Settings
LDAP_USER = LDAP_USER
LDAP_PASS = LDAP_PASS
LDAP_SERVER = LDAP_SERVER
AD_DOMAIN = AD_DOMAIN
SEARCH_BASE = SEARCH_BASE


# --- Neue Konfiguration für die QR-Code-Erstellung ---
# Definiert den Ordner, in dem die Bilder gespeichert werden (innerhalb von 'static')
QR_CODE_OUTPUT_DIR = os.path.join(app.static_folder, 'raumschilder')
# Pfad zur Logo-Datei (muss in static/logo.png liegen)
LOGO_FILE = os.path.join(app.static_folder, 'logo.png')
# Pfad zur Schriftart (muss im Projekt-Hauptverzeichnis liegen oder System-Pfad sein)
FONT_FILE = "arial.ttf"


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
                # JETZT die zusätzlichen Daten abrufen und dem Objekt hinzufügen
                try:
                    # get_user_data gibt ein Tupel zurück
                    user_details = get_user_data(username)
                    if user_details:
                        user.cn, user.mail, user.department, user.groups = user_details
                        print(f"User data loaded for {username}: Groups - {user.groups}")
                        return user
                    else:
                        # Falls aus irgendeinem Grund keine Daten gefunden wurden
                        print(f"Authentication successful, but could not retrieve data for {username}")
                        return False
                except Exception as e:
                    print(f"Error retrieving user data: {e}")
                    return False
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


@app.route('/', methods=["GET"])
def home():
    if current_user.is_authenticated:
        return render_template('main.html')
    else:
        return redirect(url_for("login"))


@app.route('/inv', methods=["GET"])
def inv():
    if current_user.is_authenticated:
        return render_template('inv.html')
    else:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_ldap(form.username.data, form.password.data)
        if user and "1.05" in user.groups:
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


@app.route('/direct_import', methods=['POST'])
def direct_import():
    # 1. Sicherstellen, dass der Benutzer eingeloggt ist
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    # 2. Daten direkt vom Frontend empfangen
    data_from_frontend = request.get_json()
    if not data_from_frontend:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    # Listen für ein detailliertes Feedback
    report = {
        'successful': [],
        'not_found': [],
        'errors': []
    }

    try:
        # 3. Raum und Geräte-Codes direkt aus den empfangenen Daten extrahieren
        text_item = next((item for item in data_from_frontend if 'Text' in item), None)
        room = text_item['Text'] if text_item else "N/A"
        device_codes = [item['code'] for item in data_from_frontend if 'code' in item]

        # 4. TopDesk-Logik für jeden Code ausführen (genau wie vorher)
        for code_id in device_codes:
            try:
                asset = topdesk.getAsset(code_id)
                new_room_location = topdesk.getLocation(room)

                if not asset:
                    report['not_found'].append(f"Asset mit Code '{code_id}'")
                    continue
                if not new_room_location:
                    report['not_found'].append(f"Raum '{room}'")
                    # Wenn der Raum nicht existiert, brechen wir für alle Geräte ab
                    # Da sie nicht zugewiesen werden können.
                    raise Exception(f"Raum '{room}' nicht in TopDesk gefunden.")

                current_assignments = topdesk.getAssignments(asset)
                is_already_in_correct_room = any(
                    loc.get('location', {}).get('id') == new_room_location.get('id')
                    for loc in current_assignments.get('locations', [])
                )

                if is_already_in_correct_room:
                    report['successful'].append(f"Asset {code_id} war bereits in Raum {room}.")
                else:
                    if current_assignments.get('locations'):
                        old_room_id = current_assignments['locations'][0]['location']['id']
                        topdesk.unlinkAssignments(old_room_id, asset)
                    topdesk.addAssignments(asset, new_room_location['branch']['id'], new_room_location['id'])
                    report['successful'].append(f"Asset {code_id} wurde zu Raum {room} verschoben.")

            except Exception as api_error:
                report['errors'].append(f"Fehler bei Code {code_id}: {str(api_error)}")

        # 5. Detailliertes Ergebnis an das Frontend zurückgeben
        return jsonify({
            'success': True,
            'message': 'Verarbeitung abgeschlossen.',
            'report': report
        }), 200

    except Exception as e:
        # Fängt allgemeine Fehler ab (z.B. wenn der Raum nicht gefunden wurde)
        return jsonify({'success': False, 'message': str(e)}), 500


# --- Angepasste Route für die Anzeige der Raumliste ---
@app.route('/raumschilder')
def raumschilder():
    # 1. Sicherstellen, dass überhaupt ein Benutzer eingeloggt ist
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    # 2. Spezifisch prüfen, ob der eingeloggte Benutzer "wenzelf" ist
    if current_user.id != 'wenzelf':
        flash("Sie haben keine Berechtigung, auf diese Seite zuzugreifen.", "danger")
        return redirect(url_for('home'))

    # Sicherstellen, dass der Ausgabeordner existiert
    os.makedirs(QR_CODE_OUTPUT_DIR, exist_ok=True)

    try:
        # 3. Daten von TopDesk abrufen
        all_rooms = topdesk.getAllRooms()

        # 4. Daten anreichern: Prüfen, ob für jeden Raum bereits ein QR-Bild existiert
        for room in all_rooms:
            # Erzeugt einen für Dateisysteme sicheren Namen
            safe_filename = "".join(c for c in room.get('name', 'unbekannt') if c.isalnum() or c in (' ', '_')).rstrip()
            filename = f"{safe_filename}.png"
            filepath = os.path.join(QR_CODE_OUTPUT_DIR, filename)
            room['qr_exists'] = os.path.exists(filepath)
            room['filename'] = filename  # Dateiname wird für die Generierung benötigt

        # 5. Die angereicherten Daten an das Template übergeben
        return render_template('raumschilder.html', title='Raumschilder', rooms=all_rooms)

    except Exception as e:
        flash(f"Fehler beim Laden der Raumdaten von TopDesk: {e}", "danger")
        return render_template('raumschilder.html', title='Raumschilder', rooms=[])


# --- Neue Route zur Generierung der QR-Code-Bilder ---
@app.route('/generate_qr_codes', methods=['POST'])
def generate_qr_codes():
    if not current_user.is_authenticated or current_user.id != 'wenzelf':
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    rooms_to_process = request.get_json()
    if not rooms_to_process:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    generated_files = []
    errors = []

    # --- Ihre Skript-Logik, integriert in die Route ---
    # Konfiguration (Größe, Farben etc.)
    IMG_WIDTH, IMG_HEIGHT = 1240, 1754
    BACKGROUND_COLOR = "white"
    QR_CODE_BOX_SIZE = 15

    # Schriftarten laden
    try:
        font_large = ImageFont.truetype(FONT_FILE, 60)
        font_small = ImageFont.truetype(FONT_FILE, 40)
    except IOError:
        font_large, font_small = ImageFont.load_default(), ImageFont.load_default()
        errors.append("Warnung: arial.ttf nicht gefunden, Standard-Schriftart wird verwendet.")

    # Logo laden
    try:
        logo_img = Image.open(LOGO_FILE).convert("RGBA")
        w_percent = (200 / float(logo_img.size[0]))
        h_size = int((float(logo_img.size[1]) * float(w_percent)))
        logo_img = logo_img.resize((200, h_size), Image.LANCZOS)
    except FileNotFoundError:
        logo_img = None
        errors.append(f"Warnung: Logo-Datei '{LOGO_FILE}' nicht gefunden.")

    # Verarbeitung der übergebenen Räume
    for room in rooms_to_process:
        try:
            # Das gesamte JSON-Objekt wird in den QR-Code kodiert
            json_string = json.dumps(room, indent=4, ensure_ascii=False)

            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=QR_CODE_BOX_SIZE,
                               border=2)
            qr.add_data(json_string)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            # Bild-Leinwand erstellen
            schild_img = Image.new('RGB', (IMG_WIDTH, IMG_HEIGHT), BACKGROUND_COLOR)

            # QR-Code und Logo positionieren und einfügen
            qr_x, qr_y = (IMG_WIDTH - qr_img.size[0]) // 2, 200
            schild_img.paste(qr_img, (qr_x, qr_y))
            if logo_img:
                schild_img.paste(logo_img, (IMG_WIDTH - logo_img.width - 50, 50), logo_img)

            # Text erstellen und zentriert einfügen
            draw = ImageDraw.Draw(schild_img)

            label1_text = room.get("name", "Kein Name")
            text_bbox1 = draw.textbbox((0, 0), label1_text, font=font_large)
            text_x1 = (IMG_WIDTH - (text_bbox1[2] - text_bbox1[0])) // 2
            text_y1 = qr_y + qr_img.size[1] + 150
            draw.text((text_x1, text_y1), label1_text, fill="black", font=font_large)

            label2_text = room.get("branch", {}).get("name", "Keine Zweigstelle")
            text_bbox2 = draw.textbbox((0, 0), label2_text, font=font_small)
            text_x2 = (IMG_WIDTH - (text_bbox2[2] - text_bbox2[0])) // 2
            text_y2 = text_y1 + 100
            draw.text((text_x2, text_y2), label2_text, fill="black", font=font_small)

            # Bild speichern
            output_filename = os.path.join(QR_CODE_OUTPUT_DIR, room['filename'])
            schild_img.save(output_filename)

            generated_files.append(room.get('name'))
        except Exception as e:
            errors.append(f"Fehler bei '{room.get('name')}': {str(e)}")

    # Feedback an das Frontend senden
    if errors and not generated_files:
        return jsonify({'success': False, 'message': 'QR-Codes konnten nicht erstellt werden.', 'errors': errors})

    return jsonify({
        'success': True,
        'message': f'{len(generated_files)} von {len(rooms_to_process)} QR-Codes erfolgreich erstellt.',
        'errors': errors
    })


@app.route('/get_assets_for_room')
def get_assets_for_room():
    # 1. Sicherstellen, dass der Benutzer eingeloggt ist
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    # 2. Den Raumnamen aus der Anfrage holen
    room_name = request.args.get('room')
    if not room_name:
        return jsonify({'success': False, 'message': 'Kein Raumname angegeben'}), 400

    try:
        # 3. Zuerst die ID des Raumes anhand des Namens von TopDesk holen
        location_details = topdesk.getLocation(room_name)
        if not location_details or 'id' not in location_details:
            return jsonify({'success': False, 'message': f'Raum "{room_name}" nicht in TopDesk gefunden.'}), 404

        location_id = location_details['id']

        # 4. Mit der Raum-ID alle zugehörigen Assets abrufen
        assets_in_room = topdesk.getLocationAssets(location_id)

        # 5. Die gefundene Asset-Liste als JSON an das Frontend zurückgeben
        return jsonify({'success': True, 'assets': assets_in_room})

    except Exception as e:
        # Fängt Fehler bei der Kommunikation mit der TopDesk-API ab
        error_message = f"Fehler bei der Abfrage von TopDesk: {e}"
        print(error_message)
        return jsonify({'success': False, 'message': error_message}), 500


@app.route('/test', methods=["GET"])
def test():
    return render_template('test.html')


if __name__ == '__main__':
    # No SSL
    app.run(host='0.0.0.0', port=3000, debug=True)

    # With SSL active, for testing purposes on iPad for ex.
    # app.run(host='0.0.0.0', port=3000, debug=True, ssl_context="adhoc")
