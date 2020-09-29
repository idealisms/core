"""Interfaces with the myLeviton API for Decora Smart WiFi products."""

import logging

# pylint: disable=import-error
from decora_wifi import DecoraWiFiSession
from decora_wifi.models.person import Person
from decora_wifi.models.residence import Residence
from decora_wifi.models.residential_account import ResidentialAccount
import voluptuous as vol

from homeassistant.components.fan import (
    PLATFORM_SCHEMA,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_OFF,
    SUPPORT_SET_SPEED,
    FanEntity,
)

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

SPEED_MAX = "max"
SPEED_LIST = [SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH, SPEED_MAX]
SPEED_TO_VALUE = {SPEED_LOW: 25, SPEED_MEDIUM: 50, SPEED_HIGH: 75, SPEED_MAX: 100}
VALUE_TO_SPEED = dict([reversed(i) for i in SPEED_TO_VALUE.items()])

SUPPORTED_FEATURES = SUPPORT_SET_SPEED

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)

NOTIFICATION_ID = "leviton_notification_fan"
NOTIFICATION_TITLE = "myLeviton Decora Wifi Fan Setup"

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Decora WiFi platform."""

    email = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    session = DecoraWiFiSession()

    try:
        success = session.login(email, password)

        # If login failed, notify user.
        if success is None:
            msg = "Failed to log into myLeviton Services. Check credentials."
            _LOGGER.error(msg)
            hass.components.persistent_notification.create(
                msg, title=NOTIFICATION_TITLE, notification_id=NOTIFICATION_ID
            )
            return False

        # Gather all the available devices...
        perms = session.user.get_residential_permissions()
        all_switches = []
        for permission in perms:
            if permission.residentialAccountId is not None:
                acct = ResidentialAccount(session, permission.residentialAccountId)
                for residence in acct.get_residences():
                    for switch in residence.get_iot_switches():
                        all_switches.append(switch)
            elif permission.residenceId is not None:
                residence = Residence(session, permission.residenceId)
                for switch in residence.get_iot_switches():
                    all_switches.append(switch)

        # DW4SF is a fan switch, not a light.
        add_entities(DecoraWifiFan(sw) for sw in all_switches if sw.model == 'DW4SF')
    except ValueError:
        _LOGGER.error("Failed to communicate with myLeviton Service")

    # Listen for the stop event and log out.
    def logout(event):
        """Log out..."""
        try:
            if session is not None:
                Person.logout(session)
        except ValueError:
            _LOGGER.error("Failed to log out of myLeviton Service")

    hass.bus.listen(EVENT_HOMEASSISTANT_STOP, logout)


class DecoraWifiFan(FanEntity):
    """Representation of a Decora WiFi fan switch."""

    def __init__(
        self, switch
    ) -> None:
        """Initialize the entity."""
        self._switch = switch

    @property
    def unique_id(self):
        """Return the unique id of this fan."""
        return self._switch.id

    @property
    def name(self) -> str:
        """Get entity name."""
        return self._switch.name

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._switch.power == 'ON'

    @property
    def speed(self) -> str:
        """Return the current speed."""
        speed = VALUE_TO_SPEED.get(self._switch.brightness)
        if speed is None:
          _LOGGER.error("Unknown speed: {}".format(self._switch.brightness))
          return SPEED_MEDIUM
        return speed

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        return SPEED_LIST

    def turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn on the fan."""
        attribs = {"power": "ON"}
        if speed is not None:
          attribs['brightness'] = SPEED_TO_VALUE[speed]
        try:
            self._switch.update_attributes(attribs)
        except ValueError:
            _LOGGER.error("Failed to turn on myLeviton fan")

    def turn_off(self, **kwargs) -> None:
        """Turn off the fan."""
        attribs = {"power": "OFF"}
        try:
            self._switch.update_attributes(attribs)
        except ValueError:
            _LOGGER.error("Failed to turn off myLeviton fan")

    def set_speed(self, speed: str) -> None:
        """Set the speed of the fan."""
        attribs = {
          "power": "ON",
          "brightness": SPEED_TO_VALUE[speed],
        }
        try:
            self._switch.update_attributes(attribs)
        except ValueError:
            _LOGGER.error("Failed to set the speed of myLeviton fan")

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORTED_FEATURES

    def update(self):
        """Fetch new state data for this switch."""
        try:
            self._switch.refresh()
        except ValueError:
            _LOGGER.error("Failed to update myLeviton fan data")
