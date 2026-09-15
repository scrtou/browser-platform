package access

import (
	"bufio"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

func loginAttempt(f *fixture, actor, password string) *httptest.ResponseRecorder {
	initial := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	var challenge *http.Cookie
	for _, cookie := range initial.Result().Cookies() {
		if cookie.Name == loginCookie {
			challenge = cookie
		}
	}
	if challenge == nil {
		return initial
	}
	return request(f.handler, "POST", "https://entry.test/auth/login", url.Values{
		"username": {actor}, "password": {password}, "csrf": {challenge.Value},
	}, challenge)
}

func TestInvalidDisabledAndThrottledLoginsNeverGrantAccess(t *testing.T) {
	f := newFixture(t)
	for _, actor := range []string{"alice", "unknown"} {
		if got := loginAttempt(f, actor, "incorrect-test-password"); got.Code != 401 || len(got.Result().Cookies()) != 0 {
			t.Fatal("incorrect or unknown credentials received a login")
		}
	}
	registry, _, _ := ReadRegistry(f.registry, nil)
	registry.Users[0].Disabled = true
	if WriteRegistry(f.registry, registry) != nil || f.g.reload() != nil {
		t.Fatal("disable failed")
	}
	for i := 0; i < 6; i++ {
		if loginAttempt(f, "alice", testPassword).Code != 401 {
			t.Fatal("disabled account was not rejected")
		}
	}
	if loginAttempt(f, "bob", testPassword).Code != 429 {
		t.Fatal("source rate limit was not enforced")
	}
	if f.calls.Load() != 0 || f.upstream.Load() != 0 {
		t.Fatal("failed login reached business state")
	}
}

func TestKDFConcurrencyLimitAndLoginCSRF(t *testing.T) {
	f := newFixture(t)
	f.g.passwordSlots <- struct{}{}
	f.g.passwordSlots <- struct{}{}
	if loginAttempt(f, "alice", testPassword).Code != 503 {
		t.Fatal("busy password derivation did not fail closed")
	}
	<-f.g.passwordSlots
	<-f.g.passwordSlots
	initial := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	challenge := responseCookie(t, initial, loginCookie)
	if initial.Header().Get("Referrer-Policy") != "same-origin" {
		t.Fatal("form would lose its Origin in Chromium")
	}
	for _, form := range []url.Values{
		{"username": {"alice"}, "password": {testPassword}},
		{"username": {"alice", "bob"}, "password": {testPassword}, "csrf": {challenge.Value}},
		{"username": {"alice"}, "password": {strings.Repeat("x", 257)}, "csrf": {challenge.Value}},
	} {
		result := request(f.handler, "POST", "https://entry.test/auth/login", form, challenge)
		if result.Code != 400 && result.Code != 403 {
			t.Fatal("malformed login was accepted")
		}
	}
	if f.calls.Load() != 0 {
		t.Fatal("invalid login reached profiles")
	}
}

func TestHandoffIsAtomicAndExpires(t *testing.T) {
	f := newFixture(t, func(c *Config) { c.TicketSeconds = 1 })
	entry, csrf := f.login(t, "alice")
	grant := func() string {
		response := request(f.handler, "POST", "https://entry.test/browser/personal/start", url.Values{"csrf": {csrf}}, entry)
		if response.Code != 303 {
			t.Fatal("handoff could not be issued")
		}
		return response.Header().Get("Location")
	}
	target := grant()
	var wg sync.WaitGroup
	statuses := make(chan int, 12)
	for range 12 {
		wg.Add(1)
		go func() { defer wg.Done(); statuses <- request(f.handler, "GET", target, nil).Code }()
	}
	wg.Wait()
	close(statuses)
	accepted := 0
	for status := range statuses {
		if status == 303 {
			accepted++
		} else if status != 403 {
			t.Fatalf("unexpected handoff result: %d", status)
		}
	}
	if accepted != 1 {
		t.Fatalf("handoff accepted %d times", accepted)
	}
	target = grant()
	time.Sleep(1150 * time.Millisecond)
	if request(f.handler, "GET", target, nil).Code != 403 {
		t.Fatal("expired handoff accepted")
	}
	target = grant()
	f.invalidBinding.Store(true)
	if request(f.handler, "GET", target, nil).Code != 403 {
		t.Fatal("changed binding accepted")
	}
}

func openDisplay(t *testing.T, f *fixture, cookie *http.Cookie) (net.Conn, *bufio.Reader) {
	t.Helper()
	front := httptest.NewServer(f.handler)
	t.Cleanup(front.Close)
	u, _ := url.Parse(front.URL)
	conn, err := net.DialTimeout("tcp", u.Host, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = io.WriteString(conn, "GET /"+personalSession+"/ws HTTP/1.1\r\nHost: session.test\r\nOrigin: https://session.test\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nCookie: "+cookie.Name+"="+cookie.Value+"\r\n\r\n")
	reader := bufio.NewReader(conn)
	response, err := http.ReadResponse(reader, &http.Request{Method: "GET"})
	if err != nil || response.StatusCode != 101 {
		conn.Close()
		t.Fatalf("upgrade failed: %v", err)
	}
	return conn, reader
}

func TestHandoffNeverReturnsBackendCapability(t *testing.T) {
	f := newFixture(t)
	entry, csrf := f.login(t, "alice")
	grant := request(f.handler, "POST", "https://entry.test/browser/personal/start", url.Values{"csrf": {csrf}}, entry)
	accepted := request(f.handler, "GET", grant.Header().Get("Location"), nil)
	if accepted.Code != 303 || strings.Contains(accepted.Header().Get("Location"), "access_token") ||
		strings.Contains(accepted.Body.String(), "synthetic-backend-access-token") {
		t.Fatal("redeemed handoff exposed backend capability")
	}
	display := responseCookie(t, accepted, displayCookie+personalSession)
	before := f.upstream.Load()
	for _, key := range []string{"access_token", "token", "ticket"} {
		result := request(f.handler, "GET", "https://session.test/"+personalSession+"/?"+key+"=untrusted", nil, display)
		if result.Code != 403 || f.upstream.Load() != before {
			t.Fatal("client capability query reached the backend")
		}
	}
}

func TestRepeatedHandoffPreservesTheExistingDisplayConnection(t *testing.T) {
	f := newFixture(t)
	entry, csrf, display := f.display(t, "alice", "personal")
	conn, reader := openDisplay(t, f, display)
	defer conn.Close()
	grant := request(f.handler, "POST", "https://entry.test/browser/personal/start", url.Values{"csrf": {csrf}}, entry)
	accepted := request(f.handler, "GET", grant.Header().Get("Location"), nil, display)
	if accepted.Code != 303 || responseCookie(t, accepted, displayCookie+personalSession).Value != display.Value {
		t.Fatal("same-login handoff replaced an existing display authorization")
	}
	_ = conn.SetDeadline(time.Now().Add(time.Second))
	if _, err := conn.Write([]byte("ping")); err != nil {
		t.Fatal("existing connection was closed")
	}
	buf := make([]byte, 4)
	if _, err := io.ReadFull(reader, buf); err != nil || string(buf) != "ping" {
		t.Fatal("existing connection stopped forwarding")
	}
	request(f.handler, "POST", "https://entry.test/auth/logout", url.Values{"csrf": {csrf}}, entry)
	_ = conn.SetReadDeadline(time.Now().Add(time.Second))
	_, err := reader.ReadByte()
	if err == nil {
		t.Fatal("reused display survived logout")
	}
	if timeout, ok := err.(net.Error); ok && timeout.Timeout() {
		t.Fatal("logout did not close the reused connection")
	}
}

func TestWatchRevocationAndDeadlineCloseAlreadyUpgradedConnections(t *testing.T) {
	for _, reason := range []string{"disabled", "binding", "deadline", "missing_registry"} {
		t.Run(reason, func(t *testing.T) {
			f := newFixture(t, func(c *Config) { c.SessionSeconds = 5 })
			entry, _, display := f.display(t, "alice", "personal")
			conn, reader := openDisplay(t, f, display)
			defer conn.Close()
			before := f.calls.Load()
			switch reason {
			case "disabled":
				registry, _, _ := ReadRegistry(f.registry, nil)
				registry.Users[0].Disabled = true
				if err := WriteRegistry(f.registry, registry); err != nil {
					t.Fatal(err)
				}
			case "binding":
				f.invalidBinding.Store(true)
			case "missing_registry":
				if err := os.Remove(f.registry); err != nil {
					t.Fatal(err)
				}
			}
			_ = conn.SetReadDeadline(time.Now().Add(6 * time.Second))
			_, err := reader.ReadByte()
			if err == nil {
				t.Fatal("revoked display remained open")
			}
			if timeout, ok := err.(net.Error); ok && timeout.Timeout() {
				t.Fatal("revocation did not close the tunnel")
			}
			if f.calls.Load() != before {
				t.Fatal("revocation mutated Profile lifecycle")
			}
			if reason != "binding" && request(f.handler, "GET", "https://entry.test/browser/personal/", nil, entry).Code != 303 {
				t.Fatal("revoked entry cookie still accepted")
			}
			if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, display).Code != 401 {
				t.Fatal("revoked display credential still accepted")
			}
		})
	}
}

func TestSessionPathsOriginAndTLSAreEnforcedBeforeDisplay(t *testing.T) {
	f := newFixture(t)
	_, _, cookie := f.display(t, "alice", "personal")
	before := f.upstream.Load()
	for _, path := range []string{"/api/sessions", "/internal/resolve", "/" + personalSession + "/../" + workSession + "/", "/" + personalSession + "/%2e%2e/", "/%32d3aaeda-bf75-4a4e-b31d-44dd999a713f/", "/" + personalSession + "/back%5cslash"} {
		if result := request(f.handler, "GET", "https://session.test"+path, nil, cookie); result.Code != 404 {
			t.Fatalf("invalid Session path accepted: %d", result.Code)
		}
	}
	for _, origin := range []string{"null", "https://session.test/path", "https://evil.invalid"} {
		r := httptest.NewRequest("GET", "https://session.test/"+personalSession+"/", nil)
		r.AddCookie(cookie)
		r.Header.Set("Origin", origin)
		response := httptest.NewRecorder()
		f.handler.ServeHTTP(response, r)
		if response.Code != 403 {
			t.Fatal("invalid display Origin accepted")
		}
	}
	if f.upstream.Load() != before {
		t.Fatal("invalid display request reached backend")
	}
	cfg := f.g.cfg
	cfg.SessionTLSName = "wrong-name.invalid"
	transport, err := SessionTransport(cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: time.Second}
	if _, err := client.Get(cfg.SessionUpstreamURL); err == nil {
		t.Fatal("mismatched upstream TLS name accepted")
	}
	if f.upstream.Load() != before {
		t.Fatal("TLS failure sent an authenticated HTTP request")
	}
}
