package profile

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

type managementAdmin struct {
	authorizeCalls int
	authorizeErr   error
	lastAuthorize  sealskin.ProxySecretAuthorizationRequest
	installCalls   int
	replaceCalls   int
	deleteCalls    int
	archiveCalls   int
	installErr     error
	archiveErr     error
	lastApp        map[string]any
	lastReplace    map[string]any
	lastHome       string
	lastArchive    string

	patchCalls       int
	patchErr         error
	lastPatchApp     string
	lastPatch        map[string]any
	importCalls      int
	importErr        error
	lastImport       sealskin.ProxySecretImportRequest
	lastImportKey    string
	probeCalls       int
	probeErr         error
	probeResult      sealskin.ProxyProbeResult
	lastProbe        sealskin.ProxyProbeRequest
	appendCalls      int
	appendErr        error
	lastAppend       sealskin.NetworkPolicyAppendRequest
	lastAppendKey    string
	appendStarted    chan<- struct{}
	appendRelease    <-chan struct{}
	revoked          []string
	revokeOperations []string
	revokeErr        error
	revokeStarted    chan<- struct{}
}

func (a *managementAdmin) InstallApp(_ context.Context, app map[string]any, _ string) error {
	a.installCalls++
	a.lastApp = app
	return a.installErr
}

func (a *managementAdmin) ReplaceInstalledApp(_ context.Context, appID string, app map[string]any, _ string) error {
	a.replaceCalls++
	a.lastPatchApp, a.lastReplace = appID, app
	return a.patchErr
}

func (a *managementAdmin) DeleteInstalledApp(_ context.Context, _ string, _ string) error {
	a.deleteCalls++
	return nil
}

func (a *managementAdmin) PatchInstalledApp(_ context.Context, appID string, patch map[string]any, _ string) error {
	a.patchCalls++
	a.lastPatchApp, a.lastPatch = appID, patch
	return a.patchErr
}

func (a *managementAdmin) ImportProxySecret(_ context.Context, request sealskin.ProxySecretImportRequest, key string) (sealskin.ProxySecretRefs, error) {
	a.importCalls++
	a.lastImport, a.lastImportKey = request, key
	if a.importErr != nil {
		return sealskin.ProxySecretRefs{}, a.importErr
	}
	version := strconv.Itoa(request.SecretVersion)
	return sealskin.ProxySecretRefs{UsernameSecretRef: "secret://" + request.SecretID + "/username/" + version, PasswordSecretRef: "secret://" + request.SecretID + "/password/" + version}, nil
}

func (a *managementAdmin) ProbeProxyDraft(_ context.Context, request sealskin.ProxyProbeRequest) (sealskin.ProxyProbeResult, error) {
	a.probeCalls++
	a.lastProbe = request
	if a.probeErr != nil {
		return sealskin.ProxyProbeResult{}, a.probeErr
	}
	if a.probeResult.Status == "" {
		return sealskin.ProxyProbeResult{Status: "passed", Code: "PROXY_PROBE_OK", UpstreamIP: "203.0.113.9", HTTPStatus: 204}, nil
	}
	return a.probeResult, nil
}

func (a *managementAdmin) AppendNetworkPolicy(_ context.Context, request sealskin.NetworkPolicyAppendRequest, key string) (sealskin.NetworkPolicyAppendResponse, error) {
	a.appendCalls++
	a.lastAppend, a.lastAppendKey = request, key
	if a.appendStarted != nil {
		a.appendStarted <- struct{}{}
	}
	if a.appendRelease != nil {
		<-a.appendRelease
	}
	if a.appendErr != nil {
		return sealskin.NetworkPolicyAppendResponse{}, a.appendErr
	}
	encoded, _ := json.Marshal(request.Policy)
	digest := sha256.Sum256(encoded)
	return sealskin.NetworkPolicyAppendResponse{PolicyID: request.PolicyID, PolicySHA256: hex.EncodeToString(digest[:]), Created: true}, nil
}

func (a *managementAdmin) RevokeProfileSecret(_ context.Context, reference, operationID string) (sealskin.RevokeSecretResult, error) {
	if a.revokeStarted != nil {
		a.revokeStarted <- struct{}{}
	}
	a.revoked = append(a.revoked, reference)
	a.revokeOperations = append(a.revokeOperations, operationID)
	if a.revokeErr != nil {
		return sealskin.RevokeSecretResult{}, a.revokeErr
	}
	return sealskin.RevokeSecretResult{Revoked: true, EgressBlocked: true, CleanupComplete: true}, nil
}

func (a *managementAdmin) ArchiveHomeDirectory(_ context.Context, home string, archive sealskin.ArchiveHomeRequest, _ string) error {
	a.archiveCalls++
	a.lastHome, a.lastArchive = home, archive.ArchiveName
	return a.archiveErr
}

func managementService(t *testing.T, admin *managementAdmin) (*Service, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(t.TempDir(), "profiles.json")
	service, err := NewService(fake, store, "https://adapter.example", []Definition{{
		ID: "existing", ApplicationID: "existing-app", HomeName: "existing-home", StartURL: "https://example.com",
	}}, WithLifecycle(fake), WithDirectory(directory), WithAdminOrchestrator(admin), WithEnvironmentCatalog(StaticEnvironmentCatalog{
		"env-r9": {ID: "env-r9", SHA256: strings.Repeat("a", 64), AcceptanceSHA256: strings.Repeat("d", 64), Image: "sha256:" + strings.Repeat("b", 64), Source: "frozen", Status: "accepted",
			Application:                 map[string]any{"provider_config": map[string]any{"image": "sha256:" + strings.Repeat("b", 64), "docker_overrides": map[string]any{"labels": map[string]any{}}}},
			RequiredRuntimeCapabilities: map[string]int{"browser_shutdown_version": 1, "session_auth_version": 1}},
	}), WithHomeArchiver(admin), WithProxyTemplate(testProxyTemplate()))
	if err != nil {
		t.Fatal(err)
	}
	return service, fake
}

func createRequest() CreateBrowserRequest {
	return CreateBrowserRequest{Label: "新浏览器", StartURL: "https://start.example/", EnvironmentArtifactID: "env-r9",
		NetworkMode: "direct", NetworkPolicyID: "direct-r1", NetworkPolicySHA256: strings.Repeat("c", 64)}
}

func TestCreateBrowserPersistsFixedBindingsAndIsIdempotent(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := managementService(t, admin)
	record, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-1")
	if err != nil {
		t.Fatal(err)
	}
	if record.Status != RecordReady || record.Revision != 2 || record.EnvironmentArtifactID != "env-r9" || record.NetworkMode != "direct" || !service.KnownProfile(record.ID) {
		t.Fatalf("record = %+v", record)
	}
	if admin.installCalls != 1 || admin.lastApp["id"] != record.ApplicationID || !contains(fake.homes, record.HomeName) {
		t.Fatalf("side effects: install=%d app=%v homes=%v", admin.installCalls, admin.lastApp, fake.homes)
	}
	again, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-1")
	if err != nil || again.ID != record.ID || admin.installCalls != 1 {
		t.Fatalf("idempotent retry: %+v err=%v installs=%d", again, err, admin.installCalls)
	}
	changed := createRequest()
	changed.StartURL = "https://other.example/"
	if _, err := service.CreateBrowser(context.Background(), changed, "root", "request-1"); !errors.Is(err, ErrRevisionMismatch) {
		t.Fatalf("changed idempotent request: %v", err)
	}
}

func TestCreateBrowserManagedDirectMaterializesPolicyServerSide(t *testing.T) {
	admin := &managementAdmin{}
	service, _ := managementService(t, admin)
	service.directTemplate = &DirectTemplate{
		Owner: "adapter", ApprovedResolverID: "cloudflare-r7e", ApprovedResolverIP: "1.1.1.1",
		RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/",
	}
	request := createRequest()
	request.NetworkPolicyID, request.NetworkPolicySHA256 = "", ""
	record, err := service.CreateBrowser(context.Background(), request, "root", "managed-direct-create")
	if err != nil {
		t.Fatal(err)
	}
	if admin.appendCalls != 1 || admin.lastAppend.Policy["mode"] != "direct" ||
		admin.lastAppend.Policy["approved_resolver_id"] != "cloudflare-r7e" ||
		record.NetworkPolicyID != admin.lastAppend.PolicyID || record.NetworkPolicySHA256 == "" {
		t.Fatalf("managed DIRECT create: record=%+v append=%+v calls=%d", record, admin.lastAppend, admin.appendCalls)
	}
	raw := createRequest()
	if _, err := service.CreateBrowser(context.Background(), raw, "root", "managed-direct-raw"); !errors.Is(err, ErrManagedPolicyRequired) {
		t.Fatalf("raw policy reference accepted with managed DIRECT enabled: %v", err)
	}
}

func TestCreateFailureStaysCreatingAndRetryCompletes(t *testing.T) {
	admin := &managementAdmin{installErr: errors.New("controller unavailable")}
	service, _ := managementService(t, admin)
	record, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-2")
	if err == nil || record.Status != RecordCreating {
		t.Fatalf("failed creation: %+v %v", record, err)
	}
	if _, err := service.IssueLaunchPlan(context.Background(), "root", record.ID); !errors.Is(err, ErrBrowserCreating) {
		t.Fatalf("creating browser issued a launch plan: %v", err)
	}
	admin.installErr = nil
	ready, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-2")
	if err != nil || ready.Status != RecordReady || admin.installCalls != 2 {
		t.Fatalf("retry: %+v %v installs=%d", ready, err, admin.installCalls)
	}
}

func TestDeleteBrowserArchivesOnlyAfterRuntimeIsEmpty(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := managementService(t, admin)
	record, err := service.CreateBrowser(context.Background(), createRequest(), "root", "request-3")
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = record.HomeName
	fake.snapshot.Records = []sealskin.RuntimeRecord{{SessionID: "foreign"}}
	if err := service.DeleteBrowser(context.Background(), record.ID, "root", "delete-1"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatalf("busy/foreign runtime deletion: %v", err)
	}
	if admin.archiveCalls != 0 || admin.deleteCalls != 0 {
		t.Fatal("destructive admin calls ran before ownership was empty")
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = record.HomeName
	admin.archiveErr = errors.New("archive controller unavailable")
	if err := service.DeleteBrowser(context.Background(), record.ID, "root", "delete-1"); err == nil {
		t.Fatal("archive failure was accepted")
	}
	firstArchive := admin.lastArchive
	admin.archiveErr = nil
	if err := service.DeleteBrowser(context.Background(), record.ID, "root", "delete-1"); err != nil {
		t.Fatal(err)
	}
	if service.KnownProfile(record.ID) || admin.archiveCalls != 2 || admin.deleteCalls != 1 || admin.lastHome != record.HomeName || admin.lastArchive != firstArchive || !strings.HasPrefix(admin.lastArchive, "archive-"+record.ID+"-") {
		t.Fatalf("delete result: known=%v archive=%d delete=%d home=%q archiveName=%q", service.KnownProfile(record.ID), admin.archiveCalls, admin.deleteCalls, admin.lastHome, admin.lastArchive)
	}
}

func TestLaunchPlanBindsSubjectRevisionExpiryAndSingleUse(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := managementService(t, admin)
	now := time.Date(2026, 9, 18, 13, 25, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	plan, err := service.IssueLaunchPlan(context.Background(), "alice", "existing")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "bob", "existing", plan.Token); !errors.Is(err, ErrLaunchPlanInvalid) {
		t.Fatalf("cross-account plan: %v", err)
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", "existing", plan.Token); err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", "existing", plan.Token); !errors.Is(err, ErrLaunchPlanInvalid) {
		t.Fatalf("reused plan: %v", err)
	}
	if fake.launches != 1 {
		t.Fatalf("launches = %d", fake.launches)
	}
	expired, err := service.IssueLaunchPlan(context.Background(), "alice", "existing")
	if err != nil {
		t.Fatal(err)
	}
	now = now.Add(91 * time.Second)
	if _, err := service.EnsureWithLaunchPlan(context.Background(), "alice", "existing", expired.Token); !errors.Is(err, ErrLaunchPlanInvalid) {
		t.Fatalf("expired plan: %v", err)
	}
}

func (a *managementAdmin) AuthorizeProxySecret(_ context.Context, request sealskin.ProxySecretAuthorizationRequest, _ string) error {
	a.authorizeCalls++
	a.lastAuthorize = request
	return a.authorizeErr
}
