package access

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestPasswordByteBoundaries(t *testing.T) {
	for _, tc := range []struct {
		password string
		valid    bool
	}{{"abc", false}, {"abcd", true}, {"中", false}, {"中a", true}, {strings.Repeat("a", 256), true}, {strings.Repeat("a", 257), false}} {
		hash, err := HashPassword(tc.password)
		if (err == nil) != tc.valid {
			t.Fatalf("byte length %d: %v", len(tc.password), err)
		}
		if tc.valid && !checkPassword(hash, tc.password) {
			t.Fatal("hash verification failed")
		}
	}
}

func TestPasswordModalJSONAndSessionRevocation(t *testing.T) {
	f, _ := manageFixture(t)
	user, csrf := f.login(t, "root")
	other, _ := f.login(t, "root")
	post := func(current, password, confirm, token, origin string) *httptest.ResponseRecorder {
		data := url.Values{"csrf": {token}, "current": {current}, "password": {password}, "confirm": {confirm}}
		req := httptest.NewRequest("POST", "https://entry.test/auth/password", strings.NewReader(data.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("Accept", "application/json")
		req.Header.Set("Origin", origin)
		req.AddCookie(user)
		res := httptest.NewRecorder()
		f.handler.ServeHTTP(res, req)
		return res
	}
	for _, tc := range []struct {
		current, password, confirm string
		code                       int
	}{{testPassword, "abc", "abc", 400}, {testPassword, "abcd", "abce", 400}, {"incorrect", "abcd", "abcd", 401}} {
		res := post(tc.current, tc.password, tc.confirm, csrf, "https://entry.test")
		var result struct {
			Done    bool
			Message string
		}
		if res.Code != tc.code || json.Unmarshal(res.Body.Bytes(), &result) != nil || result.Done || result.Message == "" {
			t.Fatalf("JSON rejection: %d %s", res.Code, res.Body.String())
		}
	}
	if post(testPassword, "abcd", "abcd", "bad", "https://entry.test").Code != 403 {
		t.Fatal("bad CSRF accepted")
	}
	if post(testPassword, "abcd", "abcd", csrf, "https://other.test").Code != 403 {
		t.Fatal("bad Origin accepted")
	}
	res := post(testPassword, "中a", "中a", csrf, "https://entry.test")
	var result struct{ Done bool }
	if res.Code != 200 || json.Unmarshal(res.Body.Bytes(), &result) != nil || !result.Done {
		t.Fatalf("JSON success: %d %s", res.Code, res.Body.String())
	}
	if request(f.handler, "GET", "https://entry.test/", nil, user).Code != 200 {
		t.Fatal("current login revoked")
	}
	if request(f.handler, "GET", "https://entry.test/", nil, other).Code == 200 {
		t.Fatal("other login retained")
	}
	if loginAttempt(f, "root", "中a").Code != http.StatusSeeOther {
		t.Fatal("4 byte password ineffective")
	}
	if strings.Contains(f.logs.String(), "中a") {
		t.Fatal("password in logs")
	}
	// Account create and reset share the same byte boundary.
	if err := f.g.Accounts().Put("fourbyte", "abcd", RoleUser, []string{"personal"}, false); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Accounts().SetPassword("fourbyte", "中a"); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Accounts().SetPassword("fourbyte", "abc"); err == nil {
		t.Fatal("3 byte reset accepted")
	}
}

func TestReauthDialogJSON(t *testing.T) {
	f, _ := manageFixture(t)
	user, csrf := f.login(t, "root")
	for _, tc := range []struct {
		password, token, origin string
		code                    int
		done                    bool
	}{{testPassword, "bad", "https://entry.test", 403, false}, {testPassword, csrf, "https://wrong.test", 403, false}, {"wrong", csrf, "https://entry.test", 401, false}, {testPassword, csrf, "https://entry.test", 200, true}} {
		data := url.Values{"csrf": {tc.token}, "password": {tc.password}}
		req := httptest.NewRequest("POST", "https://entry.test/auth/reauth", strings.NewReader(data.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("Origin", tc.origin)
		req.Header.Set("Accept", "application/json")
		req.AddCookie(user)
		res := httptest.NewRecorder()
		f.handler.ServeHTTP(res, req)
		if res.Code != tc.code {
			t.Fatalf("status %d expected %d", res.Code, tc.code)
		}
		if tc.code != 403 {
			var v struct{ Done bool }
			if json.Unmarshal(res.Body.Bytes(), &v) != nil || v.Done != tc.done {
				t.Fatal("bad reauth JSON")
			}
		}
	}
	if !decodeEcho(t, request(f.handler, "GET", "https://entry.test/manage/environments", nil, user)).Reauth {
		t.Fatal("confirmation not recorded")
	}
}
