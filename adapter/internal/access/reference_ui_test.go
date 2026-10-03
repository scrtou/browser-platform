package access

import (
	"encoding/json"
	"html/template"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReferenceAuthPageFixtures(t *testing.T) {
	home := struct {
		Subject       string
		Cards         []HomeCard
		CSRF          string
		Admin         bool
		NetworkIssues int
		LatestSample  string
		ScriptNonce   string
	}{
		Subject: "qa-owner", CSRF: "qa-csrf", Admin: true, NetworkIssues: 1, LatestSample: "2026-10-02T00:00:00Z", ScriptNonce: "qa-script-nonce",
		Cards: []HomeCard{
			{ProfileID: "office", Label: "办公浏览器", EntryPath: "/browser/office/", Available: true, Enabled: true, Observed: true, Status: "stopped", Health: "offline", HealthCode: "PROFILE_STOPPED", Network: "proxy_required", NetworkName: "台湾办公代理", BrowserTemplate: "camoufox-linux-v152", Fingerprint: "env-tw-camoufox-r10", Display: "x11-selkies-1920x1080", CheckedAt: "2026-10-02T02:28:28Z"},
			{ProfileID: "review", Label: "审阅环境 <测试>", EntryPath: "/browser/review/", Available: true, Enabled: true, Observed: true, Stale: true, Status: "stopped", Health: "healthy", NetworkIssue: true, Network: "代理不可用"},
		},
	}
	member := home
	member.Admin = false
	member.Subject = "qa-member"
	empty := member
	empty.Cards = nil
	cases := []struct {
		name string
		tpl  *template.Template
		data any
	}{
		{"login", loginTemplate, struct {
			CSRF, Next    string
			SetupRequired bool
		}{"qa-csrf", "/", false}},
		{"home-admin", indexTemplate, home}, {"home-user", indexTemplate, member}, {"home-empty", indexTemplate, empty},
		{"reauth", reauthTemplate, struct{ CSRF, Next, Error string }{"qa-csrf", "/manage/", ""}},
		{"reauth-error", reauthTemplate, struct{ CSRF, Next, Error string }{"qa-csrf", "/manage/", "密码不正确"}},
		{"password", passwordTemplate, struct {
			CSRF, Error string
			Done        bool
		}{"qa-csrf", "", false}},
		{"password-error", passwordTemplate, struct {
			CSRF, Error string
			Done        bool
		}{"qa-csrf", "两次输入的密码不一致", false}},
		{"password-done", passwordTemplate, struct {
			CSRF, Error string
			Done        bool
		}{"qa-csrf", "", true}},
		{"forbidden", forbiddenTemplate, nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			if strings.HasPrefix(tc.name, "home-") {
				homePageHeaders(rec, "qa-script-nonce")
			} else {
				pageHeaders(rec)
			}
			if err := tc.tpl.Execute(rec, tc.data); err != nil {
				t.Fatal(err)
			}
			body := rec.Body.String()
			if !strings.HasPrefix(tc.name, "home-") && strings.Contains(body, "<script") {
				t.Fatal("unsafe auth template")
			}
			if strings.Contains(body, "<测试>") {
				t.Fatal("unsafe auth template")
			}
			if strings.HasPrefix(tc.name, "home-") {
				if !strings.Contains(body, `<script nonce="qa-script-nonce">`) {
					t.Fatal("home page missing strict nonce script")
				}
				if rec.Header().Get("Content-Security-Policy") != "default-src 'none'; script-src 'nonce-qa-script-nonce'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'" {
					t.Fatal("home page missing strict CSP")
				}
			}
			if tc.name == "home-user" && strings.Contains(body, `href="/manage/`) {
				t.Fatal("member sees administration link")
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
			raw, err := json.Marshal(map[string]any{"body": body, "headers": map[string]string{"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": rec.Header().Get("Content-Security-Policy")}})
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(root, tc.name+".json"), raw, 0600); err != nil {
				t.Fatal(err)
			}
		})
	}
}
