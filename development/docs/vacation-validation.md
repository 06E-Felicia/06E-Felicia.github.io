# Vacation 1.38 validation (2026-10-29)

This release includes the previously implemented 74 simulated street stations, three-day 3000-point homework game, independent Shenzhen map, coastal trigger adjustment and conserved core-rain fallout limit. The latest change only changes map menus, street display names and warning downgrade delay. It does not change convection, cold pools or scoring again.

Passed targeted fixtures: independent yellow/orange/red rolling thresholds; retaining an issued level for 60 continuous minutes below threshold; recovery cancelling that timer; warning/checkpoint continuity; 1000/667/time-decay scoring and three independent days; 100 mm/h core fallout ceiling with excess condensate returned to the model ledger.

A headless Chrome run with the real Worker initialized all 74 stations, checked both five-layer menu orders and the independent Shenzhen view, paused at 21:00 and 00:00 choices, selected staying awake and then makeup, switched all five right-map layers, saved and restored those choices successfully. No page errors were reported. This was a short interaction run, not a full three-day weather acceptance run.

Street warnings are point markers, not verified street polygons. Street coordinates are official public representative grid points explicitly approved for game simulation; they are not claimed to be physical automatic stations. Test browser storage was removed on exit. No full-field replay, screenshot or simulation archive was generated.
