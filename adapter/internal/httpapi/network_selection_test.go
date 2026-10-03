package httpapi

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/state"
)

type networkSelectionManager struct {
	*fakeNetworkProfiles
	directCall string
}

func (m *networkSelectionManager) SetBrowserManagedDirect(_ context.Context, id string, revision int, actor, key string) (profile.Record, error) {
	m.directCall = strings.Join([]string{id, strconv.Itoa(revision), actor, key}, "/")
	return profile.Record{}, m.operationError
}
func networkSelectionFixture() *networkSelectionManager {
	summary := sampleSummary("personal")
	summary.Status = state.StatusStopped
	return &networkSelectionManager{fakeNetworkProfiles: &fakeNetworkProfiles{
		fakeBrowserManager: &fakeBrowserManager{fakeProfiles: &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": summary}}, capabilities: profile.ManagementCapabilities{ManagedDirect: true, NetworkProfiles: true},
			records: []profile.Record{{Definition: profile.Definition{ID: "personal", NetworkMode: "proxy_required", NetworkProfileID: "corp", NetworkProfileRevision: 2}}}},
		profiles: []profile.NetworkProfileRevisionSummary{
			{ID: "corp", Label: "公司代理", Revision: 2, Auth: "basic", Status: profile.NetworkRevisionAccepted, AllowedProfiles: []string{"personal"}},
			{ID: "corp", Label: "公司代理", Revision: 3, Auth: "basic", Status: profile.NetworkRevisionAccepted, AllowedProfiles: []string{"personal"}},
			{ID: "other", Label: "其他代理", Revision: 1, Auth: "none", Status: profile.NetworkRevisionAccepted},
			{ID: "ungranted", Revision: 1, Auth: "basic", Status: profile.NetworkRevisionAccepted},
			{ID: "disabled", Revision: 1, Auth: "none", Status: profile.NetworkRevisionDisabled},
			{ID: "expired", Revision: 1, Auth: "none", Status: profile.NetworkRevisionAccepted, Expired: true},
		},
	}}
}

func TestBrowserNetworkSelectCurrentBindingAndUnavailableOptions(t *testing.T) {
	for _, name := range []string{"proxy", "direct", "missing", "disabled", "ungranted", "running", "no-options", "long-label"} {
		t.Run(name, func(t *testing.T) {
			m := networkSelectionFixture()
			want := `value="proxy|corp|2" selected`
			switch name {
			case "direct":
				m.records[0].NetworkMode = "direct"
				want = `value="direct" selected`
			case "missing", "disabled", "ungranted":
				m.records[0].NetworkProfileID = name
				m.records[0].NetworkProfileRevision = 1
				want = `value="" selected disabled`
			case "running":
				row := m.environments["personal"]
				row.Status = state.StatusRunning
				m.environments["personal"] = row
			case "no-options":
				m.profiles = nil
				m.capabilities.ManagedDirect = false
			case "long-label":
				m.profiles[0].Label = strings.Repeat("长名称", 60) + "<script>bad()</script>"
			}
			s := linkedCreateServer(linkedCreateFixture())
			s.profiles = m
			w := httptest.NewRecorder()
			s.ServeHTTP(w, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/", nil), "root", []access.Grant{{Profile: "personal", Capabilities: []string{"view", "manage"}}}))
			body := w.Body.String()
			if w.Code != 200 {
				t.Fatal(w.Code)
			}
			if name == "no-options" {
				if strings.Contains(body, `name="network_selection"`) {
					t.Fatal("empty selector")
				}
				return
			}
			if !strings.Contains(body, want) || strings.Count(body, `name="network_selection"`) != 1 || strings.Count(body, `>应用网络</button>`) != 1 {
				t.Fatal("network selection/current binding mismatch")
			}
			for _, forbidden := range []string{`value="proxy|ungranted|1"`, `value="proxy|disabled|1"`, `value="proxy|expired|1"`, `/network-profile"`, `<script>bad()`} {
				if strings.Contains(body, forbidden) {
					t.Fatal("unavailable/old option", forbidden)
				}
			}
			if strings.Contains(body, `disabled>应用网络</button>`) != (name == "running") {
				t.Fatal("running button state")
			}
			if root := os.Getenv("R6X_UI_ROOT"); root != "" {
				if !strings.Contains(root, "/runtime/r6x-network-select-") {
					t.Fatal("fixture scope")
				}
				if err := os.MkdirAll(root, 0700); err != nil {
					t.Fatal(err)
				}
				raw, err := json.Marshal(map[string]any{"body": body, "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": w.Header().Get("Content-Security-Policy")}})
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(root, name+".json"), raw, 0600); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}

func TestBrowserNetworkSelectDispatchAndRejections(t *testing.T) {
	for _, tc := range []struct {
		name, selection, notice string
		mutate                  func(*networkSelectionManager, url.Values)
	}{
		{"direct", "direct", "network_applied", nil},
		{"proxy", "proxy|corp|3", "network_applied", nil},
		{"empty", "", "invalid", nil}, {"bad-revision", "proxy|corp|0", "invalid", nil}, {"empty-id", "proxy||2", "invalid", nil}, {"extra", "proxy|corp|2|direct", "invalid", nil},
		{"no-capability", "direct", "invalid", func(m *networkSelectionManager, v url.Values) { m.capabilities.ManagedDirect = false }},
		{"no-proxy-capability", "proxy|corp|3", "invalid", func(m *networkSelectionManager, v url.Values) { m.capabilities.NetworkProfiles = false }},
		{"duplicate", "direct", "invalid", func(m *networkSelectionManager, v url.Values) { v.Add("network_selection", "proxy|corp|3") }},
		{"invalid-browser-revision", "direct", "invalid", func(m *networkSelectionManager, v url.Values) { v.Set("revision", "0") }},
		{"missing-key", "direct", "invalid", func(m *networkSelectionManager, v url.Values) { v.Del("idempotency_key") }},
		{"busy", "proxy|corp|3", "network_busy", func(m *networkSelectionManager, v url.Values) { m.operationError = profile.ErrBrowserBusy }},
		{"stale", "proxy|corp|3", "revision", func(m *networkSelectionManager, v url.Values) { m.operationError = profile.ErrRevisionMismatch }},
		{"unauthorized", "proxy|corp|3", "invalid", func(m *networkSelectionManager, v url.Values) {
			m.operationError = profile.ErrNetworkProfileUnauthorized
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := networkSelectionFixture()
			s := linkedCreateServer(linkedCreateFixture())
			s.profiles = m
			v := url.Values{"action": {"network_select"}, "revision": {"3"}, "network_selection": {tc.selection}, "idempotency_key": {"change-1"}, "network_profile_id": {"ignored"}, "network_revision": {"9"}}
			if tc.mutate != nil {
				tc.mutate(m, v)
			}
			w := httptest.NewRecorder()
			s.ServeHTTP(w, manageForm(v, "root", []access.Grant{{Profile: "personal", Capabilities: []string{"manage"}}}, "https://adapter.example/manage/browsers/personal"))
			if w.Code != 303 || w.Header().Get("Location") != "/manage/?notice="+tc.notice {
				t.Fatalf("%d %s", w.Code, w.Header().Get("Location"))
			}
			if tc.name == "direct" && m.directCall != "personal/3/root/change-1" {
				t.Fatal(m.directCall)
			}
			if tc.name == "proxy" && (m.lastBind != "personal/3/corp/3/change-1" || m.lastActor != "root") {
				t.Fatal(m.lastBind, m.lastActor)
			}
			if tc.notice == "invalid" && m.operationError == nil && (m.lastBind != "" || m.directCall != "") {
				t.Fatal("invalid form applied")
			}
			if len(m.stopCalls) != 0 {
				t.Fatal("implicit stop")
			}
		})
	}
	for _, name := range []string{"no-grant", "no-reauth"} {
		m := networkSelectionFixture()
		s := linkedCreateServer(linkedCreateFixture())
		s.profiles = m
		caps := []string{"view"}
		if name == "no-reauth" {
			caps = []string{"manage"}
			s.access = &access.Gateway{}
		}
		r := manageForm(url.Values{"action": {"network_select"}, "revision": {"3"}, "network_selection": {"direct"}, "idempotency_key": {"change-1"}}, "root", []access.Grant{{Profile: "personal", Capabilities: caps}}, "https://adapter.example/manage/browsers/personal")
		r.SetPathValue("profile", "personal")
		w := httptest.NewRecorder()
		s.manageBrowser(w, r)
		if m.directCall != "" || (name == "no-grant" && w.Code != 403) || (name == "no-reauth" && w.Header().Get("Location") != "/manage/?notice=reauth") {
			t.Fatal(name, w.Code)
		}
	}
}
