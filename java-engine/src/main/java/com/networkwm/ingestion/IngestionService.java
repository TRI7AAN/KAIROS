package com.networkwm.ingestion;

import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Consumer;
import java.util.regex.Pattern;

/**
 * Streaming CICFlowMeter CSV ingestion with deterministic numeric sanitation and
 * published-timeline stage labels. Windowing and host aggregation begin in Phase 9.
 */
@Service
public class IngestionService {
    public static final double DEFAULT_ABSOLUTE_CLIP = 1.0e12;
    private static final int MAX_REPORTED_VALIDATION_ERRORS = 10;

    private static final DateTimeFormatter CIC_TIMESTAMP =
            DateTimeFormatter.ofPattern("d/M/uuuu H:mm:ss", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);
    private static final Pattern NON_ALPHANUMERIC = Pattern.compile("[^a-z0-9]+");
    private static final Set<String> DROPPED_COLUMNS =
            Set.of("flow_id", "src_ip", "source_ip", "dst_ip", "destination_ip",
                    "timestamp", "label");

    private final ZoneId datasetZone;
    private final double absoluteClip;

    public IngestionService() {
        this(ZoneId.of("UTC"), DEFAULT_ABSOLUTE_CLIP);
    }

    public IngestionService(ZoneId datasetZone, double absoluteClip) {
        this.datasetZone = Objects.requireNonNull(datasetZone, "datasetZone");
        if (!Double.isFinite(absoluteClip) || absoluteClip <= 0.0) {
            throw new IllegalArgumentException("absoluteClip must be finite and positive");
        }
        this.absoluteClip = absoluteClip;
    }

    public IngestionSummary ingest(
            Path csvPath,
            List<AttackTimeline> timelines,
            Consumer<FlowRecord> sink) throws IOException {
        Objects.requireNonNull(csvPath, "csvPath");
        Objects.requireNonNull(timelines, "timelines");
        Objects.requireNonNull(sink, "sink");

        long rowsRead = 0L;
        long rowsEmitted = 0L;
        long repeatedHeadersSkipped = 0L;
        long sanitizedValues = 0L;
        long validationErrorCount = 0L;
        List<String> validationErrors = new ArrayList<>();

        try (BufferedReader reader = Files.newBufferedReader(csvPath, StandardCharsets.UTF_8)) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                throw new IOException("CSV file is empty: " + csvPath);
            }
            List<String> rawHeaders = parseCsvLine(headerLine);
            List<String> headers = normalizeHeaders(rawHeaders);
            int timestampIndex = requiredIndex(headers, "timestamp");
            int labelIndex = requiredIndex(headers, "label");

            String line;
            while ((line = reader.readLine()) != null) {
                ++rowsRead;
                if (line.isBlank()) {
                    continue;
                }
                List<String> values;
                try {
                    values = parseCsvLine(line);
                } catch (CsvFormatException error) {
                    ++validationErrorCount;
                    addValidationError(validationErrors,
                            "row " + (rowsRead + 1L) + ": " + error.getMessage());
                    continue;
                }
                if (values.size() != headers.size()) {
                    ++validationErrorCount;
                    addValidationError(validationErrors,
                            "row " + (rowsRead + 1L) + " has " + values.size()
                                    + " fields; expected " + headers.size());
                    continue;
                }
                if ("timestamp".equals(normalizeHeader(values.get(timestampIndex)))
                        && "label".equals(normalizeHeader(values.get(labelIndex)))) {
                    ++repeatedHeadersSkipped;
                    continue;
                }

                LocalDateTime localTimestamp;
                try {
                    localTimestamp = LocalDateTime.parse(
                            values.get(timestampIndex).trim(), CIC_TIMESTAMP);
                } catch (RuntimeException error) {
                    ++validationErrorCount;
                    addValidationError(validationErrors,
                            "row " + (rowsRead + 1L)
                                    + " has an invalid CIC timestamp");
                    continue;
                }

                String rawLabel = values.get(labelIndex).trim();
                String normalizedLabel = normalizeLabel(rawLabel);
                String sourceIp = optionalField(values, headers, "src_ip", "source_ip");
                String destinationIp = optionalField(values, headers, "dst_ip", "destination_ip");
                Map<String, Double> features = new LinkedHashMap<>();
                boolean validRow = true;
                for (int index = 0; index < headers.size(); ++index) {
                    String header = headers.get(index);
                    if (DROPPED_COLUMNS.contains(header)) {
                        continue;
                    }
                    NumericValue parsed;
                    try {
                        parsed = sanitize(values.get(index), rowsRead + 1L, header);
                    } catch (CsvFormatException error) {
                        ++validationErrorCount;
                        addValidationError(validationErrors, error.getMessage());
                        validRow = false;
                        break;
                    }
                    features.put(header, parsed.value());
                    sanitizedValues += parsed.sanitized() ? 1L : 0L;
                }
                if (!validRow) {
                    continue;
                }
                int sourcePort = integerFeature(features, "src_port", "source_port");
                int destinationPort = integerFeature(features, "dst_port", "destination_port");
                int protocol = integerFeature(features, "protocol");


                AttackStage stage = stageFor(localTimestamp, normalizedLabel, timelines);
                sink.accept(new FlowRecord(
                        localTimestamp.atZone(datasetZone).toInstant(),
                        sourceIp,
                        destinationIp,
                        sourcePort,
                        destinationPort,
                        protocol,
                        Collections.unmodifiableMap(features),
                        rawLabel,
                        normalizedLabel,
                        stage));
                ++rowsEmitted;
            }
        }

        if (validationErrorCount > 0L) {
            long omitted = validationErrorCount - validationErrors.size();
            String suffix = omitted > 0L
                    ? "; plus " + omitted + " additional invalid row(s)" : "";
            throw new CsvFormatException(
                    "CSV validation failed: " + String.join("; ", validationErrors)
                            + suffix);
        }

        return new IngestionSummary(
                rowsRead, rowsEmitted, repeatedHeadersSkipped, sanitizedValues);
    }

    public List<FlowRecord> readAll(
            Path csvPath,
            List<AttackTimeline> timelines) throws IOException {
        List<FlowRecord> records = new ArrayList<>();
        ingest(csvPath, timelines, records::add);
        return List.copyOf(records);
    }

    public static List<AttackTimeline> cicIds2018Timelines() {
        return List.of(
                timeline("2018-02-14", "10:32", "12:09",
                        "FTP-BruteForce", AttackStage.INITIAL_ACCESS),
                timeline("2018-02-14", "14:01", "15:31",
                        "SSH-Bruteforce", AttackStage.INITIAL_ACCESS),
                timeline("2018-02-15", "09:26", "10:09",
                        "DoS attacks-GoldenEye", AttackStage.IMPACT),
                timeline("2018-02-15", "10:59", "11:40",
                        "DoS attacks-Slowloris", AttackStage.IMPACT),
                timeline("2018-02-28", "10:50", "12:05",
                        "Infiltration", AttackStage.INITIAL_ACCESS),
                timeline("2018-02-28", "13:42", "14:40",
                        "Infiltration", AttackStage.INITIAL_ACCESS),
                timeline("2018-03-02", "10:11", "11:34",
                        "Bot", AttackStage.COMMAND_AND_CONTROL),
                timeline("2018-03-02", "14:24", "15:55",
                        "Bot", AttackStage.COMMAND_AND_CONTROL));
    }

    public static String normalizeHeader(String header) {
        String trimmed = header == null ? "" : header.replace("\uFEFF", "").trim();
        String normalized = NON_ALPHANUMERIC.matcher(
                trimmed.toLowerCase(Locale.ROOT)).replaceAll("_");
        return normalized.replaceAll("^_+|_+$", "");
    }

    public static String normalizeLabel(String label) {
        String trimmed = label == null ? "" : label.trim();
        if (trimmed.equalsIgnoreCase("Infilteration")) {
            return "Infiltration";
        }
        if (trimmed.equalsIgnoreCase("Benign")) {
            return "Benign";
        }
        return trimmed;
    }
    private static String optionalField(
            List<String> values,
            List<String> headers,
            String... aliases) {
        for (String alias : aliases) {
            int index = headers.indexOf(alias);
            if (index >= 0) {
                return values.get(index).trim();
            }
        }
        return "";
    }

    private static int integerFeature(
            Map<String, Double> features,
            String... aliases) {
        for (String alias : aliases) {
            Double value = features.get(alias);
            if (value != null && Double.isFinite(value)) {
                if (value >= Integer.MAX_VALUE) {
                    return Integer.MAX_VALUE;
                }
                if (value <= Integer.MIN_VALUE) {
                    return Integer.MIN_VALUE;
                }
                return value.intValue();
            }
        }
        return 0;
    }


    private static List<String> normalizeHeaders(List<String> rawHeaders)
            throws CsvFormatException {
        List<String> normalized = new ArrayList<>(rawHeaders.size());
        Set<String> seen = new java.util.HashSet<>();
        for (String rawHeader : rawHeaders) {
            String header = normalizeHeader(rawHeader);
            if (header.isEmpty() || !seen.add(header)) {
                throw new CsvFormatException(
                        "Empty or duplicate normalized CSV header: " + rawHeader);
            }
            normalized.add(header);
        }
        return normalized;
    }

    private static int requiredIndex(List<String> headers, String required)
            throws CsvFormatException {
        int index = headers.indexOf(required);
        if (index < 0) {
            throw new CsvFormatException(
                    "Required CSV column is missing: " + required);
        }
        return index;
    }

    private NumericValue sanitize(String raw, long row, String header)
            throws CsvFormatException {
        String value = raw.trim();
        if (value.isEmpty()
                || value.equalsIgnoreCase("nan")
                || value.equalsIgnoreCase("inf")
                || value.equalsIgnoreCase("+inf")
                || value.equalsIgnoreCase("-inf")
                || value.equalsIgnoreCase("infinity")
                || value.equalsIgnoreCase("+infinity")
                || value.equalsIgnoreCase("-infinity")) {
            boolean negative = value.startsWith("-");
            if (value.equalsIgnoreCase("nan") || value.isEmpty()) {
                return new NumericValue(0.0, true);
            }
            return new NumericValue(
                    negative ? -absoluteClip : absoluteClip, true);
        }
        final double parsed;
        try {
            parsed = Double.parseDouble(value);
        } catch (NumberFormatException error) {
            throw new CsvFormatException(
                    "Non-numeric feature at row " + row + ", column " + header, error);
        }
        if (Double.isNaN(parsed)) {
            return new NumericValue(0.0, true);
        }
        if (parsed == Double.POSITIVE_INFINITY) {
            return new NumericValue(absoluteClip, true);
        }
        if (parsed == Double.NEGATIVE_INFINITY) {
            return new NumericValue(-absoluteClip, true);
        }
        if (parsed > absoluteClip) {
            return new NumericValue(absoluteClip, true);
        }
        if (parsed < -absoluteClip) {
            return new NumericValue(-absoluteClip, true);
        }
        return new NumericValue(parsed, false);
    }

    private static AttackStage stageFor(
            LocalDateTime timestamp,
            String normalizedLabel,
            List<AttackTimeline> timelines) {
        if ("Benign".equalsIgnoreCase(normalizedLabel) || normalizedLabel.isBlank()) {
            return AttackStage.NONE;
        }
        for (AttackTimeline timeline : timelines) {
            if (timeline.contains(timestamp)
                    && timeline.attackLabel().equalsIgnoreCase(normalizedLabel)) {
                return timeline.stage();
            }
        }
        return AttackStage.NONE;
    }

    private static AttackTimeline timeline(
            String date,
            String start,
            String finish,
            String attackLabel,
            AttackStage stage) {
        return new AttackTimeline(
                LocalDate.parse(date),
                LocalTime.parse(start),
                LocalTime.parse(finish),
                attackLabel,
                stage);
    }

    static List<String> parseCsvLine(String line) throws CsvFormatException {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int index = 0; index < line.length(); ++index) {
            char character = line.charAt(index);
            if (character == '"') {
                if (quoted && index + 1 < line.length() && line.charAt(index + 1) == '"') {
                    current.append('"');
                    ++index;
                } else {
                    quoted = !quoted;
                }
            } else if (character == ',' && !quoted) {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(character);
            }
        }
        if (quoted) {
            throw new CsvFormatException("unterminated quoted CSV field");
        }
        fields.add(current.toString());
        return fields;
    }

    private record NumericValue(double value, boolean sanitized) {
    }

    private static void addValidationError(List<String> errors, String message) {
        if (errors.size() < MAX_REPORTED_VALIDATION_ERRORS) {
            errors.add(message);
        }
    }

    /** Safe, user-actionable CSV validation failure. */
    public static final class CsvFormatException extends IOException {
        public CsvFormatException(String message) {
            super(message);
        }

        public CsvFormatException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public enum AttackStage {
        NONE,
        RECONNAISSANCE,
        INITIAL_ACCESS,
        LATERAL_MOVEMENT,
        COMMAND_AND_CONTROL,
        EXFILTRATION,
        IMPACT
    }

    public record AttackTimeline(
            LocalDate date,
            LocalTime start,
            LocalTime finish,
            String attackLabel,
            AttackStage stage) {
        public AttackTimeline {
            Objects.requireNonNull(date, "date");
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(finish, "finish");
            Objects.requireNonNull(attackLabel, "attackLabel");
            Objects.requireNonNull(stage, "stage");
            if (finish.isBefore(start)) {
                throw new IllegalArgumentException("finish must not precede start");
            }
        }

        boolean contains(LocalDateTime timestamp) {
            LocalTime time = timestamp.toLocalTime();
            return date.equals(timestamp.toLocalDate())
                    && !time.isBefore(start)
                    && !time.isAfter(finish);
        }
    }

    public record FlowRecord(
            Instant timestamp,
            String sourceIp,
            String destinationIp,
            int sourcePort,
            int destinationPort,
            int protocol,
            Map<String, Double> features,
            String rawLabel,
            String normalizedLabel,
            AttackStage stage) {
    }

    public record IngestionSummary(
            long rowsRead,
            long rowsEmitted,
            long repeatedHeadersSkipped,
            long sanitizedValues) {
    }
}
