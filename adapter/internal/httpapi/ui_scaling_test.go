package httpapi

import (
	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"context"
	"io"
	"log/slog"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"
)

type scalingManager struct {
	*fakeBrowserManager
	supported bool
}

func (m *scalingManager) UIScalingPreference(string) (int, int, bool) { return 150, 3, m.supported }
func TestUIScalingManagementForm(t *testing.T) {
	base := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal")}}
	manager := &scalingManager{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: base, records: []profile.Record{{Definition: profile.Definition{ID: "personal", WaylandMode: true, UIScalingPercent: 150}, Revision: 3}}}, supported: true}
	server := New(manager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
	grants := []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage"}}}
	render := func() string {
		w := httptest.NewRecorder()
		server.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "root", grants))
		return w.Body.String()
	}
	body := render()
	if !strings.Contains(body, `value="150" selected`) || !strings.Contains(body, "旧版 Work 自动分辨率") || strings.Contains(body, `name="display_preference"`) {
		t.Fatal("legacy display form incorrect")
	}
	for i, value := range []string{"150", "0", "300"} {
		w := httptest.NewRecorder()
		server.ServeHTTP(w, manageForm(url.Values{"action": {"update"}, "revision": {strconv.Itoa(3 + i)}, "ui_scaling_percent": {value}}, "root", grants, "https://adapter.example/manage/browsers/personal"))
		if w.Code != 303 {
			t.Fatal(w.Code)
		}
	}
	if len(base.updates) != 3 || base.updates[0].UIScalingPercent == nil || *base.updates[0].UIScalingPercent != 150 || *base.updates[1].UIScalingPercent != 0 {
		t.Fatal("percentage not submitted")
	}
	for _, values := range [][]string{{"99"}, {"151"}, {"301"}, {"bad"}, {"150", "200"}} {
		w := httptest.NewRecorder()
		server.ServeHTTP(w, manageForm(url.Values{"action": {"update"}, "revision": {"3"}, "ui_scaling_percent": values}, "root", grants, "https://adapter.example/manage/browsers/personal"))
	}
	if len(base.updates) != 3 {
		t.Fatal("invalid or ambiguous value accepted")
	}
	manager.supported = false
	if strings.Contains(render(), `name="ui_scaling_percent"`) {
		t.Fatal("fixed contract exposes mutable DPI")
	}
}
