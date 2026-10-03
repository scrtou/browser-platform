package httpapi

import (
	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestDisplayPreferenceFormAndEngineRejection(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}}
	manager := &fakeEnvironmentJobs{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base, capabilities: profile.ManagementCapabilities{EnvironmentJobs: true}, records: []profile.Record{{Definition: profile.Definition{ID: "personal", BrowserTemplateID: "camoufox", DisplayPreference: "contain"}}}}}
	server := New(manager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage"}}}
	page := httptest.NewRecorder()
	server.ServeHTTP(page, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "root", grants))
	if !strings.Contains(page.Body.String(), `value="contain" selected`) {
		t.Fatal("saved display preference not selected")
	}
	manager.records[0].ResolutionMode = "auto"
	manager.records[0].DisplayPreference = ""
	autoPage := httptest.NewRecorder()
	server.ServeHTTP(autoPage, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "root", grants))
	if !strings.Contains(autoPage.Body.String(), "自动分辨率：远程桌面与网页可见屏幕尺寸随客户端窗口变化") || strings.Contains(autoPage.Body.String(), `name="display_preference"`) {
		t.Fatal("automatic mode shown as fixed scaling preference")
	}
	manager.records[0].ResolutionMode = ""
	form := url.Values{"action": {"update"}, "revision": {"3"}, "display_preference": {"fill"}}
	out := httptest.NewRecorder()
	server.ServeHTTP(out, manageForm(form, "root", grants, "https://adapter.example/manage/browsers/personal"))
	if out.Code != http.StatusSeeOther || len(base.updates) != 1 || base.updates[0].DisplayPreference == nil || *base.updates[0].DisplayPreference != "fill" {
		t.Fatal("preference not saved")
	}
	form.Set("display_preference", "resize")
	out = httptest.NewRecorder()
	server.ServeHTTP(out, manageForm(form, "root", grants, "https://adapter.example/manage/browsers/personal"))
	if len(base.updates) != 1 {
		t.Fatal("invalid preference saved")
	}
	out = httptest.NewRecorder()
	server.ServeHTTP(out, manageForm(url.Values{"browser_engine": {"chromix"}, "browser_version": {"154.0"}}, "root", grants, "https://adapter.example/manage/environment-jobs"))
	if len(manager.requests) != 0 || !strings.Contains(out.Header().Get("Location"), "job_invalid") {
		t.Fatal("unsupported generator silently selected")
	}
}
