# Home Assistant Frame Energy Art

A local Home Assistant integration that puts solar generation, home consumption,
battery levels, electric vehicles and weather onto a Tuscan painting for Samsung
The Frame's Art Mode.

Created by **Ilja Dulushkov** ([@ediplomat](https://github.com/ediplomat)), MEng Autonomous Robotics student at NMITE, Hereford.

![Example artwork with fictional data](docs/demo.jpg)

The idea: it should look like a painting on the wall, not like a tablet with a
dashboard. Numbers sit in the sky in the painting's own colours and a gallery
serif; there are no panels, boxes or clocks. Vehicles are shown as monograms
(for example **T** and **H**) rather than brand logos.

The painting is generated as a 1920 × 1080 JPEG with today's date. It reads
existing Home Assistant states; it does not wake or poll the vehicles.

## Status and compatibility

Experimental. The home-specific version was tested with Home Assistant Green
and a Samsung The Frame 43-inch (2019). This repository provides generic entity
placeholders and a demo containing fictional readings. Other TV models and
Home Assistant versions have not been verified.

This is a companion to an existing third-party **Samsung Frame Art** custom
integration with domain `samsung_frame`. That integration must provide
`samsung_frame.update` and accept an `image_path` argument. It handles pairing,
authentication and uploading to the television. Samsung's standard media-player
integration alone is insufficient. The uploader is not bundled here.

**Storage limitation (separate uploader only):** the tested `samsung_frame`
uploader adds a new TV image for each update.
There is no automatic retention or deletion in this project. A 15-minute
schedule can add 96 images per day. Start with manual updates and monitor the
TV's storage before enabling frequent unattended updates. Do not use a
“delete all images” command to clean up your personal artwork.

## Manual installation

1. Install and pair a compatible `samsung_frame` integration. Confirm that its
   `samsung_frame.update` action accepts an explicit `image_path`.
2. Copy `custom_components/frame_energy` into your Home Assistant
   `/config/custom_components/` directory.
3. Copy `assets/tuscan_background.jpg` to
   `/media/frame_assets/tuscan_background.jpg`.
4. Restart Home Assistant. In **Settings → Devices & services → Add integration**,
   add **Frame Energy Art**.
5. Replace the example entity IDs in the form with your own sensors. The
   background and output paths are also configurable. The output must be a
   different file from the background.
6. Disable the Samsung uploader's own date, calendar and weather overlays so
   it does not draw a second set of panels on top.
7. Run **Frame Energy Art: Render** (`frame_energy.render`) from Developer tools
   → Actions. Check the generated image, the uploader's logs and the TV.
8. If your uploader has an image filename setting, select `frame_energy_live.jpg`
   after the first render, with `/media/frame` as the image folder.

No token or password belongs in this repository. The existing TV integration
manages its own credentials. Installation by copying files works today. The repository also contains
`hacs.json`, so once it is public it can be added to HACS as a custom
repository (Integration).

## Built-in uploader (experimental)

Instead of the separate `samsung_frame` integration you can let this
integration talk to the TV directly. Enter the TV's IP address during setup or
later in **Configure**, press Submit and choose **Allow** on the TV. The TV's
token is kept in Home Assistant's own storage.

Each update then:

1. uploads the new picture and waits for the TV to confirm it;
2. shows it in Art Mode;
3. deletes this project's previous picture (and only that — personal artwork
   and photos are never touched).

If the TV does not confirm, the render action fails and the status sensor's
`error` attribute says why. Pictures that could not be deleted are retried on
the next update (`pending_deletes`). Tested only with a 2019 Frame (43-inch).
Leave the IP address empty to keep the previous behaviour with `samsung_frame`.

## Entity mapping

All fields below are configurable during setup. Names in this table are
placeholders, not automatically created sensors.

| Field | Example entity | Expected value |
| --- | --- | --- |
| Solar | `sensor.solar_power` | W or kW |
| Home | `sensor.home_power` | W or kW |
| Battery | `sensor.home_battery_percentage` | 0–100% |
| Battery charge | `sensor.battery_charging_power` | W or kW, positive |
| Battery discharge | `sensor.battery_discharging_power` | W or kW, positive |
| Tesla | `sensor.tesla_battery_level` | 0–100% |
| Tesla power | `sensor.tesla_charging_power` | W or kW |
| Hyundai | `sensor.hyundai_battery_level` | 0–100% |
| Hyundai power | `sensor.hyundai_charging_power` | W or kW |
| Weather | `weather.home` | Weather entity with daily forecasts |

Vehicle names, their monograms (one or two letters) and the text under the
weather (for example your village) are set in the integration's form. Power units come from sensor attributes.
Missing, non-finite or unsupported values display a dash, and percentages
outside 0–100 are rejected. Existing sensor values can be stale; the integration
does not verify their freshness; the status sensor shows when the picture was
last generated.

## Optional schedule

After a successful manual test and a decision about TV storage, use
[examples/automation.yaml](examples/automation.yaml) in the automation YAML
editor. It runs every 15 minutes and one minute after Home Assistant starts.
No schedule is installed automatically by the integration.

## Troubleshooting

- **No Frame Energy Art in Add integration:** check the directory name and
  restart Home Assistant after copying the files.
- **Missing background:** check the absolute path and file permissions.
- **Dashes instead of readings:** check entity IDs, availability and units.
- **Missing forecast:** the selected weather entity must support daily forecasts.
  Current weather and energy rendering can continue without a forecast.
- **Image generated but TV unchanged:** check `samsung_frame` logs and pairing.
  The tested uploader can log errors without returning an exception.
- **Status:** `sensor.frame_energy_last_generated` records successful JPEG
  generation. Its `last_upload_attempt` attribute means an attempt, not confirmed
  delivery. Its `error` attribute records errors propagated to this integration.

Only one config entry is supported. Sensors, paths and the TV can be changed
later with **Configure** on the integration. To stop updates, disable your automation. To return to
ordinary artwork, select it through your existing Samsung integration or TV.

## Development

Pillow draws text and icons on the background and atomically replaces the output
file. Rendering runs in Home Assistant's executor; a lock prevents simultaneous
renders. The included DejaVu Serif font provides consistent typography.

Run the local renderer checks with:

```sh
python -m pip install 'Pillow>=10.0.0'
python -m unittest discover -s tests
```

## Support

Shared as is, from one home setup. Issues and pull requests are welcome, but
there is no promise of support or of compatibility with other TV models.

## Licence and assets

Original integration code and documentation: MIT, see [LICENSE](LICENSE).
The bundled font retains its separate Bitstream Vera / DejaVu notices in
[FONT_LICENSE.txt](FONT_LICENSE.txt); it is not relicensed under MIT.
The Tuscan background is a generated illustration supplied as a sample asset;
no exclusive copyright claim is made for it. You may substitute artwork you
have permission to use. Samsung, Tesla, Hyundai and Home Assistant names belong
to their respective owners. This project is not affiliated with them.
