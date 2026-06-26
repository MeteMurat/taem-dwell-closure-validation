# Q1-Oriented Terminal Analysis Report

## Run summary

- Run ID: `multiSimulation_case`
- Vehicles: 3
- TAEM reached rate: 0.000
- Any-reached rate: 0.000
- Average dwell: 0.000 s
- Evaluation tolerances: h=1500.0 m, v=120.0 m/s, s_go=15000.0 m, psi=8.00 deg

## Vehicle-wise metrics

- Vehicle 1: reached=False, lower-bound score=0.001, final s_go=275208.6 m, min |h_err|=0.12 m, min |v_err|=0.076 m/s, min |s_go_err|=0.13 m, min |psi_err|=0.000002 rad
- Vehicle 0: reached=False, lower-bound score=0.001, final s_go=52694.3 m, min |h_err|=1.36 m, min |v_err|=0.051 m/s, min |s_go_err|=16.31 m, min |psi_err|=0.000004 rad
- Vehicle 2: reached=False, lower-bound score=62.476, final s_go=6178438.0 m, min |h_err|=0.41 m, min |v_err|=0.122 m/s, min |s_go_err|=937145.93 m, min |psi_err|=0.000002 rad

## Key interpretation

- Best TAEM-proximity candidate (lower-bound score): vehicle 1.
- Best final geographic/range closure candidate: vehicle 0.
- Note: the lower-bound score uses per-channel minimum absolute errors, so it is a conservative proximity indicator rather than proof of simultaneous in-box satisfaction.

## Failure-mode classification

- Vehicle 1: Near-success / no dwell (final s_go=275208.6 m)
- Vehicle 0: Near-success / no dwell (final s_go=52694.3 m)
- Vehicle 2: Multi-channel near-hit (final s_go=6178438.0 m)

## Suggested manuscript usage

- Use `q1_vehicle_metrics.csv` as the basis for a vehicle-wise terminal proximity table.
- Use `q1_failure_modes.csv` as the basis for a failure-mode discussion subsection.
- Report both event success (`taem_reached`) and continuous proximity (`taem_lb_score`) to avoid collapsing near-success and true latch into the same class.