package profile

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestR6PAcceptedCombinationsResolve(t *testing.T) {
	root := os.Getenv("R6P_CATALOG_ROOT")
	if root == "" {
		t.Skip("isolated accepted catalogs not requested")
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
	if e != nil {
		t.Fatal(e)
	}
	if len(items) != 2 {
		t.Fatalf("want 2, got %d", len(items))
	}
	for _, v := range items {
		if v.EnvironmentLabel == "" {
			t.Fatal("missing source/display label")
		}
		if _, _, e = s.resolveTemplateBinding(context.Background(), v.BrowserTemplateID, v.EnvironmentArtifactID, v.DisplayTemplateID); e != nil {
			t.Fatal(e)
		}
	}
	if items[0].DisplayTemplateID == items[1].DisplayTemplateID {
		t.Fatal("display choices not independent")
	}
	if _, _, e = s.resolveTemplateBinding(context.Background(), items[0].BrowserTemplateID, items[0].EnvironmentArtifactID, items[1].DisplayTemplateID); e == nil {
		t.Fatal("unaccepted combination allowed")
	}
}
