import os
import requests
import json
import Domoticz
from datetime import datetime
import config
import common

from pcomfortcloud import ApiClient
from pcomfortcloud import constants
import pcomfortcloud

############################
# Generic helper functions #
############################

# Each Domoticz widget is identified by a stable key embedded in its DeviceID:
#   "<panasonic guid>#<widget key>"   e.g. "CS-BZ60CKE+E299301492#room_temp"
# This makes the identification independent from the widget Name, so users can
# rename widgets freely without breaking updates/commands or causing duplicates.
WIDGET_KEY_SEPARATOR = '#'

# widget key -> default name suffix
WIDGET_DEFS = {
    'power': '[Power]',
    'room_temp': '[Room Temp]',
    'outdoor_temp': '[Outdoor Temp]',
    'target_temp': '[Target temp]',
    'mode': '[Mode]',
    'fan_speed': '[Fan Speed]',
    'eco_mode': '[Eco Mode]',
    'air_swing': '[Air Swing]',
    'energy': '[Energy]',
}

def make_widget_device_id(guid, widget_key):
    return f"{guid}{WIDGET_KEY_SEPARATOR}{widget_key}"

# returns (panasonic_guid, widget_key); widget_key is '' for legacy/aquarea ids
def split_widget_device_id(device_id):
    guid, _, widget_key = device_id.partition(WIDGET_KEY_SEPARATOR)
    return guid, widget_key

def get_widget_key(device):
    return split_widget_device_id(device.DeviceID)[1]

def get_panasonic_guid(device):
    return split_widget_device_id(device.DeviceID)[0]

# call the api to get a token
def get_client():
    client = ApiClient(config.username, config.password)
    client.start_session()
    client.get_devices()
    return client

# call the api to get device infos
def get_device_by_id(device_id):
    #todo: use client api
    #device_hash_guid=get_device_hash_guid(device_id)
    #json_response=config.client.get_device(device_hash_guid)
    try:
        json_response = config.client.execute_get(config.client._get_device_status_url(device_id), "get_device", 200)
    except Exception as e:
        # e.g. HTTP 500 {"code":5005,"message":"Adapter Communication error"} when
        # the unit is powered off. Return None so the caller can mark it unreachable.
        Domoticz.Debug(f"get_device_by_id failed for {device_id}: {e}")
        return None
    Domoticz.Debug(f"in get_device_by_id, json_response={json_response}")
    return json_response


# track whether a device is reachable. We deliberately do NOT flag the Domoticz
# device as TimedOut: that triggers "device expired" notification popups. Instead
# we keep the widgets available with their last known values and just stop
# updating them while the unit is powered off. Logs only once per transition.
def set_reachable(device, reachable):
    # key on the panasonic guid (shared by all widgets of a unit) so the
    # transition is logged once per unit, not once per widget
    guid = get_panasonic_guid(device)
    was_unreachable = guid in config.unreachable_devices
    if reachable and was_unreachable:
        config.unreachable_devices.discard(guid)
        Domoticz.Log(f"{guid} is reachable again")
    elif not reachable and not was_unreachable:
        config.unreachable_devices.add(guid)
        Domoticz.Log(f"{guid} is unreachable (air conditioner powered off?); keeping last known values")

# Panasonic uses -255 as a "no data" sentinel for hourly slots that haven't
# happened yet or weren't recorded.
NO_DATA = -255

# pull a per-hour consumption (kWh) out of one historyDataList entry, or None if
# the slot has no data. The key has varied across API versions, so be permissive.
def _entry_consumption(entry):
    if not isinstance(entry, dict):
        return None
    for key in ('consumption', 'energyConsumption', 'energy'):
        value = entry.get(key)
        if value is not None and value != NO_DATA:
            return value
    return None

# call the api to get device historic data
def get_historic_data(device_id):
    # Panasonic exposes consumption through the deviceHistoryData endpoint. We
    # query the current day in "Day" mode: historyDataList holds one entry per
    # hour with the consumption in kWh (future/empty hours are -255).
    # Domoticz' kWh widget wants "<instant W>;<total Wh>".
    # device_id here is already the real Panasonic deviceGuid (see
    # get_panasonic_guid in the caller), which is exactly what the payload needs.
    payload = {
        "deviceGuid": device_id,
        "dataMode": constants.DataMode.Day.value,
        "date": datetime.now().strftime('%Y%m%d'),
        "osTimezone": "+01:00",
    }
    try:
        response = config.client.execute_post(
            config.client._get_device_history_url(), payload, "history", 200)
    except Exception as e:
        # e.g. unit powered off / API hiccup: signal the caller to keep the
        # previous value rather than writing a bogus 0.
        Domoticz.Log(f"get_historic_data failed for {device_id} (powered off?): {e}")
        return '-255;0'

    Domoticz.Debug(f"get_historic_data raw response for {device_id}: {response}")
    history_list = (response or {}).get('historyDataList') or []

    # keep only the hours that actually have data, in chronological order
    consumptions = [c for c in (_entry_consumption(e) for e in history_list)
                    if c is not None]

    # day total so far (kWh -> Wh) and the most recent recorded hour as the
    # "instantaneous" figure for the kWh widget
    energy_wh = int(sum(consumptions) * 1000)
    last_wh = int(consumptions[-1] * 1000) if consumptions else 0

    Domoticz.Debug(f"get_historic_data for {device_id} = {last_wh};{energy_wh}")
    return f'{last_wh};{energy_wh}'

# call the api to update device parameter
def update_device_id(device_id, parameter_name, parameter_value):
    device_hash_guid=get_device_hash_guid(device_id)
    Domoticz.Log(f"updating DeviceId={device_id}, device_hash_guid={device_hash_guid}, {parameter_name}={parameter_value}...")
    payload= {parameter_name: parameter_value}
    try:
        res=config.client.set_device(device_hash_guid, **payload)
    except Exception as e:
        # e.g. HTTP 500 "Adapter Communication error" when the unit is powered off
        Domoticz.Log(f"Could not send command to {device_id} (powered off?): {e}")
        return None
    #Domoticz.Log(f"payload={payload} url={config.client._get_device_status_control_url()}")
    #response = config.client.execute_post(config.client._get_device_status_control_url(), payload, "set_device", 200)

    Domoticz.Log(f"update_device_id={res}")
    return res

def handle_response(response, retry_func):
    if response is None:
        return None

    error_handlers = {
        "New version app has been published": handle_api_version_update,
    }

    for error_text, handler in error_handlers.items():
        if error_text in response.text:
            handler()
            return retry_func()
        elif '"errorMessage":' in response.text:
            Domoticz.Error(f"error not handled in response {response.text} for retry_func={retry_func}")

    return json.loads(response.text)

def handle_api_version_update():
    Domoticz.Log("New version app has been published")
    # if api_version_file_path file exists delete it
    if os.path.exists(config.api_version_file_path):
        os.remove(config.api_version_file_path)
    config.api_version = common.get_app_version()

# dumps the http response to the log
def dump_http_response_to_log(httpResp, level=0):
    if (level == 0): Domoticz.Debug("HTTP Details (" + str(len(httpResp)) + "):")
    indentStr = ""
    for x in range(level):
        indentStr += "----"
    if isinstance(httpResp, dict):
        for x in httpResp:
            if not isinstance(httpResp[x], dict) and not isinstance(httpResp[x], list):
                Domoticz.Debug(indentStr + ">'" + x + "':'" + str(httpResp[x]) + "'")
            else:
                Domoticz.Debug(indentStr + ">'" + x + "':")
                dump_http_response_to_log(httpResp[x], level + 1)
    elif isinstance(httpResp, list):
        for x in httpResp:
            Domoticz.Debug(indentStr + "['" + x + "']")
    else:
        Domoticz.Debug(indentStr + ">'" + x + "':'" + str(httpResp[x]) + "'")


########################
# End helper functions #
########################

# build the [Mode] selector options, hiding modes the unit does not support (e.g.
# no Fan). The order matches the OperationMode enum (Auto=0, Dry=1, Cool=2, Heat=3,
# Fan=4) so the level mapping (value+1)*10 stays valid. We only drop unsupported
# modes from the END of the list, which keeps every remaining level aligned.
def build_mode_options(deviceid):
    mode_defs = [("Auto", "autoMode"), ("Dry", "dryMode"), ("Cool", "coolMode"),
                 ("Heat", "heatMode"), ("Fan", "fanMode")]
    status = get_device_by_id(deviceid) or {}
    # default to available when the status is unknown, so we never hide a real mode
    mode_names = [name if status.get(flag, True) else "" for (name, flag) in mode_defs]
    while mode_names and mode_names[-1] == "":
        mode_names.pop()
    return {"LevelActions": "|" * len(mode_names), "LevelNames": "|" + "|".join(mode_names), "LevelOffHidden": "true", "SelectorStyle": "1"}


# Create only the widgets that don't exist yet for this device, so deleting a
# single widget recreates just that one and existing widgets keep their history.
# Widgets are identified by a stable key embedded in their DeviceID (see
# make_widget_device_id), NOT by their Name, so they can be renamed freely.
def add_device(devicename, deviceid, nbdevices):
    # migrate from the legacy scheme where all widgets shared the bare panasonic
    # guid as DeviceID: those can't be told apart reliably, delete them once (they
    # are recreated right below with the new composite DeviceID)
    legacy_units = [x for x in list(config.devices) if config.devices[x].DeviceID == deviceid]
    for x in legacy_units:
        Domoticz.Log(f"Migrating legacy device {config.devices[x].Name} (recreated with a per-widget DeviceID)...")
        config.devices[x].Delete()

    existing_ids = {config.devices[x].DeviceID for x in config.devices}

    widgets = [
        ('power', dict(Image=16, TypeName="Switch")),
        ('room_temp', dict(TypeName="Temperature")),
        ('outdoor_temp', dict(TypeName="Temperature")),
        ('target_temp', dict(Type=242, Subtype=1, Image=16)),
        # mode options are built lazily below (needs a network call)
        ('mode', dict(TypeName="Selector Switch", Image=16, Options=None)),
        ('fan_speed', dict(TypeName="Selector Switch", Image=7,
             Options={"LevelActions": "|||||||", "LevelNames": "|Auto|Low|LowMid|Mid|HighMid|High", "LevelOffHidden": "true", "SelectorStyle": "1"})),
        ('eco_mode', dict(TypeName="Selector Switch", Image=7,
             Options={"LevelActions": "|||||||", "LevelNames": "|Normal|Powerful|Quiet", "LevelOffHidden": "true", "SelectorStyle": "1"})),
        ('air_swing', dict(TypeName="Selector Switch", Image=7,
             Options={"LevelActions": "|||||||||", "LevelNames": "Auto|Up|Down|Mid|UpMid|DownMid|Swing", "LevelOffHidden": "true", "SelectorStyle": "1"})),
        # Use Options={'EnergyMeterMode': '1'} for "Calculated"; default is "From Device"
        ('energy', dict(TypeName="kWh", Options={'EnergyMeterMode': '0'})),
    ]

    next_unit = max(config.devices) if config.devices else 0
    created = 0
    for widget_key, kwargs in widgets:
        widget_device_id = make_widget_device_id(deviceid, widget_key)
        if widget_device_id in existing_ids:
            continue
        if widget_key == 'mode':
            # only hit the network when the Mode widget actually needs creating
            kwargs = dict(kwargs, Options=build_mode_options(deviceid))
        next_unit += 1
        Domoticz.Device(Name=devicename + WIDGET_DEFS[widget_key], Unit=next_unit, Used=1,
                        DeviceID=widget_device_id, **kwargs).Create()
        created += 1

    if created:
        Domoticz.Log(f"Created {created} missing device(s) for {devicename} (DeviceID={deviceid}).")
    else:
        Domoticz.Debug(f"All devices already present for {devicename} (DeviceID={deviceid}).")



def handle_accsmart(device, devicejson):
    power = 0
    value = "----"
    widget_key = get_widget_key(device)
    if (widget_key == 'target_temp'):
        value = str(float(devicejson['parameters']['temperatureSet']))
    elif (widget_key == 'room_temp'):
        value = str(float(devicejson['parameters']['insideTemperature']))
    elif (widget_key == 'outdoor_temp'):
        if (float(devicejson['parameters']['outTemperature']) > 100):
            value = "--"
        else:
            value = str(float(devicejson['parameters']['outTemperature']))
    elif (widget_key == 'power'):
        power = int(devicejson['parameters']['operate'])
        value = str(power * 100)
    elif (widget_key == 'mode'):
        operationmode = int(devicejson['parameters']['operationMode'])
        value = str((operationmode + 1) * 10)
    elif (widget_key == 'fan_speed'):
        fanspeed = int(devicejson['parameters']['fanSpeed'])
        value = str((fanspeed + 1) * 10)
    elif (widget_key == 'eco_mode'):
        # ecoMode enum: Normal(=Auto in the API)=0, Powerful=1, Quiet=2.
        # selector levels are Normal=10, Powerful=20, Quiet=30 -> (value + 1) * 10
        ecomode = int(devicejson['parameters']['ecoMode'])
        value = str((ecomode + 1) * 10)
    elif (widget_key == 'air_swing'):
        # airSwingUD enum: Auto=-1, Up=0, Down=1, Mid=2, UpMid=3, DownMid=4, Swing=5.
        # The selector LevelNames are ordered to match, so level = (value + 1) * 10.
        # When the vertical swing is in Auto, the API keeps the last manual
        # position in airSwingUD and signals Auto through fanAutoMode instead
        # (Both=0 or AirSwingUD=2), so honour fanAutoMode first.
        fan_auto_mode = devicejson['parameters'].get('fanAutoMode')
        if fan_auto_mode in (constants.AirSwingAutoMode.Both.value,
                             constants.AirSwingAutoMode.AirSwingUD.value):
            value = "0"  # Auto
        else:
            airswing = int(devicejson['parameters']['airSwingUD'])
            value = str((airswing + 1) * 10)
    elif (widget_key == 'energy'):
        value = get_historic_data(get_panasonic_guid(device)) # historic data is in kWh, domoticz wants W
        if value.startswith('-255'):
            Domoticz.Log(f"keep previous value of get_historic_data for {device.DeviceID} = {device.sValue}")
            value = device.sValue  # keep previous value
        else:
            # convert the API's daily total into a monotonic Wh counter so the
            # midnight reset stops drawing a negative bar in Domoticz.
            value = common.monotonic_energy(device, value)

    # update value only if value has changed
    if (device.sValue != value):
        device.Update(nValue=power, sValue=value)



def update_accsmart(p, Command, Level, device):
    guid = get_panasonic_guid(device)
    widget_key = get_widget_key(device)
    if (Command == "On"):
        update_device_id(guid, "operate", 1)
        device.Update(nValue=1, sValue="100")
        p.powerOn = 1
    elif (Command == "Off"):
        update_device_id(guid, "operate", 0)
        device.Update(nValue=0, sValue="0")
        p.powerOn = 0
    elif (Command == "Set Level"):
        if (device.nValue != p.powerOn or (device.sValue != Level) and Level != "--"):
            if (widget_key == 'target_temp'):
                update_device_id(guid, "temperatureSet", float(Level))
            if (widget_key == 'mode'):
                operationmode = (Level / 10) - 1
                update_device_id(guid, "operationMode", int(operationmode))
            elif (widget_key == 'fan_speed'):
                fanspeed = (Level / 10) - 1
                update_device_id(guid, "fanSpeed", int(fanspeed))
            elif (widget_key == 'eco_mode'):
                ecomode = (Level / 10) - 1
                update_device_id(guid, "ecoMode", int(ecomode))
            elif (widget_key == 'air_swing'):
                # inverse of the read mapping: value = (Level / 10) - 1
                airswing = int((Level / 10) - 1)
                # go through airSwingVertical (the enum) so set_device runs its
                # fanAutoMode routine: Auto (-1) toggles fanAutoMode instead of
                # just writing a raw airSwingUD that the unit would ignore.
                update_device_id(guid, "airSwingVertical",
                                 constants.AirSwingUD(airswing))
            device.Update(nValue=p.powerOn, sValue=str(Level))

def get_device_hash_guid(device_id):
    for key, value in config.client._device_indexer.items():
        if value == device_id:
            matching_key = key
            break
    return matching_key