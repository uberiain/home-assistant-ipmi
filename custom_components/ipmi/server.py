from __future__ import annotations

import async_timeout
import requests
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Mapping, cast
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

# The domain of your component. Should be equal to the name of your component.
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ALIAS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)


from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    dispatcher_send,
)

from .const import (
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    CONF_ADDON_PORT,
    CONF_IPMI_SERVER_HOST,
    CONF_IGNORE_CHECKSUM_ERRORS,
    CONF_IGNORE_FRU_RC,
    DOMAIN,
    PLATFORMS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_NEW_SENSOR_SIGNAL,
    IPMI_UPDATE_SENSOR_SIGNAL,
    USER_AVAILABLE_COMMANDS,
    INTEGRATION_SUPPORTED_COMMANDS,
    SERVERS,
    DISPATCHERS,
    IPMI_DEV_INFO_TO_DEV_INFO,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class IpmiDeviceInfo:
    """Device information for the IPMI server."""

    device: dict[str, str] = None
    power_on: bool | False = False
    sensors: dict[str, str] = None
    states: dict[str, str] = None
    alias: str = None


class IpmiServer:
    """Stores the data retrieved from IPMI.

    For each entity to use, acts as the single point responsible for fetching
    updates from the server.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str | None,
        connection_data: dict,
    ) -> None:
        """Initialize the data object."""

        self._entry_id = entry_id
        self.hass = hass
        self._host = connection_data.get("host")
        self._port = connection_data.get("port")
        self._alias = connection_data.get("alias")
        self._username = connection_data.get("username")
        self._password = connection_data.get("password")
        self._kg_key = connection_data.get("kg_key")
        self._privilege_level = connection_data.get("privilege_level")
        self._addon_url = (
            connection_data.get("ipmi_server_host")
            + ":"
            + connection_data.get("addon_port")
        )
        self._addon_interface = connection_data.get("addon_interface")
        self._addon_extra_params = connection_data.get("addon_extra_params")
        self._ignore_checksum_errors = connection_data.get(
            CONF_IGNORE_CHECKSUM_ERRORS, False
        )
        self._ignore_fru_rc = connection_data.get("ignore_fru_rc")

        # when addon runs in dev mode (local web server)
        #         self._addon_url += '/repositories/home-assistant-addons/ipmi-server/rootfs/app/public'

        self._device_info: IpmiDeviceInfo | None = None
        self._known_sensors = []

    @property
    def name(self) -> str:
        """Return the name of the IPMI server."""
        return self._alias or f"IPMI-{self._host}"

    @property
    def device_info(self) -> IpmiDeviceInfo:
        """Return the device info for the IPMI server."""
        return self._device_info

    def getFromAddon(self, path: str | None):
        response = None

        try:
            params = {
                "host": self._host,
                "port": self._port,
                "user": self._username,
                "password": self._password,
            }

            if self._addon_interface is not None and self._addon_interface != "auto":
                params["interface"] = self._addon_interface

            if self._kg_key:
                params["kg_key"] = self._kg_key

            if self._privilege_level:
                params["privilege_level"] = self._privilege_level

            if self._addon_extra_params:
                params["extra"] = self._addon_extra_params
            
            params["ignore_fru_rc"] = self._ignore_fru_rc
            
            url = self._addon_url

            if path is not None:
                url += "/" + path

            _LOGGER.debug(url)
            _LOGGER.debug(params)
            ipmi = requests.get(url, params=params)
            response = ipmi.json()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug(err)
            _LOGGER.debug("'ipmi-server' addon is not available. Let's use RMCP.")

        return response

    def generateId(self, name: str):
        id = re.sub("[^A-Za-z0-9 _]+", "", name)
        id = id.replace(" ", "_").lower()

        return id

    def update(self) -> None:
        info = None

        json = self.getFromAddon(None)

        if json is not None:
            if not json["success"]:
                _LOGGER.error(json["message"])
                json = None
        else:
            _LOGGER.error( "Addon not available, cannot update IPMI data")

        if json is not None:
            info = IpmiDeviceInfo()
            info.device = json["device"]
            info.power_on = json["power_on"]
            info.sensors = json["sensors"]
            info.states = json["states"]
            info.alias = self._alias
            self._device_info = info
        else:
            self._device_info = None

        if info is not None:
            new_sensors = []
            # _LOGGER.critical(repr(info))
            # _LOGGER.critical(self._known_sensors)

            if len(info.states) == 0:
                self._known_sensors.clear()
            else:
                to_remove = []
                for id in self._known_sensors:
                    if id not in info.states:
                        to_remove.append(id)
                for id in to_remove:
                    self._known_sensors.remove(id)

                for id in info.states:
                    if self._known_sensors.count(id) == 0:
                        new_sensors.append(id)

                if len(new_sensors) > 0:
                    dispatcher_send(
                        self.hass, IPMI_NEW_SENSOR_SIGNAL.format(self._entry_id)
                    )

    def is_known_sensor(self, id: str) -> bool:
        return self._known_sensors.count(id) > 0

    def add_known_sensor(self, id: str) -> None:
        if self._known_sensors.count(id) == 0:
            self._known_sensors.append(id)

    def power_on(self) -> None:
        json = self.getFromAddon("power_on")
        if json is None:
            _LOGGER.error( "Addon not available 1 cannot execute power_on")

    def power_off(self) -> None:
        json = self.getFromAddon("power_off")
        if json is None:
            _LOGGER.error( "Addon net available, cannot execute power_off")

    def power_cycle(self) -> None:
        json = self.getFromAddon("power_cycle")
        if json is None:
            _LOGGER.error( "Addon not available, cannot execute power_cycle")

    def power_reset(self) -> None:
        json = self.getFromAddon("power_reset")
        if json is None:
            _LOGGER.error( "Addon net available 1 cannot execute power_reset")

    def soft_shutdown(self) -> None:
        json = self.getFromAddon("soft_shutdown")
        if json is None:
            _LOGGER.error("Addon not available, cannot execute soft shutdown")

    def send_command(self, command: str, ignore_errors: bool) -> str:
        cmd = command.replace("$host$", self._host)
        cmd = cmd.replace("$port$", str(self._port))
        cmd = cmd.replace("$username$", self._username)
        cmd = cmd.replace("$password$", self._password)

        uri_encoded = requests.utils.quote(cmd)
        response = self.getFromAddon("command?params=" + uri_encoded)

        if response is None:
            err = "Error executing command: {}", command.format(command)
            if ignore_errors:
                _LOGGER.error(err)
            else:
                raise Exception(err)

        if response["success"] == False:
            err = "Error executing command: {}, Error: {}".format(
                command, response["output"]
            )
            if ignore_errors:
                _LOGGER.error(err)
            else:
                raise Exception(err)

        return response["output"]
