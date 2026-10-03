package profile

import (
	"browser-platform/adapter/internal/state"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSharedDisplayBuiltinAndAllEngines(t *testing.T) {
	s, _ := jobService(t)
	s.templateCatalog = multiEngineCatalog()
	sources, e := s.TemplateSources()
	if e != nil || len(sources.Displays) != 2 || sources.Displays[0] != builtinDisplayPreset() {
		t.Fatal(sources, e)
	}
	if _, e = s.CreateDisplayPreset(context.Background(), builtinDisplayPreset()); e == nil {
		t.Fatal("built-in mutation allowed")
	}
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "Generic", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"})
	if e != nil {
		t.Fatal(e)
	}
	for _, target := range sources.GenerationTargets {
		job, e := s.CreateTemplateCombination(context.Background(), "root", fp.ID, builtinDisplayID, target.BrowserTemplateID)
		if e != nil {
			t.Fatal(target, e)
		}
		if job.Screen != "auto@system" || job.Window != "auto" {
			t.Fatal("automatic display mislabeled", job)
		}
		var req environmentJobRequestFile
		raw, e := os.ReadFile(filepath.Join(s.jobSpool, "queue", job.ID+".json"))
		if e != nil {
			t.Fatal(e)
		}
		if e = json.Unmarshal(raw, &req); e != nil {
			t.Fatal(e)
		}
		if req.Spec.Screen.Mode != "auto" || req.Spec.Screen.DPRMode != "system" || req.Spec.Screen.DeviceScaleFactor != nil {
			t.Fatal(req.Spec)
		}
	}
}

func TestR6SPrepareFixture(t *testing.T) {
	root := os.Getenv("R6S_QA_ROOT")
	if root == "" {
		t.Skip("isolated fixture only")
	}
	if !strings.Contains(root, "/runtime/r6s-shared-display-") {
		t.Fatal("scope")
	}
	s, _ := jobService(t)
	spool := filepath.Join(root, "jobs")
	if e := os.Mkdir(spool, 0700); e != nil {
		t.Fatal(e)
	}
	WithEnvironmentJobs(spool)(s)
	s.templateCatalog = multiEngineCatalog()
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "默认通用 · en-US / UTC", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"})
	if e != nil {
		t.Fatal(e)
	}
	fixed, e := s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "自定义 1280×900 · 窗口 1000×800", Mode: "fixed", Width: 1280, Height: 900, DPR: 1, WindowWidth: 1000, WindowHeight: 800})
	if e != nil {
		t.Fatal(e)
	}
	// Queue three automatic jobs first; fixed jobs use the same source later.
	for _, target := range multiEngineCatalog().BrowserTemplates {
		if _, e = s.CreateTemplateCombination(context.Background(), "r6s-qa", fp.ID, builtinDisplayID, target.ID); e != nil {
			t.Fatal(e)
		}
	}
	raw, _ := json.MarshalIndent(multiEngineCatalog(), "", "  ")
	if e = os.WriteFile(filepath.Join(root, "template-catalog.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
	raw, _ = json.Marshal(map[string]string{"fingerprint_id": fp.ID, "fixed_display_id": fixed.ID})
	if e = os.WriteFile(filepath.Join(root, "fixture.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
}

func TestR6SQueueFixed(t *testing.T) {
	root := os.Getenv("R6S_FIXED_ROOT")
	queueR6SDisplay(t, root, false)
}

func TestR6SQueueAutomatic(t *testing.T) {
	queueR6SDisplay(t, os.Getenv("R6S_AUTO_ROOT"), true)
}

func queueR6SDisplay(t *testing.T, root string, automatic bool) {
	t.Helper()
	if root == "" {
		t.Skip("isolated fixture only")
	}
	if !strings.Contains(root, "/runtime/r6s-shared-display-") {
		t.Fatal("scope")
	}
	s, _ := jobService(t)
	WithEnvironmentJobs(filepath.Join(root, "jobs"))(s)
	s.templateCatalog = multiEngineCatalog()
	raw, e := os.ReadFile(filepath.Join(root, "fixture.json"))
	if e != nil {
		t.Fatal(e)
	}
	var ids map[string]string
	if e = json.Unmarshal(raw, &ids); e != nil {
		t.Fatal(e)
	}
	for _, target := range multiEngineCatalog().BrowserTemplates {
		if engine := os.Getenv("R6S_ENGINE"); engine != "" && target.Engine != engine {
			continue
		}
		displayID := ids["fixed_display_id"]
		if engine := os.Getenv("R6S_AUTO_ENGINE"); automatic && engine != "" && target.Engine != engine {
			continue
		}
		if automatic {
			displayID = builtinDisplayID
		}
		fingerprintID := ids["fingerprint_id"]
		if target.Engine == "chromix" && ids["chromix_fingerprint_id"] != "" {
			fingerprintID = ids["chromix_fingerprint_id"]
		}
		if _, e = s.CreateTemplateCombination(context.Background(), "r6s-qa", fingerprintID, displayID, target.ID); e != nil {
			t.Fatal(e)
		}
	}
}

func TestR6SReplaceChromixSource(t *testing.T) {
	root := os.Getenv("R6S_NEW_SOURCE_ROOT")
	if root == "" {
		t.Skip("isolated revised image")
	}
	if !strings.Contains(root, "/runtime/r6s-shared-display-") {
		t.Fatal("scope")
	}
	s, _ := jobService(t)
	WithEnvironmentJobs(filepath.Join(root, "jobs"))(s)
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "通用模板 2 · en-US / UTC", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"})
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(root, "fixture.json")
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	var ids map[string]string
	if e = json.Unmarshal(raw, &ids); e != nil {
		t.Fatal(e)
	}
	if ids["chromix_fingerprint_id"] != "" {
		t.Fatal("source already created")
	}
	ids["chromix_fingerprint_id"] = fp.ID
	raw, e = json.Marshal(ids)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(path, raw, 0600); e != nil {
		t.Fatal(e)
	}
}

func TestR6SAcceptedCatalog(t *testing.T) {
	root := os.Getenv("R6S_CATALOG_ROOT")
	if root == "" {
		t.Skip("isolated catalog only")
	}
	ec, e := NewFileEnvironmentCatalog(filepath.Join(root, "environment-catalog.json"))
	if e != nil {
		t.Fatal(e)
	}
	tc, e := NewFileTemplateCatalog(filepath.Join(root, "template-catalog.json"))
	if e != nil {
		t.Fatal(e)
	}
	s := &Service{catalog: ec, templateCatalog: tc}
	items, e := s.CompatibleTemplates(context.Background())
	if e != nil || len(items) != 6 {
		t.Fatal(len(items), e)
	}
	for _, v := range items {
		if _, _, e = s.resolveTemplateBinding(context.Background(), v.BrowserTemplateID, v.EnvironmentArtifactID, v.DisplayTemplateID); e != nil {
			t.Fatal(e)
		}
		store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
		if err != nil {
			t.Fatal(err)
		}
		fake := &lifecycleFake{snapshot: emptyRuntime()}
		service, err := NewService(fake, store, "https://adapter.example", []Definition{{ID: "seed", ApplicationID: "seed-app", HomeName: "seed-home", StartURL: "https://example.com"}}, WithLifecycle(fake), WithDirectory(filepath.Join(t.TempDir(), "profiles.json")), WithAdminOrchestrator(&managementAdmin{}), WithEnvironmentCatalog(ec), WithTemplateCatalog(tc))
		if err != nil {
			t.Fatal(err)
		}
		record, err := service.CreateBrowser(context.Background(), CreateBrowserRequest{Label: "Shared display", StartURL: "https://example.com", BrowserTemplateID: v.BrowserTemplateID, EnvironmentArtifactID: v.EnvironmentArtifactID, DisplayTemplateID: v.DisplayTemplateID, NetworkMode: "direct", NetworkPolicyID: "direct-r1", NetworkPolicySHA256: strings.Repeat("f", 64)}, "root", "shared-create")
		if err != nil {
			t.Fatal(v, err)
		}
		if (record.ResolutionMode == "auto") != (v.Screen == "auto@system") {
			t.Fatal(record)
		}
	}
	raw, err := json.Marshal(items)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "compatible.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
}
