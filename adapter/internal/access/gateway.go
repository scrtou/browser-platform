package access

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"html/template"
	"log/slog"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"
)

const loginCookie = "__Host-bp_login"
const entryCookie = "__Host-bp_entry"
const displayCookie = "__Host-bp_display_"

type Config struct {
	UsersFile          string `json:"users_file"`
	SessionUpstreamURL string `json:"session_upstream_url"`
	SessionCAFile      string `json:"session_ca_file"`
	SessionTLSName     string `json:"session_tls_name"`
	SessionSeconds     int    `json:"session_seconds,omitempty"`
	TicketSeconds      int    `json:"ticket_seconds,omitempty"`
}

func (c Config) Lifetime() time.Duration {
	if c.SessionSeconds == 0 {
		return 30 * time.Minute
	}
	return time.Duration(c.SessionSeconds) * time.Second
}

func (c Config) TicketLifetime() time.Duration {
	if c.TicketSeconds == 0 {
		return 30 * time.Second
	}
	return time.Duration(c.TicketSeconds) * time.Second
}

func (c Config) Validate() error {
	if c.UsersFile == "" || c.SessionCAFile == "" || c.SessionTLSName == "" ||
		c.Lifetime() < 5*time.Second || c.Lifetime() > time.Hour || c.TicketLifetime() < time.Second || c.TicketLifetime() > time.Minute {
		return errors.New("access requires private accounts, verified Session TLS and bounded lifetimes")
	}
	u, err := origin(c.SessionUpstreamURL)
	if err != nil {
		return errors.New("access Session upstream must be a single HTTPS origin")
	}
	ip := net.ParseIP(u.Hostname())
	if u.Hostname() != "localhost" && (ip == nil || !ip.IsLoopback()) {
		return errors.New("access Session upstream must use the local SealSkin listener")
	}
	return nil
}

type login struct {
	Actor, Audience, Parent, Profile, Session, CSRF string
	BackendToken                                    string
	Expires                                         time.Time
	// AccountHash identifies the account record this login was issued for;
	// a changed record revokes only this account's logins.
	AccountHash [32]byte
	// ReauthAt is the last successful password confirmation for sensitive
	// management operations; zero until the login re-authenticates.
	ReauthAt time.Time
}

// ReauthWindow bounds how long a password confirmation covers sensitive
// management operations. It never extends the login itself.
const ReauthWindow = 5 * time.Minute

type ticket struct {
	Parent, Profile, Session, Target, BackendToken string
	Expires                                        time.Time
}

type attemptWindow struct {
	Since time.Time
	Count int
}

type requestLogin struct {
	Hash [32]byte
	Data login
}

type contextKey struct{}

// Grant is one Profile the current login may see on management pages. The
// only capabilities today are "view" (list and read summaries) and "start"
// (the existing fixed entry); stop and configuration are not granted here.
type Grant struct {
	Profile      string   `json:"profile_id"`
	Capabilities []string `json:"capabilities"`
}

type grantsKey struct{}

// ManagePath reports whether a request path belongs to the management
// surface served behind the login. Only administrators reach it; GET/HEAD and
// CSRF-checked form POSTs are the only methods.
func ManagePath(path string) bool {
	return strings.HasPrefix(path, "/manage/")
}

// ProfileSet is the gateway's view of the configured Profiles. A dynamic
// directory changes it at runtime; the gateway never caches the answer.
type ProfileSet interface {
	KnownProfile(string) bool
	ProfileIDs() []string
}

type staticProfiles map[string]bool

func (p staticProfiles) KnownProfile(id string) bool { return p[id] }
func (p staticProfiles) ProfileIDs() []string {
	ids := make([]string, 0, len(p))
	for id := range p {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// StaticProfiles adapts a fixed Profile list to ProfileSet.
func StaticProfiles(ids []string) ProfileSet {
	set := make(staticProfiles, len(ids))
	for _, id := range ids {
		set[id] = true
	}
	return set
}

// BindingCheck must only inspect the current business binding. It must not
// start, probe, resume or stop a generation in response to a display request.
type BindingCheck func(context.Context, string, string) error

type Gateway struct {
	cfg            Config
	entry, session *url.URL
	profiles       ProfileSet
	accounts       *AccountStore
	checkBinding   BindingCheck
	logger         *slog.Logger
	proxy          *httputil.ReverseProxy
	mu             sync.Mutex
	users          map[string]Account
	revision       [32]byte
	accountsReady  bool
	sessions       map[[32]byte]login
	tickets        map[[32]byte]ticket
	attempts       map[string]attemptWindow
	active         map[uint64]activeRequest
	sequence       uint64
	passwordSlots  chan struct{}
}

type activeRequest struct {
	Hash   [32]byte
	Cancel context.CancelFunc
}

func New(ctx context.Context, cfg Config, entryURL, sessionURL string, profiles ProfileSet, check BindingCheck, logger *slog.Logger) (*Gateway, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	entry, err1 := origin(entryURL)
	session, err2 := origin(sessionURL)
	if err1 != nil || err2 != nil || strings.EqualFold(entry.Host, session.Host) || check == nil || profiles == nil {
		return nil, errors.New("access requires separate, valid entry and Session origins, a Profile set and binding checks")
	}
	if logger == nil {
		logger = slog.Default()
	}
	g := &Gateway{cfg: cfg, entry: entry, session: session, profiles: profiles, checkBinding: check, logger: logger,
		sessions: make(map[[32]byte]login), tickets: make(map[[32]byte]ticket), attempts: make(map[string]attemptWindow),
		active: make(map[uint64]activeRequest), passwordSlots: make(chan struct{}, 2)}
	g.accounts = NewAccountStore(cfg.UsersFile, g.knownProfiles)
	if err := g.reload(); err != nil {
		return nil, err
	}
	if err := g.prepareProxy(); err != nil {
		return nil, err
	}
	go func() {
		timer := time.NewTicker(time.Second)
		defer timer.Stop()
		for {
			select {
			case <-ctx.Done():
				g.mu.Lock()
				g.clearLocked()
				g.mu.Unlock()
				if transport, ok := g.proxy.Transport.(*http.Transport); ok {
					transport.CloseIdleConnections()
				}
				return
			case <-timer.C:
				_ = g.reload()
				g.mu.Lock()
				g.pruneLocked(time.Now())
				g.mu.Unlock()
				g.checkDisplays(ctx)
			}
		}
	}()
	return g, nil
}

func (g *Gateway) checkDisplays(ctx context.Context) {
	// A WebSocket also loses access when the business binding changes or the
	// Profile grant is withdrawn. Copy under the access lock, then read
	// business state without holding it.
	g.mu.Lock()
	displays := make(map[[32]byte]login)
	for key, data := range g.sessions {
		if data.Audience == "display" {
			displays[key] = data
		}
	}
	g.mu.Unlock()
	for key, data := range displays {
		if !g.allowed(data.Actor, data.Profile) || g.checkBinding(ctx, data.Profile, data.Session) != nil {
			g.mu.Lock()
			g.revokeLocked(key)
			g.mu.Unlock()
		}
	}
}

func (g *Gateway) knownProfiles() map[string]bool {
	known := make(map[string]bool)
	for _, id := range g.profiles.ProfileIDs() {
		known[id] = true
	}
	return known
}

// accountHash identifies one account record. Any change to it revokes that
// account's logins without touching other accounts.
func accountHash(account Account) [32]byte {
	grants := append([]string(nil), account.Profiles...)
	sort.Strings(grants)
	return sha256.Sum256([]byte(account.ID + "\x00" + account.PasswordHash + "\x00" + strings.Join(grants, ",") + "\x00" +
		fmt.Sprint(account.Disabled) + "\x00" + account.EffectiveRole()))
}

func origin(value string) (*url.URL, error) {
	u, err := url.Parse(value)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.Opaque != "" ||
		(u.Path != "" && u.Path != "/") || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.RawFragment != "" {
		return nil, errors.New("invalid HTTPS origin")
	}
	u.Path = ""
	return u, nil
}

func SameOrigin(r *http.Request, expected *url.URL) bool {
	values := r.Header.Values("Origin")
	if len(values) != 1 || strings.TrimSpace(values[0]) != values[0] {
		return false
	}
	u, err := origin(values[0])
	return err == nil && u.Path == "" && strings.EqualFold(u.Host, expected.Host) && values[0] == u.Scheme+"://"+u.Host
}

func opaque() (string, error) {
	data := make([]byte, 32)
	if _, err := rand.Read(data); err != nil {
		return "", errors.New("access randomness unavailable")
	}
	return base64.RawURLEncoding.EncodeToString(data), nil
}

func hash(value string) [32]byte { return sha256.Sum256([]byte(value)) }

func hashString(value [32]byte) string { return base64.RawURLEncoding.EncodeToString(value[:]) }

func (g *Gateway) clearLocked() {
	for _, running := range g.active {
		running.Cancel()
	}
	clear(g.sessions)
	clear(g.tickets)
}

func (g *Gateway) revokeLocked(key [32]byte) {
	delete(g.sessions, key)
	for child, data := range g.sessions {
		if data.Parent == hashString(key) {
			g.revokeLocked(child)
		}
	}
	for _, running := range g.active {
		if running.Hash == key {
			running.Cancel()
		}
	}
	for ticketKey, pending := range g.tickets {
		if pending.Parent == hashString(key) {
			delete(g.tickets, ticketKey)
		}
	}
}

func (g *Gateway) pruneLocked(now time.Time) {
	for key, data := range g.sessions {
		if !now.Before(data.Expires) {
			g.revokeLocked(key)
		}
	}
	for key, data := range g.tickets {
		if !now.Before(data.Expires) {
			delete(g.tickets, key)
		}
	}
	for key, window := range g.attempts {
		if now.Sub(window.Since) > time.Minute {
			delete(g.attempts, key)
		}
	}
}

// reload re-reads the account table. A missing or invalid table still revokes
// everything; a changed table revokes only the logins whose account record
// changed or vanished, plus display logins whose Profile grant was withdrawn.
func (g *Gateway) reload() error { return g.reloadKeeping("") }

// Reload applies account-table changes immediately instead of waiting for the
// background check.
func (g *Gateway) Reload() error { return g.reload() }

// Accounts exposes the shared account store used by the management surface
// and the CLI.
func (g *Gateway) Accounts() *AccountStore { return g.accounts }

func (g *Gateway) reloadKeeping(keepActor string) error {
	registry, revision, err := ReadRegistry(g.cfg.UsersFile, g.knownProfiles())
	g.mu.Lock()
	defer g.mu.Unlock()
	if err != nil {
		g.clearLocked()
		g.accountsReady = false
		return err
	}
	if g.accountsReady && revision == g.revision {
		return nil
	}
	wasReady := g.accountsReady
	users := make(map[string]Account, len(registry.Users))
	for _, user := range registry.Users {
		users[user.ID] = user
	}
	if !wasReady {
		g.clearLocked()
	}
	g.users, g.revision, g.accountsReady = users, revision, true
	for key, data := range g.sessions {
		account, exists := users[data.Actor]
		if !exists || account.Disabled {
			g.revokeLocked(key)
			continue
		}
		current := accountHash(account)
		if data.AccountHash != current {
			if data.Actor == keepActor && data.Audience == "entry" {
				data.AccountHash = current
				g.sessions[key] = data
				continue
			}
			g.revokeLocked(key)
			continue
		}
		if data.Audience == "display" && !g.allowedLocked(data.Actor, data.Profile) {
			g.revokeLocked(key)
		}
	}
	return nil
}

func cookieValue(r *http.Request, name string) string {
	value, count := "", 0
	for _, cookie := range r.Cookies() {
		if cookie.Name == name {
			value, count = cookie.Value, count+1
		}
	}
	if count != 1 || len(value) != 43 {
		return ""
	}
	return value
}

func setCookie(w http.ResponseWriter, name, value string, expires time.Time) {
	maxAge := int(time.Until(expires).Seconds())
	if value == "" {
		maxAge = -1
	}
	http.SetCookie(w, &http.Cookie{Name: name, Value: value, Path: "/", HttpOnly: true, Secure: true,
		SameSite: http.SameSiteLaxMode, Expires: expires.UTC(), MaxAge: maxAge})
}

func (g *Gateway) validLocked(key [32]byte, audience string) (login, bool) {
	data, ok := g.sessions[key]
	user, exists := g.users[data.Actor]
	if !ok || !g.accountsReady || !exists || user.Disabled || data.Audience != audience || !time.Now().Before(data.Expires) {
		return login{}, false
	}
	if data.Parent != "" {
		raw, err := base64.RawURLEncoding.DecodeString(data.Parent)
		if err != nil || len(raw) != 32 {
			return login{}, false
		}
		parent := [32]byte(raw)
		p, ok := g.sessions[parent]
		if !ok || p.Actor != data.Actor || p.Audience != "entry" || !time.Now().Before(p.Expires) {
			return login{}, false
		}
	}
	return data, true
}

func (g *Gateway) authenticated(r *http.Request, name, audience string) (requestLogin, bool) {
	value := cookieValue(r, name)
	if value == "" {
		return requestLogin{}, false
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	key := hash(value)
	data, ok := g.validLocked(key, audience)
	return requestLogin{Hash: key, Data: data}, ok
}

func (g *Gateway) allowed(actor, id string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.allowedLocked(actor, id)
}

func (g *Gateway) allowedLocked(actor, id string) bool {
	user := g.users[actor]
	if !g.accountsReady || user.Disabled || !g.profiles.KnownProfile(id) {
		return false
	}
	for _, grant := range user.Profiles {
		if grant == id {
			return true
		}
	}
	return false
}

// role returns the effective role of a ready, enabled account or "".
func (g *Gateway) role(actor string) string {
	g.mu.Lock()
	defer g.mu.Unlock()
	user, ok := g.users[actor]
	if !g.accountsReady || !ok || user.Disabled {
		return ""
	}
	return user.EffectiveRole()
}

// grants lists what an administrator may do with every configured Profile:
// view, manage and stop everywhere, start only where the account is granted.
// It only consults the account table and the Profile set, never business state.
func (g *Gateway) grants(actor string) []Grant {
	ids := g.profiles.ProfileIDs()
	g.mu.Lock()
	defer g.mu.Unlock()
	user := g.users[actor]
	if !g.accountsReady || user.Disabled || user.EffectiveRole() != RoleAdmin {
		return nil
	}
	granted := make(map[string]bool, len(user.Profiles))
	for _, id := range user.Profiles {
		granted[id] = true
	}
	result := make([]Grant, 0, len(ids))
	for _, id := range ids {
		capabilities := []string{"view", "manage", "stop"}
		if granted[id] {
			capabilities = append(capabilities, "start")
		}
		result = append(result, Grant{Profile: id, Capabilities: capabilities})
	}
	return result
}

// Reauthenticated reports whether the request's login confirmed its password
// within ReauthWindow; handlers require it before sensitive changes.
func (g *Gateway) Reauthenticated(r *http.Request) bool {
	identity, ok := r.Context().Value(contextKey{}).(requestLogin)
	if !ok {
		return false
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	data, valid := g.validLocked(identity.Hash, "entry")
	return valid && !data.ReauthAt.IsZero() && time.Since(data.ReauthAt) <= ReauthWindow
}

// Grants returns the management grants the gateway attached to a request.
// Without a gateway, or outside the management surface, there are none.
func Grants(r *http.Request) ([]Grant, bool) {
	grants, ok := r.Context().Value(grantsKey{}).([]Grant)
	return grants, ok
}

// ContextWithGrants attaches a subject and grants exactly as the gateway does
// for the management surface. It exists for handler tests and carries no
// cookie, ticket or backend capability.
func ContextWithGrants(ctx context.Context, subject string, grants []Grant) context.Context {
	ctx = context.WithValue(ctx, contextKey{}, requestLogin{Data: login{Actor: subject, Audience: "entry"}})
	return context.WithValue(ctx, grantsKey{}, grants)
}

// Subject returns the authenticated account ID, or "" without a login.
func Subject(r *http.Request) string {
	identity, _ := r.Context().Value(contextKey{}).(requestLogin)
	return identity.Data.Actor
}

func safeHeaders(w http.ResponseWriter) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("X-Content-Type-Options", "nosniff")
}

func (g *Gateway) Wrap(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		safeHeaders(w)
		switch {
		case strings.EqualFold(r.Host, g.entry.Host):
			g.serveEntry(w, r, next)
		case strings.EqualFold(r.Host, g.session.Host):
			g.serveSession(w, r)
		default:
			http.Error(w, "Unknown entry", http.StatusMisdirectedRequest)
		}
	})
}

func profilePath(path string) string {
	parts := strings.Split(path, "/")
	if len(parts) < 3 || parts[1] != "browser" {
		return ""
	}
	return parts[2]
}

func (g *Gateway) serveEntry(w http.ResponseWriter, r *http.Request, next http.Handler) {
	if r.URL.Path == "/auth/login" {
		g.serveLogin(w, r)
		return
	}
	if r.URL.Path == "/healthz" || r.URL.Path == "/readyz" || (r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/bootstrap/")) {
		next.ServeHTTP(w, r)
		return
	}
	identity, ok := g.authenticated(r, entryCookie, "entry")
	if !ok {
		if r.Method == http.MethodGet && (r.URL.Path == "/" || strings.HasSuffix(r.URL.Path, "/")) {
			target := "/auth/login"
			if id := profilePath(r.URL.Path); g.profiles.KnownProfile(id) {
				target += "?next=" + url.QueryEscape("/browser/"+id+"/")
			}
			http.Redirect(w, r, target, http.StatusSeeOther)
		} else {
			http.Error(w, "Login required", http.StatusUnauthorized)
		}
		return
	}
	if r.URL.Path == "/auth/logout" {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if !g.verifyCSRF(w, r, identity.Data.CSRF) {
			return
		}
		g.mu.Lock()
		g.revokeLocked(identity.Hash)
		g.mu.Unlock()
		setCookie(w, entryCookie, "", time.Unix(1, 0))
		g.logger.Info("access session revoked", "event", "ACCESS_LOGOUT")
		http.Redirect(w, r, "/auth/login", http.StatusSeeOther)
		return
	}
	if r.URL.Path == "/" && r.Method == http.MethodGet {
		var links []string
		for _, id := range g.profiles.ProfileIDs() {
			if g.allowed(identity.Data.Actor, id) {
				links = append(links, id)
			}
		}
		pageHeaders(w)
		_ = indexTemplate.Execute(w, struct {
			Profiles []string
			CSRF     string
			Admin    bool
		}{links, identity.Data.CSRF, g.role(identity.Data.Actor) == RoleAdmin})
		return
	}
	if r.URL.Path == "/auth/reauth" || r.URL.Path == "/auth/password" {
		g.serveCredential(w, r, identity)
		return
	}
	if ManagePath(r.URL.Path) {
		if g.role(identity.Data.Actor) != RoleAdmin {
			pageHeaders(w)
			w.WriteHeader(http.StatusForbidden)
			_ = forbiddenTemplate.Execute(w, nil)
			return
		}
		switch r.Method {
		case http.MethodGet, http.MethodHead:
		case http.MethodPost:
			if !g.verifyCSRF(w, r, identity.Data.CSRF) {
				return
			}
		default:
			w.Header().Set("Allow", "GET, HEAD, POST")
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		ctx := context.WithValue(r.Context(), contextKey{}, identity)
		ctx = context.WithValue(ctx, grantsKey{}, g.grants(identity.Data.Actor))
		next.ServeHTTP(w, r.WithContext(ctx))
		return
	}
	id := profilePath(r.URL.Path)
	if !g.allowed(identity.Data.Actor, id) {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodGet && r.Method != http.MethodHead && !g.verifyCSRF(w, r, identity.Data.CSRF) {
		return
	}
	ctx := context.WithValue(r.Context(), contextKey{}, identity)
	next.ServeHTTP(w, r.WithContext(ctx))
}

func (g *Gateway) verifyCSRF(w http.ResponseWriter, r *http.Request, expected string) bool {
	if !SameOrigin(r, g.entry) || !strings.HasPrefix(r.Header.Get("Content-Type"), "application/x-www-form-urlencoded") {
		http.Error(w, "Request origin rejected", http.StatusForbidden)
		return false
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8192)
	if r.ParseForm() != nil || len(r.PostForm["csrf"]) != 1 || expected == "" || subtle.ConstantTimeCompare([]byte(r.PostForm.Get("csrf")), []byte(expected)) != 1 {
		http.Error(w, "Request validation failed", http.StatusForbidden)
		return false
	}
	return true
}

func CSRF(r *http.Request) string {
	identity, _ := r.Context().Value(contextKey{}).(requestLogin)
	return identity.Data.CSRF
}

func (g *Gateway) loginRate(r *http.Request, username string) bool {
	peer, _, _ := net.SplitHostPort(r.RemoteAddr)
	keys := []string{"peer:" + peer, "account:" + username}
	g.mu.Lock()
	defer g.mu.Unlock()
	g.pruneLocked(time.Now())
	if len(g.attempts) > 1024 {
		return false
	}
	for _, key := range keys {
		window := g.attempts[key]
		if window.Count >= 8 {
			return false
		}
	}
	for _, key := range keys {
		window := g.attempts[key]
		if window.Count == 0 {
			window.Since = time.Now()
		}
		window.Count++
		g.attempts[key] = window
	}
	return true
}

func nextProfile(value string) string {
	id := profilePath(value)
	if id == "" || value != "/browser/"+id+"/" || strings.ContainsAny(id, "%?\\#") {
		return ""
	}
	return id
}

func (g *Gateway) serveLogin(w http.ResponseWriter, r *http.Request) {
	pageHeaders(w)
	// same-origin is needed for the browser's form Origin header, including
	// the Chromium/WebView behavior already verified by the entry handler.
	w.Header().Set("Referrer-Policy", "same-origin")
	if r.Method == http.MethodGet {
		csrf, err := opaque()
		if err != nil {
			http.Error(w, "Login unavailable", http.StatusServiceUnavailable)
			return
		}
		setCookie(w, loginCookie, csrf, time.Now().Add(5*time.Minute))
		next := ""
		if id := nextProfile(r.URL.Query().Get("next")); g.profiles.KnownProfile(id) {
			next = "/browser/" + id + "/"
		}
		_ = loginTemplate.Execute(w, struct{ CSRF, Next string }{csrf, next})
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !g.verifyCSRF(w, r, cookieValue(r, loginCookie)) {
		return
	}
	username, password := r.PostForm.Get("username"), r.PostForm.Get("password")
	if len(r.PostForm["username"]) != 1 || len(r.PostForm["password"]) != 1 || !accountID.MatchString(username) || len(password) > 256 || len(password) < 1 {
		http.Error(w, "Invalid login request", http.StatusBadRequest)
		return
	}
	if !g.loginRate(r, username) {
		w.Header().Set("Retry-After", "60")
		http.Error(w, "Retry login later", http.StatusTooManyRequests)
		return
	}
	select {
	case g.passwordSlots <- struct{}{}:
		defer func() { <-g.passwordSlots }()
	default:
		http.Error(w, "Login is busy", http.StatusServiceUnavailable)
		return
	}
	g.mu.Lock()
	user, found := g.users[username]
	revision, ready := g.revision, g.accountsReady
	g.mu.Unlock()
	valid := checkPassword(user.PasswordHash, password)
	r.PostForm.Del("password")
	r.Form.Del("password")
	password = ""
	if !valid || !found || !ready || user.Disabled {
		g.logger.Warn("login denied", "event", "ACCESS_LOGIN_DENIED")
		http.Error(w, "Login failed", http.StatusUnauthorized)
		return
	}
	token, err1 := opaque()
	csrf, err2 := opaque()
	if err1 != nil || err2 != nil {
		http.Error(w, "Login unavailable", http.StatusServiceUnavailable)
		return
	}
	expires := time.Now().Add(g.cfg.Lifetime())
	g.mu.Lock()
	if revision != g.revision || !g.accountsReady || len(g.sessions) >= 4096 {
		g.mu.Unlock()
		http.Error(w, "Login unavailable", http.StatusServiceUnavailable)
		return
	}
	if previous := cookieValue(r, entryCookie); previous != "" {
		g.revokeLocked(hash(previous))
	}
	g.sessions[hash(token)] = login{Actor: username, Audience: "entry", CSRF: csrf, Expires: expires, AccountHash: accountHash(user)}
	g.mu.Unlock()
	setCookie(w, entryCookie, token, expires)
	setCookie(w, loginCookie, "", time.Unix(1, 0))
	g.logger.Info("login succeeded", "event", "ACCESS_LOGIN")
	next := "/"
	if id := nextProfile(r.PostForm.Get("next")); g.allowed(username, id) {
		next = "/browser/" + id + "/"
	}
	http.Redirect(w, r, next, http.StatusSeeOther)
}

// Grant keeps the backend capability in memory and returns only a bounded,
// single-use handoff. Both issuance and redemption check the same binding.
func (g *Gateway) Grant(r *http.Request, profile, sessionID, target string) (string, error) {
	identity, ok := r.Context().Value(contextKey{}).(requestLogin)
	if !ok || !g.allowed(identity.Data.Actor, profile) || g.checkBinding(r.Context(), profile, sessionID) != nil {
		return "", errors.New("current display authorization unavailable")
	}
	u, err := url.Parse(target)
	if err != nil || !validSessionID(sessionID) || u.User != nil || u.Fragment != "" || u.Host != g.session.Host || u.Scheme != "https" || u.Path != "/"+sessionID+"/" || u.RawPath != "" {
		return "", errors.New("invalid Session handoff target")
	}
	query, err := url.ParseQuery(u.RawQuery)
	if err != nil || len(query["access_token"]) != 1 || !backendTokenPattern.MatchString(query.Get("access_token")) {
		return "", errors.New("invalid Session capability")
	}
	for key, values := range query {
		if (key != "access_token" && key != "embedded") || len(values) != 1 {
			return "", errors.New("invalid Session handoff parameters")
		}
	}
	backendToken := query.Get("access_token")
	query.Del("access_token")
	u.RawQuery = query.Encode()
	value, err := opaque()
	if err != nil {
		return "", err
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	current, ok := g.validLocked(identity.Hash, "entry")
	if !ok || current.Actor != identity.Data.Actor || len(g.tickets) >= 256 {
		return "", errors.New("Session handoff unavailable")
	}
	expires := time.Now().Add(g.cfg.TicketLifetime())
	if current.Expires.Before(expires) {
		expires = current.Expires
	}
	g.tickets[hash(value)] = ticket{Parent: hashString(identity.Hash), Profile: profile, Session: sessionID,
		Target: u.String(), BackendToken: backendToken, Expires: expires}
	return g.session.String() + "/auth/accept?ticket=" + url.QueryEscape(value), nil
}

func (g *Gateway) accept(w http.ResponseWriter, r *http.Request) {
	query, err := url.ParseQuery(r.URL.RawQuery)
	if r.Method != http.MethodGet || err != nil || len(query) != 1 || len(query["ticket"]) != 1 || len(query.Get("ticket")) != 43 {
		http.Error(w, "Invalid handoff", http.StatusForbidden)
		return
	}
	g.mu.Lock()
	key := hash(query.Get("ticket"))
	pending, ok := g.tickets[key]
	delete(g.tickets, key)
	parentRaw, parentErr := base64.RawURLEncoding.DecodeString(pending.Parent)
	var parent [32]byte
	if parentErr == nil && len(parentRaw) == 32 {
		copy(parent[:], parentRaw)
	}
	identity, valid := g.validLocked(parent, "entry")
	g.mu.Unlock()
	if !ok || parentErr != nil || !valid || !time.Now().Before(pending.Expires) || !g.allowed(identity.Actor, pending.Profile) || g.checkBinding(r.Context(), pending.Profile, pending.Session) != nil {
		http.Error(w, "Handoff expired or unavailable", http.StatusForbidden)
		return
	}
	value, err := opaque()
	if err != nil {
		http.Error(w, "Handoff unavailable", http.StatusServiceUnavailable)
		return
	}
	g.mu.Lock()
	current, valid := g.validLocked(parent, "entry")
	if !valid {
		g.mu.Unlock()
		http.Error(w, "Handoff unavailable", http.StatusForbidden)
		return
	}
	if old := cookieValue(r, displayCookie+pending.Session); old != "" {
		previous, exists := g.validLocked(hash(old), "display")
		if exists && previous.Parent == pending.Parent && previous.Actor == current.Actor &&
			previous.Profile == pending.Profile && previous.Session == pending.Session && previous.BackendToken == pending.BackendToken {
			g.mu.Unlock()
			setCookie(w, displayCookie+pending.Session, old, previous.Expires)
			http.Redirect(w, r, pending.Target, http.StatusSeeOther)
			return
		}
		g.revokeLocked(hash(old))
	}
	if len(g.sessions) >= 4096 {
		g.mu.Unlock()
		http.Error(w, "Handoff unavailable", http.StatusServiceUnavailable)
		return
	}
	g.sessions[hash(value)] = login{Actor: current.Actor, Audience: "display", Parent: pending.Parent,
		Profile: pending.Profile, Session: pending.Session, BackendToken: pending.BackendToken, Expires: current.Expires,
		AccountHash: current.AccountHash}
	g.mu.Unlock()
	setCookie(w, displayCookie+pending.Session, value, current.Expires)
	http.Redirect(w, r, pending.Target, http.StatusSeeOther)
}

func pageHeaders(w http.ResponseWriter) {
	// A no-referrer form document makes Chromium send Origin: null on POST.
	// Cross-origin handoffs still receive no-referrer from safeHeaders.
	w.Header().Set("Referrer-Policy", "same-origin")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
}

var loginTemplate = template.Must(template.New("login").Parse(`<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录浏览器平台</title><style>body{font:16px system-ui;margin:3rem auto;padding:1rem;max-width:24rem}label{display:block;margin:1rem 0}input,button{font:inherit;padding:.5rem;box-sizing:border-box;width:100%}</style>
<h1>登录浏览器平台</h1><form method="post" action="/auth/login">
<input type="hidden" name="csrf" value="{{.CSRF}}"><input type="hidden" name="next" value="{{.Next}}">
<label>账号<input name="username" autocomplete="username" required maxlength="32"></label>
<label>密码<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label>
<button>登录</button></form></html>`))

var indexTemplate = template.Must(template.New("index").Parse(`<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>浏览器</title><style>body{font:16px system-ui;margin:2rem}li{margin:1rem 0}button{font:inherit;padding:.5rem 1rem}</style>
<h1>浏览器</h1><ul>{{range .Profiles}}<li><a href="/browser/{{.}}/">{{.}}</a></li>{{end}}</ul>
<p>{{if .Admin}}<a href="/manage/">管理面板</a> · {{end}}<a href="/auth/password">修改密码</a></p>
<form method="post" action="/auth/logout"><input type="hidden" name="csrf" value="{{.CSRF}}"><button>退出登录</button></form></html>`))

var forbiddenTemplate = template.Must(template.New("forbidden").Parse(`<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>需要管理员账号</title><style>body{font:16px system-ui;margin:3rem auto;padding:1rem;max-width:28rem}</style>
<h1>需要管理员账号</h1><p>管理面板只对管理员账号开放。请使用管理员账号登录，或返回 <a href="/">首页</a>。</p></html>`))

var reauthTemplate = template.Must(template.New("reauth").Parse(`<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>确认密码</title><style>body{font:16px system-ui;margin:3rem auto;padding:1rem;max-width:24rem}label{display:block;margin:1rem 0}input,button{font:inherit;padding:.5rem;box-sizing:border-box;width:100%}.err{color:#b3261e}</style>
<h1>确认密码</h1><p>敏感操作需要在 5 分钟内重新输入密码。</p>{{if .Error}}<p class="err">{{.Error}}</p>{{end}}<form method="post" action="/auth/reauth">
<input type="hidden" name="csrf" value="{{.CSRF}}"><input type="hidden" name="next" value="{{.Next}}">
<label>密码<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label>
<button>确认</button></form></html>`))

var passwordTemplate = template.Must(template.New("password").Parse(`<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>修改密码</title><style>body{font:16px system-ui;margin:3rem auto;padding:1rem;max-width:24rem}label{display:block;margin:1rem 0}input,button{font:inherit;padding:.5rem;box-sizing:border-box;width:100%}.err{color:#b3261e}.ok{color:#1b5e20}</style>
<h1>修改密码</h1>{{if .Error}}<p class="err">{{.Error}}</p>{{end}}{{if .Done}}<p class="ok">密码已更新，其他设备上的登录已撤销。</p>{{end}}<form method="post" action="/auth/password">
<input type="hidden" name="csrf" value="{{.CSRF}}">
<label>当前密码<input type="password" name="current" autocomplete="current-password" required maxlength="256"></label>
<label>新密码（12–256 字节）<input type="password" name="password" autocomplete="new-password" required minlength="12" maxlength="256"></label>
<label>再次输入新密码<input type="password" name="confirm" autocomplete="new-password" required minlength="12" maxlength="256"></label>
<button>更新密码</button></form><p><a href="/">返回首页</a></p></html>`))

func manageNext(value string) string {
	if strings.HasPrefix(value, "/manage/") && !strings.ContainsAny(value, "\\\r\n") && !strings.Contains(value, "//") && !strings.Contains(value, "..") {
		return value
	}
	return "/manage/"
}

// verifyPassword runs the same throttled, slot-limited check as login for an
// already authenticated account. The password never reaches logs or forms.
func (g *Gateway) verifyPassword(w http.ResponseWriter, r *http.Request, actor, password string) (bool, bool) {
	if len(password) < 1 || len(password) > 256 {
		http.Error(w, "Invalid password request", http.StatusBadRequest)
		return false, false
	}
	if !g.loginRate(r, actor) {
		w.Header().Set("Retry-After", "60")
		http.Error(w, "Retry later", http.StatusTooManyRequests)
		return false, false
	}
	select {
	case g.passwordSlots <- struct{}{}:
		defer func() { <-g.passwordSlots }()
	default:
		http.Error(w, "Verification is busy", http.StatusServiceUnavailable)
		return false, false
	}
	g.mu.Lock()
	user, found := g.users[actor]
	ready := g.accountsReady
	g.mu.Unlock()
	valid := checkPassword(user.PasswordHash, password)
	return valid && found && ready && !user.Disabled, true
}

// serveCredential handles password confirmation for sensitive management
// operations and self-service password changes for any login.
func (g *Gateway) serveCredential(w http.ResponseWriter, r *http.Request, identity requestLogin) {
	pageHeaders(w)
	if r.Method == http.MethodGet {
		if r.URL.Path == "/auth/reauth" {
			_ = reauthTemplate.Execute(w, struct{ CSRF, Next, Error string }{identity.Data.CSRF, manageNext(r.URL.Query().Get("next")), ""})
		} else {
			_ = passwordTemplate.Execute(w, struct {
				CSRF, Error string
				Done        bool
			}{identity.Data.CSRF, "", false})
		}
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !g.verifyCSRF(w, r, identity.Data.CSRF) {
		return
	}
	defer func() {
		for _, field := range []string{"password", "current", "confirm"} {
			r.PostForm.Del(field)
			r.Form.Del(field)
		}
	}()
	if r.URL.Path == "/auth/reauth" {
		next := manageNext(r.PostForm.Get("next"))
		valid, checked := g.verifyPassword(w, r, identity.Data.Actor, r.PostForm.Get("password"))
		if !checked {
			return
		}
		if !valid {
			g.logger.Warn("login denied", "event", "ACCESS_REAUTH_DENIED")
			w.WriteHeader(http.StatusUnauthorized)
			_ = reauthTemplate.Execute(w, struct{ CSRF, Next, Error string }{identity.Data.CSRF, next, "密码不正确"})
			return
		}
		g.mu.Lock()
		if data, ok := g.validLocked(identity.Hash, "entry"); ok {
			data.ReauthAt = time.Now()
			g.sessions[identity.Hash] = data
		}
		g.mu.Unlock()
		g.logger.Info("login succeeded", "event", "ACCESS_REAUTH")
		http.Redirect(w, r, next, http.StatusSeeOther)
		return
	}
	render := func(status int, message string, done bool) {
		w.WriteHeader(status)
		_ = passwordTemplate.Execute(w, struct {
			CSRF, Error string
			Done        bool
		}{identity.Data.CSRF, message, done})
	}
	current, replacement, confirm := r.PostForm.Get("current"), r.PostForm.Get("password"), r.PostForm.Get("confirm")
	if len(r.PostForm["password"]) != 1 || len(r.PostForm["confirm"]) != 1 || replacement != confirm {
		render(http.StatusBadRequest, "两次输入的新密码不一致", false)
		return
	}
	if len(replacement) < 12 || len(replacement) > 256 {
		render(http.StatusBadRequest, "新密码须为 12–256 字节", false)
		return
	}
	valid, checked := g.verifyPassword(w, r, identity.Data.Actor, current)
	if !checked {
		return
	}
	if !valid {
		g.logger.Warn("login denied", "event", "ACCESS_PASSWORD_DENIED")
		render(http.StatusUnauthorized, "当前密码不正确", false)
		return
	}
	if err := g.accounts.SetPassword(identity.Data.Actor, replacement); err != nil {
		render(http.StatusServiceUnavailable, "密码暂时无法更新", false)
		return
	}
	replacement, confirm = "", ""
	// Keep this login, revoke the account's other logins and displays.
	g.mu.Lock()
	for key, data := range g.sessions {
		if data.Actor == identity.Data.Actor && key != identity.Hash && data.Parent != hashString(identity.Hash) {
			g.revokeLocked(key)
		}
	}
	g.mu.Unlock()
	if err := g.reloadKeeping(identity.Data.Actor); err != nil {
		render(http.StatusServiceUnavailable, "密码已更新，但账号表重新加载失败，请重新登录", true)
		return
	}
	g.logger.Info("access session revoked", "event", "ACCESS_PASSWORD_CHANGED")
	render(http.StatusOK, "", true)
}

// Keep format errors independent of request contents in proxy callbacks.
func unavailable(w http.ResponseWriter, status int) {
	http.Error(w, fmt.Sprintf("Display access unavailable (%d)", status), status)
}
