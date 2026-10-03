package httpapi

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
)

type deletionDataManager struct {
	*fingerprintDataManager
	deleted   []string
	deleteErr error
}

func (m *deletionDataManager) DeleteTemplateData(_ context.Context, kind, id, browser, display, actor string) error {
	m.deleted = append(m.deleted, strings.Join([]string{kind, id, browser, display, actor}, "/"))
	return m.deleteErr
}

type deletionNetworkManager struct {
	*networkSelectionManager
	deleted   string
	deleteErr error
}

func (m *deletionNetworkManager) DeleteNetworkProfile(_ context.Context, id string, revision int, actor, key string) error {
	m.deleted = id + "/" + actor + "/" + key
	return m.deleteErr
}
func deletionFixture() *deletionDataManager {
	return &deletionDataManager{fingerprintDataManager: fingerprintDataFixture()}
}
func writeDeletionFixture(t *testing.T, name string, w *httptest.ResponseRecorder) {
	t.Helper()
	root := os.Getenv("R6Y_UI_ROOT")
	if root == "" {
		return
	}
	if !strings.Contains(root, "/runtime/r6y-management-delete-") {
		t.Fatal("fixture scope")
	}
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(map[string]any{"body": w.Body.String(), "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": w.Header().Get("Content-Security-Policy")}})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, name+".json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
}
func TestDataDeletionFormsAndRoutes(t *testing.T) {
	for _, tc := range []struct{ section, path, kind string }{{"fingerprints", "fingerprint-templates", "fingerprints"}, {"displays", "display-templates", "displays"}, {"combinations", "template-combinations", "combinations"}, {"combinations", "environment-jobs", "jobs"}} {
		m := deletionFixture()
		s := linkedCreateServer(linkedCreateFixture())
		s.profiles = m
		page := httptest.NewRecorder()
		s.ServeHTTP(page, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?tab=fingerprint-data&section="+tc.section, nil), "root", []access.Grant{{Profile: "seed", Capabilities: []string{"manage"}}}))
		if page.Code != 200 || !strings.Contains(page.Body.String(), `class="delete-form"`) {
			t.Fatal(tc, page.Code)
		}
		if tc.section == "displays" && strings.Contains(page.Body.String(), `/display-templates/display-auto/delete`) {
			t.Fatal("builtin delete form")
		}
		writeDeletionFixture(t, tc.section, page)
		v := url.Values{"confirm": {"delete"}, "browser_template_id": {"camoufox"}, "display_template_id": {"display-fixed"}}
		target := "https://adapter.example/manage/" + tc.path + "/item/delete"
		w := httptest.NewRecorder()
		s.ServeHTTP(w, manageForm(v, "root", []access.Grant{}, target))
		if w.Header().Get("Location") != "/manage/?tab=fingerprint-data&section="+tc.section+"&notice=data_deleted" || len(m.deleted) != 1 {
			t.Fatal(tc, w.Code, w.Header())
		}
		for _, bad := range []url.Values{{}, {"confirm": {"delete", "delete"}}, {"confirm": {"delete"}, "foreign": {"value"}}} {
			w = httptest.NewRecorder()
			s.ServeHTTP(w, manageForm(bad, "root", []access.Grant{}, target))
			if len(m.deleted) != 1 || !strings.HasSuffix(w.Header().Get("Location"), "notice=invalid") {
				t.Fatal("invalid delete accepted")
			}
		}
		m.deleteErr = profile.ErrDataReferenced
		w = httptest.NewRecorder()
		s.ServeHTTP(w, manageForm(v, "root", []access.Grant{}, target))
		if !strings.HasSuffix(w.Header().Get("Location"), "notice=data_referenced") {
			t.Fatal(w.Header())
		}
	}
	m := &deletionNetworkManager{networkSelectionManager: networkSelectionFixture()}
	s := linkedCreateServer(linkedCreateFixture())
	s.profiles = m
	page := httptest.NewRecorder()
	s.ServeHTTP(page, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?tab=network", nil), "root", []access.Grant{}))
	if page.Code != 200 || !strings.Contains(page.Body.String(), `name="action" value="delete"`) {
		t.Fatal(page.Code)
	}
	writeDeletionFixture(t, "network", page)
	v := url.Values{"action": {"delete"}, "confirm": {"delete"}, "id": {"corp"}, "revision": {"2"}, "idempotency_key": {"delete-corp-r2"}}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, manageForm(v, "root", []access.Grant{}, "https://adapter.example/manage/network-profiles"))
	if m.deleted != "corp/root/delete-corp-r2" || w.Header().Get("Location") != "/manage/?tab=network&notice=data_deleted" {
		t.Fatal(w.Header(), m.deleted)
	}
}

func TestBuiltinDataHasNoDeleteFormAndAPIReportsProtection(t *testing.T) {
	for _, section := range []string{"fingerprints", "displays", "combinations"} {
		m := deletionFixture()
		for i := range m.sources.Fingerprints {
			m.sources.Fingerprints[i].Builtin = true
		}
		for i := range m.sources.Displays {
			m.sources.Displays[i].Builtin = true
		}
		for i := range m.items {
			m.items[i].Builtin = true
		}
		// Completed job records are ordinary history and have their own deletion policy.
		m.jobs = nil
		s := linkedCreateServer(linkedCreateFixture())
		s.profiles = m
		page := httptest.NewRecorder()
		s.ServeHTTP(page, withGrants(httptest.NewRequest("GET", "https://adapter.example/manage/?tab=fingerprint-data&section="+section, nil), "root", []access.Grant{}))
		if page.Code != 200 || strings.Contains(page.Body.String(), `class="delete-form"`) || !strings.Contains(page.Body.String(), "不能删除") {
			t.Fatal(section, page.Code)
		}
		if section == "displays" && !strings.Contains(page.Body.String(), "1920 × 1080") {
			t.Fatal("fixed built-in rendered as automatic")
		}
		m.deleteErr = profile.ErrBuiltinTemplate
		path := map[string]string{"fingerprints": "fingerprint-templates", "displays": "display-templates", "combinations": "template-combinations"}[section]
		values := url.Values{"confirm": {"delete"}, "browser_template_id": {"camoufox"}, "display_template_id": {"display-fixed"}}
		w := httptest.NewRecorder()
		s.ServeHTTP(w, manageForm(values, "root", []access.Grant{}, "https://adapter.example/manage/"+path+"/item/delete"))
		if len(m.deleted) != 1 || !strings.Contains(w.Header().Get("Location"), "notice=data_builtin") {
			t.Fatal(section, w.Header())
		}
	}
}
