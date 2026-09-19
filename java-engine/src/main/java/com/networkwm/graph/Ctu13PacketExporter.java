package com.networkwm.graph;

import com.networkwm.bridge.CppBridge;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

/** Bounded offline exporter: CTU-13 pcap -&gt; packet-native contract. */
public final class Ctu13PacketExporter {
    private Ctu13PacketExporter() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length < 3) {
            throw new IllegalArgumentException(
                    "usage: Ctu13PacketExporter OUTPUT.json CAPTURE.pcap MAX_PACKETS [WINDOW_SECONDS]");
        }
        Path destination = Path.of(arguments[0]).toAbsolutePath();
        Path capture = Path.of(arguments[1]).toAbsolutePath();
        long maxPackets = Long.parseLong(arguments[2]);
        long windowSeconds = arguments.length >= 4 ? Long.parseLong(arguments[3]) : 10L;

        CppBridge.ExtractionBatch batch =
                new CppBridge().extract(capture, maxPackets, new CppBridge.ScanConfig(20, 0.70));
        GraphContractService.GraphSequence sequence =
                new Ctu13PacketContractService().fromExtraction(
                        batch, Instant.parse("2011-08-16T13:31:00Z"), windowSeconds);
        new GraphContractService().write(destination, sequence);
        System.out.printf(
                "exported %d packet flows (%d port-scan sources) into %d windows at %s%n",
                batch.flows().size(),
                batch.portScans().size(),
                sequence.windows().size(),
                destination);
    }
}
