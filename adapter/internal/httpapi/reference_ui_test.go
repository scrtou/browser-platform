package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

func TestReferenceBrowserFixture(t *testing.T) {
	m := linkedCreateFixture()
	m.fakeNetworkProfiles = networkSelectionFixture().fakeNetworkProfiles
	m.capabilities.CreateDelete = true
	m.capabilities.TemplateCatalog = true
	s := linkedCreateServer(m)
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "qa-owner", []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage", "stop"}}}))
	if rec.Code != 200 {
		t.Fatal(rec.Code)
	}
	root := os.Getenv("R6AA_UI_ROOT")
	if root == "" {
		return
	}
	if !strings.Contains(root, "/runtime/r6aa-") {
		t.Fatal("fixture scope")
	}
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(map[string]any{"body": rec.Body.String(), "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": rec.Header().Get("Content-Security-Policy")}})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "browsers.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
}

func TestReferenceHealthCountsExcludeStaleAndBlocking(t *testing.T) {
	summaries := map[string]profile.EnvironmentSummary{}
	grants := []access.Grant{}
	for _, id := range []string{"healthy", "stale", "blocking", "degraded"} {
		item := sampleSummary(id)
		item.Health.Overall = profile.OverallHealthy
		item.Health.Stale = id == "stale"
		item.Health.Blocking = id == "blocking"
		if id == "degraded" {
			item.Health.Overall = profile.OverallDegraded
		}
		summaries[id] = item
		grants = append(grants, access.Grant{Profile: id, Capabilities: []string{"view"}})
	}
	profiles := &fakeProfiles{environments: summaries}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	rec := httptest.NewRecorder()
	server.ServeHTTP(rec, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "root", grants))
	counts := regexp.MustCompile(`<div class="stat-card-val">([0-9]+)</div>`).FindAllStringSubmatch(rec.Body.String(), -1)
	if len(counts) != 4 || counts[0][1] != "4" || counts[2][1] != "1" || counts[3][1] != "3" {
		t.Fatalf("incorrect health counts: %v", counts)
	}
	if !strings.Contains(rec.Body.String(), "<script nonce=") || profiles.ensureCalls != 0 || profiles.healthCalls != 0 {
		t.Fatal("read-only/no-capability behavior changed")
	}
}
