package access

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

var uuidPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var backendTokenPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,512}$`)

const backendAuthHeader = "X-Browser-Platform-Session-Access"

func validSessionID(value string) bool { return uuidPattern.MatchString(value) }

func sessionPath(r *http.Request) (string, bool) {
	parts := strings.Split(r.URL.EscapedPath(), "/")
	if len(parts) < 3 || !validSessionID(parts[1]) || strings.Contains(r.URL.Path, "\\") {
		return "", false
	}
	for _, part := range strings.Split(r.URL.Path, "/") {
		if part == "." || part == ".." {
			return "", false
		}
	}
	return parts[1], true
}

// SessionTransport is shared by the private control client and display proxy.
// It never consults environment proxies and always verifies the configured CA.
func SessionTransport(cfg Config) (*http.Transport, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	ca, err := os.ReadFile(cfg.SessionCAFile)
	if err != nil {
		return nil, errors.New("Session CA unavailable")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return nil, errors.New("Session CA invalid")
	}
	return &http.Transport{
		Proxy: nil, DialContext: (&net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		TLSClientConfig:     &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots, ServerName: cfg.SessionTLSName},
		TLSHandshakeTimeout: 10 * time.Second, ResponseHeaderTimeout: 30 * time.Second,
		MaxIdleConns: 32, MaxIdleConnsPerHost: 16, IdleConnTimeout: time.Minute, MaxResponseHeaderBytes: 65536,
	}, nil
}

func (g *Gateway) prepareProxy() error {
	transport, err := SessionTransport(g.cfg)
	if err != nil {
		return err
	}
	upstream, _ := url.Parse(g.cfg.SessionUpstreamURL)
	g.proxy = &httputil.ReverseProxy{
		Transport: transport,
		// ReverseProxy can log an upstream parse/upgrade failure containing
		// arbitrary bytes. The public error hook below emits a stable event.
		ErrorLog: log.New(io.Discard, "", 0),
		Rewrite: func(proxy *httputil.ProxyRequest) {
			proxy.SetURL(upstream)
			proxy.Out.Host = g.session.Host
			for key := range proxy.Out.Header {
				name := strings.ToLower(key)
				if name == "authorization" || name == "proxy-authorization" || name == "forwarded" ||
					strings.HasPrefix(name, "x-forwarded-") || strings.HasPrefix(name, "x-upstream-") ||
					strings.HasPrefix(name, "x-browser-platform-") ||
					strings.HasPrefix(name, "x-auth-") || strings.HasPrefix(name, "x-original-") || name == "remote-user" {
					proxy.Out.Header.Del(key)
				}
			}
			proxy.Out.Header.Set("X-Forwarded-Proto", "https")
			proxy.Out.Header.Set("X-Forwarded-Host", g.session.Host)
			proxy.Out.Header.Del("Cookie")
			identity := proxy.In.Context().Value(contextKey{}).(requestLogin)
			proxy.Out.Header.Set(backendAuthHeader, identity.Data.BackendToken)
		},
		ModifyResponse: func(response *http.Response) error {
			id, ok := sessionPath(response.Request)
			if !ok {
				return errors.New("invalid proxied Session path")
			}
			if location := response.Header.Get("Location"); location != "" {
				relative, err := url.Parse(location)
				if err != nil || relative.User != nil || relative.Fragment != "" || relative.Opaque != "" || relative.ForceQuery {
					return errors.New("invalid Session redirect")
				}
				base := *g.session
				base.Path = response.Request.URL.Path
				resolved := base.ResolveReference(relative)
				resolvedID, valid := sessionPath(&http.Request{URL: resolved})
				if !valid || resolvedID != id || resolved.Scheme != "https" || resolved.Host != g.session.Host {
					return errors.New("Session redirect escaped its binding")
				}
				query, err := url.ParseQuery(resolved.RawQuery)
				if err != nil || query.Has("access_token") || query.Has("token") ||
					strings.Contains(resolved.String(), response.Request.Header.Get(backendAuthHeader)) {
					return errors.New("Session redirect contains a private capability")
				}
				response.Header.Set("Location", resolved.String())
			}
			response.Header.Del("Set-Cookie")
			for key := range response.Header {
				lower := strings.ToLower(key)
				if strings.HasPrefix(lower, "access-control-") || strings.HasPrefix(lower, "x-upstream-") || strings.HasPrefix(lower, "x-browser-platform-") {
					response.Header.Del(key)
				}
			}
			response.Header.Set("Cache-Control", "no-store")
			response.Header.Set("Referrer-Policy", "no-referrer")
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			g.logger.Warn("Session proxy unavailable", "event", "DISPLAY_UPSTREAM_UNAVAILABLE")
			unavailable(w, http.StatusBadGateway)
		},
	}
	return nil
}

func (g *Gateway) serveSession(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/auth/accept" && r.URL.RawPath == "" {
		g.accept(w, r)
		return
	}
	id, ok := sessionPath(r)
	if !ok {
		http.NotFound(w, r)
		return
	}
	query, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil || query.Has("access_token") || query.Has("token") || query.Has("ticket") {
		unavailable(w, http.StatusForbidden)
		return
	}
	if values := r.Header.Values("Origin"); len(values) > 0 {
		if !SameOrigin(r, g.session) && !SameOrigin(r, g.entry) {
			unavailable(w, http.StatusForbidden)
			return
		}
	} else if (r.Method != http.MethodGet && r.Method != http.MethodHead) || strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		unavailable(w, http.StatusForbidden)
		return
	}
	identity, ok := g.authenticated(r, displayCookie+id, "display")
	if !ok || identity.Data.Session != id || !g.allowed(identity.Data.Actor, identity.Data.Profile) {
		unavailable(w, http.StatusUnauthorized)
		return
	}
	if g.checkBinding(r.Context(), identity.Data.Profile, id) != nil {
		unavailable(w, http.StatusConflict)
		return
	}
	ctx, cancel := context.WithDeadline(r.Context(), identity.Data.Expires)
	ctx = context.WithValue(ctx, contextKey{}, identity)
	defer cancel()
	g.mu.Lock()
	if _, ok := g.validLocked(identity.Hash, "display"); !ok {
		g.mu.Unlock()
		unavailable(w, http.StatusUnauthorized)
		return
	}
	if len(g.active) >= 1024 {
		g.mu.Unlock()
		unavailable(w, http.StatusServiceUnavailable)
		return
	}
	g.sequence++
	key := g.sequence
	g.active[key] = activeRequest{Hash: identity.Hash, Cancel: cancel}
	g.mu.Unlock()
	defer func() {
		g.mu.Lock()
		delete(g.active, key)
		g.mu.Unlock()
	}()
	g.proxy.ServeHTTP(w, r.WithContext(ctx))
}
