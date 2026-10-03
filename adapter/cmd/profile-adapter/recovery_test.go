package main

import (
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

type unusedOrchestrator struct{ profile.Orchestrator }
type startupRecorder struct {
	*profile.Service
	ids      []string
	contexts []context.Context
	t        *testing.T
}

func (r *startupRecorder) Reconcile(ctx context.Context, id string) (profile.LifecycleResult, error) {
	r.ids = append(r.ids, id)
	r.contexts = append(r.contexts, ctx)
	deadline, ok := ctx.Deadline()
	if !ok || time.Until(deadline) > sealskin.LongOperationTimeout+15*time.Second || ctx.Err() != nil {
		r.t.Fatal("missing per-profile recovery budget")
	}
	if id == "dynamic-a" {
		return profile.LifecycleResult{}, errors.New("retained unknown generation")
	}
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusStopped}, nil
}
func TestStartupUsesPersistedDirectoryAndContinuesAfterFailure(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "profiles.json")
	var rows []map[string]any
	for _, id := range []string{"dynamic-b", "retired", "dynamic-a"} {
		status := "ready"
		if id == "retired" {
			status = "deleted"
		}
		rows = append(rows, map[string]any{"id": id, "application_id": "firefox", "home_name": id, "start_url": "https://example.com/", "revision": 1, "status": status})
	}
	raw, _ := json.Marshal(map[string]any{"version": 1, "revision": 1, "browsers": rows})
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	store, err := state.NewStore(filepath.Join(root, "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := profile.NewService(&unusedOrchestrator{}, store, "https://entry.example.test", []profile.Definition{{ID: "old-seed", ApplicationID: "firefox", HomeName: "old-seed", StartURL: "https://example.com/"}}, profile.WithDirectory(path))
	if err != nil {
		t.Fatal(err)
	}
	recorder := &startupRecorder{Service: service, t: t}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	reconcileAtStartup(context.Background(), recorder, logger)
	if !reflect.DeepEqual(recorder.ids, []string{"dynamic-a", "dynamic-b"}) {
		t.Fatalf("wrong recovery subjects: %v", recorder.ids)
	}
	for _, ctx := range recorder.contexts {
		if ctx.Err() != context.Canceled {
			t.Fatal("recovery context not released")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	reconcileAtStartup(ctx, recorder, logger)
	if len(recorder.ids) != 2 {
		t.Fatal("shutdown started another recovery")
	}
}

type retryStartup struct {
	contexts []context.Context
	errors   []error
	statuses []state.Status
	onCall   func()
}

func (r *retryStartup) ProfileIDs() []string { return []string{"dynamic"} }
func (r *retryStartup) Reconcile(ctx context.Context, id string) (profile.LifecycleResult, error) {
	i := len(r.contexts)
	r.contexts = append(r.contexts, ctx)
	if r.onCall != nil {
		r.onCall()
	}
	return profile.LifecycleResult{ProfileID: id, Status: r.statuses[i]}, r.errors[i]
}

func TestStartupResumeRetryKeepsBudgetAndStopsOnTerminalResult(t *testing.T) {
	for _, tc := range []struct {
		name     string
		errors   []error
		statuses []state.Status
	}{
		{"late guard readiness", []error{profile.ErrResumeFailed, nil}, []state.Status{state.StatusUnknown, state.StatusRunning}},
		{"permanent resume failure", []error{profile.ErrResumeFailed, profile.ErrResumeFailed, profile.ErrResumeFailed}, []state.Status{state.StatusUnknown, state.StatusUnknown, state.StatusUnknown}},
		{"unknown ownership", []error{profile.ErrOwnershipUnknown}, []state.Status{state.StatusUnknown}},
		{"stop intent wins", []error{profile.ErrResumeFailed, nil}, []state.Status{state.StatusUnknown, state.StatusStopped}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
			defer cancel()
			r := &retryStartup{errors: tc.errors, statuses: tc.statuses}
			result, err := reconcileStartupProfile(ctx, r, "dynamic", 0)
			if len(r.contexts) != len(tc.errors) || !errors.Is(err, tc.errors[len(tc.errors)-1]) || result.Status != tc.statuses[len(tc.statuses)-1] {
				t.Fatalf("wrong recovery result: calls=%d result=%+v error=%v", len(r.contexts), result, err)
			}
			for _, used := range r.contexts {
				if used != ctx {
					t.Fatal("retry reset the original recovery context")
				}
			}
		})
	}
}

func TestStartupResumeRetryHonorsCancellationAndExpiry(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	r := &retryStartup{errors: []error{profile.ErrResumeFailed}, statuses: []state.Status{state.StatusUnknown}, onCall: cancel}
	_, err := reconcileStartupProfile(ctx, r, "dynamic", time.Hour)
	if !errors.Is(err, context.Canceled) || len(r.contexts) != 1 {
		t.Fatalf("cancellation started another attempt: calls=%d error=%v", len(r.contexts), err)
	}
	expired, stop := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer stop()
	r = &retryStartup{}
	_, err = reconcileStartupProfile(expired, r, "dynamic", 0)
	if !errors.Is(err, context.DeadlineExceeded) || len(r.contexts) != 0 {
		t.Fatal("expired recovery started work")
	}
}

func TestStartupContinuesAnInterruptedResume(t *testing.T) {
	r := &retryStartup{errors: []error{profile.ErrResumeFailed, nil}, statuses: []state.Status{state.StatusUnknown, state.StatusRunning}}
	reconcileAtStartup(context.Background(), r, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if len(r.contexts) != 2 || r.contexts[0] != r.contexts[1] || r.contexts[0].Err() != context.Canceled {
		t.Fatal("startup did not complete the original bounded recovery")
	}
}
