#include "feature_extractor.hpp"

#include <jni.h>

#include <cstddef>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

void throw_java(JNIEnv* env, const char* class_name, const std::string& message) {
    jclass exception_class = env->FindClass(class_name);
    if (exception_class != nullptr) {
        env->ThrowNew(exception_class, message.c_str());
    }
}

std::string json_escape(const std::string& value) {
    std::ostringstream escaped;
    for (const unsigned char character : value) {
        switch (character) {
        case '"': escaped << "\\\""; break;
        case '\\': escaped << "\\\\"; break;
        case '\b': escaped << "\\b"; break;
        case '\f': escaped << "\\f"; break;
        case '\n': escaped << "\\n"; break;
        case '\r': escaped << "\\r"; break;
        case '\t': escaped << "\\t"; break;
        default:
            if (character < 0x20U) {
                escaped << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << static_cast<unsigned>(character)
                        << std::dec;
            } else {
                escaped << character;
            }
        }
    }
    return escaped.str();
}

std::string serialize(const networkwm::ExtractionBatch& batch) {
    std::ostringstream json;
    json << std::setprecision(12) << "{\"flows\":[";
    for (std::size_t index = 0; index < batch.flows.size(); ++index) {
        if (index != 0U) {
            json << ',';
        }
        const auto& value = batch.flows[index];
        json << "{\"sourceIp\":\"" << json_escape(value.key.source_ip)
             << "\",\"destinationIp\":\""
             << json_escape(value.key.destination_ip)
             << "\",\"sourcePort\":" << value.key.source_port
             << ",\"destinationPort\":" << value.key.destination_port
             << ",\"protocol\":" << static_cast<unsigned>(value.key.protocol)
             << ",\"packetCount\":" << value.packet_count
             << ",\"ttlMean\":" << value.ttl_mean
             << ",\"ttlVariance\":" << value.ttl_variance
             << ",\"tcpWindowTrend\":" << value.tcp_window_trend
             << ",\"fragmentCount\":" << value.fragment_count
             << ",\"retransmissionCount\":" << value.retransmission_count
             << ",\"truncatedPacketCount\":" << value.truncated_packet_count
             << ",\"payloadSizeMean\":" << value.payload_size_mean
             << ",\"payloadSizeStddev\":" << value.payload_size_stddev
             << ",\"payloadSizeSkew\":" << value.payload_size_skew << '}';
    }
    json << "],\"portScans\":[";
    for (std::size_t index = 0; index < batch.port_scans.size(); ++index) {
        if (index != 0U) {
            json << ',';
        }
        const auto& value = batch.port_scans[index];
        json << "{\"sourceIp\":\"" << json_escape(value.source_ip)
             << "\",\"observedPackets\":" << value.observed_packets
             << ",\"uniqueDestinationPorts\":"
             << value.unique_destination_ports
             << ",\"sequentialTransitionRatio\":"
             << value.sequential_transition_ratio
             << ",\"pattern\":\"" << networkwm::to_string(value.pattern)
             << "\"}";
    }
    json << "]}";
    return json.str();
}

} // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_com_networkwm_bridge_CppBridge_extractNative(
    JNIEnv* env,
    jclass,
    jstring capture_path,
    jlong maximum_packets,
    jint minimum_unique_ports,
    jdouble sequential_ratio_threshold) {
    if (capture_path == nullptr) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "capturePath must not be null");
        return nullptr;
    }

    const char* path_chars = env->GetStringUTFChars(capture_path, nullptr);
    if (path_chars == nullptr) {
        return nullptr;
    }
    const std::string path(path_chars);
    env->ReleaseStringUTFChars(capture_path, path_chars);

    try {
        networkwm::FeatureExtractor extractor;
        if (!extractor.open(path)) {
            throw_java(env, "java/io/IOException", extractor.last_error());
            return nullptr;
        }
        const networkwm::PortScanConfig config{
            static_cast<std::size_t>(minimum_unique_ports),
            sequential_ratio_threshold};
        const auto batch = extractor.extract_next_batch_analysis(
            static_cast<std::size_t>(maximum_packets), config);
        const std::string encoded = serialize(batch);
        return env->NewStringUTF(encoded.c_str());
    } catch (const std::exception& error) {
        throw_java(env, "java/lang/IllegalArgumentException", error.what());
        return nullptr;
    }
}
