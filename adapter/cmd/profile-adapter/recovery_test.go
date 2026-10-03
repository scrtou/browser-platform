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
