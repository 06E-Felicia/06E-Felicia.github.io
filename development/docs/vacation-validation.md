# Vacation 1.39 validation (2026-10-29)

The eastern WSW deceleration distribution is adjusted toward the coast while retaining seeded inland/offshore positions and continuous daily movement. Wind, lifting and moisture use the same local exit. There is no fixed eastern inland exclusion. Terrain contributes one quarter of its previous cell-steering blend; advection speed is retained.

Passed short real-DEM probes: an inland exit favors inland terrain, a shoreward exit favors coastal terrain, offshore offsets retain their sign, seeds 17 and 131 produce distinct reproducible tracks, and terrain steering stays within 20 degrees of the input wind in the probe. Existing coastal PRD/western terrain checks passed. These probes do not establish full-run rainband longevity.

Passed warning fixtures: orange -> adjacent yellow; red -> adjacent orange -> second-ring yellow; no third-ring cascade; no invented rainfall; continuous one-hour downgrade hold with recovery reset and checkpoint continuity. Adjacency uses a relative-neighborhood graph of the 74 approved representative points capped at 20 km, not verified administrative topology.

Passed game fixtures: early settlement for red at 00:00, intermediate morning times and 07:30 inclusive; pending midnight choice is completed before settlement; score remains locked; newly issued afternoon red only triggers the extra event in (07:30,16:30] for skipped homework with zero score. Extra event and settlement survive save/restore. Existing 1000/667/time-decay and three-day fixtures pass.

A short Chrome real-Worker run checked the prominent action above observation search, both five-layer menus, 21:00 / 00:00 choices, makeup and save/restore without page errors. A second seeded browser run received red at midnight, displayed the early 1000-point settlement, hid the now-inapplicable makeup action and restored that result successfully. Browser storage is cleared on exit. No full three-day weather simulation, screenshot or full-field replay was recorded.
