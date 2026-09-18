package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"html/template"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/safelog"
	"browser-platform/adapter/internal/sealskin"
)

type profileService interface {
	Ensure(context.Context, string) (sealskin.Session, error)
	BootstrapTarget(string, string) (string, error)
	Health(context.Context, string, profile.HealthOptions) (profile.HealthReport, error)
	Environment(context.Context, string) (profile.EnvironmentSummary, error)
}

// HealthUI controls the entry page's read-only pre-check. EntryWait bounds how
// long the entry waits for a report before falling back to the plain auto-POST.
type HealthUI struct {
	EntryHint bool
	EntryWait time.Duration
}

type Server struct {
	profiles       profileService
	listSessions   func(context.Context) ([]sealskin.Session, error)
	sessionBaseURL string
	publicOrigin   *url.URL
	logger         *slog.Logger
	handler        http.Handler
	healthUI       HealthUI
	access         *access.Gateway
}

type Option func(*Server)

func WithAccess(gateway *access.Gateway) Option { return func(s *Server) { s.access = gateway } }

func New(profiles profileService, listSessions func(context.Context) ([]sealskin.Session, error), publicBaseURL, sessionBaseURL string, logger *slog.Logger, healthUI HealthUI, options ...Option) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	logger = safelog.Logger(logger)
	publicOrigin, _ := url.Parse(publicBaseURL)
	server := &Server{profiles: profiles, listSessions: listSessions, publicOrigin: publicOrigin, sessionBaseURL: sessionBaseURL, logger: logger, healthUI: healthUI}
	for _, option := range options {
		option(server)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", server.health)
	mux.HandleFunc("GET /readyz", server.ready)
	mux.HandleFunc("GET /browser/{profile}/", server.entry)
	mux.HandleFunc("GET /browser/{profile}/health", server.profileHealth)
	mux.HandleFunc("POST /browser/{profile}/start", server.start)
	mux.HandleFunc("GET /bootstrap/{profile}/{operation}", server.bootstrap)
	// Management pages exist only behind the access gateway, which attaches
	// the login's grants; without them both handlers answer 404.
	mux.HandleFunc("GET /manage/{$}", server.managePage)
	mux.HandleFunc("GET /manage/environments", server.manageEnvironments)
	mux.HandleFunc("POST /manage/browsers/{profile}", server.manageBrowser)
	mux.HandleFunc("POST /manage/accounts", server.manageAccounts)
	mux.HandleFunc("POST /manage/accounts/{account}", server.manageAccount)
	server.handler = securityHeaders(mux)
	if server.access != nil {
		server.handler = server.access.Wrap(server.handler)
	}
	return server
}

// profileHealth serves the sanitized report. It is read-only: a stale or
// missing report remains unavailable until an internal probe or sampler runs.
func (s *Server) profileHealth(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	profileID := request.PathValue("profile")
	options := profile.HealthOptions{CachedOnly: true}
	ctx, cancel := context.WithTimeout(request.Context(), 30*time.Second)
	defer cancel()
	report, err := s.profiles.Health(ctx, profileID, options)
	if err != nil {
		status, message := http.StatusServiceUnavailable, "Health report is not available"
		switch {
		case errors.Is(err, profile.ErrProfileNotFound):
			status, message = http.StatusNotFound, "Browser profile not found"
		case errors.Is(err, profile.ErrLifecycleDisabled):
			status, message = http.StatusNotImplemented, "Health reports require the verified lifecycle"
		case errors.Is(err, profile.ErrHealthUnavailable):
			status, message = http.StatusNotFound, "No health report has been collected yet"
		case errors.Is(err, profile.ErrHealthPending):
			writer.Header().Set("Retry-After", "5")
			message = "Health collection is still running; retry shortly"
		}
		s.logger.Warn("profile health unavailable", "profile", profileID, "status", status, "error", err)
		http.Error(writer, message, status)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(report.Public())
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
	if s.healthUI.EntryHint {
		if report, ok := s.blockingRecovery(request); ok {
			s.renderRecovery(writer, request.PathValue("profile"), report, access.CSRF(request))
			return
		}
	}
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
		CSRF    string
	}{Profile: request.PathValue("profile"), Nonce: nonce, CSRF: access.CSRF(request)}
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
	if s.access != nil {
		target, err = s.access.Grant(request, profileID, session.SessionID, target)
		if err != nil {
			s.logger.Warn("display authorization unavailable", "profile", profileID, "code", "DISPLAY_GRANT_UNAVAILABLE")
			http.Error(writer, "Session authorization unavailable", http.StatusServiceUnavailable)
			return
		}
	}
	writer.Header().Set("Referrer-Policy", "no-referrer")
	http.Redirect(writer, request, target, http.StatusSeeOther)
}

// blockingRecovery runs the read-only pre-check with a bounded wait. Any
// error, timeout or non-blocking result keeps the original auto-POST entry.
func (s *Server) blockingRecovery(request *http.Request) (profile.HealthReport, bool) {
	profileID := request.PathValue("profile")
	options := profile.HealthOptions{CachedOnly: true}
	ctx, cancel := context.WithTimeout(request.Context(), s.healthUI.EntryWait+time.Second)
	defer cancel()
	report, err := s.profiles.Health(ctx, profileID, options)
	if err != nil && !errors.Is(err, profile.ErrHealthThrottled) {
		if !errors.Is(err, profile.ErrProfileNotFound) && !errors.Is(err, profile.ErrLifecycleDisabled) {
			s.logger.Info("entry pre-check skipped", "profile", profileID, "error", err)
		}
		return profile.HealthReport{}, false
	}
	if report.Recovery == nil || !report.Recovery.Blocking {
		return profile.HealthReport{}, false
	}
	return report, true
}

func (s *Server) renderRecovery(writer http.ResponseWriter, profileID string, report profile.HealthReport, csrf string) {
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	writer.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' "+s.sessionBaseURL+"; base-uri 'none'")
	data := struct {
		Profile   string
		Overall   string
		Code      string
		Title     string
		Steps     []string
		CheckedAt string
		Checks    []profile.HealthCheck
		CSRF      string
	}{Profile: profileID, Overall: string(report.Overall), Code: report.Recovery.Code, Title: report.Recovery.Title,
		Steps: report.Recovery.Steps, CheckedAt: report.CheckedAt.UTC().Format(time.RFC3339), Checks: report.Checks, CSRF: csrf}
	if err := recoveryTemplate.Execute(writer, data); err != nil {
		s.logger.Error("render recovery hint", "error", err)
	}
}

func sameOrigin(request *http.Request, expected *url.URL) bool {
	origin := strings.TrimSpace(request.Header.Get("Origin"))
	if origin == "" {
		return true
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil || parsed.Path != "" || parsed.RawQuery != "" || parsed.ForceQuery || parsed.Fragment != "" {
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
	case errors.Is(err, profile.ErrResumeFailed):
		status, message = http.StatusConflict, "Browser profile could not be resumed after a restart; retry later or ask the operator to resume or stop it"
	case errors.Is(err, profile.ErrCoherenceBlocked):
		status, message = http.StatusServiceUnavailable, "当前会话尚未通过环境与网络一致性检查。请查看健康报告，等待采样或由运维重查；Home 数据和运行占用已保留。"
		writer.Header().Set("Retry-After", "10")
	case errors.Is(err, profile.ErrCapacity):
		status, message = http.StatusServiceUnavailable, "Capacity limit reached; no browser was started. Retry later or ask the operator"
		writer.Header().Set("Retry-After", "30")
	case errors.Is(err, profile.ErrRuntimeUnsupported):
		status, message = http.StatusServiceUnavailable, "浏览器暂时不可用，需完成维护后再试。"
	case errors.Is(err, profile.ErrProfileDisabled):
		status, message = http.StatusServiceUnavailable, "该浏览器已由管理员停用，暂不能启动或进入。"
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

var recoveryTemplate = template.Must(template.New("recovery").Parse(strings.TrimSpace(`
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{.Profile}}：{{.Title}}</title>
  <style>
    body { font: 16px system-ui, sans-serif; margin: 2rem; color: #202124; max-width: 44rem; }
    h1 { font-size: 1.25rem; }
    ol li { margin: .4rem 0; }
    button { padding: .65rem 1rem; font: inherit; }
    table { border-collapse: collapse; margin-top: 1.5rem; font-size: .9rem; }
    td, th { text-align: left; padding: .2rem .6rem; border-bottom: 1px solid #ddd; }
    .meta { color: #5f6368; font-size: .9rem; }
  </style>
</head>
<body>
  <h1>{{.Profile}}：{{.Title}}</h1>
  <p class="meta">状态 {{.Overall}} · {{.Code}} · 检查时间 {{.CheckedAt}}</p>
  <ol>{{range .Steps}}<li>{{.}}</li>{{end}}</ol>
  <form method="post" action="start">{{if .CSRF}}<input type="hidden" name="csrf" value="{{.CSRF}}">{{end}}<button type="submit">继续进入会话</button></form>
  <p class="meta"><a href="./?recheck=1">重新检查</a> · <a href="health">健康报告 (JSON)</a></p>
  <table>
    <tr><th>检查</th><th>结果</th><th>代码</th><th>说明</th></tr>
    {{range .Checks}}<tr><td>{{.Name}}</td><td>{{.Status}}</td><td>{{.Code}}</td><td>{{.Message}}</td></tr>{{end}}
  </table>
</body>
</html>
`)))

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
  <form method="post" action="start">{{if .CSRF}}<input type="hidden" name="csrf" value="{{.CSRF}}">{{end}}<button type="submit">继续</button></form>
  <script nonce="{{.Nonce}}">document.forms[0].submit()</script>
</body>
</html>
`)))
