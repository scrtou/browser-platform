package access

import (
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
	"context"
	"encoding/json"
	"encoding/pem"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type scalingQAOrchestrator struct{}

func (scalingQAOrchestrator) ListSessions(context.Context) ([]sealskin.Session, error) {
	return nil, errors.New("QA has no lifecycle access")
}
func (scalingQAOrchestrator) LaunchURL(context.Context, sealskin.LaunchURLRequest, string) (sealskin.LaunchResponse, error) {
	return sealskin.LaunchResponse{}, errors.New("QA has no lifecycle access")
}
func (scalingQAOrchestrator) ListHomeDirectories(context.Context) ([]string, error) {
	return nil, errors.New("QA has no Home access")
}
func (scalingQAOrchestrator) CreateHomeDirectory(context.Context, string, string) error {
	return errors.New("QA has no Home access")
}

// Opt-in real Worker fixture. The runner supplies an isolated internal network
// and private synthetic credentials; this test never opens production state.
func TestUIScalingBrowserFixture(t *testing.T) {
	root := os.Getenv("BP_DISPLAY_FIXTURE")
	if root == "" {
		t.Skip("isolated real Worker fixture")
	}
	root, err := filepath.Abs(root)
	if err != nil || !strings.Contains(root, "/runtime/r6ar-display-persistence-") {
		t.Fatal("task-private fixture path required")
	}
	var cfg struct{ Worker, Listen, User, Password, Mode string }
	raw, err := os.ReadFile(filepath.Join(root, "fixture.json"))
	if err != nil {
		t.Fatal(err)
	}
	if json.Unmarshal(raw, &cfg) != nil {
		t.Fatal("invalid fixture config")
	}
	worker, err := url.Parse(cfg.Worker)
	if err != nil || worker.Scheme != "http" || net.ParseIP(worker.Hostname()) == nil {
		t.Fatal("QA Worker IP required")
	}
	host, _, err := net.SplitHostPort(cfg.Listen)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsPrivate() {
		t.Fatal("private QA listener required")
	}
	f := newFixture(t)
	st, err := state.NewStore(filepath.Join(root, "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	def := profile.Definition{ID: "personal", ApplicationID: "qa", HomeName: "qa", StartURL: "https://example.com", WaylandMode: true}
	if cfg.Mode != "legacy" {
		def.BrowserTemplateID = "qa-native"
		def.BrowserTemplateRevision = 1
		def.EnvironmentArtifactID = "qa-env"
		def.EnvironmentArtifactSHA256 = strings.Repeat("a", 64)
		def.EnvironmentSource = "frozen"
		def.EnvironmentTemplateRevision = 1
		def.DisplayTemplateID = "qa-auto"
		def.DisplayTemplateRevision = 1
		def.ResolutionMode = "auto"
	}
	catalog := profile.TemplateCatalogData{Version: 1, DisplayTemplates: []profile.DisplayTemplate{{ID: "qa-auto", Revision: 1, Status: "accepted", Label: "QA Auto", DisplayServer: "x11", Transport: "selkies", Screen: "auto@system", Scaling: "auto"}}}
	svc, err := profile.NewService(scalingQAOrchestrator{}, st, "https://entry.test", []profile.Definition{def}, profile.WithDirectory(filepath.Join(root, "profiles.json")), profile.WithTemplateCatalog(profile.StaticTemplateCatalog(catalog)))
	if err != nil {
		t.Fatal(err)
	}
	if _, _, ok := svc.UIScalingPreference("personal"); !ok {
		t.Fatal("QA Profile does not support system DPI")
	}
	f.g.uiScaling = svc.UIScalingPreference
	f.g.updateUIScaling = func(id string, revision, percent int, actor string) (int, error) {
		rec, e := svc.UpdateBrowser(id, revision, actor, profile.BrowserPatch{UIScalingPercent: &percent})
		if errors.Is(e, profile.ErrRevisionMismatch) {
			e = ErrDisplayRevisionConflict
		}
		return rec.Revision, e
	}
	_, csrf, cookie := f.display(t, "alice", "personal")
	proxy := httputil.NewSingleHostReverseProxy(worker)
	original := proxy.Director
	proxy.Director = func(r *http.Request) {
		original(r)
		r.Header.Del(backendAuthHeader)
		r.SetBasicAuth(cfg.User, cfg.Password)
	}
	backend := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get(backendAuthHeader) != "synthetic-backend-access-token" {
			http.Error(w, "unauthorized", 401)
			return
		}
		proxy.ServeHTTP(w, r)
	}))
	defer backend.Close()
	ca := filepath.Join(root, "upstream-ca.pem")
	if os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: backend.Certificate().Raw}), 0600) != nil {
		t.Fatal("write CA")
	}
	f.g.cfg.SessionUpstreamURL = backend.URL
	f.g.cfg.SessionCAFile = ca
	front := httptest.NewUnstartedServer(f.handler)
	listener, err := net.Listen("tcp", cfg.Listen)
	if err != nil {
		t.Fatal(err)
	}
	front.Listener.Close()
	front.Listener = listener
	f.g.session, _ = url.Parse("https://" + cfg.Listen)
	if err := f.g.prepareProxy(); err != nil {
		t.Fatal(err)
	}
	front.StartTLS()
	defer front.Close()
	ready, _ := json.Marshal(map[string]any{"url": front.URL + "/" + personalSession + "/", "cookie": cookie, "csrf": csrf})
	if os.WriteFile(filepath.Join(root, "ready.json"), ready, 0600) != nil {
		t.Fatal("write readiness")
	}
	deadline := time.Now().Add(12 * time.Minute)
	for time.Now().Before(deadline) {
		if _, e := os.Stat(filepath.Join(root, "stop")); e == nil {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("fixture deadline")
}
