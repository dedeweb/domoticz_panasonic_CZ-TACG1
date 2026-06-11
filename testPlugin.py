import Domoticz  # mock module (rename .Domoticz.py to Domoticz.py and set your credentials)
import plugin
import config
import aquarea
import accsmart

# Domoticz normally injects Parameters and Devices as globals into the plugin
# module at runtime. Reproduce that here for standalone testing.
plugin.Parameters = Domoticz.Parameters
plugin.Devices = Domoticz.Devices


####################
# start test calls #
####################
p1 = plugin.PanasonicCZTACG1Plugin()
p1.onStart()
