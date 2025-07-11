from flask import Flask, render_template, flash, redirect, url_for, request, send_file, make_response, jsonify
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from flask_mail import Mail, Message
from forms import LoginForm
import ldap3
from credentials import *
import topdesk
import json
import os
import io
import csv
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
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    data_from_frontend = request.get_json()
    if not data_from_frontend:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    room_item = next((item for item in data_from_frontend if 'Text' in item), None)
    scanned_items = [item['code'] for item in data_from_frontend if 'code' in item]
    missing_items_payload = next((item for item in data_from_frontend if 'missingAssetIds' in item), None)

    room_name = room_item['Text'] if room_item else None
    missing_asset_uuids = missing_items_payload['missingAssetIds'] if missing_items_payload else []

    if not room_name:
        flash("Import fehlgeschlagen: Kein Raum angegeben.", "danger")
        return jsonify({'success': False, 'redirect_url': url_for('home')})

    # Der Report wird jetzt verwendet, um die Asset-Codes/IDs zu sammeln
    report = {'successful': [], 'removed': [], 'errors': [], 'info': []}

    try:
        location_details = topdesk.getLocation(room_name)
        if not location_details:
            raise Exception(f"Ziel-Raum '{room_name}' nicht in TopDesk gefunden.")

        new_location_id = location_details['id']
        new_branch_id = location_details['branch']['id']

        # VERARBEITUNG: FEHLENDE ASSETS ENTFERNEN
        if missing_asset_uuids:
            try:
                success = topdesk.unlinkAssignments(new_location_id, missing_asset_uuids)
                if success:
                    # Speichert die Liste der entfernten UUIDs für den Report
                    report['removed'] = missing_asset_uuids
                else:
                    report['errors'].append("Ein Fehler ist beim gebündelten Entfernen der Assets aufgetreten.")
            except Exception as e:
                report['errors'].append(f"Fehler bei der gebündelten Entfernung: {str(e)}")

        # VERARBEITUNG: GESCANnte ASSETS AKTUALISIEREN
        for code in scanned_items:
            try:
                asset_uuid = topdesk.getAsset(code)
                if not asset_uuid:
                    report['errors'].append(f"Asset '{code}' nicht gefunden. E-Mail-Benachrichtigung wird versendet.")
                    try:
                        recipient_email = str(current_user.mail[0]) if current_user.mail and len(
                            current_user.mail) > 0 else None
                        if not recipient_email:
                            raise Exception("E-Mail-Adresse des Benutzers konnte nicht ermittelt werden.")
                        msg = Message(subject="Neues Asset zur Anlage in TopDesk", sender='florian.wenzel@worms.de',
                                      recipients=[recipient_email])
                        msg.body = f"Hallo {current_user.id},\n\nein neues, bisher unbekanntes Asset wurde im folgenden Raum gescannt und muss in TopDesk angelegt werden:\n\nRaum: {room_name}\nAsset-Code: {code}\n\nBitte legen Sie dieses Asset in TopDesk an.\n\nMit freundlichen Grüßen,\nIhre Inventar-App"
                        mail.send(msg)
                    except Exception as e:
                        report['errors'].append(
                            f"E-Mail-Benachrichtigung für Asset '{code}' konnte nicht gesendet werden: {e}")
                    continue

                current_assignments = topdesk.getAssignments(asset_uuid)
                current_locations = current_assignments.get('locations', [])
                is_correctly_placed = any(
                    loc.get('location', {}).get('id') == new_location_id for loc in current_locations)

                if is_correctly_placed:
                    # Speichert den Code des Assets für den Report
                    report['info'].append(code)
                else:
                    if current_locations:
                        old_location_id = current_locations[0]['location']['id']
                        topdesk.unlinkAssignments(old_location_id, [asset_uuid])
                    topdesk.addAssignments(asset_uuid, new_branch_id, new_location_id)
                    # Speichert den Code des Assets für den Report
                    report['successful'].append(code)

            except Exception as e:
                report['errors'].append(f"Fehler bei der Aktualisierung von Asset '{code}': {str(e)}")

        # --- GEÄNDERT: Flash-Nachrichten werden hier am Ende mit den Asset-Listen erstellt ---
        if report['successful']:
            asset_list = ", ".join(report['successful'])
            flash(f"Erfolgreich aktualisiert/verschoben ({len(report['successful'])}): {asset_list}", "success")

        if report['removed']:
            # NEU: Namen der entfernten Assets für die Meldung abrufen
            removed_names = []
            for uuid in report['removed']:
                try:
                    # Diese Funktion holt die Details eines Assets anhand der UUID
                    asset_details = topdesk.getAssetInfo(uuid)
                    # Wir verwenden den Asset-Namen (die ID), falls verfügbar
                    if asset_details and asset_details.get('name'):
                        removed_names.append(asset_details.get('name'))
                    else:
                        # Fallback, falls die Details nicht abgerufen werden können
                        removed_names.append(f"Unbekanntes Asset (UUID: ...{uuid[-6:]})")
                except Exception:
                    removed_names.append(f"Unbekanntes Asset (UUID: ...{uuid[-6:]})")

            asset_list = ", ".join(removed_names)
            flash(f"{len(report['removed'])} fehlende Assets wurden erfolgreich aus dem Raum entfernt: {asset_list}",
                  "warning")

        if report['info']:
            asset_list = ", ".join(report['info'])
            flash(f"Bereits korrekt zugeordnet ({len(report['info'])}): {asset_list}", "info")

        if report['errors']:
            error_details = " | ".join(report['errors'])
            flash(f"{len(report['errors'])} Fehler sind aufgetreten: {error_details}", "danger")

        return jsonify({'success': True, 'redirect_url': url_for('home')})

    except Exception as e:
        flash(f"Ein schwerwiegender Fehler ist aufgetreten: {e}", "danger")
        return jsonify({'success': False, 'redirect_url': url_for('home')})


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


@app.route('/generate_qr_codes', methods=['POST'])
def generate_qr_codes():
    if not current_user.is_authenticated or current_user.id != 'wenzelf':
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    rooms_to_process = request.get_json()
    if not rooms_to_process:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    generated_files = []
    errors = []

    # --- Konfiguration ---
    BACKGROUND_COLOR = "white"
    PADDING = 60  # Rand zwischen Inhalt und Rahmen
    FRAME_WIDTH = 8  # Dicke des Rahmens
    QR_CODE_BOX_SIZE = 12
    V_SPACING_1 = 60  # Abstand zwischen QR-Code und erstem Text
    V_SPACING_2 = 30  # Abstand zwischen den Texten

    # Schriftarten laden
    try:
        font_large = ImageFont.truetype(FONT_FILE, 70)
        font_small = ImageFont.truetype(FONT_FILE, 50)
    except IOError:
        font_large, font_small = ImageFont.load_default(), ImageFont.load_default()
        errors.append("Warnung: arial.ttf nicht gefunden, Standard-Schriftart wird verwendet.")

    # Logo laden
    try:
        logo_img_master = Image.open(LOGO_FILE).convert("RGBA")
    except FileNotFoundError:
        logo_img_master = None
        errors.append(f"Warnung: Logo-Datei '{LOGO_FILE}' nicht gefunden.")

    # Verarbeitung der übergebenen Räume
    for room in rooms_to_process:
        try:
            qr_data_string = room.get("id", "")
            if not qr_data_string:
                errors.append(f"Fehler bei '{room.get('name')}': Keine ID im Raum-Objekt gefunden.")
                continue

            # 1. QR-Code generieren
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=QR_CODE_BOX_SIZE, border=2)
            qr.add_data(qr_data_string)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

            # Logo einfügen
            if logo_img_master:
                logo_img = logo_img_master.copy()
                logo_max_size = qr_img.size[0] // 4
                logo_img.thumbnail((logo_max_size, logo_max_size), Image.LANCZOS)
                logo_pos = ((qr_img.width - logo_img.width) // 2, (qr_img.height - logo_img.height) // 2)
                logo_bg = Image.new("RGBA", (logo_img.width + 20, logo_img.height + 20), "white")
                qr_img.paste(logo_bg, (logo_pos[0] - 10, logo_pos[1] - 10))
                qr_img.paste(logo_img, logo_pos, logo_img)

            # 2. Textgrößen messen
            draw_temp = ImageDraw.Draw(Image.new('RGB', (1, 1)))
            label1_text = room.get("name", "Kein Name")
            label2_text = room.get("branch", {}).get("name", "Keine Zweigstelle")

            bbox1 = draw_temp.textbbox((0, 0), label1_text, font=font_large)
            bbox2 = draw_temp.textbbox((0, 0), label2_text, font=font_small)
            text_width1, text_height1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
            text_width2, text_height2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

            # 3. Gesamtgröße des Inhalts berechnen
            content_width = max(qr_img.width, text_width1, text_width2)
            content_height = qr_img.height + V_SPACING_1 + text_height1 + V_SPACING_2 + text_height2

            # 4. Finale Bildgröße basierend auf Inhalt und Rändern berechnen
            final_width = content_width + 2 * PADDING
            final_height = content_height + 2 * PADDING

            # 5. Finale Leinwand erstellen
            schild_img = Image.new('RGB', (final_width, final_height), BACKGROUND_COLOR)
            draw = ImageDraw.Draw(schild_img)

            # 6. Elemente zentriert auf der Leinwand platzieren
            qr_x = (final_width - qr_img.width) // 2
            qr_y = PADDING
            schild_img.paste(qr_img.convert("RGB"), (qr_x, qr_y))

            text_x1 = (final_width - text_width1) // 2
            text_y1 = qr_y + qr_img.height + V_SPACING_1
            draw.text((text_x1, text_y1), label1_text, fill="black", font=font_large)

            text_x2 = (final_width - text_width2) // 2
            text_y2 = text_y1 + text_height1 + V_SPACING_2
            draw.text((text_x2, text_y2), label2_text, fill="black", font=font_small)

            # 7. Schneidrahmen um das gesamte Bild zeichnen
            draw.rectangle((0, 0, final_width - 1, final_height - 1), outline="black", width=FRAME_WIDTH)

            # 8. Bild speichern
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

    # 2. Den 'room'-Parameter aus der URL lesen (z.B. ?room=Raumname)
    room_name = request.args.get('room')
    if not room_name:
        return jsonify({'success': False, 'message': 'Kein Raumname in der Anfrage gefunden.'}), 400

    print(f"Anfrage für Assets in Raum erhalten: '{room_name}'")

    try:
        # 3. Zuerst die ID des Raumes anhand des Namens von TopDesk holen
        # Hier wird die Original-Funktion aus Ihrer topdesk.py aufgerufen
        location_details = topdesk.getLocation(room_name)
        # 4. Prüfen, ob der Raum gefunden wurde
        if not location_details or 'id' not in location_details:
            print(f"Raum '{room_name}' nicht in TopDesk gefunden.")
            return jsonify({'success': False, 'message': f'Raum "{room_name}" nicht in TopDesk gefunden.'}), 404

        location_id = location_details['id']
        print(f"Raum-ID für '{room_name}' ist: {location_id}")

        # 5. Mit der Raum-ID alle zugehörigen Assets abrufen
        # Hier wird die Original-Funktion aus Ihrer topdesk.py aufgerufen
        assets_in_room = topdesk.getLocationAssets(location_id)
        print(assets_in_room)
        # 6. Die gefundene Asset-Liste als JSON an das Frontend zurückgeben
        print(f"{len(assets_in_room)} Assets gefunden.")
        return jsonify({'success': True, 'assets': assets_in_room})

    except Exception as e:
        # Fängt alle anderen Fehler ab, die in den topdesk-Funktionen auftreten könnten
        error_message = f"Ein Fehler ist bei der Verarbeitung der TopDesk-Anfrage aufgetreten: {e}"
        print(error_message)
        # Geben Sie eine detailliertere Fehlermeldung für das Debugging zurück
        return jsonify({'success': False, 'message': error_message}), 500


@app.route('/quick_inventory')
def quick_inventory():
    # GEÄNDERT: Die Beschränkung auf 'wenzelf' wurde entfernt.
    if not current_user.is_authenticated:
        flash("Sie müssen angemeldet sein, um auf diese Seite zuzugreifen.", "danger")
        return redirect(url_for('login'))

    templates = []
    try:
        template_data = topdesk.getTemplates()
        if template_data and 'dataSet' in template_data:
            for card in template_data['dataSet']:
                if 'text' in card:
                    templates.append(card['text'])
    except Exception as e:
        flash(f"Fehler beim Laden der Asset-Vorlagen von TopDesk: {e}", "warning")

    return render_template('quick_inventory.html', title='Schnell-Inventur', templates=templates)


@app.route('/save_new_assets', methods=['POST'])
def save_new_assets():
    # GEÄNDERT: Die Beschränkung auf 'wenzelf' wurde entfernt.
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    payload = request.get_json()
    if not payload:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    assets_to_create = payload.get('assets', [])
    device_type = payload.get('deviceType', '')  # Für den Dateinamen
    model_name = payload.get('modelName', '')  # Für den CSV-Inhalt

    if not assets_to_create:
        return jsonify({'success': False, 'message': 'Keine Asset-Daten erhalten'}), 400

    try:
        # --- Dynamische Spaltenerkennung ---
        # Prüfen, ob eine Modellbezeichnung vorhanden ist
        has_model_name = bool(model_name)
        # Prüfen, ob mindestens eine MAC-Adresse vorhanden ist
        has_mac_address = any(asset.get('mac', '').strip() for asset in assets_to_create)

        output = io.StringIO()
        writer = csv.writer(output)

        # 1. Kopfzeile dynamisch erstellen
        header = ['Geräte-ID', 'Seriennummer']
        if has_mac_address:
            header.append('MAC-Adresse')
        if has_model_name:
            header.append('Modellbezeichnung')
        writer.writerow(header)

        # 2. Datenzeilen dynamisch erstellen
        for asset in assets_to_create:
            asset_id = asset.get('id', '')
            serial_number = asset.get('serial', '')
            mac_address = asset.get('mac', '')

            # Nur Zeilen hinzufügen, die mindestens einen Wert haben
            if asset_id or serial_number or (has_mac_address and mac_address):
                row = [asset_id, serial_number]
                if has_mac_address:
                    row.append(mac_address)
                if has_model_name:
                    row.append(model_name)
                writer.writerow(row)

        csv_data = output.getvalue()

        # Dateiname wird vom Gerätetyp (Dropdown) bestimmt
        if device_type:
            safe_filename = "".join(c for c in device_type if c.isalnum() or c in (' ', '_')).rstrip()
            csv_filename = f"{safe_filename}.csv"
        else:
            csv_filename = "inventarliste.csv"

        recipient_email = str(current_user.mail[0]) if current_user.mail and len(current_user.mail) > 0 else None
        if not recipient_email:
            raise Exception("E-Mail-Adresse des Benutzers konnte nicht ermittelt werden.")

        msg = Message(
            subject=f"Neue Inventarliste: {device_type if device_type else 'Allgemein'}",
            sender=MAIL_ADDRESS,
            recipients=[recipient_email]
        )

        # E-Mail-Text dynamisch anpassen
        email_body = f"Hallo {current_user.id},\n\nanbei finden Sie die Liste der neu erfassten Geräte als CSV-Datei.\n\nGerätetyp: {device_type if device_type else 'Nicht angegeben'}"
        if has_model_name:
            email_body += f"\nModellbezeichnung: {model_name}"
        email_body += "\n\nMit freundlichen Grüßen,\nIhre Inventar-App"
        msg.body = email_body

        msg.attach(csv_filename, "text/csv", csv_data)
        mail.send(msg)

        return jsonify({
            'success': True,
            'message': f'{len(assets_to_create)} Geräte erfasst. Eine CSV-Liste wurde erfolgreich per E-Mail an {recipient_email} gesendet.'
        })

    except Exception as e:
        print(f"Fehler beim Erstellen oder Senden der CSV-E-Mail: {e}")
        return jsonify({
            'success': False,
            'message': f"Fehler beim Erstellen der CSV-Datei: {str(e)}"
        }), 500


@app.route('/get_location_details_by_id')
def get_location_details_by_id():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    location_id = request.args.get('id')
    if not location_id:
        return jsonify({'success': False, 'message': 'Keine ID angegeben'}), 400

    try:
        # Ruft die Funktion aus Ihrer topdesk.py auf

        location_details = topdesk.getLocationById(location_id)

        # KORREKTUR: Prüft, ob die Antwort ein Dictionary ist, bevor sie verwendet wird.
        # Dies fängt den Fall ab, dass Ihre Funktion bei einem Fehler einen String zurückgibt.
        if isinstance(location_details, dict):
            # Gibt das von Ihrer Funktion gefundene Raum-Objekt direkt an das Frontend weiter.
            return jsonify({'success': True, 'location': location_details})
        else:
            # Wenn die Funktion etwas anderes als ein Dictionary zurückgibt (z.B. einen Fehlerstring oder None),
            # wird dies als "nicht gefunden" behandelt.
            error_msg = location_details if isinstance(location_details,
                                                       str) else f"Raum mit ID {location_id} nicht gefunden."
            return jsonify({'success': False, 'message': error_msg}), 404

    except Exception as e:
        error_message = f"Fehler bei der Abfrage von TopDesk für ID {location_id}: {e}"
        print(error_message)
        return jsonify({'success': False, 'message': error_message}), 500


@app.route('/raum_info')
def raum_info():
    # Sichert die Seite ab
    if not current_user.is_authenticated:
        flash("Sie müssen angemeldet sein, um auf diese Seite zuzugreifen.", "danger")
        return redirect(url_for('login'))

    # Rendert die neue HTML-Seite
    return render_template('raum_info.html', title='Raum-Information')


@app.route('/test', methods=["GET"])
def test():
    return render_template('test.html')


if __name__ == '__main__':
    # No SSL
    # app.run(host='0.0.0.0', port=3000, debug=True)

    # With SSL active, for testing purposes on iPad for ex.
    app.run(host='0.0.0.0', port=3000, debug=True, ssl_context="adhoc")
