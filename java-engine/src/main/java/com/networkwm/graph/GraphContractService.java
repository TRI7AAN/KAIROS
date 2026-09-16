package com.networkwm.graph;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.networkwm.graph.GraphConstructionService.GraphEdge;
import com.networkwm.graph.GraphConstructionService.GraphNode;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/**
 * Versioned Java-to-Python JSON contract for ordered network-state graphs.
 */
@Service
public final class GraphContractService {
    public static final String CONTRACT_VERSION = "kairos.sequence.v1";

    private final ObjectMapper mapper;

    public GraphContractService() {
        mapper = new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    public GraphSequence sequence(List<GraphSnapshot> windows) {
        Objects.requireNonNull(windows, "windows");
        TreeSet<String> nodeFeatures = new TreeSet<>();
        TreeSet<String> edgeFeatures = new TreeSet<>();
        for (GraphSnapshot window : windows) {
            window.nodes().forEach(node -> nodeFeatures.addAll(node.features().keySet()));
            window.edges().forEach(edge -> edgeFeatures.addAll(edge.features().keySet()));
        }
        GraphSequence sequence = new GraphSequence(
                CONTRACT_VERSION,
                List.copyOf(nodeFeatures),
                List.copyOf(edgeFeatures),
                List.copyOf(windows));
        validate(sequence);
        return sequence;
    }

    public String toJson(GraphSequence sequence) throws JsonProcessingException {
        validate(sequence);
        return mapper.writeValueAsString(sequence);
    }

    public GraphSequence fromJson(String encoded) throws JsonProcessingException {
        GraphSequence sequence = mapper.readValue(encoded, GraphSequence.class);
        validate(sequence);
        return sequence;
    }

    public void write(Path path, GraphSequence sequence) throws IOException {
        validate(sequence);
        mapper.writeValue(path.toFile(), sequence);
    }

    public GraphSequence read(Path path) throws IOException {
        GraphSequence sequence = mapper.readValue(path.toFile(), GraphSequence.class);
        validate(sequence);
        return sequence;
    }

    public void validate(GraphSequence sequence) {
        Objects.requireNonNull(sequence, "sequence");
        if (!CONTRACT_VERSION.equals(sequence.contractVersion())) {
            throw new IllegalArgumentException(
                    "Unsupported graph contract: " + sequence.contractVersion());
        }
        if (!new HashSet<>(sequence.nodeFeatureNames()).stream()
                .allMatch(name -> name != null && !name.isBlank())
                || new HashSet<>(sequence.nodeFeatureNames()).size()
                        != sequence.nodeFeatureNames().size()) {
            throw new IllegalArgumentException("Node feature names must be unique and nonblank");
        }
        if (!new HashSet<>(sequence.edgeFeatureNames()).stream()
                .allMatch(name -> name != null && !name.isBlank())
                || new HashSet<>(sequence.edgeFeatureNames()).size()
                        != sequence.edgeFeatureNames().size()) {
            throw new IllegalArgumentException("Edge feature names must be unique and nonblank");
        }

        java.time.Instant priorStart = null;
        for (GraphSnapshot window : sequence.windows()) {
            if (!GraphConstructionService.SCHEMA_VERSION.equals(window.schemaVersion())) {
                throw new IllegalArgumentException(
                        "Unsupported graph schema: " + window.schemaVersion());
            }
            if (!window.windowStart().isBefore(window.windowEnd())) {
                throw new IllegalArgumentException("Window end must be after its start");
            }
            if (priorStart != null && window.windowStart().isBefore(priorStart)) {
                throw new IllegalArgumentException("Graph windows must be time ordered");
            }
            priorStart = window.windowStart();
            validateWindow(window, sequence);
        }
    }

    private static void validateWindow(
            GraphSnapshot window,
            GraphSequence sequence) {
        Set<String> nodeIds = new HashSet<>();
        for (GraphNode node : window.nodes()) {
            if (node.id() == null || node.id().isBlank() || !nodeIds.add(node.id())) {
                throw new IllegalArgumentException(
                        "Graph node identifiers must be unique and nonblank");
            }
            validateFeatures(node.features().keySet(), node.features().values(),
                    sequence.nodeFeatureNames(), "node");
        }
        Set<String> edgeIds = new HashSet<>();
        for (GraphEdge edge : window.edges()) {
            if (edge.id() == null || edge.id().isBlank() || !edgeIds.add(edge.id())) {
                throw new IllegalArgumentException(
                        "Graph edge identifiers must be unique and nonblank");
            }
            if (!nodeIds.contains(edge.source()) || !nodeIds.contains(edge.destination())) {
                throw new IllegalArgumentException(
                        "Graph edge references an unknown node: " + edge.id());
            }
            validateFeatures(edge.features().keySet(), edge.features().values(),
                    sequence.edgeFeatureNames(), "edge");
        }
    }

    private static void validateFeatures(
            java.util.Collection<String> keys,
            java.util.Collection<Double> values,
            List<String> schema,
            String kind) {
        if (!schema.containsAll(keys)) {
            throw new IllegalArgumentException(
                    "Graph " + kind + " contains an undeclared feature");
        }
        if (values.stream().anyMatch(value -> value == null || !Double.isFinite(value))) {
            throw new IllegalArgumentException(
                    "Graph " + kind + " features must be finite");
        }
    }

    public record GraphSequence(
            String contractVersion,
            List<String> nodeFeatureNames,
            List<String> edgeFeatureNames,
            List<GraphSnapshot> windows) {
        public GraphSequence {
            nodeFeatureNames = List.copyOf(nodeFeatureNames);
            edgeFeatureNames = List.copyOf(edgeFeatureNames);
            windows = List.copyOf(windows);
        }
    }
}
