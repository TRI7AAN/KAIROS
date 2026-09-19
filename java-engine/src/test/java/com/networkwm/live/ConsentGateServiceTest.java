package com.networkwm.live;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConsentGateServiceTest {
    @TempDir
    Path temporaryDirectory;

    private ConsentGateService gate() {
        return new ConsentGateService(
                temporaryDirectory.resolve("audit-" + System.nanoTime() + ".log"));
    }

    @Test
    void emptyAllowlistDeniesEverything() {
        ConsentGateService gate = gate();
        ConsentGateService.GateDecision decision =
                gate.check("lo", "passive", "operator-1");
        assertEquals(ConsentGateService.Decision.DENIED, decision.decision());
        assertNull(decision.target());
        assertEquals(1, gate.auditLog().size());
        assertEquals(ConsentGateService.Decision.DENIED,
                gate.auditLog().get(0).decision());
    }

    @Test
    void allowlistedInterfaceProceedsAndIsAudited() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of("lo"), List.of());
        ConsentGateService.GateDecision decision =
                gate.check("lo", "passive", "operator-2");
        assertEquals(ConsentGateService.Decision.ALLOWED, decision.decision());
        assertNotNull(decision.target());
        assertEquals("127.0.0.1", decision.target().pinnedIp());
        assertTrue(decision.target().loopback());
        assertEquals(1, gate.auditLog().size());
        assertEquals(ConsentGateService.Decision.ALLOWED,
                gate.auditLog().get(0).decision());
        assertEquals("operator-2", gate.auditLog().get(0).operatorId());
    }

    @Test
    void outOfAllowlistTargetIsRefusedAndLogged() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of("lo"), List.of("127.0.0.0/8"));
        ConsentGateService.GateDecision decision =
                gate.check("8.8.8.8", "passive", "operator-3");
        assertEquals(ConsentGateService.Decision.DENIED, decision.decision());
        assertEquals(1, gate.auditLog().size());
        assertEquals(ConsentGateService.Decision.DENIED,
                gate.auditLog().get(0).decision());
        assertEquals("8.8.8.8", gate.auditLog().get(0).requestedTarget());
    }

    @Test
    void allowlistedCidrRangeAuthorizesMatchingAddress() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of(), List.of("127.0.0.0/8"));
        ConsentGateService.GateDecision allowed =
                gate.check("127.0.0.5", "passive", "operator-4");
        assertEquals(ConsentGateService.Decision.ALLOWED, allowed.decision());
        assertEquals("127.0.0.5", allowed.target().pinnedIp());
        ConsentGateService.GateDecision denied =
                gate.check("10.0.2.15", "passive", "operator-4");
        assertEquals(ConsentGateService.Decision.DENIED, denied.decision());
        assertEquals(2, gate.auditLog().size());
    }

    @Test
    void hostnameIsPinnedToResolvedIp() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of(), List.of("127.0.0.0/8", "::1/128"));
        ConsentGateService.GateDecision decision =
                gate.check("localhost", "passive", "operator-5");
        assertEquals(ConsentGateService.Decision.ALLOWED, decision.decision());
        assertNotNull(decision.target().pinnedIp());
    }

    @Test
    void activeModeIsAlwaysRefused() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of("lo"), List.of("127.0.0.0/8"));
        ConsentGateService.GateDecision decision =
                gate.check("lo", "active", "operator-6");
        assertEquals(ConsentGateService.Decision.DENIED, decision.decision());
        assertEquals(ConsentGateService.Decision.DENIED,
                gate.auditLog().get(0).decision());
    }

    @Test
    void unresolvableTargetIsRefused() {
        ConsentGateService gate = gate();
        gate.configureAllowlist(List.of("lo"), List.of("0.0.0.0/0"));
        ConsentGateService.GateDecision decision = gate.check(
                "kairos-nonexistent0", "passive", "operator-7");
        assertEquals(ConsentGateService.Decision.DENIED, decision.decision());
    }
}
