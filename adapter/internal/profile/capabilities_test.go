package profile

import (
	"context"
	"path/filepath"
	"testing"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func requireR7(service *Service) {
	definition, _ := service.directory.get("personal")
	definition.RequiredRuntimeCapabilities = map[string]int{"browser_shutdown_version": 1, "session_auth_version": 1}
	service.directory.records["personal"] = Record{Definition: definition, Revision: 1}
}

func TestIncompatibleControllerDoesNotCreateHomeOrLaunch(t *testing.T) {
	for _, versions := range [][2]int{{0, 0}, {1, 0}, {0, 1}, {1, 2}} {
		fake := &lifecycleFake{snapshot: emptyRuntime()}
		fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = versions[0], versions[1]
		store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
		if err != nil {
			t.Fatal(err)
		}
		service := lifecycleService(t, fake, store)
		requireR7(service)
		if _, err := service.Ensure(context.Background(), "personal"); err == nil {
			t.Fatal("incompatible controller accepted")
		}
		if fake.launches != 0 || len(fake.homes) != 0 {
			t.Fatal("rejection created a Home or Worker")
		}
		if _, found, err := store.Get("personal"); err != nil || found {
			t.Fatal("rejection changed journal", err)
		}
	}
}

func TestRuntimeRequirementsAllowMatchingLaunchAndPreserveStopAfterDowngrade(t *testing.T) {
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = 1, 1
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service := lifecycleService(t, fake, store)
	requireR7(service)
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	result, err := service.Inspect(context.Background(), "personal")
	if err != nil || result.Capabilities["session_auth_version"] != 1 {
		t.Fatal("missing live capability", err)
	}
	before, _, _ := store.Get("personal")
	fake.snapshot.SessionAuthVersion = 0
	if _, err := service.Ensure(context.Background(), "personal"); err == nil {
		t.Fatal("downgraded controller reused session")
	}
	after, _, _ := store.Get("personal")
	if before.OperationID != after.OperationID || fake.launches != 1 {
		t.Fatal("rejection changed operation")
	}
	if result, err := service.Stop(context.Background(), "personal"); err != nil || result.Status != state.StatusStopped {
		t.Fatal("capability rejection prevented verified cleanup", err)
	}
}

func TestRuntimeCapabilityDowngradeDuringLaunchPreservesUnknown(t *testing.T) {
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = 1, 1
	fake.launchHook = func(sealskin.LaunchURLRequest) { fake.snapshot.SessionAuthVersion = 0 }
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service := lifecycleService(t, fake, store)
	requireR7(service)
	if _, err := service.Ensure(context.Background(), "personal"); err == nil {
		t.Fatal("controller downgrade during launch accepted")
	}
	binding, found, err := store.Get("personal")
	if err != nil || !found || binding.Status != state.StatusUnknown || fake.launches != 1 {
		t.Fatalf("failed launch lost reservation: %+v %v", binding, err)
	}
}

func TestUnsupportedRuntimeRequirementsAreRejected(t *testing.T) {
	for _, requirement := range []map[string]int{{"session_auth_version": 0}, {"session_auth_version": 2}, {"unknown": 1}} {
		definition := Definition{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com",
			RequiredRuntimeCapabilities: requirement}
		if err := validateDefinition(definition); err == nil {
			t.Fatal("unsupported runtime requirement accepted")
		}
	}
}

func TestUnsupportedControllerCannotResumeThroughReconciliation(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	requireR7(service)
	makeDormant(fake)
	before, _, _ := store.Get("personal")
	if _, err := service.Reconcile(context.Background(), "personal"); err == nil {
		t.Fatal("reconciliation resumed on an incompatible controller")
	}
	after, _, _ := store.Get("personal")
	if fake.resumeCalls != 0 || fake.launches != 1 || after.OperationID != before.OperationID {
		t.Fatal("capability refusal mutated the dormant generation")
	}
}
