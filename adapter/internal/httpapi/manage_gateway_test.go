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
	// The new query selects only the view: every pane keeps the real admin gate.
	for _, tab := range []string{"browsers", "jobs", "fingerprints", "displays", "fingerprint-data&section=fingerprints", "fingerprint-data&section=displays", "fingerprint-data&section=combinations", "accounts"} {
		target := "https://adapter.example/manage/?tab=" + tab
		if do(http.MethodGet, target, nil).Code != http.StatusSeeOther || do(http.MethodGet, target, nil, alice).Code != http.StatusForbidden {
			t.Fatalf("tab %s bypassed the login/admin gate", tab)
		}
		body := do(http.MethodGet, target, nil, bob).Body.String()
		if strings.Contains(body, "password_hash") || strings.Contains(body, "pbkdf2") {
			t.Fatalf("tab %s exposes verifiers", tab)
		}
		if tab == "accounts" && (!strings.Contains(body, `action="/manage/accounts/alice"`) || !strings.Contains(body, `action="/manage/accounts/bob"`)) {
			t.Fatal("account row forms missing on the account tab")
		}
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
	createManager := linkedCreateFixture()
	createServer := New(createManager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example",
		slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	for _, tc := range []struct {
		cookie       *http.Cookie
		csrf, origin string
		allowed      bool
	}{
		{nil, token, "https://adapter.example", false}, {alice, token, "https://adapter.example", false},
		{bob, "invalid", "https://adapter.example", false}, {bob, token, "https://foreign.example", false},
		{bob, token, "https://adapter.example", true},
	} {
		createManager.createKey = ""
		values := url.Values{"csrf": {tc.csrf}, "label": {"linked"}, "start_url": {"https://start.example"}, "idempotency_key": {"gateway-linked"},
			"browser_template_id": {"firefox"}, "environment_artifact_id": {"firefox-auto"}, "network_selection": {"direct"}}
		r := httptest.NewRequest("POST", "https://adapter.example/manage/browsers", strings.NewReader(values.Encode()))
		r.Header.Set("Origin", tc.origin)
		r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		if tc.cookie != nil {
			r.AddCookie(tc.cookie)
		}
		w := httptest.NewRecorder()
		createServer.ServeHTTP(w, r)
		if (createManager.createKey != "") != tc.allowed {
			t.Fatalf("linked create gateway mismatch: %d allowed=%v", w.Code, tc.allowed)
		}
		if tc.allowed && (createManager.createRequest.DisplayTemplateID != "auto" || w.Header().Get("Location") != "/manage/?notice=created") {
			t.Fatal("authenticated create lost its accepted display binding")
		}
	}

	templateService := &sourceForms{fakeEnvironmentJobs: &fakeEnvironmentJobs{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: profiles, capabilities: profile.ManagementCapabilities{EnvironmentJobs: true}}}}
	templateServer := New(templateService, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	for _, path := range []string{"fingerprint-templates", "display-templates", "template-combinations"} {
		for _, tc := range []struct {
			cookie       *http.Cookie
			csrf, origin string
			allowed      bool
		}{{nil, token, "https://adapter.example", false}, {alice, token, "https://adapter.example", false}, {bob, "wrong", "https://adapter.example", false}, {bob, token, "https://foreign.example", false}, {bob, token, "https://adapter.example", true}} {
			before := templateService.calls
			values := url.Values{"csrf": {tc.csrf}}
			if path == "template-combinations" {
				values.Set("browser_template_id", "camoufox-linux-v152")
			}
			r := httptest.NewRequest("POST", "https://adapter.example/manage/"+path, strings.NewReader(values.Encode()))
			r.Header.Set("Origin", tc.origin)
			r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
			if tc.cookie != nil {
				r.AddCookie(tc.cookie)
			}
			w := httptest.NewRecorder()
			templateServer.ServeHTTP(w, r)
			if (templateService.calls > before) != tc.allowed {
				t.Fatalf("template route %s authorization bypass or valid request denied: %d", path, w.Code)
			}
		}
	}
	migrationProfiles := &fakeLegacyMigrator{fakeProfiles: profiles}
	migrationServer := New(migrationProfiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example",
		slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	migrationWrite := func(cookie *http.Cookie, csrfValue, origin string) *httptest.ResponseRecorder {
		values := url.Values{"csrf": {csrfValue}, "action": {"legacy_network_migrate"}, "revision": {"4"}, "migration_id": {"work-direct"}, "idempotency_key": {"migrate-1"}, "image": {"untrusted:latest"}}
		request := httptest.NewRequest(http.MethodPost, "https://adapter.example/manage/browsers/work", strings.NewReader(values.Encode()))
		request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		request.Header.Set("Origin", origin)
		if cookie != nil {
			request.AddCookie(cookie)
		}
		response := httptest.NewRecorder()
		migrationServer.ServeHTTP(response, request)
		return response
	}
	for _, test := range []struct {
		cookie       *http.Cookie
		csrf, origin string
	}{
		{nil, token, "https://adapter.example"}, {alice, token, "https://adapter.example"},
		{bob, "invalid", "https://adapter.example"}, {bob, token, "https://foreign.example"}, {bob, token, "https://adapter.example"},
	} {
		migrationWrite(test.cookie, test.csrf, test.origin)
		if len(migrationProfiles.calls) != 0 {
			t.Fatal("legacy migration bypassed login/admin/CSRF/Origin/recent authentication")
		}
	}
	selectionManager := networkSelectionFixture()
	selectionServer := New(selectionManager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	checkSelectionGateway := func(confirmed bool) {
		for _, selection := range []string{"direct", "proxy|corp|3"} {
			for _, tc := range []struct {
				cookie       *http.Cookie
				csrf, origin string
				valid        bool
			}{
				{nil, token, "https://adapter.example", false}, {alice, token, "https://adapter.example", false},
				{bob, "wrong", "https://adapter.example", false}, {bob, token, "https://foreign.example", false}, {bob, token, "https://adapter.example", true},
			} {
				selectionManager.directCall, selectionManager.lastBind = "", ""
				v := url.Values{"csrf": {tc.csrf}, "action": {"network_select"}, "revision": {"3"}, "network_selection": {selection}, "idempotency_key": {"select-gateway"}}
				r := httptest.NewRequest("POST", "https://adapter.example/manage/browsers/personal", strings.NewReader(v.Encode()))
				r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
				r.Header.Set("Origin", tc.origin)
				if tc.cookie != nil {
					r.AddCookie(tc.cookie)
				}
				w := httptest.NewRecorder()
				selectionServer.ServeHTTP(w, r)
				applied := selectionManager.directCall != "" || selectionManager.lastBind != ""
				if applied != (tc.valid && confirmed) {
					t.Fatalf("network select gateway: %s %d confirmed=%v", selection, w.Code, confirmed)
				}
			}
		}
	}
	checkSelectionGateway(false)

	deletionManager := deletionFixture()
	deletionServer := New(deletionManager, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	deleteNetwork := &deletionNetworkManager{networkSelectionManager: networkSelectionFixture()}
	deleteNetworkServer := New(deleteNetwork, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	if err := gateway.Accounts().Put("disposable", password, access.RoleUser, []string{"personal"}, false); err != nil {
		t.Fatal(err)
	}
	if err := gateway.Reload(); err != nil {
		t.Fatal(err)
	}
	checkDeletionGateway := func(confirmed bool) {
		for _, route := range []string{"fingerprint-templates/item/delete", "display-templates/item/delete", "template-combinations/item/delete", "environment-jobs/item/delete", "network-profiles", "accounts/disposable"} {
			for _, tc := range []struct {
				cookie                *http.Cookie
				csrf, origin, confirm string
				valid                 bool
			}{
				{nil, token, "https://adapter.example", "delete", false}, {alice, token, "https://adapter.example", "delete", false},
				{bob, "wrong", "https://adapter.example", "delete", false}, {bob, token, "https://foreign.example", "delete", false},
				{bob, token, "https://adapter.example", "", false}, {bob, token, "https://adapter.example", "delete", true},
			} {
				v := url.Values{"csrf": {tc.csrf}, "confirm": {tc.confirm}}
				targetServer := deletionServer
				if route == "network-profiles" {
					targetServer = deleteNetworkServer
					v.Set("action", "delete")
					v.Set("id", "corp")
					v.Set("revision", "2")
					v.Set("idempotency_key", "delete-corp-r2")
				}
				if route == "accounts/disposable" {
					targetServer = server
					v.Set("action", "delete")
				}
				before := len(deletionManager.deleted)
				deleteNetwork.deleted = ""
				r := httptest.NewRequest("POST", "https://adapter.example/manage/"+route, strings.NewReader(v.Encode()))
				if route == "environment-jobs/item/delete" {
					r.Header.Set("Accept", "application/json")
				}
				r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
				r.Header.Set("Origin", tc.origin)
				if tc.cookie != nil {
					r.AddCookie(tc.cookie)
				}
				w := httptest.NewRecorder()
				targetServer.ServeHTTP(w, r)
				if route == "environment-jobs/item/delete" && tc.valid {
					var result struct {
						Done   bool
						Reauth bool
					}
					if json.Unmarshal(w.Body.Bytes(), &result) != nil || result.Done != confirmed || result.Reauth == confirmed {
						t.Fatalf("delete JSON feedback: %s", w.Body.String())
					}
				}

				applied := len(deletionManager.deleted) > before || deleteNetwork.deleted != ""
				if route == "accounts/disposable" {
					rows, err := gateway.Accounts().Snapshot()
					if err != nil {
						t.Fatal(err)
					}
					exists := false
					for _, row := range rows {
						exists = exists || row.ID == "disposable"
					}
					applied = !exists
				}
				if applied != (confirmed && tc.valid) {
					t.Fatalf("delete route %s: status=%d confirmed=%v", route, w.Code, confirmed)
				}
			}
		}
	}
	checkDeletionGateway(false)

	networkBase := &fakeProfiles{environments: map[string]profile.EnvironmentSummary{"personal": sampleSummary("personal"), "work": sampleSummary("work")}}
	networkProfiles := &fakeNetworkProfiles{fakeBrowserManager: &fakeBrowserManager{fakeProfiles: networkBase,
		capabilities: profile.ManagementCapabilities{CreateDelete: true, ProxyDrafts: true, NetworkProfiles: true, TemplateCatalog: true}}}
	networkServer := New(networkProfiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example",
		slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	networkWrite := func(values url.Values) *httptest.ResponseRecorder {
		values.Set("csrf", token)
		request := httptest.NewRequest(http.MethodPost, "https://adapter.example/manage/network-profiles", strings.NewReader(values.Encode()))
		request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		request.Header.Set("Origin", "https://adapter.example")
		request.AddCookie(bob)
		response := httptest.NewRecorder()
		networkServer.ServeHTTP(response, request)
		return response
	}
	for _, values := range []url.Values{
		{"action": {"create"}, "id": {"corp"}, "label": {"Corp"}, "idempotency_key": {"create-corp"}, "protocol": {"socks5"}, "auth": {"none"}, "host": {"proxy.example.net"}, "port": {"1080"}},
		{"action": {"probe"}, "id": {"corp"}, "draft_id": {"draft-corp"}},
	} {
		if response := networkWrite(values); response.Code != http.StatusForbidden || networkProfiles.lastCreate.ID != "" || networkProfiles.lastProbe != "" {
			t.Fatalf("network mutation bypassed re-authentication: %d create=%q probe=%q", response.Code, networkProfiles.lastCreate.ID, networkProfiles.lastProbe)
		}
	}
	proxyServer := New(&fakeProxyDrafts{fakeBrowserManager: networkProfiles.fakeBrowserManager}, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)), HealthUI{}, WithAccess(gateway))
	// Every sensitive action must signal reauthentication before any side effect.
	for _, tc := range []struct {
		handler      http.Handler
		path, action string
	}{
		{networkServer, "/manage/network-profiles", "create"}, {networkServer, "/manage/network-profiles", "probe"},
		{networkServer, "/manage/network-profiles", "disable"}, {networkServer, "/manage/network-profiles", "revoke"}, {networkServer, "/manage/network-profiles", "delete"},
		{networkServer, "/manage/browsers/personal/network-profile", "bind"},
		{networkServer, "/manage/browsers/personal/template", "apply"}, {networkServer, "/manage/browsers/personal/template", "rollback"},
		{networkServer, "/manage/browsers/personal", "delete"}, {proxyServer, "/manage/browsers/personal", "proxy_apply"}, {proxyServer, "/manage/browsers/personal", "network_direct"},
		{selectionServer, "/manage/browsers/personal", "network_direct_managed"}, {selectionServer, "/manage/browsers/personal", "network_select"},
		{migrationServer, "/manage/browsers/work", "legacy_network_migrate"}, {migrationServer, "/manage/browsers/work", "legacy_network_rollback"},
		{server, "/manage/accounts", "create"}, {server, "/manage/accounts/alice", "delete"}, {server, "/manage/accounts/alice", "reset_password"},
		{server, "/manage/accounts/alice", "disable"}, {server, "/manage/accounts/alice", "enable"}, {server, "/manage/accounts/alice", "role"},
	} {
		values := url.Values{"csrf": {token}, "action": {tc.action}, "revision": {"3"}, "idempotency_key": {"original-key"}, "network_selection": {"direct"}, "confirm": {"delete"}, "account": {"modaladmin"}, "password": {"qa-new-password"}, "role": {"admin"}}
		req := httptest.NewRequest("POST", "https://adapter.example"+tc.path, strings.NewReader(values.Encode()))
		req.Header.Set("Origin", "https://adapter.example")
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("Accept", "application/json")
		req.AddCookie(bob)
		res := httptest.NewRecorder()
		tc.handler.ServeHTTP(res, req)
		var result struct {
			Done   bool
			Reauth bool
		}
		if res.Code != 403 || json.Unmarshal(res.Body.Bytes(), &result) != nil || !result.Reauth || result.Done {
			t.Fatalf("sensitive reauth %s %s: %d %s", tc.path, tc.action, res.Code, res.Body.String())
		}
	}
	// Create an entry account from the panel; it can log in and open its browser only.
	created := do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"carol"}, "password": {"carol-synthetic-password"}, "role": {"user"}, "profiles": {"work"}}, bob)
	if created.Code != http.StatusSeeOther || created.Header().Get("Location") != "/manage/?tab=accounts&notice=account_created" {
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
	if do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"dave"}, "password": {"dave-synthetic-password"}, "role": {"admin"}}, bob).Header().Get("Location") != "/manage/?tab=accounts&notice=reauth" {
		t.Fatal("administrator created without re-authentication")
	}
	for _, tab := range []string{"browsers", "jobs", "accounts"} {
		next := "/manage/?tab=" + tab
		prompt := do(http.MethodGet, "https://adapter.example/auth/reauth?next="+url.QueryEscape(next), nil, bob)
		if prompt.Code != http.StatusOK || !strings.Contains(prompt.Body.String(), `name="next" value="`+next+`"`) || !strings.Contains(prompt.Body.String(), `name="password"`) {
			t.Fatalf("reauth form lost tab %s or password input", tab)
		}
		confirmed := do(http.MethodPost, "https://adapter.example/auth/reauth", url.Values{"csrf": {token}, "password": {password}, "next": {next}}, bob)
		if confirmed.Code != http.StatusSeeOther || confirmed.Header().Get("Location") != next {
			t.Fatalf("reauth did not return to %s", tab)
		}
	}
	checkSelectionGateway(true)
	checkDeletionGateway(true)
	if w := do("POST", "https://adapter.example/manage/accounts/bob", url.Values{"csrf": {token}, "action": {"delete"}, "confirm": {"delete"}}, bob); w.Header().Get("Location") != "/manage/?tab=accounts&notice=account_self_delete" {
		t.Fatal("self delete", w.Code)
	}
	writeDeletionFixture(t, "accounts", do("GET", "https://adapter.example/manage/?tab=accounts", nil, bob))
	acceptedNetwork := networkWrite(url.Values{"action": {"create"}, "id": {"corp"}, "label": {"Corp"}, "idempotency_key": {"create-corp"},
		"protocol": {"socks5"}, "auth": {"none"}, "host": {"proxy.example.net"}, "port": {"1080"}})
	if response := migrationWrite(bob, token, "https://adapter.example"); response.Code != http.StatusSeeOther ||
		strings.Join(migrationProfiles.calls, ",") != "work/4/work-direct/bob/migrate-1" {
		t.Fatalf("authenticated migration failed or accepted arbitrary resource fields: %d", response.Code)
	}
	if acceptedNetwork.Code != http.StatusCreated || networkProfiles.lastCreate.ID != "corp" {
		t.Fatalf("network mutation rejected after re-authentication: %d %s", acceptedNetwork.Code, acceptedNetwork.Body.String())
	}
	if do(http.MethodPost, "https://adapter.example/manage/accounts", url.Values{"csrf": {token}, "account": {"dave"}, "password": {"dave-synthetic-password"}, "role": {"admin"}}, bob).Header().Get("Location") != "/manage/?tab=accounts&notice=account_created" {
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
