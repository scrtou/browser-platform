package profile

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func idleService(t *testing.T, timeout int) (*Service, *state.Store, *lifecycleFake, *time.Time) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(fake, store, "https://adapter.example", []Definition{{
		ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
		IdlePolicy: &IdlePolicy{Mode: "disconnected", TimeoutSeconds: timeout},
	}}, WithLifecycle(fake))
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 9, 13, 12, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	return service, store, fake, &now
}

func connections(fake *lifecycleFake, count int) {
	fake.observeHook = func(h *sealskin.HomeHealth) {
		for i := range h.Workers {
			h.Workers[i].DisplayConnections = count
		}
	}
}

func freshReport(t *testing.T, service *Service) HealthReport {
	t.Helper()
	report, err := service.Health(context.Background(), "personal", HealthOptions{Force: true})
	if err != nil && !errors.Is(err, ErrHealthThrottled) {
		t.Fatal(err)
	}
	return report
}

func TestIdleReclaimCountsOnlyWhileDisconnectedAndStopsViaVerifiedStop(t *testing.T) {
	service, store, fake, now := idleService(t, 60)
	connections(fake, 1)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "connected" {
		t.Fatalf("connected report: %+v", d)
	}
	if binding, _, _ := store.Get("personal"); binding.IdleSince != nil {
		t.Fatal("connected profile must not carry idle_since")
	}
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "counting" || d.Remaining != 60*time.Second {
		t.Fatalf("first disconnected sample: %+v", d)
	}
	binding, _, _ := store.Get("personal")
	if binding.IdleSince == nil || !binding.IdleSince.Equal(*now) {
		t.Fatalf("idle_since not persisted: %+v", binding.IdleSince)
	}
	*now = now.Add(30 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "counting" || d.Remaining != 30*time.Second {
		t.Fatalf("mid countdown: %+v", d)
	}
	// Reconnect cancels the countdown (H06).
	connections(fake, 2)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "connected" {
		t.Fatalf("reconnect: %+v", d)
	}
	if binding, _, _ := store.Get("personal"); binding.IdleSince != nil || fake.stopCalls != 0 {
		t.Fatal("reconnect must clear idle_since without stopping")
	}
	// Disconnect again; countdown restarts from zero, then expires and reclaims through Stop.
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "counting" || d.Remaining != 60*time.Second {
		t.Fatalf("restart countdown: %+v", d)
	}
	*now = now.Add(61 * time.Second)
	// Expiry on a report that says 0, but the forced fresh observation sees a
	// reconnect: no reclaim, countdown cleared.
	expired := freshReport(t, service)
	connections(fake, 1)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), expired, nil); d.Action != "connected" || fake.stopCalls != 0 {
		t.Fatalf("fresh observation must override the cached expiry: %+v stops=%d", d, fake.stopCalls)
	}
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	service.ApplyIdle(context.Background(), freshReport(t, service), nil)
	*now = now.Add(61 * time.Second)
	d := service.ApplyIdle(context.Background(), freshReport(t, service), nil)
	if d.Action != "reclaimed" || fake.stopCalls != 1 {
		t.Fatalf("expiry: %+v stops=%d", d, fake.stopCalls)
	}
	if binding, _, _ := store.Get("personal"); binding.Status != state.StatusStopped {
		t.Fatalf("binding after reclaim: %+v", binding)
	}
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "skipped" || fake.stopCalls != 1 {
		t.Fatalf("stopped profile must be skipped: %+v", d)
	}
}

func TestIdleReclaimIgnoresUnobservedStaleAndUnknownReports(t *testing.T) {
	service, store, fake, now := idleService(t, 60)
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "counting" {
		t.Fatalf("start counting: %+v", d)
	}
	// Unobservable connection count: neither advance nor clear.
	connections(fake, -1)
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "unobserved" {
		t.Fatalf("unobserved: %+v", d)
	}
	before, _, _ := store.Get("personal")
	if before.IdleSince == nil {
		t.Fatal("unobserved sample cleared idle_since")
	}
	// Control plane outage → unknown report: no decision.
	fake.observeErr = errors.New("SealSkin unavailable")
	*now = now.Add(11 * time.Second)
	if d := service.ApplyIdle(context.Background(), freshReport(t, service), nil); d.Action != "unobserved" {
		t.Fatalf("unknown report: %+v", d)
	}
	fake.observeErr = nil
	// Stale report never reclaims even if the countdown has passed.
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	fresh := freshReport(t, service)
	*now = now.Add(HealthTTL + 200*time.Second)
	stale := fresh.AsOf(*now)
	if !stale.Stale {
		t.Fatal("test precondition: report should be stale")
	}
	if d := service.ApplyIdle(context.Background(), stale, nil); d.Action != "unobserved" || fake.stopCalls != 0 {
		t.Fatalf("stale report must not reclaim: %+v stops=%d", d, fake.stopCalls)
	}
}

func TestIdleReclaimKeepsPendingWhenStopIsUnconfirmed(t *testing.T) {
	service, store, fake, now := idleService(t, 60)
	connections(fake, 0)
	*now = now.Add(11 * time.Second)
	service.ApplyIdle(context.Background(), freshReport(t, service), nil)
	fake.keepOnStop = true
	*now = now.Add(61 * time.Second)
	freshReport(t, service)
	*now = now.Add(11 * time.Second)
	d := service.ApplyIdle(context.Background(), freshReport(t, service), nil)
	if d.Action != "reclaim_pending" || fake.stopCalls != 1 {
		t.Fatalf("unconfirmed stop: %+v stops=%d", d, fake.stopCalls)
	}
	if binding, _, _ := store.Get("personal"); binding.Status != state.StatusStopping {
		t.Fatalf("binding=%+v", binding)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOperationRunning) {
		t.Fatalf("entry during pending reclaim: %v", err)
	}
	fake.keepOnStop = false
	if result, err := service.Reconcile(context.Background(), "personal"); err != nil || result.Status != state.StatusStopped {
		t.Fatalf("reconcile finishes reclaim: %+v %v", result, err)
	}
}

func TestIdleReportsAndValidation(t *testing.T) {
	service, _, fake, now := idleService(t, 900)
	connections(fake, 0)
	report := freshReport(t, service)
	if idle := check(t, report, "idle"); idle.Code != "IDLE_DISCONNECTED" || idle.Required {
		t.Fatalf("idle check before counting: %+v", idle)
	}
	service.ApplyIdle(context.Background(), report, nil)
	*now = now.Add(11 * time.Second)
	report = freshReport(t, service)
	if idle := check(t, report, "idle"); idle.Code != "IDLE_COUNTING" || !strings.Contains(idle.Message, "14m") {
		t.Fatalf("idle counting check: %+v", idle)
	}
	if report.Overall != OverallDegraded {
		t.Fatalf("an idle countdown is a degraded, non-blocking state: %s", report.Overall)
	}
	for _, policy := range []*IdlePolicy{{Mode: "input_idle", TimeoutSeconds: 900}, {Mode: "weird"}, {Mode: "disconnected", TimeoutSeconds: 10}} {
		if err := validateDefinition(Definition{ID: "p", ApplicationID: "a", HomeName: "h", StartURL: "https://x.example", IdlePolicy: policy}); err == nil {
			t.Fatalf("policy %+v accepted", policy)
		}
	}
	fake2 := &fakeOrchestrator{}
	store, _ := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if _, err := NewService(fake2, store, "https://adapter.example", []Definition{{ID: "p", ApplicationID: "a", HomeName: "h", StartURL: "https://x.example", IdlePolicy: &IdlePolicy{Mode: "disconnected", TimeoutSeconds: 900}}}); err == nil {
		t.Fatal("idle policy without lifecycle accepted")
	}
}

func TestCapacityLimitsRefuseBeforeReservation(t *testing.T) {
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	free := int64(100)
	limits := Limits{MaxActiveProfiles: 1, MaxConcurrentLaunch: 1, MinFreeDiskMiB: 500, StoragePath: "/", freeDiskMiB: func(string) (int64, error) { return free, nil }}
	service, err := NewService(fake, store, "https://adapter.example", []Definition{
		{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"},
		{ID: "work", ApplicationID: "firefox", HomeName: "work", StartURL: "https://example.com"},
	}, WithLifecycle(fake), WithLimits(limits))
	if err != nil {
		t.Fatal(err)
	}
	var capacity *CapacityError
	if _, err := service.Ensure(context.Background(), "personal"); !errors.As(err, &capacity) || capacity.Code != "CAPACITY_DISK" || !errors.Is(err, ErrCapacity) {
		t.Fatalf("disk limit: %v", err)
	}
	if _, found, _ := store.Get("personal"); found || fake.launches != 0 {
		t.Fatal("a refused launch must not write the journal or reach SealSkin")
	}
	free = 5000
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Ensure(context.Background(), "work"); !errors.As(err, &capacity) || capacity.Code != "CAPACITY_ACTIVE_PROFILES" {
		t.Fatalf("active limit: %v", err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.launches != 1 {
		t.Fatalf("existing running profile must still be reachable under the limit: %v", err)
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Ensure(context.Background(), "work"); err != nil || fake.launches != 2 {
		t.Fatalf("limit released after verified stop: %v", err)
	}
}
