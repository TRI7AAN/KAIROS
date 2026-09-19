# Offline + safety regression (Phase 76) — run 2026-09-19

## Passive mode with network disabled

- Isolated namespace (`unshare -Urn`, loopback only, no external route):
  `NETNS_UP` confirmed, loopback up.
- Bounded passive capture inside the namespace
  (`dumpcap -i lo -f "udp port 29776" -s 256 -a packets:4`): backend exit 0,
  4/4 packets captured from locally generated UDP traffic.
- Existing dependency-free extractor parses the offline file: 1 flow,
  `127.0.0.1 -> 127.0.0.1 pkts=4`, header-derived payload mean 60 —
  passive capture on a local interface requires no internet connectivity.
- Java `LiveSessionServiceTest` (6/6 incl. real 5s loopback capture with
  real counters) and `live_capture_tests` (bounded + packet-limit self-stop)
  re-run fresh in this phase: all pass.

## Active mode refusals (fresh, independent of Phase 70/75 tests)

- `Phase76ActiveRefusalTest` (3/3, new in this phase):
  - active start without any authorization flag -> 403 refused;
  - active start against allowlisted `lo` with operator id -> 403 refused;
  - passive start against non-allowlisted `9.9.9.9` -> 403 refused.
- Pre-existing enforcement (re-asserted, not merely referenced):
  `ConsentGateServiceTest#activeModeIsAlwaysRefused`,
  `LiveSessionServiceTest#nonPassiveModeIsRefused`.
- No active-probe code path exists anywhere in this session (Stop Gate 1
  never reached; Phases 75-78 not implemented).
