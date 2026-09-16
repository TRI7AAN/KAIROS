package com.networkwm.ingestion;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.ZoneId;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class IngestionServiceTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void normalizesSanitizesDropsMetadataAndLabelsFromTimeline() throws Exception {
        Path csv = temporaryDirectory.resolve("flows.csv");
        Files.writeString(csv, String.join("\n",
                " Flow Duration ,Flow Byts/s,Odd Feature,Timestamp,Label,Flow ID",
                "100,Infinity,NaN,14/02/2018 10:45:00,FTP-BruteForce,drop-me",
                " Flow Duration ,Flow Byts/s,Odd Feature,Timestamp,Label,Flow ID",
                "-Infinity,1e20,,14/02/2018 08:31:01,Benign,drop-me-too"));

        IngestionService service = new IngestionService(ZoneId.of("UTC"), 1000.0);
        List<IngestionService.FlowRecord> records = service.readAll(
                csv, IngestionService.cicIds2018Timelines());

        assertEquals(2, records.size());
        IngestionService.FlowRecord attack = records.get(0);
        assertEquals(IngestionService.AttackStage.INITIAL_ACCESS, attack.stage());
        assertEquals(100.0, attack.features().get("flow_duration"));
        assertEquals(1000.0, attack.features().get("flow_byts_s"));
        assertEquals(0.0, attack.features().get("odd_feature"));
        assertFalse(attack.features().containsKey("flow_id"));
        assertFalse(attack.features().containsKey("timestamp"));
        assertFalse(attack.features().containsKey("label"));

        IngestionService.FlowRecord benign = records.get(1);
        assertEquals(IngestionService.AttackStage.NONE, benign.stage());
        assertEquals(-1000.0, benign.features().get("flow_duration"));
        assertEquals(1000.0, benign.features().get("flow_byts_s"));
        assertEquals(0.0, benign.features().get("odd_feature"));

        java.util.ArrayList<IngestionService.FlowRecord> streamed = new java.util.ArrayList<>();
        IngestionService.IngestionSummary summary = service.ingest(
                csv, IngestionService.cicIds2018Timelines(), streamed::add);
        assertEquals(3, summary.rowsRead());
        assertEquals(2, summary.rowsEmitted());
        assertEquals(1, summary.repeatedHeadersSkipped());
        assertEquals(5, summary.sanitizedValues());
    }

    @Test
    void normalizesKnownDatasetAnomaly() {
        assertEquals("Infiltration",
                IngestionService.normalizeLabel(" Infilteration "));
        assertEquals("flow_byts_s",
                IngestionService.normalizeHeader(" Flow Byts/s "));
    }

    @Test
    void sanitizesLowercaseInfFromCappedCsvs() throws Exception {
        Path csv = temporaryDirectory.resolve("capped.csv");
        Files.writeString(csv, String.join("\n",
                "Flow Duration,Flow Byts/s,Flow Pkts/s,Timestamp,Label",
                "884,inf,8097.16,14/02/2018 12:55:54,Benign",
                "247,-inf,Infinity,14/02/2018 12:55:55,Benign"));

        IngestionService service = new IngestionService(ZoneId.of("UTC"), 1000.0);
        List<IngestionService.FlowRecord> records = service.readAll(
                csv, IngestionService.cicIds2018Timelines());

        assertEquals(2, records.size());
        assertEquals(1000.0, records.get(0).features().get("flow_byts_s"));
        assertEquals(-1000.0, records.get(1).features().get("flow_byts_s"));
        assertEquals(1000.0, records.get(1).features().get("flow_pkts_s"));
    }
}
