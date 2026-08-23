# Neural Mech

Neural Mech is a dependency-free HVAC digital twin and predictive-maintenance demonstration. It simulates live equipment telemetry, introduces realistic fault and degradation scenarios, detects developing problems with two independent techniques, and presents maintenance risk through an industrial operator dashboard.

The project is intentionally implemented with the Python standard library and browser-native HTML, CSS, and JavaScript. No package installation or external services are required.

## What it demonstrates

- A live HVAC-001 digital twin with one-second telemetry updates
- Normal operating variation and correlated engineering signals
- Gradual fault injection and recovery instead of instantaneous value changes
- Classic statistical and adaptive AI-based anomaly detection
- Hybrid analysis that increases confidence when both detectors agree
- Risk, evidence, estimated time remaining, and maintenance recommendations
- Responsive live charts and a predictive-maintenance alert register

## Architecture

```text
Browser dashboard
      │
      ▼
server.py ─────────────── HTTP pages and JSON APIs
      │
      ├── simulators/hvac001_simulator.py
      │      Normal telemetry, faults, degradation, and recovery
      │
      ├── anomaly-detector/classic.py
      │      EWMA, persistence, thresholds, and trend analysis
      │
      └── anomaly-detector/ai-based.py
             Adaptive multivariate anomaly scoring
```

### Server

[`server.py`](server.py) serves the asset registry, digital-twin dashboard, telemetry API, and fault-control API. It connects the simulator to both anomaly detectors and produces a third hybrid result by combining their findings.

### Simulator

[`simulators/hvac001_simulator.py`](simulators/hvac001_simulator.py) generates continuously changing HVAC telemetry for:

- Supply and return air temperature
- Airflow
- Filter differential pressure
- Motor current
- Fan vibration
- Temperature setpoint and HVAC operating state

The simulator maintains thread-safe recent history and generates representative longer-range history for the dashboard.

### Anomaly detectors

[`anomaly-detector/classic.py`](anomaly-detector/classic.py) implements the classic detector using exponentially weighted moving averages, engineering thresholds, persistence rules, hysteresis, and bounded trend windows. It is designed to detect sustained deviations while rejecting isolated noisy samples.

[`anomaly-detector/ai-based.py`](anomaly-detector/ai-based.py) implements an explainable adaptive detector using standardized residuals and diagonal Mahalanobis-style multivariate scoring. It starts with engineering reference values, learns slowly from nominal observations, and prevents developing faults from being absorbed into its learned baseline.

The hybrid result combines findings by component and fault mode. Agreement between both methods increases the reported confidence and risk priority; single-detector findings remain visible instead of being discarded. The dashboard tabs allow Classic, AI-based, and Hybrid results to be evaluated independently.

## Simulated fault scenarios

The operator panel can activate multiple conditions independently:

| Scenario | Simulated physical signature |
| --- | --- |
| Clogged filter | Filter differential pressure rises while airflow and efficiency decline |
| Cooling-coil fouling | Supply air temperature rises as cooling capacity degrades |
| Fan imbalance | Fan vibration and motor load increase while airflow performance falls |
| Drive-belt slip | Airflow drops, the motor unloads, and vibration may increase |

Fault intensity ramps up over approximately 30 seconds. Clearing a fault begins a gradual recovery, allowing detector persistence and alert-clearing behavior to be observed.

## Predictive-maintenance output

Each detector reports a consistent alert structure containing:

- Component at risk and likely degradation mode
- Advisory, warning, or critical severity
- Risk and confidence scores
- Signals contributing to the finding
- Estimated time remaining when a defensible trend exists
- A targeted predictive-maintenance recommendation

Remaining-life values are simulation estimates derived from short-term trends. They are useful for demonstrating the workflow, but they are not production maintenance forecasts.

## Run locally

Requirements:

- Python 3.10 or newer
- A modern web browser

Start the application:

```bash
python3 server.py
```

Open <http://127.0.0.1:8000> and select `HVAC-001`, or go directly to:

<http://127.0.0.1:8000/digital-twin/HVAC-001>

To watch raw simulated readings in the terminal:

```bash
python3 -m simulators.hvac001_simulator
```

## API

### Read telemetry and detector results

```http
GET /api/assets/HVAC-001/telemetry?range=1m
```

Supported ranges:

| Range | Approximate points | Sampling represented |
| --- | ---: | --- |
| `1m` | 60 | One second |
| `1h` | 120 | Thirty seconds |
| `1d` | 144 | Ten minutes |

Example:

```bash
curl "http://127.0.0.1:8000/api/assets/HVAC-001/telemetry?range=1m"
```

The response includes the current `reading`, `history`, engineering `metadata`, active `faults`, and `anomaly_detection` results for `classic`, `ai_based`, and `hybrid` modes.

### Activate or clear a fault

Activate fan imbalance:

```bash
curl -X POST http://127.0.0.1:8000/api/assets/HVAC-001/faults \
  -H "Content-Type: application/json" \
  -d '{"fault_id":"fan_imbalance","active":true}'
```

Deactivate one fault by sending the same `fault_id` with `"active": false`, or clear every fault:

```bash
curl -X POST http://127.0.0.1:8000/api/assets/HVAC-001/faults \
  -H "Content-Type: application/json" \
  -d '{"reset":true}'
```

Valid fault IDs are `filter_clog`, `coil_fouling`, `fan_imbalance`, and `belt_slip`.

## Suggested validation workflow

1. Start the server and allow both detectors to observe normal telemetry.
2. Confirm that the predictive-maintenance table remains in monitoring mode.
3. Select the Classic or AI-based tab to view each detector independently.
4. Activate one fault and watch its correlated telemetry signals develop.
5. Compare the detector evidence, risk, confidence, and estimated time remaining.
6. Select Hybrid to see whether both methods agree on the component and fault mode.
7. Clear the fault and observe gradual telemetry and alert recovery.

## Project structure

```text
neural-mech/
├── server.py
├── simulators/
│   ├── __init__.py
│   └── hvac001_simulator.py
├── anomaly-detector/
│   ├── classic.py
│   └── ai-based.py
├── .gitignore
└── README.md
```

## Scope and limitations

This repository is an engineering demonstration, not a certified condition-monitoring system. Its detector thresholds, confidence values, and remaining-life estimates are calibrated for the included simulator. Before using the approach with physical equipment, validate it with site-specific sensor quality, operating envelopes, labelled maintenance history, failure definitions, and appropriate safety procedures.
