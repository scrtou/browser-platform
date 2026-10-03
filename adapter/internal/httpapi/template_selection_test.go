package httpapi

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"regexp"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type selectionManager struct{ *fakeBrowserManager }

func (m *selectionManager) CompatibleTemplates(ctx context.Context) ([]profile.CompatibleTemplateSummary, error) {
	items, err := m.fakeBrowserManager.CompatibleTemplates(ctx)
	items = append(items, profile.CompatibleTemplateSummary{BrowserTemplateID: "chromix", BrowserLabel: "Chromix", EnvironmentArtifactID: "cjk-r2", DisplayTemplateID: "chromix-1280", DisplayLabel: "1280", AllowNewBrowsers: true})
	return items, err
}

func TestEditTemplateSelectsEachRowsActualBinding(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{}}
	manager := &selectionManager{&fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{TemplateCatalog: true}}}
	grants := []access.Grant{}
	for _, id := range []string{"personal", "chromix", "missing", "legacy"} {
		base.environments[id] = sampleSummary(id)
		grants = append(grants, access.Grant{Profile: id, Capabilities: []string{"view", "manage"}})
	}
	manager.records = []profile.Record{
		{Definition: profile.Definition{ID: "personal", BrowserTemplateID: "camoufox-linux", EnvironmentArtifactID: "env-r9", DisplayTemplateID: "fixed-1920"}},
		{Definition: profile.Definition{ID: "chromix", BrowserTemplateID: "chromix", EnvironmentArtifactID: "cjk-r2", DisplayTemplateID: "chromix-1280"}},
		{Definition: profile.Definition{ID: "missing", BrowserTemplateID: "retired", EnvironmentArtifactID: "retired-env", DisplayTemplateID: "retired-display"}},
		{Definition: profile.Definition{ID: "legacy"}},
	}
	server := New(manager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/", nil), "root", grants))
	if page.Code != http.StatusOK {
		t.Fatal(page.Code)
	}
	body := page.Body.String()
	selected := func(id string) string {
		t.Helper()
		match := regexp.MustCompile(`<select id="` + regexp.QuoteMeta(id) + `"[^>]*>(.*?)</select>`).FindStringSubmatch(body)
		if len(match) != 2 {
			t.Fatalf("missing select %s", id)
		}
		options := regexp.MustCompile(`<option value="([^"]*)"([^>]*)>`).FindAllStringSubmatch(match[1], -1)
		values := []string{}
		for _, o := range options {
			if strings.Contains(o[2], "selected") {
				values = append(values, o[1])
				if o[1] == "" && !strings.Contains(o[2], "disabled") {
					t.Fatal("missing binding selectable")
				}
			}
		}
		if len(values) != 1 {
			t.Fatalf("%s selected=%v", id, values)
		}
		return values[0]
	}
	expected := map[string][]string{"personal": {"camoufox-linux", "env-r9", "fixed-1920"}, "chromix": {"chromix", "cjk-r2", "chromix-1280"}, "missing": {"", "", ""}, "legacy": {"", "", ""}}
	for id, want := range expected {
		fields := url.Values{"browser_template_id": {selected("browser-template-" + id)}, "environment_artifact_id": {selected("fingerprint-template-" + id)}, "display_template_id": {selected("display-template-" + id)}}
		for i, key := range []string{"browser_template_id", "environment_artifact_id", "display_template_id"} {
			if fields.Get(key) != want[i] {
				t.Fatalf("%s %s got %q want %q", id, key, fields.Get(key), want[i])
			}
		}
		if id == "chromix" {
			fields.Set("return_to", "browsers")
			fields.Set("action", "apply")
			fields.Set("browser_revision", "3")
			fields.Set("idempotency_key", "selected-current")
			response := httptest.NewRecorder()
			server.ServeHTTP(response, manageForm(fields, "root", grants, "https://adapter.example/manage/browsers/chromix/template"))
			if response.Code != http.StatusSeeOther || len(manager.templateApply) != 1 || manager.templateApply[0] != "chromix/3/chromix/cjk-r2/chromix-1280/root/selected-current" {
				t.Fatalf("wrong submitted selection: %d %v", response.Code, manager.templateApply)
			}
		}
	}
}
