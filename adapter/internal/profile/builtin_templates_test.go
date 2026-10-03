package profile

import (
	"browser-platform/adapter/internal/state"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"
)

func TestR6AWInstalledCatalog(t *testing.T) {
	root := os.Getenv("R6AW_CATALOG_ROOT")
	if root == "" {
		t.Skip("isolated installed catalog verification")
	}
	if !strings.Contains(root, "/r6aw-protected-builtins-20261002/") {
		t.Fatal("QA scope")
	}
	ec, err := NewFileEnvironmentCatalog(filepath.Join(root, "environment-catalog.json"))
	if err != nil {
		t.Fatal(err)
	}
	tc, err := NewFileTemplateCatalog(filepath.Join(root, "template-catalog.json"))
	if err != nil {
		t.Fatal(err)
	}
	s := &Service{catalog: ec, templateCatalog: tc}
	if _, err := os.Stat(filepath.Join(root, "jobs")); err == nil {
		s.jobSpool = filepath.Join(root, "jobs")
	}
	items, err := s.CompatibleTemplates(context.Background())
	if err != nil || len(items) != 24 {
		t.Fatal(len(items), err)
	}
	seen := map[string]bool{}
	for _, item := range items {
		if !item.Builtin || !item.AllowNewBrowsers {
			t.Fatal("unprotected or unavailable combination", item)
		}
		key := item.Engine + "/" + item.Locale + "/" + item.Screen
		if seen[key] {
			t.Fatal("duplicate combination", key)
		}
		seen[key] = true
		store, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
		if err != nil {
			t.Fatal(err)
		}
		fake := &lifecycleFake{snapshot: emptyRuntime()}
		service, err := NewService(fake, store, "https://adapter.example", []Definition{{ID: "seed", ApplicationID: "seed-app", HomeName: "seed-home", StartURL: "https://example.com"}}, WithLifecycle(fake), WithDirectory(filepath.Join(t.TempDir(), "profiles.json")), WithAdminOrchestrator(&managementAdmin{}), WithEnvironmentCatalog(ec), WithTemplateCatalog(tc))
		if err != nil {
			t.Fatal(err)
		}
		service.jobSpool = t.TempDir()
		os.Chmod(service.jobSpool, 0700)
		if err := service.DeleteTemplateData(context.Background(), "combinations", item.EnvironmentArtifactID, item.BrowserTemplateID, item.DisplayTemplateID, "root"); !errors.Is(err, ErrBuiltinTemplate) {
			t.Fatal(key, err)
		}
		record, err := service.CreateBrowser(context.Background(), CreateBrowserRequest{Label: "QA built-in", StartURL: "https://example.com", BrowserTemplateID: item.BrowserTemplateID, EnvironmentArtifactID: item.EnvironmentArtifactID, DisplayTemplateID: item.DisplayTemplateID, NetworkMode: "direct", NetworkPolicyID: "direct-r1", NetworkPolicySHA256: strings.Repeat("f", 64)}, "root", "builtin-create")
		if err != nil || (record.ResolutionMode == "auto") != (item.Screen == "auto@system") {
			t.Fatal(key, record, err)
		}
	}
	raw, err := json.Marshal(items)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "verified-choices.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
}

func TestBuiltinSourcesStablePrivateAndProtected(t *testing.T) {
	s, root := jobService(t)
	s.templateCatalog = multiEngineCatalog()
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := s.TemplateSources(); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	got, err := s.TemplateSources()
	if err != nil || !reflect.DeepEqual(got.Fingerprints, builtinFingerprintTemplates()) || !reflect.DeepEqual(got.Displays, builtinDisplayPresets()) {
		t.Fatal(got, err)
	}
	for _, fp := range got.Fingerprints {
		if _, err := s.CreateFingerprintTemplate(context.Background(), fp); !errors.Is(err, ErrEnvironmentJobInvalid) {
			t.Fatal(err)
		}
		if err := s.DeleteTemplateData(context.Background(), "fingerprints", fp.ID, "", "", "root"); !errors.Is(err, ErrBuiltinTemplate) {
			t.Fatal(err)
		}
	}
	for _, dp := range got.Displays {
		if _, err := s.CreateDisplayPreset(context.Background(), dp); !errors.Is(err, ErrEnvironmentJobInvalid) {
			t.Fatal(err)
		}
		if err := s.DeleteTemplateData(context.Background(), "displays", dp.ID, "", "", "root"); !errors.Is(err, ErrBuiltinTemplate) {
			t.Fatal(err)
		}
	}
	reopened, _ := jobService(t)
	reopened.jobSpool = root
	reopened.templateCatalog = multiEngineCatalog()
	again, err := reopened.TemplateSources()
	if err != nil || !reflect.DeepEqual(got, again) {
		t.Fatal(again, err)
	}
	for kind, ids := range map[string][]string{"fingerprints": {got.Fingerprints[0].ID}, "displays": {got.Displays[0].ID, got.Displays[1].ID}} {
		for _, id := range ids {
			info, err := os.Stat(filepath.Join(root, "templates", kind, id+".json"))
			if err != nil || info.Mode().Perm() != 0600 {
				t.Fatal(info, err)
			}
		}
	}
}

func TestBuiltinCorruptionFailsWithoutOverwritingEvidence(t *testing.T) {
	for _, change := range []string{"fingerprint-content", "fingerprint-flag", "display-content", "display-flag", "tombstone"} {
		t.Run(change, func(t *testing.T) {
			s, root := jobService(t)
			s.templateCatalog = generationCatalog()
			sources, err := s.TemplateSources()
			if err != nil {
				t.Fatal(err)
			}
			kind, id := "fingerprints", sources.Fingerprints[0].ID
			if strings.HasPrefix(change, "display") {
				kind, id = "displays", builtinFixedDisplayID
			}
			path := filepath.Join(root, "templates", kind, id+".json")
			if change == "tombstone" {
				if err := s.markDataDeleted("fingerprints", "root", id); err != nil {
					t.Fatal(err)
				}
			} else {
				raw, _ := os.ReadFile(path)
				var value map[string]any
				if err := json.Unmarshal(raw, &value); err != nil {
					t.Fatal(err)
				}
				if strings.HasSuffix(change, "flag") {
					delete(value, "builtin")
				} else {
					value["label"] = "altered"
				}
				raw, _ = json.Marshal(value)
				if err := os.WriteFile(path, raw, 0600); err != nil {
					t.Fatal(err)
				}
			}
			before, _ := os.ReadFile(path)
			if _, err := s.TemplateSources(); err == nil {
				t.Fatal("corrupt built-in accepted")
			}
			after, _ := os.ReadFile(path)
			if string(before) != string(after) {
				t.Fatal("corruption silently overwritten")
			}
		})
	}
}

func TestBuiltinCombinationCannotBeDeleted(t *testing.T) {
	s := templateService(t, r7dArtifact())
	s.jobSpool = t.TempDir()
	os.Chmod(s.jobSpool, 0700)
	catalog, err := s.templateCatalog.Read(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	catalog.Compatibility[0].Builtin = true
	s.templateCatalog = StaticTemplateCatalog(catalog)
	combo := catalog.Compatibility[0]
	if err := s.DeleteTemplateData(context.Background(), "combinations", combo.EnvironmentArtifactID, combo.BrowserTemplateID, combo.DisplayTemplateID, "root"); !errors.Is(err, ErrBuiltinTemplate) {
		t.Fatal(err)
	}
	choices, err := s.CompatibleTemplates(context.Background())
	if err != nil || len(choices) != 1 || !choices[0].Builtin {
		t.Fatal(choices, err)
	}
}

// Real-service queue fixture, executed only against an explicitly scoped QA root.
func TestR6AWQueueBuiltinBatch(t *testing.T) {
	root := os.Getenv("R6AW_QA_ROOT")
	if root == "" {
		t.Skip("isolated acceptance fixture")
	}
	if !strings.Contains(root, "/r6aw-protected-builtins-20261002/") {
		t.Fatal("QA scope")
	}
	s, _ := jobService(t)
	spool := filepath.Join(root, "jobs")
	if err := os.MkdirAll(spool, 0700); err != nil {
		t.Fatal(err)
	}
	WithEnvironmentJobs(spool)(s)
	s.templateCatalog = multiEngineCatalog()
	sources, err := s.TemplateSources()
	if err != nil {
		t.Fatal(err)
	}
	fpID, dpID := os.Getenv("R6AW_FP"), os.Getenv("R6AW_DISPLAY")
	for _, target := range sources.GenerationTargets {
		if _, err := s.CreateTemplateCombination(context.Background(), "r6aw-qa", fpID, dpID, target.BrowserTemplateID); err != nil {
			t.Fatal(err)
		}
	}
	path := filepath.Join(root, "template-catalog.json")
	if _, err := os.Stat(path); os.IsNotExist(err) {
		raw, _ := json.MarshalIndent(multiEngineCatalog(), "", "  ")
		if err := os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
}
