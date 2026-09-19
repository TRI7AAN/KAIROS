# Live-capture performance (Phase 77) — measured 2026-09-19

Host: Kali Linux 6.19.14+kali-amd64, AMD Ryzen 5 5600H, dumpcap 4.6.6 /
libpcap 1.10.6 (TPACKET_V3), loopback interface, snaplen 256, BPF
`udp port N`. Generator: single-threaded Python UDP burst to 127.0.0.1.

## Throughput (5s bounded captures, file packet count / capture span)

| Target rate | Sent | Captured (file) | Span | Measured |
|---|---|---|---|---|
| ~50 pps | 200 | 200 | 3.61s | 55.4 pps |
| ~200 pps | 800 | 800 | 3.92s | 203.9 pps |
| ~800 pps | 3120 | 3120 | 3.98s | 784.6 pps |

Zero loss at all three rates (file count == sent in every run).

## Drop-rate behavior under load

Burst run (`udp port 29778`, 6s duration bound, 30-packet Python send
bursts, ~147k pps offered): backend stderr accounting reports

- `Packets captured: 662520`
- `Packets received/dropped on interface 'Loopback: lo': 662520/0
  (pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0) (100.0%)`

No drops observed up to ~147k pps loopback burst on this host; the
`pcap_stats`-equivalent drop counter (parsed from the backend's own
`received/dropped` line, never simulated) is the instrument that would
report the threshold. Drop-threshold sweep above this rate was not pushed
further: the offered load already exceeds any realistic live-demo rate by
two orders of magnitude.

## Memory bound

`live_emitter_tests` (32s capture + replay through `LiveFeatureEmitter`,
10s windows): RSS sampled every 5s stayed flat at 4116 kB across all six
samples (t=5..30s). The emitter clears per-window aggregates on every
emission, so buffered state is bounded by one open window.

## Backpressure

Overload rule is verified, not assumed:

- `live_capture_tests` packet-limit run: backend `-a packets:4` autostop
  fires and the session self-stops (C++ dual-bound mechanism 1).
- `LiveSessionServiceTest#supervisorSelfStopsAtPacketBound`: the Java
  supervisor's independent packet bound stops the session even if the
  backend bound is missed (dual-bound mechanism 2).
- Under induced overload the system drops with a visible counter (the
  `received/dropped` line above) rather than crashing or losing data
  silently: counters are parsed from backend stderr accounting in both the
  C++ (`LiveCaptureSession::counters`) and Java
  (`ProcessCaptureBackend::parseCounters`) paths.
