# Panasonic CZ-TACG1 Python Plugin for Domoticz
#
# Author: sdamasoc
#
"""
<plugin key="CZ-TACG1" name="Panasonic Airco (CZ-TACG1)" author="sdamasoc" version="2.0.0" externallink="https://www.panasonic.com/global/hvac/air-conditioning/connectivity/comfort-cloud/home-owner.html">
    <description>
        <h2>Panasonic Cloud Control Plugin</h2><br/>
        This is a Domoticz python plugin to communicate through Panasonic Cloud Comfort API.
        <h3>Configuration</h3>
        <p>Just enter your Panasonic Cloud Comfort username and password and everything will be detected automatically.</p>
        <p>You can also configure the update interval to not overload http requests.</p>
        <p>The API version can also be given when an API update is available.</p>
    </description>
    <params>
        <param field="Username" label="Username" width="200px" required="true" default=""/>
        <param field="Password" label="Password" width="200px" required="true" default=""/>
        <param field="Mode1" label="Update every x seconds" width="75px">
            <options>
                <option label="30" value="30" />
                <option label="60" value="60" default="true" />
                <option label="90" value="90" />
                <option label="120" value="120" />
                <option label="150" value="150" />
                <option label="180" value="180" />
                <option label="210" value="210" />
                <option label="240" value="240" />
            </options>
        </param>
        <param field="Mode2" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
        <param field="Mode3" label="API Version" width="60px" required="true" default="1.22.0"/>
    </params>
</plugin>
"""
import Domoticz
import time
import accsmart
import aquarea
import config
import common
import os
# Parameters and Devices are injected into this module's globals by Domoticz at
# runtime. For standalone testing, testPlugin.py injects equivalent mocks before
# calling onStart (see testPlugin.py).

class PanasonicCZTACG1Plugin:
    enabled = True
    powerOn = 0
    last_update = 0

    def __init__(self):
        return

    def onStart(self):
        # set config parameters
        config.update_interval = int(Parameters["Mode1"])
        config.debug_level = Parameters["Mode2"]
        config.api_version = Parameters["Mode3"]
        config.username = Parameters["Username"]
        config.password = Parameters["Password"]
        config.devices = Devices

        Domoticz.Debug("onStart called")
        # 1st try to get last version of the plugin
        config.api_version = common.get_app_version(True)
        try:
            config.client = accsmart.get_client()
        except Exception as e:
            # Panasonic sometimes refuses the login temporarily (HTTP 401/412).
            # Don't crash and don't wipe the existing devices: keep them and let
            # onHeartbeat re-establish the session on its own.
            Domoticz.Error(f"Could not connect to Panasonic Comfort Cloud at startup: {e}")
            Domoticz.Error("Existing devices are kept; will retry on next heartbeat.")
            return
        config.aquarea_token = aquarea.get_aquarea_token()

        if config.debug_level == "Debug":
            # 0: None. All Python and framework debugging is disabled.
            # 1: All. Very verbose log from plugin framework and plugin debug messages.
            # 2: Mask value. Shows messages from Plugin Domoticz.Debug() calls only.
            # https://www.domoticz.com/wiki/Developing_a_Python_plugin#C.2B.2B_Callable_API 
            Domoticz.Debugging(2)

        # get devices list
        panasonic_devices = config.client._groups
        Domoticz.Debug(f"panasonic_devices={panasonic_devices}")

        # loop found devices to create then in domoticz
        nbdevices = len(config.devices)  # (nbdevices:=nbdevices+1) = ++nbdevices

        Domoticz.Log("##################################################################################")
        for x in list(Devices):
            Domoticz.Log(f"Removing existing device: {Devices[x].Name}...")
            Devices[x].Delete()
        Domoticz.Log("##################################################################################")

        for group in panasonic_devices['groupList']:
            groupname = group['groupName']
            for device in group['deviceList']:
                devicename = device['deviceName']
                deviceid = device['deviceGuid']
                deviceType = device['deviceType']

                exist = False
                for x in config.devices:
                    # Domoticz.Debug("x="+str(x)+",DeviceID="+ config.devices[x].DeviceID + ", Name="+config.devices[x].Name + "Dump=" + str(config.devices[x]));
                    # check if there's an unitId > nbdevices
                    if (x > nbdevices):
                        nbdevices = x
                    # check if device already exist in Domoticz
                    if (devicename in config.devices[x].Name):
                        exist = True

                if exist :
                    Domoticz.Log("Device " + devicename + " already exists in domoticz (DeviceID=" + deviceid + ").")
                elif(deviceType == "2"):
                    Domoticz.Log("Aquarea devices (deviceType=" + deviceType + ") IS IN ALPHA MODE") 
                    aquarea.add_device(devicename, nbdevices)
                else :
                    accsmart.add_device(devicename, deviceid, nbdevices)

        onHeartbeat()
        #dump_config_to_log()

        Domoticz.Debug("onStart end")

    def onStop(self):
        Domoticz.Debug("onStop called")
        if os.path.exists(config.token_file_path):
            os.remove(config.token_file_path)
        if os.path.exists(config.aquarea_token_file_path):
            os.remove(config.aquarea_token_file_path)
        if os.path.exists(config.api_version_file_path):
            os.remove(config.api_version_file_path)
        Domoticz.Debug("onStop end")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called, Status=" + str(Status))

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")
        accsmart.dump_http_response_to_log(Data)

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("Command received for device Name=" + config.devices[Unit].Name + "(deviceId=" + config.devices[
            Unit].DeviceID + ") U=" + str(Unit) + " C=" + str(Command) + " L=" + str(Level) + " H=" + str(Hue))

        # same accsmart/aquarea split as onHeartbeat (accsmart device IDs are short,
        # e.g. 'CS-BZ60CKE+E299301492'; aquarea IDs are much longer)
        if len(config.devices[Unit].DeviceID) < 70:
            # handle accsmart
            accsmart.update_accsmart(self, Command, Level, config.devices[Unit])
        else:
            # handle aquarea
            aquarea.update_aquarea(self, Command, Level, config.devices[Unit])


    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(
            Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("Connection " + Connection.Name + " closed.")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat started...")
        update_interval = config.update_interval
        Domoticz.Debug("interval since last update = " + str(time.time() - self.last_update) + ", update_interval = " + str(update_interval))
        if time.time() - self.last_update < update_interval:
            Domoticz.Debug("update interval not reached")
            return

        # if the Comfort Cloud session could not be established at startup
        # (e.g. Panasonic temporarily refused the login with a 401/412), try to
        # re-establish it here so the plugin recovers on its own. Throttled by
        # update_interval to avoid hammering Panasonic's login endpoint.
        if config.client is None:
            try:
                Domoticz.Log("Comfort Cloud session not established, trying to reconnect...")
                config.client = accsmart.get_client()
            except Exception as e:
                Domoticz.Error(f"Reconnect to Panasonic Comfort Cloud failed, will retry: {e}")
                self.last_update = time.time()
                return

        previous_id = None
        deviceid = None
        devicejson = None
        for x in config.devices:
            deviceid = config.devices[x].DeviceID
            if len(deviceid) < 70:
                if previous_id != deviceid:
                    # one network call per unique device; a powered-off unit makes
                    # Panasonic answer HTTP 500 "Adapter Communication error" -> None
                    devicejson = accsmart.get_device_by_id(deviceid)
                if devicejson is None or devicejson.get('parameters') is None:
                    # device unreachable (e.g. powered off): grey out the widget
                    accsmart.set_reachable(config.devices[x], False)
                    previous_id = deviceid
                    continue
                accsmart.set_reachable(config.devices[x], True)
                accsmart.handle_accsmart(config.devices[x], devicejson)
            else:
                if previous_id != deviceid:
                    devicejson = aquarea.load_device_details(deviceid)
                if devicejson is None:
                    accsmart.set_reachable(config.devices[x], False)
                    previous_id = deviceid
                    continue
                accsmart.set_reachable(config.devices[x], True)
                aquarea.handle_aquarea(config.devices[x], devicejson)
            previous_id = deviceid



        # Domoticz.Debug("Device ID:       '" + str(config.devices[x].ID) + "'")
        # Domoticz.Debug("Device Name:     '" + config.devices[x].Name + "'")
        # Domoticz.Debug("Device nValue:    " + str(config.devices[x].nValue))
        # Domoticz.Debug("Device sValue:   '" + config.devices[x].sValue + "'")
        # Domoticz.Debug("Device LastLevel: " + str(config.devices[x].LastLevel))
        self.last_update = time.time()
        Domoticz.Debug("onHeartbeat ended.")


global _plugin
_plugin = PanasonicCZTACG1Plugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)


def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)


def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)


def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)


def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Dumps the config to debug log
def dump_config_to_log():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(config.devices)))
    for x in config.devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(config.devices[x]))
        Domoticz.Debug("Device ID:       '" + str(config.devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + config.devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(config.devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + config.devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(config.devices[x].LastLevel))
    return
