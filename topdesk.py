import requests
from requests.auth import HTTPBasicAuth
import json
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
    url = f"{base_url}/tas/api/locations/id/{id}"
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
