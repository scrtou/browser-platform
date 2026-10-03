package profile

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestDeleteNetworkRevisionPreservesVersionsAndRefusesReferences(t *testing.T) {
	ctx := context.Background()
	admin := &managementAdmin{}
	s, _, record, path := networkCatalogService(t, admin)
	draft, err := s.CreateNetworkProfileDraft(ctx, "root", networkDraftRequest())
	if err != nil {
		t.Fatal(err)
	}
	// A creating browser is also a reference, before its external binding finishes.
	bound := record
	bound.NetworkProfileID = draft.ID
	bound.NetworkProfileRevision = draft.Revision
	s.directory.mu.Lock()
	s.directory.records[record.ID] = bound
	s.directory.mu.Unlock()
	if err := s.DeleteNetworkProfile(ctx, draft.ID, 1, "root", "delete-1"); !errors.Is(err, ErrNetworkProfileReferenced) {
		t.Fatal(err)
	}
	s.directory.mu.Lock()
	s.directory.records[record.ID] = record
	s.directory.mu.Unlock()
	admin.revokeErr = errors.New("QA revoke failure")
	if err := s.DeleteNetworkProfile(ctx, draft.ID, 1, "root", "delete-1"); err == nil {
		t.Fatal("revocation failure hidden")
	}
	if items, _ := s.NetworkProfiles(); len(items) != 1 {
		t.Fatal("failed deletion removed record")
	}
	admin.revokeErr = nil
	if err := s.DeleteNetworkProfile(ctx, draft.ID, 1, "root", "delete-1"); err != nil {
		t.Fatal(err)
	}
	if err := s.DeleteNetworkProfile(ctx, draft.ID, 1, "root", "delete-1"); err != nil {
		t.Fatal(err)
	}
	reopened, err := newNetworkProfileCatalog(path, s.now)
	if err != nil {
		t.Fatal(err)
	}
	s.networkProfiles = reopened
	list, err := s.NetworkProfiles()
	if err != nil || len(list) != 0 {
		t.Fatal(list, err)
	}
	if _, err := s.BindNetworkProfile(ctx, record.ID, record.Revision, draft.ID, 1, "root", "bind-deleted"); !errors.Is(err, ErrNetworkProfileNotAccepted) {
		t.Fatal(err)
	}
	req := networkDraftRequest()
	req.IdempotencyKey = "create-r2"
	next, err := s.CreateNetworkProfileDraft(ctx, "root", req)
	if err != nil || next.Revision != 2 {
		t.Fatal(next, err)
	}
	if err := s.DeleteNetworkProfile(ctx, next.ID, 2, "root", "delete-1"); !errors.Is(err, ErrRevisionMismatch) {
		t.Fatal(err)
	}
}

func TestDeleteSourcesChecksIndirectReferencesAndPreservesEvidence(t *testing.T) {
	ctx := context.Background()
	s, root := jobService(t)
	s.templateCatalog = generationCatalog()
	fp, err := s.CreateFingerprintTemplate(ctx, FingerprintTemplate{Label: "QA", Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC"})
	if err != nil {
		t.Fatal(err)
	}
	dp, err := s.CreateDisplayPreset(ctx, DisplayPreset{Label: "QA", Mode: "fixed", Width: 1920, Height: 1080, DPR: 1})
	if err != nil {
		t.Fatal(err)
	}
	sources, _ := s.TemplateSources()
	job, err := s.CreateTemplateCombination(ctx, "root", fp.ID, dp.ID, sources.GenerationTargets[0].BrowserTemplateID)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(root, "templates/fingerprints", fp.ID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	record := s.Records()[0]
	for _, reference := range []string{"current", "pending", "history"} {
		binding := TemplateBinding{EnvironmentArtifactID: job.EnvironmentID}
		changed := record
		switch reference {
		case "current":
			changed.EnvironmentArtifactID = job.EnvironmentID
		case "pending":
			changed.PendingTemplate = &PendingTemplateChange{Target: binding}
		case "history":
			changed.TemplateHistory = []TemplateRevisionSnapshot{{Binding: binding}}
		}
		s.directory.mu.Lock()
		s.directory.records[record.ID] = changed
		s.directory.mu.Unlock()
		for kind, id := range map[string]string{"fingerprints": fp.ID, "displays": dp.ID, "jobs": job.ID} {
			if err := s.DeleteTemplateData(ctx, kind, id, "", "", "root"); !errors.Is(err, ErrDataReferenced) {
				t.Fatalf("%s %s: %v", reference, kind, err)
			}
		}
	}
	s.directory.mu.Lock()
	s.directory.records[record.ID] = record
	s.directory.mu.Unlock()
	if err := s.DeleteTemplateData(ctx, "jobs", job.ID, "", "", "root"); !errors.Is(err, ErrDataInUse) {
		t.Fatal(err)
	}
	if err := s.DeleteTemplateData(ctx, "displays", builtinDisplayID, "", "", "root"); !errors.Is(err, ErrBuiltinTemplate) {
		t.Fatal(err)
	}
	for kind, id := range map[string]string{"fingerprints": fp.ID, "displays": dp.ID} {
		if err := s.DeleteTemplateData(ctx, kind, id, "", "", "root"); err != nil {
			t.Fatal(err)
		}
	}
	remaining, err := s.TemplateSources()
	if err != nil || len(remaining.Fingerprints) != 4 || len(remaining.Displays) != 2 {
		t.Fatal(remaining, err)
	}
	after, _ := os.ReadFile(filepath.Join(root, "templates/fingerprints", fp.ID+".json"))
	if string(after) != string(raw) {
		t.Fatal("source bytes changed")
	}
	if _, err := s.CreateTemplateCombination(ctx, "root", fp.ID, dp.ID, sources.GenerationTargets[0].BrowserTemplateID); err == nil {
		t.Fatal("deleted source selectable")
	}
	req := jobRequest()
	req.Templates = &TemplateSourceRef{FingerprintID: fp.ID, DisplayID: dp.ID}
	if _, err := s.CreateEnvironmentJob(ctx, "root", req); !errors.Is(err, ErrDataDeleted) {
		t.Fatal(err)
	}
	jobs, err := s.EnvironmentJobs()
	if err != nil || len(jobs) != 1 || jobs[0].Status != "queued" {
		t.Fatal(jobs, err)
	}
	// Immutable deletion survives a new service reading the same spool.
	reopened, _ := jobService(t)
	reopened.jobSpool = root
	reopened.templateCatalog = generationCatalog()
	remaining, err = reopened.TemplateSources()
	if err != nil || len(remaining.Fingerprints) != 4 {
		t.Fatal(remaining, err)
	}
	if err := reopened.DeleteTemplateData(ctx, "fingerprints", fp.ID, "", "", "root"); err != nil {
		t.Fatal(err)
	}
	// Corrupted or symlinked tombstones never silently restore choices.
	marker := filepath.Join(root, "templates/deleted", deletionName("fingerprints", []string{fp.ID}))
	if err := os.WriteFile(marker, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := reopened.TemplateSources(); err == nil {
		t.Fatal("invalid tombstone accepted")
	}
}

func TestDeleteCombinationRefusesBindingAndRejectsStaleSelection(t *testing.T) {
	ctx := context.Background()
	s := templateService(t, r7dArtifact())
	s.jobSpool = t.TempDir()
	if err := os.Chmod(s.jobSpool, 0700); err != nil {
		t.Fatal(err)
	}
	combo := [3]string{"camoufox-linux", "env-r7d", "fixed-1920"}
	record := s.Records()[0]
	bound := record
	bound.BrowserTemplateID = combo[0]
	bound.EnvironmentArtifactID = combo[1]
	bound.DisplayTemplateID = combo[2]
	s.directory.mu.Lock()
	s.directory.records[record.ID] = bound
	s.directory.mu.Unlock()
	if err := s.DeleteTemplateData(ctx, "combinations", combo[1], combo[0], combo[2], "root"); !errors.Is(err, ErrDataReferenced) {
		t.Fatal(err)
	}
	s.directory.mu.Lock()
	s.directory.records[record.ID] = record
	s.directory.mu.Unlock()
	if err := s.DeleteTemplateData(ctx, "combinations", combo[1], combo[0], combo[2], "root"); err != nil {
		t.Fatal(err)
	}
	choices, err := s.CompatibleTemplates(ctx)
	if err != nil || len(choices) != 0 {
		t.Fatal(choices, err)
	}
	if _, err := s.templateAllowsNewBrowser(ctx, combo[0], combo[1], combo[2]); !errors.Is(err, ErrDataDeleted) {
		t.Fatal(err)
	}
	if _, err := s.ApplyBrowserTemplate(ctx, record.ID, record.Revision, combo[0], combo[1], combo[2], "root", "stale-form"); !errors.Is(err, ErrDataDeleted) {
		t.Fatal(err)
	}
	if _, _, err := s.resolveTemplateBinding(ctx, combo[0], combo[1], combo[2]); err != nil {
		t.Fatal("evidence unavailable", err)
	}
}

func TestDeleteFinishedJobHidesOnlyRecordAndKeepsIndirectReferenceChecks(t *testing.T) {
	ctx := context.Background()
	s, root := jobService(t)
	job, err := s.CreateEnvironmentJob(ctx, "root", jobRequest())
	if err != nil {
		t.Fatal(err)
	}
	statusDir := filepath.Join(root, "status")
	if err := os.Mkdir(statusDir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := writeNewTemplate(filepath.Join(statusDir, job.ID+".json"), environmentJobStatusFile{Version: 1, JobID: job.ID, Status: "failed"}); err != nil {
		t.Fatal(err)
	}
	if err := s.DeleteTemplateData(ctx, "jobs", job.ID, "", "", "root"); err != nil {
		t.Fatal(err)
	}
	jobs, err := s.EnvironmentJobs()
	if err != nil || len(jobs) != 0 {
		t.Fatal(jobs, err)
	}
	reopened, _ := jobService(t)
	reopened.jobSpool = root
	for i := 0; i < 3; i++ {
		list, err := reopened.EnvironmentJobs()
		if err != nil || len(list) != 0 {
			t.Fatalf("deleted job returned after reload: %v %v", list, err)
		}
	}
	if err := reopened.DeleteTemplateData(ctx, "jobs", job.ID, "", "", "root"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "queue", job.ID+".json")); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(statusDir, job.ID+".json")); err != nil {
		t.Fatal(err)
	}
	if err := s.DeleteTemplateData(ctx, "jobs", "../outside", "", "", "root"); err == nil {
		t.Fatal("unsafe id")
	}
	if err := s.DeleteTemplateData(ctx, "jobs", job.ID, "", "", "invalid/actor"); err == nil {
		t.Fatal("invalid actor")
	}
}

func TestSourceReferenceScanIncludesHiddenJobsBeyondListingLimit(t *testing.T) {
	ctx := context.Background()
	s, root := jobService(t)
	s.templateCatalog = generationCatalog()
	fp, err := s.CreateFingerprintTemplate(ctx, FingerprintTemplate{Label: "QA", Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC"})
	if err != nil {
		t.Fatal(err)
	}
	sources, _ := s.TemplateSources()
	job, err := s.CreateTemplateCombination(ctx, "root", fp.ID, builtinDisplayID, sources.GenerationTargets[0].BrowserTemplateID)
	if err != nil {
		t.Fatal(err)
	}
	var req environmentJobRequestFile
	if err := readPrivateJSON(filepath.Join(root, "queue", job.ID+".json"), 64<<10, &req); err != nil {
		t.Fatal(err)
	}
	if err := s.markDataDeleted("jobs", "root", job.ID); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 102; i++ {
		other := req
		other.JobID = fmt.Sprintf("job-%016x", i)
		other.Spec.ID = fmt.Sprintf("env-custom-%016x", i)
		other.Templates = nil
		if err := writeNewTemplate(filepath.Join(root, "queue", other.JobID+".json"), other); err != nil {
			t.Fatal(err)
		}
	}
	list, err := s.EnvironmentJobs()
	if err != nil || len(list) != 100 {
		t.Fatal(len(list), err)
	}
	record := s.Records()[0]
	record.EnvironmentArtifactID = job.EnvironmentID
	s.directory.mu.Lock()
	s.directory.records[record.ID] = record
	s.directory.mu.Unlock()
	if err := s.DeleteTemplateData(ctx, "fingerprints", fp.ID, "", "", "root"); !errors.Is(err, ErrDataReferenced) {
		t.Fatal("lost hidden indirect reference", err)
	}
}
