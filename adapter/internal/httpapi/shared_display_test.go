package httpapi

import (
	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type sharedDisplayManager struct {
	*fakeBrowserManager
	items []profile.CompatibleTemplateSummary
}

func (s *sharedDisplayManager) CompatibleTemplates(context.Context) ([]profile.CompatibleTemplateSummary, error) {
	return s.items, nil
}
func TestR6SNewBrowserChoices(t *testing.T) {
	root := os.Getenv("R6S_CREATE_UI_ROOT")
	if root == "" {
		t.Skip("isolated accepted catalog")
	}
	if !strings.Contains(root, "/runtime/r6s-shared-display-") {
		t.Fatal("scope")
	}
	raw, e := os.ReadFile(filepath.Join(root, "integration-3", "compatible.json"))
	if e != nil {
		t.Fatal(e)
	}
	manager := &sharedDisplayManager{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: &fakeProfiles{environments: map[string]profile.EnvironmentSummary{}}, capabilities: profile.ManagementCapabilities{CreateDelete: true, TemplateCatalog: true, ManagedDirect: true}}}
	if e = json.Unmarshal(raw, &manager.items); e != nil {
		t.Fatal(e)
	}
	server := New(manager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	w := httptest.NewRecorder()
	server.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?tab=browsers", nil), "root", []access.Grant{{Profile: "seed", Capabilities: []string{"view", "manage"}}}))
	if w.Code != 200 {
		t.Fatal(w.Code)
	}
	for _, id := range []string{"camoufox-linux-v152", "chromix-linux-154", "firefox-linux-155"} {
		if !strings.Contains(w.Body.String(), `value="`+id+`"`) {
			t.Fatal("missing choice", id)
		}
	}
	if e = os.WriteFile(filepath.Join(root, "ui-create", "browsers.html"), w.Body.Bytes(), 0600); e != nil {
		t.Fatal(e)
	}
}
