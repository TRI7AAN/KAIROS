package com.networkwm.bridge;

/**
 * JNI/JNA bridge to the C++ packet feature extraction engine.
 *
 * Intended responsibility (deferred to later phases):
 *   - Load the native cpp-engine shared library.
 *   - Expose Java-callable methods that delegate to FeatureExtractor
 *     (open PCAP, extract next batch of packet-level features).
 *   - In the prototype, fall back to subprocess invocation of a C++
 *     CLI wrapper if JNI/JNA binding is not yet available.
 *
 * TODO: implement in Phase 2 (C++ engine integration) and Phase 3 (bridge wiring).
 */
public class CppBridge {
    // TODO: implement in Phase 2/3.
}
