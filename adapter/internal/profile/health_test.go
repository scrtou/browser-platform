package profile

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func check(t *testing.T, report HealthReport, name string) HealthCheck {
	t.Helper()
	for _, item := range report.Checks {
		if item.Name == name {
			return item
		}
	}
	t.Fatalf("check %q missing in %+v", name, report.Checks)
	return HealthCheck{}
}

func newHealthService(t *testing.T) (*Service, *state.Store, *lifecycleFake, *time.Time) {
	t.Helper()
	service, store, fake := newLifecycleService(t)
	now := time.Date(2026, 9, 13, 12, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	return service, store, fake, &now
}

func TestHealthyRunningProfileBindsJournalAndObservation(t *testing.T) {
	service, store, fake, _ := newHealthService(t)
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	binding, _, _ := store.Get("personal")
	if report.Overall != OverallHealthy || report.Stale || report.Cached {
		t.Fatalf("report=%+v", report)
	}
	if report.Binding.OperationID != binding.OperationID || report.Binding.SessionID != binding.SessionID || report.Binding.Status != state.StatusRunning {
		t.Fatalf("binding not carried: %+v", report.Binding)
	}
	if report.ExpiresAt.Sub(report.CheckedAt) != HealthTTL || report.Environment.ID != "env-test-r1" {
		t.Fatalf("freshness/environment: %+v", report)
	}
	for name, code := range map[string]string{"entry": "ADAPTER_OK", "control": "CONTROL_OK", "session": "SESSION_RUNNING", "worker": "WORKER_RUNNING",
		"browser": "BROWSER_RUNNING", "display": "DISPLAY_READY", "proxy": "PROXY_NOT_CONFIGURED", "freshness": "REPORT_FRESH"} {
		if got := check(t, report, name); got.Code != code {
			t.Fatalf("%s=%+v want %s", name, got, code)
		}
	}
	if report.Recovery != nil || fake.launches != 1 || fake.stopCalls != 0 || fake.observeCalls != 1 || fake.observeUpstream[0] {
		t.Fatalf("healthy report side effects: recovery=%+v launches=%d stops=%d observe=%d", report.Recovery, fake.launches, fake.stopCalls, fake.observeCalls)
	}
	public := report.Public()
	if public.Binding.OperationID != "" || public.Binding.SessionID != "" || public.Overall != OverallHealthy {
		t.Fatalf("public report: %+v", public.Binding)
	}
}

func TestHealthCacheRejectsChangedGenerationWithoutProbing(t *testing.T) {
	for name, change := range map[string]func(*state.Binding){
		"operation":   func(b *state.Binding) { b.OperationID = strings.Repeat("b", 32) },
		"session":     func(b *state.Binding) { b.SessionID = "replacement-session" },
		"application": func(b *state.Binding) { b.ApplicationID = "replacement-app" },
		"home":        func(b *state.Binding) { b.HomeName = "replacement-home" },
		"policy": func(b *state.Binding) {
			b.NetworkPolicyID, b.NetworkPolicySHA256 = "replacement", strings.Repeat("c", 64)
		},
		"status": func(b *state.Binding) { b.Status = state.StatusUnknown },
		"resume": func(b *state.Binding) { b.ResumeIdempotencyKey = "replacement-resume" },
	} {
		t.Run(name, func(t *testing.T) {
			service, store, fake, _ := newHealthService(t)
			if _, err := service.Health(context.Background(), "personal", HealthOptions{}); err != nil {
				t.Fatal(err)
			}
			if err := store.Update("personal", func(b *state.Binding) (*state.Binding, error) { change(b); return b, nil }); err != nil {
				t.Fatal(err)
			}
			for _, opts := range []HealthOptions{{CachedOnly: true}, {}, {Force: true}} {
				report, err := service.Health(context.Background(), "personal", opts)
				if err != nil && !errors.Is(err, ErrHealthThrottled) {
					t.Fatal(err)
				}
				if report.Overall != OverallUnknown || check(t, report, "control").Code != "BINDING_CHANGED" {
					t.Fatalf("old cache escaped after %s change: %+v", name, report)
				}
			}
			if fake.observeCalls != 1 || fake.launches != 1 || fake.stopCalls != 0 {
				t.Fatal("reading an invalidated cache caused an operation")
			}
		})
	}
}

func TestHealthCollectionRejectsSessionChangeWithinSameOperation(t *testing.T) {
	service, store, fake, _ := newHealthService(t)
	fake.observeHook = func(_ *sealskin.HomeHealth) {
		if err := store.Update("personal", func(b *state.Binding) (*state.Binding, error) {
			b.SessionID = "changed-while-probing"
			return b, nil
		}); err != nil {
			t.Error(err)
		}
	}
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil || report.Overall != OverallUnknown || check(t, report, "control").Code != "BINDING_CHANGED" {
		t.Fatalf("session change accepted: %+v %v", report, err)
	}
}

func TestHealthExpiresAtExactDeadline(t *testing.T) {
	service, _, _, _ := newHealthService(t)
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if current := report.AsOf(report.ExpiresAt); !current.Stale || current.Overall != OverallUnknown {
		t.Fatal("expiry boundary was treated as fresh")
	}
}

func TestExitedBrowserIsUnhealthyWithBlockingRecoveryAndNoRelaunch(t *testing.T) {
	service, _, fake, _ := newHealthService(t)
	fake.observeHook = func(health *sealskin.HomeHealth) { health.Workers[0].Processes.BrowserMain = 0 }
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if report.Overall != OverallUnhealthy || check(t, report, "browser").Code != "BROWSER_EXITED" || check(t, report, "display").Code != "DISPLAY_READY" {
		t.Fatalf("report=%+v", report)
	}
	if report.Recovery == nil || !report.Recovery.Blocking || report.Recovery.Code != "BROWSER_EXITED" || !strings.Contains(strings.Join(report.Recovery.Steps, " "), "FireFox") {
		t.Fatalf("recovery=%+v", report.Recovery)
	}
	for range 5 {
		if _, err := service.Health(context.Background(), "personal", HealthOptions{Force: true}); err != nil && !errors.Is(err, ErrHealthThrottled) {
			t.Fatal(err)
		}
	}
	if fake.launches != 1 || fake.stopCalls != 0 {
		t.Fatal("health reporting must never launch or stop")
	}
}

func TestDisplayAndWorkerFailuresAreDistinguished(t *testing.T) {
	cases := map[string]struct {
		hook     func(*sealskin.HomeHealth)
		name     string
		code     string
		blocking bool
	}{
		"streamer missing":    {func(h *sealskin.HomeHealth) { h.Workers[0].Processes.Streamer = 0 }, "display", "DISPLAY_STREAMER_MISSING", true},
		"display server gone": {func(h *sealskin.HomeHealth) { h.Workers[0].Processes.DisplayServer = nil }, "display", "DISPLAY_SERVER_MISSING", true},
		"display endpoint": {func(h *sealskin.HomeHealth) {
			h.Workers[0].Display = sealskin.ObservedCheck{Status: "fail", Code: "DISPLAY_ENDPOINT_UNREACHABLE"}
		}, "display", "DISPLAY_ENDPOINT_UNREACHABLE", true},
		"worker dormant": {func(h *sealskin.HomeHealth) {
			h.Runtime.Workers[0].Status, h.Workers[0].Status = "exited", "exited"
		}, "worker", "WORKER_DORMANT", false},
		"worker paused": {func(h *sealskin.HomeHealth) {
			h.Runtime.Workers[0].Status, h.Workers[0].Status = "paused", "paused"
		}, "worker", "WORKER_NOT_RUNNING", false},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			service, _, fake, _ := newHealthService(t)
			fake.observeHook = tc.hook
			report, err := service.Health(context.Background(), "personal", HealthOptions{})
			if err != nil {
				t.Fatal(err)
			}
			if report.Overall != OverallUnhealthy || check(t, report, tc.name).Code != tc.code {
				t.Fatalf("%s: report=%+v", name, report)
			}
			if report.Recovery == nil || report.Recovery.Blocking != tc.blocking {
				t.Fatalf("%s: recovery=%+v", name, report.Recovery)
			}
			if tc.name == "worker" && check(t, report, "browser").Status != CheckUnknown {
				t.Fatal("an exited worker cannot prove browser state")
			}
		})
	}
}

func managedHealthService(t *testing.T) (*Service, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(fake, store, "https://adapter.example", []Definition{{
		ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
		NetworkPolicyID: "personal-socks5-r2", NetworkPolicySHA256: strings.Repeat("a", 64),
	}}, WithLifecycle(fake))
	if err != nil {
		t.Fatal(err)
	}
	service.now = func() time.Time { return time.Date(2026, 9, 13, 12, 0, 0, 0, time.UTC) }
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	return service, fake
}

func TestManagedGenerationProbesUpstreamAndReportsRelayFailures(t *testing.T) {
	service, fake := managedHealthService(t)
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if report.Overall != OverallHealthy || check(t, report, "proxy").Code != "PROXY_OK" || !fake.observeUpstream[0] {
		t.Fatalf("managed healthy report=%+v upstream=%v", report, fake.observeUpstream)
	}
	if report.Binding.NetworkPolicyID != "personal-socks5-r2" || report.Runtime.NetworkPhase != "running" {
		t.Fatalf("binding/runtime: %+v %+v", report.Binding, report.Runtime)
	}
	for name, tc := range map[string]struct {
		hook func(*sealskin.HomeHealth)
		code string
		want CheckStatus
	}{
		"relay stopped": {func(h *sealskin.HomeHealth) {
			h.Network.Relay = sealskin.RelayHealth{Container: "exited", Status: "fail", Code: "PROXY_RELAY_NOT_RUNNING"}
			h.Network.Upstream = nil
		}, "PROXY_RELAY_NOT_RUNNING", CheckFail},
		"guard stopped": {func(h *sealskin.HomeHealth) { h.Network.Guard.Container = "exited" }, "PROXY_GUARD_NOT_RUNNING", CheckFail},
		"upstream tls": {func(h *sealskin.HomeHealth) {
			h.Network.Upstream = &sealskin.ObservedCheck{Status: "fail", Code: "PROXY_TLS_INVALID"}
		}, "PROXY_TLS_INVALID", CheckFail},
		"upstream timeout": {func(h *sealskin.HomeHealth) {
			h.Network.Upstream = &sealskin.ObservedCheck{Status: "unknown", Code: "PROXY_PROBE_TIMEOUT"}
		}, "PROXY_PROBE_TIMEOUT", CheckUnknown},
		"namespace changed":  {func(h *sealskin.HomeHealth) { value := false; h.Network.WorkerNamespace = &value }, "PROXY_NAMESPACE_CHANGED", CheckFail},
		"network unobserved": {func(h *sealskin.HomeHealth) { h.Network = nil }, "PROXY_UNOBSERVED", CheckUnknown},
	} {
		t.Run(name, func(t *testing.T) {
			fake.observeHook = tc.hook
			report, err := service.Health(context.Background(), "personal", HealthOptions{Force: true})
			if err != nil && !errors.Is(err, ErrHealthThrottled) {
				t.Fatal(err)
			}
			if errors.Is(err, ErrHealthThrottled) {
				now := service.now().Add(HealthMinInterval + time.Second)
				service.now = func() time.Time { return now }
				if report, err = service.Health(context.Background(), "personal", HealthOptions{Force: true}); err != nil {
					t.Fatal(err)
				}
			}
			proxy := check(t, report, "proxy")
			if proxy.Code != tc.code || proxy.Status != tc.want || !proxy.Required {
				t.Fatalf("%s: proxy=%+v", name, proxy)
			}
			want := OverallUnhealthy
			if tc.want == CheckUnknown {
				want = OverallUnknown
			}
			if report.Overall != want || check(t, report, "browser").Code != "BROWSER_RUNNING" {
				t.Fatalf("%s: overall=%s browser=%+v", name, report.Overall, check(t, report, "browser"))
			}
			if tc.want == CheckFail && (report.Recovery == nil || !report.Recovery.Blocking || report.Recovery.Code != tc.code) {
				t.Fatalf("%s: recovery=%+v", name, report.Recovery)
			}
		})
	}
	if fake.launches != 1 || fake.stopCalls != 0 {
		t.Fatal("proxy health must not mutate the generation")
	}
}

func TestLegacyGenerationUnderNewPolicyIsDegradedNotUnhealthy(t *testing.T) {
	service, store, fake, _ := newHealthService(t)
	definition, _ := service.directory.get("personal")
	definition.NetworkPolicyID, definition.NetworkPolicySHA256 = "personal-socks5-r2", strings.Repeat("b", 64)
	service.directory.records["personal"] = Record{Definition: definition, Revision: 1}
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	binding, _, _ := store.Get("personal")
	if binding.NetworkPolicyID != "" {
		t.Fatal("test precondition: legacy binding has no policy")
	}
	proxy := check(t, report, "proxy")
	if report.Overall != OverallDegraded || proxy.Status != CheckWarn || proxy.Required || proxy.Code != "PROXY_LEGACY_GENERATION" {
		t.Fatalf("report=%+v", report)
	}
	if report.Recovery == nil || report.Recovery.Blocking || fake.observeUpstream[0] {
		t.Fatalf("legacy recovery=%+v upstream=%v", report.Recovery, fake.observeUpstream)
	}
}

func TestStoppedProfileIsOfflineAndUnknownStatesNeverPass(t *testing.T) {
	service, store, fake, _ := newHealthService(t)
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if report.Overall != OverallOffline || report.Recovery == nil || report.Recovery.Code != "PROFILE_STOPPED" || report.Recovery.Blocking {
		t.Fatalf("offline report=%+v", report)
	}
	for _, status := range []state.Status{state.StatusUnknown, state.StatusLaunching, state.StatusStopping} {
		if err := store.Update("personal", func(current *state.Binding) (*state.Binding, error) {
			current.Status = status
			if status == state.StatusStopping {
				current.StopOperationID, current.StopIdempotencyKey = "stop", "key"
			}
			return current, nil
		}); err != nil {
			t.Fatal(err)
		}
		report, err := service.Health(context.Background(), "personal", HealthOptions{Force: true})
		if err != nil && !errors.Is(err, ErrHealthThrottled) {
			t.Fatal(err)
		}
		if errors.Is(err, ErrHealthThrottled) {
			now := service.now().Add(HealthMinInterval + time.Second)
			service.now = func() time.Time { return now }
			if report, err = service.Health(context.Background(), "personal", HealthOptions{Force: true}); err != nil {
				t.Fatal(err)
			}
		}
		if report.Overall != OverallUnknown || report.Binding.Status != status {
			t.Fatalf("%s: overall=%s binding=%+v", status, report.Overall, report.Binding)
		}
	}
	if fake.launches != 1 || fake.stopCalls != 1 {
		t.Fatal("health reporting mutated the profile")
	}
}

func TestControlOutageTimeoutAndExpiryAreUnknownNotOffline(t *testing.T) {
	service, _, fake, now := newHealthService(t)
	fake.observeErr = errors.New("SealSkin unavailable")
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if report.Overall != OverallUnknown || check(t, report, "control").Code != "CONTROL_UNAVAILABLE" || check(t, report, "browser").Status != CheckUnknown {
		t.Fatalf("outage report=%+v", report)
	}
	if report.Recovery == nil || report.Recovery.Blocking {
		t.Fatalf("outage recovery=%+v", report.Recovery)
	}
	fake.observeErr = context.DeadlineExceeded
	*now = now.Add(HealthMinInterval + time.Second)
	report, err = service.Health(context.Background(), "personal", HealthOptions{Force: true})
	if err != nil || check(t, report, "control").Code != "CONTROL_TIMEOUT" || report.Overall != OverallUnknown {
		t.Fatalf("timeout report=%+v err=%v", report, err)
	}
	fake.observeErr = nil
	*now = now.Add(HealthMinInterval + time.Second)
	healthy, err := service.Health(context.Background(), "personal", HealthOptions{Force: true})
	if err != nil || healthy.Overall != OverallHealthy {
		t.Fatalf("healthy report=%+v err=%v", healthy, err)
	}
	*now = now.Add(HealthTTL + time.Second)
	expired, err := service.Health(context.Background(), "personal", HealthOptions{CachedOnly: true})
	if err != nil || !expired.Stale || expired.Overall != OverallUnknown || check(t, expired, "freshness").Code != "REPORT_EXPIRED" {
		t.Fatalf("expired report=%+v err=%v", expired, err)
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	offline, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil || offline.Overall != OverallOffline {
		t.Fatalf("offline=%+v err=%v", offline, err)
	}
	*now = now.Add(HealthTTL + time.Second)
	staleOffline, err := service.Health(context.Background(), "personal", HealthOptions{CachedOnly: true})
	if err != nil || staleOffline.Overall != OverallUnknown {
		t.Fatalf("an expired offline report must not claim offline: %+v", staleOffline)
	}
}

func TestHealthCacheThrottleAndSingleFlight(t *testing.T) {
	service, _, fake, now := newHealthService(t)
	first, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	second, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil || !second.Cached || second.CheckedAt != first.CheckedAt || fake.observeCalls != 1 {
		t.Fatalf("cache miss: cached=%v calls=%d err=%v", second.Cached, fake.observeCalls, err)
	}
	if _, err := service.Health(context.Background(), "personal", HealthOptions{Force: true}); !errors.Is(err, ErrHealthThrottled) || fake.observeCalls != 1 {
		t.Fatalf("force within %s must be throttled: err=%v calls=%d", HealthMinInterval, err, fake.observeCalls)
	}
	*now = now.Add(HealthMinInterval)
	if _, err := service.Health(context.Background(), "personal", HealthOptions{Force: true}); err != nil || fake.observeCalls != 2 {
		t.Fatalf("force after interval: err=%v calls=%d", err, fake.observeCalls)
	}
	*now = now.Add(HealthTTL + time.Second)
	if _, err := service.Health(context.Background(), "personal", HealthOptions{}); err != nil || fake.observeCalls != 3 {
		t.Fatalf("expired cache must refresh: err=%v calls=%d", err, fake.observeCalls)
	}
	*now = now.Add(HealthTTL + time.Second)
	fake.observeBlock = make(chan struct{})
	var wg sync.WaitGroup
	results := make(chan error, 20)
	for range 20 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := service.Health(context.Background(), "personal", HealthOptions{})
			results <- err
		}()
	}
	pending, err := service.Health(context.Background(), "personal", HealthOptions{Wait: 20 * time.Millisecond})
	if !errors.Is(err, ErrHealthPending) || pending.Version != 0 {
		t.Fatalf("bounded wait must report pending: %v", err)
	}
	cachedOnly, err := service.Health(context.Background(), "personal", HealthOptions{CachedOnly: true})
	if err != nil || !cachedOnly.Stale {
		t.Fatalf("cached-only during collection: %+v %v", cachedOnly, err)
	}
	close(fake.observeBlock)
	wg.Wait()
	close(results)
	for err := range results {
		if err != nil {
			t.Fatal(err)
		}
	}
	if fake.observeCalls != 4 {
		t.Fatalf("20 concurrent readers must share one observation: calls=%d", fake.observeCalls)
	}
}

func TestHealthRequiresLifecycleAndKnownProfile(t *testing.T) {
	orchestrator := &fakeOrchestrator{}
	service, _ := newTestService(t, orchestrator)
	if _, err := service.Health(context.Background(), "personal", HealthOptions{}); !errors.Is(err, ErrLifecycleDisabled) {
		t.Fatalf("lifecycle disabled: %v", err)
	}
	lifecycle, _, _, _ := newHealthService(t)
	if _, err := lifecycle.Health(context.Background(), "missing", HealthOptions{}); !errors.Is(err, ErrProfileNotFound) {
		t.Fatalf("unknown profile: %v", err)
	}
	if _, err := lifecycle.Health(context.Background(), "personal", HealthOptions{CachedOnly: true}); !errors.Is(err, ErrHealthUnavailable) {
		t.Fatalf("cached-only before any collection: %v", err)
	}
}

func TestOverallOrderFollowsSpecification(t *testing.T) {
	required := func(status CheckStatus) HealthCheck { return HealthCheck{Name: "r", Status: status, Required: true} }
	optional := func(status CheckStatus) HealthCheck { return HealthCheck{Name: "o", Status: status} }
	cases := []struct {
		checks []HealthCheck
		want   Overall
	}{
		{[]HealthCheck{required(CheckPass), optional(CheckPass)}, OverallHealthy},
		{[]HealthCheck{required(CheckPass), optional(CheckNotApplicable)}, OverallHealthy},
		{[]HealthCheck{required(CheckPass), optional(CheckWarn)}, OverallDegraded},
		{[]HealthCheck{required(CheckPass), optional(CheckUnknown)}, OverallDegraded},
		{[]HealthCheck{required(CheckPass), optional(CheckFail)}, OverallDegraded},
		{[]HealthCheck{required(CheckUnknown), optional(CheckFail)}, OverallUnknown},
		{[]HealthCheck{required(CheckFail), required(CheckUnknown)}, OverallUnhealthy},
		{[]HealthCheck{required(CheckWarn)}, OverallHealthy},
	}
	for _, tc := range cases {
		if got := overallStatus(tc.checks, false); got != tc.want {
			t.Fatalf("%+v: got %s want %s", tc.checks, got, tc.want)
		}
	}
	if overallStatus([]HealthCheck{required(CheckFail)}, true) != OverallOffline {
		t.Fatal("confirmed offline wins")
	}
}

func fixedClock() func() time.Time {
	now := time.Date(2026, 9, 13, 12, 0, 0, 0, time.UTC)
	return func() time.Time { return now }
}
