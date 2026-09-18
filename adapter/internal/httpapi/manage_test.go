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
	createRequest profile.CreateBrowserRequest
	createActor   string
	createKey     string
	deleteID      string
	deleteActor   string
	deleteKey     string
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
	profiles := &fakeProxyDrafts{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base}, drafts: map[string]profile.ProxyDraftSummary{}, probeStatus: "passed"}
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

func TestManagementCreatesDeletesAndListsFixedArtifacts(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}, stopResult: profile.LifecycleResult{Status: state.StatusStopped}}
	profiles := &fakeBrowserManager{fakeProfiles: base}
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
