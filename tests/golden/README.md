# Golden data notes (tests/golden/)

Hand calculations behind `tests/unit/test_flags.py`. Base clock
T0 = 1_760_000_000_000 ms. Sample period 5 s unless stated.

## QF-01 GAP (warn)
Samples: seq 1,2,3 at T0, T0+5 s, T0+10 s; seq 5 at T0+30 s.
Delta 20 s > 3 x 5 s = 15 s, and seq jumps 3 -> 5.
=> one GAP, severity warn (20 s < 15 min), interval [T0+10 s, T0+30 s].

## QF-01 GAP (error)
Same but last sample at T0+20 min. Delta 19 min 50 s > 15 min => error.

## QF-03 STUCK_PIR
pir = 1 for 73 samples at 5-min spacing = T0 .. T0+6 h, timetable present.
No change for 6 h >= 6 h threshold => STUCK_PIR warn, [T0, T0+6 h].

## QF-04 STUCK_CURRENT (zero variance while on)
current = 2.5 A, load_state = 1, 13 samples at 5-min spacing = 60 min span.
now = last + 1 s => still 60 min >= 60 min => warn, reason zero-variance-while-on.

## QF-04 STUCK_CURRENT (dead 24 h weekday)
current = 0 for 24 h + 1 min on a Monday (2026-10-05 UTC), load_state = 0.
=> warn, reason dead-24h-weekday.

## QF-05 OUT_OF_RANGE
voltage_v = 400 (bounds 80-300) => one point flag [ts, ts].
Everything inside bounds => no flags.

## QF-09 FW_MIXED
Nodes A (0.1.0), B (0.2.0) enabled => common = "0.1.0", one flag on B.

## TC-QF-12 chunk equivalence
Gap scenario split as [1,2] + [3,5] fed through two advance() calls with
carried state must equal flags from one advance() call over [1,2,3,5].
