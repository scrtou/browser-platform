package control

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/state"
)

type fakeService struct {
	err           error
	healthErr     error
	healthOptions []profile.HealthOptions
}

func (f *fakeService) Inspect(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusRunning, Workers: 1}, f.err
}
func (f *fakeService) Stop(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusStopped}, f.err
}
func (f *fakeService) Reconcile(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusStopped}, f.err
}
func (f *fakeService) Resume(_ context.Context, id string) (profile.LifecycleResult, error) {
	return profile.LifecycleResult{ProfileID: id, Status: state.StatusRunning}, f.err
}
func (f *fakeService) Health(_ context.Context, id string, opts profile.HealthOptions) (profile.HealthReport, error) {
	f.healthOptions = append(f.healthOptions, opts)
	if f.healthErr != nil {
		return profile.HealthReport{}, f.healthErr
	}
	return profile.HealthReport{Version: 1, ProfileID: id, Overall: profile.OverallHealthy, Binding: profile.HealthBinding{OperationID: "op-secret", SessionID: "sid"}}, f.err
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
	for _, action := range []string{"inspect", "stop", "reconcile", "resume"} {
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

func TestResumeReadinessErrorsRetainActualStateAndDoNotClaimStopped(t *testing.T) {
	for _, tc := range []struct {
		name  string
		err   error
		retry string
	}{
		{"resume-unverified", profile.ErrResumeFailed, ""},
		{"coherence-pending", profile.ErrCoherenceBlocked, "10"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			service := &fakeService{err: fmt.Errorf("%w: backend-private-detail", tc.err)}
			recorder := httptest.NewRecorder()
			Handler(service).ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/profiles/personal/resume", nil))
			var response reply
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
				t.Fatal(err)
			}
			if recorder.Code != http.StatusServiceUnavailable || recorder.Header().Get("Retry-After") != tc.retry ||
				response.Result.Status != state.StatusRunning || response.Error == "" ||
				strings.Contains(response.Error, "remains stopped") || strings.Contains(response.Error, "backend-private-detail") {
				t.Fatalf("readiness response=%+v status=%d retry=%q", response, recorder.Code, recorder.Header().Get("Retry-After"))
			}
		})
	}
}

func TestControlHealthCommandsUseCacheForceAndCachedOnly(t *testing.T) {
	path := filepath.Join(t.TempDir(), "control.sock")
	listener, err := Listen(path)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	service := &fakeService{}
	server := &http.Server{Handler: Handler(service)}
	defer server.Close()
	go server.Serve(listener) //nolint:errcheck
	report, err := HealthCommand(context.Background(), path, "health", "personal")
	if err != nil || report.ProfileID != "personal" || report.Binding.OperationID != "op-secret" {
		t.Fatalf("health via private socket keeps the full report: %+v %v", report, err)
	}
	if _, err := HealthCommand(context.Background(), path, "probe", "personal"); err != nil {
		t.Fatal(err)
	}
	if len(service.healthOptions) != 2 || service.healthOptions[0].Force || !service.healthOptions[1].Force || service.healthOptions[1].Wait == 0 {
		t.Fatalf("unexpected options %+v", service.healthOptions)
	}
	if _, err := HealthCommand(context.Background(), path, "delete", "personal"); err == nil {
		t.Fatal("unsupported health command accepted")
	}
	service.healthErr = profile.ErrHealthThrottled
	if _, err := HealthCommand(context.Background(), path, "probe", "personal"); err == nil || !strings.Contains(err.Error(), "HTTP 429") {
		t.Fatalf("throttled probe: %v", err)
	}
	service.healthErr = profile.ErrHealthPending
	if _, err := HealthCommand(context.Background(), path, "health", "personal"); err == nil || !strings.Contains(err.Error(), "HTTP 503") {
		t.Fatalf("pending report: %v", err)
	}
}
