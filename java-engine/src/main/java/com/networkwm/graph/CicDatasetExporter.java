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
                    "usage: CicDatasetExporter [--window-seconds N] OUTPUT.json INPUT.csv [INPUT.csv...]");
        }
        List<String> options = new java.util.ArrayList<>(Arrays.asList(arguments));
        long windowSeconds = 10L;
        int windowFlag = options.indexOf("--window-seconds");
        if (windowFlag >= 0) {
            if (windowFlag + 1 >= options.size()) {
                throw new IllegalArgumentException(
                        "--window-seconds requires a value");
            }
            windowSeconds = Long.parseLong(options.get(windowFlag + 1));
            options.subList(windowFlag, windowFlag + 2).clear();
        }
        if (options.size() < 2) {
            throw new IllegalArgumentException(
                    "usage: CicDatasetExporter [--window-seconds N] OUTPUT.json INPUT.csv [INPUT.csv...]");
        }
        Path destination = Path.of(options.get(0)).toAbsolutePath();
        List<Path> inputs = options.stream()
                .skip(1)
                .map(Path::of)
                .map(Path::toAbsolutePath)
                .toList();
        CicGraphDatasetService.ExportSummary summary =
                new CicGraphDatasetService().export(
                        inputs, destination, Duration.ofSeconds(windowSeconds));
        System.out.printf(
                "exported %d rows into %d windows at %s%n",
                summary.rowsAggregated(),
                summary.windowsExported(),
                summary.destination());
    }
}
