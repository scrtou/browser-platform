package access

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
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

// HomeCard is the deliberately small, non-sensitive view rendered on the
// authenticated landing page. It must never contain Home paths, policy
// digests, Session URLs, credentials or resolved fingerprint values.
type HomeCard struct {
	ProfileID, Label, EntryPath           string
	Status, Health, HealthCode, Network   string
	NetworkName                           string
	BrowserTemplate, Fingerprint, Display string
	CheckedAt                             string
	Enabled, Available, Observed, Stale   bool
	NetworkIssue                          bool
}

// HomeProvider reads already-cached business summaries for the authorized
// Profile IDs. It must not probe, start, resume or stop a generation.
type HomeProvider func(context.Context, []string) []HomeCard

// WithDisplayPreference supplies a read-only per-Profile presentation preference.
func WithDisplayPreference(provider func(string) string) GatewayOption {
	return func(g *Gateway) { g.displayPreference = provider }
}

type GatewayOption func(*Gateway)

func WithHomeProvider(provider HomeProvider) GatewayOption {
	return func(g *Gateway) { g.homeProvider = provider }
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
	displayPreference func(string) string
	uiScaling         func(string) (int, int, bool)
	updateUIScaling   func(string, int, int, string) (int, error)
	cfg               Config
	entry, session    *url.URL
	profiles          ProfileSet
	homeProvider      HomeProvider
	accounts          *AccountStore
	checkBinding      BindingCheck
	logger            *slog.Logger
	proxy             *httputil.ReverseProxy
	mu                sync.Mutex
	users             map[string]Account
	revision          [32]byte
	accountsReady     bool
	setupRequired     bool
	sessions          map[[32]byte]login
	tickets           map[[32]byte]ticket
	attempts          map[string]attemptWindow
	active            map[uint64]activeRequest
	sequence          uint64
	passwordSlots     chan struct{}
}

type activeRequest struct {
	Hash   [32]byte
	Cancel context.CancelFunc
}

func New(ctx context.Context, cfg Config, entryURL, sessionURL string, profiles ProfileSet, check BindingCheck, logger *slog.Logger, options ...GatewayOption) (*Gateway, error) {
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
	for _, option := range options {
		option(g)
	}
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
		g.setupRequired = false
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
	g.setupRequired = registry.SetupRequired
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
		cards := make([]HomeCard, 0, len(links))
		if g.homeProvider != nil {
			allowed := make(map[string]bool, len(links))
			for _, id := range links {
				allowed[id] = true
			}
			for _, card := range g.homeProvider(r.Context(), append([]string(nil), links...)) {
				if allowed[card.ProfileID] {
					cards = append(cards, card)
					delete(allowed, card.ProfileID)
				}
			}
		} else {
			for _, id := range links {
				cards = append(cards, HomeCard{ProfileID: id, Label: id, EntryPath: "/browser/" + id + "/", Available: true, Enabled: true})
			}
		}
		networkIssues := 0
		latestSample := ""
		for _, card := range cards {
			if card.NetworkIssue {
				networkIssues++
			}
			if card.CheckedAt > latestSample {
				latestSample = card.CheckedAt
			}
		}
		nonce := homeScriptNonce()
		if nonce == "" {
			http.Error(w, "page unavailable", http.StatusInternalServerError)
			return
		}
		homePageHeaders(w, nonce)
		_ = indexTemplate.Execute(w, struct {
			Subject       string
			Cards         []HomeCard
			CSRF          string
			Admin         bool
			NetworkIssues int
			LatestSample  string
			ScriptNonce   string
		}{identity.Data.Actor, cards, identity.Data.CSRF, g.role(identity.Data.Actor) == RoleAdmin, networkIssues, latestSample, nonce})
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
		g.mu.Lock()
		setupRequired := g.setupRequired
		g.mu.Unlock()
		_ = loginTemplate.Execute(w, struct {
			CSRF, Next    string
			SetupRequired bool
		}{csrf, next, setupRequired})
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
		AccountHash: current.AccountHash, CSRF: current.CSRF}
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

func homeScriptNonce() string {
	nonceBytes := make([]byte, 18)
	if _, err := rand.Read(nonceBytes); err != nil {
		return ""
	}
	return base64.RawStdEncoding.EncodeToString(nonceBytes)
}

func homePageHeaders(w http.ResponseWriter, nonce string) {
	w.Header().Set("Referrer-Policy", "same-origin")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'nonce-"+nonce+"'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
}

var loginTemplate = template.Must(template.New("login").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录浏览器平台</title><style>
:root{--bg-page:#f4f6f8;--bg-card:#ffffff;--bg-input:#f1f5f9;--border-color:#e2e8f0;--border-focus:#2563eb;--text-primary:#0f172a;--text-secondary:#64748b;--color-primary:#2563eb;--color-primary-hover:#1d4ed8;--radius-md:10px;--radius-xl:20px;--shadow-card:0 20px 25px -5px rgba(15,23,42,.08),0 8px 10px -6px rgba(15,23,42,.04)}
*,*::before,*::after{box-sizing:border-box}body{min-height:100vh;margin:0;padding:2rem 1.5rem;display:flex;align-items:center;justify-content:center;background-color:var(--bg-page);background-image:radial-gradient(at 85% 15%,rgba(219,234,254,.7) 0,transparent 50%),radial-gradient(at 15% 85%,rgba(224,231,255,.5) 0,transparent 50%),linear-gradient(to right,rgba(226,232,240,.6) 1px,transparent 1px),linear-gradient(to bottom,rgba(226,232,240,.6) 1px,transparent 1px);background-size:100% 100%,100% 100%,44px 44px,44px 44px;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--text-primary)}
.auth-card{background:var(--bg-card);border:1px solid rgba(226,232,240,.8);border-radius:var(--radius-xl);box-shadow:var(--shadow-card);width:100%;max-width:28rem;padding:2.25rem}
.auth-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.75rem}
.auth-brand{display:flex;align-items:center;gap:.75rem}
.brand-icon{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:10px;background:#0f172a;color:#fff}
.brand-name{font-size:1.05rem;font-weight:700;line-height:1.2}
.brand-sub{font-size:.75rem;font-weight:600;letter-spacing:.06em;color:var(--text-secondary);text-transform:uppercase}
.auth-badges{display:flex;gap:.35rem}
.badge-capsule{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:8px;background:var(--bg-input);color:var(--text-secondary);border:1px solid var(--border-color)}
.auth-title{font-size:1.65rem;font-weight:700;letter-spacing:-.02em;margin:0 0 .4rem}
.auth-desc{color:var(--text-secondary);font-size:.9rem;margin:0 0 1.75rem;line-height:1.4}
.form-group{margin-bottom:1.25rem}
.form-label{display:block;font-size:.88rem;font-weight:600;margin-bottom:.5rem;color:var(--text-primary)}
.input-box{position:relative;display:flex;align-items:center}
.input-box svg{position:absolute;left:.85rem;color:var(--text-secondary);pointer-events:none}
.input-box input{font:inherit;font-size:.92rem;width:100%;padding:.75rem .9rem .75rem 2.5rem;background:var(--bg-input);border:1px solid transparent;border-radius:var(--radius-md);color:var(--text-primary);transition:all .15s ease}
.input-box input:focus{outline:none;background:#fff;border-color:var(--border-focus);box-shadow:0 0 0 3px rgba(37,99,235,.15)}
.btn-submit{display:block;width:100%;font:inherit;font-size:1rem;font-weight:600;padding:.8rem;border:none;border-radius:var(--radius-md);background:var(--color-primary);color:#fff;cursor:pointer;margin-top:1.5rem;transition:background-color .15s ease}
.btn-submit:hover{background:var(--color-primary-hover)}
.btn-submit:focus-visible{outline:2px solid var(--border-focus);outline-offset:2px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}
</style></head><body class="auth-page">
<main class="auth-card">
<div class="auth-header">
  <div class="auth-brand">
    <div class="brand-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg></div>
    <div>
      <div class="brand-name">浏览器平台</div>
      <div class="brand-sub">浏览器工作区</div>
    </div>
  </div>
  <div class="auth-badges">
    <span class="badge-capsule" title="安全凭据"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span>
    <span class="badge-capsule" title="安全密钥"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="15" r="4"/><line x1="10.85" y1="12.15" x2="19" y2="4"/><line x1="18" y1="5" x2="20" y2="7"/><line x1="15" y1="8" x2="17" y2="10"/></svg></span>
  </div>
</div>
<h1 class="auth-title">登录浏览器平台</h1>
<p class="auth-desc">使用你的账号访问已分配的浏览器。</p>
{{if .SetupRequired}}<p class="auth-subtitle" role="status">平台尚未初始化，请联系服务器管理员创建首位管理员账号。</p>{{else}}
<form method="post" action="/auth/login">
<input type="hidden" name="csrf" value="{{.CSRF}}"><input type="hidden" name="next" value="{{.Next}}">
<div class="form-group">
  <label class="form-label" for="username">账号</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
    <input id="username" name="username" autocomplete="username" required maxlength="32" placeholder="请输入账号">
  </div>
</div>
<div class="form-group">
  <label class="form-label" for="password">密码</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
    <input id="password" type="password" name="password" autocomplete="current-password" required maxlength="256" placeholder="请输入密码">
  </div>
</div>
<button type="submit" class="btn-submit">登录</button>
</form>{{end}}
</main></body></html>`))

var indexTemplate = template.Must(template.New("index").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>浏览器工作区</title><style>
:root{
  --bg-page:#f4f6f8;
  --bg-card:#ffffff;
  --bg-subtle:#f8fafc;
  --bg-input:#f1f5f9;
  --border-color:#e2e8f0;
  --border-subtle:#f1f5f9;
  --border-focus:#2563eb;
  --text-primary:#0f172a;
  --text-secondary:#64748b;
  --color-primary:#2563eb;
  --color-primary-hover:#1d4ed8;
  --color-success:#10b981;
  --color-success-bg:#ecfdf5;
  --color-warning:#f59e0b;
  --color-warning-bg:#fffbeb;
  --color-warning-border:#fde68a;
  --color-danger:#ef4444;
  --color-danger-bg:#fef2f2;
  --color-danger-border:#fecaca;
  --radius-sm:6px;
  --radius-md:10px;
  --radius-lg:14px;
  --radius-xl:18px;
  --shadow-sm:0 1px 2px 0 rgba(0,0,0,.05);
  --shadow-card:0 1px 3px rgba(0,0,0,.05),0 1px 2px rgba(0,0,0,.03);
  --shadow-md:0 4px 6px -1px rgba(0,0,0,.07),0 2px 4px -2px rgba(0,0,0,.05);
  --shadow-modal:0 25px 50px -12px rgba(15,23,42,.25);
}
*,*::before,*::after{box-sizing:border-box}
body{font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--text-primary);background:var(--bg-page);margin:0;padding:0;min-height:100vh}
a{color:var(--color-primary);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--border-focus);outline-offset:2px}
.stale{color:var(--color-danger)}
.meta{color:var(--text-secondary);font-size:.82rem}

/* Layout */
.app-layout{display:flex;min-height:100vh}
.app-sidebar{width:230px;background:#fff;border-right:1px solid var(--border-color);display:flex;flex-direction:column;flex-shrink:0;min-height:100vh;padding:1.25rem 1rem}
.sidebar-header{display:flex;align-items:center;justify-content:space-between;padding:.25rem .5rem 1.25rem;border-bottom:1px solid var(--border-color)}
.sidebar-brand{display:flex;align-items:center;gap:.75rem}
.brand-icon{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:10px;background:#0f172a;color:#fff}
.brand-title{font-size:1.05rem;font-weight:700;line-height:1.2}
.brand-badge{display:inline-block;font-size:.7rem;font-weight:500;color:var(--text-secondary);background:var(--bg-subtle);padding:.1rem .4rem;border-radius:4px;margin-top:.2rem}

.sidebar-collapse-btn{display:none;cursor:pointer;padding:.35rem;border-radius:var(--radius-sm);color:var(--text-secondary);border:none;background:transparent}
.sidebar-collapse-btn:hover{background:var(--bg-subtle);color:var(--text-primary)}

/* Sidebar Navigation */
.sidebar-nav{display:flex;flex-direction:column;gap:.35rem;margin:1.25rem 0;flex:1}
.nav-link{display:flex;align-items:center;gap:.75rem;padding:.65rem .85rem;border-radius:var(--radius-md);font-size:.92rem;font-weight:500;color:var(--text-secondary);transition:all .15s ease;text-decoration:none}
.nav-link:hover{background:var(--bg-subtle);color:var(--text-primary);text-decoration:none}
.nav-link.active{background:#eff6ff;color:var(--color-primary);font-weight:600}
.nav-link svg{flex-shrink:0}

/* Expandable Menu */
.nav-group{margin:0}
.nav-group-summary{cursor:pointer;list-style:none;user-select:none;display:flex;align-items:center;gap:.75rem;padding:.65rem .85rem;border-radius:var(--radius-md);font-size:.92rem;font-weight:500;color:var(--text-secondary);transition:all .15s ease}
.nav-group-summary::-webkit-details-marker{display:none}
.nav-group-summary:hover{background:var(--bg-subtle);color:var(--text-primary)}
.nav-group-summary .chevron{margin-left:auto;transition:transform .2s ease}
.nav-group[open] .nav-group-summary .chevron{transform:rotate(180deg)}
.nav-sub{display:flex;flex-direction:column;gap:.25rem;padding-left:.85rem;margin:.25rem 0 .5rem;border-left:2px solid var(--border-color);margin-left:1.5rem}
.nav-sub-link{display:flex;align-items:center;gap:.65rem;padding:.5rem .75rem;border-radius:var(--radius-sm);font-size:.85rem;font-weight:500;color:var(--text-secondary);text-decoration:none;transition:all .15s ease}
.nav-sub-link:hover{background:var(--bg-subtle);color:var(--text-primary);text-decoration:none}
.nav-sub-link.active{background:#eff6ff;color:var(--color-primary);font-weight:600}

/* Sidebar Footer */
.sidebar-footer{margin-top:auto;padding-top:1rem;border-top:1px solid var(--border-color);display:flex;flex-direction:column;gap:.75rem}
.online-indicator{display:flex;align-items:center;gap:.45rem;font-size:.82rem;font-weight:500;color:var(--color-success)}
.online-dot{width:8px;height:8px;border-radius:50%;background:var(--color-success)}
.sidebar-actions{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
.actions form{margin:0}
.btn,.link-btn{font:inherit;font-size:.82rem;font-weight:500;border:1px solid var(--border-color);background:#fff;border-radius:var(--radius-sm);padding:.4rem .65rem;color:var(--text-primary);cursor:pointer;display:inline-flex;align-items:center;gap:.35rem;text-decoration:none;box-sizing:border-box}
.btn:hover,.link-btn:hover{background:var(--bg-subtle);text-decoration:none}
.btn-primary{background:var(--color-primary);color:#fff;border-color:var(--color-primary)}
.btn-primary:hover{background:var(--color-primary-hover);color:#fff}
.btn-secondary{background:#fff;color:var(--text-primary);border-color:var(--border-color)}
.btn-secondary:hover{background:var(--bg-subtle)}
.btn-sm{min-height:30px;padding:.25rem .6rem;font-size:.82rem}

/* Main Area */
.app-main-wrapper{flex:1;min-width:0;display:flex;flex-direction:column;padding:1.5rem 2rem}
.app-header{display:flex;justify-content:space-between;gap:1.5rem;align-items:flex-start;margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:1px solid var(--border-color)}
.topbar-left{display:flex;align-items:center;gap:.85rem}
.sidebar-toggle-btn{cursor:pointer;user-select:none}
.header-main{min-width:0}
.app-title{font-size:1.5rem;font-weight:700;margin:0 0 .25rem;letter-spacing:-.01em}
.header-meta{margin:0;color:var(--text-secondary);font-size:.85rem}
.header-actions{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap}

/* Stats */
.summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin-bottom:1.5rem}
.stat{background:#fff;border:1px solid var(--border-color);border-radius:var(--radius-lg);padding:1.1rem 1.25rem;box-shadow:var(--shadow-card)}
.stat-head{display:flex;justify-content:space-between;align-items:flex-start}
.stat strong{display:block;font-size:1.65rem;font-weight:700;margin-top:.4rem;color:var(--text-primary);line-height:1.2}
.stat-icon{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;background:#eff6ff;color:var(--color-primary)}

/* Browser Table / List */
.table-container{width:100%;overflow-x:auto;border:1px solid var(--border-color);border-radius:var(--radius-lg);background:#fff;margin-bottom:1.5rem;box-shadow:var(--shadow-card)}
.browser-table{width:100%;border-collapse:collapse;font-size:.88rem;text-align:left}
.browser-table th,.browser-table td{padding:.85rem 1rem;border-bottom:1px solid var(--border-color);vertical-align:middle}
.browser-table th{background:var(--bg-subtle);font-weight:600;font-size:.82rem;color:var(--text-secondary);white-space:nowrap}
.browser-table tr:last-child td{border-bottom:none}
.browser-table tbody tr:hover td{background:#fafafa}
.browser-title-wrap{display:flex;flex-direction:column;gap:.15rem}
.browser-name{font-weight:600;font-size:.95rem;color:var(--text-primary)}
.browser-id{font-size:.78rem;color:var(--text-secondary)}
.browser-table .cell-network{max-width:16rem;overflow-wrap:anywhere}
.network-summary{display:flex;flex-direction:column;align-items:flex-start;gap:.3rem}
.network-mode{color:var(--text-secondary);line-height:1.5}
.badges{display:flex;gap:.35rem;flex-wrap:wrap;align-items:center}
.badge{display:inline-flex;align-items:center;gap:.3rem;font-size:.75rem;font-weight:500;padding:.2rem .55rem;border-radius:999px;line-height:1.3;background:var(--bg-subtle);color:var(--text-secondary)}
.badge-success{background:var(--color-success-bg);color:var(--color-success);border:1px solid #a7f3d0}
.badge-disabled,.badge.off{background:#f1f5f9;color:var(--text-secondary)}
.badge-status{background:#eff6ff;color:var(--color-primary);border:1px solid #bfdbfe}
.badge-stale,.badge.warn{background:var(--color-warning-bg);color:var(--color-warning);border:1px solid var(--color-warning-border)}
.th-actions,.cell-actions{text-align:right}
.row-actions{display:inline-flex;align-items:center;gap:.45rem;justify-content:flex-end;flex-wrap:wrap}

/* No-script Fallback */
.details-fallback{display:inline-block;margin:0}
.details-fallback summary::-webkit-details-marker{display:none}
.details-fallback[open] .fallback-details-body{margin-top:.75rem;padding:.85rem;background:var(--bg-subtle);border:1px solid var(--border-color);border-radius:var(--radius-md);text-align:left}
.trigger-details-btn{display:none}

/* Grid & Fields */
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem;background:var(--bg-subtle);padding:.85rem;border-radius:var(--radius-md)}
.field{min-width:0}
.field .meta{font-size:.75rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.02em;margin-bottom:.15rem;display:block}
.value{font-size:.88rem;color:var(--text-primary);word-break:break-word}

/* Native Dialog Modal */
dialog.progressive-modal{display:none;position:fixed;inset:0;margin:auto;max-width:580px;width:calc(100% - 2rem);max-height:90vh;overflow-y:auto;border-radius:var(--radius-xl);border:1px solid rgba(226,232,240,.9);box-shadow:var(--shadow-modal);z-index:1000;padding:1.75rem;background:#fff}
dialog.progressive-modal.dialog-ready[open]{display:block}
dialog.progressive-modal::backdrop{background:rgba(15,23,42,.45);backdrop-filter:blur(3px)}
.dialog-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem;padding-bottom:.75rem;border-bottom:1px solid var(--border-color)}
.dialog-title{font-size:1.15rem;font-weight:700;margin:0 0 .2rem}
.dialog-close-btn{background:transparent;border:none;font-size:1.4rem;line-height:1;color:var(--text-secondary);cursor:pointer;padding:.2rem;border-radius:4px}
.dialog-close-btn:hover{color:var(--text-primary)}
.dialog-actions .dialog-close-btn{font-size:.82rem;padding:.4rem .65rem;border:1px solid var(--border-color)}
.dialog-status-line{display:flex;align-items:center;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
.dialog-actions{display:flex;justify-content:flex-end;gap:.75rem;margin-top:1.25rem;padding-top:1rem;border-top:1px solid var(--border-color)}

/* Empty & Footer */
.empty{background:#fff;border:1px dashed var(--border-color);border-radius:var(--radius-lg);padding:3rem 1.5rem;text-align:center}
.empty h2{margin:0 0 .5rem;font-size:1.2rem}
.app-footer{margin-top:auto;padding-top:1.5rem;border-top:1px solid var(--border-color)}

/* Sidebar Toggle Mechanics */
.sidebar-toggle-check{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);border:0}
.sidebar-backdrop{display:none}

@media(min-width:769px){
  .app-sidebar{transition:margin-left .2s ease,width .2s ease,opacity .2s ease}
  .sidebar-toggle-check:checked ~ .app-layout .app-sidebar{width:0;visibility:hidden;padding-left:0;padding-right:0;overflow:hidden;opacity:0;border-right:none;pointer-events:none}
}
@media(max-width:768px){
  .app-layout{flex-direction:column}
  .app-sidebar{position:fixed;top:0;bottom:0;left:0;width:260px;height:100vh;z-index:1000;background:#fff;box-shadow:var(--shadow-modal);visibility:hidden;transform:translateX(-100%);transition:transform .25s ease;overflow-y:auto}
  .sidebar-collapse-btn{display:inline-flex;align-items:center;justify-content:center}
  .sidebar-toggle-check:checked ~ .sidebar-backdrop{display:block;position:fixed;inset:0;background:rgba(15,23,42,.45);backdrop-filter:blur(2px);z-index:999}
  .sidebar-toggle-check:checked ~ .app-layout .app-sidebar{visibility:visible;transform:translateX(0)}
  .app-main-wrapper{padding:1rem}
  .app-header{flex-direction:column;align-items:stretch;gap:1rem}
  .summary{grid-template-columns:1fr 1fr}
}
@media(max-width:540px){
  .summary{grid-template-columns:1fr 1fr;gap:.65rem}
  .summary .stat:last-child{grid-column:1/-1}
  .stat{padding:.85rem}
  .browser-table th,.browser-table td{padding:.75rem .5rem}
  .browser-table{min-width:34rem}
  .row-actions .btn{white-space:nowrap}
  .browser-name{overflow-wrap:anywhere}
  .grid{grid-template-columns:1fr}
}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}
.sidebar-toggle-check:focus-visible ~ .app-layout .sidebar-toggle-btn,
.sidebar-toggle-btn:focus-visible,.sidebar-collapse-btn:focus-visible{outline:2px solid var(--border-focus);outline-offset:2px}
` + PasswordDialogCSS + `</style></head><body>
<input type="checkbox" id="sidebar-toggle" class="sidebar-toggle-check sr-only" aria-label="收起或展开侧栏">
<label for="sidebar-toggle" class="sidebar-backdrop" aria-hidden="true"></label>
<div class="app-layout">
  <aside class="app-sidebar sidebar" id="sidebar" aria-label="工作区侧栏">
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <div class="brand-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg></div>
        <div>
          <div class="brand-title">浏览器工作区</div>
          <div class="brand-badge">控制台中心</div>
        </div>
      </div>
      <label for="sidebar-toggle" class="sidebar-collapse-btn" role="button" tabindex="0" title="收起侧栏" aria-label="收起侧栏">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </label>
    </div>
    <nav class="sidebar-nav nav-tabs" aria-label="工作区导航">
      <a href="/" class="nav-link tab-item active" aria-current="page">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        <span>工作区概览</span>
      </a>
      {{if .Admin}}
      <details class="nav-group" id="manage-menu">
        <summary class="nav-group-summary" >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
          <span>管理面板</span>
          <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </summary>
        <div class="nav-sub">
          <a href="/manage/?tab=browsers" class="nav-sub-link tab-item">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            <span>浏览器</span>
          </a>
          <a href="/manage/?tab=network" class="nav-sub-link tab-item">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            <span>网络代理</span>
          </a>
          <a href="/manage/?tab=fingerprint-data" class="nav-sub-link tab-item">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 0-10 10c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.1-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/></svg>
            <span>指纹数据</span>
          </a>
          <a href="/manage/?tab=accounts" class="nav-sub-link tab-item">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>访问账号</span>
          </a>
        </div>
      </details>
      {{end}}
      <a href="/auth/password" class="nav-link tab-item">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span>修改密码</span>
      </a>
    </nav>
    <div class="sidebar-footer">
      <div class="online-indicator"><span class="online-dot"></span>已登录</div>
      <form method="post" action="/auth/logout" style="margin:0"><input type="hidden" name="csrf" value="{{.CSRF}}"><button class="btn btn-secondary" style="width:100%;justify-content:center" type="submit"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>退出登录</button></form>
    </div>
  </aside>

  <div class="app-main-wrapper main-wrapper">
    <header class="app-header topbar">
      <div class="topbar-left">
        <label for="sidebar-toggle" class="sidebar-toggle-btn btn btn-secondary" role="button" tabindex="0" title="收起/展开侧栏" aria-label="收起/展开侧栏">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          <span class="sidebar-toggle-text">侧栏</span>
        </label>
        <div class="header-main brand">
          <h1 class="app-title">浏览器工作区</h1>
          <p class="header-meta meta">{{.Subject}} · 只显示当前账号已授权的浏览器</p>
        </div>
      </div>
    </header>

    <main>
      <section class="summary" aria-label="工作区摘要">
        <div class="stat">
          <div class="stat-head"><span class="meta">可访问浏览器</span><span class="stat-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg></span></div>
          <strong>{{len .Cards}}</strong>
        </div>
        <div class="stat">
          <div class="stat-head"><span class="meta">需要处理的网络问题</span><span class="stat-icon" style="background:var(--color-warning-bg);color:var(--color-warning)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></span></div>
          <strong>{{.NetworkIssues}}</strong>
        </div>
        <div class="stat">
          <div class="stat-head"><span class="meta">最近健康采样</span><span class="stat-icon" style="background:var(--color-success-bg);color:var(--color-success)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span></div>
          <strong style="font-size:1.1rem;margin-top:.6rem">{{if .LatestSample}}{{.LatestSample}}{{else}}尚无采样{{end}}</strong>
        </div>
      </section>

      {{if .Cards}}
      <section class="browser-list-section cards" aria-label="浏览器列表">
        <div class="table-container">
          <table class="browser-table">
            <thead>
              <tr>
                <th scope="col">浏览器名称</th>
                <th scope="col">状态</th>
                <th scope="col">网络</th>
                <th scope="col" class="th-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {{range .Cards}}
              <tr class="browser-row">
                <td class="cell-name">
                  <div class="browser-title-wrap">
                    <span class="browser-name">{{.Label}}</span>
                    {{if ne .Label .ProfileID}}<span class="meta browser-id">{{.ProfileID}}</span>{{end}}
                  </div>
                </td>
                <td class="cell-status">
                  <div class="badges">
                    {{if not .Available}}<span class="badge warn">摘要不可用</span>
                    {{else}}
                      {{if .Enabled}}<span class="badge badge-success">已启用</span>{{else}}<span class="badge badge-disabled">已停用</span>{{end}}
                      <span class="badge badge-status">{{if .Status}}{{.Status}}{{else}}unknown{{end}}</span>
                      {{if .Stale}}<span class="badge badge-stale">健康已过期</span>{{end}}
                    {{end}}
                  </div>
                </td>
                <td class="cell-network">
                  <div class="network-summary">
                    <span class="network-mode">{{if not .Available}}摘要不可用{{else if eq .Network "direct"}}直连{{else if eq .Network "proxy_required"}}{{if .NetworkName}}{{.NetworkName}}{{else}}代理名称不可用{{end}}{{else if eq .Network "managed"}}受管理网络{{else if eq .Network "unmanaged"}}未受管理{{else if eq .Network "legacy"}}旧版网络{{else if .Network}}{{.Network}}{{else}}未登记{{end}}</span>
                    {{if .NetworkIssue}}<span class="badge warn">需要处理</span>{{end}}
                  </div>
                </td>
                <td class="cell-actions">
                  <div class="row-actions">
                    <a class="btn btn-primary btn-sm" href="{{.EntryPath}}">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                      <span>打开浏览器</span>
                    </a>
                    <button type="button" class="btn btn-secondary btn-sm trigger-details-btn" data-dialog-id="details-dialog-{{.ProfileID}}" aria-haspopup="dialog">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                      <span>详情</span>
                    </button>
                    <details class="details-fallback">
                      <summary class="btn btn-secondary btn-sm fallback-summary">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                        <span>详情</span>
                      </summary>
                      <div class="fallback-details-body">
                        <div class="grid details-grid">
                          <div class="field"><span class="meta">健康</span><span class="value">{{if not .Available}}摘要不可用{{else if .Stale}}<span class="stale">未知（采样已过期）</span>{{else if .Observed}}{{.Health}}{{if .HealthCode}} · {{.HealthCode}}{{end}}{{else}}未观测{{end}}</span></div>
                          <div class="field"><span class="meta">网络</span><span class="value">{{if .NetworkName}}{{.NetworkName}} · {{end}}{{.Network}}{{if .NetworkIssue}} · <span class="stale">需要处理</span>{{end}}</span></div>
                          <div class="field"><span class="meta">浏览器模板</span><span class="value">{{if .BrowserTemplate}}{{.BrowserTemplate}}{{else}}legacy / 未登记{{end}}</span></div>
                          <div class="field"><span class="meta">指纹模板</span><span class="value">{{if .Fingerprint}}{{.Fingerprint}}{{else}}未登记{{end}}</span></div>
                          <div class="field"><span class="meta">显示模板</span><span class="value">{{if .Display}}{{.Display}}{{else}}未登记{{end}}</span></div>
                          <div class="field"><span class="meta">采样时间</span><span class="value">{{if .CheckedAt}}{{.CheckedAt}}{{else}}—{{end}}</span></div>
                        </div>
                      </div>
                    </details>
                  </div>
                </td>
              </tr>
              {{end}}
            </tbody>
          </table>
        </div>

        {{range .Cards}}
        <dialog id="details-dialog-{{.ProfileID}}" class="modal-dialog progressive-modal details-dialog" aria-labelledby="dialog-title-{{.ProfileID}}">
          <div class="dialog-header">
            <div>
              <h2 id="dialog-title-{{.ProfileID}}" class="dialog-title">{{.Label}}</h2>
              {{if ne .Label .ProfileID}}<div class="meta">{{.ProfileID}}</div>{{end}}
            </div>
            <button type="button" class="dialog-close-btn" aria-label="关闭详情">×</button>
          </div>
          <div class="dialog-body">
            <div class="dialog-status-line">
              <span class="meta">当前状态：</span>
              {{if not .Available}}<span class="badge warn">摘要不可用</span>
              {{else}}
                {{if .Enabled}}<span class="badge badge-success">已启用</span>{{else}}<span class="badge badge-disabled">已停用</span>{{end}}
                <span class="badge badge-status">{{if .Status}}{{.Status}}{{else}}unknown{{end}}</span>
                {{if .Stale}}<span class="badge badge-stale">健康已过期</span>{{end}}
              {{end}}
            </div>
            <div class="grid details-grid">
              <div class="field">
                <span class="meta">健康</span>
                <span class="value">{{if not .Available}}摘要不可用{{else if .Stale}}<span class="stale">未知（采样已过期）</span>{{else if .Observed}}{{.Health}}{{if .HealthCode}} · {{.HealthCode}}{{end}}{{else}}未观测{{end}}</span>
              </div>
              <div class="field">
                <span class="meta">网络</span>
                <span class="value">{{if .NetworkName}}{{.NetworkName}} · {{end}}{{.Network}}{{if .NetworkIssue}} · <span class="stale">需要处理</span>{{end}}</span>
              </div>
              <div class="field">
                <span class="meta">浏览器模板</span>
                <span class="value">{{if .BrowserTemplate}}{{.BrowserTemplate}}{{else}}legacy / 未登记{{end}}</span>
              </div>
              <div class="field">
                <span class="meta">指纹模板</span>
                <span class="value">{{if .Fingerprint}}{{.Fingerprint}}{{else}}未登记{{end}}</span>
              </div>
              <div class="field">
                <span class="meta">显示模板</span>
                <span class="value">{{if .Display}}{{.Display}}{{else}}未登记{{end}}</span>
              </div>
              <div class="field">
                <span class="meta">采样时间</span>
                <span class="value">{{if .CheckedAt}}{{.CheckedAt}}{{else}}—{{end}}</span>
              </div>
            </div>
          </div>
          <div class="dialog-actions">
            <a class="btn btn-primary" href="{{.EntryPath}}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              <span>打开浏览器</span>
            </a>
            <button type="button" class="btn btn-secondary dialog-close-btn">关闭</button>
          </div>
        </dialog>
        {{end}}
      </section>
      {{else}}
      <section class="empty">
        <h2>没有可访问的浏览器</h2>
        <p class="meta">当前账号没有分配浏览器。请联系管理员分配访问权限。</p>
      </section>
      {{end}}
    </main>
    <footer class="app-footer footer meta">状态以最近一次健康采样为准。</footer>
  </div>
</div>

` + PasswordDialogMarkup + `
<script nonce="{{.ScriptNonce}}">
(() => {
  const triggers = document.querySelectorAll('.trigger-details-btn');
  const fallbacks = document.querySelectorAll('.details-fallback');
  if (typeof HTMLDialogElement === 'function' && typeof HTMLDialogElement.prototype.showModal === 'function') {
    triggers.forEach(btn => {
      btn.style.display = 'inline-flex';
      const dialogId = btn.getAttribute('data-dialog-id');
      const dialog = document.getElementById(dialogId);
      if (!dialog) return;
      dialog.classList.add('dialog-ready');
      let lastFocus;
      btn.addEventListener('click', () => {
        lastFocus = btn;
        dialog.showModal();
        const first = dialog.querySelector('button, a[href], [tabindex]:not([tabindex="-1"])');
        if (first) first.focus();
      });
      dialog.querySelectorAll('.dialog-close-btn').forEach(closeBtn => {
        closeBtn.addEventListener('click', () => dialog.close());
      });
      dialog.addEventListener('close', () => {
        if (lastFocus && (document.activeElement === document.body || dialog.contains(document.activeElement))) {
          lastFocus.focus();
        }
      });
      dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], summary, [tabindex]:not([tabindex="-1"])')].filter(el => el.getClientRects().length);
        if (!controls.length) { event.preventDefault(); return; }
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });
    });
    fallbacks.forEach(el => el.style.display = 'none');
  }

  const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.app-sidebar');
  const main = document.querySelector('.app-main-wrapper');
  const trigger = document.querySelector('.sidebar-toggle-btn');
  const mobile = window.matchMedia('(max-width: 768px)');
  if (toggle && sidebar && trigger) {
    toggle.tabIndex = -1;
    const sync = (focus) => {
      const open = mobile.matches ? toggle.checked : !toggle.checked;
      trigger.setAttribute('aria-expanded', String(open));
      trigger.setAttribute('aria-controls', 'sidebar');
      sidebar.inert = !open;
      main.inert = mobile.matches && open;
      if (focus) {
        if (mobile.matches && open) sidebar.querySelector('.sidebar-collapse-btn').focus();
        else trigger.focus();
      }
    };
    toggle.addEventListener('change', () => sync(true));
    document.querySelectorAll('.sidebar-toggle-btn, .sidebar-collapse-btn').forEach(btn => {
      btn.addEventListener('keydown', event => {
        if (event.key === ' ' || event.key === 'Enter') {
          event.preventDefault(); toggle.checked = !toggle.checked; sync(true);
        }
      });
    });
    document.addEventListener('keydown', event => {
      if (!mobile.matches || !toggle.checked || document.querySelector('dialog[open]')) return;
      if (event.key === 'Escape') { event.preventDefault(); toggle.checked = false; sync(true); }
      if (event.key === 'Tab') {
        const controls = [...sidebar.querySelectorAll('a[href], button, summary, [tabindex="0"]')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    mobile.addEventListener('change', () => { toggle.checked = false; sync(false); });
    sync(false);
  }
})();
` + PasswordDialogScript + `
</script>
</body></html>`))

var forbiddenTemplate = template.Must(template.New("forbidden").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>需要管理员账号</title><style>
:root{--bg-page:#f4f6f8;--bg-card:#ffffff;--border-color:#e2e8f0;--text-primary:#0f172a;--text-secondary:#64748b;--color-danger:#ef4444;--radius-md:10px;--radius-xl:20px;--shadow-card:0 20px 25px -5px rgba(15,23,42,.08),0 8px 10px -6px rgba(15,23,42,.04)}
*,*::before,*::after{box-sizing:border-box}body{min-height:100vh;margin:0;padding:2rem 1.5rem;display:flex;align-items:center;justify-content:center;background:var(--bg-page);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--text-primary)}
.auth-card{background:var(--bg-card);border:1px solid rgba(226,232,240,.8);border-radius:var(--radius-xl);box-shadow:var(--shadow-card);width:100%;max-width:28rem;padding:2.25rem;text-align:center}
.icon-box{display:inline-flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:12px;background:#fef2f2;color:var(--color-danger);margin-bottom:1.25rem}
h1{font-size:1.45rem;font-weight:700;margin:0 0 .5rem}
p{color:var(--text-secondary);font-size:.9rem;line-height:1.5;margin:0 0 1.5rem}
a{color:#2563eb;text-decoration:none;font-weight:600}a:hover{text-decoration:underline}
.btn-back{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;padding:.7rem 1.25rem;border-radius:var(--radius-md);background:#0f172a;color:#fff;text-decoration:none;font-weight:600;font-size:.9rem}
.btn-back:hover{background:#1e293b;text-decoration:none}
</style></head><body>
<main class="auth-card">
<div class="icon-box"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>
<h1>需要管理员账号</h1>
<p>管理面板只对管理员账号开放。请使用管理员账号登录，或返回 <a href="/">首页</a>。</p>
<a href="/" class="btn-back">返回首页</a>
</main></body></html>`))

var reauthTemplate = template.Must(template.New("reauth").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>确认密码</title><style>
:root{--bg-page:#f4f6f8;--bg-card:#ffffff;--bg-input:#f1f5f9;--border-color:#e2e8f0;--border-focus:#2563eb;--text-primary:#0f172a;--text-secondary:#64748b;--color-primary:#2563eb;--color-primary-hover:#1d4ed8;--color-danger:#ef4444;--radius-md:10px;--radius-xl:20px;--shadow-card:0 20px 25px -5px rgba(15,23,42,.08),0 8px 10px -6px rgba(15,23,42,.04)}
*,*::before,*::after{box-sizing:border-box}body{min-height:100vh;margin:0;padding:2rem 1.5rem;display:flex;align-items:center;justify-content:center;background:var(--bg-page);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--text-primary)}
.auth-card{background:var(--bg-card);border:1px solid rgba(226,232,240,.8);border-radius:var(--radius-xl);box-shadow:var(--shadow-card);width:100%;max-width:28rem;padding:2.25rem}
.auth-header{display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem}
.brand-icon{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:10px;background:#0f172a;color:#fff}
.brand-title{font-size:1.05rem;font-weight:700;line-height:1.2}
.brand-sub{font-size:.75rem;color:var(--text-secondary);font-weight:600;text-transform:uppercase}
h1{font-size:1.5rem;font-weight:700;margin:0 0 .4rem}
p{color:var(--text-secondary);font-size:.9rem;line-height:1.4;margin:0 0 1.5rem}
.err{color:var(--color-danger);background:#fef2f2;border:1px solid #fecaca;padding:.65rem .85rem;border-radius:var(--radius-md);font-size:.85rem;margin-bottom:1.25rem}
.form-group{margin-bottom:1.25rem}
.form-label{display:block;font-size:.88rem;font-weight:600;margin-bottom:.5rem;color:var(--text-primary)}
.input-box{position:relative;display:flex;align-items:center}
.input-box svg{position:absolute;left:.85rem;color:var(--text-secondary);pointer-events:none}
.input-box input{font:inherit;font-size:.92rem;width:100%;padding:.75rem .9rem .75rem 2.5rem;background:var(--bg-input);border:1px solid transparent;border-radius:var(--radius-md);color:var(--text-primary)}
.input-box input:focus{outline:none;background:#fff;border-color:var(--border-focus);box-shadow:0 0 0 3px rgba(37,99,235,.15)}
.btn-submit{display:block;width:100%;font:inherit;font-size:1rem;font-weight:600;padding:.8rem;border:none;border-radius:var(--radius-md);background:var(--color-primary);color:#fff;cursor:pointer;margin-top:1.5rem}
.btn-submit:hover{background:var(--color-primary-hover)}
</style></head><body>
<main class="auth-card">
<div class="auth-header">
  <div class="brand-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
  <div><div class="brand-title">安全验证</div><div class="brand-sub">CONFIRM CREDENTIALS</div></div>
</div>
<h1>确认密码</h1>
<p>敏感操作需要在 5 分钟内重新输入密码。</p>
{{if .Error}}<p class="err">{{.Error}}</p>{{end}}
<form method="post" action="/auth/reauth">
<input type="hidden" name="csrf" value="{{.CSRF}}"><input type="hidden" name="next" value="{{.Next}}">
<div class="form-group">
  <label class="form-label" for="password">密码</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
    <input id="password" type="password" name="password" autocomplete="current-password" required maxlength="256" placeholder="输入当前密码">
  </div>
</div>
<button type="submit" class="btn-submit">确认</button>
</form></main></body></html>`))

var passwordTemplate = template.Must(template.New("password").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>修改密码</title><style>
:root{--bg-page:#f4f6f8;--bg-card:#ffffff;--bg-input:#f1f5f9;--border-color:#e2e8f0;--border-focus:#2563eb;--text-primary:#0f172a;--text-secondary:#64748b;--color-primary:#2563eb;--color-primary-hover:#1d4ed8;--color-success:#10b981;--color-danger:#ef4444;--radius-md:10px;--radius-xl:20px;--shadow-card:0 20px 25px -5px rgba(15,23,42,.08),0 8px 10px -6px rgba(15,23,42,.04)}
*,*::before,*::after{box-sizing:border-box}body{min-height:100vh;margin:0;padding:2rem 1.5rem;display:flex;align-items:center;justify-content:center;background:var(--bg-page);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--text-primary)}
.auth-card{background:var(--bg-card);border:1px solid rgba(226,232,240,.8);border-radius:var(--radius-xl);box-shadow:var(--shadow-card);width:100%;max-width:28rem;padding:2.25rem}
.auth-header{display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem}
.brand-icon{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:10px;background:#0f172a;color:#fff}
.brand-title{font-size:1.05rem;font-weight:700;line-height:1.2}
.brand-sub{font-size:.75rem;color:var(--text-secondary);font-weight:600;text-transform:uppercase}
h1{font-size:1.5rem;font-weight:700;margin:0 0 .4rem}
.err{color:var(--color-danger);background:#fef2f2;border:1px solid #fecaca;padding:.65rem .85rem;border-radius:var(--radius-md);font-size:.85rem;margin-bottom:1.25rem}
.ok{color:var(--color-success);background:#ecfdf5;border:1px solid #a7f3d0;padding:.65rem .85rem;border-radius:var(--radius-md);font-size:.85rem;margin-bottom:1.25rem}
.form-group{margin-bottom:1.25rem}
.form-label{display:block;font-size:.88rem;font-weight:600;margin-bottom:.5rem;color:var(--text-primary)}
.input-box{position:relative;display:flex;align-items:center}
.input-box svg{position:absolute;left:.85rem;color:var(--text-secondary);pointer-events:none}
.input-box input{font:inherit;font-size:.92rem;width:100%;padding:.75rem .9rem .75rem 2.5rem;background:var(--bg-input);border:1px solid transparent;border-radius:var(--radius-md);color:var(--text-primary)}
.input-box input:focus{outline:none;background:#fff;border-color:var(--border-focus);box-shadow:0 0 0 3px rgba(37,99,235,.15)}
.btn-submit{display:block;width:100%;font:inherit;font-size:1rem;font-weight:600;padding:.8rem;border:none;border-radius:var(--radius-md);background:var(--color-primary);color:#fff;cursor:pointer;margin-top:1.5rem}
.btn-submit:hover{background:var(--color-primary-hover)}
.auth-nav{margin-top:1.25rem;text-align:center;font-size:.9rem}
a{color:#2563eb;text-decoration:none;font-weight:500}a:hover{text-decoration:underline}
</style></head><body>
<main class="auth-card">
<div class="auth-header">
  <div class="brand-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
  <div><div class="brand-title">账户凭据</div><div class="brand-sub">UPDATE PASSWORD</div></div>
</div>
<h1>修改密码</h1>
{{if .Error}}<p class="err">{{.Error}}</p>{{end}}
{{if .Done}}<p class="ok">密码已更新，其他设备上的登录已撤销。</p>{{end}}
<form method="post" action="/auth/password">
<input type="hidden" name="csrf" value="{{.CSRF}}">
<div class="form-group">
  <label class="form-label" for="current">当前密码</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
    <input id="current" type="password" name="current" autocomplete="current-password" required maxlength="256" placeholder="输入当前密码">
  </div>
</div>
<div class="form-group">
  <label class="form-label" for="new-password">新密码（4–256 字节）</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m10 15 5-3-5-3v6Z"/></svg>
    <input id="new-password" type="password" name="password" autocomplete="new-password" required minlength="1" data-password-bytes="4" maxlength="256" placeholder="输入至少4字节新密码">
  </div>
</div>
<div class="form-group">
  <label class="form-label" for="confirm-password">再次输入新密码</label>
  <div class="input-box">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
    <input id="confirm-password" type="password" name="confirm" autocomplete="new-password" required minlength="1" data-password-bytes="4" maxlength="256" placeholder="再次确认新密码">
  </div>
</div>
<button type="submit" class="btn-submit">更新密码</button>
</form>
<p class="auth-nav"><a href="/">返回首页</a></p>
</main></body></html>`))

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
			if r.Header.Get("Accept") == "application/json" {
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.WriteHeader(http.StatusUnauthorized)
				_ = json.NewEncoder(w).Encode(map[string]any{"done": false, "message": "密码不正确"})
				return
			}
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
		if r.Header.Get("Accept") == "application/json" {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			_ = json.NewEncoder(w).Encode(map[string]any{"done": true})
			return
		}
		http.Redirect(w, r, next, http.StatusSeeOther)
		return
	}
	render := func(status int, message string, done bool) {
		if r.Header.Get("Accept") == "application/json" {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(status)
			_ = json.NewEncoder(w).Encode(struct {
				Message string `json:"message"`
				Done    bool   `json:"done"`
			}{message, done})
			return
		}
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
	if len(replacement) < MinPasswordBytes || len(replacement) > MaxPasswordBytes {
		render(http.StatusBadRequest, "新密码须为 4–256 字节", false)
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
