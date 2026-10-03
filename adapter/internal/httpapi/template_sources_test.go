package httpapi

import (
	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type sourceForms struct {
	*fakeEnvironmentJobs
	sources   profile.TemplateSources
	calls     int
	sourceErr error
}

func (f *sourceForms) TemplateSources() (profile.TemplateSources, error) {
	return f.sources, f.sourceErr
}
func (f *sourceForms) CreateFingerprintTemplate(_ context.Context, v profile.FingerprintTemplate) (profile.FingerprintTemplate, error) {
	f.calls++
	f.sources.Fingerprints = append(f.sources.Fingerprints, v)
	return v, nil
}
func (f *sourceForms) CreateDisplayPreset(_ context.Context, v profile.DisplayPreset) (profile.DisplayPreset, error) {
	f.calls++
	f.sources.Displays = append(f.sources.Displays, v)
	return v, nil
}
func (f *sourceForms) CreateTemplateCombination(context.Context, string, string, string, string) (profile.EnvironmentJobSummary, error) {
	f.calls++
	return profile.EnvironmentJobSummary{}, nil
}
func TestTemplateFormsSeparateFieldsAndRejectCrossSubmission(t *testing.T) {
	svc := &sourceForms{fakeEnvironmentJobs: &fakeEnvironmentJobs{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: &fakeProfiles{environments: map[string]profile.EnvironmentSummary{}}, capabilities: profile.ManagementCapabilities{EnvironmentJobs: true}}}}
	server := New(svc, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage"}}}
	svc.sources = profile.TemplateSources{
		Fingerprints:      []profile.FingerprintTemplate{{ID: "fp-aaaaaaaaaaaaaaaa", Label: "通用模板", Version: 2, Locale: "en-US", Timezone: "UTC"}},
		Displays:          []profile.DisplayPreset{{ID: "display-bbbbbbbbbbbbbbbb", Label: "桌面 1280", Width: 1280, Height: 900, DPR: 1, WindowWidth: 1280, WindowHeight: 900}},
		GenerationTargets: []profile.GenerationTarget{{BrowserTemplateID: "camoufox-linux-v152", BrowserTemplateRevision: 1, Engine: "camoufox", BrowserVersion: "152.0"}, {BrowserTemplateID: "chromix-linux-154", BrowserTemplateRevision: 1, Engine: "chromix", BrowserVersion: "154.0.8037.57"}, {BrowserTemplateID: "firefox-linux-155", BrowserTemplateRevision: 1, Engine: "firefox", BrowserVersion: "155.0.1"}},
	}
	if os.Getenv("R6S_UI_EMPTY") == "1" {
		svc.sources.Fingerprints = nil
	}
	svc.sources.Displays = append(svc.sources.Displays, profile.DisplayPreset{ID: "display-0000000000000001", Label: "自动分辨率 · DPR 随缩放变化", Revision: 1, Builtin: true, Mode: "auto", DPRMode: "system", Width: 1280, Height: 720, WindowWidth: 1280, WindowHeight: 720})
	for _, tab := range []string{"fingerprints", "displays", "jobs"} {
		w := httptest.NewRecorder()
		server.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?tab="+tab, nil), "root", grants))
		body := w.Body.String()
		if output := os.Getenv("R6Q_UI_OUTPUT"); output != "" {
			if !strings.Contains(output, "/runtime/r6q-engine-neutral-") && !strings.Contains(output, "/runtime/r6r-multi-engine-") && !strings.Contains(output, "/runtime/r6s-shared-display-") {
				t.Fatal("isolated output required")
			}
			if err := os.WriteFile(filepath.Join(output, tab+".html"), []byte(body), 0600); err != nil {
				t.Fatal(err)
			}
		}
		if w.Code != 200 {
			t.Fatal(w.Code)
		}
		if tab == "fingerprints" {
			for _, name := range []string{"width", "height", "screen_width", "screen_height", "window_width", "dpr", "engine", "browser_version"} {
				if strings.Contains(body, `name="`+name+`"`) {
					t.Fatalf("fingerprint form contains %s", name)
				}
			}
			if !strings.Contains(body, `action="/manage/fingerprint-templates"`) || strings.Contains(body, `name="browser_template_id"`) {
				t.Fatal("no fingerprint form")
			}
		} else if tab == "jobs" {
			if !strings.Contains(body, `value="firefox-linux-155"`) || !strings.Contains(body, `value="chromix-linux-154"`) || !strings.Contains(body, `name="browser_template_id"`) || !strings.Contains(body, `action="/manage/template-combinations"`) {
				t.Fatal("no combination form")
			}
		} else {
			if !strings.Contains(body, `name="width"`) || !strings.Contains(body, `name="dpr"`) || strings.Contains(body, `name="locale"`) {
				t.Fatal("display form ownership incorrect")
			}
		}
	}
	svc.sources.Fingerprints = nil
	values := url.Values{"label": {"US"}, "locale": {"en-US"}, "languages": {"en-US,en"}, "timezone": {"UTC"}}
	post := func(v url.Values) *httptest.ResponseRecorder {
		w := httptest.NewRecorder()
		server.ServeHTTP(w, manageForm(v, "root", grants, "https://adapter.example/manage/fingerprint-templates"))
		return w
	}
	w := post(values)
	if w.Code != http.StatusSeeOther || svc.calls != 1 || svc.sources.Fingerprints[0].Languages[1] != "en" {
		t.Fatal("valid fingerprint not stored")
	}
	for _, field := range []string{"engine", "browser_version"} {
		values.Set(field, "camoufox")
		post(values)
		values.Del(field)
		if svc.calls != 1 {
			t.Fatal("engine accepted on source")
		}
	}
	values.Set("screen_width", "1920")
	w = post(values)
	if svc.calls != 1 || !strings.Contains(w.Header().Get("Location"), "notice=invalid") {
		t.Fatal("screen accepted on fingerprint")
	}
	values.Del("screen_width")
	values["locale"] = []string{"en-US", "de-DE"}
	post(values)
	if svc.calls != 1 {
		t.Fatal("duplicate accepted")
	}
	w = httptest.NewRecorder()
	server.ServeHTTP(w, httptest.NewRequest("POST", "https://adapter.example/manage/display-templates", nil))
	if w.Code != 404 || svc.calls != 1 {
		t.Fatal("ungranted write")
	}
	w = httptest.NewRecorder()
	server.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/template-sources", nil), "root", grants))
	var listed struct {
		Version      int
		Fingerprints []profile.FingerprintTemplate
	}
	if w.Code != 200 || json.Unmarshal(w.Body.Bytes(), &listed) != nil || listed.Version != 1 || len(listed.Fingerprints) != 1 || !strings.Contains(w.Header().Get("Cache-Control"), "no-store") {
		t.Fatal("template source API")
	}
	svc.sourceErr = errors.New("private source path sentinel")
	for _, path := range []string{"/manage/template-sources", "/manage/?tab=fingerprints", "/manage/?tab=displays", "/manage/?tab=fingerprint-data"} {
		w = httptest.NewRecorder()
		server.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example"+path, nil), "root", grants))
		if w.Code != 503 || strings.Contains(w.Body.String(), "sentinel") {
			t.Fatal("unavailable sources masked or leaked")
		}
	}
}
