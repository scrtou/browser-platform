package profile

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func networkService(t *testing.T, fake *lifecycleFake, store *state.Store) *Service {
	t.Helper()
	service, err := NewService(fake, store, "https://adapter.example", []Definition{{
		ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
		NetworkPolicyID: "socks-r1", NetworkPolicySHA256: strings.Repeat("c", 64),
	}}, WithLifecycle(fake))
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func newNetworkService(t *testing.T, launch bool) (*Service, *state.Store, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service := networkService(t, fake, store)
	if launch {
		if _, err := service.Ensure(context.Background(), "personal"); err != nil {
			t.Fatal(err)
		}
	}
	return service, store, fake
}

func TestNetworkLaunchPersistsPolicyAndStopCarriesSameRevision(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	binding, _, _ := store.Get("personal")
	if binding.NetworkPolicyID != "socks-r1" || binding.NetworkPolicySHA256 != strings.Repeat("c", 64) {
		t.Fatal("new generation did not persist its network policy")
	}
	fake.beforeStop = func(request sealskin.StopProfileRequest, _ string) {
		if request.NetworkPolicyID != binding.NetworkPolicyID || request.NetworkPolicySHA256 != binding.NetworkPolicySHA256 {
			t.Fatal("stop lost the generation's policy")
		}
	}
	result, err := service.Inspect(context.Background(), "personal")
	if err != nil || result.Resources != 5 || result.Networks != 2 || result.Relays != 1 || result.Guards != 1 || result.NetworkPhase != "running" {
		t.Fatalf("network inventory missing: %+v %v", result, err)
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
}

func TestManagedLaunchSeparatesInitialURLOnlyWithExplicitControllerCapability(t *testing.T) {
	for _, version := range []int{0, 1, 2} {
		service, store, fake := newNetworkService(t, false)
		fake.snapshot.ProfileInitialURLVersion = version
		fake.launchHook = func(request sealskin.LaunchURLRequest) {
			if (version == 1 && request.InitialURL != "https://example.com") || (version != 1 && request.InitialURL != "") {
				t.Fatalf("version %d sent unexpected initial URL %q", version, request.InitialURL)
			}
			if !strings.HasPrefix(request.URL, "https://adapter.example/bootstrap/personal/") || request.URL == request.InitialURL {
				t.Fatal("launch lost the unique reconciliation marker")
			}
		}
		if _, err := service.Ensure(context.Background(), "personal"); err != nil {
			t.Fatal(err)
		}
		binding, _, _ := store.Get("personal")
		if fake.sessions[0].LaunchContext.Value != binding.BootstrapURL || binding.Status != state.StatusRunning {
			t.Fatal("initial URL changed the durable launch ownership")
		}
		if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.launches != 1 {
			t.Fatal("existing generation was not reused")
		}
	}
}

func TestInitialURLCapabilityLossDuringLaunchKeepsUnknownReservation(t *testing.T) {
	service, store, fake := newNetworkService(t, false)
	fake.snapshot.ProfileInitialURLVersion = 1
	fake.launchHook = func(sealskin.LaunchURLRequest) { fake.snapshot.ProfileInitialURLVersion = 0 }
	if _, err := service.Ensure(context.Background(), "personal"); err == nil {
		t.Fatal("controller capability loss was accepted")
	}
	binding, found, err := store.Get("personal")
	if err != nil || !found || binding.Status != state.StatusUnknown || fake.launches != 1 {
		t.Fatal("uncertain initial URL launch lost its reservation")
	}
}

func TestNetworkResourcesPreventReleaseAfterWorkerDisappears(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	fake.keepResourcesOnStop = true
	result, err := service.Stop(context.Background(), "personal")
	if !errors.Is(err, ErrStopUnconfirmed) || result.Status != state.StatusStopping || result.Workers != 0 || result.Resources != 5 {
		t.Fatalf("network cleanup failure released Profile: %+v %v", result, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOperationRunning) || fake.launches != 1 {
		t.Fatal("pending network cleanup launched another Worker")
	}
	fake.keepResourcesOnStop = false
	restarted := networkService(t, fake, store)
	result, err = restarted.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped || fake.stopKeys[0] != fake.stopKeys[1] {
		t.Fatalf("restart did not finish network cleanup with original key: %+v %v", result, err)
	}
}

func TestDirectSealSkinStopIntentResumesWithoutSessionRecord(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	fake.snapshot.Records, fake.snapshot.Workers, fake.sessions = []sealskin.RuntimeRecord{}, []sealskin.RuntimeWorker{}, nil
	fake.snapshot.Resources[0].Status = "stopping"
	result, err := service.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped || fake.stopCalls != 1 {
		t.Fatalf("server-side stop intent was not resumed: %+v %v", result, err)
	}
}

func TestRelayOutageKeepsExistingBrowserSessionAvailable(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	fake.snapshot.Resources[3].Status = "exited"
	binding, _, _ := store.Get("personal")
	session, err := service.Ensure(context.Background(), "personal")
	if err != nil || session.SessionID != binding.SessionID || fake.launches != 1 || fake.stopCalls != 0 {
		t.Fatal("Relay outage replaced or hid a live browser")
	}
}

func TestLegacyBindingUsesNewPolicyOnlyAfterStop(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	legacy, _, _ := store.Get("personal")
	service = networkService(t, fake, store)
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatalf("enabling future policy disrupted legacy session: %v", err)
	}
	stillLegacy, _, _ := store.Get("personal")
	if stillLegacy.NetworkPolicyID != "" || stillLegacy.OperationID != legacy.OperationID || fake.launches != 1 {
		t.Fatal("existing session was silently migrated")
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	next, _, _ := store.Get("personal")
	if next.NetworkPolicyID != "socks-r1" || next.OperationID == legacy.OperationID || fake.launches != 2 {
		t.Fatal("next generation did not take the pinned policy")
	}
}

func TestNetworkCapabilityRequiredBeforeCreateAndAfterStop(t *testing.T) {
	service, _, fake := newNetworkService(t, false)
	fake.snapshot.NetworkRuntimeVersion, fake.snapshot.Resources = 0, nil
	if _, err := service.Ensure(context.Background(), "personal"); err == nil || fake.launches != 0 {
		t.Fatal("old server silently ignored a network policy")
	}
	fake.snapshot = emptyRuntime()
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	fake.downgradeAfterStop = true
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrStopUnconfirmed) {
		t.Fatal("incomplete network inventory released Profile after stop")
	}
	fake.snapshot = emptyRuntime()
	if result, err := service.Reconcile(context.Background(), "personal"); err != nil || result.Status != state.StatusStopped {
		t.Fatalf("complete inventory did not finish stop: %+v %v", result, err)
	}
}

func TestNetworkEnforcementRequiredEvenWhenNetworkInventoryExists(t *testing.T) {
	service, _, fake := newNetworkService(t, false)
	fake.snapshot.NetworkEnforcementVersion = 0
	if _, err := service.Ensure(context.Background(), "personal"); err == nil || fake.launches != 0 {
		t.Fatal("a server without network enforcement accepted a new managed launch")
	}
}

func TestForeignGuardPreventsAnyStop(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	fake.snapshot.Resources[4].OperationID = "foreign-generation"
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
		t.Fatal("an unrelated namespace guardian authorized cleanup")
	}
}

func TestNetworkOwnershipRefusesForeignResourceBeforeStop(t *testing.T) {
	for _, field := range []string{"profile", "operation", "policy", "sha", "owned", "kind"} {
		t.Run(field, func(t *testing.T) {
			service, _, fake := newNetworkService(t, true)
			resource := &fake.snapshot.Resources[3]
			switch field {
			case "profile":
				resource.ProfileID = "work"
			case "operation":
				resource.OperationID = "different-generation"
			case "policy":
				resource.PolicyID = "another-policy"
			case "sha":
				resource.PolicySHA256 = strings.Repeat("d", 64)
			case "owned":
				resource.Owned = false
			case "kind":
				resource.Kind = "unrecognized"
			}
			if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
				t.Fatal("foreign resource allowed destructive stop")
			}
		})
	}
}

func TestActiveNetworkPolicyCannotDrift(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	definition := service.profiles["personal"]
	definition.NetworkPolicySHA256 = strings.Repeat("d", 64)
	service.profiles["personal"] = definition
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.launches != 1 {
		t.Fatal("active network policy drift was accepted")
	}
}

func TestPartialPreparationWithClientErrorRemainsUnknownUntilCleanup(t *testing.T) {
	service, store, fake := newNetworkService(t, false)
	fake.launchErr = &sealskin.APIError{StatusCode: 422, Detail: "override rejected after preparation"}
	fake.launchHook = func(request sealskin.LaunchURLRequest) {
		fake.snapshot.Resources = []sealskin.RuntimeResource{{ID: "reservation", Kind: "reservation", Owned: true,
			ProfileID: request.ProfileID, OperationID: request.OperationID, AppID: request.ApplicationID,
			PolicyID: request.NetworkPolicyID, PolicySHA256: request.NetworkPolicySHA256, Status: "preparing"}}
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatal("partial preparation was treated as a clean rejection")
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusUnknown || binding.SessionID != "" {
		t.Fatal("partial allocation lost its generation")
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.launches != 1 {
		t.Fatal("unknown network allocation caused a second create")
	}
	if result, err := service.Stop(context.Background(), "personal"); err != nil || result.Status != state.StatusStopped {
		t.Fatalf("partial preparation could not be cleaned: %+v %v", result, err)
	}
}

func TestNetworkPolicyRequiresLifecycleAndCompleteHash(t *testing.T) {
	store, _ := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	definition := Definition{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
		NetworkPolicyID: "socks-r1", NetworkPolicySHA256: strings.Repeat("c", 64)}
	if _, err := NewService(&fakeOrchestrator{}, store, "https://adapter.example", []Definition{definition}); err == nil {
		t.Fatal("network policy allowed without lifecycle")
	}
	definition.NetworkPolicySHA256 = ""
	if err := validateDefinition(definition); err == nil {
		t.Fatal("policy without revision hash accepted")
	}
}
