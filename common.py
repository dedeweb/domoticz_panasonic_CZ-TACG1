import Domoticz
import requests
import config
import os
import requests
import Domoticz
from datetime import datetime
import config

# get current timestamp
def get_timestamp():
    return f"'{datetime.now().strftime('%Y%m%d %H:%M:%S')}'"

# get current timestamp
def get_date():
    return f"{datetime.now().strftime('%Y%m%d')}"

# call app store to get latest version
def get_app_version(first_time=False):
    if first_time and os.path.exists(config.api_version_file_path):
        os.remove(config.api_version_file_path)
        print(f"{config.api_version_file_path} has been deleted.")

    version = config.api_version
    # if api_version_file_path already exist reuse it
    if os.path.exists(config.api_version_file_path):
        with open(config.api_version_file_path, 'r') as version_file:
            version = version_file.read().strip()
            Domoticz.Log("Reusing existing api_version=" + version)
            return version
    # else, query the iTunes lookup API which returns the current version as JSON
    try:
        Domoticz.Log("Getting latest Comfort Cloud version from the App Store...")
        response = requests.get(config.appstore_lookup_url, timeout=10)
        response.raise_for_status()  # Vérifiez si la requête a réussi; sinon, une exception est levée

        results = response.json().get("results", [])
        if results and results[0].get("version"):
            version = results[0]["version"]
            Domoticz.Log("get_app_version=" + version)
        else:
            Domoticz.Error(f"Could not find version in App Store response; keeping {version}")

        # save the version
        with open(config.api_version_file_path, 'w') as version_file:
            version_file.write(version)

    except requests.RequestException as e:
        Domoticz.Error(f"Failed to get the latest Comfort Cloud version: {e}")

    except Exception as e:
        Domoticz.Error(f"An unexpected error occurred: {e}")

    return version

# Domoticz' "From Device" kWh meter treats the energy field as an absolute,
# ever-increasing Wh counter and draws each bar as the difference between two
# readings. The Panasonic APIs return the *daily* total, which resets to 0 every
# midnight, so the rollover shows up as a big negative bar. Turn that daily
# figure into a monotonic counter by only ever adding the increment.
_energy_state = {}  # device DeviceID -> {'meter': Wh, 'day_total': Wh}

def monotonic_energy(device, raw):
    last_part, _, total_part = raw.partition(';')
    day_total = int(total_part)
    key = device.DeviceID
    state = _energy_state.get(key)
    if state is None:
        # first poll this session: continue from whatever counter Domoticz already
        # stored, so a plugin restart doesn't create a one-off jump or drop.
        try:
            meter = int(float(device.sValue.split(';')[1]))
        except (ValueError, IndexError, AttributeError):
            meter = day_total
        _energy_state[key] = {'meter': meter, 'day_total': day_total}
        return f'{last_part};{meter}'
    # a smaller day_total than last time means midnight rolled over (or the unit
    # was off and the day reset), so the new total is itself the increment.
    delta = day_total - state['day_total'] if day_total >= state['day_total'] else day_total
    state['meter'] += delta
    state['day_total'] = day_total
    return f'{last_part};{state["meter"]}'
