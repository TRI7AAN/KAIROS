package com.networkwm.live;

import java.util.List;
import java.util.Objects;

public record NetworkInterfaceInfo(
        String name,
        String description,
        boolean loopback,
        List<String> addresses) {
    public NetworkInterfaceInfo {
        Objects.requireNonNull(name, "name");
        addresses = addresses == null ? List.of() : List.copyOf(addresses);
    }
}
