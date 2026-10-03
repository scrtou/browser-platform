package profile

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestExplicitEmptyDirectoryCanCreateFirstBrowserAndReopen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "profiles.json")
	raw := []byte(`{"version":1,"revision":1,"browsers":[]}`)
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	seed := Definition{ID: "old-seed", ApplicationID: "firefox", HomeName: "old-seed", StartURL: "https://example.com"}
	service, fake := directoryService(t, path, []Definition{seed})
	if len(service.Records()) != 0 || len(service.ProfileIDs()) != 0 {
		t.Fatal("empty persisted catalog imported old seed")
	}
	ids, err := DirectoryProfileIDs(path)
	if err != nil || len(ids) != 0 {
		t.Fatal("empty catalog cannot be used by account initialization", err)
	}
	record := Record{Definition: Definition{ID: "first", ApplicationID: "firefox-first", HomeName: "first", StartURL: "https://example.com"}, Status: RecordReady}
	if err := service.directory.add(record); err != nil {
		t.Fatal(err)
	}
	again, _ := directoryService(t, path, nil)
	if !again.KnownProfile("first") || again.KnownProfile("old-seed") || len(again.Records()) != 1 {
		t.Fatal("first browser did not persist across restart")
	}
	if fake.launches != 0 || fake.stopCalls != 0 {
		t.Fatal("catalog initialization changed runtime")
	}
}

func TestEmptyDirectoryStillRejectsMissingAndMalformedState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "profiles.json")
	d, _ := newDirectory(nil, time.Now)
	if err := d.open(path); err == nil {
		t.Fatal("missing directory silently initialized")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("missing state was changed")
	}
	for _, raw := range []string{
		`{"version":1,"revision":1}`, `{"version":1,"revision":1,"browsers":null}`,
		`{"version":1,"revision":0,"browsers":[]}`, `{"version":2,"revision":1,"browsers":[]}`,
		`{"version":1,"revision":1,"browsers":[]} {}`, `{"version":1,"revision":1,"browsers":[],"extra":true}`,
	} {
		if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		d, _ := newDirectory(nil, time.Now)
		if err := d.open(path); err == nil {
			t.Errorf("malformed catalog accepted: %s", raw)
		}
		after, _ := os.ReadFile(path)
		if string(after) != raw {
			t.Fatal("rejected state changed")
		}
	}
}
