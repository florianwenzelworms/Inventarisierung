import requests
from requests.auth import HTTPBasicAuth
import json
import re
from credentials import TOPDESK_API_URL, TOPDESK_API_USER, TOPDESK_API_PASS, HTTP_PROXY


proxies = {"http": HTTP_PROXY,
           "https": HTTP_PROXY}
auth = HTTPBasicAuth(TOPDESK_API_USER, TOPDESK_API_PASS)
base_url = TOPDESK_API_URL


def getAsset(assetID):
    """Sucht ein Asset anhand seiner ID/Namen und gibt die TopDesk-UUID zurück."""
    url = f"{base_url}/tas/api/assetmgmt/assets?searchTerm={assetID}"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=10)
        response.raise_for_status()  # Löst Fehler bei 4xx/5xx-Status aus
        data = response.json()
        if data.get('dataSet'):
            for asset in data['dataSet']:
                if asset.get('text') == assetID:
                    return asset.get('id')
        return None # Explizit None zurückgeben, wenn nichts gefunden wurde
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getAsset für '{assetID}': {e}")
        return None


def getAssignments(assetID):
    """Holt die Zuweisungen für ein Asset."""
    url = f"{base_url}/tas/api/assetmgmt/assets/{assetID}/assignments"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getAssignments für Asset-ID '{assetID}': {e}")
        return None

def unlinkAssignments(roomID, assetIDs):
    """Entfernt die Zuweisung von Assets von einem Standort."""
    url = f"{base_url}/tas/api/assetmgmt/assets/unlink/location/{roomID}"
    payload = json.dumps({"assetIds": assetIDs})
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, data=payload, headers=headers, auth=auth, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in unlinkAssignments für Raum-ID '{roomID}': {e}")
        return None


def getLocation(roomname):
    """Sucht einen Standort anhand des Namens."""
    url = f"{base_url}/tas/api/locations?query=name=='{roomname}'"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Die API gibt eine Liste zurück, auch wenn nur ein Ergebnis erwartet wird.
        for res in data:
            if res.get('name') == roomname:
                return res # Gibt das passende Objekt direkt zurück
        return None
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getLocation für '{roomname}': {e}")
        return None


def getLocationById(id):
    """Holt die Details eines Standorts anhand seiner ID."""
    temp_id = id
    if len(temp_id) == 6:
        pre_url = f"{base_url}/tas/api/locations?query=optionalFields1.text1=={temp_id}"
        try:
            response = requests.get(pre_url, auth=auth, proxies=proxies, timeout=10)
            response.raise_for_status()
            temp_id = response.json()[0].get('id')
        except requests.exceptions.RequestException as e:
            print(f"API Fehler in getLocationById für ID '{temp_id}': {e}")
            return None
    url = f"{base_url}/tas/api/locations/id/{temp_id}"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getLocationById für ID '{id}': {e}")
        return None


def addAssignments(assetID, branch, room):
    """Weist ein Asset einem neuen Standort zu."""
    url = f"{base_url}/tas/api/assetmgmt/assets/{assetID}/assignments"
    payload = json.dumps({
        "branchId": branch,
        "linkToId": room,
        "linkType": "location"
    })
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.put(url, headers=headers, data=payload, auth=auth, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in addAssignments für Asset-ID '{assetID}': {e}")
        return None


def getAllRooms():
    """Holt eine Liste aller Standorte."""
    url = f"{base_url}/tas/api/locations"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getAllRooms: {e}")
        return [] # Gibt eine leere Liste bei Fehlern zurück


def getLocationAssets(location):
    """Holt alle Assets, die einem Standort zugewiesen sind."""
    url = f"{base_url}/tas/api/assetmgmt/assets?linkedTo=location/{location}"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=20)
        response.raise_for_status()
        data = response.json()
        assets = []
        if data.get('dataSet'):
            for asset in data['dataSet']:
                # Holt für jedes gefundene Asset die Detailinformationen
                asset_info = getAssetInfo(asset.get('id'))
                if asset_info and 'data' in asset_info:
                    assets.append(asset_info['data'])
        return assets
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getLocationAssets für Standort '{location}': {e}")
        return []


def getAssetInfo(asset):
    """Holt die Detailinformationen für ein einzelnes Asset."""
    url = f"{base_url}/tas/api/assetmgmt/assets/{asset}"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getAssetInfo für Asset '{asset}': {e}")
        return None


def getTemplates():
    """Holt alle verfügbaren Asset-Vorlagen."""
    url = f"{base_url}/tas/api/assetmgmt/templates"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getTemplates: {e}")
        return None


def updateRoomId(location_uuid, custom_room_id):
    """
    Aktualisiert das benutzerdefinierte ID-Feld ('text1') für einen bestimmten Standort.

    Args:
        location_uuid (str): Die eindeutige UUID des Standorts in TopDesk.
        custom_room_id (str): Die 6-stellige benutzerdefinierte ID, die gesetzt werden soll.

    Returns:
        dict: Das JSON-Objekt des aktualisierten Standorts bei Erfolg, sonst None.
    """
    # Der API-Endpunkt für den spezifischen Standort
    url = f"{base_url}/tas/api/locations/id/{location_uuid}"

    # Die Daten, die aktualisiert werden sollen. Nur das spezifische Feld wird gesendet.
    payload = json.dumps({
        "optionalFields1": {
            "text1": custom_room_id
        }
    })

    headers = {'Content-Type': 'application/json'}

    try:
        # Führt die PUT-Anfrage aus, um die Daten zu aktualisieren
        response = requests.put(url, headers=headers, data=payload, auth=auth, proxies=proxies, timeout=10)

        # Löst eine Ausnahme aus, wenn der Server einen Fehlerstatus (4xx oder 5xx) zurückgibt
        response.raise_for_status()

        # Gibt die JSON-Antwort des Servers bei Erfolg zurück
        return response.json()

    except requests.exceptions.RequestException as e:
        # Fängt Netzwerkfehler, Timeouts, etc. ab
        print(f"API Fehler in updateRoomId für Standort-UUID '{location_uuid}': {e}")
        return None
    except json.JSONDecodeError as e:
        # Fängt Fehler ab, wenn die Antwort vom Server kein gültiges JSON ist
        print(f"Fehler beim Parsen der JSON-Antwort in updateRoomId für Standort-UUID '{location_uuid}': {e}")
        return None


def getBuildingZones():
    """Holt eine Liste aller Gebäudebereiche."""
    url = f"{base_url}/tas/api/locations/building_zones"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getBuildingZones: {e}")
        return [] # Gibt eine leere Liste bei Fehlern zurück


def getBranches():
    """Holt eine Liste aller Niederlassungen."""
    url = f"{base_url}/tas/api/branches"
    try:
        response = requests.get(url, auth=auth, proxies=proxies, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in getBranches: {e}")
        return [] # Gibt eine leere Liste bei Fehlern zurück


def newLocation(name, roomnumber, branch, buildingzone):
    """Legt einen neuen Raum an"""
    url = f"{base_url}/tas/api/locations"

    # Es werden Raumname, Raumnummer, Niederlassung und Gebäudebereich benötigt.
    print('branch: ', branch)
    print('buildingzone: ', buildingzone)
    print('name: ', name)
    print('roomnumber: ', roomnumber)
    payload = json.dumps({
        'branch': {
            'id': branch['id'],
            'name': branch['name']
        },
        'buildingZone': {
            'id': buildingzone['id'],
            'name': buildingzone['name']
        },
        'roomNumber': roomnumber,
        'name': name
    })

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload, auth=auth, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Fehler in newLocation: {e}")
        return None


if __name__ == "__main__":
    # # print(getAsset('016918'))
    # # print(getAssignments(getAsset('016918'))['locations'][0]['location']['name'])
    #
    # # Scanne den Raum und die Geräte darin
    # id = '016918'
    # room = 'Lutherring 31 - 209'
    #
    # # Hole die Topdesk ID vom Asset und Raum
    # asset = getAsset(id)
    # roomID = getLocation(room)
    #
    # # Hole den verknüpften Raum
    # assetroom = getAssignments(asset)
    #
    # # Überprüfe, ob der verlinkte Raum der neue Raum ist
    # newroom = True
    # for loc in assetroom['locations']:
    #     if loc['location']['id'] == roomID['id']:
    #         newroom = False
    #
    # # Wenn nicht der Raum entferne den zugeordneten Raum
    # if newroom:
    #     # Wenn alter Raum zugewiesen wird er erst entfernt
    #     if len(assetroom['locations']) > 0:
    #         oldroomID = assetroom['locations'][0]['location']['id']
    #         unlinkAssignments(oldroomID, asset)
    #
    #     # Hole ID von neuem Raum
    #     neuloc = getLocation(room)
    #
    #     # Linke neuen Raum
    #     addAssignments(asset, neuloc['branch']['id'], neuloc['id'])
    # print(getAllRooms())
    pass
