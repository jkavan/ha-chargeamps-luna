"""Shared Home Assistant fixtures; all credentials and chargers are synthetic."""

from copy import deepcopy

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow loading the custom integration in Home Assistant tests."""


@pytest.fixture
def raw_chargers():
    return deepcopy(
        [
            {
                "id": "test-luna",
                "name": "Luna",
                "productName": "LUNA",
                "installedFirmwareVersion": "1.7.5",
                "availableFirmwareVersion": "1.8.0",
                "lastHeartbeat": None,
                "offlineSince": None,
                "firmwareLastUpdated": "2025-10-09T11:18:02.6633333",
                "wifiSignalStrength": None,
                "chargePointStatus": "Online",
                "ownerReadOnly": False,
                "ocppEnabled": False,
                "wifiPassword": "PRIVATE_WIFI",
                "ownerEmail": "PRIVATE_EMAIL",
                "unrelatedSetting": {"preserve": True},
                "connectors": [
                    {
                        "connectorId": 1,
                        "mode": "On",
                        "ocppStatus": "Available",
                        "isCharging": False,
                        "errorCode": "NoError",
                        "totalConsumptionKwh": 3.945984,
                        "totalConsumptionRaw": 3945984.0,
                        "userCurrent": 16,
                        "defaultNfcTagId": "PRIVATE_TAG",
                    }
                ],
            }
        ]
    )


@pytest.fixture
def config_data():
    return {
        "username": "test@example.test",
        "password": "test-password",
        "url": "https://my.charge.space",
        "refresh_interval": 15,
    }
