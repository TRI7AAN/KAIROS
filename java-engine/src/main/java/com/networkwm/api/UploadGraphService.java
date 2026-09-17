package com.networkwm.api;

import com.networkwm.graph.CicGraphDatasetService;
import com.networkwm.graph.GraphContractService.GraphSequence;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import java.util.Objects;

/** Bounded upload-to-graph adapter for the trained CIC feature contract. */
@Service
public final class UploadGraphService {
    public static final long MAX_UPLOAD_BYTES = 750L * 1024L * 1024L;

    private final CicGraphDatasetService cic;

    public UploadGraphService(CicGraphDatasetService cic) {
        this.cic = Objects.requireNonNull(cic, "cic");
    }

    public GraphSequence fromUpload(MultipartFile file) throws IOException {
        Objects.requireNonNull(file, "file");
        if (file.isEmpty()) {
            throw new IllegalArgumentException("uploaded file is empty");
        }
        if (file.getSize() > MAX_UPLOAD_BYTES) {
            throw new IllegalArgumentException(
                    "uploaded file exceeds the 750 MiB limit");
        }
        String filename = file.getOriginalFilename() == null
                ? "" : file.getOriginalFilename();
        String lower = filename.toLowerCase(Locale.ROOT);
        if (!lower.endsWith(".csv")) {
            throw new IllegalArgumentException(
                    "Phase 50 accepts CICFlowMeter CSV; PCAP schema adaptation "
                            + "is completed in Phase 58");
        }
        Path temporary = Files.createTempFile("kairos-upload-", ".csv");
        try {
            file.transferTo(temporary);
            return fromCsv(temporary);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    GraphSequence fromCsv(Path csv) throws IOException {
        return cic.aggregateCsv(csv, Duration.ofSeconds(10));
    }
}
