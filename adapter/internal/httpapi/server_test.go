package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type fakeProfiles struct {
	ensureCalls      int
	session          sealskin.Session
	err              error
	target           string
	health           profile.HealthReport
	healthErr        error
	healthCalls      int
	healthOptions    []profile.HealthOptions
	healthDelay      time.Duration
	environments     map[string]profile.EnvironmentSummary
	environmentErr   error
	environmentCalls []string
	stopCalls        []string
	stopResult       profile.LifecycleResult
	stopErr          error
	updates          []profile.BrowserPatch
	updateErr        error
	updateRevision   int
}

func (f *fakeProfiles) Stop(_ context.Context, id string) (profile.LifecycleResult, error) {
	f.stopCalls = append(f.stopCalls, id)
	return f.stopResult, f.stopErr
}

func (f *fakeProfiles) UpdateBrowser(id string, revision int, _ string, patch profile.BrowserPatch) (profile.Record, error) {
	if f.updateErr != nil {
		return profile.Record{}, f.updateErr
	}
	summary, ok := f.environments[id]
	if !ok {
		return profile.Record{}, profile.ErrProfileNotFound
	}
	if revision != summary.Revision {
		return profile.Record{}, profile.ErrRevisionMismatch
	}
	f.updates = append(f.updates, patch)
	if patch.Label != nil {
		summary.Label = *patch.Label
	}
	if patch.StartURL != nil {
		summary.StartURL = *patch.StartURL
	}
	if patch.Disabled != nil {
		summary.Enabled = !*patch.Disabled
	}
	summary.Revision++
	f.environments[id] = summary
	f.updateRevision = summary.Revision
	return profile.Record{Definition: profile.Definition{ID: id, Label: summary.Label, StartURL: summary.StartURL, Disabled: !summary.Enabled}, Revision: summary.Revision}, nil
}

func TestUnsupportedRuntimeReturnsUnavailableWithoutSessionAddress(t *testing.T) {
	profiles := &fakeProfiles{err: profile.ErrRuntimeUnsupported}
	server := New(profiles, nil, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil))
	if response.Code != http.StatusServiceUnavailable || response.Header().Get("Location") != "" || !strings.Contains(response.Body.String(), "需完成维护后再试") {
		t.Fatalf("unexpected capability rejection: status=%d body=%q", response.Code, response.Body.String())
	}
}

func (f *fakeProfiles) Health(ctx context.Context, _ string, opts profile.HealthOptions) (profile.HealthReport, error) {
	f.healthCalls++
	f.healthOptions = append(f.healthOptions, opts)
	if f.healthDelay > 0 {
		select {
		case <-time.After(f.healthDelay):
		case <-ctx.Done():
			return profile.HealthReport{}, ctx.Err()
		}
	}
	return f.health, f.healthErr
}

func (f *fakeProfiles) Environment(_ context.Context, id string) (profile.EnvironmentSummary, error) {
	f.environmentCalls = append(f.environmentCalls, id)
	if f.environmentErr != nil {
		return profile.EnvironmentSummary{}, f.environmentErr
	}
	summary, ok := f.environments[id]
	if !ok {
		return profile.EnvironmentSummary{}, profile.ErrProfileNotFound
	}
	return summary, nil
}

func (f *fakeProfiles) Ensure(context.Context, string) (sealskin.Session, error) {
	f.ensureCalls++
	return f.session, f.err
}

func (f *fakeProfiles) BootstrapTarget(profileID, operationID string) (string, error) {
	if profileID != "personal" || operationID != "operation-1" {
		return "", profile.ErrProfileNotFound
	}
	return f.target, nil
}

func TestEntryGETDoesNotLaunchAndPOSTRedirects(t *testing.T) {
	profiles := &fakeProfiles{session: sealskin.Session{
		SessionID: "session-1", SessionURL: "/session-1/?access_token=secret",
	}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})

	get := httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil)
	getResponse := httptest.NewRecorder()
	server.ServeHTTP(getResponse, get)
	if getResponse.Code != http.StatusOK || profiles.ensureCalls != 0 {
		t.Fatalf("GET status=%d ensureCalls=%d", getResponse.Code, profiles.ensureCalls)
	}
	if !strings.Contains(getResponse.Body.String(), `method="post"`) {
		t.Fatal("entry does not POST to start")
	}
	if getResponse.Header().Get("Referrer-Policy") != "same-origin" {
		t.Fatal("entry must preserve its origin on the form POST")
	}
	if getResponse.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("entry must not be cached")
	}
	if !strings.Contains(getResponse.Header().Get("Content-Security-Policy"), "form-action 'self' https://sessions.example;") {
		t.Fatal("entry must allow the form's redirect to the configured Session origin")
	}

	post := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
	post.Header.Set("Origin", "https://adapter.example")
	postResponse := httptest.NewRecorder()
	server.ServeHTTP(postResponse, post)
	if postResponse.Code != http.StatusSeeOther || profiles.ensureCalls != 1 {
		t.Fatalf("POST status=%d ensureCalls=%d body=%s", postResponse.Code, profiles.ensureCalls, postResponse.Body.String())
	}
	want := "https://sessions.example/session-1/?access_token=secret&embedded=true"
	if location := postResponse.Header().Get("Location"); location != want {
		t.Fatalf("Location=%q, want %q", location, want)
	}
	if postResponse.Header().Get("Cache-Control") != "no-store" || postResponse.Header().Get("Referrer-Policy") != "no-referrer" {
		t.Fatal("token-bearing redirect lacks no-store/no-referrer")
	}
	for _, origin := range []string{"null", "https://evil.example", "https://adapter.example.evil.example", "http://adapter.example"} {
		t.Run("reject_"+origin, func(t *testing.T) {
			crossOrigin := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
			crossOrigin.Header.Set("Origin", origin)
			crossOriginResponse := httptest.NewRecorder()
			server.ServeHTTP(crossOriginResponse, crossOrigin)
			if crossOriginResponse.Code != http.StatusForbidden || profiles.ensureCalls != 1 {
				t.Fatalf("cross-origin status=%d ensureCalls=%d", crossOriginResponse.Code, profiles.ensureCalls)
			}
			if crossOriginResponse.Header().Get("Location") != "" {
				t.Fatal("rejected start must not disclose a Session URL")
			}
		})
	}
}

type fakeLaunchProfiles struct {
	*fakeProfiles
	issuedSubject string
	issuedProfile string
	usedSubject   string
	usedProfile   string
	usedToken     string
}

func (f *fakeLaunchProfiles) IssueLaunchPlan(_ context.Context, subject, profileID string) (profile.LaunchPlan, error) {
	f.issuedSubject, f.issuedProfile = subject, profileID
	return profile.LaunchPlan{Token: "plan-token", ProfileID: profileID, Revision: 3, ExpiresAt: time.Now().Add(time.Minute)}, nil
}

func (f *fakeLaunchProfiles) EnsureWithLaunchPlan(_ context.Context, subject, profileID, token string) (sealskin.Session, error) {
	f.usedSubject, f.usedProfile, f.usedToken = subject, profileID, token
	return f.session, nil
}

func TestAuthenticatedEntryRequiresIssuedLaunchPlan(t *testing.T) {
	profiles := &fakeLaunchProfiles{fakeProfiles: &fakeProfiles{session: sealskin.Session{SessionID: "session-1", SessionURL: "/session-1/?access_token=secret"}}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"start"}}}
	get := withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil), "alice", grants)
	getResponse := httptest.NewRecorder()
	server.ServeHTTP(getResponse, get)
	if getResponse.Code != http.StatusOK || profiles.issuedSubject != "alice" || profiles.issuedProfile != "personal" || !strings.Contains(getResponse.Body.String(), `name="launch_plan" value="plan-token"`) {
		t.Fatalf("entry plan: status=%d subject=%q profile=%q body=%s", getResponse.Code, profiles.issuedSubject, profiles.issuedProfile, getResponse.Body.String())
	}
	missing := withGrants(httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil), "alice", grants)
	missing.Header.Set("Origin", "https://adapter.example")
	missingResponse := httptest.NewRecorder()
	server.ServeHTTP(missingResponse, missing)
	if missingResponse.Code != http.StatusConflict || profiles.usedToken != "" {
		t.Fatalf("missing plan: status=%d token=%q", missingResponse.Code, profiles.usedToken)
	}
	post := withGrants(httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", strings.NewReader("launch_plan=plan-token")), "alice", grants)
	post.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	post.Header.Set("Origin", "https://adapter.example")
	postResponse := httptest.NewRecorder()
	server.ServeHTTP(postResponse, post)
	if postResponse.Code != http.StatusSeeOther || profiles.usedSubject != "alice" || profiles.usedProfile != "personal" || profiles.usedToken != "plan-token" {
		t.Fatalf("plan start: status=%d subject=%q profile=%q token=%q", postResponse.Code, profiles.usedSubject, profiles.usedProfile, profiles.usedToken)
	}
}

func TestBootstrapRedirectAndUnknownOwnershipError(t *testing.T) {
	profiles := &fakeProfiles{target: "https://start.example/", err: profile.ErrOwnershipUnknown}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, errors.New("offline") }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})

	bootstrap := httptest.NewRequest(http.MethodGet, "https://adapter.example/bootstrap/personal/operation-1", nil)
	bootstrapResponse := httptest.NewRecorder()
	server.ServeHTTP(bootstrapResponse, bootstrap)
	if bootstrapResponse.Code != http.StatusSeeOther || bootstrapResponse.Header().Get("Location") != "https://start.example/" {
		t.Fatalf("bootstrap status=%d location=%q", bootstrapResponse.Code, bootstrapResponse.Header().Get("Location"))
	}

	start := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
	startResponse := httptest.NewRecorder()
	server.ServeHTTP(startResponse, start)
	if startResponse.Code != http.StatusConflict || !strings.Contains(startResponse.Body.String(), "安全关闭") ||
		!strings.Contains(startResponse.Body.String(), "固定入口") || strings.Contains(startResponse.Body.String(), "operator recovery") {
		t.Fatalf("start status=%d body=%q", startResponse.Code, startResponse.Body.String())
	}
	profiles.err = profile.ErrResumeFailed
	resumeFailed := httptest.NewRecorder()
	server.ServeHTTP(resumeFailed, httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil))
	if resumeFailed.Code != http.StatusConflict || !strings.Contains(resumeFailed.Body.String(), "resumed") || resumeFailed.Header().Get("Location") != "" {
		t.Fatalf("resume failure status=%d body=%q", resumeFailed.Code, resumeFailed.Body.String())
	}
	profiles.err = profile.ErrCoherenceBlocked
	coherenceFailed := httptest.NewRecorder()
	server.ServeHTTP(coherenceFailed, httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil))
	if coherenceFailed.Code != http.StatusServiceUnavailable || !strings.Contains(coherenceFailed.Body.String(), "一致性检查") ||
		coherenceFailed.Header().Get("Retry-After") != "10" || coherenceFailed.Header().Get("Location") != "" {
		t.Fatalf("coherence failure status=%d body=%q", coherenceFailed.Code, coherenceFailed.Body.String())
	}

	ready := httptest.NewRequest(http.MethodGet, "https://adapter.example/readyz", nil)
	readyResponse := httptest.NewRecorder()
	server.ServeHTTP(readyResponse, ready)
	if readyResponse.Code != http.StatusServiceUnavailable {
		t.Fatalf("ready status=%d", readyResponse.Code)
	}
}

func newHealthServer(profiles *fakeProfiles, ui HealthUI) *Server {
	return New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), ui)
}

func blockingReport() profile.HealthReport {
	return profile.HealthReport{Version: 1, ProfileID: "personal", Overall: profile.OverallUnhealthy, CheckedAt: time.Unix(1_700_000_000, 0),
		Binding:  profile.HealthBinding{OperationID: "operation-secret", SessionID: "session-secret"},
		Checks:   []profile.HealthCheck{{Name: "browser", Status: profile.CheckFail, Required: true, Code: "BROWSER_EXITED", Message: "浏览器主进程已退出"}},
		Recovery: &profile.Recovery{Code: "BROWSER_EXITED", Title: "浏览器已退出", Blocking: true, Steps: []string{"右键 → FireFox"}}}
}

func TestEntryShowsBlockingRecoveryAndKeepsManualContinue(t *testing.T) {
	profiles := &fakeProfiles{session: sealskin.Session{SessionID: "s", SessionURL: "/s/?access_token=secret"}, health: blockingReport()}
	server := newHealthServer(profiles, HealthUI{EntryHint: true, EntryWait: time.Second})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil))
	body := response.Body.String()
	if response.Code != http.StatusOK || !strings.Contains(body, "浏览器已退出") || !strings.Contains(body, "右键 → FireFox") {
		t.Fatalf("recovery hint missing: %d %s", response.Code, body)
	}
	if strings.Contains(body, "document.forms[0].submit()") || !strings.Contains(body, `<form method="post" action="start">`) {
		t.Fatal("blocking recovery must not auto-submit but must keep the manual continue button")
	}
	if strings.Contains(body, "operation-secret") || strings.Contains(body, "session-secret") {
		t.Fatal("recovery page leaked binding identifiers")
	}
	if profiles.ensureCalls != 0 || profiles.healthCalls != 1 || profiles.healthOptions[0].Force || !profiles.healthOptions[0].CachedOnly {
		t.Fatalf("entry pre-check side effects: ensure=%d health=%d opts=%+v", profiles.ensureCalls, profiles.healthCalls, profiles.healthOptions)
	}
	recheck := httptest.NewRecorder()
	server.ServeHTTP(recheck, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/?recheck=1", nil))
	if profiles.healthOptions[1].Force || !profiles.healthOptions[1].CachedOnly {
		t.Fatal("a public query parameter must not trigger a probe")
	}
	post := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
	post.Header.Set("Origin", "https://adapter.example")
	postResponse := httptest.NewRecorder()
	server.ServeHTTP(postResponse, post)
	if postResponse.Code != http.StatusSeeOther || profiles.ensureCalls != 1 {
		t.Fatalf("manual continue must still reach the Session: %d", postResponse.Code)
	}
}

func TestEntryFallsBackToAutoSubmitWhenHealthIsSlowUnavailableOrHealthy(t *testing.T) {
	for name, profiles := range map[string]*fakeProfiles{
		"healthy":      {health: profile.HealthReport{Overall: profile.OverallHealthy}},
		"non-blocking": {health: profile.HealthReport{Overall: profile.OverallDegraded, Recovery: &profile.Recovery{Code: "PROXY_LEGACY_GENERATION"}}},
		"error":        {healthErr: errors.New("control unavailable")},
		"pending":      {healthErr: profile.ErrHealthPending},
		"slow":         {health: blockingReport(), healthDelay: 2 * time.Second},
	} {
		t.Run(name, func(t *testing.T) {
			server := newHealthServer(profiles, HealthUI{EntryHint: true, EntryWait: 50 * time.Millisecond})
			response := httptest.NewRecorder()
			server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil))
			if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "document.forms[0].submit()") {
				t.Fatalf("%s: entry did not fall back to auto-submit: %d %s", name, response.Code, response.Body.String())
			}
			if profiles.ensureCalls != 0 {
				t.Fatal("GET entry launched a session")
			}
		})
	}
	disabled := &fakeProfiles{health: blockingReport()}
	server := newHealthServer(disabled, HealthUI{})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil))
	if disabled.healthCalls != 0 || !strings.Contains(response.Body.String(), "document.forms[0].submit()") {
		t.Fatal("disabled entry hint must not consult health")
	}
}

func TestPublicHealthEndpointIsSanitizedAndReadOnly(t *testing.T) {
	profiles := &fakeProfiles{health: blockingReport()}
	server := newHealthServer(profiles, HealthUI{EntryHint: true, EntryWait: time.Second})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/health", nil))
	if response.Code != http.StatusOK || response.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("health status=%d headers=%v", response.Code, response.Header())
	}
	var decoded profile.HealthReport
	if err := json.Unmarshal(response.Body.Bytes(), &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Binding.OperationID != "" || decoded.Binding.SessionID != "" || decoded.Recovery == nil || decoded.Recovery.Code != "BROWSER_EXITED" {
		t.Fatalf("public report not sanitized: %+v", decoded)
	}
	if profiles.ensureCalls != 0 || profiles.healthOptions[0].Force || !profiles.healthOptions[0].CachedOnly {
		t.Fatalf("public health must read (not force) and never launch: %+v", profiles.healthOptions)
	}
	cached := httptest.NewRecorder()
	server.ServeHTTP(cached, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/health?cached=1", nil))
	if !profiles.healthOptions[1].CachedOnly {
		t.Fatal("cached=1 must not trigger collection")
	}
	for err, status := range map[error]int{profile.ErrProfileNotFound: http.StatusNotFound, profile.ErrHealthPending: http.StatusServiceUnavailable,
		profile.ErrHealthUnavailable: http.StatusNotFound, profile.ErrLifecycleDisabled: http.StatusNotImplemented, errors.New("control access_token=x"): http.StatusServiceUnavailable} {
		profiles.healthErr = err
		failed := httptest.NewRecorder()
		server.ServeHTTP(failed, httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/health", nil))
		if failed.Code != status || strings.Contains(failed.Body.String(), "access_token") {
			t.Fatalf("%v: status=%d body=%q", err, failed.Code, failed.Body.String())
		}
	}
}
