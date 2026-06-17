# Visual Regression Suite (AUT-34)

Diese Suite bildet die Monitor-L1/L2-Layouts auf den Zielauflösungen aus `AUT-34` ab:

- 1280x720
- 1366x768
- 1536x864
- 1920x1080
- 2560x1440

## Abgedeckte Targets

- `MonitorView` L1 (Full Page)
- `ZoneTileCard` (Komponenten-Snapshot)
- `MonitorView` L2 (Full Page)
- `SensorCard` Normalwert
- `SensorCard` Overflow/Langtext

## Ausführen

```bash
npm run test:visual
```

## Baselines aktualisieren

```bash
npm run test:visual:update-snapshots
```

Die Screenshots werden unter `tests/e2e/visual/__screenshots__/` gespeichert und sind Teil des Repositories.
