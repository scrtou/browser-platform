package access

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

const personalSession = "2d3aaeda-bf75-4a4e-b31d-44dd999a713f"
const workSession = "047ed0e0-caaa-444c-86e8-4b0b6c4c15ff"
const testPassword = "synthetic-test-password-not-a-real-secret"

var verifierOnce sync.Once
var verifier string

func testVerifier(t *testing.T) string {
	t.Helper()
	verifierOnce.Do(func() { verifier, _ = HashPassword(testPassword) })
	if verifier == "" {
		t.Fatal("password verifier unavailable")
	}
	return verifier
}

type fixture struct {
	g              *Gateway
	handler        http.Handler
	calls          atomic.Int64
	bindings       atomic.Int64
	upstream       atomic.Int64
	registry       string
	logs           bytes.Buffer
	last           chan http.Header
	invalidBinding atomic.Bool
}

func newFixture(t *testing.T, options ...func(*Config)) *fixture {
	t.Helper()
	f := &fixture{last: make(chan http.Header, 128)}
	backend := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.upstream.Add(1)
		f.last <- r.Header.Clone()
		if r.Header.Get(backendAuthHeader) != "synthetic-backend-access-token" {
			http.Error(w, "private authentication required", http.StatusUnauthorized)
			return
		}
		if strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
			conn, buf, err := w.(http.Hijacker).Hijack()
			if err != nil {
				return
			}
			defer conn.Close()
			digest := sha1.Sum([]byte(r.Header.Get("Sec-WebSocket-Key") + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
			_, _ = buf.WriteString("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: " + base64.StdEncoding.EncodeToString(digest[:]) + "\r\n\r\n")
			_ = buf.Flush()
			_, _ = io.Copy(conn, conn)
			return
		}
		if r.URL.Query().Get("redirect") != "" {
			w.Header().Set("Location", "https://outside.invalid/?access_token=synthetic-private-token")
			w.WriteHeader(http.StatusSeeOther)
			return
		}
		w.Header().Set("Access-Control-Allow-Origin", "https://evil.invalid")
		w.Header().Set("X-Upstream-Auth", "synthetic-private-upstream-auth")
		w.Header().Set("Set-Cookie", "sealskin_session=synthetic-backend-access-token; Path=/; Secure")
		_, _ = w.Write([]byte("display"))
	}))
	t.Cleanup(backend.Close)
	directory := t.TempDir()
	if err := os.Chmod(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	f.registry = filepath.Join(directory, "users.json")
	users := Registry{Version: 1, Users: []Account{
		{ID: "alice", PasswordHash: testVerifier(t), Profiles: []string{"personal"}},
		{ID: "bob", PasswordHash: testVerifier(t), Profiles: []string{"work"}},
	}}
	if err := WriteRegistry(f.registry, users); err != nil {
		t.Fatal(err)
	}
	ca := filepath.Join(directory, "ca.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: backend.Certificate().Raw}), 0o600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	var err error
	cfg := Config{UsersFile: f.registry, SessionUpstreamURL: backend.URL, SessionCAFile: ca, SessionTLSName: "example.com"}
	for _, option := range options {
		option(&cfg)
	}
	f.g, err = New(ctx, cfg,
		"https://entry.test", "https://session.test", []string{"personal", "work"},
		func(ctx context.Context, profile, session string) error {
			f.bindings.Add(1)
			if f.invalidBinding.Load() {
				return errors.New("binding changed")
			}
			if (profile == "personal" && session == personalSession) || (profile == "work" && session == workSession) {
				return nil
			}
			return errors.New("binding mismatch")
		}, slog.New(slog.NewJSONHandler(&f.logs, nil)))
	if err != nil {
		t.Fatal(err)
	}
	f.handler = f.g.Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.calls.Add(1)
		if r.Method == http.MethodPost {
			profile := profilePath(r.URL.Path)
			session := personalSession
			if profile == "work" {
				session = workSession
			}
			target, err := f.g.Grant(r, profile, session, "https://session.test/"+session+"/?access_token=synthetic-backend-access-token&embedded=true")
			if err != nil {
				http.Error(w, "grant failed", 503)
				return
			}
			http.Redirect(w, r, target, 303)
			return
		}
		_, _ = w.Write([]byte(CSRF(r)))
	}))
	return f
}

func request(handler http.Handler, method, target string, form url.Values, cookies ...*http.Cookie) *httptest.ResponseRecorder {
	var body io.Reader
	if form != nil {
		body = strings.NewReader(form.Encode())
	}
	r := httptest.NewRequest(method, target, body)
	if form != nil {
		r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		r.Header.Set("Origin", "https://entry.test")
	}
	for _, cookie := range cookies {
		r.AddCookie(cookie)
	}
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	return w
}

func responseCookie(t *testing.T, response *httptest.ResponseRecorder, name string) *http.Cookie {
	t.Helper()
	for _, cookie := range response.Result().Cookies() {
		if cookie.Name == name {
			if !cookie.HttpOnly || !cookie.Secure || cookie.Path != "/" || cookie.Domain != "" || cookie.SameSite != http.SameSiteLaxMode {
				t.Fatal("cookie attributes do not enforce the intended host boundary")
			}
			return cookie
		}
	}
	t.Fatalf("missing cookie %s", name)
	return nil
}

func (f *fixture) login(t *testing.T, actor string) (*http.Cookie, string) {
	t.Helper()
	initial := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	challenge := responseCookie(t, initial, loginCookie)
	result := request(f.handler, "POST", "https://entry.test/auth/login", url.Values{
		"username": {actor}, "password": {testPassword}, "csrf": {challenge.Value},
	}, challenge)
	if result.Code != 303 {
		t.Fatalf("login status %d: %s", result.Code, result.Body.String())
	}
	cookie := responseCookie(t, result, entryCookie)
	profile := "personal"
	if actor == "bob" {
		profile = "work"
	}
	page := request(f.handler, "GET", "https://entry.test/browser/"+profile+"/", nil, cookie)
	if page.Code != 200 || page.Body.Len() != 43 {
		t.Fatal("authenticated entry did not receive a CSRF token")
	}
	return cookie, page.Body.String()
}

func (f *fixture) display(t *testing.T, actor, profile string) (*http.Cookie, string, *http.Cookie) {
	t.Helper()
	cookie, csrf := f.login(t, actor)
	grant := request(f.handler, "POST", "https://entry.test/browser/"+profile+"/start", url.Values{"csrf": {csrf}}, cookie)
	if grant.Code != 303 || strings.Contains(grant.Header().Get("Location"), "access_token") {
		t.Fatalf("entry did not issue a private handoff: %d", grant.Code)
	}
	accept := request(f.handler, "GET", grant.Header().Get("Location"), nil)
	if accept.Code != 303 {
		t.Fatalf("handoff failed: %d", accept.Code)
	}
	session := personalSession
	if profile == "work" {
		session = workSession
	}
	display := responseCookie(t, accept, displayCookie+session)
	replay := request(f.handler, "GET", grant.Header().Get("Location"), nil)
	if replay.Code != 403 {
		t.Fatal("handoff replay accepted")
	}
	return cookie, csrf, display
}

func TestUnauthenticatedAndCrossAccountRequestsDoNotReachProfiles(t *testing.T) {
	f := newFixture(t)
	for _, scenario := range []struct {
		method, path string
		status       int
	}{
		{"GET", "/browser/personal/", 303}, {"GET", "/browser/personal/health", 401}, {"POST", "/browser/personal/start", 401},
	} {
		response := request(f.handler, scenario.method, "https://entry.test"+scenario.path, nil)
		if response.Code != scenario.status || f.calls.Load() != 0 {
			t.Fatalf("unauthenticated request reached profiles: %d", response.Code)
		}
	}
	cookie, csrf := f.login(t, "alice")
	before := f.calls.Load()
	for _, scenario := range []struct{ method, path string }{{"GET", "/browser/work/"}, {"GET", "/browser/work/health"}, {"POST", "/browser/work/start"}} {
		response := request(f.handler, scenario.method, "https://entry.test"+scenario.path, url.Values{"csrf": {csrf}}, cookie)
		if response.Code != 404 || f.calls.Load() != before {
			t.Fatal("cross-account Profile request was evaluated")
		}
	}
	duplicate := request(f.handler, "GET", "https://entry.test/browser/personal/", nil, cookie, cookie)
	if duplicate.Code != 303 || f.calls.Load() != before {
		t.Fatal("duplicate login cookies were accepted")
	}
}

func TestCSRFAndOriginAreRequiredBeforeMutation(t *testing.T) {
	f := newFixture(t)
	cookie, csrf := f.login(t, "alice")
	before := f.calls.Load()
	for _, origin := range []string{"", "null", "https://entry.test/", "https://user@entry.test", "https://entry.test/path", "https://entry.test?x=y", "https://elsewhere.test"} {
		r := httptest.NewRequest("POST", "https://entry.test/browser/personal/start", strings.NewReader(url.Values{"csrf": {csrf}}.Encode()))
		r.Header.Set("Origin", origin)
		r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		r.AddCookie(cookie)
		w := httptest.NewRecorder()
		f.handler.ServeHTTP(w, r)
		if w.Code != 403 || f.calls.Load() != before {
			t.Errorf("invalid Origin %q reached mutation", origin)
		}
	}
	for _, values := range []url.Values{{}, {"csrf": {"incorrect"}}, {"csrf": {csrf, csrf}}} {
		w := request(f.handler, "POST", "https://entry.test/browser/personal/start", values, cookie)
		if w.Code != 403 || f.calls.Load() != before {
			t.Fatal("invalid CSRF reached mutation")
		}
	}
}

func TestDisplayBindingHeadersRedirectAndLogout(t *testing.T) {
	f := newFixture(t)
	entry, csrf, display := f.display(t, "alice", "personal")
	r := httptest.NewRequest("GET", "https://session.test/"+personalSession+"/", nil)
	r.AddCookie(display)
	r.AddCookie(&http.Cookie{Name: "backend_cookie", Value: "synthetic-backend-cookie"})
	r.Header.Set("X-Auth-User", "bob")
	r.Header.Set("X-Upstream-Auth", "synthetic-attacker-auth")
	r.Header.Set("Authorization", "Bearer synthetic-attacker-bearer")
	r.Header.Set("X-Forwarded-Host", "outside.invalid")
	r.Header.Set(backendAuthHeader, "synthetic-attacker-capability")
	w := httptest.NewRecorder()
	f.handler.ServeHTTP(w, r)
	if w.Code != 200 || w.Body.String() != "display" || w.Header().Get("Access-Control-Allow-Origin") != "" || w.Header().Get("X-Upstream-Auth") != "" || w.Header().Get("Set-Cookie") != "" {
		t.Fatalf("valid display proxy failed: %d", w.Code)
	}
	headers := <-f.last
	if headers.Get("Authorization") != "" || headers.Get("X-Auth-User") != "" || headers.Get("X-Upstream-Auth") != "" || strings.Contains(headers.Get("Cookie"), display.Value) || headers.Get("X-Forwarded-Host") != "session.test" {
		t.Fatal("untrusted identity or portal credentials reached the backend")
	}
	if headers.Get(backendAuthHeader) != "synthetic-backend-access-token" || headers.Get("Cookie") != "" {
		t.Fatal("private authentication was replaced by client cookies or headers")
	}
	if redirected := request(f.handler, "GET", "https://session.test/"+personalSession+"/?redirect=1", nil, display); redirected.Code != 502 || redirected.Header().Get("Location") != "" {
		t.Fatal("upstream redirect escaped the bound Session")
	}
	_, _, other := f.display(t, "bob", "work")
	forged := *other
	forged.Name = displayCookie + personalSession
	before := f.upstream.Load()
	if response := request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, &forged); response.Code != 401 || f.upstream.Load() != before {
		t.Fatal("another account reached the Session")
	}
	logout := request(f.handler, "POST", "https://entry.test/auth/logout", url.Values{"csrf": {csrf}}, entry)
	if logout.Code != 303 {
		t.Fatal("logout failed")
	}
	if response := request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, display); response.Code != 401 || f.upstream.Load() != before {
		t.Fatal("display cookie survived logout")
	}
	for _, secret := range []string{testPassword, display.Value, "synthetic-backend-access-token", "synthetic-attacker-auth", "synthetic-private-token"} {
		if strings.Contains(f.logs.String(), secret) {
			t.Fatal("sensitive data reached ordinary access logs")
		}
	}
}

func TestAccountChangesInvalidateSessionsAndPendingTickets(t *testing.T) {
	f := newFixture(t)
	entry, csrf := f.login(t, "alice")
	grant := request(f.handler, "POST", "https://entry.test/browser/personal/start", url.Values{"csrf": {csrf}}, entry)
	if grant.Code != 303 {
		t.Fatal("grant unavailable")
	}
	if err := os.Remove(f.registry); err != nil {
		t.Fatal(err)
	}
	if f.g.reload() == nil {
		t.Fatal("missing account registry accepted")
	}
	if request(f.handler, "GET", grant.Header().Get("Location"), nil).Code != 403 || request(f.handler, "GET", "https://entry.test/browser/personal/", nil, entry).Code != 303 {
		t.Fatal("account failure kept access alive")
	}
}

func TestLogoutClosesAnAlreadyUpgradedDisplayConnection(t *testing.T) {
	f := newFixture(t)
	entry, csrf, display := f.display(t, "alice", "personal")
	front := httptest.NewServer(f.handler)
	t.Cleanup(front.Close)
	u, _ := url.Parse(front.URL)
	conn, err := net.DialTimeout("tcp", u.Host, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_, _ = io.WriteString(conn, "GET /"+personalSession+"/ws HTTP/1.1\r\nHost: session.test\r\nOrigin: https://session.test\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nCookie: "+display.Name+"="+display.Value+"\r\n\r\n")
	reader := bufio.NewReader(conn)
	response, err := http.ReadResponse(reader, &http.Request{Method: "GET"})
	if err != nil || response.StatusCode != 101 {
		t.Fatalf("display upgrade failed: %v", err)
	}
	request(f.handler, "POST", "https://entry.test/auth/logout", url.Values{"csrf": {csrf}}, entry)
	_ = conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, err = reader.ReadByte()
	if err == nil {
		t.Fatal("display tunnel remained open after logout")
	}
	if timeout, ok := err.(net.Error); ok && timeout.Timeout() {
		t.Fatal("display revocation was not enforced on the existing tunnel")
	}
}

func TestRegistryRejectsPermissiveSymlinkDuplicateAndUnknownGrant(t *testing.T) {
	dir := t.TempDir()
	if err := os.Chmod(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	p := filepath.Join(dir, "users.json")
	registry := Registry{Version: 1, Users: []Account{{ID: "alice", PasswordHash: testVerifier(t), Profiles: []string{"personal"}}}}
	if err := WriteRegistry(p, registry); err != nil {
		t.Fatal(err)
	}
	if _, _, err := ReadRegistry(p, map[string]bool{"work": true}); err == nil {
		t.Fatal("unknown Profile grant accepted")
	}
	link := filepath.Join(dir, "link.json")
	if err := os.Symlink(p, link); err != nil {
		t.Fatal(err)
	}
	if _, _, err := ReadRegistry(link, nil); err == nil {
		t.Fatal("symlink account file accepted")
	}
	_ = os.Chmod(p, 0o644)
	if _, _, err := ReadRegistry(p, nil); err == nil {
		t.Fatal("publicly readable password verifiers accepted")
	}
	registry.Users = append(registry.Users, registry.Users[0])
	if validateRegistry(registry, nil) == nil {
		t.Fatal("duplicate account accepted")
	}
}
