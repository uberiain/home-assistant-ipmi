# IPMI connector (UB) for Home Assistant

This connector is based on the work of https://github.com/ateodorescu/home-assistant-ipmi adding
test for FRU rc ) Problem with my AsRockRack systems.

## What is IPMI?
IPMI (Intelligent Platform Management Interface) is a set of standardized specifications for
hardware-based platform management systems that makes it possible to control and monitor servers centrally.

## Home Assistant integration
This integration allows you to monitor and control servers that support IPMI.
It can connect to your servers in this way:

- via the `ipmi-server` addon from [here](https://github.com/uberiain/ipmi-addon) which is
	basically a wrapper for `ipmitool`.

## Installation
Install it via HACS or just copy the `custom_components` folder in your home assistant `config` folder.
Restart HASS and then add the `ipmi` integration.

## What does the integration?
The component allows you to configure multiple servers that have unique aliases.
For each server that you configure the component will add all available `sensors`, 5 `actions` and 1 `switch`.

The following `sensors` will be added:
- all temperature sensors
- all fan sensors
- all voltage sensors
- all power sensors

The following `actions` are added:
- power on
- power off
- power cycle
- power reset
- soft shutdown

The `switch` allows you to turn on the server and shut it down gracefully.

There is a `send command` service available too, which allows you to send custom commands
to the server. This works only when the `ipmi-server` addon is used.
