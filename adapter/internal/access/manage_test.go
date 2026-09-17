package access

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
)

// manageFixture wraps the gateway around a handler that echoes the grants it
// received, so the tests observe exactly what a management handler would see.
func manageFixture(t *testing.T) (*fixture, *int) {
	t.Helper()
	f := newFixture(t)
	reached := 0
	f.handler = f.g.Wrap(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !ManagePath(r.URL.Path) {
			// Keep the fixture's entry behaviour so login() still works.
			_, _ = w.Write([]byte(CSRF(r)))
			return
		}
		reached++
		grants, ok := Grants(r)
		_ = json.NewEncoder(w).Encode(struct {
			Subject string  `json:"subject"`
			OK      bool    `json:"ok"`
			Grants  []Grant `json:"grants"`
			CSRF    string  `json:"csrf"`
		}{Subject(r), ok, grants, CSRF(r)})
	}))
	return f, &reached
}

func TestManagementSurfaceRequiresLoginAndOnlyGetOrHead(t *testing.T) {
	f, reached := manageFixture(t)
	for _, path := range []string{"/manage/", "/manage/environments"} {
		if response := request(f.handler, "GET", "https://entry.test"+path, nil); response.Code != 303 && response.Code != 401 || *reached != 0 {
			t.Fatalf("unauthenticated %s reached management: %d", path, response.Code)
		}
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil); response.Code != 401 {
		t.Fatalf("unauthenticated JSON list must be a plain 401, got %d", response.Code)
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/", nil); response.Code != 303 || response.Header().Get("Location") != "/auth/login" {
		t.Fatalf("unauthenticated page must go to the login without a next hint: %d %s", response.Code, response.Header().Get("Location"))
	}
	cookie, csrf := f.login(t, "alice")
	for _, path := range []string{"/manage/", "/manage/environments"} {
		response := request(f.handler, "POST", "https://entry.test"+path, url.Values{"csrf": {csrf}}, cookie)
		if response.Code != 405 || response.Header().Get("Allow") != "GET, HEAD" || *reached != 0 {
			t.Fatalf("POST %s: %d", path, response.Code)
		}
	}
	for _, path := range []string{"/manage", "/manage/other", "/manage/environments/", "/manage/../manage/"} {
		if response := request(f.handler, "GET", "https://entry.test"+path, nil, cookie); response.Code != 404 || *reached != 0 {
			t.Fatalf("path %s outside the management surface reached the handler: %d", path, response.Code)
		}
	}
}

func TestManagementGrantsAreLimitedToTheLoginAndRevokedWithIt(t *testing.T) {
	f, reached := manageFixture(t)
	cookie, csrf := f.login(t, "alice")
	response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, cookie)
	if response.Code != 200 || *reached != 1 {
		t.Fatalf("authenticated list: %d", response.Code)
	}
	var echo struct {
		Subject string
		OK      bool
		Grants  []Grant
		CSRF    string
	}
	if err := json.Unmarshal(response.Body.Bytes(), &echo); err != nil {
		t.Fatal(err)
	}
	if !echo.OK || echo.Subject != "alice" || len(echo.Grants) != 1 || echo.Grants[0].Profile != "personal" || strings.Join(echo.Grants[0].Capabilities, ",") != "view,start" || echo.CSRF != csrf {
		t.Fatalf("grants: %+v", echo)
	}
	if strings.Contains(response.Body.String(), "work") {
		t.Fatal("another account's Profile was granted")
	}
	head := httptest.NewRequest("HEAD", "https://entry.test/manage/", nil)
	head.AddCookie(cookie)
	headResponse := httptest.NewRecorder()
	f.handler.ServeHTTP(headResponse, head)
	if headResponse.Code != 200 || *reached != 2 {
		t.Fatalf("HEAD: %d", headResponse.Code)
	}
	registry, _, _ := ReadRegistry(f.registry, nil)
	registry.Users[0].Disabled = true
	if WriteRegistry(f.registry, registry) != nil || f.g.reload() != nil {
		t.Fatal("disable failed")
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, cookie); response.Code != 401 || *reached != 2 {
		t.Fatalf("disabled account kept its list: %d", response.Code)
	}
	if err := os.Remove(f.registry); err != nil {
		t.Fatal(err)
	}
	_ = f.g.reload()
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, cookie); response.Code != 401 || *reached != 2 {
		t.Fatalf("missing registry kept the list alive: %d", response.Code)
	}
	if grants := f.g.grants("alice"); grants != nil {
		t.Fatalf("grants without a ready registry: %+v", grants)
	}
}

func TestLogoutRevokesManagementAccess(t *testing.T) {
	f, reached := manageFixture(t)
	cookie, csrf := f.login(t, "bob")
	if response := request(f.handler, "GET", "https://entry.test/manage/", nil, cookie); response.Code != 200 || !strings.Contains(response.Body.String(), `"work"`) || strings.Contains(response.Body.String(), `"personal"`) {
		t.Fatalf("bob's list: %d %s", response.Code, response.Body.String())
	}
	if request(f.handler, "POST", "https://entry.test/auth/logout", url.Values{"csrf": {csrf}}, cookie).Code != 303 {
		t.Fatal("logout failed")
	}
	before := *reached
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, cookie); response.Code != 401 || *reached != before {
		t.Fatalf("logged-out list: %d", response.Code)
	}
	index := request(f.handler, "GET", "https://entry.test/", nil, f.loginCookie(t, "bob"))
	if index.Code != 200 || !strings.Contains(index.Body.String(), `href="/manage/"`) {
		t.Fatalf("index lost the management link: %d", index.Code)
	}
}

func (f *fixture) loginCookie(t *testing.T, actor string) *http.Cookie {
	t.Helper()
	cookie, _ := f.login(t, actor)
	return cookie
}
