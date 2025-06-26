# FLASK APP SETTINGS
SECRET_KEY = 'e79b9847144221ba4e85df9dd483a3e5'
SQLALCHEMY_DATABASE_URI = "sqlite:///Inventarisierung.db"

# MAIL CREDENTIALS
MAIL_SERVER = 'oma.worms.de'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'wenzelf'
MAIL_PASSWORD = '***********'


# LDAP SETTINGS
LDAP_USER = 'anmelde_dom\\readad'
LDAP_PASS = '***REMOVED***'
LDAP_SERVER = "ldap://2.1.10.245"
AD_DOMAIN = "ANMELDE_DOM"
SEARCH_BASE = "CN=Users,DC=stadt,DC=worms"

# TOPDESK API
TOPDESK_API_URL = "https://topdesk.worms.de"
TOPDESK_API_USER = "topdeskapi"
TOPDESK_API_PASS = "***REMOVED***"

# PROXY
HTTP_PROXY = "http://127.0.0.1:3128"