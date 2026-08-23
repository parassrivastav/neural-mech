# Neural Mech

A dependency-free asset registry with a live HVAC-001 digital twin simulator.

Run it with:

```sh
python3 server.py
```

Then open <http://127.0.0.1:8000>. The Assets page is available at `/`, `/home`,
and `/assets`; the HVAC asset links to `/digital-twin/HVAC-001`.

The digital twin polls its built-in simulator every second. Current telemetry and
the latest 60 readings are available as JSON at:

```text
GET /api/assets/HVAC-001/telemetry
```

Select a bounded history with `?range=1m`, `?range=1h`, or `?range=1d`.
Responses contain approximately 60, 120, and 144 points respectively, plus
central engineering baseline and unit metadata for every numeric signal.
Metadata also includes a fixed zero-based engineering `chart_max` used by the
dashboard y-axes; exceptional readings safely extend the displayed range.

Responses use `Cache-Control: no-store`; unknown asset IDs return JSON 404s. The
simulator starts automatically in-process and requires no separate service. To
watch its console demonstration directly, run:

```sh
python3 -m simulators.hvac001_simulator
```

The simulation covers supply/return temperature, airflow, filter differential
pressure, motor current, fan vibration, temperature setpoint, and HVAC state.
