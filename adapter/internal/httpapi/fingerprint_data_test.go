package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"html"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
)

type fingerprintDataManager struct {
	*sourceForms
	items     []profile.CompatibleTemplateSummary
	createErr error
}

func (m *fingerprintDataManager) CompatibleTemplates(context.Context) ([]profile.CompatibleTemplateSummary, error) {
	return m.items, nil
}
func (m *fingerprintDataManager) CreateTemplateCombination(ctx context.Context, actor, fingerprint, display, engine string) (profile.EnvironmentJobSummary, error) {
	if m.createErr != nil {
		return profile.EnvironmentJobSummary{}, m.createErr
	}
	return m.sourceForms.CreateTemplateCombination(ctx, actor, fingerprint, display, engine)
}
func fingerprintDataFixture() *fingerprintDataManager {
	m := &fingerprintDataManager{sourceForms: &sourceForms{fakeEnvironmentJobs: &fakeEnvironmentJobs{fakeBrowserManager: &fakeBrowserManager{
		fakeProfiles: &fakeProfiles{environments: map[string]profile.EnvironmentSummary{}},
		capabilities: profile.ManagementCapabilities{EnvironmentJobs: true, TemplateCatalog: true, CreateDelete: true, ManagedDirect: true},
	}}}, items: linkedCreateFixture().items}
	m.sources.Fingerprints = []profile.FingerprintTemplate{
		{ID: "fp-one", Label: "中文工作环境", Locale: "zh-CN", Languages: []string{"zh-CN", "zh", "en-US"}, Timezone: "Asia/Shanghai"},
		{ID: "fp-two", Label: "English environment", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"},
	}
	m.sources.Displays = []profile.DisplayPreset{
		{ID: "display-auto", Label: "自动分辨率 · DPR 随缩放变化", Builtin: true, Mode: "auto"},
		{ID: "display-fixed", Label: "办公桌面", Mode: "fixed", Width: 1920, Height: 1080, DPR: 1, WindowWidth: 1600, WindowHeight: 900},
	}
	for _, engine := range []string{"camoufox", "chromix", "firefox"} {
		m.sources.GenerationTargets = append(m.sources.GenerationTargets, profile.GenerationTarget{BrowserTemplateID: engine, Engine: engine, BrowserVersion: "155.0"})
	}
	for _, status := range []string{"queued", "running", "accepted", "failed"} {
		m.jobs = append(m.jobs, profile.EnvironmentJobSummary{ID: "job-" + status, Status: status, Locale: "zh-CN", Timezone: "Asia/Shanghai", Actor: "root", FingerprintTemplateID: "fp-one", DisplayPresetID: "display-auto"})
	}
	return m
}

func fingerprintDataPage(m *fingerprintDataManager, query string) *httptest.ResponseRecorder {
	s := linkedCreateServer(linkedCreateFixture())
	s.profiles = m
	w := httptest.NewRecorder()
	s.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?"+query, nil), "root", []access.Grant{{Profile: "seed", Capabilities: []string{"view", "manage"}}}))
	return w
}

func TestFingerprintDataNavigationAndFixtures(t *testing.T) {
	for _, name := range []string{"filled", "empty", "no-targets", "no-displays", "escaped"} {
		m := fingerprintDataFixture()
		switch name {
		case "empty":
			m.sources.Fingerprints = nil
			m.sources.Displays = m.sources.Displays[:1]
			m.jobs = nil
			m.items = nil
		case "no-targets":
			m.sources.GenerationTargets = nil
		case "no-displays":
			m.sources.Displays = nil
		case "escaped":
			m.sources.Fingerprints[0].Label = `<script>window.injected=true</script>` + strings.Repeat("长名称", 15)
		}
		for _, section := range []string{"fingerprints", "displays", "combinations"} {
			query := "tab=fingerprint-data&section=" + section
			w := fingerprintDataPage(m, query)
			body := html.UnescapeString(w.Body.String())
			if w.Code != 200 || !strings.Contains(body, `data-section="`+section+`"`) || !strings.Contains(body, `href="/manage/?tab=fingerprint-data" class="tab-item active"`) {
				t.Fatalf("%s/%s wrong panel", name, section)
			}
			for other, action := range map[string]string{"fingerprints": "fingerprint-templates", "displays": "display-templates", "combinations": "template-combinations"} {
				if strings.Contains(body, `action="/manage/`+action+`"`) != (other == section) {
					t.Fatal("wrong form ownership", section, other)
				}
			}
			if !strings.Contains(body, "/auth/reauth?next="+url.QueryEscape("/manage/?"+query)) || strings.Contains(w.Body.String(), "<script>window.injected") || m.calls != 0 {
				t.Fatal("reauth, escaping or readonly contract")
			}
			if root := os.Getenv("R6V_UI_ROOT"); root != "" {
				if !strings.Contains(root, "/runtime/r6v-fingerprint-data-") {
					t.Fatal("fixture scope")
				}
				if err := os.MkdirAll(root, 0700); err != nil {
					t.Fatal(err)
				}
				raw, err := json.Marshal(map[string]any{"body": w.Body.String(), "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": w.Header().Get("Content-Security-Policy")}})
				if err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(filepath.Join(root, name+"-"+section+".json"), raw, 0600); err != nil {
					t.Fatal(err)
				}
			}
		}
	}
	for query, section := range map[string]string{
		"tab=fingerprint-data": "fingerprints", "tab=fingerprint-data&section=bad": "fingerprints",
		"tab=fingerprint-data&section=https%3A%2F%2Fevil.example": "fingerprints", "tab=fingerprints": "fingerprints", "tab=displays": "displays", "tab=jobs": "combinations",
	} {
		w := fingerprintDataPage(fingerprintDataFixture(), query)
		if w.Code != 200 || !strings.Contains(w.Body.String(), `data-section="`+section+`"`) || strings.Contains(w.Body.String(), "evil.example") {
			t.Fatal("navigation fallback", query)
		}
	}
	m := fingerprintDataFixture()
	m.capabilities.EnvironmentJobs = false
	if body := fingerprintDataPage(m, "tab=fingerprint-data").Body.String(); strings.Contains(body, `class="data-nav"`) || strings.Contains(body, `href="/manage/?tab=fingerprint-data"`) {
		t.Fatal("capability gate")
	}
	m = fingerprintDataFixture()
	m.sourceErr = errors.New("private source sentinel")
	for _, section := range []string{"fingerprints", "displays", "combinations"} {
		w := fingerprintDataPage(m, "tab=fingerprint-data&section="+section)
		if w.Code != 503 || strings.Contains(w.Body.String(), "sentinel") {
			t.Fatal("source failure hidden/leaked")
		}
	}
}

func TestFingerprintDataPostReturnsToFunction(t *testing.T) {
	for _, tc := range []struct {
		path, section, notice string
		values                url.Values
	}{
		{"fingerprint-templates", "fingerprints", "template_saved", url.Values{"label": {"new"}, "locale": {"en-US"}, "languages": {"en-US,en"}, "timezone": {"UTC"}}},
		{"display-templates", "displays", "template_saved", url.Values{"label": {"new"}, "mode": {"fixed"}, "width": {"1280"}, "height": {"720"}, "dpr": {"1"}}},
		{"template-combinations", "combinations", "job_created", url.Values{"fingerprint_id": {"fp-one"}, "display_id": {"display-auto"}, "browser_template_id": {"camoufox"}}},
	} {
		m := fingerprintDataFixture()
		s := linkedCreateServer(linkedCreateFixture())
		s.profiles = m
		post := func() *httptest.ResponseRecorder {
			w := httptest.NewRecorder()
			s.ServeHTTP(w, manageForm(tc.values, "root", []access.Grant{{Profile: "seed", Capabilities: []string{"manage"}}}, "https://adapter.example/manage/"+tc.path))
			return w
		}
		base := "/manage/?tab=fingerprint-data&section=" + tc.section + "&notice="
		if w := post(); w.Code != 303 || w.Header().Get("Location") != base+tc.notice || m.calls != 1 {
			t.Fatal("successful return", tc.path, w.Header())
		}
		tc.values.Set("foreign", "rejected")
		if w := post(); w.Header().Get("Location") != base+"invalid" || m.calls != 1 {
			t.Fatal("invalid return", tc.path)
		}
		if tc.path == "template-combinations" {
			tc.values.Del("foreign")
			m.createErr = profile.ErrEnvironmentJobsBusy
			if w := post(); w.Header().Get("Location") != base+"job_busy" || m.calls != 1 {
				t.Fatal("busy return")
			}
		}
	}
}
