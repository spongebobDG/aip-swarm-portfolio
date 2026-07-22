# AIP Fleet Foxglove Panels

Custom Foxglove Studio extension for the AIP swarm driving system.

## Panels

- **AIP E-Stop**: Fleet-wide emergency stop button → publishes `OverrideCommand(ESTOP, "*")` to `/fleet/override`. Clear E-Stop requires confirmation.
- **AIP Override**: Per-vehicle override control (PAUSE / RESUME / MANUAL drive). Wildcard `"*"` requires confirmation. Manual drive streams at UI event rate.

## Install

```bash
npm install
npm run build
npm run local-install   # installs into Foxglove Studio
```

Or import the packaged `.foxe` file via Foxglove Studio → Extensions → Import.
