package profile

import (
	"context"
	"errors"
	"strings"
	"testing"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

// makeDormant stops every container of the launched generation in place, as a
// daemon or host restart leaves them.
func makeDormant(fake *lifecycleFake) {
	fake.runtimeMu.Lock()
	defer fake.runtimeMu.Unlock()
	for i := range fake.snapshot.Workers {
		fake.snapshot.Workers[i].Status = "exited"
	}
	for i := range fake.snapshot.Resources {
		if fake.snapshot.Resources[i].Kind == "relay" || fake.snapshot.Resources[i].Kind == "guard" {
			fake.snapshot.Resources[i].Status = "exited"
		}
	}
}

func TestDormantGenerationIsResumedByReconcileWithoutLaunch(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	before, _, _ := store.Get("personal")
	makeDormant(fake)
	if _, dormant := dormantRuntime(fake.snapshot); !dormant {
		t.Fatal("test precondition: runtime not classified dormant")
	}
	result, err := service.Reconcile(context.Background(), "personal")
	if err != nil || result.Status != state.StatusRunning || result.SessionID != before.SessionID {
		t.Fatalf("reconcile=%+v err=%v", result, err)
	}
	after, _, _ := store.Get("personal")
	if fake.resumeCalls != 1 || fake.launches != 1 || fake.stopCalls != 0 || after.OperationID != before.OperationID || after.ResumeIdempotencyKey != "" || len(fake.resumeKeys) != 1 || fake.resumeKeys[0] == "" {
		t.Fatalf("resume side effects: resume=%d launches=%d stops=%d binding=%+v", fake.resumeCalls, fake.launches, fake.stopCalls, after)
	}
	request := fake.resumeRequests[0]
	if request.OperationID != before.OperationID || request.SessionID != before.SessionID || request.NetworkPolicyID != "socks-r1" {
		t.Fatalf("resume request lost generation identity: %+v", request)
	}
	if _, live := liveRuntime(fake.snapshot); !live {
		t.Fatal("resumed runtime is not live")
	}
}

func TestEntryResumesDormantGenerationInsteadOfUnknown(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	before, _, _ := store.Get("personal")
	makeDormant(fake)
	session, err := service.Ensure(context.Background(), "personal")
	if err != nil || session.SessionID != before.SessionID {
		t.Fatalf("entry after dormant: session=%+v err=%v", session, err)
	}
	if fake.launches != 1 || fake.resumeCalls != 1 {
		t.Fatalf("entry launched or skipped resume: launches=%d resume=%d", fake.launches, fake.resumeCalls)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.resumeCalls != 1 {
		t.Fatalf("live generation must not be resumed again: err=%v resume=%d", err, fake.resumeCalls)
	}
}

func TestResumeFailureKeepsReservationAndStableCode(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	before, _, _ := store.Get("personal")
	makeDormant(fake)
	fake.resumeErr = &sealskin.APIError{StatusCode: 503, Detail: "NETWORK_PROBE_FAILED"}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrResumeFailed) {
		t.Fatalf("entry error=%v", err)
	}
	binding, _, _ := store.Get("personal")
	if binding.Status != state.StatusUnknown || !strings.Contains(binding.LastError, "NETWORK_PROBE_FAILED") || binding.OperationID != before.OperationID {
		t.Fatalf("binding after failed resume=%+v", binding)
	}
	if fake.launches != 1 || fake.stopCalls != 0 || fake.snapshot.Workers[0].Status != "exited" {
		t.Fatal("failed resume mutated the generation")
	}
	first := fake.resumeKeys[0]
	fake.resumeErr = nil
	result, err := service.Resume(context.Background(), "personal")
	if err != nil || result.Status != state.StatusRunning || fake.resumeKeys[1] != first {
		t.Fatalf("retry=%+v err=%v keys=%v", result, err, fake.resumeKeys)
	}
	if binding, _, _ := store.Get("personal"); binding.Status != state.StatusRunning || binding.SessionID != before.SessionID {
		t.Fatalf("binding after retry=%+v", binding)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.launches != 1 {
		t.Fatalf("entry after successful retry: err=%v launches=%d", err, fake.launches)
	}
}

func TestResumeSuccessWithoutLiveInventoryStaysUnknown(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	makeDormant(fake)
	fake.resumeKeepDormant = true
	if _, err := service.Resume(context.Background(), "personal"); !errors.Is(err, ErrResumeFailed) {
		t.Fatalf("resume error=%v", err)
	}
	if binding, _, _ := store.Get("personal"); binding.Status != state.StatusUnknown {
		t.Fatalf("binding=%+v", binding)
	}
}

func TestResumeRefusesNonDormantAndStoppedProfiles(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	if _, err := service.Resume(context.Background(), "personal"); err != nil || fake.resumeCalls != 0 {
		t.Fatalf("live generation resume should be a no-op: err=%v calls=%d", err, fake.resumeCalls)
	}
	makeDormant(fake)
	fake.snapshot.Workers[0].Recorded = false
	fake.snapshot.Records = []sealskin.RuntimeRecord{}
	if _, err := service.Resume(context.Background(), "personal"); !errors.Is(err, ErrNotDormant) && !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatalf("orphan resume error=%v", err)
	}
	if fake.resumeCalls != 0 {
		t.Fatal("orphan was resumed")
	}
	stopped, _, fake2 := newNetworkService(t, true)
	if _, err := stopped.Stop(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if _, err := stopped.Resume(context.Background(), "personal"); !errors.Is(err, ErrNotDormant) || fake2.resumeCalls != 0 {
		t.Fatalf("stopped profile resume error=%v", err)
	}
}

func TestDormantClassificationRequiresCompleteAllocation(t *testing.T) {
	_, _, fake := newNetworkService(t, true)
	makeDormant(fake)
	if _, ok := dormantRuntime(fake.snapshot); !ok {
		t.Fatal("complete dormant generation not recognized")
	}
	partial := fake.snapshot
	partial.Resources = append([]sealskin.RuntimeResource{}, fake.snapshot.Resources[:4]...)
	if _, ok := dormantRuntime(partial); ok {
		t.Fatal("incomplete allocation classified dormant")
	}
	probing := fake.snapshot
	probing.Resources = append(append([]sealskin.RuntimeResource{}, fake.snapshot.Resources...), sealskin.RuntimeResource{Kind: "probe", ID: "probe-1", Owned: true, Status: "exited"})
	if _, ok := dormantRuntime(probing); ok {
		t.Fatal("leftover probe classified dormant")
	}
	stopping := fake.snapshot
	stopping.Records = []sealskin.RuntimeRecord{fake.snapshot.Records[0]}
	stopping.Records[0].Phase = "stopping"
	if _, ok := dormantRuntime(stopping); ok {
		t.Fatal("stopping record classified dormant")
	}
	_, _, legacyFake, _ := newHealthService(t)
	makeDormant(legacyFake)
	if _, ok := dormantRuntime(legacyFake.snapshot); !ok {
		t.Fatal("legacy dormant generation not recognized")
	}
	legacyFake.snapshot.Resources = []sealskin.RuntimeResource{{Kind: "relay", ID: "x", Owned: true}}
	if _, ok := dormantRuntime(legacyFake.snapshot); ok {
		t.Fatal("legacy generation with resources classified dormant")
	}
}

func TestHealthReportsDormantWorkerWithResumeHint(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	service.now = fixedClock()
	makeDormant(fake)
	fake.observeHook = func(h *sealskin.HomeHealth) {
		h.Workers[0].Status = "exited"
		h.Network.Relay = sealskin.RelayHealth{Container: "exited", Status: "fail", Code: "PROXY_RELAY_NOT_RUNNING"}
		h.Network.Guard.Container = "exited"
	}
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if got := check(t, report, "worker"); got.Code != "WORKER_DORMANT" || got.Status != CheckFail {
		t.Fatalf("worker=%+v", got)
	}
	if report.Overall != OverallUnhealthy || report.Recovery == nil || report.Recovery.Code != "WORKER_DORMANT" || report.Recovery.Blocking {
		t.Fatalf("report=%+v recovery=%+v", report.Overall, report.Recovery)
	}
	if fake.resumeCalls != 0 || fake.launches != 1 {
		t.Fatal("health report triggered resume or launch")
	}
}

func TestEachDormantEpisodeUsesAFreshKeyWhileRetriesReuseIt(t *testing.T) {
	service, store, fake := newNetworkService(t, true)
	makeDormant(fake)
	fake.resumeErr = &sealskin.APIError{StatusCode: 503, Detail: "NETWORK_PROBE_FAILED"}
	if _, err := service.Reconcile(context.Background(), "personal"); !errors.Is(err, ErrResumeFailed) {
		t.Fatalf("first attempt error=%v", err)
	}
	fake.resumeErr = nil
	if _, err := service.Resume(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if fake.resumeKeys[0] != fake.resumeKeys[1] {
		t.Fatal("a retry within one dormant episode must reuse the durable key")
	}
	if binding, _, _ := store.Get("personal"); binding.ResumeIdempotencyKey != "" || binding.Status != state.StatusRunning {
		t.Fatalf("running binding must clear the resume key: %+v", binding)
	}
	makeDormant(fake)
	if _, err := service.Reconcile(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	if fake.resumeKeys[2] == fake.resumeKeys[1] {
		t.Fatal("a new dormant episode reused the previous key; SealSkin would replay the stale success")
	}
	fake.resumeKeepDormant = true
	makeDormant(fake)
	if _, err := service.Reconcile(context.Background(), "personal"); !errors.Is(err, ErrResumeFailed) {
		t.Fatalf("stale replay must not be trusted: %v", err)
	}
	if binding, _, _ := store.Get("personal"); !strings.Contains(binding.LastError, "RESUME_INVENTORY_MISMATCH") {
		t.Fatalf("binding=%+v", binding)
	}
}

func TestHealthReportsResumeFailureCode(t *testing.T) {
	service, _, fake := newNetworkService(t, true)
	service.now = fixedClock()
	makeDormant(fake)
	fake.resumeErr = &sealskin.APIError{StatusCode: 503, Detail: "NETWORK_PROBE_FAILED"}
	if _, err := service.Reconcile(context.Background(), "personal"); !errors.Is(err, ErrResumeFailed) {
		t.Fatalf("reconcile error=%v", err)
	}
	report, err := service.Health(context.Background(), "personal", HealthOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if report.Overall != OverallUnknown || check(t, report, "worker").Code != "NETWORK_PROBE_FAILED" || report.Recovery == nil || report.Recovery.Code != "NETWORK_PROBE_FAILED" || report.Recovery.Blocking {
		t.Fatalf("report=%+v recovery=%+v", report.Checks, report.Recovery)
	}
}
