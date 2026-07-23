# TAEM 3D validated replay

This directory contains an interactive 3D replay generated from an existing
validated R1-R4 trajectory CSV. It is post-processing only; no new trajectory
propagation was executed.

- Representative case: `phase2_B5A_hp278p652m_vm0p282673mps_sp2deg_combined`
- Selection: strict-case mean event time nearest accepted-case median
- Source CSV SHA256: `8B497B965EA127D9CD556EDFDE8D56194042738D766E37938F589C1D07A2C295`
- Roles: `route_left`, `route_mid`, `route_right`
- Event marker: first completion of the adopted `N_dwell = 3` strict-box condition.

## GitHub Pages

Copy this `docs` directory to the target repository and enable GitHub Pages from
the repository's `docs/` folder. The normal URL form is:

`https://<github-user>.github.io/<repository>/`

No commit or push is performed by the builder.

<!-- TAEM_3D_DISPLAY_SCALING_BEGIN -->
## Display scaling

The default **Enhanced 3D** view uses independent visual axis scaling so that
the approximately 0--80 km altitude range remains visible beside the
multi-thousand-kilometre horizontal displacement. Axis labels, numerical
values, event coordinates, and hover values remain in physical units. The
**Scientific scale** control restores data-proportional geometry. The enhanced
view is a visualization aid and is not an additional validation criterion.
<!-- TAEM_3D_DISPLAY_SCALING_END -->
