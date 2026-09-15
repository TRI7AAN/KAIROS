cmake_minimum_required(VERSION 3.16)
project(cpp-engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Static library target for the dependency-free classic-PCAP feature extractor.
# Phase 4 intentionally avoids a libpcap runtime dependency so offline builds
# can parse Ethernet/raw-IPv4 PCAP files directly.
add_library(feature_extractor STATIC
    src/feature_extractor.cpp
)

target_include_directories(feature_extractor PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
