package com.networkwm.api;

import com.networkwm.graph.CicGraphDatasetService;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UploadGraphServiceTest {
    private static final String CSV = String.join("\n",
            "Flow Duration,TotLen Fwd Pkts,TotLen Bwd Pkts,Timestamp,Label",
            "100,80,20,14/02/2018 10:45:00,Benign",
            "300,250,50,14/02/2018 10:45:05,FTP-BruteForce",
            "500,400,100,14/02/2018 10:45:12,Benign");

    @Test
    void convertsUploadedCicCsvIntoInferenceContract() throws Exception {
        UploadGraphService service =
                new UploadGraphService(new CicGraphDatasetService());

        var sequence = service.fromUpload(
                new BytesMultipartFile("traffic.csv", CSV.getBytes()));

        assertEquals("kairos.sequence.v1", sequence.contractVersion());
        assertEquals(2, sequence.windows().size());
        assertFalse(sequence.windows().get(0).topologyAvailable());
        assertTrue(sequence.edgeFeatureNames().contains(
                "flow_duration.mean"));
    }

    @Test
    void rejectsUnsupportedUploadExtension() {
        UploadGraphService service =
                new UploadGraphService(new CicGraphDatasetService());

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.fromUpload(
                        new BytesMultipartFile("capture.txt", new byte[]{1})));

        assertTrue(error.getMessage().contains(".pcap"));
    }

    /**
     * Item 14: PCAP upload end-to-end through the REAL native extractor.
     *
     * <p>A synthetic two-packet capture is written to disk, extracted via
     * JNI, and routed through the fused upload path. The resulting edge
     * must carry real, non-zero values for BOTH the derived flow-level
     * summaries and the native packet-level features — sourced from the
     * same underlying traffic — and must be flagged as genuinely fused
     * (neither flow-only nor packet-only). Fields the capture cannot
     * observe (e.g. TCP flag counts) must be absent, never zero-filled.
     */
    @Test
    void pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture()
            throws Exception {
        Assumptions.assumeTrue(
                System.getProperty("kairos.native.library") != null,
                "set -Dkairos.native.library to run the real-extractor "
                        + "upload test");
        UploadGraphService service =
                new UploadGraphService(new CicGraphDatasetService());

        var sequence = service.fromUpload(
                new BytesMultipartFile("capture.pcap", knownCapture()));

        assertEquals("kairos.sequence.v1", sequence.contractVersion());
        assertEquals(1, sequence.windows().size());
        assertTrue(sequence.windows().get(0).topologyAvailable());
        assertEquals(1, sequence.windows().get(0).edges().size());

        var edge = sequence.windows().get(0).edges().get(0);
        assertEquals("10.0.0.1", edge.source());
        assertEquals("10.0.0.2", edge.destination());
        assertFalse(edge.flowOnly());
        assertFalse(edge.packetOnly());

        // Native packet-level measurements from the real extractor.
        assertEquals(2.0, edge.features().get("packet.packet_count"));
        assertEquals(63.0, edge.features().get("packet.ttl_mean"));
        assertEquals(1.0, edge.features().get("packet.ttl_variance"));
        assertEquals(6.0, edge.features().get("packet.payload_size_mean"));

        // Flow-level summaries derived from the SAME extraction batch.
        assertEquals(2.0, edge.features().get("flow.packet_count"));
        assertEquals(
                1_000_000.0, edge.features().get("flow.duration_micros"));
        assertEquals(
                12.0, edge.features().get("flow.payload_bytes_estimate"));
        assertTrue(edge.features().get("flow.packet_rate_per_s") > 0.0);

        // Shared 5-tuple identifiers present once for both levels.
        assertEquals(80.0, edge.features().get("destination_port"));
        assertEquals(17.0, edge.features().get("protocol"));

        // Unobservable fields are absent, never fabricated as zeros.
        assertFalse(edge.features().containsKey("syn_count"));
        assertFalse(edge.features().containsKey("ack_count"));
        assertFalse(edge.features().containsKey("flow.tot_bwd_pkts"));

        // Scan-evidence node features ride along with honest zero defaults.
        var source = sequence.windows().get(0).nodes().stream()
                .filter(node -> node.id().equals("10.0.0.1"))
                .findFirst().orElseThrow();
        assertEquals(0.0, source.features().get(
                "packet.capture_scan_unique_destination_ports"));
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

    private record BytesMultipartFile(
            String originalFilename,
            byte[] contents) implements MultipartFile {
        @Override
        public String getName() {
            return "file";
        }

        @Override
        public String getOriginalFilename() {
            return originalFilename;
        }

        @Override
        public String getContentType() {
            return "text/csv";
        }

        @Override
        public boolean isEmpty() {
            return contents.length == 0;
        }

        @Override
        public long getSize() {
            return contents.length;
        }

        @Override
        public byte[] getBytes() {
            return contents.clone();
        }

        @Override
        public InputStream getInputStream() {
            return new ByteArrayInputStream(contents);
        }

        @Override
        public void transferTo(File destination) throws IOException {
            Files.write(destination.toPath(), contents);
        }

        @Override
        public void transferTo(Path destination) throws IOException {
            Files.write(destination, contents);
        }
    }
}
