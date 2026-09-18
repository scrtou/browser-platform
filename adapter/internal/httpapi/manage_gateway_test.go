package httpapi

import (
	"context"
	"encoding/json"
	"encoding/pem"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

// TestManagementBehindTheRealGateway wires the real access gateway in front of
// the HTTP API: a login sees only its own grants, another login sees its own,
// and nothing is served before login.
func TestManagementBehindTheRealGateway(t *testing.T) {
	const password = "synthetic-management-test-password"
	directory := t.TempDir()
	if err := os.Chmod(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	verifier, err := access.HashPassword(password)
	if err != nil {
		t.Fatal(err)
	}
	registry := filepath.Join(directory, "users.json")
	if err := access.WriteRegistry(registry, access.Registry{Version: 2, Users: []access.Account{
		{ID: "alice", PasswordHash: verifier, Profiles: []string{"personal"}},
		{ID: "bob", PasswordHash: verifier, Profiles: []string{"work", "personal"}, Role: access.RoleAdmin},
	}}); err != nil {
		t.Fatal(err)
	}
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { http.Error(w, "unused", http.StatusTeapot) }))
	t.Cleanup(upstream.Close)
	ca := filepath.Join(directory, "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: upstream.Certificate().Raw}), 0o600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	profiles := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal"), "work": sampleSummary("work")}}
	gateway, err := access.New(ctx, access.Config{UsersFile: registry, SessionUpstreamURL: upstream.URL, SessionCAFile: ca, SessionTLSName: "example.com"},
		"https://adapter.example", "https://sessions.example", access.StaticProfiles([]string{"personal", "work"}),
		func(context.Context, string, string) error { return nil }, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example",
		slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	do := func(method, target string, form url.Values, cookies ...*http.Cookie) *httptest.ResponseRecorder {
		var body io.Reader
		if form != nil {
			body = strings.NewReader(form.Encode())
		}
		r := httptest.NewRequest(method, target, body)
		if form != nil {
			r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
			r.Header.Set("Origin", "https://adapter.example")
		}
		for _, cookie := range cookies {
			r.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		server.ServeHTTP(w, r)
		return w
	}
	cookieNamed := func(response *httptest.ResponseRecorder, name string) *http.Cookie {
		for _, cookie := range response.Result().Cookies() {
			if cookie.Name == name {
				return cookie
			}
		}
		t.Fatalf("missing cookie %s", name)
		return nil
	}
	login := func(actor string) *http.Cookie {
		challenge := cookieNamed(do(http.MethodGet, "https://adapter.example/auth/login", nil), "__Host-bp_login")
		result := do(http.MethodPost, "https://adapter.example/auth/login", url.Values{"username": {actor}, "password": {password}, "csrf": {challenge.Value}}, challenge)
		if result.Code != http.StatusSeeOther {
			t.Fatalf("login %s: %d %s", actor, result.Code, result.Body.String())
		}
		return cookieNamed(result, "__Host-bp_entry")
	}
	if anonymous := do(http.MethodGet, "https://adapter.example/manage/environments", nil); anonymous.Code != http.StatusUnauthorized || len(profiles.environmentCalls) != 0 {
		t.Fatalf("anonymous list: %d", anonymous.Code)
	}
	alice := login("alice")
	list := do(http.MethodGet, "https://adapter.example/manage/environments", nil, alice)
	if list.Code != http.StatusForbidden || len(profiles.environmentCalls) != 0 || strings.Contains(list.Body.String(), "personal") {
		t.Fatalf("entry account list: %d %s", list.Code, list.Body.String())
	}
	bob := login("bob")
	both := do(http.MethodGet, "https://adapter.example/manage/environments", nil, bob)
	var decoded environmentList
	if both.Code != http.StatusOK || json.Unmarshal(both.Body.Bytes(), &decoded) != nil || decoded.Subject != "bob" || len(decoded.Environments) != 2 || decoded.Environments[0].ProfileID != "personal" || decoded.Environments[1].ProfileID != "work" {
		t.Fatalf("admin list: %d %s", both.Code, both.Body.String())
	}
	if strings.Join(decoded.Environments[0].Accounts, ",") != "alice,bob" || strings.Join(decoded.Environments[1].Accounts, ",") != "bob" {
		t.Fatalf("assigned accounts: %+v", decoded.Environments)
	}
	page := do(http.MethodGet, "https://adapter.example/manage/", nil, bob)
	if page.Code != http.StatusOK || !strings.Contains(page.Body.String(), "管理员 bob") || !strings.Contains(page.Body.String(), "https://adapter.example/browser/work/") || !strings.Contains(page.Body.String(), "alice") {
		t.Fatalf("admin page: %d %s", page.Code, page.Body.String())
	}
	if strings.Contains(page.Body.String(), "password_hash") || strings.Contains(page.Body.String(), "pbkdf2") {
		t.Fatal("page exposes verifiers")
	}
	csrf := func(cookie *http.Cookie) string {
		entry := do(http.MethodGet, "https://adapter.example/manage/environments", nil, cookie)
		var value environmentList
		_ = json.Unmarshal(entry.Body.Bytes(), &value)
		// The CSRF token is only rendered into HTML forms; read it from the page.
		body := do(http.MethodGet, "https://adapter.example/manage/", nil, cookie).Body.String()
		marker := `name="csrf" value="`
		start := strings.Index(body, marker) + len(marker)
		return body[start : start+43]
	}
	token := csrf(bob)
	// Create an entry account from the panel; it can log in and open its browser only.
	created := do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"carol"}, "password": {"carol-synthetic-password"}, "role": {"user"}, "profiles": {"work"}}, bob)
	if created.Code != http.StatusSeeOther || created.Header().Get("Location") != "/manage/?notice=account_created" {
		t.Fatalf("create account: %d %s %s", created.Code, created.Header().Get("Location"), created.Body.String())
	}
	if do(http.MethodGet, "https://adapter.example/manage/", nil, bob).Code != http.StatusOK {
		t.Fatal("administrator was logged out by creating another account")
	}
	challenge := cookieNamed(do(http.MethodGet, "https://adapter.example/auth/login", nil), "__Host-bp_login")
	carolLogin := do(http.MethodPost, "https://adapter.example/auth/login", url.Values{"username": {"carol"}, "password": {"carol-synthetic-password"}, "csrf": {challenge.Value}}, challenge)
	carol := cookieNamed(carolLogin, "__Host-bp_entry")
	if do(http.MethodGet, "https://adapter.example/browser/work/", nil, carol).Code != http.StatusOK || do(http.MethodGet, "https://adapter.example/browser/personal/", nil, carol).Code != http.StatusNotFound || do(http.MethodGet, "https://adapter.example/manage/", nil, carol).Code != http.StatusForbidden {
		t.Fatal("created entry account has the wrong reach")
	}
	// Creating an administrator requires a recent password confirmation.
	if do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"dave"}, "password": {"dave-synthetic-password"}, "role": {"admin"}}, bob).Header().Get("Location") != "/manage/?notice=reauth" {
		t.Fatal("administrator created without re-authentication")
	}
	if do(http.MethodPost, "https://adapter.example/auth/reauth", url.Values{"csrf": {token}, "password": {password}, "next": {"/manage/"}}, bob).Code != http.StatusSeeOther {
		t.Fatal("reauth failed")
	}
	if do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"dave"}, "password": {"dave-synthetic-password"}, "role": {"admin"}}, bob).Header().Get("Location") != "/manage/?notice=account_created" {
		t.Fatal("administrator not created after re-authentication")
	}
	// Stop through the real gateway, then confirm nothing launched or collected health.
	stop := do(http.MethodPost, "https://adapter.example/manage/browsers/work", url.Values{"csrf": {token}, "action": {"stop"}}, bob)
	if stop.Code != http.StatusSeeOther || strings.Join(profiles.stopCalls, ",") != "work" {
		t.Fatalf("stop via gateway: %d calls=%v", stop.Code, profiles.stopCalls)
	}
	if do(http.MethodPost, "https://adapter.example/manage/browsers/work", url.Values{"csrf": {token}, "action": {"stop"}}, carol).Code != http.StatusForbidden || len(profiles.stopCalls) != 1 {
		t.Fatal("entry account stopped a browser")
	}
	if do(http.MethodGet, "https://adapter.example/browser/work/health", nil, alice).Code != http.StatusNotFound {
		t.Fatal("management grants widened the fixed-entry authorization")
	}
	if profiles.ensureCalls != 0 || profiles.healthCalls != 0 {
		t.Fatalf("management requests changed lifecycle or collected health: ensure=%d health=%d", profiles.ensureCalls, profiles.healthCalls)
	}
}
