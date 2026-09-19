package com.networkwm.live;

import com.networkwm.graph.GraphContractService;
import com.networkwm.graph.GraphContractService.GraphSequence;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LiveSequenceAdapterTest {
    private static final String WINDOW_A = "{"
            + "\"windowIndex\":0,"
            + "\"windowStartEpochMicros\":1000000,"
            + "\"windowEndEpochMicros\":11000000,"
            + "\"flows\":[{"
            + "\"sourceIp\":\"127.0.0.1\",\"destinationIp\":\"127.0.0.1\","
            + "\"sourcePort\":40000,\"destinationPort\":8080,\"protocol\":17,"
            + "\"packetCount\":5,\"firstSeenEpochMicros\":1000000,"
            + "\"lastSeenEpochMicros\":5000000,"
            + "\"ttlMean\":64.0,\"ttlVariance\":0.0,\"tcpWindowTrend\":0.0,"
            + "\"fragmentCount\":0,\"retransmissionCount\":0,"
            + "\"truncatedPacketCount\":5,"
            + "\"payloadSizeMean\":120.0,\"payloadSizeStddev\":14.14,"
            + "\"payloadSizeSkew\":0.0}],"
            + "\"portScans\":[]}";

    private static final String WINDOW_B = "{"
            + "\"windowIndex\":1,"
            + "\"windowStartEpochMicros\":11000000,"
            + "\"windowEndEpochMicros\":21000000,"
            + "\"flows\":[{"
            + "\"sourceIp\":\"127.0.0.1\",\"destinationIp\":\"127.0.0.1\","
            + "\"sourcePort\":40001,\"destinationPort\":8081,\"protocol\":6,"
            + "\"packetCount\":3,\"firstSeenEpochMicros\":11000000,"
            + "\"lastSeenEpochMicros\":15000000,"
            + "\"ttlMean\":63.5,\"ttlVariance\":0.25,\"tcpWindowTrend\":1.5,"
            + "\"fragmentCount\":1,\"retransmissionCount\":0,"
            + "\"truncatedPacketCount\":3,"
            + "\"payloadSizeMean\":80.0,\"payloadSizeStddev\":5.0,"
            + "\"payloadSizeSkew\":0.1}],"
            + "\"portScans\":[]}";

    private final LiveSequenceAdapter adapter =
            new LiveSequenceAdapter(new GraphContractService());

    @Test
    void liveWindowsAdaptToVersionedContract() throws Exception {
        GraphSequence sequence = adapter.adapt(List.of(WINDOW_A, WINDOW_B));
        assertEquals(GraphContractService.CONTRACT_VERSION,
                sequence.contractVersion());
        assertEquals(2, sequence.windows().size());
        assertEquals("kairos.graph.v1",
                sequence.windows().get(0).schemaVersion());
        assertTrue(sequence.windows().get(0).topologyAvailable());
        assertTrue(sequence.windows().get(1).windowStart()
                .isAfter(sequence.windows().get(0).windowStart()));
        new GraphContractService().validate(sequence);
    }

    @Test
    void malformedWindowIsRejectedWithClearError() {
        String malformed = "{\"windowIndex\":0,"
                + "\"windowStartEpochMicros\":21000000,"
                + "\"windowEndEpochMicros\":11000000,"
                + "\"flows\":[]}";
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> adapter.adapt(malformed));
        assertTrue(error.getMessage().contains("live window 0"));
    }

    @Test
    void nonFiniteFeatureIsRejected() {
        String poisoned = WINDOW_A.replace("\"ttlMean\":64.0", "\"ttlMean\":1e400");
        assertThrows(IllegalArgumentException.class,
                () -> adapter.adapt(poisoned));
    }

    @Test
    void blankEndpointIsRejected() {
        String blank = WINDOW_A.replace("127.0.0.1", "");
        assertThrows(IllegalArgumentException.class,
                () -> adapter.adapt(blank));
    }
}
