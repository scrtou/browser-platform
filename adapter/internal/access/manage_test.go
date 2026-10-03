package access

import (
	"context"
	"encoding/json"
	"html"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"
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
			Reauth  bool    `json:"reauth"`
		}{Subject(r), ok, grants, CSRF(r), f.g.Reauthenticated(r)})
	}))
	return f, &reached
}

type echo struct {
	Subject string
	OK      bool
	Grants  []Grant
	CSRF    string
	Reauth  bool
}

func decodeEcho(t *testing.T, response *httptest.ResponseRecorder) echo {
	t.Helper()
	var value echo
	if err := json.Unmarshal(response.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode: %v %s", err, response.Body.String())
	}
	return value
}

func TestManagementSurfaceIsAdminOnlyWithCSRFForms(t *testing.T) {
	f, reached := manageFixture(t)
	for _, path := range []string{"/manage/", "/manage/environments", "/manage/browsers/personal"} {
		if response := request(f.handler, "GET", "https://entry.test"+path, nil); response.Code != 303 && response.Code != 401 || *reached != 0 {
			t.Fatalf("unauthenticated %s reached management: %d", path, response.Code)
		}
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/", nil); response.Code != 303 || response.Header().Get("Location") != "/auth/login" {
		t.Fatalf("unauthenticated page must go to the login without a next hint: %d %s", response.Code, response.Header().Get("Location"))
	}
	user, userCSRF := f.login(t, "alice")
	for _, path := range []string{"/manage/", "/manage/environments"} {
		response := request(f.handler, "GET", "https://entry.test"+path, nil, user)
		if response.Code != 403 || *reached != 0 || strings.Contains(response.Body.String(), "personal") || strings.Contains(response.Body.String(), "work") {
			t.Fatalf("entry account reached the management surface: %d %s", response.Code, response.Body.String())
		}
	}
	if response := request(f.handler, "POST", "https://entry.test/manage/browsers/personal", url.Values{"csrf": {userCSRF}, "action": {"stop"}}, user); response.Code != 403 || *reached != 0 {
		t.Fatalf("entry account POSTed to management: %d", response.Code)
	}
	index := request(f.handler, "GET", "https://entry.test/", nil, user)
	if index.Code != 200 || strings.Contains(index.Body.String(), `href="/manage/?tab=browsers"`) || !strings.Contains(index.Body.String(), `href="/auth/password"`) {
		t.Fatalf("entry index: %d %s", index.Code, index.Body.String())
	}
	admin, csrf := f.login(t, "root")
	for _, path := range []string{"/manage", "/other"} {
		if response := request(f.handler, "GET", "https://entry.test"+path, nil, admin); response.Code != 404 || *reached != 0 {
			t.Fatalf("path %s outside the management surface reached the handler: %d", path, response.Code)
		}
	}
	if response := request(f.handler, "PUT", "https://entry.test/manage/browsers/personal", nil, admin); response.Code != 405 || response.Header().Get("Allow") != "GET, HEAD, POST" || *reached != 0 {
		t.Fatalf("PUT: %d", response.Code)
	}
	r := httptest.NewRequest("POST", "https://entry.test/manage/browsers/personal", strings.NewReader(url.Values{"csrf": {csrf}, "action": {"stop"}}.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Origin", "https://elsewhere.test")
	r.AddCookie(admin)
	w := httptest.NewRecorder()
	f.handler.ServeHTTP(w, r)
	if w.Code != 403 || *reached != 0 {
		t.Fatal("cross-origin management POST reached the handler")
	}
	if response := request(f.handler, "POST", "https://entry.test/manage/browsers/personal", url.Values{"csrf": {"wrong"}, "action": {"stop"}}, admin); response.Code != 403 || *reached != 0 {
		t.Fatal("bad CSRF management POST reached the handler")
	}
	if response := request(f.handler, "POST", "https://entry.test/manage/browsers/personal", url.Values{"csrf": {csrf}, "action": {"stop"}}, admin); response.Code != 200 || *reached != 1 {
		t.Fatalf("admin form POST: %d", response.Code)
	}
	adminIndex := request(f.handler, "GET", "https://entry.test/", nil, admin)
	if !strings.Contains(adminIndex.Body.String(), `href="/manage/?tab=browsers"`) {
		t.Fatal("admin index lost the management link")
	}
}

func TestHomeWorkspaceUsesOnlyAuthorizedCachedSummaries(t *testing.T) {
	f := newFixture(t)
	var requested []string
	f.g.homeProvider = func(_ context.Context, ids []string) []HomeCard {
		requested = append([]string(nil), ids...)
		cards := make([]HomeCard, 0, len(ids))
		for _, id := range ids {
			cards = append(cards, HomeCard{
				ProfileID: id, Label: "个人浏览器", EntryPath: "/browser/" + id + "/",
				Status: "running", Health: "degraded", HealthCode: "EGRESS_NOT_CONFIGURED", Network: "proxy_required", NetworkName: "公司代理 <测试>",
				BrowserTemplate: "camoufox-linux", Fingerprint: "env-r7d", Display: "fixed-1920",
				CheckedAt: "2026-09-23T00:30:00Z", Enabled: true, Available: true, Observed: true, NetworkIssue: true,
			})
		}
		return cards
	}
	user, _ := f.login(t, "alice")
	index := request(f.handler, "GET", "https://entry.test/", nil, user)
	if index.Code != http.StatusOK || strings.Join(requested, ",") != "personal" {
		t.Fatalf("home provider authorization: status=%d requested=%v", index.Code, requested)
	}
	body := index.Body.String()
	for _, want := range []string{"浏览器工作区", "个人浏览器", "公司代理 &lt;测试&gt;", "可访问浏览器", "需要处理的网络问题", "EGRESS_NOT_CONFIGURED", "camoufox-linux", "env-r7d", "fixed-1920", `href="/browser/personal/"`, "@media(max-width:768px)"} {
		if !strings.Contains(body, want) {
			t.Fatalf("home workspace missing %q: %s", want, body)
		}
	}
	if strings.Contains(body, "/browser/work/") || strings.Contains(body, `href="/manage/?tab=browsers"`) {
		t.Fatalf("entry account home exposed unauthorized/admin content: %s", body)
	}
	for _, forbidden := range []string{"personal-home", "network_policy_sha256", "secret://", "access_token", "session.test/"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("home workspace exposed internal value %q", forbidden)
		}
	}
}

func TestHomeWorkspaceRejectsProviderExtrasAndStaleHealthy(t *testing.T) {
	f := newFixture(t)
	f.g.homeProvider = func(_ context.Context, _ []string) []HomeCard {
		return []HomeCard{
			{ProfileID: "work", Label: "unauthorized", NetworkName: "private-proxy-name", EntryPath: "/browser/work/", Available: true},
			{ProfileID: "personal", Label: "Personal", EntryPath: "/browser/personal/", Available: true, Observed: true, Stale: true, Health: "healthy", CheckedAt: "2026-09-20T00:00:00Z"},
		}
	}
	user, _ := f.login(t, "alice")
	response := request(f.handler, "GET", "https://entry.test/", nil, user)
	body := response.Body.String()
	if response.Code != http.StatusOK || strings.Contains(body, "unauthorized") || strings.Contains(body, "private-proxy-name") || strings.Contains(body, "/browser/work/") || strings.Contains(body, "healthy") || !strings.Contains(body, "未知（采样已过期）") {
		t.Fatalf("home exposed provider extra or stale healthy: %d %s", response.Code, body)
	}
}

func TestAdminGrantsCoverEveryProfileAndFollowAccountChanges(t *testing.T) {
	f, reached := manageFixture(t)
	admin, _ := f.login(t, "root")
	response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin)
	if response.Code != 200 || *reached != 1 {
		t.Fatalf("admin list: %d", response.Code)
	}
	value := decodeEcho(t, response)
	if !value.OK || value.Subject != "root" || len(value.Grants) != 2 || value.Grants[0].Profile != "personal" || value.Grants[1].Profile != "work" {
		t.Fatalf("grants: %+v", value)
	}
	if strings.Join(value.Grants[0].Capabilities, ",") != "view,manage,stop,start" || strings.Join(value.Grants[1].Capabilities, ",") != "view,manage,stop" {
		t.Fatalf("capabilities: %+v", value.Grants)
	}
	if value.Reauth {
		t.Fatal("fresh login must not count as re-authenticated")
	}
	head := httptest.NewRequest("HEAD", "https://entry.test/manage/", nil)
	head.AddCookie(admin)
	headResponse := httptest.NewRecorder()
	f.handler.ServeHTTP(headResponse, head)
	if headResponse.Code != 200 || *reached != 2 {
		t.Fatalf("HEAD: %d", headResponse.Code)
	}
	// Demoting the administrator revokes only its own login; alice's stays.
	alice, _ := f.login(t, "alice")
	if err := f.g.Accounts().Put("second", testPassword, RoleAdmin, []string{"work"}, false); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Accounts().SetRole("root", RoleUser); err != nil || f.g.reload() != nil {
		t.Fatalf("demote: %v", err)
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin); response.Code != 401 || *reached != 2 {
		t.Fatalf("demoted admin kept management access: %d", response.Code)
	}
	if response := request(f.handler, "GET", "https://entry.test/browser/personal/", nil, alice); response.Code != 200 {
		t.Fatalf("unrelated account lost its login on someone else's change: %d", response.Code)
	}
	if err := f.g.Accounts().SetRole("second", RoleUser); err != ErrLastAdmin {
		t.Fatalf("last administrator demoted: %v", err)
	}
	if err := f.g.Accounts().SetDisabled("second", true); err != ErrLastAdmin {
		t.Fatalf("last administrator disabled: %v", err)
	}
	if err := os.Remove(f.registry); err != nil {
		t.Fatal(err)
	}
	_ = f.g.reload()
	if response := request(f.handler, "GET", "https://entry.test/browser/personal/", nil, alice); response.Code != 303 {
		t.Fatalf("missing registry kept a login alive: %d", response.Code)
	}
	if grants := f.g.grants("root"); grants != nil {
		t.Fatalf("grants without a ready registry: %+v", grants)
	}
}

func TestAccountChangesRevokeOnlyTheChangedAccount(t *testing.T) {
	f := newFixture(t)
	aliceEntry, _, aliceDisplay := f.display(t, "alice", "personal")
	bobEntry, _, bobDisplay := f.display(t, "bob", "work")
	if err := f.g.Accounts().SetPassword("bob", "another-synthetic-password"); err != nil || f.g.reload() != nil {
		t.Fatalf("password change: %v", err)
	}
	if request(f.handler, "GET", "https://session.test/"+workSession+"/", nil, bobDisplay).Code != 401 || request(f.handler, "GET", "https://entry.test/browser/work/", nil, bobEntry).Code != 303 {
		t.Fatal("changed account kept its logins")
	}
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, aliceDisplay).Code != 200 || request(f.handler, "GET", "https://entry.test/browser/personal/", nil, aliceEntry).Code != 200 {
		t.Fatal("unchanged account lost its logins")
	}
	// A grant change is an account-record change: that account's logins and
	// displays end, the next login sees the new grants, nobody else is touched.
	if err := f.g.Accounts().SetGrants("alice", []string{}); err == nil {
		t.Fatal("an entry account without any grant was accepted")
	}
	if err := f.g.Accounts().Put("carol", testPassword, "", []string{"personal", "work"}, false); err != nil || f.g.reload() != nil {
		t.Fatal(err)
	}
	carolEntry, _, carolDisplay := f.display(t, "carol", "personal")
	if err := f.g.Accounts().SetGrants("carol", []string{"work"}); err != nil || f.g.reload() != nil {
		t.Fatalf("grant change: %v", err)
	}
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, carolDisplay).Code != 401 || request(f.handler, "GET", "https://entry.test/browser/work/", nil, carolEntry).Code != 303 {
		t.Fatal("withdrawn grant kept the display or the login")
	}
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, aliceDisplay).Code != 200 {
		t.Fatal("another account's display ended on carol's change")
	}
	carolAgain, _ := f.login(t, "carol")
	if request(f.handler, "GET", "https://entry.test/browser/work/", nil, carolAgain).Code != 200 || request(f.handler, "GET", "https://entry.test/browser/personal/", nil, carolAgain).Code != 404 {
		t.Fatal("new login did not see the new grants")
	}
	// A directory change without an account change: the display check also
	// revokes displays whose Profile is no longer configured.
	f.g.profiles = StaticProfiles([]string{"work"})
	f.g.checkDisplays(context.Background())
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, aliceDisplay).Code != 401 {
		t.Fatal("display for a removed Profile survived the check")
	}
	if strings.Contains(f.logs.String(), "another-synthetic-password") {
		t.Fatal("password reached logs")
	}
}

func TestReauthAndPasswordChange(t *testing.T) {
	f, _ := manageFixture(t)
	admin, csrf := f.login(t, "root")
	page := request(f.handler, "GET", "https://entry.test/auth/reauth?next=/manage/", nil, admin)
	if page.Code != 200 || !strings.Contains(page.Body.String(), `name="next" value="/manage/"`) {
		t.Fatalf("reauth page: %d", page.Code)
	}
	for _, next := range []string{"https://evil.test/", "/browser/personal/", "/manage/..", "//evil"} {
		p := request(f.handler, "GET", "https://entry.test/auth/reauth?next="+url.QueryEscape(next), nil, admin)
		if !strings.Contains(p.Body.String(), `name="next" value="/manage/"`) {
			t.Fatalf("unsafe next %q accepted", next)
		}
	}
	if response := request(f.handler, "POST", "https://entry.test/auth/reauth", url.Values{"csrf": {csrf}, "password": {"wrong-password-value"}, "next": {"/manage/"}}, admin); response.Code != 401 {
		t.Fatalf("wrong reauth password: %d", response.Code)
	}
	if decodeEcho(t, request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin)).Reauth {
		t.Fatal("failed reauth counted")
	}
	if response := request(f.handler, "POST", "https://entry.test/auth/reauth", url.Values{"csrf": {csrf}, "password": {testPassword}, "next": {"/manage/"}}, admin); response.Code != 303 || response.Header().Get("Location") != "/manage/" {
		t.Fatalf("reauth: %d %s", response.Code, response.Header().Get("Location"))
	}
	if !decodeEcho(t, request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin)).Reauth {
		t.Fatal("reauth not recorded")
	}
	f.g.mu.Lock()
	for key, data := range f.g.sessions {
		if data.Actor == "root" && data.Audience == "entry" {
			data.ReauthAt = time.Now().Add(-ReauthWindow - time.Second)
			f.g.sessions[key] = data
		}
	}
	f.g.mu.Unlock()
	if decodeEcho(t, request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin)).Reauth {
		t.Fatal("expired reauth still counted")
	}
	// Self-service password change keeps this login and revokes the others.
	other, _ := f.login(t, "root")
	form := url.Values{"csrf": {csrf}, "current": {testPassword}, "password": {"new-synthetic-password-9x"}, "confirm": {"new-synthetic-password-9x"}}
	if response := request(f.handler, "POST", "https://entry.test/auth/password", url.Values{"csrf": {csrf}, "current": {testPassword}, "password": {"abc"}, "confirm": {"abc"}}, admin); response.Code != 400 {
		t.Fatalf("short password accepted: %d", response.Code)
	}
	if response := request(f.handler, "POST", "https://entry.test/auth/password", url.Values{"csrf": {csrf}, "current": {"wrong-password-value"}, "password": {"new-synthetic-password-9x"}, "confirm": {"new-synthetic-password-9x"}}, admin); response.Code != 401 {
		t.Fatalf("wrong current password accepted: %d", response.Code)
	}
	if response := request(f.handler, "POST", "https://entry.test/auth/password", form, admin); response.Code != 200 || !strings.Contains(response.Body.String(), "密码已更新") {
		t.Fatalf("password change: %d %s", response.Code, response.Body.String())
	}
	if request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin).Code != 200 {
		t.Fatal("the changing login was revoked")
	}
	if request(f.handler, "GET", "https://entry.test/manage/environments", nil, other).Code != 401 {
		t.Fatal("other logins of the account survived the password change")
	}
	if loginAttempt(f, "root", testPassword).Code != 401 || loginAttempt(f, "root", "new-synthetic-password-9x").Code != 303 {
		t.Fatal("new password not effective")
	}
	if strings.Contains(f.logs.String(), "new-synthetic-password-9x") {
		t.Fatal("new password reached logs")
	}
}

func TestLogoutRevokesManagementAccess(t *testing.T) {
	f, reached := manageFixture(t)
	admin, csrf := f.login(t, "root")
	if response := request(f.handler, "GET", "https://entry.test/manage/", nil, admin); response.Code != 200 || *reached != 1 {
		t.Fatalf("admin page: %d", response.Code)
	}
	if request(f.handler, "POST", "https://entry.test/auth/logout", url.Values{"csrf": {csrf}}, admin).Code != 303 {
		t.Fatal("logout failed")
	}
	if response := request(f.handler, "GET", "https://entry.test/manage/environments", nil, admin); response.Code != 401 || *reached != 1 {
		t.Fatalf("logged-out list: %d", response.Code)
	}
}

func TestAccessUIRedesignContracts(t *testing.T) {
	f, _ := manageFixture(t)
	// 1. Login page visual elements & zero external dependencies
	loginRes := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	if loginRes.Code != http.StatusOK {
		t.Fatalf("login page status: %d", loginRes.Code)
	}
	loginBody := loginRes.Body.String()
	for _, expected := range []string{"auth-card", "登录浏览器平台", "使用你的账号访问已分配的浏览器。", "账号", "密码", "btn-submit"} {
		if !strings.Contains(loginBody, expected) {
			t.Fatalf("login page missing visual element %q", expected)
		}
	}
	if strings.Contains(loginBody, "http://") || strings.Contains(loginBody, "https://") || strings.Contains(loginBody, "<script") {
		t.Fatal("login page must not contain external asset URLs or scripts")
	}

	// 2. Reauth page visual contracts
	admin, _ := f.login(t, "root")
	reauthRes := request(f.handler, "GET", "https://entry.test/auth/reauth", nil, admin)
	if reauthRes.Code != http.StatusOK {
		t.Fatalf("reauth page status: %d", reauthRes.Code)
	}
	reauthBody := reauthRes.Body.String()
	for _, expected := range []string{"auth-card", "确认密码", "敏感操作需要在 5 分钟内重新输入密码。", "btn-submit"} {
		if !strings.Contains(reauthBody, expected) {
			t.Fatalf("reauth page missing visual element %q", expected)
		}
	}

	// 3. Password change page visual contracts
	pwdRes := request(f.handler, "GET", "https://entry.test/auth/password", nil, admin)
	if pwdRes.Code != http.StatusOK {
		t.Fatalf("password page status: %d", pwdRes.Code)
	}
	pwdBody := pwdRes.Body.String()
	for _, expected := range []string{"auth-card", "修改密码", "当前密码", "新密码（4–256 字节）", "再次输入新密码", "btn-submit"} {
		if !strings.Contains(pwdBody, expected) {
			t.Fatalf("password page missing visual element %q", expected)
		}
	}

	// 4. Index landing page sidebar & cards structure
	indexRes := request(f.handler, "GET", "https://entry.test/", nil, admin)
	if indexRes.Code != http.StatusOK {
		t.Fatalf("index page status: %d", indexRes.Code)
	}
	indexBody := indexRes.Body.String()
	for _, expected := range []string{"sidebar", "sidebar-brand", "浏览器工作区", "summary", "cards", "打开浏览器", "@media(max-width:768px)"} {
		if !strings.Contains(indexBody, expected) {
			t.Fatalf("index page missing visual structure %q", expected)
		}
	}
}

func TestHomeNonceChangesPerResponseAndAuthRemainsScriptFree(t *testing.T) {
	f := newFixture(t)
	user, _ := f.login(t, "alice")
	var last string
	for range 2 {
		page := request(f.handler, "GET", "https://entry.test/", nil, user)
		body := page.Body.String()
		marker := `<script nonce="`
		start := strings.Index(body, marker)
		if start < 0 {
			t.Fatal("home script missing")
		}
		nonce := html.UnescapeString(strings.Split(body[start+len(marker):], `"`)[0])
		csp := page.Header().Get("Content-Security-Policy")
		if len(nonce) < 24 || nonce == last || !strings.Contains(csp, "script-src 'nonce-"+nonce+"'") || strings.Contains(csp, "script-src 'unsafe-inline'") {
			t.Fatal("home nonce contract")
		}
		last = nonce
	}
	auth := request(f.handler, "GET", "https://entry.test/auth/login", nil)
	if strings.Contains(auth.Header().Get("Content-Security-Policy"), "script-src") || strings.Contains(auth.Body.String(), "<script") {
		t.Fatal("auth CSP changed")
	}
}
