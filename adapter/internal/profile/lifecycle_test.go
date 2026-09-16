package profile

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

type lifecycleFake struct {
	fakeOrchestrator
	runtimeMu           sync.Mutex
	snapshot            sealskin.HomeRuntime
	inspectErr          error
	postStopErr         error
	stopErr             error
	keepOnStop          bool
	keepResourcesOnStop bool
	downgradeAfterStop  bool
	launchHook          func(sealskin.LaunchURLRequest)
	stopCalls           int
	stopKeys            []string
	beforeStop          func(sealskin.StopProfileRequest, string)
	stopEntered         chan struct{}
	stopRelease         chan struct{}
	observeErr          error
	observeCalls        int
	observeUpstream     []bool
	observeHook         func(*sealskin.HomeHealth)
	observeBlock        chan struct{}
	resumeErr           error
	resumeCalls         int
	resumeKeys          []string
	resumeRequests      []sealskin.StopProfileRequest
	resumeKeepDormant   bool
}

func emptyRuntime() sealskin.HomeRuntime {
	return sealskin.HomeRuntime{Version: 1, HomeName: "personal", Records: []sealskin.RuntimeRecord{}, Workers: []sealskin.RuntimeWorker{},
		NetworkRuntimeVersion: 1, NetworkEnforcementVersion: 1, Resources: []sealskin.RuntimeResource{}}
}

func (f *lifecycleFake) LaunchURL(ctx context.Context, request sealskin.LaunchURLRequest, key string) (sealskin.LaunchResponse, error) {
	if f.launchHook != nil {
		f.launchHook(request)
	}
	response, err := f.fakeOrchestrator.LaunchURL(ctx, request, key)
	if err != nil {
		return response, err
	}
	f.runtimeMu.Lock()
	defer f.runtimeMu.Unlock()
	instance := strings.Repeat("a", 64)
	f.snapshot = sealskin.HomeRuntime{Version: 1, HomeName: request.HomeName,
		NetworkRuntimeVersion: 1, NetworkEnforcementVersion: 1, Resources: []sealskin.RuntimeResource{},
		ProfileInitialURLVersion: f.snapshot.ProfileInitialURLVersion,
		BrowserShutdownVersion:   f.snapshot.BrowserShutdownVersion, SessionAuthVersion: f.snapshot.SessionAuthVersion,
		Records: []sealskin.RuntimeRecord{{SessionID: response.SessionID, AppID: request.ApplicationID,
			NetworkPolicyID: request.NetworkPolicyID, NetworkPolicySHA256: request.NetworkPolicySHA256,
			ProfileID: request.ProfileID, OperationID: request.OperationID, Phase: "running", InstanceIDs: []string{instance},
			LaunchContext: &sealskin.LaunchContext{Type: "url", Value: request.URL}}},
		Workers: []sealskin.RuntimeWorker{{InstanceID: instance, SessionID: response.SessionID, AppID: request.ApplicationID,
			NetworkPolicyID: request.NetworkPolicyID, NetworkPolicySHA256: request.NetworkPolicySHA256,
			ProfileID: request.ProfileID, OperationID: request.OperationID, Status: "running", Owned: true, Managed: true, Recorded: true}},
	}
	if request.NetworkPolicyID != "" {
		for _, kind := range []string{"reservation", "internal", "egress", "relay", "guard"} {
			f.snapshot.Resources = append(f.snapshot.Resources, sealskin.RuntimeResource{ID: kind + "-1", Kind: kind, Owned: true, Recorded: true,
				Status: "running", ProfileID: request.ProfileID, OperationID: request.OperationID, AppID: request.ApplicationID,
				PolicyID: request.NetworkPolicyID, PolicySHA256: request.NetworkPolicySHA256})
		}
	}
	return response, nil
}

func (f *lifecycleFake) InspectHome(_ context.Context, home string) (sealskin.HomeRuntime, error) {
	f.runtimeMu.Lock()
	defer f.runtimeMu.Unlock()
	if f.inspectErr != nil {
		return sealskin.HomeRuntime{}, f.inspectErr
	}
	if f.snapshot.HomeName != "" && home != "" && f.snapshot.HomeName != home {
		// Inventories are per Home; another Home is empty in this fake.
		other := emptyRuntime()
		other.HomeName = home
		return other, nil
	}
	snapshot := f.snapshot
	snapshot.Records = append([]sealskin.RuntimeRecord{}, f.snapshot.Records...)
	snapshot.Workers = append([]sealskin.RuntimeWorker{}, f.snapshot.Workers...)
	if f.snapshot.Resources != nil {
		snapshot.Resources = append([]sealskin.RuntimeResource{}, f.snapshot.Resources...)
	}
	return snapshot, nil
}

// ObserveHome derives a healthy observation from the current snapshot; tests
// mutate it through observeHook to simulate exited browsers or failed relays.
func (f *lifecycleFake) ObserveHome(ctx context.Context, home string, upstream bool) (sealskin.HomeHealth, error) {
	if f.observeBlock != nil {
		select {
		case <-f.observeBlock:
		case <-ctx.Done():
			return sealskin.HomeHealth{}, ctx.Err()
		}
	}
	snapshot, err := f.InspectHome(ctx, home)
	f.runtimeMu.Lock()
	defer f.runtimeMu.Unlock()
	f.observeCalls++
	f.observeUpstream = append(f.observeUpstream, upstream)
	if f.observeErr != nil {
		return sealskin.HomeHealth{}, f.observeErr
	}
	if err != nil {
		return sealskin.HomeHealth{}, err
	}
	health := sealskin.HomeHealth{Version: 1, HomeName: home, ObservedAt: 1_700_000_000, Runtime: snapshot, Workers: []sealskin.WorkerHealth{}}
	for _, worker := range snapshot.Workers {
		health.Workers = append(health.Workers, sealskin.WorkerHealth{InstanceID: worker.InstanceID, SessionID: worker.SessionID,
			Owned: worker.Owned, Recorded: worker.Recorded, Status: worker.Status, StartedAt: "2026-09-13T00:00:00Z",
			Environment: sealskin.EnvironmentIdentity{ID: "env-test-r1", ArtifactSHA256: strings.Repeat("1", 64)},
			Processes:   sealskin.ProcessSummary{Total: 5, BrowserMain: 1, BrowserChild: 2, DisplayServer: []string{"Xvfb"}, Streamer: 1},
			Display:     sealskin.ObservedCheck{Status: "pass", Code: "DISPLAY_ENDPOINT_OK", LatencyMS: 2}})
	}
	for _, resource := range snapshot.Resources {
		if resource.Kind == "reservation" {
			namespace := true
			health.Network = &sealskin.NetworkHealth{Phase: resource.Status, PolicyID: resource.PolicyID, PolicySHA256: resource.PolicySHA256,
				EnforcementVersion: 1, Relay: sealskin.RelayHealth{Container: "running", Status: "pass", Code: "PROXY_RELAY_OK", LatencyMS: 1},
				Guard: sealskin.GuardHealth{Container: "running"}, WorkerNamespace: &namespace}
			if upstream {
				health.Network.Upstream = &sealskin.ObservedCheck{Status: "pass", Code: "PROXY_OK", LatencyMS: 40, MeasuredAt: 1_700_000_000}
			}
		}
	}
	if f.observeHook != nil {
		f.observeHook(&health)
	}
	return health, nil
}

// ResumeHome marks the dormant generation running again unless a failure is
// injected; a failed resume leaves every container exactly as it was.
func (f *lifecycleFake) ResumeHome(_ context.Context, _ string, request sealskin.StopProfileRequest, key string) (sealskin.ResumeResult, error) {
	f.runtimeMu.Lock()
	defer f.runtimeMu.Unlock()
	f.resumeCalls++
	f.resumeKeys = append(f.resumeKeys, key)
	f.resumeRequests = append(f.resumeRequests, request)
	if f.resumeErr != nil {
		return sealskin.ResumeResult{}, f.resumeErr
	}
	if len(f.snapshot.Records) != 1 || len(f.snapshot.Workers) != 1 {
		return sealskin.ResumeResult{}, &sealskin.APIError{StatusCode: 409, Detail: "RESUME_NOT_DORMANT"}
	}
	if !f.resumeKeepDormant {
		f.snapshot.Workers[0].Status = "running"
		for i := range f.snapshot.Resources {
			f.snapshot.Resources[i].Status = "running"
		}
	}
	return sealskin.ResumeResult{Resumed: true, State: "live", SessionID: f.snapshot.Records[0].SessionID,
		InstanceID: f.snapshot.Workers[0].InstanceID, Steps: []string{"relay", "guard", "controller", "probe", "worker", "display", "committed"}}, nil
}

func (f *lifecycleFake) StopHome(ctx context.Context, _ string, request sealskin.StopProfileRequest, key string) error {
	if f.beforeStop != nil {
		f.beforeStop(request, key)
	}
	if f.stopEntered != nil {
		close(f.stopEntered)
		select {
		case <-f.stopRelease:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	f.runtimeMu.Lock()
	defer f.runtimeMu.Unlock()
	f.stopCalls++
	f.stopKeys = append(f.stopKeys, key)
	if !f.keepOnStop {
		resources := f.snapshot.Resources
		f.snapshot = emptyRuntime()
		if f.keepResourcesOnStop {
			f.snapshot.Resources = resources
			for i := range f.snapshot.Resources {
				f.snapshot.Resources[i].Status = "stopping"
			}
		}
		if f.downgradeAfterStop {
			f.snapshot.NetworkRuntimeVersion, f.snapshot.Resources = 0, nil
		}
		f.mu.Lock()
		f.sessions = nil
		f.mu.Unlock()
	}
	if f.postStopErr != nil {
		f.inspectErr = f.postStopErr
	}
	return f.stopErr
}

func lifecycleService(t *testing.T, fake *lifecycleFake, store *state.Store) *Service {
	t.Helper()
	service, err := NewService(fake, store, "https://adapter.example", []Definition{{
		ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com", WaylandMode: false,
	}}, WithLifecycle(fake))
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func newLifecycleService(t *testing.T) (*Service, *state.Store, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service := lifecycleService(t, fake, store)
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	return service, store, fake
}

func TestVerifiedStopPersistsIntentBeforeMutation(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.beforeStop = func(request sealskin.StopProfileRequest, key string) {
		binding, found, err := store.Get("personal")
		if err != nil || !found || binding.Status != state.StatusStopping || binding.StopOperationID == "" || binding.StopIdempotencyKey != key {
			t.Fatalf("stop reached runtime without durable intent: %+v %v", binding, err)
		}
		if binding.OperationID != request.OperationID || binding.SessionID != request.SessionID || request.ProfileID != "personal" {
			t.Fatal("stop lost the expected launch generation")
		}
	}
	result, err := service.Stop(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped || result.Workers != 0 {
		t.Fatalf("result=%+v err=%v", result, err)
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil || fake.stopCalls != 1 {
		t.Fatalf("repeated stop: calls=%d err=%v", fake.stopCalls, err)
	}
}

func TestFalseStopSuccessDoesNotReleaseProfile(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.keepOnStop = true
	result, err := service.Stop(context.Background(), "personal")
	if !errors.Is(err, ErrStopUnconfirmed) || result.Status != state.StatusStopping {
		t.Fatalf("false success result=%+v err=%v", result, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOperationRunning) {
		t.Fatalf("Ensure while stopping: %v", err)
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusStopping || fake.launches != 1 {
		t.Fatal("unconfirmed stop released the Home")
	}
}

func TestPendingStopSurvivesServiceRestartAndReusesKey(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.keepOnStop, fake.stopErr = true, errors.New("docker stop failed")
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrStopUnconfirmed) {
		t.Fatal(err)
	}
	first, _, _ := store.Get("personal")
	fake.keepOnStop, fake.stopErr = false, nil
	restarted := lifecycleService(t, fake, store)
	result, err := restarted.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped {
		t.Fatalf("restart reconciliation=%+v err=%v", result, err)
	}
	if len(fake.stopKeys) != 2 || fake.stopKeys[0] != fake.stopKeys[1] || fake.stopKeys[1] != first.StopIdempotencyKey {
		t.Fatal("retry lost the durable stop key")
	}
}

func TestLostStopResponseCanCompleteOnlyAfterFreshAbsence(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.stopErr = &sealskin.AmbiguousMutationError{Operation: "stop", Cause: errors.New("EOF")}
	result, err := service.Stop(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped {
		t.Fatalf("verified absence after lost response=%+v err=%v", result, err)
	}
}

func TestPostStopInventoryFailureKeepsPendingState(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.postStopErr = errors.New("Docker unavailable")
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrStopUnconfirmed) {
		t.Fatal(err)
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusStopping {
		t.Fatal("missing inventory was treated as absence")
	}
	fake.inspectErr = nil
	result, err := service.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped || fake.stopCalls != 1 {
		t.Fatalf("completion reconciliation=%+v err=%v", result, err)
	}
}

func TestInventoryUnavailableDoesNotStopOrLaunch(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.inspectErr = errors.New("Docker unavailable")
	if _, err := service.Stop(context.Background(), "personal"); err == nil {
		t.Fatal("stop ignored inventory failure")
	}
	if _, err := service.Ensure(context.Background(), "personal"); err == nil {
		t.Fatal("Ensure ignored inventory failure")
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusRunning || fake.stopCalls != 0 || fake.launches != 1 {
		t.Fatal("unavailable inventory caused a mutation")
	}
}

func TestLabeledOrphanQuarantinedThenExplicitlyRecovered(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	fake.snapshot.Records = []sealskin.RuntimeRecord{}
	fake.snapshot.Workers[0].Recorded = false
	fake.sessions = nil
	result, err := service.Reconcile(context.Background(), "personal")
	if !errors.Is(err, ErrOwnershipUnknown) || result.Orphans != 1 || fake.stopCalls != 0 {
		t.Fatalf("orphan reconciliation=%+v err=%v", result, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.launches != 1 {
		t.Fatal("orphan caused a duplicate launch")
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusStopped || fake.stopCalls != 1 {
		t.Fatal("owned orphan was not recovered")
	}
}

func TestUnlabeledOrphanIsNeverStopped(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.snapshot.Records = []sealskin.RuntimeRecord{}
	fake.snapshot.Workers[0].Owned = false
	fake.snapshot.Workers[0].Managed = false
	fake.snapshot.Workers[0].Recorded = false
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
		t.Fatal("unproven container was stopped")
	}
}

func TestOlderOperationCannotStopNewerWorker(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.snapshot.Records[0].OperationID = strings.Repeat("e", 32)
	fake.snapshot.Workers[0].OperationID = strings.Repeat("e", 32)
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
		t.Fatal("stale generation reached stop")
	}
}

func TestLegacySessionCanBeReconciledAndStoppedByExactMarker(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.snapshot.Records[0].ProfileID, fake.snapshot.Records[0].OperationID = "", ""
	fake.snapshot.Workers[0].ProfileID, fake.snapshot.Workers[0].OperationID = "", ""
	fake.snapshot.Workers[0].Managed = false
	if result, err := service.Reconcile(context.Background(), "personal"); err != nil || result.Status != state.StatusRunning {
		t.Fatalf("legacy reconcile=%+v err=%v", result, err)
	}
	if _, err := service.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
}

func TestUnexpectedContainerSharingHomeBlocksStop(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.snapshot.Workers = append(fake.snapshot.Workers, sealskin.RuntimeWorker{InstanceID: strings.Repeat("f", 64), Status: "running"})
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
		t.Fatal("foreign Home occupant was ignored")
	}
}

func TestReconcileConfirmedDisappearanceWithoutLaunching(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.snapshot = emptyRuntime()
	fake.sessions = nil
	result, err := service.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped || fake.launches != 1 || fake.stopCalls != 0 {
		t.Fatalf("disappearance result=%+v err=%v", result, err)
	}
}

func TestUnacknowledgedEmptyLaunchRemainsUnknown(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	if err := store.Update("personal", func(current *state.Binding) (*state.Binding, error) {
		current.Status, current.SessionID = state.StatusUnknown, ""
		return current, nil
	}); err != nil {
		t.Fatal(err)
	}
	fake.snapshot = emptyRuntime()
	fake.sessions = nil
	if _, err := service.Reconcile(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatal("ambiguous create was released")
	}
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatal("stop assumed an ambiguous create did not run")
	}
}

func TestLaunchJournalSettlesAmbiguousCreateOnlyWhenInventoryIsEmpty(t *testing.T) {
	service, store, fake := newLifecycleService(t)
	if err := store.Update("personal", func(current *state.Binding) (*state.Binding, error) {
		current.Status, current.SessionID = state.StatusUnknown, ""
		return current, nil
	}); err != nil {
		t.Fatal(err)
	}
	binding, _, _ := store.Get("personal")
	fake.snapshot = emptyRuntime()
	fake.snapshot.LaunchJournalVersion = 1
	fake.sessions = nil
	// A pending or failed journal still reserves the Home.
	fake.snapshot.Resources = []sealskin.RuntimeResource{{ID: binding.OperationID, Kind: "launch", Owned: true, Recorded: true, Status: "pending",
		ProfileID: "personal", OperationID: binding.OperationID, AppID: "firefox"}}
	result, err := service.Reconcile(context.Background(), "personal")
	if !errors.Is(err, ErrOwnershipUnknown) || result.LaunchPhase != "pending" {
		t.Fatalf("pending journal must keep the Home reserved: %+v %v", result, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.launches != 1 {
		t.Fatal("a journaled launch allowed a second launch")
	}
	fake.snapshot.Resources = []sealskin.RuntimeResource{}
	result, err = service.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped {
		t.Fatalf("empty journaled inventory should settle as stopped: %+v %v", result, err)
	}
	if fake.stopCalls != 0 {
		t.Fatal("settling an ambiguous create must not call stop")
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.launches != 2 {
		t.Fatalf("settled Profile must launch again: err=%v launches=%d", err, fake.launches)
	}
}

func TestEnsureWaitsUntilStopHasBeenVerified(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	fake.stopEntered, fake.stopRelease = make(chan struct{}), make(chan struct{})
	stopped, ensured := make(chan error, 1), make(chan error, 1)
	go func() { _, err := service.Stop(context.Background(), "personal"); stopped <- err }()
	<-fake.stopEntered
	go func() { _, err := service.Ensure(context.Background(), "personal"); ensured <- err }()
	select {
	case err := <-ensured:
		t.Fatalf("Ensure escaped a pending stop: %v", err)
	default:
	}
	close(fake.stopRelease)
	if err := <-stopped; err != nil {
		t.Fatal(err)
	}
	if err := <-ensured; err != nil {
		t.Fatal(err)
	}
	if fake.launches != 2 || fake.stopCalls != 1 {
		t.Fatal("unexpected launch/stop count")
	}
}

func TestConcurrentStopsRemoveOnlyOnce(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	results := make(chan error, 20)
	for range 20 {
		go func() { _, err := service.Stop(context.Background(), "personal"); results <- err }()
	}
	for range 20 {
		if err := <-results; err != nil {
			t.Fatal(err)
		}
	}
	if fake.stopCalls != 1 {
		t.Fatal("repeated stop reached Docker again")
	}
}

func TestConfigurationDriftAndUncheckedResetAreRejected(t *testing.T) {
	service, _, fake := newLifecycleService(t)
	definition := service.profiles["personal"]
	definition.HomeName = "another-home"
	service.profiles["personal"] = definition
	if _, err := service.Stop(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) || fake.stopCalls != 0 {
		t.Fatal("configuration drift was accepted")
	}
	if err := service.ResetUnknown("personal"); err == nil {
		t.Fatal("unchecked reset remained enabled")
	}
}

func TestProfileDefinitionsCannotShareHome(t *testing.T) {
	_, store, fake := newLifecycleService(t)
	_, err := NewService(fake, store, "https://adapter.example", []Definition{
		{ID: "one", HomeName: "shared", ApplicationID: "firefox", StartURL: "https://example.com"},
		{ID: "two", HomeName: "shared", ApplicationID: "firefox", StartURL: "https://example.com"},
	})
	if err == nil {
		t.Fatal("shared Profile Home was accepted")
	}
}
