package profile

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func multiEngineCatalog() StaticTemplateCatalog {
	data := generationCatalog()
	data.BrowserTemplates = append(data.BrowserTemplates,
		BrowserTemplate{ID: "chromix-linux-154", Revision: 1, Status: "accepted", Label: "Chromix 154", Engine: "chromix", Version: "154.0.8037.57", OSFamily: "linux", Platform: "Linux x86_64", UserAgentProduct: "Chrome", AllowNewBrowsers: true},
		BrowserTemplate{ID: "firefox-linux-155", Revision: 1, Status: "accepted", Label: "Firefox 155", Engine: "firefox", Version: "155.0.1", OSFamily: "linux", Platform: "Linux x86_64", UserAgentProduct: "Firefox", AllowNewBrowsers: true})
	return data
}
func TestMultiEngineTargetsAndPolicy(t *testing.T) {
	s, _ := jobService(t)
	s.templateCatalog = multiEngineCatalog()
	targets, e := s.generationTargets(context.Background())
	if e != nil || len(targets) != 3 {
		t.Fatalf("targets: %v %v", targets, e)
	}
	for _, target := range targets {
		spec, e := validateEnvironmentJob(EnvironmentJobRequest{Generation: &target, Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC", ScreenWidth: 1280, ScreenHeight: 900, DPR: 1})
		if e != nil {
			t.Fatal(e)
		}
		if target.Engine == "chromix" && spec.WebRTCPolicy != "proxy-only" {
			t.Fatal("wrong WebRTC promise")
		}
		if target.Engine != "camoufox" {
			_, e = validateEnvironmentJob(EnvironmentJobRequest{Generation: &target, Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC", ScreenWidth: 1280, ScreenHeight: 900, DPR: 1, WindowWidth: 1000, WindowHeight: 800})
			if e != nil {
				t.Fatal("valid fixed native window rejected", e)
			}
		}
	}
	a := r7dArtifact()
	a.BrowserEngine = "firefox"
	a.BrowserTemplateID = "firefox-linux-155"
	a.BrowserVersion = "155.0.1"
	a.UserAgent = "Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0"
	b := multiEngineCatalog().BrowserTemplates[2]
	d := DisplayTemplate{Screen: a.Screen}
	if e := coherentTemplateArtifact(b, d, a); e != nil {
		t.Fatal(e)
	}
	a.UserAgent = strings.ReplaceAll(a.UserAgent, "155.0", "154.0")
	if coherentTemplateArtifact(b, d, a) == nil {
		t.Fatal("foreign UA accepted")
	}
}
func TestR6RPrepareIsolatedFixture(t *testing.T) {
	root := os.Getenv("R6R_QA_ROOT")
	if root == "" {
		t.Skip("isolated fixture not requested")
	}
	if !strings.Contains(root, "/runtime/r6r-multi-engine-") {
		t.Fatal("QA scope required")
	}
	spool := filepath.Join(root, "jobs")
	if e := os.Mkdir(spool, 0700); e != nil {
		t.Fatal(e)
	}
	s, _ := jobService(t)
	WithEnvironmentJobs(spool)(s)
	s.templateCatalog = multiEngineCatalog()
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "QA 通用多语言", Locale: "zh-CN", Languages: []string{"zh-CN", "en-US", "en"}, Timezone: "Asia/Taipei"})
	if e != nil {
		t.Fatal(e)
	}
	for _, width := range []int{1280, 1600} {
		dp, e := s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "QA Desktop", Mode: "fixed", Width: width, Height: 900, DPR: 1})
		if e != nil {
			t.Fatal(e)
		}
		for _, id := range []string{"chromix-linux-154", "firefox-linux-155"} {
			if _, e := s.CreateTemplateCombination(context.Background(), "r6r-qa", fp.ID, dp.ID, id); e != nil {
				t.Fatal(e)
			}
		}
	}
	raw, _ := json.MarshalIndent(multiEngineCatalog(), "", "  ")
	if e := os.WriteFile(filepath.Join(root, "template-catalog.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
}

func TestNativeFirefoxCannotSwitchExistingEngineHome(t *testing.T) {
	for _, engines := range [][2]string{{"camoufox", "firefox"}, {"firefox", "camoufox"}, {"chromix", "firefox"}, {"firefox", "chromix"}} {
		current := r7dArtifact()
		current.BrowserEngine = engines[0]
		s := &Service{catalog: StaticEnvironmentCatalog{current.ID: current}}
		record := Record{Definition: Definition{EnvironmentArtifactID: current.ID}}
		_, err := s.applyTemplateBindingLocked(context.Background(), record, 1, TemplateBinding{}, EnvironmentArtifact{BrowserEngine: engines[1]}, "root", "native-engine-switch")
		if err == nil || !strings.Contains(err.Error(), "engine change requires a new browser Home") {
			t.Fatalf("%v: %v", engines, err)
		}
	}
}
func TestR6RAcceptedCombinationsResolve(t *testing.T) {
	root := os.Getenv("R6R_CATALOG_ROOT")
	if root == "" {
		t.Skip("isolated catalogs not requested")
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
	if e != nil || len(items) != 4 {
		t.Fatalf("catalog %d: %v", len(items), e)
	}
	for _, item := range items {
		if _, _, e := s.resolveTemplateBinding(context.Background(), item.BrowserTemplateID, item.EnvironmentArtifactID, item.DisplayTemplateID); e != nil {
			t.Fatal(e)
		}
	}
}
