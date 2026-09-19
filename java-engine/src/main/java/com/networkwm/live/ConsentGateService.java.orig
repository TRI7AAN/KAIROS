package com.networkwm.live;

import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.IDN;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * Phase 70: target resolver and consent gate. A real, enforced code path.
 *
 * <ul>
 *   <li>URL/IP validation: any user-provided target (interface name or
 *   literal address) is validated as well-formed and resolvable before any
 *   action proceeds.</li>
 *   <li>DNS pinning: hostnames are resolved once, the resolved IP is pinned
 *   for the session, and sessions running longer than
 *   {@link #DNS_REVALIDATION_SECONDS} re-resolve and re-validate.</li>
 *   <li>Allowlist / lab-policy check: an explicit operator-configured
 *   allowlist of interfaces and CIDR ranges, default EMPTY (nothing is
 *   authorized until configured). Non-allowlisted targets are REFUSED.</li>
 *   <li>Audit session record: every attempt (allowed or denied) appends a
 *   JSON line with timestamp, target, mode, decision, and operator id.</li>
 * </ul>
 */
@Service
public final class ConsentGateService {
    public static final long DNS_REVALIDATION_SECONDS = 300L;

    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    private final List<String> allowedInterfaces = new ArrayList<>();
    private final List<CidrRange> allowedRanges = new ArrayList<>();
    private final CopyOnWriteArrayList<AuditRecord> auditLog =
            new CopyOnWriteArrayList<>();
    private final Path auditFile;

    public ConsentGateService() {
        this(defaultAuditFile());
    }

    public ConsentGateService(Path auditFile) {
        this.auditFile = Objects.requireNonNull(auditFile, "auditFile");
    }

    public enum Decision {
        ALLOWED,
        DENIED
    }

    public record ResolvedTarget(
            String requested,
            String pinnedIp,
            boolean loopback,
            Instant resolvedAt) {
    }

    public record AuditRecord(
            Instant timestamp,
            String requestedTarget,
            String mode,
            Decision decision,
            String reason,
            String operatorId) {
    }

    public record GateDecision(
            Decision decision,
            ResolvedTarget target,
            String reason) {
    }

    public void configureAllowlist(
            List<String> interfaces, List<String> cidrs) {
        Objects.requireNonNull(interfaces, "interfaces");
        Objects.requireNonNull(cidrs, "cidrs");
        lock.writeLock().lock();
        try {
            allowedInterfaces.clear();
            for (String name : interfaces) {
                if (name == null || name.isBlank() || name.length() > 64
                        || !name.matches("[A-Za-z0-9_.:\\-]+")) {
                    throw new IllegalArgumentException(
                            "invalid allowlisted interface: " + name);
                }
                allowedInterfaces.add(name.trim());
            }
            allowedRanges.clear();
            for (String cidr : cidrs) {
                allowedRanges.add(CidrRange.parse(cidr));
            }
        } finally {
            lock.writeLock().unlock();
        }
    }

    public List<String> allowedInterfaces() {
        lock.readLock().lock();
        try {
            return List.copyOf(allowedInterfaces);
        } finally {
            lock.readLock().unlock();
        }
    }

    public List<String> allowedRanges() {
        lock.readLock().lock();
        try {
            List<String> rendered = new ArrayList<>();
            for (CidrRange range : allowedRanges) {
                rendered.add(range.render());
            }
            return List.copyOf(rendered);
        } finally {
            lock.readLock().unlock();
        }
    }

    public GateDecision check(
            String requestedTarget, String mode, String operatorId) {
        Objects.requireNonNull(requestedTarget, "requestedTarget");
        String operator = operatorId == null ? "" : operatorId;
        String modeName = mode == null ? "passive" : mode;
        Instant now = Instant.now();

        ResolvedTarget resolved;
        try {
            resolved = resolve(requestedTarget);
        } catch (IllegalArgumentException error) {
            return deny(requestedTarget, modeName,
                    "unresolvable target: " + error.getMessage(), operator, now);
        }

        if (!"passive".equalsIgnoreCase(modeName)) {
            return deny(requestedTarget, modeName,
                    "mode '" + modeName + "' is not authorized "
                            + "(only passive capture is implemented)",
                    operator, now);
        }

        lock.readLock().lock();
        try {
            if (allowedInterfaces.isEmpty() && allowedRanges.isEmpty()) {
                return deny(requestedTarget, modeName,
                        "allowlist is empty: no target is authorized "
                                + "until the operator configures one",
                        operator, now);
            }
            if (allowedInterfaces.contains(requestedTarget.trim())) {
                return allow(requestedTarget, modeName, resolved,
                        "interface allowlist match", operator, now);
            }
            for (CidrRange range : allowedRanges) {
                if (range.contains(resolved.pinnedIp())) {
                    return allow(requestedTarget, modeName, resolved,
                            "address allowlist match (" + range.render() + ")",
                            operator, now);
                }
            }
        } finally {
            lock.readLock().unlock();
        }
        return deny(requestedTarget, modeName,
                "target is not on the operator allowlist", operator, now);
    }

    public void revalidate(ResolvedTarget target, String mode, String operatorId) {
        Objects.requireNonNull(target, "target");
        if (Duration.between(target.resolvedAt(), Instant.now()).getSeconds()
                < DNS_REVALIDATION_SECONDS) {
            return;
        }
        ResolvedTarget fresh = resolve(target.requested());
        if (!fresh.pinnedIp().equals(target.pinnedIp())) {
            throw new IllegalStateException(
                    "DNS revalidation failed: " + target.requested()
                            + " changed from " + target.pinnedIp() + " to "
                            + fresh.pinnedIp());
        }
    }

    public List<AuditRecord> auditLog() {
        return List.copyOf(auditLog);
    }

    private GateDecision allow(
            String requested, String mode, ResolvedTarget target, String reason,
            String operator, Instant now) {
        AuditRecord record = new AuditRecord(
                now, requested, mode, Decision.ALLOWED, reason, operator);
        appendAudit(record);
        return new GateDecision(Decision.ALLOWED, target, reason);
    }

    private GateDecision deny(
            String requested, String mode, String reason, String operator,
            Instant now) {
        AuditRecord record = new AuditRecord(
                now, requested, mode, Decision.DENIED, reason, operator);
        appendAudit(record);
        return new GateDecision(Decision.DENIED, null, reason);
    }

    private void appendAudit(AuditRecord record) {
        auditLog.add(record);
        try {
            if (auditFile.getParent() != null) {
                Files.createDirectories(auditFile.getParent());
            }
            String line = "{\"timestamp\":\"" + record.timestamp() + "\","
                    + "\"requestedTarget\":\"" + escape(record.requestedTarget()) + "\","
                    + "\"mode\":\"" + escape(record.mode()) + "\","
                    + "\"decision\":\"" + record.decision() + "\","
                    + "\"reason\":\"" + escape(record.reason()) + "\","
                    + "\"operatorId\":\"" + escape(record.operatorId()) + "\"}\n";
            Files.writeString(auditFile, line, StandardCharsetsHolder.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ignored) {
            // The in-memory log is authoritative; file persistence is best-effort.
        }
    }

    static ResolvedTarget resolve(String requested) {
        if (requested == null || requested.isBlank()) {
            throw new IllegalArgumentException("target must not be blank");
        }
        String trimmed = requested.trim();
        if (trimmed.length() > 253) {
            throw new IllegalArgumentException("target is too long");
        }
        if (trimmed.matches("[A-Za-z0-9_.:\\-]+") && !looksLikeAddress(trimmed)
                && !isResolvableHostname(trimmed)) {
            String known = matchKnownInterface(trimmed);
            if (known != null) {
                return new ResolvedTarget(
                        trimmed, known, isLoopbackAddress(known), Instant.now());
            }
            throw new IllegalArgumentException(
                    "unknown interface '" + trimmed + "'");
        }
        String host = stripUrl(trimmed);
        try {
            String ascii = IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES);
            InetAddress[] resolved = InetAddress.getAllByName(ascii);
            if (resolved.length == 0) {
                throw new IllegalArgumentException("no address resolved");
            }
            String pinned = resolved[0].getHostAddress();
            boolean loopback = resolved[0].isLoopbackAddress();
            return new ResolvedTarget(trimmed, pinned, loopback, Instant.now());
        } catch (UnknownHostException | IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    "cannot resolve '" + trimmed + "': " + error.getMessage(),
                    error);
        }
    }

    private static boolean isResolvableHostname(String value) {
        try {
            InetAddress.getAllByName(IDN.toASCII(value, IDN.USE_STD3_ASCII_RULES));
            return true;
        } catch (UnknownHostException | IllegalArgumentException error) {
            return false;
        }
    }

    private static boolean looksLikeAddress(String value) {
        if (value.contains(".") || value.contains(":")) {
            return true;
        }
        try {
            IDN.toASCII(value, IDN.USE_STD3_ASCII_RULES);
            return false;
        } catch (IllegalArgumentException error) {
            return false;
        }
    }

    private static String matchKnownInterface(String name) {
        List<NetworkInterfaceInfo> interfaces =
                new ProcessCaptureBackend().listInterfaces();
        for (NetworkInterfaceInfo info : interfaces) {
            if (info.name().equals(name)) {
                if (!info.addresses().isEmpty()) {
                    return info.addresses().get(0);
                }
                return info.loopback() ? "127.0.0.1" : name;
            }
        }
        if (name.equals("lo")) {
            return "127.0.0.1";
        }
        return null;
    }

    private static boolean isLoopbackAddress(String address) {
        try {
            return InetAddress.getByName(address).isLoopbackAddress();
        } catch (UnknownHostException error) {
            return false;
        }
    }

    private static String stripUrl(String value) {
        String candidate = value;
        int scheme = candidate.indexOf("://");
        if (scheme >= 0) {
            candidate = candidate.substring(scheme + 3);
        }
        int slash = candidate.indexOf('/');
        if (slash >= 0) {
            candidate = candidate.substring(0, slash);
        }
        int at = candidate.lastIndexOf('@');
        if (at >= 0) {
            candidate = candidate.substring(at + 1);
        }
        if (candidate.startsWith("[") && candidate.contains("]")) {
            return candidate.substring(1, candidate.indexOf(']'));
        }
        int colon = candidate.lastIndexOf(':');
        if (colon >= 0 && candidate.indexOf(':') == colon
                && !candidate.substring(colon + 1).contains(".")
                && candidate.substring(colon + 1).matches("\\d+")) {
            return candidate.substring(0, colon);
        }
        return candidate;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static Path defaultAuditFile() {
        String configured = System.getProperty("kairos.live.audit");
        if (configured != null && !configured.isBlank()) {
            return Path.of(configured);
        }
        return Path.of("live-sessions", "audit.log");
    }

    static final class CidrRange {
        private final byte[] network;
        private final int prefix;
        private final boolean ipv6;
        private final String rendered;

        private CidrRange(byte[] network, int prefix, boolean ipv6, String rendered) {
            this.network = network;
            this.prefix = prefix;
            this.ipv6 = ipv6;
            this.rendered = rendered;
        }

        static CidrRange parse(String cidr) {
            if (cidr == null || cidr.isBlank()) {
                throw new IllegalArgumentException("CIDR must not be blank");
            }
            String trimmed = cidr.trim();
            String address = trimmed;
            int prefix = -1;
            int slash = trimmed.indexOf('/');
            if (slash >= 0) {
                address = trimmed.substring(0, slash);
                try {
                    prefix = Integer.parseInt(trimmed.substring(slash + 1));
                } catch (NumberFormatException error) {
                    throw new IllegalArgumentException(
                            "invalid CIDR prefix: " + cidr, error);
                }
            }
            final InetAddress base;
            try {
                base = InetAddress.getByName(address);
            } catch (UnknownHostException error) {
                throw new IllegalArgumentException(
                        "invalid CIDR address: " + cidr, error);
            }
            boolean ipv6 = base instanceof Inet6Address;
            int max = ipv6 ? 128 : 32;
            if (prefix < 0) {
                prefix = max;
            }
            if (prefix < 0 || prefix > max) {
                throw new IllegalArgumentException(
                        "CIDR prefix out of range: " + cidr);
            }
            byte[] raw = base.getAddress();
            int fullBytes = prefix / 8;
            int restBits = prefix % 8;
            byte[] masked = raw.clone();
            for (int i = fullBytes + (restBits > 0 ? 1 : 0); i < masked.length; i++) {
                masked[i] = 0;
            }
            if (restBits > 0 && fullBytes < masked.length) {
                int mask = 0xFF << (8 - restBits);
                masked[fullBytes] = (byte) (masked[fullBytes] & mask);
            }
            if (!ipv6 && !(base instanceof Inet4Address)) {
                throw new IllegalArgumentException("invalid IPv4 CIDR: " + cidr);
            }
            return new CidrRange(
                    masked, prefix, ipv6,
                    base.getHostAddress() + "/" + prefix);
        }

        boolean contains(String address) {
            final InetAddress candidate;
            try {
                candidate = InetAddress.getByName(address);
            } catch (UnknownHostException error) {
                return false;
            }
            if ((candidate instanceof Inet6Address) != ipv6) {
                return false;
            }
            byte[] raw = candidate.getAddress();
            int fullBytes = prefix / 8;
            int restBits = prefix % 8;
            for (int i = 0; i < fullBytes; i++) {
                if (raw[i] != network[i]) {
                    return false;
                }
            }
            if (restBits > 0 && fullBytes < raw.length) {
                int mask = 0xFF << (8 - restBits);
                if ((raw[fullBytes] & mask) != (network[fullBytes] & mask)) {
                    return false;
                }
            }
            return true;
        }

        String render() {
            return rendered.toLowerCase(Locale.ROOT);
        }
    }

    private static final class StandardCharsetsHolder {
        private static final java.nio.charset.Charset UTF_8 =
                java.nio.charset.StandardCharsets.UTF_8;
    }
}
