package com.networkwm.api;

import com.networkwm.graph.CicGraphDatasetService;
import org.junit.jupiter.api.Test;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
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
    void rejectsUnsupportedPcapUntilSchemaAdapterIsAvailable() {
        UploadGraphService service =
                new UploadGraphService(new CicGraphDatasetService());

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.fromUpload(
                        new BytesMultipartFile("capture.pcap", new byte[]{1})));

        assertTrue(error.getMessage().contains("CICFlowMeter CSV"));
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
