package com.networkwm.api;

import com.networkwm.bridge.CppBridge.ExtractionBatch;
import com.networkwm.bridge.CppBridge.FlowFeatures;
import com.networkwm.bridge.CppBridge.PortScanFeatures;
import com.networkwm.graph.CicGraphDatasetService;
import com.networkwm.graph.Ctu13PacketContractService;
import org.junit.jupiter.api.Test;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

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
    void convertsUploadedPcapIntoPacketNativeWindows() throws Exception {
        List<FlowFeatures> flows = List.of(
                flow(1_700_000_000_000_000L, "10.0.0.1", "10.0.0.2"),
                flow(1_700_000_025_000_000L, "10.0.0.2", "10.0.0.3"));
        UploadGraphService service = new UploadGraphService(
                new CicGraphDatasetService(),
                new Ctu13PacketContractService(),
                ignored -> new ExtractionBatch(flows, List.of(
                        new PortScanFeatures(
                                "10.0.0.1", 25, 22, 0.8, "sequential"))));

        var sequence = service.fromUpload(
                new BytesMultipartFile("capture.pcap", new byte[]{1}));

        assertEquals(3, sequence.windows().size());
        assertTrue(sequence.windows().get(0).topologyAvailable());
        assertFalse(sequence.windows().get(1).topologyAvailable());
        assertEquals("__network__",
                sequence.windows().get(1).nodes().get(0).id());
        assertEquals(22.0, sequence.windows().get(0).nodes().stream()
                .filter(node -> node.id().equals("10.0.0.1"))
                .findFirst().orElseThrow().features().get(
                        "packet.capture_scan_unique_destination_ports"));
        assertTrue(sequence.edgeFeatureNames().contains(
                "packet.packet_count"));
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

    private static FlowFeatures flow(
            long epochMicros,
            String source,
            String destination) {
        return new FlowFeatures(
                source, destination, 12345, 443, 6, 5,
                epochMicros, epochMicros + 1_000_000L,
                64.0, 0.0, 0.0, 0, 0, 0,
                128.0, 10.0, 0.0);
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
