[![CodeQL](https://github.com/sdamasoc/domoticz_panasonic_CZ-TACG1/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/sdamasoc/domoticz_panasonic_CZ-TACG1/actions/workflows/codeql-analysis.yml)

# Domoticz python plugin for Panasonic Comfort Cloud devices
A Python plugin for Domoticz to communicate with Panasonic Comfort Cloud API.
It was designed for CZ-TACG1 WiFi adapter but should work with other Panasonic Cloud Comfort devices such as Aquarea devices.

# Getting started
If you don't have git:
```
sudo apt-get update
sudo apt-get install git
```
Goto to the plugins directory of your domoticz installation folder and clone this repository:
```
cd domoticz/plugins
git clone https://github.com/sdamasoc/domoticz_panasonic_CZ-TACG1.git domoticz_panasonic_CZ-TACG1
```
So in this case the directory structure should now be: domoticz/plugins/domoticz_panasonic_CZ-TACG1/plugin.py

> **Note:** on recent Domoticz versions and on the Docker images, the plugins directory is `userdata/plugins` (e.g. `/opt/domoticz/userdata/plugins/`). Clone the plugin there instead. Each plugin must sit in its own subfolder with `plugin.py` directly inside it, otherwise Domoticz won't detect it.

Next, you need to restart Domoticz so that it will find the plugin:
```
 sudo systemctl restart domoticz.service
```
or
```
sudo service domoticz.sh restart
```
From here the plugin should be able to be set-up from the Domoticz interface. Go to the hardware page and look in the dropdown, you should find "Panasonic Airco (CZ-TACG1)"

Then, fill your email, password and click on "Add"

If you run Linux and the plugin does not show up in the hardware list, you may have to make the plugin.py file executable. Go to the directory and execute the command:
```
 chmod +x domoticz_panasonic_CZ-TACG1/plugin.py
```

https://www.domoticz.com/wiki/Using_Python_plugins

# Requirements
- This plugin requires python v3.8 (or greater)
- It depends on the python `requests` module (to talk to the Panasonic cloud) and `beautifulsoup4`/`bs4` (to parse the Panasonic login page). These are listed in `requirements.txt`; install them as root with:
  ```
  pip3 install -r requirements.txt
  ```
- If you run Domoticz in Docker, install them into the interpreter Domoticz uses (often a virtualenv). For example:
  ```
  docker exec <container> /opt/venv/bin/pip install -r /opt/domoticz/userdata/plugins/domoticz_panasonic_CZ-TACG1/requirements.txt
  ```
  Note that packages installed this way are lost if the container is recreated, so prefer baking them into a custom image (e.g. a `RUN pip install -r requirements.txt` in your Dockerfile).

- You need a panasonic id associated with your devices to be able to use this plugin:
1. Create a new panasonic account here: [Panasonic ID Registration](https://csapl.pcpf.panasonic.com/Account/Register001?lang=en)
2. Verify email using the link sent to the email id specified
3. Sign into the Panasonic Comfort Cloud app on your smart device using the newly created Panasonic ID
4. Agree to the terms and conditions displayed in app
5. Agree to the privacy notice displayed in app
6. You should now be on the home screen of the App
7. Click the "+" button
8. Choose "Air Conditioner"
9. Use the device ID from the original device package
10. Enter the device password you used when originally setting up the device
11. In step 3: Enter a name for the aircon
12. Click Send Request
13. Log out of the app
14. Sign in with the original email account in the Panasonic Comfort Cloud App
15. Click the Device you've requested sharing for
16. Click the hamburger menu and expand the "Owner" menu item, click "User list"
17. You should now see an id with a waiting approval status
18. Click the "Waiting Approval" button
19. Select the "Allow both monitoring and controlling air conditioner" permission
20. Confirm
21. The waiting for approval button should have disappeared and replaced with a blue check icon
22. Use the newly created id in the homekit accessory configuration

(instructions copied from codyc1515: https://github.com/codyc1515/homebridge-panasonic-air-conditioner/)

Aquarea support inspired by: https://github.com/Hernas/homebridge-panasonic-heat-pump 

# Compatibility
This script was tested with:
* Domoticz Version: 2023.2
* Python Version: 3.10.12 and 3.11
* Ubuntu: 22.04.3 LTS (and the Domoticz Docker image)

# Troubleshooting
- **The plugin doesn't appear in the hardware dropdown:** check it's in the right plugins folder (`userdata/plugins/<name>/plugin.py` on recent/Docker installs), that the dependencies are installed for the interpreter Domoticz uses (see Requirements), and look at the Domoticz log at startup for the exact error.
- **`401 ... Login ID or password is incorrect`:** use your Panasonic **Comfort Cloud account** email and password (the ones you log in with in the mobile app) — *not* the device ID / device password printed on the unit.
- **`401 ... New version app has been published`:** the API version is too old. The plugin auto-detects the latest Comfort Cloud version from the App Store; you can also override it via the "API Version" hardware field.
- **`412 Precondition Failed` (code 41201):** an intermittent, server-side Panasonic condition (often temporary throttling after many logins). Wait ~30–60 min and retry; avoid restarting the plugin in a loop.
- **Air conditioner powered off / unplugged:** the API returns `500 Adapter Communication error`. The plugin handles this gracefully — it keeps the widgets with their last known values (no error spam) and resumes automatically when the unit is back.

# To test this plugin outside Domoticz
A mock `Domoticz` module and a `testPlugin.py` harness let you run the plugin standalone (no editing of `plugin.py` needed):
1. Rename `.Domoticz.py` to `Domoticz.py`
2. Put your Panasonic account credentials in `Domoticz.py` (and optionally adjust the `Mode3` API version)
3. Run the test harness: `python3 testPlugin.py`

`testPlugin.py` injects `Parameters` and `Devices` into the plugin module just like Domoticz does at runtime.