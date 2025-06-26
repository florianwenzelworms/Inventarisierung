import requests
from requests.auth import HTTPBasicAuth
import json
import credentials


proxies = {"http": credentials.HTTP_PROXY,
           "https": credentials.HTTP_PROXY}
auth = HTTPBasicAuth(credentials.TOPDESK_API_USER, credentials.TOPDESK_API_PASS)


def getAsset(assetID):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets?searchTerm=%s" % assetID
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    if response.status_code == 200:
        for asset in json.loads(response.text)['dataSet']:
            if asset['text'] == assetID:
                return asset['id']


def getAssignments(assetID):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets/%s/assignments" % assetID
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    if response.status_code == 200:
        return json.loads(response.text)


def unlinkAssignments(roomID, assetID):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets/unlink/location/%s" % roomID
    payload = json.dumps({
        "assetIds": [
            assetID
        ]
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, data=payload, headers=headers, auth=auth, proxies=proxies)
    if response.status_code == 200:
        return json.loads(response.text)


def getLocation(roomname):
    url = "https://topdesk.worms.de/tas/api/locations?query=name=='%s'" %roomname
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    j = json.loads(response.text)
    if j.status_code == 200:
        for res in j:
            if res['name'] == roomname:
                return json.loads(response.text)[0]


def addAssignments(assetID, branch, room):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets/%s/assignments" % assetID
    payload = json.dumps({
        "branchId": branch,
        "linkToId": room,
        "linkType": "location"
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("PUT", url, headers=headers, data=payload, auth=auth, proxies=proxies)
    if response.status_code == 200:
        return json.loads(response.text)


def getAllRooms():
    url = "https://topdesk.worms.de/tas/api/locations"
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    if response.status_code == 200:
        return json.loads(response.text)


def getLocationAssets(location):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets?linkedTo=location/%s" % location
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    if response.status_code == 200:
        data = json.loads(response.text)['dataSet']
        assets = []
        for asset in data:
            assets.append(getAssetInfo(asset['data']['unid']))
        return assets


def getAssetInfo(asset):
    url = "https://topdesk.worms.de/tas/api/assetmgmt/assets/%s" % asset
    response = requests.request("GET", url, auth=auth, proxies=proxies)
    if response.status_code == 200:
        return json.loads(response.text)


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
    print(getAllRooms())
