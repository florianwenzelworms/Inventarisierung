from flask import Flask, render_template, flash, redirect, url_for, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
from flask_mail import Mail, Message
from forms import LoginForm
import ldap3
from credentials import *
import topdesk
import os
import re
import io
import csv
import logging
from logging.handlers import RotatingFileHandler


app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
login_manager = LoginManager(app)

# --- Logging Konfiguration ---
try:
    if not os.path.exists('logs'):
        os.mkdir('logs')

    # 1. Logger für Benutzeraktionen (Audit Log) erstellen
    audit_log_file = 'logs/audit.log'
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)

    # Rotiert die Log-Datei, wenn sie 5MB groß wird, und behält bis zu 10 alte Dateien.
    audit_handler = RotatingFileHandler(audit_log_file, maxBytes=1024 * 1024 * 5, backupCount=10, encoding='utf-8')

    # Formatiert die Log-Nachricht: Zeitstempel - Benutzername - Aktion
    audit_formatter = logging.Formatter('%(asctime)s - %(user)s - [%(caller)s] - %(message)s', defaults={'user': 'System', 'caller': 'unbekannt'})
    audit_handler.setFormatter(audit_formatter)

    # Verhindert, dass Logs doppelt an den Root-Logger gesendet werden
    audit_logger.propagate = False

    # Fügt den Handler nur hinzu, wenn noch keiner vorhanden ist, um Duplikate zu vermeiden
    if not audit_logger.handlers:
        audit_logger.addHandler(audit_handler)

except Exception as e:
    print(f"WARNUNG: Der Audit-Logger konnte nicht konfiguriert werden. Fehler: {e}")
    # Erstellt einen Dummy-Logger, damit die App nicht abstürzt, falls das Logging fehlschlägt
    audit_logger = logging.getLogger('audit_dummy')
    audit_logger.addHandler(logging.NullHandler())


def log_event(action_message, log_type='SYSTEM'):
    """
    Protokolliert eine Aktion.

    Args:
        action_message (str): Die Log-Nachricht.
        log_type (str): 'USER' für Benutzeraktionen, 'SYSTEM' für Systemereignisse.
    """
    user_id = current_user.id if current_user.is_authenticated else 'Anonymous'

    caller_name = "Kein Request-Kontext"
    if request:
        caller_name = request.endpoint

    audit_logger.info(action_message, extra={'user': user_id, 'caller': caller_name, 'log_type': log_type})


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
                log_event("Authentication successful")
                user = User(username)
                # JETZT die zusätzlichen Daten abrufen und dem Objekt hinzufügen
                try:
                    # get_user_data gibt ein Tupel zurück
                    user_details = get_user_data(username)
                    if user_details:
                        user.cn, user.mail, user.department, user.groups = user_details
                        log_event(f"User data loaded for {username}: Groups - {user.groups}")
                        return user
                    else:
                        # Falls aus irgendeinem Grund keine Daten gefunden wurden
                        log_event(f"Authentication successful, but could not retrieve data for {username}")
                        return False
                except Exception as e:
                    log_event(f"Error retrieving user data: {e}")
                    return False
    except Exception as e:
        log_event(f"LDAP authentication failed: {e}")
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


@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    # NEU: Lädt die Vorlagen für das Modal auf der Hauptseite
    templates = []
    try:
        template_data = topdesk.getTemplates()
        if template_data and 'dataSet' in template_data:
            for card in template_data['dataSet']:
                if 'text' in card:
                    templates.append(card['text'])
    except Exception as e:
        flash(f"Fehler beim Laden der Asset-Vorlagen: {e}", "warning")

    return render_template('main.html', templates=templates)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_ldap(form.username.data, form.password.data)
        if user and "1.05" in user.groups:
            login_user(user, remember=True)
            log_event("Login erfolgreich.")
            flash("Eingeloggt als " + user.id + "!", "success")
            return redirect(url_for('home'))
        else:
            log_event(f"Fehlgeschlagener Login-Versuch für Benutzer '{form.username.data}'.")
            flash("Falsches Passwort oder Benutzername", "danger")
    return render_template("login.html", title="login", form=form)


@app.route("/logout", methods=["GET"])
def logout():
    log_event("Logout erfolgreich.")
    logout_user()
    return redirect(url_for("login"))


@app.route('/direct_import', methods=['POST'])
def direct_import():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    data_from_frontend = request.get_json()
    room_item = next((item for item in data_from_frontend if 'Text' in item), None)
    scanned_items = [item['code'] for item in data_from_frontend if 'code' in item]
    missing_items_payload = next((item for item in data_from_frontend if 'missingAssetIds' in item), None)

    room_name = room_item['Text'] if room_item else None
    missing_asset_uuids = missing_items_payload['missingAssetIds'] if missing_items_payload else []

    if not room_name:
        log_event("Import fehlgeschlagen: Kein Raum angegeben.")
        flash("Import fehlgeschlagen: Kein Raum angegeben.", "danger")
        return jsonify({'success': False, 'redirect_url': url_for('home')})

    # Listen zum Sammeln der Ergebnisse für detailliertes Feedback
    not_found_codes = []
    moved_assets = []
    already_correct_assets = []
    removed_assets_feedback = []
    errors = []

    try:
        location_details = topdesk.getLocation(room_name)
        if not location_details:
            log_event(f"Ziel-Raum '{room_name}' nicht in TopDesk gefunden.")
            raise Exception(f"Ziel-Raum '{room_name}' nicht in TopDesk gefunden.")

        new_location_id = location_details['id']
        new_branch_id = location_details['branch']['id']

        # --- VERARBEITUNG: FEHLENDE ASSETS ENTFERNEN ---
        if missing_asset_uuids:
            try:
                success = topdesk.unlinkAssignments(new_location_id, missing_asset_uuids)
                if success:
                    log_event(f"Erfolgreich {len(missing_asset_uuids)} Assets ({', '.join(missing_asset_uuids)}) aus Raum {room_name} entfernt")
                    removed_assets_feedback.append(
                        f"{len(missing_asset_uuids)} fehlende Assets wurden aus Raum '{room_name}' entfernt.")
                else:
                    log_event("Ein Fehler ist beim gebündelten Entfernen der Assets aufgetreten.")
                    errors.append("Ein Fehler ist beim gebündelten Entfernen der Assets aufgetreten.")
            except Exception as e:
                log_event(f"Fehler bei der gebündelten Entfernung: {str(e)}")
                errors.append(f"Fehler bei der gebündelten Entfernung: {str(e)}")

        # --- VERARBEITUNG: GESCANnte ASSETS AKTUALISIEREN ---
        for code in scanned_items:
            try:
                asset_uuid = topdesk.getAsset(code)
                if not asset_uuid:
                    if code not in not_found_codes:
                        not_found_codes.append(code)
                    continue

                current_assignments = topdesk.getAssignments(asset_uuid)
                current_locations = current_assignments.get('locations', [])
                is_correctly_placed = any(
                    loc.get('location', {}).get('id') == new_location_id for loc in current_locations)

                if is_correctly_placed:
                    already_correct_assets.append(code)
                else:
                    if current_locations:
                        old_location_id = current_locations[0]['location']['id']
                        topdesk.unlinkAssignments(old_location_id, [asset_uuid])
                    topdesk.addAssignments(asset_uuid, new_branch_id, new_location_id)
                    moved_assets.append(code)
            except Exception as e:
                log_event(f"Fehler bei Asset '{code}': {str(e)}")
                errors.append(f"Fehler bei Asset '{code}': {str(e)}")

        # --- DETAILLIERTE FLASH-NACHRICHTEN AM ENDE ERSTELLEN ---
        if moved_assets:
            log_event(f"Erfolgreich verschoben ({len(moved_assets)}): {', '.join(moved_assets)}")
            flash(f"Erfolgreich verschoben ({len(moved_assets)}): {', '.join(moved_assets)}", "success")
        if already_correct_assets:
            log_event(f"Bereits korrekt zugeordnet ({len(already_correct_assets)}): {', '.join(already_correct_assets)}")
            flash(f"Bereits korrekt zugeordnet ({len(already_correct_assets)}): {', '.join(already_correct_assets)}",
                  "info")
        if removed_assets_feedback:
            flash(removed_assets_feedback[0], "warning")
        if errors:
            log_event(f"{len(errors)} Fehler aufgetreten: {'; '.join(errors)}")
            flash(f"{len(errors)} Fehler aufgetreten: {'; '.join(errors)}", "danger")

        return jsonify({
            'success': True,
            'redirect_url': url_for('home'),
            'not_found_codes': not_found_codes
        })

    except Exception as e:
        log_event(f"Ein schwerwiegender Fehler ist aufgetreten: {e}")
        flash(f"Ein schwerwiegender Fehler ist aufgetreten: {e}", "danger")
        return jsonify({'success': False, 'redirect_url': url_for('home')})


@app.route('/send_new_asset_report', methods=['POST'])
def send_new_asset_report():
    """Nimmt die neuen Assets aus dem Modal entgegen und sendet eine E-Mail."""
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    data = request.get_json()
    new_assets = data.get('new_assets', [])
    room_name = data.get('room_name', 'Unbekannt')

    if not new_assets:
        log_event('Keine Daten erhalten')
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    try:
        recipient_email = str(current_user.mail[0]) if current_user.mail and len(current_user.mail) > 0 else None
        if not recipient_email:
            log_event("E-Mail-Adresse des Benutzers konnte nicht ermittelt werden.")
            raise Exception("E-Mail-Adresse des Benutzers konnte nicht ermittelt werden.")

        email_body = f"Hallo {current_user.id},\n\n"
        email_body += f"die folgenden neuen Assets wurden im Raum '{room_name}' erfasst und müssen in TopDesk angelegt werden:\n\n"
        for asset in new_assets:
            email_body += f"- Asset-ID: {asset.get('code')},  Gerätetyp: {asset.get('type')}\n"
        email_body += "\nMit freundlichen Grüßen,\nIhre Inventar-App"

        msg = Message(
            subject="Meldung über neue, unbekannte Assets",
            sender=MAIL_ADDRESS,
            recipients=[recipient_email],
            body=email_body
        )
        mail.send(msg)

        log_event("E-Mail-Bericht erfolgreich versendet.")
        flash("Bericht für neue Assets erfolgreich per E-Mail versendet.", "success")
        return jsonify({'success': True, 'message': 'E-Mail-Bericht erfolgreich versendet.'})

    except Exception as e:
        log_event(str(e))
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/get_assets_for_room')
def get_assets_for_room():
    # 1. Sicherstellen, dass der Benutzer eingeloggt ist
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht authentifiziert'}), 401

    # 2. Den 'room'-Parameter aus der URL lesen (z.B. ?room=Raumname)
    room_name = request.args.get('room')
    if not room_name:
        log_event('Kein Raumname in der Anfrage gefunden.')
        return jsonify({'success': False, 'message': 'Kein Raumname in der Anfrage gefunden.'}), 400

    try:
        # 3. Zuerst die ID des Raumes anhand des Namens von TopDesk holen
        # Hier wird die Original-Funktion aus Ihrer topdesk.py aufgerufen
        location_details = topdesk.getLocation(room_name)
        # 4. Prüfen, ob der Raum gefunden wurde
        if not location_details or 'id' not in location_details:
            log_event(f"Raum '{room_name}' nicht in TopDesk gefunden.")
            return jsonify({'success': False, 'message': f'Raum "{room_name}" nicht in TopDesk gefunden.'}), 404

        location_id = location_details['id']

        # 5. Mit der Raum-ID alle zugehörigen Assets abrufen
        # Hier wird die Original-Funktion aus Ihrer topdesk.py aufgerufen
        assets_in_room = topdesk.getLocationAssets(location_id)
        log_event(f'Assets für Raum {room_name} abgefragt')
        # 6. Die gefundene Asset-Liste als JSON an das Frontend zurückgeben
        return jsonify({'success': True, 'assets': assets_in_room})

    except Exception as e:
        # Fängt alle anderen Fehler ab, die in den topdesk-Funktionen auftreten könnten
        error_message = f"Ein Fehler ist bei der Verarbeitung der TopDesk-Anfrage aufgetreten: {e}"
        log_event(error_message)
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
        log_event(f"Fehler beim Laden der Asset-Vorlagen von TopDesk: {e}")
        flash(f"Fehler beim Laden der Asset-Vorlagen von TopDesk: {e}", "warning")

    return render_template('quick_inventory.html', title='Schnell-Inventur', templates=templates)


@app.route('/save_new_assets', methods=['POST'])
def save_new_assets():
    # GEÄNDERT: Die Beschränkung auf 'wenzelf' wurde entfernt.
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    payload = request.get_json()
    if not payload:
        log_event('Keine Daten erhalten')
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400

    assets_to_create = payload.get('assets', [])
    device_type = payload.get('deviceType', '')  # Für den Dateinamen
    model_name = payload.get('modelName', '')  # Für den CSV-Inhalt

    if not assets_to_create:
        log_event('Keine Asset-Daten erhalten')
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
            log_event("E-Mail-Adresse des Benutzers konnte nicht ermittelt werden.")
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

        log_event(f'{len(assets_to_create)} Geräte erfasst. Eine CSV-Liste wurde erfolgreich per E-Mail an {recipient_email} gesendet.')
        return jsonify({
            'success': True,
            'message': f'{len(assets_to_create)} Geräte erfasst. Eine CSV-Liste wurde erfolgreich per E-Mail an {recipient_email} gesendet.'
        })

    except Exception as e:
        log_event(f"Fehler beim Erstellen oder Senden der CSV-E-Mail: {str(e)}")
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
        log_event('Keine ID angegeben')
        return jsonify({'success': False, 'message': 'Keine ID angegeben'}), 400

    try:
        # Ruft Ihre Funktion aus topdesk.py auf
        location_details = topdesk.getLocationById(location_id)

        # Prüft, ob die Funktion ein sinnvolles Ergebnis zurückgegeben hat.
        # Dies funktioniert sowohl, wenn die Funktion None als auch wenn sie eine leere Liste [] zurückgibt.
        if location_details:
            log_event(f"Abfrage für Location {location_id}")
            return jsonify({'success': True, 'location': location_details})
        else:
            # Dieser Fall wird jetzt korrekt behandelt, wenn eine leere Liste zurückkommt.
            log_event(f'Raum mit ID "{location_id}" nicht gefunden.')
            return jsonify({'success': False, 'message': f'Raum mit ID "{location_id}" nicht gefunden.'}), 404

    except IndexError:
        # Fängt explizit den "list index out of range"-Fehler ab, falls er doch
        # innerhalb Ihrer topdesk.py-Funktion auftritt.
        log_event(f"IndexError bei der Suche nach ID '{location_id}'. Das bedeutet, die Suche lieferte keine Ergebnisse.")
        return jsonify({'success': False, 'message': f'Raum mit ID "{location_id}" nicht gefunden.'}), 404

    except Exception as e:
        # Fängt alle anderen unerwarteten Fehler ab.
        error_message = f"Fehler bei der Abfrage von TopDesk für ID {location_id}: {e}"
        log_event(error_message)
        return jsonify({'success': False, 'message': error_message}), 500


@app.route('/raum_info')
def raum_info():
    # Sichert die Seite ab
    if not current_user.is_authenticated:
        flash("Sie müssen angemeldet sein, um auf diese Seite zuzugreifen.", "danger")
        return redirect(url_for('login'))

    # Holt alle Daten, die für die Modals benötigt werden
    all_rooms = []
    branches = []
    building_zones = []
    try:
        all_rooms = topdesk.getAllRooms()
        branches = topdesk.getBranches()
        building_zones = topdesk.getBuildingZones()
    except Exception as e:
        log_event(f"Fehler beim Laden der Daten von TopDesk: {e}")
        flash(f"Fehler beim Laden der Daten von TopDesk: {e}", "warning")

    # Übergibt alle Listen an das HTML-Template
    return render_template('raum_info.html', title='Raum-Information',
                           all_rooms=all_rooms,
                           branches=branches,
                           building_zones=building_zones)


@app.route('/create_new_location', methods=['POST'])
def create_new_location():
    """Nimmt Daten aus dem Modal entgegen und legt einen neuen Raum in TopDesk an."""
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    data = request.get_json()
    branch = data.get('branch')
    building_zone = data.get('buildingZone')
    room_number = data.get('roomNumber')

    if not all([branch, building_zone, room_number]):
        log_event('Unvollständige Daten erhalten.')
        return jsonify({'success': False, 'message': 'Unvollständige Daten erhalten.'}), 400

    try:
        # Logik zur Erstellung des Raumnamens, wie von Ihnen vorgegeben
        building_zone_name = building_zone.get('name', '')
        base_name = ''
        if ' - ' in building_zone_name:
            base_name = building_zone_name.split(' - ')[0]
        else:
            match = re.search(r'\d', building_zone_name)
            if match:
                base_name = building_zone_name[:match.start()].strip()
            else:
                base_name = building_zone_name

        # Der finale Name wird aus dem Basisnamen und der Raumnummer zusammengesetzt
        final_room_name = f"{base_name} - {room_number}"

        # Die Funktion in topdesk.py aufrufen
        new_location = topdesk.newLocation(
            name=final_room_name,
            roomnumber=room_number,
            branch=branch,
            buildingzone=building_zone
        )

        if new_location:
            return jsonify({
                'success': True,
                'message': f"Raum '{final_room_name}' wurde erfolgreich angelegt.",
                'newLocation': new_location  # Gibt den neuen Raum zurück
            })
        else:
            log_event(f"Fehler beim Anlegen des Raums {final_room_name} in TopDesk.")
            return jsonify({'success': False, 'message': "Fehler beim Anlegen des Raums in TopDesk."}), 500

    except Exception as e:
        error_message = f"Fehler bei der Raumerstellung: {e}"
        log_event(error_message)
        return jsonify({'success': False, 'message': error_message}), 500


@app.route('/assign_custom_id_to_room', methods=['POST'])
def assign_custom_id_to_room():
    """
    Nimmt eine gescannte Custom-ID und eine ausgewählte Raum-UUID entgegen
    und aktualisiert den Raum in TopDesk.
    """
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': 'Nicht autorisiert'}), 403

    data = request.get_json()
    location_uuid = data.get('location_uuid')
    custom_room_id = data.get('custom_room_id')

    if not location_uuid or not custom_room_id:
        log_event('Unvollständige Daten erhalten.')
        return jsonify({'success': False, 'message': 'Unvollständige Daten erhalten.'}), 400

    try:
        # Ruft die von Ihnen bereitgestellte Funktion aus topdesk.py auf
        updated_room = topdesk.updateRoomId(location_uuid, custom_room_id)

        if updated_room:
            log_event(f"Die ID '{custom_room_id}' wurde erfolgreich dem Raum '{updated_room.get('name', '')}' zugewiesen.")
            return jsonify({
                'success': True,
                'message': f"Die ID '{custom_room_id}' wurde erfolgreich dem Raum '{updated_room.get('name', '')}' zugewiesen."
            })
        else:
            log_event("Fehler beim Aktualisieren des Raums in TopDesk.")
            return jsonify({
                'success': False,
                'message': "Fehler beim Aktualisieren des Raums in TopDesk."
            }), 500

    except Exception as e:
        error_message = f"Fehler bei der Zuweisung: {e}"
        log_event(error_message)
        return jsonify({'success': False, 'message': error_message}), 500


if __name__ == '__main__':
    # No SSL
    # app.run(host='0.0.0.0', port=3000, debug=True)

    # With SSL active, for testing purposes on iPad for ex.
    app.run(host='0.0.0.0', port=3000, debug=True, ssl_context="adhoc")
