# Changelog

All notable changes to Frame Energy Art. Versions 1.1.0 to 1.2.0 were released
on 11 and 12 October 2026.

## 1.3.1

### New

- **List TV pictures** (`frame_energy.list_images`): shows the pictures in My
  Photos with their IDs. Nothing is changed.
- **Delete TV pictures** (`frame_energy.delete_images`): deletes only the IDs
  you enter. Useful on older Frames that can't delete pictures from the TV
  menu or SmartThings.

### Fixed

- An old picture the TV refuses to delete is no longer retried forever. After
  ten refusals in a row it is dropped with a warning, and the error on the
  status sensor goes away.

## 1.3.0

### New

- The picture updates by itself, every 15 minutes by default. Change it in
  **Configure → Update the picture by itself**: 5, 10, 15, 30 or 60 minutes,
  or Manual. Updates run on the clock and start one minute after Home
  Assistant starts. An automation is no longer needed.
- An update is skipped if a picture was made less than half an interval ago,
  so an old automation and the built-in updates do not upload twice.
- Integration icon.

### Fixed

- If the TV kept the connection open but never answered (for example while an
  **Allow** message waited on the screen), an update could hang for minutes.
  Now the connection is closed when the two minutes are over, and the error
  says to look for an Allow message on the TV.

### Changed

- Ready for the HACS default store: issue tracker link in the manifest and
  automatic Hassfest, HACS and test checks on GitHub.
- Every release now has a `frame_energy.zip` file. HACS installs from it.
- If you use the example automation, either turn it off or set the update
  setting to Manual.

## 1.2.1

### Fixed

- An update that got stuck while talking to the TV could block all later
  updates for hours. The picture stayed old and the log showed nothing. Now the
  whole talk with the TV is limited to two minutes, and a stuck update ends
  with an error.
- If an upload is stopped or cut off after the TV has confirmed the picture,
  its ID is kept. The picture is deleted at a later update and does not stay on
  the TV.

### Changed

- The example automation uses `mode: restart` instead of `mode: single`. If you
  copied the old example, change the mode.
- New troubleshooting entry for a picture that stops updating.

## 1.2.0

- The Tuscan painting is built into the integration, so it works right after
  installation.
- One car or no car: an empty column is not drawn and the row is centred.
- Optional "Show update time" (off by default).

## 1.1.2

- If the connection drops after the TV confirms a picture, its ID is still
  saved, so the picture can be deleted later.
- Old pictures that could not be deleted are never forgotten. Up to 5 are
  tried per update and the rest wait.
- The last delete problem is shown on the status sensor.
- Docs: pairing text, background picture steps, local and cloud data, LG not
  supported yet.

## 1.1.1

- A new picture no longer switches the TV to Art Mode while someone is watching
  TV. It is shown at once only if Art Mode is already on.

## 1.1.0

First public version.

- Own connection to Samsung The Frame. No other integration is needed.
- The TV confirms every picture before it counts as delivered.
- Only the previous picture from this project is deleted, so pictures do not
  pile up on the TV. Personal photos are never touched.
- Car names, monograms and the text under the weather are set in the form.
- Configure button to change sensors, names and the TV without removing the
  integration.
- No clock on the picture, so it looks like a painting.
