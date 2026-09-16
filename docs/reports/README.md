# Jev experiment atlas

Open `jev-experiment.html` locally in a browser. It is self-contained and needs no network connection, API key or server. `jev-experiment.png` is the static companion for PR discussions. Both are generated from `docs/evidence/stress-lab.json`.

```sh
# Default: offline fixtures, no provider calls. Use a separate output to preserve captured observations.
python -m jev_review.stress_lab --output /tmp/jev-fixtures.json

# Explicit experiment: at most ten provider calls; never executes fixture code.
python -m jev_review.stress_lab --live --output /tmp/jev-live.json
python scripts/build_experiment_report.py --input /tmp/jev-live.json --output /tmp/jev-experiment.html
```

Interactive features: case selection, exact diff inspection, full response provenance, downloadable evidence and a hypothetical probability-threshold simulation. The simulation ignores the deployed policy's other gates and cannot change its configuration.

The PNG exporter is optional and uses build-time Pillow and macOS Arial/Georgia fonts. Neither is needed for the bot or HTML report. These hand-designed experiments are not independent evaluation data or production calibration.
