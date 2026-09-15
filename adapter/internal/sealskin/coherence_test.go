package sealskin

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func protocolCoherenceReport(request StopProfileRequest) *CoherenceReport {
	now := time.Now().Add(-time.Second)
	report := &CoherenceReport{Version: 1, Enabled: true, Mode: "strict", NetworkMode: "direct",
		Constraints: &CoherenceConstraints{AllowedCountries: []string{"US"}, OnExitChange: "recheck"},
		Overall:     "degraded", Allowed: true, Code: "COHERENCE_DEGRADED",
		CheckedAt: float64(now.UnixNano()) / 1e9, ExpiresAt: float64(now.Add(time.Minute).UnixNano()) / 1e9,
		Nonce: strings.Repeat("a", 32), GateSequence: 1789418577645029073,
		Binding: CoherenceBinding{ApplicationID: request.ApplicationID, ProfileID: request.ProfileID, HomeName: "personal",
			OperationID: request.OperationID, SessionID: request.SessionID, PolicyID: request.NetworkPolicyID,
			PolicySHA256: request.NetworkPolicySHA256, EnvironmentID: "env-us-test-r1",
			ArtifactSHA256: strings.Repeat("b", 64), AcceptanceSHA256: strings.Repeat("c", 64),
			WorkerID: strings.Repeat("d", 64), RelayID: strings.Repeat("e", 64), GuardID: strings.Repeat("f", 64),
			WorkerStartedAt: now.Add(-time.Minute).Format(time.RFC3339Nano), RelayStartedAt: now.Add(-time.Minute).Format(time.RFC3339Nano),
			GuardStartedAt: now.Add(-time.Minute).Format(time.RFC3339Nano)}}
	for _, name := range append(append([]string{}, coherenceRequiredChecks...), "country", "direct_exit") {
		report.Checks = append(report.Checks, CoherenceCheck{Name: name, Status: "pass", Required: true, Code: "OBSERVED"})
	}
	report.Checks = append(report.Checks, CoherenceCheck{Name: "city", Status: "unknown", Code: "GEOIP_CITY_UNKNOWN"})
	return report
}

func TestCoherenceUsesAuthenticatedEncryptedPostsWithCompleteBinding(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	request := StopProfileRequest{ProfileID: "personal", ApplicationID: "camoufox-qa", OperationID: strings.Repeat("a", 32),
		SessionID: "qa-session", BootstrapURL: "https://adapter.example/bootstrap/personal/operation",
		NetworkPolicyID: "direct-qa-r1", NetworkPolicySHA256: strings.Repeat("b", 64)}
	report := protocolCoherenceReport(request)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey,
		coherence: CoherenceAccess{Version: 1, Enabled: true, Allowed: true, Report: report}}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	for _, probe := range []bool{false, true} {
		got, err := client.CheckCoherence(context.Background(), "personal", request, probe)
		if err != nil || !got.Allowed || got.Report.GateSequence != report.GateSequence {
			t.Fatalf("complete encrypted coherence request failed: %v", err)
		}
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if len(fake.coherenceBodies) != 2 || fake.coherenceBodies[0] != request || fake.coherenceBodies[1] != request ||
		fake.coherenceKeys[0] == "" || fake.coherenceKeys[0] == fake.coherenceKeys[1] ||
		fake.coherencePaths[0] != "/api/profile-runtime/personal/coherence/access" || fake.coherencePaths[1] != "/api/profile-runtime/personal/coherence/probe" {
		t.Fatal("coherence omitted the binding, request identity, or action")
	}
}

func TestCoherenceEncryptedResponsesPreserveBlockedReportsAndRejectOtherGenerations(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	request := StopProfileRequest{ProfileID: "personal", ApplicationID: "camoufox-qa", OperationID: strings.Repeat("a", 32),
		SessionID: "qa-session", BootstrapURL: "https://adapter.example/bootstrap/personal/operation",
		NetworkPolicyID: "direct-qa-r1", NetworkPolicySHA256: strings.Repeat("b", 64)}
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	report := protocolCoherenceReport(request)
	report.Allowed, report.Overall, report.Code = false, "unknown", "COHERENCE_UNOBSERVED"
	fake.coherence = CoherenceAccess{Version: 1, Enabled: true, Allowed: false, Report: report}
	got, err := client.CheckCoherence(context.Background(), "personal", request, true)
	if err != nil || got.Allowed || got.Report.Code != "COHERENCE_UNOBSERVED" {
		t.Fatalf("blocked report was lost: %v", err)
	}
	report = protocolCoherenceReport(request)
	report.Binding.SessionID = "another-session"
	fake.mu.Lock()
	fake.coherence = CoherenceAccess{Version: 1, Enabled: true, Allowed: true, Report: report}
	fake.mu.Unlock()
	if _, err := client.CheckCoherence(context.Background(), "personal", request, false); err == nil {
		t.Fatal("accepted another generation's permitted report")
	}
}
