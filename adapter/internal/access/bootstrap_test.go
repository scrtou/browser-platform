package access

import (
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestExplicitBootstrapStateRejectsAmbiguousOrCorruptRegistry(t *testing.T) {
	dir := t.TempDir()
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "users.json")
	if _, _, err := ReadRegistry(path, nil); err == nil {
		t.Fatal("missing table accepted")
	}
	for _, raw := range []string{
		`{"version":1,"users":[]}`, `{"version":2,"users":[]}`,
		`{"version":3,"users":[]}`, `{"version":2,"users":[],"setup_required":true}`,
		`{"version":3,"users":null,"setup_required":true}`,
		`{"version":3,"users":[],"setup_required":true,"unknown":true}`,
		`{"version":3,"users":[],"setup_required":true} trailing`,
	} {
		if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		if _, _, err := ReadRegistry(path, nil); err == nil {
			t.Fatalf("invalid state accepted: %s", raw)
		}
	}
	if err := WriteRegistry(path, Registry{Version: 3, Users: []Account{}, SetupRequired: true}); err != nil {
		t.Fatal(err)
	}
	registry, _, err := ReadRegistry(path, map[string]bool{})
	if err != nil || !registry.SetupRequired || len(registry.Users) != 0 {
		t.Fatal("explicit initialization state unreadable", err)
	}
	store := NewAccountStore(path, func() map[string]bool { return map[string]bool{"personal": true} })
	before, _ := os.ReadFile(path)
	if err := store.Put("ordinary", testPassword, RoleUser, []string{"personal"}, false); err == nil {
		t.Fatal("non-admin initialized registry")
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("denied initialization changed table")
	}
}

func TestBootstrapGatewayRevokesOldLoginAndEnablesInitializedAdmin(t *testing.T) {
	f, reached := manageFixture(t)
	old, _ := f.login(t, "root")
	if err := WriteRegistry(f.registry, Registry{Version: 3, Users: []Account{}, SetupRequired: true}); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Reload(); err != nil {
		t.Fatal(err)
	}
	page := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	if page.Code != 200 || !strings.Contains(page.Body.String(), "平台尚未初始化") || strings.Contains(page.Body.String(), `<form method="post" action="/auth/login">`) {
		t.Fatal("initialization page missing or login form remains")
	}
	request(f.handler, "GET", "https://entry.test/manage/", nil, old)
	if *reached != 0 {
		t.Fatal("old admin session survived reset")
	}
	challenge := responseCookie(t, page, loginCookie)
	denied := request(f.handler, "POST", "https://entry.test/auth/login", url.Values{"username": {"root"}, "password": {testPassword}, "csrf": {challenge.Value}}, challenge)
	if denied.Code != 401 {
		t.Fatalf("old password accepted: %d", denied.Code)
	}
	if err := f.g.Accounts().InitializeAdmin("firstadmin", testPassword); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Reload(); err != nil {
		t.Fatal(err)
	}
	page = request(f.handler, "GET", "https://entry.test/auth/login", nil)
	if strings.Contains(page.Body.String(), "平台尚未初始化") {
		t.Fatal("initialization notice remains")
	}
	challenge = responseCookie(t, page, loginCookie)
	login := request(f.handler, "POST", "https://entry.test/auth/login", url.Values{"username": {"firstadmin"}, "password": {testPassword}, "csrf": {challenge.Value}}, challenge)
	if login.Code != 303 {
		t.Fatalf("initialized admin login: %d", login.Code)
	}
	admin := responseCookie(t, login, entryCookie)
	request(f.handler, "GET", "https://entry.test/manage/", nil, admin)
	if *reached != 1 {
		t.Fatal("initialized admin cannot manage")
	}
	if err := f.g.Accounts().Delete("firstadmin"); err != ErrLastAdmin {
		t.Fatal("last administrator protection lost", err)
	}
}
