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
	"browser-platform/adapter/internal/state"
)

// withGrants attaches management grants the way the gateway does in production.
func withGrants(r *http.Request, subject string, grants []access.Grant) *http.Request {
	return r.WithContext(access.ContextWithGrants(r.Context(), subject, grants))
}

func sampleSummary(id string) profile.EnvironmentSummary {
	checked := time.Date(2026, 9, 17, 16, 0, 0, 0, time.UTC)
	return profile.EnvironmentSummary{ProfileID: id, Label: "个人 · 台北", EntryPath: "/browser/" + id + "/", ApplicationID: "camoufox-" + id,
		HomeName: id + "-home", Language: "zh_TW.UTF-8", Timezone: "Asia/Taipei", DisplayMode: "x11", NetworkMode: "managed",
		NetworkPolicyID: id + "-socks5-r1", Status: state.StatusRunning, Observed: true,
		Health: &profile.EnvironmentHealth{Overall: profile.OverallDegraded, CheckedAt: checked, ExpiresAt: checked.Add(time.Minute),
			Code: "PROXY_LEGACY_GENERATION", Title: "旧代次", Environment: &sealskin.EnvironmentIdentity{ID: "env-tw-r9", ArtifactSHA256: strings.Repeat("b", 64)}}}
}

func TestManagementPagesRequireTheAccessGateway(t *testing.T) {
	profiles := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	for _, path := range []string{"/manage/", "/manage/environments", "/manage/other"} {
		response := httptest.NewRecorder()
		server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "https://adapter.example"+path, nil))
		if response.Code != http.StatusNotFound || strings.Contains(response.Body.String(), "personal") {
			t.Fatalf("%s without a gateway: %d %s", path, response.Code, response.Body.String())
		}
	}
	// The mux's canonical trailing-slash redirect names no Profile; the
	// redirected page then answers 404 like above.
	redirect := httptest.NewRecorder()
	server.ServeHTTP(redirect, httptest.NewRequest(http.MethodGet, "https://adapter.example/manage", nil))
	if redirect.Code != http.StatusTemporaryRedirect || redirect.Header().Get("Location") != "/manage/" || strings.Contains(redirect.Body.String(), "personal") {
		t.Fatalf("/manage without a gateway: %d %s", redirect.Code, redirect.Body.String())
	}
	if len(profiles.environmentCalls) != 0 {
		t.Fatal("a request without grants read a summary")
	}
}

func TestManagementListOnlyContainsGrantedProfilesAndNoCapabilities(t *testing.T) {
	profiles := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal"), "work": sampleSummary("work")}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "start"}}, {Profile: "retired", Capabilities: []string{"view"}}}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environments", nil), "alice", grants))
	if response.Code != http.StatusOK || response.Header().Get("Cache-Control") != "no-store" || response.Header().Get("Content-Type") != "application/json" {
		t.Fatalf("list: %d %v", response.Code, response.Header())
	}
	var decoded environmentList
	if err := json.Unmarshal(response.Body.Bytes(), &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Subject != "alice" || len(decoded.Environments) != 1 || decoded.Environments[0].ProfileID != "personal" || !decoded.Environments[0].Available {
		t.Fatalf("list content: %s", response.Body.String())
	}
	if strings.Contains(response.Body.String(), "camoufox-work") || strings.Contains(response.Body.String(), `"work`) || strings.Contains(response.Body.String(), "retired") {
		t.Fatalf("list named an ungranted or unknown Profile: %s", response.Body.String())
	}
	if strings.Contains(response.Body.String(), strings.Repeat("b", 64)) == false || strings.Contains(response.Body.String(), "socks5-r1") == false {
		t.Fatalf("environment identity and policy ID are part of the allowed summary: %s", response.Body.String())
	}
	if profiles.ensureCalls != 0 || profiles.healthCalls != 0 || strings.Join(profiles.environmentCalls, ",") != "personal,retired" {
		t.Fatalf("list side effects: ensure=%d health=%d environment=%v", profiles.ensureCalls, profiles.healthCalls, profiles.environmentCalls)
	}
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "alice", grants))
	body := page.Body.String()
	if page.Code != http.StatusOK || !strings.Contains(body, "个人 · 台北") || !strings.Contains(body, `href="/browser/personal/"`) || !strings.Contains(body, "env-tw-r9") || !strings.Contains(body, "PROXY_LEGACY_GENERATION") {
		t.Fatalf("page: %d %s", page.Code, body)
	}
	if strings.Contains(body, "<script") || !strings.Contains(page.Header().Get("Content-Security-Policy"), "default-src 'none'") || page.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("page must be script-free and uncacheable: %v", page.Header())
	}
	if strings.Contains(body, "camoufox-work") || strings.Contains(body, "/browser/work/") || strings.Contains(body, "retired") || strings.Contains(body, strings.Repeat("b", 64)) {
		t.Fatalf("page exposed ungranted Profiles or a full digest: %s", body)
	}
	if !strings.Contains(body, `action="/auth/logout"`) || !strings.Contains(body, `name="csrf"`) {
		t.Fatal("page lost the logout form")
	}
}

func TestManagementListKeepsUnavailableRowsWithoutErrorText(t *testing.T) {
	profiles := &fakeProfiles{environmentErr: errors.New("journal access_token=secret failed")}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "start"}}}
	for _, path := range []string{"/manage/environments", "/manage/"} {
		response := httptest.NewRecorder()
		server.ServeHTTP(response, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example"+path, nil), "alice", grants))
		body := response.Body.String()
		if response.Code != http.StatusOK || !strings.Contains(body, "personal") || strings.Contains(body, "access_token") || strings.Contains(body, "journal") {
			t.Fatalf("%s: %d %s", path, response.Code, body)
		}
	}
	var decoded environmentList
	response := httptest.NewRecorder()
	server.ServeHTTP(response, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environments", nil), "alice", grants))
	if err := json.Unmarshal(response.Body.Bytes(), &decoded); err != nil || len(decoded.Environments) != 1 || decoded.Environments[0].Available || decoded.Environments[0].Summary != nil {
		t.Fatalf("unavailable row: %s err=%v", response.Body.String(), err)
	}
	empty := httptest.NewRecorder()
	server.ServeHTTP(empty, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "bob", nil))
	if empty.Code != http.StatusOK || !strings.Contains(empty.Body.String(), "没有获授权的环境") {
		t.Fatalf("empty grants page: %d %s", empty.Code, empty.Body.String())
	}
}
