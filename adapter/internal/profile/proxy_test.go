package profile

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
)

func testProxyTemplate() ProxyTemplate {
	return ProxyTemplate{Owner: "profile-adapter", RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/", ProbeTimeoutSeconds: 8}
}

func draftRequest() ProxyDraftRequest {
	return ProxyDraftRequest{Protocol: "socks5", Auth: "username_password", Host: "proxy.example.net", Port: 1080, Username: "draft-user", Password: "draft-pässword"}
}

func createdBrowser(t *testing.T, admin *managementAdmin) (*Service, *lifecycleFake, Record) {
	t.Helper()
	service, fake := managementService(t, admin)
	record, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-proxy")
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = record.HomeName
	return service, fake, record
}

func TestProxyTemplateValidation(t *testing.T) {
	if err := testProxyTemplate().Validate(); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*ProxyTemplate){
		"owner":   func(v *ProxyTemplate) { v.Owner = "bad owner" },
		"relay":   func(v *ProxyTemplate) { v.RelayImage = "relay:latest" },
		"probe":   func(v *ProxyTemplate) { v.ProbeImage = "sha256:short" },
		"url":     func(v *ProxyTemplate) { v.ProbeURL = "http://probe.example/" },
		"creds":   func(v *ProxyTemplate) { v.ProbeURL = "https://user:pw@probe.example/" },
		"timeout": func(v *ProxyTemplate) { v.ProbeTimeoutSeconds = 21 },
	} {
		template := testProxyTemplate()
		mutate(&template)
		if err := template.Validate(); err == nil {
			t.Fatalf("%s: invalid template accepted", name)
		}
	}
}

func TestManagedDirectSwitchRequiresStoppedZeroResourceRuntime(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, record := createdBrowser(t, admin)
	service.directTemplate = &DirectTemplate{
		Owner: "profile-adapter", ApprovedResolverID: "cloudflare-r7e", ApprovedResolverIP: "1.1.1.1",
		RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/",
	}
	plan, err := service.IssueLaunchPlan(context.Background(), "alice", record.ID)
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = record.HomeName
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion, fake.snapshot.NetworkRuntimeVersion = 1, 1, 1
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", record.ID, plan.Token); err != nil {
		t.Fatal(err)
	}
	appendBefore, stopBefore := admin.appendCalls, fake.stopCalls
	if _, err := service.SetBrowserManagedDirect(context.Background(), record.ID, record.Revision, "root", "managed-direct-running"); !errors.Is(err, ErrBrowserBusy) {
		t.Fatalf("running managed DIRECT switch: %v", err)
	}
	if admin.appendCalls != appendBefore || fake.stopCalls != stopBefore {
		t.Fatalf("running managed DIRECT had side effects: appends=%d->%d stops=%d->%d", appendBefore, admin.appendCalls, stopBefore, fake.stopCalls)
	}
	if result, err := service.Stop(context.Background(), record.ID); err != nil || result.Status != "stopped" {
		t.Fatalf("explicit stop: %+v %v", result, err)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = record.HomeName
	updated, err := service.SetBrowserManagedDirect(context.Background(), record.ID, record.Revision, "root", "managed-direct-stopped")
	if err != nil {
		t.Fatal(err)
	}
	if updated.NetworkMode != "direct" || updated.NetworkPolicyID == "" || updated.NetworkPolicySHA256 == "" ||
		admin.appendCalls != appendBefore+1 || admin.lastAppend.Policy["mode"] != "direct" || admin.lastAppend.Policy["approved_resolver_ip"] != "1.1.1.1" {
		t.Fatalf("managed DIRECT result=%+v append=%+v calls=%d", updated, admin.lastAppend, admin.appendCalls)
	}
}

func TestProxyDraftValidationRejectsBeforeAnyAdminCall(t *testing.T) {
	admin := &managementAdmin{}
	service, _, record := createdBrowser(t, admin)
	cases := map[string]func(*ProxyDraftRequest){
		"protocol":        func(r *ProxyDraftRequest) { r.Protocol = "ftp" },
		"auth pair":       func(r *ProxyDraftRequest) { r.Auth = "basic" },
		"none with creds": func(r *ProxyDraftRequest) { r.Auth = "none" },
		"missing secret":  func(r *ProxyDraftRequest) { r.Password = "" },
		"control char":    func(r *ProxyDraftRequest) { r.Password = "a\nb" },
		"loopback":        func(r *ProxyDraftRequest) { r.Host = "127.0.0.1" },
		"private":         func(r *ProxyDraftRequest) { r.Host = "10.1.2.3" },
		"metadata":        func(r *ProxyDraftRequest) { r.Host = "169.254.169.254" },
		"cgnat":           func(r *ProxyDraftRequest) { r.Host = "100.64.0.1" },
		"localhost":       func(r *ProxyDraftRequest) { r.Host = "localhost" },
		"internal":        func(r *ProxyDraftRequest) { r.Host = "metadata.google.internal" },
		"single label":    func(r *ProxyDraftRequest) { r.Host = "proxy" },
		"ipv6":            func(r *ProxyDraftRequest) { r.Host = "2001:db8::1" },
		"userinfo":        func(r *ProxyDraftRequest) { r.Host = "user@proxy.example.net" },
		"port":            func(r *ProxyDraftRequest) { r.Port = 70000 },
		"ca on socks": func(r *ProxyDraftRequest) {
			r.UpstreamCAPEM = "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----"
		},
		"key as ca": func(r *ProxyDraftRequest) {
			r.Protocol, r.Auth, r.UpstreamCAPEM = "https", "basic", "-----BEGIN CERTIFICATE-----\n-----BEGIN PRIVATE KEY-----"
		},
	}
	for name, mutate := range cases {
		request := draftRequest()
		mutate(&request)
		if _, err := service.CreateProxyDraft(context.Background(), record.ID, "root", request); !errors.Is(err, ErrProxyDraftInvalid) {
			t.Fatalf("%s: %v", name, err)
		}
	}
	if admin.importCalls != 0 {
		t.Fatal("invalid drafts reached the controller")
	}
	if _, err := service.CreateProxyDraft(context.Background(), "existing", "root", draftRequest()); !errors.Is(err, ErrNetworkUnmanaged) {
		t.Fatalf("legacy browser draft: %v", err)
	}
	current, _ := service.record(record.ID)
	if current.ProxySecretVersion != 0 || current.Revision != record.Revision {
		t.Fatalf("rejected drafts changed the record: %+v", current)
	}
}

func TestProxyDraftImportsCredentialsOnceAndReservesVersions(t *testing.T) {
	admin := &managementAdmin{}
	service, _, record := createdBrowser(t, admin)
	summary, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest())
	if err != nil {
		t.Fatal(err)
	}
	expectedGrant := sealskin.SecretGrant{Owner: "profile-adapter", Profile: record.ID, Home: record.HomeName, App: record.ApplicationID}
	if admin.importCalls != 1 || admin.lastImport.SecretID != "proxy-"+record.ID || admin.lastImport.SecretVersion != 1 ||
		len(admin.lastImport.Grants) != 1 || admin.lastImport.Grants[0] != expectedGrant || admin.lastImport.Password != "draft-pässword" ||
		admin.lastImportKey != "proxy-import-"+record.ID+"-1" {
		t.Fatalf("import request: %+v key=%q", admin.lastImport, admin.lastImportKey)
	}
	if summary.ProbeStatus != "pending" || summary.SecretVersion != 1 || summary.Host != "proxy.example.net" || summary.Expired || summary.ID == "" {
		t.Fatalf("summary: %+v", summary)
	}
	current, _ := service.record(record.ID)
	if current.ProxySecretVersion != 1 || current.Revision != record.Revision+1 || current.NetworkMode != "direct" || current.ProxyUsernameSecretRef != "" {
		t.Fatalf("record after draft: %+v", current)
	}
	view, ok := service.ProxyDraft(record.ID)
	if !ok || view != summary {
		t.Fatalf("draft view: %+v %v", view, ok)
	}
	replaced, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest())
	if err != nil {
		t.Fatal(err)
	}
	if replaced.SecretVersion != 2 || admin.importCalls != 2 || len(admin.revoked) != 1 || admin.revoked[0] != "secret://proxy-"+record.ID+"/password/1" || len(admin.revokeOperations[0]) != 32 {
		t.Fatalf("replacement: %+v imports=%d revoked=%v", replaced, admin.importCalls, admin.revoked)
	}
	if view, _ := service.ProxyDraft(record.ID); view.ID != replaced.ID {
		t.Fatal("old draft still visible")
	}
	unauthenticated := ProxyDraftRequest{Protocol: "http", Auth: "none", Host: "proxy.example.net", Port: 3128}
	plain, err := service.CreateProxyDraft(context.Background(), record.ID, "root", unauthenticated)
	if err != nil || plain.SecretVersion != 3 || admin.importCalls != 2 {
		t.Fatalf("unauthenticated draft: %+v %v imports=%d", plain, err, admin.importCalls)
	}
	admin.importErr = errors.New("controller unavailable")
	if _, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest()); err == nil {
		t.Fatal("failed import was accepted")
	}
	if _, ok := service.ProxyDraft(record.ID); ok {
		t.Fatal("failed draft remained visible")
	}
	current, _ = service.record(record.ID)
	if current.ProxySecretVersion != 4 {
		t.Fatalf("failed import must still consume its version: %+v", current)
	}
}

func TestProxyDraftProbeApplyAndDirectSwitch(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, record := createdBrowser(t, admin)
	now := time.Date(2026, 9, 18, 15, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	draft, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest())
	if err != nil {
		t.Fatal(err)
	}
	current, _ := service.record(record.ID)
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-1"); !errors.Is(err, ErrProxyDraftNotProbed) {
		t.Fatalf("apply before probe: %v", err)
	}
	probed, err := service.ProbeProxyDraft(context.Background(), record.ID, draft.ID)
	if err != nil || probed.ProbeStatus != "passed" || probed.ProbeCode != "PROXY_PROBE_OK" || probed.UpstreamIP != "203.0.113.9" || probed.ProbedAt == nil {
		t.Fatalf("probe: %+v %v", probed, err)
	}
	if admin.lastProbe.Grant == nil || admin.lastProbe.Grant.Home != record.HomeName || admin.lastProbe.UsernameSecretRef != "secret://proxy-"+record.ID+"/username/1" ||
		admin.lastProbe.ProbeURL != "https://probe.example/" || admin.lastProbe.ProbeTimeoutSeconds != 8 || admin.lastProbe.UpstreamProtocol != "socks5" {
		t.Fatalf("probe request: %+v", admin.lastProbe)
	}
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision-1, draft.ID, "root", "apply-1"); !errors.Is(err, ErrRevisionMismatch) {
		t.Fatalf("stale revision: %v", err)
	}
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = 1, 1
	plan, err := service.IssueLaunchPlan(context.Background(), "alice", record.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", record.ID, plan.Token); err != nil {
		t.Fatal(err)
	}
	stopCalls := fake.stopCalls
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-1"); !errors.Is(err, ErrBrowserBusy) {
		t.Fatalf("busy runtime: %v", err)
	}
	if fake.stopCalls != stopCalls {
		t.Fatalf("proxy apply implicitly stopped a running browser: before=%d after=%d", stopCalls, fake.stopCalls)
	}
	if admin.appendCalls != 0 || admin.patchCalls != 0 {
		t.Fatal("network mutations ran while the runtime was not empty")
	}
	if result, err := service.Stop(context.Background(), record.ID); err != nil || result.Status != "stopped" {
		t.Fatalf("explicit stop before proxy apply: %+v %v", result, err)
	}
	admin.appendErr = errors.New("registry unavailable")
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-1"); err == nil {
		t.Fatal("append failure was accepted")
	}
	unchanged, _ := service.record(record.ID)
	if unchanged.NetworkMode != "direct" || unchanged.Revision != current.Revision || admin.patchCalls != 0 {
		t.Fatalf("record changed after failed append: %+v patches=%d", unchanged, admin.patchCalls)
	}
	admin.appendErr = nil
	applied, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-1")
	if err != nil {
		t.Fatal(err)
	}
	policy := admin.lastAppend.Policy
	if admin.lastAppend.PolicyID != record.ID+"-proxy-r1" || admin.lastAppendKey != "apply-1-policy" || policy["username"] != "profile-adapter" || policy["profile_id"] != record.ID ||
		policy["home_name"] != record.HomeName || policy["application_id"] != record.ApplicationID || policy["mode"] != "proxy_required" || policy["upstream_host"] != "proxy.example.net" ||
		policy["upstream_port"] != 1080 || policy["upstream_protocol"] != "socks5" || policy["upstream_auth"] != "username_password" ||
		policy["username_secret_ref"] != "secret://proxy-"+record.ID+"/username/1" || policy["relay_image"] != testProxyTemplate().RelayImage || policy["probe_url"] != "https://probe.example/" {
		t.Fatalf("appended policy: %+v", admin.lastAppend)
	}
	provider, _ := admin.lastPatch["provider_config"].(map[string]any)
	if admin.lastPatchApp != record.ApplicationID || provider["network_policy_id"] != applied.NetworkPolicyID || provider["network_policy_sha256"] != applied.NetworkPolicySHA256 {
		t.Fatalf("application patch: app=%q patch=%+v", admin.lastPatchApp, admin.lastPatch)
	}
	if applied.NetworkMode != "proxy_required" || applied.NetworkPolicyID != record.ID+"-proxy-r1" || !validDigest(applied.NetworkPolicySHA256) ||
		applied.ProxyUpstream != "socks5://proxy.example.net:1080" || applied.ProxyPasswordSecretRef != "secret://proxy-"+record.ID+"/password/1" ||
		applied.Revision != current.Revision+1 || len(admin.revoked) != 0 {
		t.Fatalf("applied record: %+v revoked=%v", applied, admin.revoked)
	}
	if _, ok := service.ProxyDraft(record.ID); ok {
		t.Fatal("applied draft still visible")
	}
	plan, err = service.IssueLaunchPlan(context.Background(), "alice", record.ID)
	if err != nil || plan.Revision != applied.Revision {
		t.Fatalf("launch plan after switch: %+v %v", plan, err)
	}
	launched := false
	fake.snapshot.HomeName = record.HomeName
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion, fake.snapshot.NetworkRuntimeVersion = 1, 1, 1
	fake.launchHook = func(request sealskin.LaunchURLRequest) {
		launched = request.NetworkPolicyID == applied.NetworkPolicyID && request.NetworkPolicySHA256 == applied.NetworkPolicySHA256
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", record.ID, plan.Token); err != nil {
		t.Fatal(err)
	}
	if !launched {
		t.Fatal("next generation did not use the new policy revision")
	}
	stopCalls = fake.stopCalls
	if _, err := service.SetBrowserDirect(context.Background(), record.ID, applied.Revision, "direct-r1", strings.Repeat("c", 64), "root", "direct-1"); !errors.Is(err, ErrBrowserBusy) {
		t.Fatalf("direct switch while running: %v", err)
	}
	if fake.stopCalls != stopCalls {
		t.Fatalf("DIRECT apply implicitly stopped a running browser: before=%d after=%d", stopCalls, fake.stopCalls)
	}
	if result, err := service.Stop(context.Background(), record.ID); err != nil || result.Status != "stopped" {
		t.Fatalf("explicit stop before DIRECT apply: %+v %v", result, err)
	}
	if _, err := service.SetBrowserDirect(context.Background(), record.ID, applied.Revision, "direct-r1", "nothex", "root", "direct-1"); !errors.Is(err, ErrManagedPolicyRequired) {
		t.Fatalf("invalid DIRECT reference: %v", err)
	}
	direct, err := service.SetBrowserDirect(context.Background(), record.ID, applied.Revision, "direct-r1", strings.Repeat("c", 64), "root", "direct-1")
	if err != nil {
		t.Fatal(err)
	}
	if direct.NetworkMode != "direct" || direct.NetworkPolicyID != "direct-r1" || direct.ProxyUpstream != "" || direct.ProxyUsernameSecretRef != "" ||
		direct.ProxySecretVersion != 1 || len(admin.revoked) != 1 || admin.revoked[0] != "secret://proxy-"+record.ID+"/password/1" {
		t.Fatalf("direct record: %+v revoked=%v", direct, admin.revoked)
	}
}

func TestProxyDraftExpiryFailureAndDeletionRevocation(t *testing.T) {
	admin := &managementAdmin{probeResult: sealskin.ProxyProbeResult{Status: "failed", Code: "PROXY_AUTH_REJECTED", UpstreamIP: "203.0.113.9"}}
	service, fake, record := createdBrowser(t, admin)
	now := time.Date(2026, 9, 18, 15, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	draft, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest())
	if err != nil {
		t.Fatal(err)
	}
	failed, err := service.ProbeProxyDraft(context.Background(), record.ID, draft.ID)
	if err != nil || failed.ProbeStatus != "failed" || failed.ProbeCode != "PROXY_AUTH_REJECTED" {
		t.Fatalf("failed probe: %+v %v", failed, err)
	}
	current, _ := service.record(record.ID)
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-2"); !errors.Is(err, ErrProxyDraftNotProbed) {
		t.Fatalf("apply after failed probe: %v", err)
	}
	if _, err := service.ProbeProxyDraft(context.Background(), record.ID, "other-draft"); !errors.Is(err, ErrProxyDraftNotFound) {
		t.Fatalf("unknown draft probe: %v", err)
	}
	now = now.Add(proxyDraftLifetime + time.Second)
	if view, ok := service.ProxyDraft(record.ID); !ok || !view.Expired {
		t.Fatalf("expired view: %+v %v", view, ok)
	}
	if _, err := service.ProbeProxyDraft(context.Background(), record.ID, draft.ID); !errors.Is(err, ErrProxyDraftNotFound) {
		t.Fatalf("expired draft probe: %v", err)
	}
	if _, err := service.ApplyProxyDraft(context.Background(), record.ID, current.Revision, draft.ID, "root", "apply-2"); !errors.Is(err, ErrProxyDraftNotFound) {
		t.Fatalf("expired draft apply: %v", err)
	}
	if admin.appendCalls != 0 || admin.patchCalls != 0 {
		t.Fatal("expired draft reached the registry")
	}
	if _, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest()); err != nil {
		t.Fatal(err)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = record.HomeName
	if err := service.DeleteBrowser(context.Background(), record.ID, "root", "delete-proxy"); err != nil {
		t.Fatal(err)
	}
	expected := []string{"secret://proxy-" + record.ID + "/password/1", "secret://proxy-" + record.ID + "/password/1", "secret://proxy-" + record.ID + "/password/2"}
	if strings.Join(admin.revoked, ",") != strings.Join(expected, ",") {
		t.Fatalf("revocations: %v", admin.revoked)
	}
	if _, ok := service.ProxyDraft(record.ID); ok {
		t.Fatal("draft survived deletion")
	}
}

func TestProxyDraftsRequireTemplateAndAdmin(t *testing.T) {
	admin := &managementAdmin{}
	service, _, record := createdBrowser(t, admin)
	service.proxyTemplate = nil
	if _, err := service.CreateProxyDraft(context.Background(), record.ID, "root", draftRequest()); !errors.Is(err, ErrProxyUnavailable) {
		t.Fatalf("draft without template: %v", err)
	}
	if _, err := service.SetBrowserDirect(context.Background(), record.ID, 1, "direct-r1", strings.Repeat("c", 64), "root", "d"); !errors.Is(err, ErrProxyUnavailable) {
		t.Fatalf("direct switch without template: %v", err)
	}
}
