package com.networkwm.api;

import com.networkwm.bridge.PythonMlClient;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.narrative.NarrativeModeService;
import com.networkwm.narrative.LocalNarrativeService.Narrative;
import com.networkwm.ingestion.IngestionService.CsvFormatException;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.util.Objects;

/** Public Java boundary for validated graph forecasts. */
@RestController
@CrossOrigin(origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000"
})
@RequestMapping("/forecast")
public final class ForecastController {
    private final PythonMlClient python;
    private final NarrativeModeService narratives;
    private final UploadGraphService uploads;

    public ForecastController(
            PythonMlClient python,
            NarrativeModeService narratives,
            UploadGraphService uploads) {
        this.python = Objects.requireNonNull(python, "python");
        this.narratives = Objects.requireNonNull(narratives, "narratives");
        this.uploads = Objects.requireNonNull(uploads, "uploads");
    }

    @PostMapping
    public ForecastResponse forecast(@RequestBody ForecastRequest request) {
        if (request == null || request.contract() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "contract is required");
        }
        int rolloutSteps =
                request.rolloutSteps() == null ? 3 : request.rolloutSteps();
        try {
            PredictionResponse prediction =
                    python.predict(request.contract(), rolloutSteps);
            Narrative narrative = narratives.generate(prediction);
            return new ForecastResponse(
                    "kairos.forecast.v1", prediction, narrative);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IOException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "Python ML service unavailable or returned invalid data",
                    error);
        }
    }

    @PostMapping(
            path = "/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> forecastUpload(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "rolloutSteps", defaultValue = "3")
                    int rolloutSteps) {
        try {
            GraphSequence contract = uploads.fromUpload(file);
            return ResponseEntity.ok(
                    forecast(new ForecastRequest(contract, rolloutSteps)));
        } catch (ResponseStatusException error) {
            // forecast() already classified the failure (400 = bad traffic
            // contract such as unexpected CSV columns; 502 = ML service
            // down/broken). Preserve that status here so uploads report a
            // 400 with the Python detail instead of a bare 502, and keep the
            // UploadError body shape the dashboard expects.
            HttpStatusCode status = error.getStatusCode();
            String detail = error.getReason() != null
                    ? error.getReason() : "Forecast failed";
            Throwable cause = error.getCause();
            if (cause != null && cause.getMessage() != null
                    && !cause.getMessage().isBlank()
                    && !detail.contains(cause.getMessage())) {
                String causeMessage = cause.getMessage();
                if (causeMessage.length() > 1_500) {
                    causeMessage = causeMessage.substring(0, 1_500);
                }
                detail = detail + ": " + causeMessage;
            }
            return ResponseEntity.status(status).body(new UploadError(detail));
        } catch (IllegalArgumentException error) {
            return ResponseEntity.badRequest().body(
                    new UploadError(error.getMessage()));
        } catch (CsvFormatException error) {
            return ResponseEntity.unprocessableEntity().body(
                    new UploadError(error.getMessage()));
        } catch (IOException error) {
            return ResponseEntity.unprocessableEntity().body(
                    new UploadError("Unable to ingest uploaded traffic file"));
        }
    }

    public record UploadError(String detail) {
    }

    public record ForecastRequest(
            GraphSequence contract,
            Integer rolloutSteps) {
    }

    public record ForecastResponse(
            String artifactVersion,
            PredictionResponse prediction,
            Narrative narrative) {
    }
}
