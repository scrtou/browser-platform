package profile

import (
	"context"
	"errors"
	"testing"
)

func TestChromixTemplateRequiresCoherentEngineAndVersion(t *testing.T) {
	artifact := r7dArtifact()
	artifact.BrowserEngine = "chromix"
	artifact.BrowserVersion = "154.0.8037.57"
	artifact.UserAgent = "Mozilla/5.0 Chrome/154.0.8037.57 Safari/537.36"
	catalog := r7dCatalog()
	catalog.BrowserTemplates[0].Engine = "chromix"
	catalog.BrowserTemplates[0].Version = artifact.BrowserVersion
	catalog.BrowserTemplates[0].UserAgentProduct = "Chrome"
	if err := validateTemplateCatalog(TemplateCatalogData(catalog)); err != nil {
		t.Fatal(err)
	}
	if err := coherentTemplateArtifact(catalog.BrowserTemplates[0], catalog.DisplayTemplates[0], artifact); err != nil {
		t.Fatal(err)
	}
	artifact.UserAgent = "Mozilla/5.0 Chrome/154.0.0.0 Safari/537.36"
	if err := coherentTemplateArtifact(catalog.BrowserTemplates[0], catalog.DisplayTemplates[0], artifact); err != nil {
		t.Fatal(err)
	}
	artifact.BrowserEngine = "camoufox"
	if err := coherentTemplateArtifact(catalog.BrowserTemplates[0], catalog.DisplayTemplates[0], artifact); err == nil {
		t.Fatal("cross-engine metadata accepted")
	}
}

func TestChromixCannotReuseExistingFirefoxHome(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := templateMutationService(t, admin)
	record, _ := service.directory.record("browser")
	artifact := r7dArtifact()
	artifact.BrowserEngine = "chromix"
	_, err := service.applyTemplateBindingLocked(context.Background(), record, record.Revision, TemplateBinding{}, artifact, "root", "cross-engine")
	if !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("err=%v", err)
	}
	after, _ := service.directory.record("browser")
	if after.Revision != record.Revision || admin.replaceCalls != 0 || fake.stopCalls != 0 {
		t.Fatal("cross-engine request mutated the Home binding")
	}
}

func TestChromixHomeCannotSwitchToFirefoxOrLoseItsSourceMetadata(t *testing.T) {
	admin := &managementAdmin{}
	service, _ := templateMutationService(t, admin)
	record, _ := service.directory.record("browser")
	record.EnvironmentArtifactID = "chromix-old"
	current := r7dArtifact()
	current.ID = record.EnvironmentArtifactID
	current.BrowserEngine = "chromix"
	service.catalog = StaticEnvironmentCatalog{current.ID: current}
	_, err := service.applyTemplateBindingLocked(context.Background(), record, record.Revision, TemplateBinding{}, r7dArtifact(), "root", "reverse")
	if !errors.Is(err, ErrTemplateCatalogUnavailable) {
		t.Fatalf("cross-engine err=%v", err)
	}
	service.catalog = StaticEnvironmentCatalog{}
	_, err = service.applyTemplateBindingLocked(context.Background(), record, record.Revision, TemplateBinding{}, r7dArtifact(), "root", "unknown")
	if !errors.Is(err, ErrArtifactUnavailable) || admin.replaceCalls != 0 {
		t.Fatalf("missing source err=%v writes=%d", err, admin.replaceCalls)
	}
}
