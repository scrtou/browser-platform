package profile

import (
	"path/filepath"
	"sync"
	"testing"
)

func TestUIScalingLegacyPersistsAndRejectsConcurrentOverwrite(t *testing.T) {
	path := filepath.Join(t.TempDir(), "profiles.json")
	seed := []Definition{{ID: "work", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com", WaylandMode: true}, {ID: "fixed", ApplicationID: "fixed", HomeName: "fixed", StartURL: "https://example.com"}}
	service, fake := directoryService(t, path, seed)
	p := 150
	if _, err := service.UpdateBrowser("fixed", 1, "owner", BrowserPatch{UIScalingPercent: &p}); err == nil {
		t.Fatal("fixed DPI modified")
	}
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for _, value := range []int{150, 200} {
		wg.Add(1)
		go func(value int) {
			defer wg.Done()
			_, err := service.UpdateBrowser("work", 1, "owner", BrowserPatch{UIScalingPercent: &value})
			results <- err
		}(value)
	}
	wg.Wait()
	close(results)
	success, conflict := 0, 0
	for err := range results {
		if err == nil {
			success++
		} else if err == ErrRevisionMismatch {
			conflict++
		} else {
			t.Fatal(err)
		}
	}
	if success != 1 || conflict != 1 {
		t.Fatal("concurrent setting overwrote accepted update")
	}
	reloaded, _ := directoryService(t, path, seed)
	percent, revision, supported := reloaded.UIScalingPreference("work")
	if !supported || revision != 2 || (percent != 150 && percent != 200) || fake.stopCalls != 0 {
		t.Fatal("setting or runtime ownership lost")
	}
	for _, bad := range []int{-1, 99, 101, 301} {
		if _, err := reloaded.UpdateBrowser("work", 2, "owner", BrowserPatch{UIScalingPercent: &bad}); err == nil {
			t.Fatalf("accepted %d", bad)
		}
	}
	p = 0
	if _, err := reloaded.UpdateBrowser("work", 2, "owner", BrowserPatch{UIScalingPercent: &p}); err != nil {
		t.Fatal(err)
	}
	again, _ := directoryService(t, path, seed)
	percent, revision, supported = again.UIScalingPreference("work")
	if percent != 0 || revision != 3 || !supported {
		t.Fatal("reset not persisted")
	}
}

func TestUIScalingRespectsBoundDisplayContract(t *testing.T) {
	def := Definition{ID: "personal", ApplicationID: "app", HomeName: "home", StartURL: "https://example.com", BrowserTemplateID: "camoufox", BrowserTemplateRevision: 1, EnvironmentArtifactID: "env", EnvironmentArtifactSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", EnvironmentSource: "frozen", EnvironmentTemplateRevision: 1, DisplayTemplateID: "auto", DisplayTemplateRevision: 1, ResolutionMode: "auto"}
	service, _ := directoryService(t, filepath.Join(t.TempDir(), "profiles.json"), []Definition{def})
	catalog := TemplateCatalogData(r7dCatalog())
	catalog.DisplayTemplates[0].ID = "auto"
	catalog.DisplayTemplates[0].Screen = "auto@system"
	catalog.DisplayTemplates[0].Scaling = "auto"
	catalog.Compatibility[0].DisplayTemplateID = "auto"
	service.templateCatalog = StaticTemplateCatalog(catalog)
	p := 200
	if _, err := service.UpdateBrowser("personal", 1, "owner", BrowserPatch{UIScalingPercent: &p}); err != nil {
		t.Fatal(err)
	}
	catalog.DisplayTemplates[0].Screen = "auto@1"
	service.templateCatalog = StaticTemplateCatalog(catalog)
	if _, _, supported := service.UIScalingPreference("personal"); supported {
		t.Fatal("fixed DPR auto template supported")
	}
	p = 150
	if _, err := service.UpdateBrowser("personal", 2, "owner", BrowserPatch{UIScalingPercent: &p}); err == nil {
		t.Fatal("auto@1 DPI changed")
	}
	def.UIScalingPercent = 200
	if changed := definitionWithTemplateBinding(def, templateBindingFromDefinition(def)); changed.UIScalingPercent != 0 {
		t.Fatal("template transition retained mutable DPI")
	}
}
