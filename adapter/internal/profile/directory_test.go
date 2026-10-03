package profile

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/state"
)

func directoryService(t *testing.T, path string, definitions []Definition) (*Service, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(fake, store, "https://adapter.example", definitions, WithLifecycle(fake), WithDirectory(path))
	if err != nil {
		t.Fatal(err)
	}
	return service, fake
}

func TestDirectoryImportsPersistsAndHotUpdates(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "profiles.json")
	seed := []Definition{{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"}}
	service, fake := directoryService(t, path, seed)
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("directory not created privately: %v %v", err, info)
	}
	records := service.Records()
	if len(records) != 1 || records[0].Revision != 1 || records[0].Label != "" || service.ProfileIDs()[0] != "personal" || !service.KnownProfile("personal") || service.KnownProfile("other") {
		t.Fatalf("imported records: %+v", records)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	label, start := "个人", "https://next.example/"
	record, err := service.UpdateBrowser("personal", 1, "root", BrowserPatch{Label: &label, StartURL: &start})
	if err != nil || record.Revision != 2 || record.Label != label || record.StartURL != start || record.UpdatedBy != "root" {
		t.Fatalf("update: %+v %v", record, err)
	}
	if _, err := service.UpdateBrowser("personal", 1, "root", BrowserPatch{Label: &label}); err != ErrRevisionMismatch {
		t.Fatalf("stale revision: %v", err)
	}
	if same, err := service.UpdateBrowser("personal", 2, "root", BrowserPatch{Label: &label}); err != nil || same.Revision != 2 {
		t.Fatalf("no-op update must not bump the revision: %+v %v", same, err)
	}
	bad := "x\n"
	if _, err := service.UpdateBrowser("personal", 2, "root", BrowserPatch{Label: &bad}); err == nil {
		t.Fatal("invalid label accepted")
	}
	badURL := "ftp://nope"
	if _, err := service.UpdateBrowser("personal", 2, "root", BrowserPatch{StartURL: &badURL}); err == nil {
		t.Fatal("invalid start URL accepted")
	}
	if _, err := service.UpdateBrowser("missing", 1, "root", BrowserPatch{Label: &label}); err != ErrProfileNotFound {
		t.Fatalf("unknown: %v", err)
	}
	// The running generation keeps working after the update; the new start
	// URL is what the next bootstrap redirect uses.
	binding, _, _ := service.store.Get("personal")
	if target, err := service.BootstrapTarget("personal", binding.OperationID); err != nil || target != start {
		t.Fatalf("bootstrap after update: %q %v", target, err)
	}
	summary, err := service.Environment(context.Background(), "personal")
	if err != nil || summary.Label != label || summary.StartURL != start || summary.Revision != 2 || !summary.Enabled {
		t.Fatalf("summary after update: %+v %v", summary, err)
	}
	// A second service on the same file reads the persisted record, not the seed.
	again, _ := directoryService(t, path, []Definition{{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"}})
	if records := again.Records(); len(records) != 1 || records[0].Label != label || records[0].Revision != 2 {
		t.Fatalf("persisted record not reloaded: %+v", records)
	}
	if ids, err := DirectoryProfileIDs(path); err != nil || strings.Join(ids, ",") != "personal" {
		t.Fatalf("directory IDs: %v %v", ids, err)
	}
	raw, _ := os.ReadFile(path)
	var file directoryFile
	if json.Unmarshal(raw, &file) != nil || file.Version != 1 || file.Revision != 2 {
		t.Fatalf("file: %s", raw)
	}
	if fake.launches != 1 || fake.stopCalls != 0 {
		t.Fatal("directory changes touched the runtime")
	}
}

func TestDisabledBrowserRefusesLaunchAndReuseButKeepsLifecycle(t *testing.T) {
	path := filepath.Join(t.TempDir(), "profiles.json")
	service, fake := directoryService(t, path, []Definition{{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"}})
	if _, err := service.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	disabled := true
	if _, err := service.UpdateBrowser("personal", 1, "root", BrowserPatch{Disabled: &disabled}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != ErrProfileDisabled {
		t.Fatalf("reuse of a disabled browser: %v", err)
	}
	binding, _, _ := service.store.Get("personal")
	if err := service.CheckDisplaySession(context.Background(), "personal", binding.SessionID); err != nil {
		t.Fatalf("running display must survive disabling: %v", err)
	}
	if report, err := service.Health(context.Background(), "personal", HealthOptions{}); err != nil || report.Overall != OverallDegraded || check(t, report, "egress").Code != "EGRESS_NOT_CONFIGURED" {
		t.Fatalf("health of a disabled running browser: %+v %v", report, err)
	}
	result, err := service.Stop(context.Background(), "personal")
	if err != nil || result.Status != state.StatusStopped {
		t.Fatalf("stop of a disabled browser: %+v %v", result, err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != ErrProfileDisabled || fake.launches != 1 {
		t.Fatalf("new launch of a disabled browser: %v launches=%d", err, fake.launches)
	}
	enabled := false
	if _, err := service.UpdateBrowser("personal", 2, "root", BrowserPatch{Disabled: &enabled}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Ensure(context.Background(), "personal"); err != nil || fake.launches != 2 {
		t.Fatalf("re-enabled launch: %v launches=%d", err, fake.launches)
	}
}

func TestDirectoryRejectsUnsafeFilesAndStaticServicesStayReadOnly(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "profiles.json")
	seed := []Definition{{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"}}
	for name, content := range map[string]string{
		"trailing":  `{"version":1,"revision":1,"browsers":[{"id":"personal","application_id":"a","home_name":"h","start_url":"https://e.com","revision":1,"updated_at":"2026-09-17T00:00:00Z"}]} {}`,
		"unknown":   `{"version":1,"revision":1,"browsers":[{"id":"personal","application_id":"a","home_name":"h","start_url":"https://e.com","revision":1,"updated_at":"2026-09-17T00:00:00Z","secret":"x"}]}`,
		"duplicate": `{"version":1,"revision":1,"browsers":[{"id":"a","application_id":"a","home_name":"h","start_url":"https://e.com","revision":1,"updated_at":"2026-09-17T00:00:00Z"},{"id":"a","application_id":"a","home_name":"h2","start_url":"https://e.com","revision":1,"updated_at":"2026-09-17T00:00:00Z"}]}`,
		"null":      `{"version":1,"revision":1,"browsers":null}`,
		"version":   `{"version":2,"revision":1,"browsers":[]}`,
	} {
		if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
		fake := &lifecycleFake{snapshot: emptyRuntime()}
		store, _ := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
		if _, err := NewService(fake, store, "https://adapter.example", seed, WithLifecycle(fake), WithDirectory(path)); err == nil {
			t.Fatalf("%s directory accepted", name)
		}
	}
	valid := `{"version":1,"revision":1,"browsers":[{"id":"personal","application_id":"a","home_name":"h","start_url":"https://e.com","revision":1,"updated_at":"2026-09-17T00:00:00Z"}]}`
	if err := os.WriteFile(path, []byte(valid), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(path, 0o644); err != nil {
		t.Fatal(err)
	}
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, _ := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if _, err := NewService(fake, store, "https://adapter.example", seed, WithLifecycle(fake), WithDirectory(path)); err == nil || !strings.Contains(err.Error(), "private") {
		t.Fatalf("permissive directory accepted: %v", err)
	}
	// Without a directory the definitions stay static and cannot be modified.
	static, _, _ := newLifecycleService(t)
	label := "x"
	if _, err := static.UpdateBrowser("personal", 1, "root", BrowserPatch{Label: &label}); err != ErrDirectoryReadOnly {
		t.Fatalf("static service accepted an update: %v", err)
	}
	if records := static.Records(); len(records) != 1 || records[0].Revision != 1 || records[0].UpdatedAt.IsZero() || time.Since(records[0].UpdatedAt) > time.Minute {
		t.Fatalf("static records: %+v", records)
	}
}
