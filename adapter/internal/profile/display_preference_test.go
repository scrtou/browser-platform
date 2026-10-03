package profile

import (
	"path/filepath"
	"testing"
)

func TestDisplayPreferencePersistsWithoutChangingBrowserIdentity(t *testing.T) {
	path := filepath.Join(t.TempDir(), "profiles.json")
	seed := []Definition{{ID: "personal", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com", BrowserTemplateID: "camoufox", BrowserTemplateRevision: 1, EnvironmentArtifactID: "env", EnvironmentArtifactSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", EnvironmentSource: "frozen", EnvironmentTemplateRevision: 1, DisplayTemplateID: "fixed", DisplayTemplateRevision: 1}}
	service, fake := directoryService(t, path, seed)
	if service.DisplayPreference("personal") != "" {
		t.Fatal("legacy behavior changed")
	}
	mode := "contain"
	r, err := service.UpdateBrowser("personal", 1, "root", BrowserPatch{DisplayPreference: &mode})
	if err != nil {
		t.Fatal(err)
	}
	if r.ApplicationID != "app" || r.HomeName != "home" || r.Revision != 2 || fake.stopCalls != 0 {
		t.Fatal("presentation changed runtime identity")
	}
	reloaded, _ := directoryService(t, path, seed)
	if reloaded.DisplayPreference("personal") != "contain" {
		t.Fatal("preference lost on restart")
	}
	bad := "resize-server"
	if _, err := reloaded.UpdateBrowser("personal", 2, "root", BrowserPatch{DisplayPreference: &bad}); err == nil {
		t.Fatal("invalid preference accepted")
	}
	mode = "fill"
	if _, err := reloaded.UpdateBrowser("personal", 1, "root", BrowserPatch{DisplayPreference: &mode}); err != ErrRevisionMismatch {
		t.Fatal("stale update accepted")
	}
	if reloaded.DisplayPreference("personal") != "contain" {
		t.Fatal("rejected update changed preference")
	}
}
