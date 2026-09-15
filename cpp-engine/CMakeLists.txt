cmake_minimum_required(VERSION 3.16)
project(cpp-engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Static library target for packet-level feature extraction.
# No external dependencies wired yet. Linkage to a native packet capture /
# parsing library (e.g. libpcap) is deferred to a later phase.
add_library(feature_extractor STATIC
    src/feature_extractor.cpp
)

target_include_directories(feature_extractor PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
