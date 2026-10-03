package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"html"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type linkedCreateManager struct {
	*fakeNetworkProfiles
	items      []profile.CompatibleTemplateSummary
	catalogErr error
}

func (m *linkedCreateManager) CompatibleTemplates(context.Context) ([]profile.CompatibleTemplateSummary, error) {
	return m.items, m.catalogErr
}

func linkedCreateFixture() *linkedCreateManager {
	m := &linkedCreateManager{fakeNetworkProfiles: &fakeNetworkProfiles{fakeBrowserManager: &fakeBrowserManager{
		fakeProfiles: &fakeProfiles{environments: map[string]profile.EnvironmentSummary{}},
		capabilities: profile.ManagementCapabilities{CreateDelete: true, TemplateCatalog: true, ManagedDirect: true},
	}}}
	for _, engine := range []string{"camoufox", "chromix", "firefox"} {
		for _, display := range []string{"fixed", "auto"} {
			m.items = append(m.items, profile.CompatibleTemplateSummary{
				BrowserTemplateID: engine, BrowserLabel: engine, BrowserVersion: "1", Engine: engine,
				EnvironmentArtifactID: engine + "-" + display, EnvironmentLabel: "测试指纹 " + display,
				DisplayTemplateID: display, DisplayLabel: display + " 显示", Locale: "zh-CN", Timezone: "Asia/Shanghai", AllowNewBrowsers: true,
			})
		}
	}
	return m
}

func linkedCreateServer(m *linkedCreateManager) *Server {
	return New(m, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{})
}

func TestLinkedCreateResolvesDisplayBeforeCreating(t *testing.T) {
	for _, item := range linkedCreateFixture().items {
		t.Run(item.EnvironmentArtifactID, func(t *testing.T) {
			m := linkedCreateFixture()
			w := httptest.NewRecorder()
			form := url.Values{"label": {"new"}, "start_url": {"https://start.example"}, "idempotency_key": {"create-linked"},
				"browser_template_id": {item.BrowserTemplateID}, "environment_artifact_id": {item.EnvironmentArtifactID}, "network_selection": {"direct"}}
			linkedCreateServer(m).ServeHTTP(w, manageForm(form, "root", []access.Grant{{Profile: "seed", Capabilities: []string{"manage"}}}, "https://adapter.example/manage/browsers"))
			if w.Header().Get("Location") != "/manage/?notice=created" || m.createRequest.DisplayTemplateID != item.DisplayTemplateID ||
				m.createRequest.EnvironmentArtifactID != item.EnvironmentArtifactID || m.createRequest.BrowserTemplateID != item.BrowserTemplateID {
				t.Fatalf("wrong binding or creation: %s %+v", w.Header().Get("Location"), m.createRequest)
			}
		})
	}
}

func TestLinkedCreateRejectsInvalidSelectionWithoutSideEffects(t *testing.T) {
	cases := map[string]func(*linkedCreateManager, url.Values){
		"cross engine":       func(_ *linkedCreateManager, f url.Values) { f.Set("browser_template_id", "firefox") },
		"missing engine":     func(_ *linkedCreateManager, f url.Values) { f.Del("browser_template_id") },
		"missing artifact":   func(_ *linkedCreateManager, f url.Values) { f.Del("environment_artifact_id") },
		"duplicate engine":   func(_ *linkedCreateManager, f url.Values) { f.Add("browser_template_id", "firefox") },
		"duplicate artifact": func(_ *linkedCreateManager, f url.Values) { f.Add("environment_artifact_id", "camoufox-auto") },
		"forged display":     func(_ *linkedCreateManager, f url.Values) { f.Set("display_template_id", "auto") },
		"empty old display":  func(_ *linkedCreateManager, f url.Values) { f.Set("display_template_id", "") },
		"old triple": func(_ *linkedCreateManager, f url.Values) {
			f.Set("template_combination", "camoufox|camoufox-fixed|fixed")
		},
		"stale artifact": func(m *linkedCreateManager, _ url.Values) { m.items = m.items[1:] },
		"not allowed":    func(m *linkedCreateManager, _ url.Values) { m.items[0].AllowNewBrowsers = false },
		"ambiguous display": func(m *linkedCreateManager, _ url.Values) {
			other := m.items[0]
			other.DisplayTemplateID = "other"
			m.items = append(m.items, other)
		},
		"catalog failure": func(m *linkedCreateManager, _ url.Values) { m.catalogErr = errors.New("private catalog token=secret") },
		"no catalog":      func(m *linkedCreateManager, _ url.Values) { m.capabilities.TemplateCatalog = false },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			m := linkedCreateFixture()
			form := url.Values{"label": {"new"}, "start_url": {"https://start.example"}, "idempotency_key": {"rejected"},
				"browser_template_id": {"camoufox"}, "environment_artifact_id": {"camoufox-fixed"}, "network_selection": {"direct"}}
			mutate(m, form)
			w := httptest.NewRecorder()
			linkedCreateServer(m).ServeHTTP(w, manageForm(form, "root", []access.Grant{{Profile: "seed", Capabilities: []string{"manage"}}}, "https://adapter.example/manage/browsers"))
			if w.Header().Get("Location") != "/manage/?notice=create_template" || m.createKey != "" {
				t.Fatalf("invalid selection reached creation: %s key=%q", w.Header().Get("Location"), m.createKey)
			}
		})
	}
}

func TestLinkedCreatePageNonceAndEmptyStates(t *testing.T) {
	var lastNonce string
	for _, name := range []string{"multi", "empty", "unavailable", "ambiguous", "network-unavailable", "escaped-label"} {
		t.Run(name, func(t *testing.T) {
			m := linkedCreateFixture()
			switch name {
			case "empty":
				m.items = nil
			case "unavailable":
				m.catalogErr = errors.New("private token=secret")
			case "ambiguous":
				m.items = append(m.items[:1], m.items[0])
			case "network-unavailable":
				m.capabilities.ManagedDirect = false
				m.capabilities.NetworkProfiles = true
			case "escaped-label":
				m.items[0].EnvironmentLabel = `</option><script>window.injected=true</script><img src=x onerror="window.injected=true">`
			}
			w := httptest.NewRecorder()
			linkedCreateServer(m).ServeHTTP(w, withGrants(httptest.NewRequest(http.MethodGet, "https://adapter.example/manage/?notice=create_template", nil), "root", []access.Grant{{Profile: "seed", Capabilities: []string{"view", "manage"}}}))
			body := w.Body.String()
			match := regexp.MustCompile(`<script nonce="([^"]+)">`).FindStringSubmatch(body)
			if len(match) == 2 {
				match[1] = html.UnescapeString(match[1])
			}
			if w.Code != http.StatusOK || len(match) != 2 || match[1] == lastNonce ||
				!strings.Contains(w.Header().Get("Content-Security-Policy"), "script-src 'nonce-"+match[1]+"'") {
				t.Fatalf("missing per-page nonce policy: %d %s", w.Code, w.Header())
			}
			lastNonce = match[1]
			for _, forbidden := range []string{`id="cb-display-template"`, `id="cb-env-artifact"`, "token=secret", `<script>window.injected`, `src=x onerror="`} {
				if strings.Contains(body, forbidden) {
					t.Fatalf("unsafe/removed field: %s", forbidden)
				}
			}
			if !strings.Contains(body, "重新选择对应引擎下的已验收指纹") || m.createKey != "" {
				t.Fatal("notice or readonly contract")
			}
			// Optional real-browser fixtures include the actual HTTP CSP, not just HTML.
			if root := os.Getenv("R6U_UI_ROOT"); root != "" {
				if !strings.Contains(root, "/runtime/r6u-linked-create-") {
					t.Fatal("fixture scope")
				}
				if err := os.MkdirAll(root, 0700); err != nil {
					t.Fatal(err)
				}
				data, err := json.Marshal(map[string]any{"body": body, "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": w.Header().Get("Content-Security-Policy")}})
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(root, name+".json"), data, 0600); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}
