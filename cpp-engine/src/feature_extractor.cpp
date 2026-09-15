#include "feature_extractor.hpp"

namespace networkwm {

struct FeatureExtractor::Impl {
    // TODO: implement internal state in Phase 2.
};

FeatureExtractor::FeatureExtractor() : impl_(new Impl{}) {
    // TODO: implement in Phase 2.
}

FeatureExtractor::~FeatureExtractor() {
    delete impl_;
}

FeatureExtractor::FeatureExtractor(FeatureExtractor&&) noexcept = default;
FeatureExtractor& FeatureExtractor::operator=(FeatureExtractor&&) noexcept = default;

bool FeatureExtractor::open(const std::string& /*pcap_path*/) {
    // TODO: implement in Phase 2.
    return false;
}

std::vector<std::uint8_t> FeatureExtractor::extract_next_batch() {
    // TODO: implement in Phase 2.
    return {};
}

} // namespace networkwm
