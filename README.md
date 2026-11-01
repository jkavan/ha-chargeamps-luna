# Charge Amps Luna for Home Assistant

Home Assistant integration for Charge Amps Luna with charger status and basic
control. Installable through HACS. No API key is required.

Tested on Home Assistant 2026.10.4.

## Installation

1. Open **HACS > three-dot menu > Custom repositories**.
2. Add `https://github.com/jkavan/ha-chargeamps-luna` and choose **Integration**.
3. Download **Charge Amps Luna** and restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration > Charge Amps Luna**.

## Configuration

| Setting | Value |
| --- | --- |
| Username | Your Charge Amps account email |
| Password | Your Charge Amps account password |
| Portal URL | `https://my.charge.space` by default |
| Refresh interval | 15 minutes by default |

Use the default refresh interval or a longer one where possible. Avoid short
intervals and frequent manual refreshes to reduce unnecessary load on Charge Amps' servers.

To change these settings, open the integration entry's three-dot menu and select
**Reconfigure**. Leave the password blank to keep the current one.

## Entities and controls

For a charger named `Luna`, the default entities are:

| Entity | Purpose |
| --- | --- |
| `sensor.luna_status` | Charger status, such as Online or Offline |
| `sensor.luna_connector_status` | Connector status, such as Available or Charging |
| `binary_sensor.luna_charging` | Whether the charger is charging |
| `select.luna_charging_mode` | Off / Schedule / Always on |
| `button.luna_refresh_status` | Refresh status immediately |

**Schedule** uses a schedule already configured in the Charge Amps portal.
**Always on** permits charging, subject to vehicle, RFID, and load-balancing
settings. Mode control is unavailable when the charger is offline or the account
has read-only access.

### Automation examples

Refresh status:

```yaml
action: chargeamps_luna.refresh
```

Set the charging mode:

```yaml
action: select.select_option
target:
  entity_id: select.luna_charging_mode
data:
  option: "Schedule"  # "Off", "Schedule", or "Always on"
```

Entity IDs may differ if renamed or already in use.

## Limitations

- Tested with a single Luna. Multiple chargers have not been tested as I only have one, but multiple chargers should work.
- Uses the Charge Amps website's undocumented interface. Portal changes may
  require an integration update.
- Status comes from the cloud, not directly from the charger.

## Development

This project is mostly vibecoded, but all AI-written code and changes have been
reviewed and checked.

Use Python 3.14.2 or newer in a virtual environment:

```sh
python -m pip install -r requirements-dev.txt
ruff check custom_components tests tools
pytest
```

On Windows, run `python tools/run_tests.py` instead of `pytest`.

## Disclaimer

This project is not affiliated with, endorsed by, or supported by Charge Amps AB.
All trademarks belong to their respective owners.
