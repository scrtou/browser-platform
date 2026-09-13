package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"html/template"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type profileService interface {
	Ensure(context.Context, string) (sealskin.Session, error)
	BootstrapTarget(string, string) (string, error)
}

type Server struct {
	profiles       profileService
	listSessions   func(context.Context) ([]sealskin.Session, error)
	sessionBaseURL string
	publicOrigin   *url.URL
	logger         *slog.Logger
	handler        http.Handler
}

func New(profiles profileService, listSessions func(context.Context) ([]sealskin.Session, error), publicBaseURL, sessionBaseURL string, logger *slog.Logger) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	publicOrigin, _ := url.Parse(publicBaseURL)
	server := &Server{profiles: profiles, listSessions: listSessions, publicOrigin: publicOrigin, sessionBaseURL: sessionBaseURL, logger: logger}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", server.health)
	mux.HandleFunc("GET /readyz", server.ready)
	mux.HandleFunc("GET /browser/{profile}/", server.entry)
	mux.HandleFunc("POST /browser/{profile}/start", server.start)
	mux.HandleFunc("GET /bootstrap/{profile}/{operation}", server.bootstrap)
	server.handler = securityHeaders(mux)
	return server
}

func (s *Server) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	s.handler.ServeHTTP(writer, request)
}

func (s *Server) health(writer http.ResponseWriter, _ *http.Request) {
	noStore(writer)
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte("{\"status\":\"ok\"}\n"))
}

func (s *Server) ready(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	ctx, cancel := context.WithTimeout(request.Context(), 5*time.Second)
	defer cancel()
	if _, err := s.listSessions(ctx); err != nil {
		http.Error(writer, "SealSkin is unavailable", http.StatusServiceUnavailable)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_, _ = writer.Write([]byte("{\"status\":\"ready\"}\n"))
}

func (s *Server) entry(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	// Chromium uses Origin: null for a form POST from a no-referrer page.
	// Keep the origin on this same-origin POST; start still suppresses the
	// referrer on the token-bearing redirect to SealSkin.
	writer.Header().Set("Referrer-Policy", "same-origin")
	nonceBytes := make([]byte, 18)
	if _, err := rand.Read(nonceBytes); err != nil {
		http.Error(writer, "Could not prepare browser entry", http.StatusInternalServerError)
		return
	}
	nonce := base64.RawStdEncoding.EncodeToString(nonceBytes)
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	// Chromium also applies form-action to the POST's redirect target.
	// sessionBaseURL is the configured, validated HTTPS Session origin.
	writer.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'nonce-"+nonce+"'; style-src 'unsafe-inline'; form-action 'self' "+s.sessionBaseURL+"; base-uri 'none'")
	data := struct {
		Profile string
		Nonce   string
	}{Profile: request.PathValue("profile"), Nonce: nonce}
	if err := entryTemplate.Execute(writer, data); err != nil {
		s.logger.Error("render browser entry", "error", err)
	}
}

func (s *Server) start(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if !sameOrigin(request, s.publicOrigin) {
		http.Error(writer, "Cross-origin start request rejected", http.StatusForbidden)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 1024)
	if err := request.ParseForm(); err != nil {
		http.Error(writer, "Invalid request", http.StatusBadRequest)
		return
	}
	profileID := request.PathValue("profile")
	session, err := s.profiles.Ensure(request.Context(), profileID)
	if err != nil {
		s.writeProfileError(writer, profileID, err)
		return
	}
	target, err := sealskin.ResolveSessionURL(s.sessionBaseURL, session.SessionURL, true)
	if err != nil {
		s.logger.Error("reject SealSkin session URL", "profile", profileID, "error", err)
		http.Error(writer, "SealSkin returned an invalid session address", http.StatusBadGateway)
		return
	}
	writer.Header().Set("Referrer-Policy", "no-referrer")
	http.Redirect(writer, request, target, http.StatusSeeOther)
}

func sameOrigin(request *http.Request, expected *url.URL) bool {
	origin := strings.TrimSpace(request.Header.Get("Origin"))
	if origin == "" {
		return true
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return false
	}
	if expected == nil || expected.Scheme == "" || expected.Host == "" {
		return false
	}
	return strings.EqualFold(parsed.Scheme, expected.Scheme) && strings.EqualFold(parsed.Host, expected.Host)
}

func (s *Server) bootstrap(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	target, err := s.profiles.BootstrapTarget(request.PathValue("profile"), request.PathValue("operation"))
	if err != nil {
		http.NotFound(writer, request)
		return
	}
	writer.Header().Set("Referrer-Policy", "no-referrer")
	http.Redirect(writer, request, target, http.StatusSeeOther)
}

func (s *Server) writeProfileError(writer http.ResponseWriter, profileID string, err error) {
	status := http.StatusBadGateway
	message := "Could not start the browser profile"
	switch {
	case errors.Is(err, profile.ErrProfileNotFound):
		status, message = http.StatusNotFound, "Browser profile not found"
	case errors.Is(err, profile.ErrOperationRunning):
		status, message = http.StatusConflict, "Browser profile is still starting; retry shortly"
	case errors.Is(err, profile.ErrOwnershipUnknown):
		status, message = http.StatusConflict, "Browser profile requires operator recovery"
	}
	s.logger.Error("profile entry failed", "profile", profileID, "status", status, "error", err)
	http.Error(writer, message, status)
}

func noStore(writer http.ResponseWriter) {
	writer.Header().Set("Cache-Control", "no-store")
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("X-Content-Type-Options", "nosniff")
		writer.Header().Set("Referrer-Policy", "no-referrer")
		writer.Header().Set("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
		next.ServeHTTP(writer, request)
	})
}

var entryTemplate = template.Must(template.New("entry").Parse(strings.TrimSpace(`
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>启动浏览器</title>
  <style>
    body { font: 16px system-ui, sans-serif; margin: 2rem; color: #202124; }
    button { padding: .65rem 1rem; font: inherit; }
  </style>
</head>
<body>
  <p>正在启动 {{.Profile}}…</p>
  <form method="post" action="start"><button type="submit">继续</button></form>
  <script nonce="{{.Nonce}}">document.forms[0].submit()</script>
</body>
</html>
`)))
