package profile

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/state"
)

func r7dArtifact() EnvironmentArtifact {
	return EnvironmentArtifact{
		ID: "env-r7d", SHA256: strings.Repeat("a", 64), AcceptanceSHA256: strings.Repeat("b", 64),
		Image: "sha256:" + strings.Repeat("c", 64), Source: "frozen", Status: "accepted",
		Application:      map[string]any{"provider_config": map[string]any{"image": "sha256:" + strings.Repeat("c", 64)}},
		TemplateRevision: 1, BrowserTemplateID: "camoufox-linux", BrowserEngine: "camoufox", BrowserVersion: "135.0",
		OSFamily: "linux", Platform: "Linux x86_64", UserAgent: "Mozilla/5.0 Firefox/135.0",
		Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "America/New_York", Screen: "1920x1080@1",
	}
}

func r7dArtifact1280() EnvironmentArtifact {
	artifact := r7dArtifact()
	artifact.ID = "env-r7d-1280"
	artifact.SHA256 = strings.Repeat("d", 64)
	artifact.Image = "sha256:" + strings.Repeat("e", 64)
	artifact.Application = map[string]any{"provider_config": map[string]any{"image": artifact.Image}}
	artifact.TemplateRevision = 2
	artifact.Screen = "1280x800@1"
	return artifact
}

func r7dCatalog() StaticTemplateCatalog {
	return StaticTemplateCatalog{
		Version: 1,
		BrowserTemplates: []BrowserTemplate{{
			ID: "camoufox-linux", Revision: 1, Status: "accepted", Label: "Camoufox", Engine: "camoufox",
			Version: "135.0", OSFamily: "linux", Platform: "Linux x86_64", UserAgentProduct: "Firefox", AllowNewBrowsers: true,
		}},
		DisplayTemplates: []DisplayTemplate{{
			ID: "fixed-1920", Revision: 1, Status: "accepted", Label: "固定指纹 1920×1080",
			DisplayServer: "x11", Transport: "selkies", Screen: "1920x1080@1", Scaling: "fixed",
		}, {
			ID: "fixed-1280", Revision: 1, Status: "accepted", Label: "固定指纹 1280×800",
			DisplayServer: "x11", Transport: "selkies", Screen: "1280x800@1", Scaling: "fixed",
		}},
		Compatibility: []TemplateCompatibility{{
			BrowserTemplateID: "camoufox-linux", EnvironmentArtifactID: "env-r7d",
			DisplayTemplateID: "fixed-1920", Status: "accepted",
		}, {
			BrowserTemplateID: "camoufox-linux", EnvironmentArtifactID: "env-r7d-1280",
			DisplayTemplateID: "fixed-1280", Status: "accepted",
		}},
	}
}

func templateService(t *testing.T, artifact EnvironmentArtifact) *Service {
	t.Helper()
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	catalog := TemplateCatalogData(r7dCatalog())
	catalog.DisplayTemplates = catalog.DisplayTemplates[:1]
	catalog.Compatibility = catalog.Compatibility[:1]
	service, err := NewService(
		&lifecycleFake{snapshot: emptyRuntime()}, store, "https://adapter.example",
		[]Definition{{ID: "personal", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com"}},
		WithEnvironmentCatalog(StaticEnvironmentCatalog{"env-r7d": artifact}), WithTemplateCatalog(StaticTemplateCatalog(catalog)),
	)
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func TestCompatibleTemplatesRequireExplicitCoherentAcceptedCombination(t *testing.T) {
	service := templateService(t, r7dArtifact())
	items, err := service.CompatibleTemplates(context.Background())
	if err != nil || len(items) != 1 {
		t.Fatalf("items=%+v err=%v", items, err)
	}
	item := items[0]
	if item.Engine != "camoufox" || item.DisplayServer != "x11" || item.Transport != "selkies" ||
		item.Screen != "1920x1080@1" || !item.AllowNewBrowsers || item.EnvironmentRevision != 1 {
		t.Fatalf("unexpected summary: %+v", item)
	}
}

func TestCompatibleTemplatesFailClosedOnLegacyOrMismatchedArtifact(t *testing.T) {
	for name, mutate := range map[string]func(*EnvironmentArtifact){
		"legacy metadata missing": func(a *EnvironmentArtifact) { a.BrowserTemplateID = "" },
		"engine mismatch":         func(a *EnvironmentArtifact) { a.BrowserEngine = "firefox_legacy" },
		"user agent mismatch":     func(a *EnvironmentArtifact) { a.UserAgent = "Chromium/140" },
		"locale mismatch":         func(a *EnvironmentArtifact) { a.Languages = []string{"fr-FR", "en-US"} },
		"screen mismatch":         func(a *EnvironmentArtifact) { a.Screen = "1280x800@1" },
	} {
		t.Run(name, func(t *testing.T) {
			artifact := r7dArtifact()
			mutate(&artifact)
			if _, err := templateService(t, artifact).CompatibleTemplates(context.Background()); !errors.Is(err, ErrTemplateCatalogUnavailable) {
				t.Fatalf("err=%v", err)
			}
		})
	}
}

func TestTemplateCatalogRejectsUnacceptedAndArbitraryCombinations(t *testing.T) {
	data := TemplateCatalogData(r7dCatalog())
	data.Compatibility[0].Status = "draft"
	if err := validateTemplateCatalog(data); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("draft combination accepted: %v", err)
	}
	data = TemplateCatalogData(r7dCatalog())
	data.Compatibility[0].DisplayTemplateID = "unknown"
	if err := validateTemplateCatalog(data); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("unknown display accepted: %v", err)
	}
	data = TemplateCatalogData(r7dCatalog())
	data.BrowserTemplates[0].Engine = "firefox_legacy"
	if err := validateTemplateCatalog(data); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("legacy Firefox was allowed for new browsers: %v", err)
	}
}

func TestFileTemplateCatalogRequiresPrivateStrictFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "templates.json")
	content := `{"version":1,"browser_templates":[{"id":"camoufox-linux","revision":1,"status":"accepted","label":"Camoufox","engine":"camoufox","version":"135.0","os_family":"linux","platform":"Linux x86_64","user_agent_product":"Firefox","allow_new_browsers":true}],"display_templates":[{"id":"fixed-1920","revision":1,"status":"accepted","label":"Fixed","display_server":"x11","transport":"selkies","screen":"1920x1080@1","scaling":"fixed"}],"compatibility":[{"browser_template_id":"camoufox-linux","environment_artifact_id":"env-r7d","display_template_id":"fixed-1920","status":"accepted"}]}`
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	catalog, err := NewFileTemplateCatalog(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := catalog.Read(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(path, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := catalog.Read(context.Background()); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("permissive file err=%v", err)
	}
	if err := os.Chmod(path, 0o600); err != nil {
		t.Fatal(err)
	}
	bad := strings.TrimSuffix(content, "}") + `,"unknown":true}`
	if err := os.WriteFile(path, []byte(bad), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := catalog.Read(context.Background()); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("unknown field err=%v", err)
	}
}

func templateMutationService(t *testing.T, admin *managementAdmin) (*Service, *lifecycleFake) {
	t.Helper()
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(t.TempDir(), "profiles.json")
	service, err := NewService(
		fake, store, "https://adapter.example",
		[]Definition{{ID: "browser", ApplicationID: "app-browser", HomeName: "browser-home", StartURL: "https://example.com"}},
		WithLifecycle(fake), WithDirectory(directory), WithAdminOrchestrator(admin),
		WithEnvironmentCatalog(StaticEnvironmentCatalog{"env-r7d": r7dArtifact(), "env-r7d-1280": r7dArtifact1280()}),
		WithTemplateCatalog(r7dCatalog()),
	)
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = "browser-home"
	return service, fake
}

func TestTemplateApplyRefusesRunningBrowserWithoutMutationOrImplicitStop(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := templateMutationService(t, admin)
	if _, err := service.Ensure(context.Background(), "browser"); err != nil {
		t.Fatal(err)
	}
	before, _ := service.directory.record("browser")
	stopCalls := fake.stopCalls
	if _, err := service.ApplyBrowserTemplate(context.Background(), "browser", before.Revision, "camoufox-linux", "env-r7d", "fixed-1920", "root", "template-running"); !errors.Is(err, ErrBrowserBusy) {
		t.Fatalf("running template apply: %v", err)
	}
	after, _ := service.directory.record("browser")
	if fake.stopCalls != stopCalls || admin.replaceCalls != 0 || after.Revision != before.Revision || after.Status != RecordReady {
		t.Fatalf("running apply had side effects: stops=%d replaces=%d before=%+v after=%+v", fake.stopCalls-stopCalls, admin.replaceCalls, before, after)
	}
}

func TestTemplateApplyCreatesRevisionAndRollbackRestoresExactAcceptedBinding(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := templateMutationService(t, admin)
	first, err := service.ApplyBrowserTemplate(context.Background(), "browser", 1, "camoufox-linux", "env-r7d", "fixed-1920", "root", "template-1")
	if err != nil {
		t.Fatal(err)
	}
	if first.Revision != 3 || first.Status != RecordReady || first.EnvironmentArtifactID != "env-r7d" ||
		first.BrowserTemplateID != "camoufox-linux" || first.DisplayTemplateID != "fixed-1920" || first.WaylandMode ||
		first.Language == nil || *first.Language != "en_US.UTF-8" || first.Timezone == nil || *first.Timezone != "America/New_York" {
		t.Fatalf("first binding: %+v", first)
	}
	if admin.replaceCalls != 1 || admin.lastReplace["id"] != first.ApplicationID {
		t.Fatalf("first app replacement: calls=%d app=%+v", admin.replaceCalls, admin.lastReplace)
	}
	second, err := service.ApplyBrowserTemplate(context.Background(), "browser", first.Revision, "camoufox-linux", "env-r7d-1280", "fixed-1280", "root", "template-2")
	if err != nil {
		t.Fatal(err)
	}
	if second.Revision != 5 || second.EnvironmentArtifactID != "env-r7d-1280" || second.DisplayTemplateID != "fixed-1280" || len(second.TemplateHistory) != 1 ||
		second.TemplateHistory[0].ProfileRevision != first.Revision || second.TemplateHistory[0].Binding.EnvironmentArtifactID != "env-r7d" {
		t.Fatalf("second binding/history: %+v", second)
	}
	fake.snapshot = emptyRuntime()
	fake.snapshot.HomeName = second.HomeName
	rolled, err := service.RollbackBrowserTemplate(context.Background(), "browser", second.Revision, first.Revision, "root", "template-rollback")
	if err != nil {
		t.Fatal(err)
	}
	if rolled.Revision != 7 || rolled.EnvironmentArtifactID != "env-r7d" || rolled.DisplayTemplateID != "fixed-1920" || len(rolled.TemplateHistory) != 2 {
		t.Fatalf("rollback: %+v", rolled)
	}
	if rolled.NetworkPolicyID != second.NetworkPolicyID || rolled.NetworkPolicySHA256 != second.NetworkPolicySHA256 || admin.replaceCalls != 3 {
		t.Fatalf("rollback changed network or skipped PUT: %+v replaces=%d", rolled, admin.replaceCalls)
	}
}

func TestTemplateApplyFailurePersistsLaunchBlockingPendingStateAndRetryCompletes(t *testing.T) {
	admin := &managementAdmin{patchErr: errors.New("controller unavailable")}
	service, _ := templateMutationService(t, admin)
	if _, err := service.ApplyBrowserTemplate(context.Background(), "browser", 1, "camoufox-linux", "env-r7d", "fixed-1920", "root", "template-retry"); err == nil {
		t.Fatal("failed application replacement was accepted")
	}
	pending, _ := service.directory.record("browser")
	if pending.Status != RecordUpdating || pending.Revision != 2 || pending.PendingTemplate == nil || pending.PendingTemplate.BaseRevision != 1 {
		t.Fatalf("pending state: %+v", pending)
	}
	if _, err := service.Ensure(context.Background(), "browser"); !errors.Is(err, ErrTemplateChangePending) {
		t.Fatalf("pending template change launched: %v", err)
	}
	admin.patchErr = nil
	completed, err := service.ApplyBrowserTemplate(context.Background(), "browser", 1, "camoufox-linux", "env-r7d", "fixed-1920", "root", "template-retry")
	if err != nil || completed.Status != RecordReady || completed.Revision != 3 || completed.PendingTemplate != nil {
		t.Fatalf("retry: %+v err=%v", completed, err)
	}
}

func TestTemplateApplyInvalidApplicationDoesNotEnterPending(t *testing.T) {
	artifact := r7dArtifact()
	artifact.Application = map[string]any{
		"provider_config": map[string]any{"image": "sha256:" + strings.Repeat("9", 64)},
	}
	admin := &managementAdmin{}
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(
		fake, store, "https://adapter.example",
		[]Definition{{ID: "browser", ApplicationID: "app-browser", HomeName: "browser-home", StartURL: "https://example.com"}},
		WithLifecycle(fake), WithDirectory(filepath.Join(t.TempDir(), "profiles.json")), WithAdminOrchestrator(admin),
		WithEnvironmentCatalog(StaticEnvironmentCatalog{"env-r7d": artifact}),
		WithTemplateCatalog(StaticTemplateCatalog{
			Version: 1,
			BrowserTemplates: []BrowserTemplate{{
				ID: "camoufox-linux", Revision: 1, Status: "accepted", Label: "Camoufox", Engine: "camoufox",
				Version: "135.0", OSFamily: "linux", Platform: "Linux x86_64", UserAgentProduct: "Firefox", AllowNewBrowsers: true,
			}},
			DisplayTemplates: []DisplayTemplate{{
				ID: "fixed-1920", Revision: 1, Status: "accepted", Label: "固定指纹 1920×1080",
				DisplayServer: "x11", Transport: "selkies", Screen: "1920x1080@1", Scaling: "fixed",
			}},
			Compatibility: []TemplateCompatibility{{
				BrowserTemplateID: "camoufox-linux", EnvironmentArtifactID: "env-r7d", DisplayTemplateID: "fixed-1920", Status: "accepted",
			}},
		}),
	)
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = "browser-home"
	if _, err := service.ApplyBrowserTemplate(context.Background(), "browser", 1, "camoufox-linux", "env-r7d", "fixed-1920", "root", "template-invalid-app"); !errors.Is(err, ErrArtifactUnavailable) {
		t.Fatalf("invalid application error=%v", err)
	}
	record, _ := service.directory.record("browser")
	if record.Status != RecordReady || record.Revision != 1 || record.PendingTemplate != nil || admin.replaceCalls != 0 {
		t.Fatalf("deterministic invalid application entered pending or mutated app: %+v replaces=%d", record, admin.replaceCalls)
	}
}

func TestCreateBrowserWithTemplateCatalogRequiresAllowedAcceptedCombination(t *testing.T) {
	admin := &managementAdmin{}
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(
		fake, store, "https://adapter.example",
		[]Definition{{ID: "seed", ApplicationID: "seed-app", HomeName: "seed-home", StartURL: "https://example.com"}},
		WithLifecycle(fake), WithDirectory(filepath.Join(t.TempDir(), "profiles.json")), WithAdminOrchestrator(admin),
		WithEnvironmentCatalog(StaticEnvironmentCatalog{"env-r7d": r7dArtifact()}),
		WithTemplateCatalog(r7dCatalog()),
	)
	if err != nil {
		t.Fatal(err)
	}
	request := CreateBrowserRequest{
		Label: "New", StartURL: "https://example.com/start", EnvironmentArtifactID: "env-r7d",
		NetworkMode: "direct", NetworkPolicyID: "direct-r1", NetworkPolicySHA256: strings.Repeat("f", 64),
	}
	if _, err := service.CreateBrowser(context.Background(), request, "root", "create-no-template"); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("raw artifact bypassed R7D selection: %v", err)
	}
	request.BrowserTemplateID, request.DisplayTemplateID = "camoufox-linux", "fixed-1920"
	record, err := service.CreateBrowser(context.Background(), request, "root", "create-template")
	if err != nil {
		t.Fatal(err)
	}
	if record.BrowserTemplateID != "camoufox-linux" || record.BrowserTemplateRevision != 1 ||
		record.EnvironmentArtifactID != "env-r7d" || record.EnvironmentTemplateRevision != 1 ||
		record.DisplayTemplateID != "fixed-1920" || record.DisplayTemplateRevision != 1 ||
		record.Language == nil || *record.Language != "en_US.UTF-8" || record.Timezone == nil || *record.Timezone != "America/New_York" {
		t.Fatalf("created template binding: %+v", record)
	}
	request.DisplayTemplateID = "fixed-1280"
	if _, err := service.CreateBrowser(context.Background(), request, "root", "create-incompatible"); !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("incompatible display was accepted: %v", err)
	}
}

func TestNetworkRevisionDoesNotRewriteTemplateBinding(t *testing.T) {
	now := time.Date(2026, 9, 23, 0, 0, 0, 0, time.UTC)
	dir, err := newDirectory([]Definition{{
		ID: "browser", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com",
		NetworkMode: "direct", NetworkPolicyID: "direct-r1", NetworkPolicySHA256: strings.Repeat("a", 64),
		EnvironmentArtifactID: "env-r7d", EnvironmentArtifactSHA256: strings.Repeat("b", 64), EnvironmentSource: "frozen",
		BrowserTemplateID: "camoufox-linux", BrowserTemplateRevision: 1, EnvironmentTemplateRevision: 1,
		DisplayTemplateID: "fixed-1920", DisplayTemplateRevision: 1,
	}}, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	dir.path = filepath.Join(t.TempDir(), "profiles.json")
	if err := dir.writeLocked(); err != nil {
		t.Fatal(err)
	}
	before, _ := dir.record("browser")
	after, err := dir.setNetwork("browser", before.Revision, "root", NetworkBinding{
		Mode: "proxy_required", PolicyID: "proxy-r2", PolicySHA256: strings.Repeat("c", 64),
	})
	if err != nil {
		t.Fatal(err)
	}
	if after.BrowserTemplateID != before.BrowserTemplateID || after.BrowserTemplateRevision != before.BrowserTemplateRevision ||
		after.EnvironmentArtifactID != before.EnvironmentArtifactID || after.EnvironmentTemplateRevision != before.EnvironmentTemplateRevision ||
		after.DisplayTemplateID != before.DisplayTemplateID || after.DisplayTemplateRevision != before.DisplayTemplateRevision {
		t.Fatalf("network revision rewrote template binding: before=%+v after=%+v", before, after)
	}
}
