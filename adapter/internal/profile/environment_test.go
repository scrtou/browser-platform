package profile

import (
	"context"
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func TestEnvironmentSummaryIsReadOnlyAndCarriesCachedEvidence(t *testing.T) {
	service, store, fake, now := newHealthService(t)
	binding, _, _ := store.Get("personal")
	before := EnvironmentSummary{}
	summary, err := service.Environment(context.Background(), "personal")
	if err != nil {
		t.Fatal(err)
	}
	if summary.Observed || summary.Health != nil || summary.Status != state.StatusRunning || summary.EntryPath != "/browser/personal/" || summary.Label != "personal" {
		t.Fatalf("running Profile without a cached report: %+v", summary)
	}
	if fake.observeCalls != 0 || fake.launches != 1 || fake.stopCalls != 0 || fake.resumeCalls != 0 {
		t.Fatalf("summary reached the runtime: observe=%d launches=%d stops=%d resumes=%d", fake.observeCalls, fake.launches, fake.stopCalls, fake.resumeCalls)
	}
	if summary == before {
		t.Fatal("summary is empty")
	}
	if _, err := service.Health(context.Background(), "personal", HealthOptions{}); err != nil {
		t.Fatal(err)
	}
	summary, err = service.Environment(context.Background(), "personal")
	if err != nil || !summary.Observed || summary.Health == nil {
		t.Fatalf("cached report not surfaced: %+v err=%v", summary, err)
	}
	if summary.Health.Overall != OverallDegraded || summary.Health.Code != "EGRESS_NOT_CONFIGURED" || summary.Health.Stale || summary.Health.Environment == nil || summary.Health.Environment.ID != "env-test-r1" ||
		summary.Health.CheckedAt != *now || summary.Health.ExpiresAt.Sub(summary.Health.CheckedAt) != HealthTTL {
		t.Fatalf("health evidence: %+v", summary.Health)
	}
	if summary.NetworkMode != "unmanaged" || summary.DisplayMode != "x11" || summary.ApplicationID != "firefox" || summary.HomeName != "personal" {
		t.Fatalf("definition fields: %+v", summary)
	}
	if fake.observeCalls != 1 {
		t.Fatalf("second summary collected again: observe=%d", fake.observeCalls)
	}
	raw, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{binding.OperationID, binding.SessionID, binding.IdempotencyKey, binding.BootstrapURL} {
		if secret != "" && strings.Contains(string(raw), secret) {
			t.Fatalf("summary leaked a journal capability: %s", raw)
		}
	}
	for _, key := range []string{"operation", "session_id", "bootstrap", "idempotency", "sha256", "last_error"} {
		if strings.Contains(string(raw), `"`+key) {
			t.Fatalf("summary exposes %s: %s", key, raw)
		}
	}
	*now = now.Add(HealthTTL + time.Second)
	summary, err = service.Environment(context.Background(), "personal")
	if err != nil || !summary.Observed || !summary.Health.Stale || summary.Health.Overall != OverallUnknown {
		t.Fatalf("expired report must be stale and unknown: %+v err=%v", summary.Health, err)
	}
	if fake.observeCalls != 1 {
		t.Fatal("an expired cache triggered a collection")
	}
}

func TestEnvironmentSummaryReportsManagedDirectAndStoppedProfiles(t *testing.T) {
	service, fake := managedHealthService(t)
	fake.observeHook = func(h *sealskin.HomeHealth) { h.Network.Mode = "direct" }
	if _, err := service.Health(context.Background(), "personal", HealthOptions{}); err != nil {
		t.Fatal(err)
	}
	summary, err := service.Environment(context.Background(), "personal")
	if err != nil || summary.NetworkMode != "direct" || summary.NetworkPolicyID != "personal-socks5-r2" {
		t.Fatalf("direct summary: %+v err=%v", summary, err)
	}
	if strings.Contains(mustJSON(t, summary), strings.Repeat("a", 64)) {
		t.Fatal("summary exposes the policy digest")
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	summary, err = service.Environment(context.Background(), "personal")
	if err != nil || summary.Status != state.StatusStopped || summary.NetworkMode != "managed" {
		t.Fatalf("stopped summary: %+v err=%v", summary, err)
	}
	if !summary.Observed || summary.Health == nil || summary.Health.Overall == OverallHealthy {
		t.Fatalf("a stopped Profile must not keep reporting the old healthy generation: %+v", summary.Health)
	}
	if _, err := service.Environment(context.Background(), "missing"); err != ErrProfileNotFound {
		t.Fatalf("unknown Profile: %v", err)
	}
}

func TestEnvironmentSummaryWithoutLifecycleOrBindingIsUnobserved(t *testing.T) {
	label := "个人 · 台北"
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(&fakeOrchestrator{}, store, "https://adapter.example", []Definition{{
		ID: "personal", Label: label, ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com", WaylandMode: true,
		Language: stringPointer("zh_TW.UTF-8"), Timezone: stringPointer("Asia/Taipei"),
	}})
	if err != nil {
		t.Fatal(err)
	}
	summary, err := service.Environment(context.Background(), "personal")
	if err != nil {
		t.Fatal(err)
	}
	if summary.Observed || summary.Health != nil || summary.Status != state.StatusStopped || summary.UpdatedAt != nil {
		t.Fatalf("legacy summary: %+v", summary)
	}
	if summary.Label != label || summary.DisplayMode != "wayland" || summary.Language != "zh_TW.UTF-8" || summary.Timezone != "Asia/Taipei" {
		t.Fatalf("definition summary: %+v", summary)
	}
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := service.Environment(cancelled, "personal"); err == nil {
		t.Fatal("cancelled context produced a summary")
	}
}

func TestEnvironmentSummaryResolvesCurrentProxyNameWithoutRuntimeCalls(t *testing.T) {
	service, fake := managedHealthService(t)
	catalog := &networkProfileCatalog{profiles: map[string]networkProfileRecord{
		"office": {ID: "office", Label: "办公代理 <测试>", Revisions: []networkProfileRevisionRecord{
			{Revision: 1, Status: NetworkRevisionDisabled, UsernameSecretRef: "secret://office/username/1"},
			{Revision: 2, Status: NetworkRevisionAccepted},
		}},
		"backup": {ID: "backup", Label: "备用代理", Revisions: []networkProfileRevisionRecord{
			{Revision: 1, Status: NetworkRevisionAccepted},
		}},
	}}
	for _, tc := range []struct {
		name, mode, id, want string
		revision             int
		withoutCatalog       bool
	}{
		{name: "bound disabled revision", mode: "proxy_required", id: "office", revision: 1, want: "办公代理 <测试>"},
		{name: "changed binding", mode: "proxy_required", id: "backup", revision: 1, want: "备用代理"},
		{name: "unknown revision", mode: "proxy_required", id: "office", revision: 3},
		{name: "missing proxy", mode: "proxy_required", id: "missing", revision: 1},
		{name: "unbound proxy", mode: "proxy_required"},
		{name: "catalog unavailable", mode: "proxy_required", id: "office", revision: 1, withoutCatalog: true},
		{name: "direct ignores stale name", mode: "direct", id: "office", revision: 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			service.networkProfiles = catalog
			if tc.withoutCatalog {
				service.networkProfiles = nil
			}
			service.directory.mu.Lock()
			record := service.directory.records["personal"]
			record.NetworkMode, record.NetworkProfileID, record.NetworkProfileRevision = tc.mode, tc.id, tc.revision
			service.directory.records["personal"] = record
			service.directory.mu.Unlock()
			binding, _, _ := service.store.Get("personal")
			beforeCatalog := mustJSON(t, catalog.profiles)
			observes, launches, resumes, stops := fake.observeCalls, fake.launches, fake.resumeCalls, fake.stopCalls
			summary, err := service.Environment(context.Background(), "personal")
			if err != nil || summary.NetworkProfileLabel != tc.want {
				t.Fatalf("proxy name = %q, want %q; err=%v", summary.NetworkProfileLabel, tc.want, err)
			}
			if strings.Contains(mustJSON(t, summary), "secret://") {
				t.Fatal("proxy lookup exposed credential references")
			}
			afterBinding, _, _ := service.store.Get("personal")
			afterRecord, _ := service.record("personal")
			if mustJSON(t, binding) != mustJSON(t, afterBinding) || mustJSON(t, record) != mustJSON(t, afterRecord) || beforeCatalog != mustJSON(t, catalog.profiles) {
				t.Fatal("proxy name lookup changed persistent state")
			}
			if fake.observeCalls != observes || fake.launches != launches || fake.resumeCalls != resumes || fake.stopCalls != stops {
				t.Fatal("proxy name lookup reached the runtime")
			}
		})
	}
}

func TestDefinitionLabelValidation(t *testing.T) {
	base := Definition{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"}
	for _, label := range []string{"", "Personal", "个人 · 台北 (r9)", strings.Repeat("x", 64)} {
		definition := base
		definition.Label = label
		if err := validateDefinition(definition); err != nil {
			t.Fatalf("label %q rejected: %v", label, err)
		}
	}
	for _, label := range []string{" leading", "trailing ", "line\nbreak", "tab\tbed", strings.Repeat("x", 65), "bad\xffutf8", "ctrl\x01"} {
		definition := base
		definition.Label = label
		if err := validateDefinition(definition); err == nil {
			t.Fatalf("label %q accepted", label)
		}
	}
	if (Definition{ID: "work"}).DisplayLabel() != "work" || (Definition{ID: "work", Label: "Work"}).DisplayLabel() != "Work" {
		t.Fatal("display label fallback")
	}
}

func mustJSON(t *testing.T, value any) string {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func stringPointer(value string) *string { return &value }
