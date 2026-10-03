package profile

import (
	"browser-platform/adapter/internal/sealskin"
	"context"
	"errors"
	"os"
	"strings"
	"sync"
	"testing"
)

func createProxyFixture(t *testing.T) (*Service, *managementAdmin, CreateBrowserRequest) {
	t.Helper()
	admin := &managementAdmin{}
	service, _, _, _ := networkCatalogService(t, admin)
	draft, err := service.CreateNetworkProfileDraft(context.Background(), "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	if _, err = service.ProbeNetworkProfileDraft(context.Background(), draft.ID, draft.DraftID, "root"); err != nil {
		t.Fatal(err)
	}
	request := createRequest()
	request.NetworkMode, request.NetworkPolicyID, request.NetworkPolicySHA256 = "proxy_required", "", ""
	request.NetworkProfileID, request.NetworkProfileRevision = draft.ID, 1
	return service, admin, request
}

func TestCreateReusesProxyWithExactGrantAndIndependentPolicies(t *testing.T) {
	service, admin, request := createProxyFixture(t)
	oldImports := admin.importCalls
	first, err := service.CreateBrowser(context.Background(), request, "root", "proxy-first")
	if err != nil {
		t.Fatal(err)
	}
	grant := admin.lastAuthorize.Grant
	if first.Status != RecordReady || grant.Owner != service.proxyTemplate.Owner || grant.Profile != first.ID || grant.Home != first.HomeName || grant.App != first.ApplicationID || admin.lastAuthorize.RequestSHA256 != first.CreationRequestSHA256 {
		t.Fatal("incorrect grant or record")
	}
	if err := service.verifyNetworkProfileBinding(first.Definition); err != nil {
		t.Fatal(err)
	}
	second, err := service.CreateBrowser(context.Background(), request, "root", "proxy-second")
	if err != nil {
		t.Fatal(err)
	}
	if first.ID == second.ID || first.NetworkPolicyID == second.NetworkPolicyID || first.ProxyPasswordSecretRef != second.ProxyPasswordSecretRef || admin.importCalls != oldImports {
		t.Fatal("expected separate policy and shared credential version")
	}
	_, revision, _ := service.networkProfiles.getRevision(request.NetworkProfileID, 1)
	if !contains(revision.AllowedProfiles, first.ID) || !contains(revision.AllowedProfiles, second.ID) {
		t.Fatal("grants not persisted")
	}
	for _, path := range []string{service.directoryPath, service.networkProfileCatalogPath} {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(raw), "catalog-password") || strings.Contains(string(raw), "catalog-user") {
			t.Fatal("plaintext credential persisted")
		}
	}
	before := admin.authorizeCalls
	if _, err := service.CreateBrowser(context.Background(), request, "root", "proxy-first"); err != nil || admin.authorizeCalls != before {
		t.Fatalf("completed retry performed side effects: %v", err)
	}
}

func TestProxyCreationFailureRetryAfterDirectoryReload(t *testing.T) {
	for _, stage := range []string{"authorize", "policy", "install"} {
		t.Run(stage, func(t *testing.T) {
			service, admin, request := createProxyFixture(t)
			failure := errors.New("lost response")
			switch stage {
			case "authorize":
				admin.authorizeErr = failure
			case "policy":
				admin.appendErr = failure
			case "install":
				admin.installErr = failure
			}
			pending, err := service.CreateBrowser(context.Background(), request, "root", "interrupted")
			if err == nil || pending.Status != RecordCreating || pending.CreationRequestSHA256 == "" {
				t.Fatalf("missing durable intent: %v", err)
			}
			service, err = NewService(service.orchestrator, service.store, "https://adapter.example", nil,
				WithLifecycle(service.runtime), WithDirectory(service.directoryPath), WithAdminOrchestrator(admin),
				WithEnvironmentCatalog(service.catalog), WithProxyTemplate(*service.proxyTemplate), WithNetworkProfileCatalog(service.networkProfileCatalogPath))
			if err != nil {
				t.Fatalf("restart after %s: %v", stage, err)
			}
			changed := request
			changed.Label = "altered"
			before := admin.authorizeCalls
			if _, err := service.CreateBrowser(context.Background(), changed, "root", "interrupted"); !errors.Is(err, ErrRevisionMismatch) || admin.authorizeCalls != before {
				t.Fatalf("altered retry accepted: %v", err)
			}
			admin.authorizeErr, admin.appendErr, admin.installErr = nil, nil, nil
			ready, err := service.CreateBrowser(context.Background(), request, "root", "interrupted")
			if err != nil || ready.Status != RecordReady || ready.ID != pending.ID {
				t.Fatalf("retry failed: %v", err)
			}
			if err := service.verifyNetworkProfileBinding(ready.Definition); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestInvalidProxyCreateHasNoAuthorizationOrPolicySideEffect(t *testing.T) {
	service, admin, request := createProxyFixture(t)
	for _, change := range []func(*CreateBrowserRequest){
		func(r *CreateBrowserRequest) { r.StartURL = "javascript:bad" },
		func(r *CreateBrowserRequest) { r.Label = strings.Repeat("x", 65) },
		func(r *CreateBrowserRequest) { r.NetworkProfileRevision = 99 },
		func(r *CreateBrowserRequest) { r.NetworkPolicyID = "raw" },
	} {
		bad := request
		change(&bad)
		before := len(service.Records())
		policies := admin.appendCalls
		if _, err := service.CreateBrowser(context.Background(), bad, "root", "invalid"); err == nil {
			t.Fatal("invalid request accepted")
		}
		if admin.authorizeCalls != 0 || admin.appendCalls != policies || len(service.Records()) != before {
			t.Fatal("invalid request produced side effects")
		}
	}
	if _, err := service.DisableNetworkProfile(request.NetworkProfileID, 1, "root", "disabled"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.CreateBrowser(context.Background(), request, "root", "disabled-create"); !errors.Is(err, ErrNetworkProfileNotAccepted) || admin.authorizeCalls != 0 {
		t.Fatalf("disabled selected: %v", err)
	}
}

func TestConcurrentIdenticalProxyCreateInstallsOnce(t *testing.T) {
	service, admin, request := createProxyFixture(t)
	installs := admin.installCalls
	var wg sync.WaitGroup
	results := make(chan error, 8)
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := service.CreateBrowser(context.Background(), request, "root", "concurrent")
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	for err := range results {
		if err != nil {
			t.Fatal(err)
		}
	}
	if admin.authorizeCalls != 1 || admin.installCalls != installs+1 {
		t.Fatal("duplicate creation side effects")
	}
}

// Model the controller's per-admin-session idempotency cache. UI administrators
// share that client, but their browser IDs and external effects must be distinct.
type cachedCreateAdmin struct {
	*managementAdmin
	policies map[string]sealskin.NetworkPolicyAppendResponse
	installs map[string]bool
}

func (a *cachedCreateAdmin) AppendNetworkPolicy(ctx context.Context, request sealskin.NetworkPolicyAppendRequest, key string) (sealskin.NetworkPolicyAppendResponse, error) {
	if prior, ok := a.policies[key]; ok {
		return prior, nil
	}
	result, err := a.managementAdmin.AppendNetworkPolicy(ctx, request, key)
	if err == nil {
		a.policies[key] = result
	}
	return result, err
}
func (a *cachedCreateAdmin) InstallApp(ctx context.Context, app map[string]any, key string) error {
	if a.installs[key] {
		return nil
	}
	err := a.managementAdmin.InstallApp(ctx, app, key)
	if err == nil {
		a.installs[key] = true
	}
	return err
}
func TestDifferentAdministratorsCanUseSameCreateKey(t *testing.T) {
	service, admin, request := createProxyFixture(t)
	cache := &cachedCreateAdmin{managementAdmin: admin, policies: map[string]sealskin.NetworkPolicyAppendResponse{}, installs: map[string]bool{}}
	service.admin = cache
	first, err := service.CreateBrowser(context.Background(), request, "first-admin", "same-key")
	if err != nil {
		t.Fatal(err)
	}
	second, err := service.CreateBrowser(context.Background(), request, "second-admin", "same-key")
	if err != nil {
		t.Fatal(err)
	}
	if first.ID == second.ID || first.NetworkPolicyID == second.NetworkPolicyID || len(cache.policies) != 2 || len(cache.installs) != 2 {
		t.Fatal("cross-administrator creation cache collision")
	}
}
