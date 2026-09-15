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

type coherenceFake struct {
	*lifecycleFake
	now        time.Time
	calls      int
	loseLaunch bool
	allowProbe bool
	mutate     func(*sealskin.CoherenceAccess)
}

func (f *coherenceFake) LaunchURL(ctx context.Context, request sealskin.LaunchURLRequest, key string) (sealskin.LaunchResponse, error) {
	result, err := f.lifecycleFake.LaunchURL(ctx, request, key)
	if err != nil {
		return result, err
	}
	f.snapshot.CoherenceRuntimeVersion = 1
	f.snapshot.Records[0].CoherenceRequired = true
	if f.loseLaunch {
		return sealskin.LaunchResponse{}, context.DeadlineExceeded
	}
	return result, nil
}

func (f *coherenceFake) CheckCoherence(_ context.Context, home string, request sealskin.StopProfileRequest, probe bool) (sealskin.CoherenceAccess, error) {
	f.calls++
	if probe && !f.allowProbe {
		return sealskin.CoherenceAccess{}, errors.New("entry requested a forced probe")
	}
	if probe && request.BootstrapURL == "" {
		return sealskin.CoherenceAccess{}, errors.New("controller requires the launch context binding")
	}
	r := &sealskin.CoherenceReport{Version: 1, Enabled: true, Allowed: true, Mode: "strict", NetworkMode: "proxy_required", Overall: "degraded", Code: "COHERENCE_DEGRADED",
		Constraints: &sealskin.CoherenceConstraints{AllowedCountries: []string{"US"}, OnExitChange: "recheck"},
		CheckedAt:   float64(f.now.Unix()), ExpiresAt: float64(f.now.Add(45 * time.Second).Unix()), Nonce: strings.Repeat("a", 32), GateSequence: 1,
		Binding: sealskin.CoherenceBinding{ApplicationID: request.ApplicationID, ProfileID: request.ProfileID, HomeName: home, OperationID: request.OperationID,
			SessionID: request.SessionID, PolicyID: request.NetworkPolicyID, PolicySHA256: request.NetworkPolicySHA256,
			ArtifactSHA256: strings.Repeat("1", 64), AcceptanceSHA256: strings.Repeat("2", 64), EnvironmentID: "env-test-r1",
			WorkerID: strings.Repeat("a", 64), RelayID: strings.Repeat("b", 64), GuardID: strings.Repeat("c", 64),
			WorkerStartedAt: "2026-09-13T00:00:00Z", RelayStartedAt: "2026-09-13T00:00:00Z", GuardStartedAt: "2026-09-13T00:00:00Z"}}
	for _, name := range []string{"observation", "user_agent", "platform", "oscpu", "cpu", "timezone", "locale", "languages", "intl_locale", "screen", "dpr",
		"webgl", "fonts", "canvas", "audio", "voices", "webrtc", "network_path", "dns", "ipv6", "direct_bypass", "exit_observation", "country"} {
		r.Checks = append(r.Checks, sealskin.CoherenceCheck{Name: name, Status: "pass", Required: true, Code: "OBSERVED"})
	}
	r.Checks = append(r.Checks, sealskin.CoherenceCheck{Name: "city", Status: "unknown", Code: "GEOIP_CITY_UNKNOWN"})
	result := sealskin.CoherenceAccess{Version: 1, Enabled: true, Allowed: true, Report: r}
	if f.mutate != nil {
		f.mutate(&result)
	}
	return result, nil
}

func newCoherenceService(t *testing.T) (*Service, *state.Store, *coherenceFake) {
	t.Helper()
	f := &coherenceFake{lifecycleFake: &lifecycleFake{snapshot: emptyRuntime()}, now: time.Date(2026, 9, 14, 12, 0, 0, 0, time.UTC)}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "journal.json"))
	if err != nil {
		t.Fatal(err)
	}
	s, err := NewService(f, store, "https://adapter.example", []Definition{{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
		NetworkPolicyID: "socks-r1", NetworkPolicySHA256: strings.Repeat("c", 64)}}, WithLifecycle(f))
	if err != nil {
		t.Fatal(err)
	}
	s.now = func() time.Time { return f.now }
	return s, store, f
}

func TestCoherenceAllEntryPathsRefuseUnverifiedSession(t *testing.T) {
	for _, path := range []string{"new", "lost-response", "reuse", "dormant", "resume-live", "resume-dormant"} {
		t.Run(path, func(t *testing.T) {
			s, store, f := newCoherenceService(t)
			if path != "new" && path != "lost-response" {
				if _, err := s.Ensure(context.Background(), "personal"); err != nil {
					t.Fatal(err)
				}
			}
			if path == "dormant" || path == "resume-dormant" {
				makeDormant(f.lifecycleFake)
			}
			f.loseLaunch = path == "lost-response"
			f.mutate = func(r *sealskin.CoherenceAccess) { r.Report.Checks[0].Status = "unknown" }
			if strings.HasPrefix(path, "resume-") {
				if _, err := s.Resume(context.Background(), "personal"); !errors.Is(err, ErrCoherenceBlocked) {
					t.Fatalf("resume allowed: %v", err)
				}
			} else {
				got, err := s.Ensure(context.Background(), "personal")
				if !errors.Is(err, ErrCoherenceBlocked) || got.SessionID != "" || got.SessionURL != "" {
					t.Fatalf("entry allowed: %+v %v", got, err)
				}
			}
			binding, found, err := store.Get("personal")
			if err != nil || !found || binding.OperationID == "" || binding.SessionID == "" || f.launches != 1 || f.stopCalls != 0 {
				t.Fatal("denial lost ownership or created another worker")
			}
			f.mutate = nil
			if got, err := s.Ensure(context.Background(), "personal"); err != nil || got.SessionID != binding.SessionID || f.launches != 1 {
				t.Fatalf("repair did not reuse same generation: %+v %v", got, err)
			}
		})
	}
}

func TestCoherenceEntryRejectsIncompleteOrCrossBoundReports(t *testing.T) {
	for name, mutate := range map[string]func(*sealskin.CoherenceAccess){
		"missing":       func(r *sealskin.CoherenceAccess) { r.Report = nil },
		"disabled":      func(r *sealskin.CoherenceAccess) { r.Enabled = false },
		"allowed-only":  func(r *sealskin.CoherenceAccess) { r.Report.Checks = r.Report.Checks[:1] },
		"optionalized":  func(r *sealskin.CoherenceAccess) { r.Report.Checks[0].Required = false },
		"duplicate":     func(r *sealskin.CoherenceAccess) { r.Report.Checks = append(r.Report.Checks, r.Report.Checks[0]) },
		"expired":       func(r *sealskin.CoherenceAccess) { r.Report.ExpiresAt = r.Report.CheckedAt },
		"nonce":         func(r *sealskin.CoherenceAccess) { r.Report.Nonce = "" },
		"profile":       func(r *sealskin.CoherenceAccess) { r.Report.Binding.ProfileID = "work" },
		"home":          func(r *sealskin.CoherenceAccess) { r.Report.Binding.HomeName = "work" },
		"operation":     func(r *sealskin.CoherenceAccess) { r.Report.Binding.OperationID = "other" },
		"session":       func(r *sealskin.CoherenceAccess) { r.Report.Binding.SessionID = "other" },
		"app":           func(r *sealskin.CoherenceAccess) { r.Report.Binding.ApplicationID = "other" },
		"policy-id":     func(r *sealskin.CoherenceAccess) { r.Report.Binding.PolicyID = "other" },
		"policy-sha":    func(r *sealskin.CoherenceAccess) { r.Report.Binding.PolicySHA256 = strings.Repeat("d", 64) },
		"worker":        func(r *sealskin.CoherenceAccess) { r.Report.Binding.WorkerID = strings.Repeat("d", 64) },
		"artifact":      func(r *sealskin.CoherenceAccess) { r.Report.Binding.ArtifactSHA256 = "" },
		"runtime-start": func(r *sealskin.CoherenceAccess) { r.Report.Binding.RelayStartedAt = "" },
		"leak":          func(r *sealskin.CoherenceAccess) { r.Report.LeakDetected = true },
		"constraints":   func(r *sealskin.CoherenceAccess) { r.Report.Constraints = nil },
		"country-row": func(r *sealskin.CoherenceAccess) {
			r.Report.Checks = append(r.Report.Checks[:22], r.Report.Checks[23:]...)
		},
		"country-optional":    func(r *sealskin.CoherenceAccess) { r.Report.Checks[22].Required = false },
		"timezone-missing":    func(r *sealskin.CoherenceAccess) { r.Report.Constraints.AllowedTimezones = []string{"Asia/Tokyo"} },
		"direct-exit-missing": func(r *sealskin.CoherenceAccess) { r.Report.NetworkMode = "direct" },
	} {
		t.Run(name, func(t *testing.T) {
			s, _, f := newCoherenceService(t)
			f.mutate = mutate
			if got, err := s.Ensure(context.Background(), "personal"); !errors.Is(err, ErrCoherenceBlocked) || got.SessionURL != "" {
				t.Fatalf("invalid %s allowed: %v", name, err)
			}
		})
	}
}

func TestExplicitCoherenceProbeNeverStartsAnEmptyHome(t *testing.T) {
	s, store, f := newCoherenceService(t)
	f.allowProbe = true
	if _, err := s.ProbeCoherence(context.Background(), "personal"); !errors.Is(err, ErrCoherenceBlocked) || f.launches != 0 || f.calls != 0 {
		t.Fatal("probe created or sampled an empty Home")
	}
	if _, err := s.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	before, _, _ := store.Get("personal")
	got, err := s.ProbeCoherence(context.Background(), "personal")
	after, _, _ := store.Get("personal")
	if err != nil || !got.Report.Permits(f.now) || !sameHealthJournal(before, after) || f.launches != 1 || f.stopCalls != 0 {
		t.Fatalf("private probe changed generation or failed: %v", err)
	}
}

func TestCoherenceHealthRejectsDifferentEnvironmentIdentity(t *testing.T) {
	for _, field := range []string{"id", "artifact"} {
		t.Run(field, func(t *testing.T) {
			s, store, f := newCoherenceService(t)
			if _, err := s.Ensure(context.Background(), "personal"); err != nil {
				t.Fatal(err)
			}
			b, _, _ := store.Get("personal")
			r, _ := f.CheckCoherence(context.Background(), "personal", sealskin.StopProfileRequest{ProfileID: b.ProfileID, OperationID: b.OperationID, SessionID: b.SessionID, ApplicationID: b.ApplicationID, NetworkPolicyID: b.NetworkPolicyID, NetworkPolicySHA256: b.NetworkPolicySHA256}, false)
			f.observeHook = func(h *sealskin.HomeHealth) {
				h.Coherence = r.Report
				if field == "id" {
					h.Workers[0].Environment.ID = "another"
				} else {
					h.Workers[0].Environment.ArtifactSHA256 = strings.Repeat("9", 64)
				}
			}
			health, err := s.Health(context.Background(), "personal", HealthOptions{})
			if err != nil || health.Overall != OverallUnknown || health.Recovery == nil || !health.Recovery.Blocking {
				t.Fatal("cross environment report accepted")
			}
		})
	}
}

func TestCoherenceHealthIsBoundExpiresAndRedactsCapabilities(t *testing.T) {
	s, store, f := newCoherenceService(t)
	if _, err := s.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	b, _, _ := store.Get("personal")
	r, err := f.CheckCoherence(context.Background(), "personal", sealskin.StopProfileRequest{ProfileID: "personal", OperationID: b.OperationID, SessionID: b.SessionID,
		ApplicationID: b.ApplicationID, NetworkPolicyID: b.NetworkPolicyID, NetworkPolicySHA256: b.NetworkPolicySHA256}, false)
	if err != nil {
		t.Fatal(err)
	}
	f.observeHook = func(h *sealskin.HomeHealth) { h.Coherence = r.Report }
	health, err := s.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if health.Overall != OverallDegraded || health.Coherence == nil || health.ExpiresAt.Sub(f.now) != 45*time.Second {
		t.Fatalf("coherence missing: %+v", health)
	}
	public := health.Public()
	if public.Coherence.Binding.OperationID != "" || public.Coherence.Binding.SessionID != "" || health.Coherence.Binding.OperationID == "" {
		t.Fatal("public report exposed capabilities or mutated cache")
	}
	f.now = health.ExpiresAt
	expired, err := s.Health(context.Background(), "personal", HealthOptions{CachedOnly: true})
	if err != nil || expired.Overall != OverallUnknown || expired.Coherence.Allowed || expired.Recovery == nil || !expired.Recovery.Blocking || f.observeCalls != 1 {
		t.Fatal("coherence expiry was hidden or triggered a probe")
	}
}
