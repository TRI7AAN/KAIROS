package com.networkwm.bridge;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CppBridgeIntegrationTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void returnsTypedNativeFeaturesForKnownCapture() throws Exception {
        Assumptions.assumeTrue(System.getProperty("kairos.native.library") != null,
                "set -Dkairos.native.library to run the JNI round-trip");
        Path capture = temporaryDirectory.resolve("known.pcap");
        Files.write(capture, knownCapture());

        CppBridge.ExtractionBatch batch = new CppBridge().extract(
                capture, 32L, new CppBridge.ScanConfig(2, 0.70));

        assertEquals(1, batch.flows().size());
        CppBridge.FlowFeatures flow = batch.flows().get(0);
        assertEquals("10.0.0.1", flow.sourceIp());
        assertEquals("10.0.0.2", flow.destinationIp());
        assertEquals(1_000_000L, flow.firstSeenEpochMicros());
        assertEquals(2_000_000L, flow.lastSeenEpochMicros());
        assertEquals(80, flow.destinationPort());
        assertEquals(2L, flow.packetCount());
        assertEquals(63.0, flow.ttlMean(), 1e-12);
        assertEquals(1.0, flow.ttlVariance(), 1e-12);
        assertEquals(6.0, flow.payloadSizeMean(), 1e-12);
        assertEquals(2.0, flow.payloadSizeStddev(), 1e-12);
        assertTrue(batch.portScans().isEmpty());
    }

    private static byte[] knownCapture() {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        little32(output, 0xA1B2C3D4L);
        little16(output, 2);
        little16(output, 4);
        little32(output, 0);
        little32(output, 0);
        little32(output, 65535);
        little32(output, 101);
        record(output, udpPacket(64, 4), 1);
        record(output, udpPacket(62, 8), 2);
        return output.toByteArray();
    }

    private static byte[] udpPacket(int ttl, int payloadSize) {
        ByteArrayOutputStream packet = new ByteArrayOutputStream();
        int udpSize = 8 + payloadSize;
        int ipSize = 20 + udpSize;
        packet.write(0x45);
        packet.write(0);
        big16(packet, ipSize);
        big16(packet, 1);
        big16(packet, 0);
        packet.write(ttl);
        packet.write(17);
        big16(packet, 0);
        packet.writeBytes(new byte[]{10, 0, 0, 1, 10, 0, 0, 2});
        big16(packet, 1234);
        big16(packet, 80);
        big16(packet, udpSize);
        big16(packet, 0);
        packet.writeBytes(new byte[payloadSize]);
        return packet.toByteArray();
    }

    private static void record(
            ByteArrayOutputStream output, byte[] packet, long timestamp) {
        little32(output, timestamp);
        little32(output, 0);
        little32(output, packet.length);
        little32(output, packet.length);
        output.writeBytes(packet);
    }

    private static void little16(ByteArrayOutputStream output, int value) {
        output.write(value & 0xFF);
        output.write((value >>> 8) & 0xFF);
    }

    private static void little32(ByteArrayOutputStream output, long value) {
        for (int shift = 0; shift < 32; shift += 8) {
            output.write((int) (value >>> shift) & 0xFF);
        }
    }

    private static void big16(ByteArrayOutputStream output, int value) {
        output.write((value >>> 8) & 0xFF);
        output.write(value & 0xFF);
    }
}
