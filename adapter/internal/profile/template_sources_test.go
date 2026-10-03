package profile

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIndependentTemplatesComposeWithoutScreenInFingerprint(t *testing.T) {
	s, root := jobService(t)
	s.templateCatalog = generationCatalog()
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "US", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"})
	if e != nil {
		t.Fatal(e)
	}
	raw, e := os.ReadFile(filepath.Join(root, "templates/fingerprints", fp.ID+".json"))
	if e != nil {
		t.Fatal(e)
	}
	for _, field := range []string{"screen", "window", "dpr", "width", "height", "engine", "browser_version"} {
		if strings.Contains(string(raw), field) {
			t.Fatalf("fingerprint contains %s", field)
		}
	}
	for _, width := range []int{1280, 1600} {
		dp, e := s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "Desktop", Mode: "fixed", Width: width, Height: 900, DPR: 1})
		if e != nil {
			t.Fatal(e)
		}
		job, e := s.CreateTemplateCombination(context.Background(), "root", fp.ID, dp.ID, "camoufox-linux-v152")
		if e != nil {
			t.Fatal(e)
		}
		var req environmentJobRequestFile
		raw, e = os.ReadFile(filepath.Join(root, "queue", job.ID+".json"))
		if e != nil {
			t.Fatal(e)
		}
		if e = json.Unmarshal(raw, &req); e != nil {
			t.Fatal(e)
		}
		if req.Version != 3 || req.Generation == nil || req.Generation.BrowserVersion != "152.0" || fp.Version != 2 || req.Spec.Screen.Width != width || req.Spec.Window.Width != width || req.Templates.FingerprintID != fp.ID || len(req.Templates.DisplaySHA256) != 64 {
			t.Fatal("composition mismatch")
		}
	}
	got, e := s.TemplateSources()
	if e != nil || len(got.Fingerprints) != 5 || len(got.Displays) != 4 {
		t.Fatalf("reload: %+v %v", got, e)
	}
	if _, e = s.CreateTemplateCombination(context.Background(), "root", "../outside", got.Displays[0].ID, "camoufox-linux-v152"); e == nil {
		t.Fatal("foreign source accepted")
	}
	if _, e = s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "Bad", Mode: "auto", Width: 1280, Height: 720, DPR: 1}); e == nil {
		t.Fatal("unsupported mode accepted")
	}
	if _, e = s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "Bad", Mode: "fixed", Width: 1280, Height: 720, DPR: 2}); e == nil {
		t.Fatal("unsupported DPR accepted")
	}
}
func TestTemplateSourceSymlinkAndUnknownFieldsRejected(t *testing.T) {
	s, root := jobService(t)
	s.templateCatalog = generationCatalog()
	outside := t.TempDir()
	if e := os.Symlink(outside, filepath.Join(root, "templates")); e != nil {
		t.Fatal(e)
	}
	if _, e := s.TemplateSources(); e == nil {
		t.Fatal("symlink source root accepted")
	}
}

// Optional integration fixture: the real service creates the exact v3 queue
// consumed by the isolated runner. It never references a production spool.
func TestR6QPrepareIsolatedFixture(t *testing.T) {
	root := os.Getenv("R6Q_QA_ROOT")
	if root == "" {
		t.Skip("isolated fixture not requested")
	}
	if !strings.Contains(root, "/runtime/r6q-engine-neutral-") {
		t.Fatal("QA scope required")
	}
	spool := filepath.Join(root, "jobs")
	if e := os.Mkdir(spool, 0700); e != nil {
		t.Fatal(e)
	}
	s, _ := jobService(t)
	s.templateCatalog = generationCatalog()
	WithEnvironmentJobs(spool)(s)
	fp, e := s.CreateFingerprintTemplate(context.Background(), FingerprintTemplate{Label: "QA US", Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "UTC"})
	if e != nil {
		t.Fatal(e)
	}
	for _, width := range []int{1280, 1600} {
		dp, e := s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: fmt.Sprintf("QA %d", width), Mode: "fixed", Width: width, Height: 900, DPR: 1})
		if e != nil {
			t.Fatal(e)
		}
		if _, e = s.CreateTemplateCombination(context.Background(), "r6q-qa", fp.ID, dp.ID, "camoufox-linux-v152"); e != nil {
			t.Fatal(e)
		}
	}
}

func generationCatalog() StaticTemplateCatalog {
	return StaticTemplateCatalog{Version: 1, BrowserTemplates: []BrowserTemplate{{ID: "camoufox-linux-v152", Revision: 1, Status: "accepted", Label: "Camoufox", Engine: "camoufox", Version: "152.0", OSFamily: "linux", Platform: "Linux x86_64", UserAgentProduct: "Firefox", AllowNewBrowsers: true}}}
}
func TestGenericSourcesRejectEngineAndRequireSupportedTarget(t *testing.T) {
	s, root := jobService(t)
	s.templateCatalog = generationCatalog()
	input := FingerprintTemplate{Label: "US", Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC"}
	bad := input
	bad.Engine = "camoufox"
	bad.BrowserVersion = "152.0"
	if _, err := s.CreateFingerprintTemplate(context.Background(), bad); err == nil {
		t.Fatal("engine fields accepted")
	}
	fp, err := s.CreateFingerprintTemplate(context.Background(), input)
	if err != nil {
		t.Fatal(err)
	}
	dp, err := s.CreateDisplayPreset(context.Background(), DisplayPreset{Label: "HD", Mode: "fixed", Width: 1280, Height: 720, DPR: 1})
	if err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"", "unknown", "chromix-linux-154"} {
		if _, err := s.CreateTemplateCombination(context.Background(), "root", fp.ID, dp.ID, id); err == nil {
			t.Fatalf("unsupported target %q accepted", id)
		}
	}
	catalog := generationCatalog()
	catalog.BrowserTemplates[0].Version = "153.0"
	s.templateCatalog = catalog
	if _, err := s.CreateTemplateCombination(context.Background(), "root", fp.ID, dp.ID, "camoufox-linux-v152"); err == nil {
		t.Fatal("unsupported version accepted")
	}
	s.templateCatalog = generationCatalog()
	// A legacy record is read as-is, and can use its original engine in a v3 job.
	bad.ID = "fp-aaaaaaaaaaaaaaaa"
	bad.Revision = 1
	bad.CreatedAt = "2026-10-01T00:00:00Z"
	path := filepath.Join(root, "templates/fingerprints", bad.ID+".json")
	if err := writeNewTemplate(path, bad); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(path)
	if _, err := s.CreateTemplateCombination(context.Background(), "root", bad.ID, dp.ID, "camoufox-linux-v152"); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("legacy source changed")
	}
	// Historical v2 jobs must remain listable beside new v3 requests.
	jobs, err := s.EnvironmentJobs()
	if err != nil || len(jobs) != 1 {
		t.Fatalf("jobs: %v %v", jobs, err)
	}
	var req environmentJobRequestFile
	queue := filepath.Join(root, "queue", jobs[0].ID+".json")
	raw, _ := os.ReadFile(queue)
	json.Unmarshal(raw, &req)
	req.Version = 2
	req.Generation = nil
	raw, _ = json.Marshal(req)
	os.WriteFile(queue, raw, 0600)
	if jobs, err = s.EnvironmentJobs(); err != nil || len(jobs) != 1 {
		t.Fatalf("v2 lost: %v", err)
	}
}
