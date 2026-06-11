# shared variables
update_interval = None
debug_level = None
api_version = None
aquarea_token = None
username = None
password = None
devices = None
client = None
# device IDs currently unreachable (e.g. air conditioner powered off), to log
# the unreachable/reachable transition only once
unreachable_devices = set()

# constants
appstore_url = 'https://apps.apple.com/app/panasonic-comfort-cloud/id1348640525'
# iTunes lookup API: returns the app metadata (including the current version) as JSON
appstore_lookup_url = 'https://itunes.apple.com/lookup?id=1348640525'
accsmart_url = "https://accsmart.panasonic.com"
aquarea_url = "https://aquarea-smart.panasonic.com"
token_file_path = '.accsmarttoken'
aquarea_token_file_path = '.aquareatoken'
api_version_file_path = '.api_version'

auth0_client = 'eyJuYW1lIjoiYXV0aDAuanMtdWxwIiwidmVyc2lvbiI6IjkuMjMuMiJ9'
authglb_url = 'https://authglb.digital.panasonic.com'
digital_panasonic_url = 'https://digital.panasonic.com'