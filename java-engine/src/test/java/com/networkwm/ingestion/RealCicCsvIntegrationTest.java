package com.networkwm.ingestion;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.EnumMap;
import java.util.Map;
import java.util.concurrent.atomic.LongAdder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealCicCsvIntegrationTest {
    @Test
    void streamsTheSelectedInfiltrationFileAndSkipsKnownRepeatedHeaders()
            throws Exception {
        String configuredPath = System.getProperty("kairos.real.csv");
        Assumptions.assumeTrue(configuredPath != null,
                "set -Dkairos.real.csv to run the real CIC CSV smoke test");

        Map<IngestionService.AttackStage, LongAdder> stages =
                new EnumMap<>(IngestionService.AttackStage.class);
        IngestionService.IngestionSummary summary = new IngestionService().ingest(
                Path.of(configuredPath),
                IngestionService.cicIds2018Timelines(),
                record -> stages.computeIfAbsent(
                        record.stage(), ignored -> new LongAdder()).increment());

        assertEquals(613_104L, summary.rowsRead());
        assertEquals(613_071L, summary.rowsEmitted());
        assertEquals(33L, summary.repeatedHeadersSkipped());
        assertTrue(summary.sanitizedValues() > 0L);
        assertTrue(stages.get(IngestionService.AttackStage.INITIAL_ACCESS).sum() > 0L);
    }
}
