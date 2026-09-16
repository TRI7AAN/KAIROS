package com.networkwm.graph;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;

/** Standalone offline exporter for the selected CIC CSV days. */
public final class CicDatasetExporter {
    private CicDatasetExporter() {
    }

    public static void main(String[] arguments) throws Exception {
        if (arguments.length < 2) {
            throw new IllegalArgumentException(
                    "usage: CicDatasetExporter OUTPUT.json INPUT.csv [INPUT.csv...]");
        }
        Path destination = Path.of(arguments[0]).toAbsolutePath();
        List<Path> inputs = Arrays.stream(arguments)
                .skip(1)
                .map(Path::of)
                .map(Path::toAbsolutePath)
                .toList();
        CicGraphDatasetService.ExportSummary summary =
                new CicGraphDatasetService().export(
                        inputs, destination, Duration.ofSeconds(10));
        System.out.printf(
                "exported %d rows into %d windows at %s%n",
                summary.rowsAggregated(),
                summary.windowsExported(),
                summary.destination());
    }
}
