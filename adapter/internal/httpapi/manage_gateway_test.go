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
	if err := access.WriteRegistry(registry, access.Registry{Version: 1, Users: []access.Account{
		{ID: "alice", PasswordHash: verifier, Profiles: []string{"personal"}},
		{ID: "bob", PasswordHash: verifier, Profiles: []string{"work", "personal"}},
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
		"https://adapter.example", "https://sessions.example", []string{"personal", "work"},
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
	var decoded environmentList
	if list.Code != http.StatusOK || json.Unmarshal(list.Body.Bytes(), &decoded) != nil || decoded.Subject != "alice" || len(decoded.Environments) != 1 || decoded.Environments[0].ProfileID != "personal" {
		t.Fatalf("alice list: %d %s", list.Code, list.Body.String())
	}
	if strings.Contains(list.Body.String(), "camoufox-work") || strings.Join(profiles.environmentCalls, ",") != "personal" {
		t.Fatalf("alice saw work: %s calls=%v", list.Body.String(), profiles.environmentCalls)
	}
	page := do(http.MethodGet, "https://adapter.example/manage/", nil, alice)
	if page.Code != http.StatusOK || !strings.Contains(page.Body.String(), "账号 alice") || strings.Contains(page.Body.String(), "/browser/work/") {
		t.Fatalf("alice page: %d %s", page.Code, page.Body.String())
	}
	bob := login("bob")
	both := do(http.MethodGet, "https://adapter.example/manage/environments", nil, bob)
	decoded = environmentList{}
	if both.Code != http.StatusOK || json.Unmarshal(both.Body.Bytes(), &decoded) != nil || len(decoded.Environments) != 2 || decoded.Environments[0].ProfileID != "personal" || decoded.Environments[1].ProfileID != "work" {
		t.Fatalf("bob list: %d %s", both.Code, both.Body.String())
	}
	if do(http.MethodPost, "https://adapter.example/manage/environments", url.Values{"csrf": {"x"}}, bob).Code != http.StatusMethodNotAllowed {
		t.Fatal("POST reached the management surface")
	}
	if do(http.MethodGet, "https://adapter.example/browser/work/health", nil, alice).Code != http.StatusNotFound {
		t.Fatal("management grants widened the fixed-entry authorization")
	}
	if profiles.ensureCalls != 0 || profiles.healthCalls != 0 {
		t.Fatalf("management requests changed lifecycle or collected health: ensure=%d health=%d", profiles.ensureCalls, profiles.healthCalls)
	}
}
