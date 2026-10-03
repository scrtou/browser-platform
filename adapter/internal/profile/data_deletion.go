package profile

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"time"
)

var (
	ErrDataDeleted     = errors.New("management data has been deleted")
	ErrDataInUse       = errors.New("management data is used by an unfinished operation")
	ErrDataReferenced  = errors.New("fingerprint data is referenced by a browser or rollback history")
	ErrBuiltinTemplate = errors.New("built-in template cannot be deleted")
)

type dataDeletion struct {
	Version int      `json:"version"`
	Kind    string   `json:"kind"`
	IDs     []string `json:"ids"`
	Actor   string   `json:"actor"`
	At      string   `json:"at"`
}

func deletionName(kind string, ids []string) string {
	raw, _ := json.Marshal(append([]string{kind}, ids...))
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]) + ".json"
}

// Immutable sidecars keep source bytes, acceptance evidence and bindings intact.
func (s *Service) dataDeleted(kind string, ids ...string) (bool, error) {
	if s.jobSpool == "" {
		return false, nil
	}
	if err := s.spoolReady(); err != nil {
		return false, err
	}
	root := filepath.Join(s.jobSpool, "templates")
	for _, p := range []string{root, filepath.Join(root, "deleted")} {
		info, err := os.Lstat(p)
		if os.IsNotExist(err) {
			return false, nil
		}
		if err != nil {
			return false, err
		}
		if !info.IsDir() || info.Mode().Perm()&0077 != 0 {
			return false, ErrEnvironmentJobsUnavailable
		}
	}
	var v dataDeletion
	err := readPrivateJSON(filepath.Join(root, "deleted", deletionName(kind, ids)), 64<<10, &v)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if v.Version != 1 || v.Kind != kind || len(v.IDs) != len(ids) || !validPolicyName(v.Actor) {
		return false, ErrEnvironmentJobInvalid
	}
	for i := range ids {
		if ids[i] != v.IDs[i] {
			return false, ErrEnvironmentJobInvalid
		}
	}
	if _, err := time.Parse(time.RFC3339Nano, v.At); err != nil {
		return false, ErrEnvironmentJobInvalid
	}
	return true, nil
}
func (s *Service) markDataDeleted(kind, actor string, ids ...string) error {
	root, err := s.templateSourceDirectory("deleted")
	if err != nil {
		return err
	}
	return writeNewTemplate(filepath.Join(root, deletionName(kind, ids)), dataDeletion{1, kind, ids, actor, s.now().UTC().Format(time.RFC3339Nano)})
}
func (s *Service) selectableCombination(browser, artifact, display string) error {
	deleted, err := s.dataDeleted("combinations", browser, artifact, display)
	if err != nil {
		return err
	}
	if deleted {
		return ErrDataDeleted
	}
	return nil
}

// DeleteTemplateData removes choices/finished list entries, never their backing
// evidence. Existing browser starts and explicit historical rollback still work.
func (s *Service) DeleteTemplateData(ctx context.Context, kind, id, browser, display, actor string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := s.spoolReady(); err != nil {
		return err
	}
	if !validPolicyName(actor) || !validPolicyName(id) {
		return ErrEnvironmentJobInvalid
	}
	ids := []string{id}
	selectionLock := s.profileLock("__template_selections")
	selectionLock.Lock()
	defer selectionLock.Unlock()
	lockName := "__template_sources"
	if kind == "combinations" {
		if !validPolicyName(browser) || !validPolicyName(display) {
			return ErrEnvironmentJobInvalid
		}
		ids = []string{browser, id, display}
	}
	lock := s.profileLock(lockName)
	lock.Lock()
	defer lock.Unlock()
	if builtinSource(kind, id) {
		return ErrBuiltinTemplate
	}
	if kind == "combinations" {
		if s.templateCatalog == nil {
			return ErrTemplateCatalogUnavailable
		}
		catalog, err := s.templateCatalog.Read(ctx)
		if err != nil {
			return err
		}
		for _, combo := range catalog.Compatibility {
			if combo.Builtin && combo.BrowserTemplateID == browser && combo.EnvironmentArtifactID == id && combo.DisplayTemplateID == display {
				return ErrBuiltinTemplate
			}
		}
	}
	deleted, err := s.dataDeleted(kind, ids...)
	if err != nil {
		return err
	}
	if deleted {
		return nil
	}
	if err := s.requireUnreferencedData(kind, id, browser, display); err != nil {
		return err
	}
	switch kind {
	case "fingerprints", "displays":
		sources, err := s.TemplateSources()
		if err != nil {
			return err
		}
		found := false
		if kind == "fingerprints" {
			for _, v := range sources.Fingerprints {
				found = found || v.ID == id
			}
		} else {
			for _, v := range sources.Displays {
				found = found || v.ID == id
			}
		}
		if !found {
			return ErrEnvironmentJobNotFound
		}
	case "jobs":
		job, err := s.EnvironmentJob(id)
		if err != nil {
			return err
		}
		if job.Status != "accepted" && job.Status != "failed" {
			return ErrDataInUse
		}
	case "combinations":
		if _, _, err := s.resolveTemplateBinding(ctx, browser, id, display); err != nil {
			return err
		}

	default:
		return ErrEnvironmentJobInvalid
	}
	return s.markDataDeleted(kind, actor, ids...)
}

func (c *networkProfileCatalog) revisionDeleted(id string, revision int) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	for _, event := range c.audit {
		if event.ID == id && event.Revision == revision && event.Action == "revision_deleted" {
			return true
		}
	}
	return false
}

// DeleteNetworkProfile keeps version numbers and audit history, and hides a
// revision only after credential revocation completes. Bind and create share
// networkProfilesMu, so no accepted binding can race into the deletion window.
func (s *Service) DeleteNetworkProfile(ctx context.Context, id string, revision int, actor, key string) error {
	if err := s.networkProfilesReady(); err != nil {
		return err
	}
	actor, key = strings.TrimSpace(actor), strings.TrimSpace(key)
	if actor == "" || key == "" || len(key) > 128 {
		return ErrNetworkProfileInvalid
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	if _, _, replay, err := s.networkProfiles.mutationByIdempotency(id, revision, actor, key, "revision_deleted"); err != nil {
		return err
	} else if replay {
		return nil
	}
	p, current, err := s.networkProfiles.getRevision(id, revision)
	if err != nil {
		return err
	}
	if s.networkRevisionSummary(p, current).References != 0 {
		return ErrNetworkProfileReferenced
	}
	if current.Auth != "none" && current.Status != NetworkRevisionRevoked {
		if err := s.revokeNetworkSecret(ctx, id, revision); err != nil {
			return err
		}
	}
	_, err = s.networkProfiles.mutate(id, revision, actor, key, "revision_deleted", func(v *networkProfileRevisionRecord) error {
		v.Status = NetworkRevisionRevoked
		v.DraftID = ""
		v.UsernameSecretRef = ""
		v.PasswordSecretRef = ""
		return nil
	})
	return err
}

// Read every retained job request, including entries hidden from the UI and
// older than the listing limit. Sources refer indirectly through their output.
func (s *Service) requireUnreferencedData(kind, id, browser, display string) error {
	artifacts := map[string]bool{}
	provenance := map[string]bool{}
	switch kind {
	case "combinations":
		artifacts[id] = true
	case "jobs":
		if !jobIDForm.MatchString(id) {
			return ErrEnvironmentJobInvalid
		}
		artifacts["env-custom-"+strings.TrimPrefix(id, "job-")] = true
	case "fingerprints", "displays":
		entries, err := os.ReadDir(filepath.Join(s.jobSpool, "queue"))
		if err != nil && !os.IsNotExist(err) {
			return err
		}
		for _, entry := range entries {
			jobID := strings.TrimSuffix(entry.Name(), ".json")
			if !jobIDForm.MatchString(jobID) || entry.Name() == jobID {
				continue
			}
			var req environmentJobRequestFile
			if err := readPrivateJSON(filepath.Join(s.jobSpool, "queue", entry.Name()), 64<<10, &req); err != nil {
				return err
			}
			if (req.Version != 1 && req.Version != 2 && req.Version != 3) || req.JobID != jobID || req.Spec.ID != "env-custom-"+strings.TrimPrefix(jobID, "job-") {
				return ErrEnvironmentJobInvalid
			}
			provenance[req.Spec.ID] = true
			if req.Templates != nil && ((kind == "fingerprints" && req.Templates.FingerprintID == id) || (kind == "displays" && req.Templates.DisplayID == id)) {
				artifacts[req.Spec.ID] = true
			}
		}
	default:
		return ErrEnvironmentJobInvalid
	}
	matches := func(b, a, d string) bool {
		return artifacts[a] && (kind != "combinations" || (b == browser && d == display))
	}
	for _, r := range s.Records() {
		if kind == "fingerprints" || kind == "displays" {
			ids := []string{r.EnvironmentArtifactID}
			if r.PendingTemplate != nil {
				ids = append(ids, r.PendingTemplate.Target.EnvironmentArtifactID)
			}
			for _, h := range r.TemplateHistory {
				ids = append(ids, h.Binding.EnvironmentArtifactID)
			}
			for _, artifactID := range ids {
				if strings.HasPrefix(artifactID, "env-custom-") && !provenance[artifactID] {
					return ErrEnvironmentJobsUnavailable
				}
			}
		}
		if matches(r.BrowserTemplateID, r.EnvironmentArtifactID, r.DisplayTemplateID) {
			return ErrDataReferenced
		}
		if p := r.PendingTemplate; p != nil && matches(p.Target.BrowserTemplateID, p.Target.EnvironmentArtifactID, p.Target.DisplayTemplateID) {
			return ErrDataReferenced
		}
		for _, h := range r.TemplateHistory {
			if matches(h.Binding.BrowserTemplateID, h.Binding.EnvironmentArtifactID, h.Binding.DisplayTemplateID) {
				return ErrDataReferenced
			}
		}
	}
	return nil
}
