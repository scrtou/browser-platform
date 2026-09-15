package profile

import (
	"context"
	"testing"
	"time"

	"browser-platform/adapter/internal/state"
)

func TestDisplayAuthorizationOnlyReadsCurrentJournalAndDoesNotWaitForLifecycle(t *testing.T) {
	fake := &fakeOrchestrator{}
	service, store := newTestService(t, fake)
	initial := state.Binding{Status: state.StatusRunning, SessionID: "session-1", OperationID: "operation-1",
		IdempotencyKey: "idempotency-1", BootstrapURL: "https://entry.test/bootstrap/personal/operation-1",
		HomeName: "personal", ApplicationID: "firefox"}
	save := func(value state.Binding) {
		t.Helper()
		if err := store.Update("personal", func(*state.Binding) (*state.Binding, error) { return &value, nil }); err != nil {
			t.Fatal(err)
		}
	}
	save(initial)
	before, _, _ := store.Get("personal")
	lock := service.profileLock("personal")
	lock.Lock()
	result := make(chan error, 1)
	go func() { result <- service.CheckDisplaySession(context.Background(), "personal", "session-1") }()
	select {
	case err := <-result:
		lock.Unlock()
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		lock.Unlock()
		t.Fatal("display authorization waited for a long lifecycle operation")
	}
	after, _, _ := store.Get("personal")
	if before != after || fake.launches != 0 || len(fake.homes) != 0 {
		t.Fatal("authorization mutated business state")
	}
	for _, mutate := range []func(*state.Binding){
		func(b *state.Binding) {
			b.Status = state.StatusStopping
			b.StopOperationID = "stop"
			b.StopIdempotencyKey = "stop-key"
		},
		func(b *state.Binding) { b.ResumeIdempotencyKey = "resume-key" },
		func(b *state.Binding) { b.SessionID = "session-2" },
		func(b *state.Binding) { b.HomeName = "other-home" },
		func(b *state.Binding) { b.ApplicationID = "other-app" },
	} {
		changed := initial
		mutate(&changed)
		save(changed)
		if service.CheckDisplaySession(context.Background(), "personal", "session-1") == nil {
			t.Fatal("mismatched binding authorized display")
		}
	}
	save(initial)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if service.CheckDisplaySession(ctx, "personal", "session-1") == nil {
		t.Fatal("cancelled authorization accepted")
	}
}
