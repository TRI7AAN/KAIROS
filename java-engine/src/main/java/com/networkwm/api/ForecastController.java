package com.networkwm.api;

import com.networkwm.bridge.PythonMlClient;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.narrative.LocalNarrativeService;
import com.networkwm.narrative.LocalNarrativeService.Narrative;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.util.Objects;

/** Public Java boundary for validated graph forecasts. */
@RestController
@RequestMapping("/forecast")
public final class ForecastController {
    private final PythonMlClient python;
    private final LocalNarrativeService narratives;

    public ForecastController(
            PythonMlClient python,
            LocalNarrativeService narratives) {
        this.python = Objects.requireNonNull(python, "python");
        this.narratives = Objects.requireNonNull(narratives, "narratives");
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
