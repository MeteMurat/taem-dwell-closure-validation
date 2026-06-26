# Updated Q1 abstract draft and contribution set

## Abstract draft

Terminal success assessment for multi-vehicle entry guidance is commonly reduced to final geographic closure or a single threshold on remaining range, which obscures near-success regimes and provides limited insight into why a trajectory fails to satisfy terminal-area-energy-management (TAEM) requirements. This study proposes an event-based terminal evaluation framework for a same-target, three-vehicle entry scenario in which TAEM satisfaction is defined through simultaneous tolerance checks in altitude, velocity, remaining range, and heading, augmented by a dwell requirement to distinguish transient contact from sustained success. In parallel, a continuous terminal proximity metric, denoted `taem_lb_score`, is introduced to quantify how closely a trajectory approaches in-box satisfaction even when no discrete latch is achieved.

The framework is embedded in a physics-based multi-phase guidance simulation and paired with a structured post-processing pipeline that classifies vehicle-wise failure modes, including near-success/no-dwell and multi-channel near-hit regimes. Across the current pilot campaign, no trajectory produced a full TAEM latch, but the proposed metric consistently separated stronger terminal candidates from weaker ones and exposed meaningful differences between vehicles despite similar mission geometry. To test whether the metric carries learnable structure rather than acting as an ad hoc diagnostic, a supervised surrogate study was performed on 46 runs (138 vehicle-level samples). Using configuration-only features, a gradient boosting regressor achieved a cross-validated mean absolute error of approximately 5.78 and an R2 of approximately 0.896 for `taem_lb_score` prediction, indicating that the metric is both behaviorally informative and data-consistent.

These results suggest that event-based TAEM evaluation should not be collapsed into a binary reached/not-reached label alone. Instead, the combined use of a dwell-based event definition and a continuous proximity surrogate offers a more discriminative, extensible, and potentially transferable framework for terminal-guidance analysis. The proposed methodology provides a basis for future robustness studies, cross-scenario validation, and machine-learning-assisted guidance assessment in high-speed entry applications.

## Updated contribution list

1. **Event-based TAEM success formalization.** TAEM success is modeled as a multi-channel event requiring simultaneous tolerance satisfaction in altitude, velocity, remaining range, and heading, together with dwell-based persistence rather than single-step threshold crossing.

2. **Continuous terminal proximity metric.** A continuous lower-bound proximity score (`taem_lb_score`) is introduced to characterize how closely a trajectory approaches TAEM satisfaction even when no discrete latch is achieved, enabling near-success regimes to be separated from outright failures.

3. **Three-vehicle same-target comparative framework.** The study preserves a common-target, multi-vehicle setup and uses the proposed terminal metrics to distinguish terminal behavior modes under different lateral-shaping and guidance parameterizations.

4. **Failure-mode-aware analysis pipeline.** The post-processing layer links event detection, continuous scoring, and qualitative failure-mode classification, producing vehicle-wise and run-wise summaries suitable for both engineering iteration and scientific reporting.

5. **ML-validatable metric hypothesis.** A supervised regression study demonstrates that `taem_lb_score` is not merely a descriptive diagnostic but a learnable quantity with strong predictive structure under configuration-only inputs, motivating its use as a candidate surrogate objective for broader terminal-guidance studies.

## Wording discipline for the manuscript

- Prefer **"promising candidate metric"** or **"ML-consistent terminal proximity metric"** over **"universal metric"** at the current stage.
- Reserve stronger universality language for the point at which the metric has been validated under multiple target locations, initial conditions, tolerance families, and guidance branches.
- Emphasize that the present evidence supports **structure, discriminative power, and learnability**, not yet full universality.
