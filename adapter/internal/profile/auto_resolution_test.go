package profile

import (
	"path/filepath"
	"testing"
)

func TestAutoDisplayCatalogRejectsFixedScreenAndUnsupportedEngine(t *testing.T) {
	catalog := TemplateCatalogData(r7dCatalog())
	catalog.DisplayTemplates[0].Scaling = "auto"
	catalog.DisplayTemplates[0].Screen = "auto@1"
	if err := validateTemplateCatalog(catalog); err != nil {
		t.Fatal(err)
	}
	artifact := r7dArtifact()
	artifact.Screen = "auto@1"
	if err := coherentTemplateArtifact(catalog.BrowserTemplates[0], catalog.DisplayTemplates[0], artifact); err == nil {
		t.Fatal("unvalidated Camoufox auto accepted")
	}
	browser := catalog.BrowserTemplates[0]
	browser.Engine = "chromix"
	browser.UserAgentProduct = "Chrome"
	artifact.BrowserEngine = "chromix"
	artifact.UserAgent = "Chrome/135.0"
	if err := coherentTemplateArtifact(browser, catalog.DisplayTemplates[0], artifact); err != nil {
		t.Fatal(err)
	}
	catalog.DisplayTemplates[0].Screen = "auto@system"
	artifact.Screen = "auto@system"
	if err := validateTemplateCatalog(catalog); err != nil {
		t.Fatal(err)
	}
	if err := coherentTemplateArtifact(browser, catalog.DisplayTemplates[0], artifact); err != nil {
		t.Fatal(err)
	}
	artifact.Screen = "auto@1"
	if err := coherentTemplateArtifact(browser, catalog.DisplayTemplates[0], artifact); err == nil {
		t.Fatal("DPR contract mismatch accepted")
	}
	for _, screen := range []string{"1920x1080@1", "auto@2", "auto"} {
		catalog.DisplayTemplates[0].Screen = screen
		if err := validateTemplateCatalog(catalog); err == nil {
			t.Fatalf("accepted %s", screen)
		}
	}
	catalog.DisplayTemplates[0].Screen = "auto@1"
	catalog.DisplayTemplates[0].Scaling = "fixed"
	if err := validateTemplateCatalog(catalog); err == nil {
		t.Fatal("fixed auto screen accepted")
	}
}

func TestAutoResolutionPersistsAndRejectsFixedPreferences(t *testing.T) {
	definition := Definition{ID: "personal", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com", BrowserTemplateID: "chromix", BrowserTemplateRevision: 1, EnvironmentArtifactID: "env", EnvironmentArtifactSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", EnvironmentSource: "frozen", EnvironmentTemplateRevision: 1, DisplayTemplateID: "auto", DisplayTemplateRevision: 1, ResolutionMode: "auto"}
	path := filepath.Join(t.TempDir(), "profiles.json")
	service, fake := directoryService(t, path, []Definition{definition})
	label := "Automatic browser"
	record, err := service.UpdateBrowser("personal", 1, "root", BrowserPatch{Label: &label})
	if err != nil {
		t.Fatal(err)
	}
	reloaded, _ := directoryService(t, path, []Definition{definition})
	got, ok := reloaded.directory.record("personal")
	if !ok || got.ResolutionMode != "auto" || record.Revision != 2 || fake.stopCalls != 0 {
		t.Fatal("automatic mode not persisted")
	}
	mode := "fill"
	if _, err := reloaded.UpdateBrowser("personal", 2, "root", BrowserPatch{DisplayPreference: &mode}); err == nil {
		t.Fatal("fixed preference accepted for auto")
	}
	if reloaded.DisplayPreference("personal") != "" {
		t.Fatal("gateway transformed dynamic stream")
	}
	binding := templateBindingFromDefinition(definition)
	base := definition
	base.ResolutionMode = ""
	base.DisplayPreference = "contain"
	if got := definitionWithTemplateBinding(base, binding); got.ResolutionMode != "auto" || got.DisplayPreference != "" {
		t.Fatal("binding did not remove fixed preference")
	}
	binding.ResolutionMode = ""
	if got := definitionWithTemplateBinding(definition, binding); got.ResolutionMode != "" {
		t.Fatal("fixed-mode rollback lost")
	}
}
