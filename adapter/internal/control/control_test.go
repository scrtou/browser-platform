package control

import (
	"context"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"testing"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/state"
)

type fakeService struct{ err error }

func (f *fakeService) Inspect(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusRunning, Workers: 1}, f.err
}
func (f *fakeService) Stop(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusStopped}, f.err
}
func (f *fakeService) Reconcile(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusStopped}, f.err
}

func TestControlUsesPrivateSocket(t *testing.T) {
	path := filepath.Join(t.TempDir(), "control.sock")
	listener, err := Listen(path)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("socket permissions: %v %v", info, err)
	}
	server := &http.Server{Handler: Handler(&fakeService{})}
	defer server.Close()
	go server.Serve(listener) //nolint:errcheck
	for _, action := range []string{"inspect", "stop", "reconcile"} {
		result, err := Command(context.Background(), path, action, "personal")
		if err != nil || result.ProfileID != "personal" {
			t.Fatalf("%s result=%+v err=%v", action, result, err)
		}
	}
	if extra, err := Listen(path); err == nil {
		extra.Close()
		t.Fatal("replaced an active adapter socket")
	}
}

func TestControlRejectsRegularFilesAndSymlinks(t *testing.T) {
	directory := t.TempDir()
	path := filepath.Join(directory, "not-a-socket")
	if err := os.WriteFile(path, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(directory, "link")
	if err := os.Symlink(path, link); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{path, link} {
		if listener, err := Listen(name); err == nil {
			listener.Close()
			t.Fatal("replaced a non-socket")
		}
	}
	if value, _ := os.ReadFile(path); string(value) != "keep" {
		t.Fatal("overwrote existing data")
	}
}

func TestControlDoesNotReturnBackendSecrets(t *testing.T) {
	path := filepath.Join(t.TempDir(), "control.sock")
	listener, err := Listen(path)
	if err != nil {
		t.Fatal(err)
	}
	server := &http.Server{Handler: Handler(&fakeService{err: errors.New("access_token=private")})}
	defer server.Close()
	go server.Serve(listener) //nolint:errcheck
	_, err = Command(context.Background(), path, "stop", "personal")
	if err == nil || err.Error() != "control command returned HTTP 503: lifecycle operation could not be verified" {
		t.Fatalf("unexpected public error: %v", err)
	}
}
