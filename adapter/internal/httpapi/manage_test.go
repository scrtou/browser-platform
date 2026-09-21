package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
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
	return profile.EnvironmentSummary{ProfileID: id, Enabled: true, Revision: 3, Label: "个人 · 台北", StartURL: "https://start.example/", EntryPath: "/browser/" + id + "/", ApplicationID: "camoufox-" + id,
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
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop", "start"}}, {Profile: "retired", Capabilities: []string{"view"}}}
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
	if strings.Contains(response.Body.String(), "camoufox-work") || strings.Contains(response.Body.String(), `"profile_id":"work"`) || strings.Contains(response.Body.String(), "retired") {
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
	if !strings.Contains(body, `action="/manage/browsers/personal"`) || !strings.Contains(body, `name="revision" value="3"`) || !strings.Contains(body, `value="https://start.example/"`) || !strings.Contains(body, "安全关闭") {
		t.Fatalf("page lacks the management forms: %s", body)
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
	if empty.Code != http.StatusOK || !strings.Contains(empty.Body.String(), "没有配置远程浏览器") {
		t.Fatalf("empty grants page: %d %s", empty.Code, empty.Body.String())
	}
}

func manageForm(values url.Values, subject string, grants []access.Grant, target string) *http.Request {
	r := httptest.NewRequest(http.MethodPost, target, strings.NewReader(values.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	return withGrants(r, subject, grants)
}

type fakeBrowserManager struct {
	*fakeProfiles
	capabilities  profile.ManagementCapabilities
	createRequest profile.CreateBrowserRequest
	createActor   string
	createKey     string
	deleteID      string
	deleteActor   string
	deleteKey     string
}

func (f *fakeBrowserManager) ManagementCapabilities() profile.ManagementCapabilities {
	return f.capabilities
}

func (f *fakeBrowserManager) CreateBrowser(_ context.Context, request profile.CreateBrowserRequest, actor, key string) (profile.Record, error) {
	f.createRequest, f.createActor, f.createKey = request, actor, key
	return profile.Record{Definition: profile.Definition{ID: "browser-new", Label: request.Label, StartURL: request.StartURL}, Revision: 2, Status: profile.RecordReady}, nil
}

func (f *fakeBrowserManager) DeleteBrowser(_ context.Context, id, actor, key string) error {
	f.deleteID, f.deleteActor, f.deleteKey = id, actor, key
	return nil
}

func (f *fakeBrowserManager) EnvironmentArtifacts(context.Context) ([]profile.EnvironmentArtifactSummary, error) {
	return []profile.EnvironmentArtifactSummary{{ID: "env-r9", SHA256: strings.Repeat("a", 64), Source: "frozen"}}, nil
}

type fakeProxyDrafts struct {
	*fakeBrowserManager
	drafts       map[string]profile.ProxyDraftSummary
	lastDraft    profile.ProxyDraftRequest
	lastActor    string
	probeCalls   []string
	applyCalls   []string
	directCalls  []string
	applyErr     error
	probeStatus  string
	createErr    error
	appliedIDKey string
}

func (f *fakeProxyDrafts) CreateProxyDraft(_ context.Context, id, actor string, request profile.ProxyDraftRequest) (profile.ProxyDraftSummary, error) {
	f.lastDraft, f.lastActor = request, actor
	if f.createErr != nil {
		return profile.ProxyDraftSummary{}, f.createErr
	}
	summary := profile.ProxyDraftSummary{ID: "draft-1", ProfileID: id, Protocol: request.Protocol, Auth: request.Auth, Host: request.Host, Port: request.Port, ProbeStatus: "pending", SecretVersion: 1}
	f.drafts[id] = summary
	return summary, nil
}

func (f *fakeProxyDrafts) ProbeProxyDraft(_ context.Context, id, draftID string) (profile.ProxyDraftSummary, error) {
	f.probeCalls = append(f.probeCalls, id+"/"+draftID)
	summary, ok := f.drafts[id]
	if !ok || summary.ID != draftID {
		return profile.ProxyDraftSummary{}, profile.ErrProxyDraftNotFound
	}
	summary.ProbeStatus, summary.ProbeCode = f.probeStatus, "PROXY_PROBE_OK"
	f.drafts[id] = summary
	return summary, nil
}

func (f *fakeProxyDrafts) ApplyProxyDraft(_ context.Context, id string, revision int, draftID, actor, key string) (profile.Record, error) {
	f.applyCalls = append(f.applyCalls, id+"/"+draftID+"/"+key)
	f.appliedIDKey = key
	if f.applyErr != nil {
		return profile.Record{}, f.applyErr
	}
	return profile.Record{Definition: profile.Definition{ID: id, NetworkMode: "proxy_required"}, Revision: revision + 1}, nil
}

func (f *fakeProxyDrafts) SetBrowserDirect(_ context.Context, id string, revision int, policyID, sha, actor, key string) (profile.Record, error) {
	f.directCalls = append(f.directCalls, id+"/"+policyID+"/"+key)
	return profile.Record{Definition: profile.Definition{ID: id, NetworkMode: "direct"}, Revision: revision + 1}, nil
}

func (f *fakeProxyDrafts) ProxyDraft(id string) (profile.ProxyDraftSummary, bool) {
	summary, ok := f.drafts[id]
	return summary, ok
}

func TestManagementProxyDraftFormsNeverEchoCredentials(t *testing.T) {
	summary := sampleSummary("personal")
	summary.ConfiguredNetworkMode = "direct"
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": summary}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	profiles := &fakeProxyDrafts{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{CreateDelete: true, ProxyDrafts: true}}, drafts: map[string]profile.ProxyDraftSummary{}, probeStatus: "passed"}
	logs := &strings.Builder{}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(logs, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}
	target := "https://adapter.example/manage/browsers/personal"
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	if page.Code != http.StatusOK || !strings.Contains(page.Body.String(), `name="action" value="proxy_draft"`) || !strings.Contains(page.Body.String(), "受管理 DIRECT") || strings.Contains(page.Body.String(), "proxy_probe") {
		t.Fatalf("page before draft: %d %s", page.Code, page.Body.String())
	}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_draft"}, "protocol": {"socks5"}, "auth": {"username_password"}, "host": {"proxy.example.net"}, "port": {"1080"},
		"username": {"draft-user"}, "password": {"draft-secret-sentinel"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=draft_created" || profiles.lastDraft.Password != "draft-secret-sentinel" || profiles.lastDraft.Port != 1080 || profiles.lastActor != "root" {
		t.Fatalf("draft: %s request=%+v", response.Header().Get("Location"), profiles.lastDraft)
	}
	page = httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?notice=draft_created", nil), "root", grants))
	body := page.Body.String()
	if !strings.Contains(body, "草稿 socks5://proxy.example.net:1080") || !strings.Contains(body, `name="draft_id" value="draft-1"`) || strings.Contains(body, "draft-secret-sentinel") || strings.Contains(body, "proxy_apply") {
		t.Fatalf("page with pending draft: %s", body)
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_probe"}, "draft_id": {"draft-1"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=draft_probed" || len(profiles.probeCalls) != 1 {
		t.Fatalf("probe: %s", response.Header().Get("Location"))
	}
	page = httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	if !strings.Contains(page.Body.String(), `name="action" value="proxy_apply"`) {
		t.Fatalf("page after probe lacks apply form: %s", page.Body.String())
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_probe"}, "draft_id": {"other"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=draft_missing" {
		t.Fatalf("unknown draft probe: %s", response.Header().Get("Location"))
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_apply"}, "draft_id": {"draft-1"}, "revision": {"3"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=invalid" || len(profiles.applyCalls) != 0 {
		t.Fatalf("apply without idempotency key: %s", response.Header().Get("Location"))
	}
	profiles.applyErr = profile.ErrBrowserBusy
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_apply"}, "draft_id": {"draft-1"}, "revision": {"3"}, "idempotency_key": {"apply-1"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=network_busy" {
		t.Fatalf("busy apply: %s", response.Header().Get("Location"))
	}
	profiles.applyErr = nil
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_apply"}, "draft_id": {"draft-1"}, "revision": {"3"}, "idempotency_key": {"apply-1"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=network_applied" || strings.Join(profiles.applyCalls, ",") != "personal/draft-1/apply-1,personal/draft-1/apply-1" {
		t.Fatalf("apply: %s calls=%v", response.Header().Get("Location"), profiles.applyCalls)
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"network_direct"}, "network_policy_id": {"direct-r1"}, "network_policy_sha256": {strings.Repeat("c", 64)}, "revision": {"4"}, "idempotency_key": {"direct-1"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=network_applied" || strings.Join(profiles.directCalls, ",") != "personal/direct-r1/direct-1" {
		t.Fatalf("direct: %s calls=%v", response.Header().Get("Location"), profiles.directCalls)
	}
	profiles.createErr = profile.ErrProxyDraftInvalid
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"proxy_draft"}, "protocol": {"socks5"}, "auth": {"none"}, "host": {"10.0.0.1"}, "port": {"1080"}}, "root", grants, target))
	if response.Header().Get("Location") != "/manage/?notice=invalid" {
		t.Fatalf("invalid draft: %s", response.Header().Get("Location"))
	}
	viewOnly := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "stop"}}}
	for _, action := range []string{"proxy_draft", "proxy_probe", "proxy_apply", "network_direct"} {
		response = httptest.NewRecorder()
		server.ServeHTTP(response, manageForm(url.Values{"action": {action}, "password": {"draft-secret-sentinel"}}, "root", viewOnly, target))
		if response.Code != http.StatusForbidden {
			t.Fatalf("%s without manage capability: %d", action, response.Code)
		}
	}
	if strings.Contains(logs.String(), "draft-secret-sentinel") || strings.Contains(logs.String(), "draft-user") {
		t.Fatalf("credentials reached the log: %s", logs.String())
	}
}

type fakeEnvironmentJobs struct {
	*fakeBrowserManager
	jobs      []profile.EnvironmentJobSummary
	requests  []profile.EnvironmentJobRequest
	actors    []string
	createErr error
}

func (f *fakeEnvironmentJobs) CreateEnvironmentJob(_ context.Context, actor string, request profile.EnvironmentJobRequest) (profile.EnvironmentJobSummary, error) {
	f.requests, f.actors = append(f.requests, request), append(f.actors, actor)
	if f.createErr != nil {
		return profile.EnvironmentJobSummary{}, f.createErr
	}
	summary := profile.EnvironmentJobSummary{ID: "job-0123456789abcdef", EnvironmentID: "env-custom-0123456789abcdef", Actor: actor, Locale: request.Locale, Timezone: request.Timezone, Status: "queued"}
	f.jobs = append(f.jobs, summary)
	return summary, nil
}

func (f *fakeEnvironmentJobs) EnvironmentJobs() ([]profile.EnvironmentJobSummary, error) {
	return append([]profile.EnvironmentJobSummary(nil), f.jobs...), nil
}

func (f *fakeEnvironmentJobs) EnvironmentArtifacts(context.Context) ([]profile.EnvironmentArtifactSummary, error) {
	return []profile.EnvironmentArtifactSummary{{ID: "env-r9", SHA256: strings.Repeat("a", 64), Source: "frozen", Locale: "zh-TW", Timezone: "Asia/Taipei", Screen: "1920x1080@1"},
		{ID: "env-custom-0123456789abcdef", SHA256: strings.Repeat("b", 64), Source: "custom", Locale: "en-US", Timezone: "America/New_York", Screen: "1920x1080@1", AcceptedAt: "2026-09-19T01:32:44Z"}}, nil
}

func TestManagementEnvironmentJobsFormListAndCatalogSelect(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	profiles := &fakeEnvironmentJobs{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{CreateDelete: true, EnvironmentJobs: true}}, jobs: []profile.EnvironmentJobSummary{{ID: "job-ffffffffffffffff", EnvironmentID: "env-custom-ffffffffffffffff", Actor: "root",
		Locale: "de-DE", Timezone: "Europe/Berlin", Screen: "1600x900@1", Window: "1600x900", Status: "failed", Phase: "failed", Code: "ENVIRONMENT_ACCEPTANCE_FAILED", Message: "exit 1", ArtifactSHA256: strings.Repeat("c", 64), Attempts: 2}}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	body := page.Body.String()
	for _, want := range []string{`<select name="environment_artifact_id"`, `env-custom-0123456789abcdef · en-US · America/New_York · 1920x1080@1 · custom`, "指纹作业"} {
		if !strings.Contains(body, want) {
			t.Fatalf("page lacks %q: %s", want, body)
		}
	}
	if strings.Contains(body, `name="environment_artifact_id" maxlength`) {
		t.Fatal("free-text artifact input rendered although the catalog is available")
	}
	jobsPage := httptest.NewRecorder()
	server.ServeHTTP(jobsPage, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs", nil), "root", grants))
	jobsBody := jobsPage.Body.String()
	for _, want := range []string{"job-ffffffffffffffff", "ENVIRONMENT_ACCEPTANCE_FAILED · exit 1", "产物 cccccccccccc…", "生成尝试 2"} {
		if !strings.Contains(jobsBody, want) {
			t.Fatalf("jobs tab lacks %q: %s", want, jobsBody)
		}
	}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"locale": {"en-US"}, "languages": {" en-US, en "}, "timezone": {"America/New_York"}, "screen_width": {"1920"}, "screen_height": {"1080"}, "dpr": {"1"}, "window_width": {"1600"}, "window_height": {"900"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
	if response.Code != http.StatusSeeOther || response.Header().Get("Location") != "/manage/?tab=jobs&notice=job_created" || len(profiles.requests) != 1 || profiles.actors[0] != "root" {
		t.Fatalf("create: %d %s requests=%+v", response.Code, response.Header().Get("Location"), profiles.requests)
	}
	got := profiles.requests[0]
	if got.Locale != "en-US" || strings.Join(got.Languages, ",") != "en-US,en" || got.Timezone != "America/New_York" || got.ScreenWidth != 1920 || got.ScreenHeight != 1080 || got.DPR != 1 || got.WindowWidth != 1600 || got.WindowHeight != 900 {
		t.Fatalf("parsed request: %+v", got)
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"locale": {"en-US"}, "languages": {"en-US"}, "timezone": {"UTC"}, "screen_width": {"1920"}, "screen_height": {"1080"}, "dpr": {"1"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
	if profiles.requests[1].WindowWidth != 0 || profiles.requests[1].WindowHeight != 0 {
		t.Fatalf("omitted window must stay zero for the service default: %+v", profiles.requests[1])
	}
	profiles.createErr = profile.ErrEnvironmentJobInvalid
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"locale": {"x"}, "languages": {"x"}, "timezone": {"UTC"}, "screen_width": {"abc"}, "screen_height": {"1080"}, "dpr": {"1"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
	if response.Header().Get("Location") != "/manage/?tab=jobs&notice=job_invalid" || profiles.requests[2].ScreenWidth != -1 {
		t.Fatalf("invalid: %s %+v", response.Header().Get("Location"), profiles.requests[2])
	}
	profiles.createErr = profile.ErrEnvironmentJobsBusy
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"locale": {"en-US"}, "languages": {"en-US"}, "timezone": {"UTC"}, "screen_width": {"1920"}, "screen_height": {"1080"}, "dpr": {"1"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
	if response.Header().Get("Location") != "/manage/?tab=jobs&notice=job_busy" {
		t.Fatalf("busy: %s", response.Header().Get("Location"))
	}
	list := httptest.NewRecorder()
	server.ServeHTTP(list, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environment-jobs", nil), "root", grants))
	if list.Code != http.StatusOK || !strings.Contains(list.Body.String(), `"id":"job-0123456789abcdef"`) || !strings.Contains(list.Body.String(), `"code":"ENVIRONMENT_ACCEPTANCE_FAILED"`) || strings.Contains(list.Body.String(), "resolvedConfig") {
		t.Fatalf("list: %d %s", list.Code, list.Body.String())
	}
	anonymous := httptest.NewRecorder()
	server.ServeHTTP(anonymous, httptest.NewRequest(http.MethodPost, "https://adapter.example/manage/environment-jobs", strings.NewReader("locale=en-US")))
	if anonymous.Code != http.StatusNotFound || len(profiles.requests) != 4 {
		t.Fatalf("POST without gateway grants: %d", anonymous.Code)
	}
	plain := New(base, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	response = httptest.NewRecorder()
	plain.ServeHTTP(response, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environment-jobs", nil), "root", grants))
	if response.Code != http.StatusNotFound {
		t.Fatalf("jobs without service: %d", response.Code)
	}
	page = httptest.NewRecorder()
	plain.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	if strings.Contains(page.Body.String(), "自定义指纹作业") || strings.Contains(page.Body.String(), `name="environment_artifact_id"`) {
		t.Fatal("page without optional capabilities rendered a job or browser creation field")
	}
}

func TestManagementCreatesDeletesAndListsFixedArtifacts(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	profiles := &fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{CreateDelete: true}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}
	created := httptest.NewRecorder()
	server.ServeHTTP(created, manageForm(url.Values{
		"label": {"新浏览器"}, "start_url": {"https://start.example/"}, "environment_artifact_id": {"env-r9"},
		"network_mode": {"direct"}, "network_policy_id": {"direct-r1"}, "network_policy_sha256": {strings.Repeat("c", 64)},
		"idempotency_key": {"create-1"},
	}, "root", grants, "https://adapter.example/manage/browsers"))
	if created.Code != http.StatusSeeOther || created.Header().Get("Location") != "/manage/?notice=created" || profiles.createActor != "root" || profiles.createKey != "create-1" || profiles.createRequest.EnvironmentArtifactID != "env-r9" || profiles.createRequest.NetworkMode != "direct" {
		t.Fatalf("create: status=%d location=%q actor=%q key=%q request=%+v", created.Code, created.Header().Get("Location"), profiles.createActor, profiles.createKey, profiles.createRequest)
	}
	deleted := httptest.NewRecorder()
	server.ServeHTTP(deleted, manageForm(url.Values{"action": {"delete"}, "idempotency_key": {"delete-1"}}, "root", grants, "https://adapter.example/manage/browsers/personal"))
	if deleted.Code != http.StatusSeeOther || deleted.Header().Get("Location") != "/manage/?notice=deleted" || profiles.deleteID != "personal" || profiles.deleteActor != "root" || profiles.deleteKey != "delete-1" {
		t.Fatalf("delete: status=%d location=%q id=%q actor=%q key=%q", deleted.Code, deleted.Header().Get("Location"), profiles.deleteID, profiles.deleteActor, profiles.deleteKey)
	}
	catalog := httptest.NewRecorder()
	server.ServeHTTP(catalog, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environments/catalog", nil), "root", grants))
	if catalog.Code != http.StatusOK || !strings.Contains(catalog.Body.String(), `"id":"env-r9"`) || strings.Contains(catalog.Body.String(), "image") {
		t.Fatalf("catalog: %d %s", catalog.Code, catalog.Body.String())
	}
}

func TestManagementUnavailableOptionalCapabilitiesAreNotAdvertisedOrCallable(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	profiles := &fakeProxyDrafts{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base}, drafts: map[string]profile.ProxyDraftSummary{}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}

	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	body := page.Body.String()
	for _, forbidden := range []string{"新增浏览器</button>", "归档并删除</button>", `name="action" value="proxy_draft"`, "自定义指纹作业"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("disabled capability %q was advertised: %s", forbidden, body)
		}
	}
	for _, required := range []string{"新增与归档删除尚未启用", `name="action" value="update"`, `name="action" value="disable"`, "安全关闭"} {
		if !strings.Contains(body, required) {
			t.Fatalf("base management action %q is missing: %s", required, body)
		}
	}

	requests := []*http.Request{
		manageForm(url.Values{"idempotency_key": {"create-1"}}, "root", grants, "https://adapter.example/manage/browsers"),
		manageForm(url.Values{"action": {"delete"}, "idempotency_key": {"delete-1"}}, "root", grants, "https://adapter.example/manage/browsers/personal"),
		manageForm(url.Values{"action": {"proxy_draft"}}, "root", grants, "https://adapter.example/manage/browsers/personal"),
		manageForm(url.Values{"locale": {"en-US"}}, "root", grants, "https://adapter.example/manage/environment-jobs"),
		withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/environments/catalog", nil), "root", grants),
	}
	for _, request := range requests {
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusNotFound {
			t.Fatalf("disabled optional endpoint %s returned %d", request.URL.Path, response.Code)
		}
	}
}

func TestManagementBrowserFormsUpdateStopAndRespectCapabilities(t *testing.T) {
	profiles := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}, stopResult: profile.LifecycleResult{Status: "stopped"}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	full := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop", "start"}}}
	target := "https://adapter.example/manage/browsers/personal"
	// Update label and start URL under the current revision.
	response := httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"update"}, "revision": {"3"}, "label": {" 新名称 "}, "start_url": {"https://next.example/"}}, "root", full, target))
	if response.Code != http.StatusSeeOther || response.Header().Get("Location") != "/manage/?notice=updated" || len(profiles.updates) != 1 || *profiles.updates[0].Label != "新名称" || *profiles.updates[0].StartURL != "https://next.example/" {
		t.Fatalf("update: %d %s updates=%+v", response.Code, response.Header().Get("Location"), profiles.updates)
	}
	// A stale revision is refused without applying anything.
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"disable"}, "revision": {"3"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=revision" || len(profiles.updates) != 1 {
		t.Fatalf("stale revision: %s", response.Header().Get("Location"))
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"disable"}, "revision": {"4"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=disabled" || profiles.environments["personal"].Enabled {
		t.Fatalf("disable: %s", response.Header().Get("Location"))
	}
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?notice=disabled", nil), "root", full))
	if !strings.Contains(page.Body.String(), "已停用") || !strings.Contains(page.Body.String(), "浏览器已停用；新的启动") || !strings.Contains(page.Body.String(), `name="action" value="enable"`) {
		t.Fatalf("disabled page: %s", page.Body.String())
	}
	unknown := httptest.NewRecorder()
	server.ServeHTTP(unknown, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?notice=<script>alert(1)</script>", nil), "root", full))
	if strings.Contains(unknown.Body.String(), "alert(1)") || strings.Contains(unknown.Body.String(), `class="notice"`) {
		t.Fatal("unknown notice value was echoed")
	}
	// Stop reuses the verified lifecycle and reports its result.
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"stop"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=stopped" || strings.Join(profiles.stopCalls, ",") != "personal" {
		t.Fatalf("stop: %s calls=%v", response.Header().Get("Location"), profiles.stopCalls)
	}
	profiles.stopErr = profile.ErrStopUnconfirmed
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"stop"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=stop_pending" {
		t.Fatalf("pending stop: %s", response.Header().Get("Location"))
	}
	profiles.stopErr = profile.ErrOwnershipUnknown
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"stop"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=stop_conflict" || strings.Contains(response.Body.String(), "ownership") {
		t.Fatalf("conflicting stop: %s", response.Header().Get("Location"))
	}
	// Capabilities and unknown Profiles are enforced per grant.
	viewOnly := []access.Grant{{Profile: "personal", Capabilities: []string{"view"}}}
	for _, action := range []string{"stop", "update", "enable"} {
		response = httptest.NewRecorder()
		server.ServeHTTP(response, manageForm(url.Values{"action": {action}, "revision": {"5"}}, "root", viewOnly, target))
		if response.Code != http.StatusForbidden {
			t.Fatalf("%s without capability: %d", action, response.Code)
		}
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"stop"}}, "root", full, "https://adapter.example/manage/browsers/other"))
	if response.Code != http.StatusNotFound || len(profiles.stopCalls) != 3 {
		t.Fatalf("ungranted Profile: %d", response.Code)
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, manageForm(url.Values{"action": {"explode"}}, "root", full, target))
	if response.Header().Get("Location") != "/manage/?notice=invalid" {
		t.Fatalf("unknown action: %s", response.Header().Get("Location"))
	}
	response = httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodPost, target, strings.NewReader("action=stop")))
	if response.Code != http.StatusNotFound || len(profiles.stopCalls) != 3 {
		t.Fatalf("POST without gateway grants: %d", response.Code)
	}
}

type fakeFullManagementService struct {
	*fakeProxyDrafts
	jobs    []profile.EnvironmentJobSummary
	jobsErr error
}

func (f *fakeFullManagementService) CreateEnvironmentJob(_ context.Context, _ string, _ profile.EnvironmentJobRequest) (profile.EnvironmentJobSummary, error) {
	return profile.EnvironmentJobSummary{}, nil
}

func (f *fakeFullManagementService) EnvironmentJobs() ([]profile.EnvironmentJobSummary, error) {
	return f.jobs, f.jobsErr
}

func TestManagementRedesignedUIStructureAndContracts(t *testing.T) {
	summary := sampleSummary("personal")
	summary.ConfiguredNetworkMode = "direct"
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": summary}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	drafts := &fakeProxyDrafts{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{CreateDelete: true, ProxyDrafts: true, EnvironmentJobs: true}}, drafts: map[string]profile.ProxyDraftSummary{}}
	profiles := &fakeFullManagementService{fakeProxyDrafts: drafts}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}

	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?notice=updated", nil), "root", grants))
	if page.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", page.Code)
	}
	body := page.Body.String()

	// 1. Semantic landmarks: header, main, section, footer
	for _, tag := range []string{"<header", "<main", "<section", "<footer"} {
		if !strings.Contains(body, tag) {
			t.Fatalf("page missing semantic tag %q", tag)
		}
	}

	// 2. Responsive viewport
	if !strings.Contains(body, `<meta name="viewport" content="width=device-width,initial-scale=1">`) {
		t.Fatal("page missing responsive viewport meta tag")
	}

	// 3. Feedback region with role=status
	if !strings.Contains(body, `role="status"`) || !strings.Contains(body, "已保存。") {
		t.Fatal("notice feedback region with role=status is missing")
	}

	// 4. Browser cards instead of 9-column desktop table
	if !strings.Contains(body, "browser-card") {
		t.Fatal("browser card structure missing")
	}

	// 5. Explicit visible labels
	if !strings.Contains(body, `<label for="label-personal">`) || !strings.Contains(body, `<label for="url-personal">`) {
		t.Fatal("explicit form labels missing")
	}

	// 6. Dangerous operations zone with visible idempotency key label
	if !strings.Contains(body, "danger-zone") || !strings.Contains(body, "危险操作") || !strings.Contains(body, `<label for="del-key-personal">`) {
		t.Fatal("danger zone or visible idempotency label missing")
	}

	// 7. Details for advanced network configuration
	if !strings.Contains(body, "<details") || !strings.Contains(body, "配置代理 / 切回 DIRECT") {
		t.Fatal("advanced network details element missing")
	}

	// 8. Key routes and fields preserved across tabs
	for _, fragment := range []string{
		`action="/manage/browsers"`,
		`action="/manage/browsers/personal"`,
		`action="/auth/logout"`,
		`name="csrf"`,
		`name="idempotency_key"`,
		`name="revision"`,
	} {
		if !strings.Contains(body, fragment) {
			t.Fatalf("page missing required form contract fragment %q", fragment)
		}
	}

	jobsPage := httptest.NewRecorder()
	server.ServeHTTP(jobsPage, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs", nil), "root", grants))
	if !strings.Contains(jobsPage.Body.String(), `action="/manage/environment-jobs"`) {
		t.Fatal("jobs tab missing environment-jobs action")
	}

	accountsPage := httptest.NewRecorder()
	server.ServeHTTP(accountsPage, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=accounts", nil), "root", grants))
	if !strings.Contains(accountsPage.Body.String(), `action="/manage/accounts"`) {
		t.Fatal("accounts tab missing accounts action")
	}
}

func TestManagementTabsNavigationFallbackReauthAndRedirects(t *testing.T) {
	summary := sampleSummary("personal")
	summary.ConfiguredNetworkMode = "direct"
	base := &fakeProfiles{
		environments: map[string]profile.EnvironmentSummary{"personal": summary},
		stopResult:   profile.LifecycleResult{Status: state.StatusStopped},
	}
	drafts := &fakeProxyDrafts{
		fakeBrowserManager: &fakeBrowserManager{
			fakeProfiles: base,
			capabilities: profile.ManagementCapabilities{CreateDelete: true, ProxyDrafts: true, EnvironmentJobs: true},
		},
		drafts: map[string]profile.ProxyDraftSummary{},
	}
	profiles := &fakeFullManagementService{
		fakeProxyDrafts: drafts,
		jobs: []profile.EnvironmentJobSummary{
			{ID: "job-test-1", Status: "running", Locale: "en-US", Timezone: "UTC"},
		},
	}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}

	// 1. Default tab (GET /manage/) -> browsers tab
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if !strings.Contains(body, `<nav class="nav-tabs" aria-label="管理功能">`) {
			t.Fatal("missing nav-tabs landmark")
		}
		if !strings.Contains(body, `href="/manage/?tab=browsers" class="tab-item active" aria-current="page"`) {
			t.Fatal("browsers tab missing active aria-current on default")
		}
		if strings.Contains(body, `href="/manage/?tab=jobs" class="tab-item active"`) || strings.Contains(body, `href="/manage/?tab=accounts" class="tab-item active"`) {
			t.Fatal("non-active tab marked active")
		}
		// Accessible navigation: NO fake ARIA tabs widget roles
		for _, fakeARIA := range []string{`role="tablist"`, `role="tab"`, `role="tabpanel"`} {
			if strings.Contains(body, fakeARIA) {
				t.Fatalf("found fake ARIA role %q", fakeARIA)
			}
		}
		// Render only active pane: browsers present, jobs/accounts absent
		if !strings.Contains(body, `<section class="section-browsers"`) {
			t.Fatal("missing browsers section")
		}
		if strings.Contains(body, `<section class="section-jobs"`) || strings.Contains(body, `<section class="section-accounts"`) {
			t.Fatal("inactive sections rendered on browsers tab")
		}
		// Confirm password link with encoded next to active fixed tab
		if !strings.Contains(body, `href="/auth/reauth?next=%2Fmanage%2F%3Ftab%3Dbrowsers"`) {
			t.Fatal("browsers tab missing top bar confirm-password link returning to browsers")
		}
	}

	// 2. Explicit tab: jobs tab
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs", nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if !strings.Contains(body, `href="/manage/?tab=jobs" class="tab-item active" aria-current="page"`) {
			t.Fatal("jobs tab missing active aria-current")
		}
		if !strings.Contains(body, `<section class="section-jobs"`) {
			t.Fatal("missing jobs section on jobs tab")
		}
		if strings.Contains(body, `<section class="section-browsers"`) || strings.Contains(body, `<section class="section-accounts"`) {
			t.Fatal("inactive sections rendered on jobs tab")
		}
		if !strings.Contains(body, `href="/auth/reauth?next=%2Fmanage%2F%3Ftab%3Djobs"`) {
			t.Fatal("jobs tab missing top bar confirm-password link returning to jobs")
		}
	}

	// 3. Explicit tab: accounts tab
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=accounts", nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if !strings.Contains(body, `href="/manage/?tab=accounts" class="tab-item active" aria-current="page"`) {
			t.Fatal("accounts tab missing active aria-current")
		}
		if !strings.Contains(body, `<section class="section-accounts"`) {
			t.Fatal("missing accounts section on accounts tab")
		}
		if strings.Contains(body, `<section class="section-browsers"`) || strings.Contains(body, `<section class="section-jobs"`) {
			t.Fatal("inactive sections rendered on accounts tab")
		}
		if !strings.Contains(body, `href="/auth/reauth?next=%2Fmanage%2F%3Ftab%3Daccounts"`) {
			t.Fatal("accounts tab missing confirm-password link returning to accounts")
		}
	}

	// 4. Invalid tab fallback to browsers
	for _, invalidTab := range []string{"unknown", "hack", "admin", "123", "../", "%3Cscript%3Ealert(1)%3C%2Fscript%3E"} {
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab="+invalidTab, nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if !strings.Contains(body, `href="/manage/?tab=browsers" class="tab-item active" aria-current="page"`) {
			t.Fatalf("invalid tab %q did not fall back to browsers tab", invalidTab)
		}
		if !strings.Contains(body, `<section class="section-browsers"`) || strings.Contains(body, `<section class="section-jobs"`) || strings.Contains(body, `<section class="section-accounts"`) {
			t.Fatalf("invalid tab %q rendered wrong panes", invalidTab)
		}
	}

	// 5. Unavailable jobs capability fallback to browsers
	{
		disabledBase := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": summary}}
		disabledDrafts := &fakeProxyDrafts{
			fakeBrowserManager: &fakeBrowserManager{
				fakeProfiles: disabledBase,
				capabilities: profile.ManagementCapabilities{CreateDelete: true, ProxyDrafts: true, EnvironmentJobs: false},
			},
			drafts: map[string]profile.ProxyDraftSummary{},
		}
		disabledServer := New(&fakeFullManagementService{fakeProxyDrafts: disabledDrafts}, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
		rec := httptest.NewRecorder()
		disabledServer.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs", nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if strings.Contains(body, `href="/manage/?tab=jobs"`) {
			t.Fatal("unavailable jobs tab link rendered in nav")
		}
		if !strings.Contains(body, `href="/manage/?tab=browsers" class="tab-item active" aria-current="page"`) {
			t.Fatal("requesting unavailable jobs did not fall back to browsers tab")
		}
		if !strings.Contains(body, `<section class="section-browsers"`) || strings.Contains(body, `<section class="section-jobs"`) {
			t.Fatal("unavailable jobs tab rendered wrong pane")
		}
	}

	// 6. POST redirect routing by request path
	// A listing failure also makes jobs unavailable without exposing internal errors.
	{
		profiles.jobsErr = errors.New("private-job-spool-detail")
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs", nil), "root", grants))
		body := rec.Body.String()
		if rec.Code != http.StatusOK || !strings.Contains(body, `<section class="section-browsers"`) || strings.Contains(body, `href="/manage/?tab=jobs"`) || strings.Contains(body, "private-job-spool-detail") {
			t.Fatal("failed jobs listing did not safely fall back to browsers")
		}
		profiles.jobsErr = nil
	}

	// 6a. Browser action keeps exact old /manage/?notice=...
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, manageForm(url.Values{"action": {"stop"}}, "root", grants, "https://adapter.example/manage/browsers/personal"))
		if rec.Code != http.StatusSeeOther || rec.Header().Get("Location") != "/manage/?notice=stopped" {
			t.Fatalf("browser action redirect: %d %s", rec.Code, rec.Header().Get("Location"))
		}
	}
	// 6b. Job action redirects to /manage/?tab=jobs&notice=...
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, manageForm(url.Values{"locale": {"en-US"}, "languages": {"en-US"}, "timezone": {"UTC"}, "screen_width": {"1920"}, "screen_height": {"1080"}, "dpr": {"1"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
		if rec.Code != http.StatusSeeOther || rec.Header().Get("Location") != "/manage/?tab=jobs&notice=job_created" {
			t.Fatalf("job action redirect: %d %s", rec.Code, rec.Header().Get("Location"))
		}
	}
	// 6c. Notice preservation on landing: tab=jobs with notice renders notice and jobs pane
	{
		rec := httptest.NewRecorder()
		server.ServeHTTP(rec, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?tab=jobs&notice=job_created", nil), "root", grants))
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		body := rec.Body.String()
		if !strings.Contains(body, `role="status"`) || !strings.Contains(body, "自定义指纹作业已排队") {
			t.Fatal("notice missing on jobs tab landing")
		}
		if !strings.Contains(body, `<section class="section-jobs"`) || strings.Contains(body, `<section class="section-browsers"`) {
			t.Fatal("wrong pane on jobs tab with notice")
		}
	}
}
