package profile

import (
	"context"
	"errors"
	"path/filepath"
	"sync"
	"testing"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

type fakeOrchestrator struct {
	mu             sync.Mutex
	homes          []string
	sessions       []sealskin.Session
	launches       int
	launchErr      error
	addBeforeError bool
}

func (f *fakeOrchestrator) ListSessions(context.Context) ([]sealskin.Session, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]sealskin.Session(nil), f.sessions...), nil
}

func (f *fakeOrchestrator) LaunchURL(_ context.Context, request sealskin.LaunchURLRequest, _ string) (sealskin.LaunchResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.launches++
	session := sealskin.Session{
		SessionID: "session-1", SessionURL: "/session-1/?access_token=secret",
		AppID:         request.ApplicationID,
		LaunchContext: &sealskin.LaunchContext{Type: "url", Value: request.URL},
	}
	if f.launchErr == nil || f.addBeforeError {
		f.sessions = append(f.sessions, session)
	}
	if f.launchErr != nil {
		return sealskin.LaunchResponse{}, f.launchErr
	}
	return sealskin.LaunchResponse{SessionID: session.SessionID, SessionURL: session.SessionURL}, nil
}

func (f *fakeOrchestrator) ListHomeDirectories(context.Context) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.homes...), nil
}

func (f *fakeOrchestrator) CreateHomeDirectory(_ context.Context, name, _ string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.homes = append(f.homes, name)
	return nil
}

func newTestService(t *testing.T, orchestrator *fakeOrchestrator) (*Service, *state.Store) {
	t.Helper()
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(orchestrator, store, "https://adapter.example", []Definition{{
		ID: "personal", ApplicationID: "firefox", HomeName: "personal",
		StartURL: "https://example.com/start", WaylandMode: true,
	}})
	if err != nil {
		t.Fatal(err)
	}
	return service, store
}

func TestEnsureConcurrentCallsLaunchOnce(t *testing.T) {
	orchestrator := &fakeOrchestrator{}
	service, _ := newTestService(t, orchestrator)

	const callers = 20
	results := make(chan sealskin.Session, callers)
	errorsFound := make(chan error, callers)
	var group sync.WaitGroup
	group.Add(callers)
	for range callers {
		go func() {
			defer group.Done()
			session, err := service.Ensure(context.Background(), "personal")
			results <- session
			errorsFound <- err
		}()
	}
	group.Wait()
	close(results)
	close(errorsFound)
	for err := range errorsFound {
		if err != nil {
			t.Fatalf("Ensure: %v", err)
		}
	}
	for session := range results {
		if session.SessionID != "session-1" {
			t.Fatalf("session ID = %q", session.SessionID)
		}
	}
	orchestrator.mu.Lock()
	defer orchestrator.mu.Unlock()
	if orchestrator.launches != 1 {
		t.Fatalf("launches = %d, want 1", orchestrator.launches)
	}
}

func TestEnsureReconcilesLostLaunchResponse(t *testing.T) {
	orchestrator := &fakeOrchestrator{
		launchErr:      &sealskin.AmbiguousMutationError{Operation: "launch", Cause: errors.New("EOF")},
		addBeforeError: true,
	}
	service, store := newTestService(t, orchestrator)
	session, err := service.Ensure(context.Background(), "personal")
	if err != nil {
		t.Fatal(err)
	}
	if session.SessionID != "session-1" {
		t.Fatalf("session = %+v", session)
	}
	binding, found, err := store.Get("personal")
	if err != nil || !found {
		t.Fatalf("binding: found=%v err=%v", found, err)
	}
	if binding.Status != state.StatusRunning || binding.SessionID != "session-1" {
		t.Fatalf("binding = %+v", binding)
	}
}

func TestEnsureDoesNotRetryAmbiguousLaunch(t *testing.T) {
	orchestrator := &fakeOrchestrator{
		launchErr: &sealskin.AmbiguousMutationError{Operation: "launch", Cause: errors.New("EOF")},
	}
	service, store := newTestService(t, orchestrator)
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatalf("first Ensure error = %v", err)
	}
	binding, found, err := store.Get("personal")
	if err != nil || !found || binding.Status != state.StatusUnknown {
		t.Fatalf("binding after ambiguity = %+v found=%v err=%v", binding, found, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatalf("second Ensure error = %v", err)
	}
	orchestrator.mu.Lock()
	defer orchestrator.mu.Unlock()
	if orchestrator.launches != 1 {
		t.Fatalf("ambiguous launch was repeated: launches=%d", orchestrator.launches)
	}
}

func TestRunningBindingDisappearanceBecomesUnknown(t *testing.T) {
	orchestrator := &fakeOrchestrator{}
	service, store := newTestService(t, orchestrator)
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	orchestrator.mu.Lock()
	orchestrator.sessions = nil
	orchestrator.mu.Unlock()
	if _, err := service.Ensure(context.Background(), "personal"); !errors.Is(err, ErrOwnershipUnknown) {
		t.Fatalf("Ensure error = %v", err)
	}
	binding, _, err := store.Get("personal")
	if err != nil {
		t.Fatal(err)
	}
	if binding.Status != state.StatusUnknown {
		t.Fatalf("status = %q, want unknown", binding.Status)
	}
	orchestrator.mu.Lock()
	defer orchestrator.mu.Unlock()
	if orchestrator.launches != 1 {
		t.Fatalf("missing running session caused relaunch: %d", orchestrator.launches)
	}
}

func TestBootstrapTargetRequiresCurrentOperation(t *testing.T) {
	orchestrator := &fakeOrchestrator{}
	service, store := newTestService(t, orchestrator)
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	binding, _, err := store.Get("personal")
	if err != nil {
		t.Fatal(err)
	}
	target, err := service.BootstrapTarget("personal", binding.OperationID)
	if err != nil || target != "https://example.com/start" {
		t.Fatalf("target=%q err=%v", target, err)
	}
	if _, err := service.BootstrapTarget("personal", "old-operation"); !errors.Is(err, ErrProfileNotFound) {
		t.Fatalf("old operation error = %v", err)
	}
}
