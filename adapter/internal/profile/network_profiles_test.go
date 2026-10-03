package profile

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
)

func networkCatalogService(t *testing.T, admin *managementAdmin) (*Service, *lifecycleFake, Record, string) {
	t.Helper()
	service, fake, record := createdBrowser(t, admin)
	path := filepath.Join(t.TempDir(), "network_profiles.json")
	catalog, err := newNetworkProfileCatalog(path, func() time.Time { return service.now() })
	if err != nil {
		t.Fatal(err)
	}
	service.networkProfileCatalogPath, service.networkProfiles = path, catalog
	service.directTemplate = &DirectTemplate{
		Owner: "adapter", ApprovedResolverID: "cloudflare-r7e", ApprovedResolverIP: "1.1.1.1",
		RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/",
	}
	return service, fake, record, path
}

func networkDraftRequest() NetworkProfileDraftRequest {
	return NetworkProfileDraftRequest{ID: "corp-egress", Label: "公司代理", IdempotencyKey: "create-corp-r1", Protocol: "socks5", Auth: "username_password",
		Host: "proxy.example.net", Port: 1080, Username: "catalog-user", Password: "catalog-password"}
}

func TestNetworkProfileCatalogPersistsRedactedPendingRevision(t *testing.T) {
	admin := &managementAdmin{}
	service, _, _, path := networkCatalogService(t, admin)
	now := time.Date(2026, 9, 22, 9, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }

	summary, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	if summary.ID != "corp-egress" || summary.Revision != 1 || summary.Status != NetworkRevisionPending || summary.Expired || summary.References != 0 {
		t.Fatalf("summary = %+v", summary)
	}
	if admin.importCalls != 1 || admin.lastImport.SecretID != "network-corp-egress" || admin.lastImport.SecretVersion != 1 || len(admin.lastImport.Grants) != 2 ||
		admin.lastImport.Username != "catalog-user" || admin.lastImport.Password != "catalog-password" || admin.lastImportKey != "network-import-corp-egress-1" {
		t.Fatalf("import = %+v key=%q", admin.lastImport, admin.lastImportKey)
	}
	retried, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil || retried.Revision != summary.Revision || retried.DraftID != summary.DraftID || admin.importCalls != 1 {
		t.Fatalf("idempotent create = %+v err=%v imports=%d", retried, err, admin.importCalls)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(data), "catalog-user") || strings.Contains(string(data), "catalog-password") {
		t.Fatal("network catalog persisted plaintext credentials")
	}
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("catalog mode = %v err=%v", info.Mode().Perm(), err)
	}

	reopened, err := newNetworkProfileCatalog(path, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	service.networkProfiles = reopened
	list, err := service.NetworkProfiles()
	if err != nil || len(list) != 1 || list[0].Status != NetworkRevisionPending || !contains(list[0].AllowedProfiles, "existing") {
		t.Fatalf("reopened list = %+v err=%v", list, err)
	}
}

func TestNetworkProfileAcceptBindDisableDirectAndRevoke(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, browser, _ := networkCatalogService(t, admin)
	now := time.Date(2026, 9, 22, 10, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, err := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	if err != nil {
		t.Fatal(err)
	}
	accepted, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root")
	if err != nil || accepted.Status != NetworkRevisionAccepted || accepted.ProbeCode != "PROXY_PROBE_OK" || accepted.ProbeAt == nil || accepted.AcceptedAt == nil {
		t.Fatalf("accepted = %+v err=%v", accepted, err)
	}
	if admin.lastProbe.UsernameSecretRef != "secret://network-corp-egress/username/1" || admin.lastProbe.Grant == nil || !contains(accepted.AllowedProfiles, browser.ID) {
		t.Fatalf("probe = %+v accepted=%+v", admin.lastProbe, accepted)
	}

	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = browser.HomeName
	bound, err := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "bind-corp-1")
	if err != nil {
		t.Fatal(err)
	}
	if bound.NetworkProfileID != draft.ID || bound.NetworkProfileRevision != 1 || bound.NetworkMode != "proxy_required" ||
		bound.ProxyUsernameSecretRef != "secret://network-corp-egress/username/1" || bound.ProxyUpstream != "socks5://proxy.example.net:1080" {
		t.Fatalf("bound = %+v", bound)
	}
	appendCalls := admin.appendCalls
	retried, err := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "bind-corp-1")
	if err != nil || retried.Revision != bound.Revision || admin.appendCalls != appendCalls {
		t.Fatalf("idempotent bind = %+v err=%v appends=%d", retried, err, admin.appendCalls)
	}
	policy := admin.lastAppend.Policy
	if policy["profile_id"] != browser.ID || policy["home_name"] != browser.HomeName || policy["application_id"] != browser.ApplicationID ||
		policy["username_secret_ref"] != bound.ProxyUsernameSecretRef || admin.lastAppendKey != "bind-corp-1-policy" {
		t.Fatalf("policy = %+v key=%q", policy, admin.lastAppendKey)
	}
	list, err := service.NetworkProfiles()
	if err != nil || len(list) != 1 || list[0].References != 1 {
		t.Fatalf("references = %+v err=%v", list, err)
	}
	disabled, err := service.DisableNetworkProfile(draft.ID, draft.Revision, "root", "disable-corp-r1")
	if err != nil || disabled.Status != NetworkRevisionDisabled || disabled.References != 1 {
		t.Fatalf("disabled = %+v err=%v", disabled, err)
	}
	catalogRevision := service.networkProfiles.revision
	retriedDisabled, err := service.DisableNetworkProfile(draft.ID, draft.Revision, "root", "disable-corp-r1")
	if err != nil || retriedDisabled.Status != NetworkRevisionDisabled || service.networkProfiles.revision != catalogRevision {
		t.Fatalf("idempotent disable = %+v err=%v catalog_revision=%d", retriedDisabled, err, service.networkProfiles.revision)
	}
	if _, err := service.BindNetworkProfile(context.Background(), browser.ID, bound.Revision, draft.ID, draft.Revision, "root", "bind-disabled"); !errors.Is(err, ErrNetworkProfileNotAccepted) {
		t.Fatalf("disabled revision bound: %v", err)
	}
	if _, err := service.RevokeNetworkProfile(context.Background(), draft.ID, draft.Revision, "root", "disable-corp-r1"); !errors.Is(err, ErrRevisionMismatch) {
		t.Fatalf("cross-operation idempotency key reused: %v", err)
	}
	if _, err := service.RevokeNetworkProfile(context.Background(), draft.ID, draft.Revision, "root", "revoke-corp-r1"); !errors.Is(err, ErrNetworkProfileReferenced) {
		t.Fatalf("referenced revision revoked: %v", err)
	}

	direct, err := service.SetBrowserDirect(context.Background(), browser.ID, bound.Revision, "direct-r1", strings.Repeat("c", 64), "root", "direct-after-catalog")
	if err != nil {
		t.Fatal(err)
	}
	if direct.NetworkProfileID != "" || direct.NetworkProfileRevision != 0 || direct.ProxyUsernameSecretRef != "" {
		t.Fatalf("DIRECT retained catalog binding: %+v", direct)
	}
	revoked, err := service.RevokeNetworkProfile(context.Background(), draft.ID, draft.Revision, "root", "revoke-corp-r1")
	if err != nil || revoked.Status != NetworkRevisionRevoked || revoked.References != 0 {
		t.Fatalf("revoked = %+v err=%v", revoked, err)
	}
	if got := admin.revoked[len(admin.revoked)-1]; got != "secret://network-corp-egress/password/1" {
		t.Fatalf("revoked refs = %v", admin.revoked)
	}
	revokeCalls, catalogRevision := len(admin.revoked), service.networkProfiles.revision
	retriedRevoked, err := service.RevokeNetworkProfile(context.Background(), draft.ID, draft.Revision, "root", "revoke-corp-r1")
	if err != nil || retriedRevoked.Status != NetworkRevisionRevoked || len(admin.revoked) != revokeCalls || service.networkProfiles.revision != catalogRevision {
		t.Fatalf("idempotent revoke = %+v err=%v revocations=%d catalog_revision=%d", retriedRevoked, err, len(admin.revoked), service.networkProfiles.revision)
	}
}

func TestNetworkProfileBindsLegacyManagedRecordAndRejectsUnmanagedLegacy(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, browser, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, err := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root"); err != nil {
		t.Fatal(err)
	}
	service.directory.mu.Lock()
	legacy := service.directory.records[browser.ID]
	legacy.NetworkMode = ""
	service.directory.records[browser.ID] = legacy
	service.directory.mu.Unlock()
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = browser.HomeName
	bound, err := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "legacy-bind")
	if err != nil || bound.NetworkMode != "proxy_required" || bound.NetworkProfileID != draft.ID {
		t.Fatalf("legacy managed bind = %+v err=%v", bound, err)
	}
	service.directory.mu.Lock()
	legacy = service.directory.records[browser.ID]
	legacy.NetworkMode, legacy.NetworkPolicyID, legacy.NetworkPolicySHA256 = "", "", ""
	service.directory.records[browser.ID] = legacy
	service.directory.mu.Unlock()
	if got, _ := service.record(browser.ID); got.NetworkMode != "" || got.NetworkPolicyID != "" || got.NetworkPolicySHA256 != "" {
		t.Fatalf("legacy clear failed: %+v", got)
	}
	if _, err := service.BindNetworkProfile(context.Background(), browser.ID, bound.Revision, draft.ID, draft.Revision, "root", "unmanaged-legacy"); !errors.Is(err, ErrNetworkUnmanaged) {
		t.Fatalf("unmanaged legacy bind error = %v", err)
	}
}

func TestNetworkProfileBindingNeverStopsRunningBrowser(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, browser, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, _ := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	if _, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root"); err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = browser.HomeName
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = 1, 1
	plan, err := service.IssueLaunchPlan(context.Background(), "alice", browser.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", browser.ID, plan.Token); err != nil {
		t.Fatal(err)
	}
	stopCalls := fake.stopCalls
	if _, err := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "bind-running"); !errors.Is(err, ErrBrowserBusy) {
		t.Fatalf("running browser binding: %v", err)
	}
	if fake.stopCalls != stopCalls || admin.appendCalls != 0 || admin.patchCalls != 0 {
		t.Fatalf("binding had side effects: stops=%d appends=%d patches=%d", fake.stopCalls-stopCalls, admin.appendCalls, admin.patchCalls)
	}
}

func TestNetworkProfileRevokeCannotRaceBindingReference(t *testing.T) {
	appendStarted, appendRelease, revokeStarted := make(chan struct{}, 1), make(chan struct{}), make(chan struct{}, 1)
	admin := &managementAdmin{appendStarted: appendStarted, appendRelease: appendRelease, revokeStarted: revokeStarted}
	service, fake, browser, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, _ := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	if _, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root"); err != nil {
		t.Fatal(err)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = browser.HomeName

	type bindResult struct {
		record Record
		err    error
	}
	bound := make(chan bindResult, 1)
	go func() {
		record, bindErr := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "bind-race")
		bound <- bindResult{record: record, err: bindErr}
	}()
	<-appendStarted
	revoked := make(chan error, 1)
	go func() {
		_, revokeErr := service.RevokeNetworkProfile(context.Background(), draft.ID, draft.Revision, "root", "revoke-race")
		revoked <- revokeErr
	}()
	interleaved := false
	select {
	case <-revokeStarted:
		interleaved = true
	case <-time.After(100 * time.Millisecond):
	}
	close(appendRelease)
	bindOutcome, revokeErr := <-bound, <-revoked
	if interleaved || bindOutcome.err != nil || bindOutcome.record.NetworkProfileID != draft.ID || !errors.Is(revokeErr, ErrNetworkProfileReferenced) {
		t.Fatalf("bind/revoke serialization: interleaved=%v bound=%+v revoke=%v", interleaved, bindOutcome, revokeErr)
	}
}

func TestNetworkProfileFailedProbeRevokesAndCannotBind(t *testing.T) {
	admin := &managementAdmin{probeResult: proxyProbeFailure()}
	service, fake, browser, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, _ := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	failed, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root")
	if err != nil || failed.Status != NetworkRevisionFailed || failed.ProbeCode != "PROXY_AUTH_REJECTED" || failed.ProbeAt == nil {
		t.Fatalf("failed = %+v err=%v", failed, err)
	}
	if len(admin.revoked) != 1 || admin.revoked[0] != "secret://network-corp-egress/password/1" {
		t.Fatalf("failed probe revocations = %v", admin.revoked)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = browser.HomeName
	if _, err := service.BindNetworkProfile(context.Background(), browser.ID, browser.Revision, draft.ID, draft.Revision, "root", "bind-failed"); !errors.Is(err, ErrNetworkProfileNotAccepted) {
		t.Fatalf("failed revision bound: %v", err)
	}
}

func proxyProbeFailure() sealskin.ProxyProbeResult {
	return sealskin.ProxyProbeResult{Status: "failed", Code: "PROXY_AUTH_REJECTED", UpstreamIP: "203.0.113.9"}
}

func TestAuthenticatedNetworkRevisionDoesNotAuthorizeFutureBrowser(t *testing.T) {
	admin := &managementAdmin{}
	service, fake, _, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	_, stored, _ := service.networkProfiles.getRevision(draft.ID, draft.Revision)
	if _, err := service.ProbeNetworkProfileDraft(context.Background(), draft.ID, stored.DraftID, "root"); err != nil {
		t.Fatal(err)
	}
	request := createRequest()
	request.NetworkPolicyID, request.NetworkPolicySHA256 = "", ""
	future, err := service.CreateBrowser(context.Background(), request, "root", "future-browser")
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = future.HomeName
	if _, err := service.BindNetworkProfile(context.Background(), future.ID, future.Revision, draft.ID, draft.Revision, "root", "future-bind"); !errors.Is(err, ErrNetworkProfileUnauthorized) {
		t.Fatalf("future browser used an ungranted credential revision: %v", err)
	}
}
