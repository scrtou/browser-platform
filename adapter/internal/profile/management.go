package profile

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

var (
	ErrArtifactUnavailable   = errors.New("accepted environment artifact is unavailable")
	ErrInvalidNetworkMode    = errors.New("browser network mode must be direct or proxy_required")
	ErrManagedPolicyRequired = errors.New("managed DIRECT or proxy mode requires an immutable network policy")
	ErrLaunchPlanInvalid     = errors.New("launch plan is invalid, expired, or already used")
	ErrLaunchPlanRevision    = errors.New("launch plan no longer matches the browser revision")
)

// launchPlan is intentionally memory-only. It is a short-lived capability,
// not a recovery record; a process restart invalidates all plans and the
// fixed entry page issues a new one.
type launchPlan struct {
	Subject   string
	ProfileID string
	Revision  int
	Token     string
	ExpiresAt time.Time
	Used      bool
}

type LaunchPlan struct {
	Token     string    `json:"token"`
	ProfileID string    `json:"profile_id"`
	Revision  int       `json:"revision"`
	ExpiresAt time.Time `json:"expires_at"`
}

type EnvironmentArtifactSummary struct {
	ID     string `json:"id"`
	SHA256 string `json:"sha256"`
	Source string `json:"source"`
	Status string `json:"status"`
}

func (s *Service) EnvironmentArtifacts(ctx context.Context) ([]EnvironmentArtifactSummary, error) {
	if s.catalog == nil {
		return nil, ErrArtifactUnavailable
	}
	artifacts, err := s.catalog.List(ctx)
	if err != nil {
		return nil, err
	}
	result := make([]EnvironmentArtifactSummary, 0, len(artifacts))
	for _, artifact := range artifacts {
		if validAcceptedArtifact(artifact) {
			result = append(result, EnvironmentArtifactSummary{ID: artifact.ID, SHA256: artifact.SHA256, Source: artifact.Source, Status: artifact.Status})
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

func (s *Service) IssueLaunchPlan(ctx context.Context, subject, profileID string) (LaunchPlan, error) {
	if err := ctx.Err(); err != nil {
		return LaunchPlan{}, err
	}
	record, ok := s.record(profileID)
	if !ok {
		return LaunchPlan{}, ErrProfileNotFound
	}
	if record.Status != RecordReady {
		return LaunchPlan{}, ErrBrowserCreating
	}
	if strings.TrimSpace(subject) == "" {
		return LaunchPlan{}, ErrLaunchPlanInvalid
	}
	token, err := randomID()
	if err != nil {
		return LaunchPlan{}, err
	}
	plan := launchPlan{Subject: subject, ProfileID: profileID, Revision: record.Revision, Token: token, ExpiresAt: s.now().UTC().Add(90 * time.Second)}
	s.plansMu.Lock()
	if s.plans == nil {
		s.plans = make(map[string]launchPlan)
	}
	s.plans[token] = plan
	s.plansMu.Unlock()
	return LaunchPlan{Token: token, ProfileID: profileID, Revision: record.Revision, ExpiresAt: plan.ExpiresAt}, nil
}

func (s *Service) EnsureWithLaunchPlan(ctx context.Context, subject, profileID, token string) (sealskin.Session, error) {
	if err := s.consumeLaunchPlan(subject, profileID, token); err != nil {
		return sealskin.Session{}, err
	}
	return s.Ensure(ctx, profileID)
}

func (s *Service) consumeLaunchPlan(subject, profileID, token string) error {
	s.plansMu.Lock()
	defer s.plansMu.Unlock()
	plan, ok := s.plans[token]
	if !ok || plan.Used || plan.Subject != subject || plan.ProfileID != profileID || !s.now().UTC().Before(plan.ExpiresAt) {
		return ErrLaunchPlanInvalid
	}
	record, ok := s.record(profileID)
	if !ok {
		return ErrProfileNotFound
	}
	if record.Revision != plan.Revision {
		return ErrLaunchPlanRevision
	}
	plan.Used = true
	s.plans[token] = plan
	return nil
}

func (s *Service) CreateBrowser(ctx context.Context, request CreateBrowserRequest, actor, idempotencyKey string) (Record, error) {
	if s.directoryPath == "" {
		return Record{}, ErrDirectoryReadOnly
	}
	if s.admin == nil {
		return Record{}, ErrAdminUnavailable
	}
	if s.catalog == nil {
		return Record{}, ErrArtifactUnavailable
	}
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if strings.TrimSpace(actor) == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return Record{}, errors.New("browser creation requires an actor and durable idempotency key")
	}
	artifactID := strings.TrimSpace(request.EnvironmentArtifactID)
	artifact, err := s.catalog.Accepted(ctx, artifactID)
	if err != nil {
		return Record{}, fmt.Errorf("%w: %v", ErrArtifactUnavailable, err)
	}
	if artifact.ID != artifactID || !validAcceptedArtifact(artifact) {
		return Record{}, ErrArtifactUnavailable
	}
	mode := strings.TrimSpace(request.NetworkMode)
	if mode != "direct" && mode != "proxy_required" {
		return Record{}, ErrInvalidNetworkMode
	}
	if !validNetworkReference(request.NetworkPolicyID, request.NetworkPolicySHA256) {
		return Record{}, ErrManagedPolicyRequired
	}
	idDigest := sha256.Sum256([]byte(actor + "\x00" + idempotencyKey))
	id := "browser-" + hex.EncodeToString(idDigest[:])[:12]
	appID := "app-" + id[8:]
	homeName := id + "-home"
	definition := Definition{ID: id, Label: strings.TrimSpace(request.Label), ApplicationID: appID, HomeName: homeName,
		StartURL: strings.TrimSpace(request.StartURL), Language: request.Language, Timezone: request.Timezone, WaylandMode: request.WaylandMode,
		NetworkMode: mode, NetworkPolicyID: request.NetworkPolicyID, NetworkPolicySHA256: request.NetworkPolicySHA256,
		EnvironmentArtifactID: artifact.ID, EnvironmentArtifactSHA256: artifact.SHA256, EnvironmentSource: artifact.Source,
		RequiredRuntimeCapabilities: cloneCapabilities(artifact.RequiredRuntimeCapabilities)}
	if err := validateDefinition(definition); err != nil {
		return Record{}, err
	}
	record := Record{Definition: definition, Revision: 1, UpdatedAt: s.now().UTC(), UpdatedBy: actor, Status: RecordCreating}
	if existing, exists := s.directory.record(id); exists {
		if existing.Status == RecordReady && sameCreatedBrowser(existing.Definition, definition) {
			return existing, nil
		}
		if existing.Status != RecordCreating || !sameCreatedBrowser(existing.Definition, definition) {
			return Record{}, ErrRevisionMismatch
		}
		record = existing
	} else if err := s.directory.add(record); err != nil {
		return Record{}, err
	}
	app, err := applicationForBrowser(artifact, definition)
	if err != nil {
		return record, err
	}
	if err := s.ensureHome(ctx, homeName); err != nil {
		return record, fmt.Errorf("create browser Home: %w", err)
	}
	if err := s.admin.InstallApp(ctx, app, "install-"+idempotencyKey); err != nil {
		return record, fmt.Errorf("install browser application: %w", err)
	}
	ready, err := s.directory.status(id, RecordReady, actor)
	if err != nil {
		return record, err
	}
	return ready, nil
}

func sameCreatedBrowser(left, right Definition) bool {
	return left.ID == right.ID && left.Label == right.Label && left.ApplicationID == right.ApplicationID && left.HomeName == right.HomeName &&
		left.StartURL == right.StartURL && left.NetworkMode == right.NetworkMode && left.NetworkPolicyID == right.NetworkPolicyID &&
		left.NetworkPolicySHA256 == right.NetworkPolicySHA256 && left.EnvironmentArtifactID == right.EnvironmentArtifactID &&
		left.EnvironmentArtifactSHA256 == right.EnvironmentArtifactSHA256 && left.EnvironmentSource == right.EnvironmentSource
}

func (s *Service) DeleteBrowser(ctx context.Context, profileID, actor, idempotencyKey string) error {
	if s.admin == nil {
		return ErrAdminUnavailable
	}
	if s.homeArchiver == nil {
		return ErrAdminUnavailable
	}
	actor = strings.TrimSpace(actor)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return errors.New("browser deletion requires an actor and durable idempotency key")
	}
	record, ok := s.directory.record(profileID)
	if !ok {
		return ErrProfileNotFound
	}
	if record.Status == RecordCreating {
		return ErrBrowserCreating
	}
	if record.Status != RecordDeleting {
		result, err := s.Stop(ctx, profileID)
		if err != nil {
			return err
		}
		if result.Status != state.StatusStopped || result.Workers != 0 || result.Resources != 0 {
			return ErrBrowserBusy
		}
		updated, err := s.directory.status(profileID, RecordDeleting, actor)
		if err != nil {
			return err
		}
		record = updated
	}
	digest := sha256.Sum256([]byte(profileID))
	prefix := profileID
	if len(prefix) > 48 {
		prefix = prefix[:48]
	}
	archiveName := "archive-" + prefix + "-" + record.UpdatedAt.UTC().Format("20060102T150405Z") + "-" + hex.EncodeToString(digest[:])[:8]
	// The deterministic archive name is stable for retries and carries no
	// credentials or Session material.
	archive := sealskin.ArchiveHomeRequest{ArchiveName: archiveName, ProfileID: record.ID, ProfileRevision: record.Revision,
		ApplicationID: record.ApplicationID, EnvironmentArtifactID: record.EnvironmentArtifactID, Actor: actor}
	if err := s.homeArchiver.ArchiveHomeDirectory(ctx, record.HomeName, archive, idempotencyKey+"-home"); err != nil {
		return fmt.Errorf("archive browser Home: %w", err)
	}
	if err := s.admin.DeleteInstalledApp(ctx, record.ApplicationID, idempotencyKey+"-app"); err != nil {
		return fmt.Errorf("delete browser application: %w", err)
	}
	if err := s.store.Update(profileID, func(*state.Binding) (*state.Binding, error) { return nil, nil }); err != nil {
		return err
	}
	_, err := s.directory.status(profileID, RecordDeleted, actor)
	return err
}

func validDigest(value string) bool {
	if len(value) != 64 || strings.ToLower(value) != value {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func validAcceptedArtifact(artifact EnvironmentArtifact) bool {
	return artifact.ID != "" && artifact.Status == "accepted" && artifact.Source == "frozen" && validDigest(artifact.SHA256) &&
		validDigest(artifact.AcceptanceSHA256) && strings.HasPrefix(artifact.Image, "sha256:") && validDigest(strings.TrimPrefix(artifact.Image, "sha256:")) &&
		len(artifact.Application) != 0
}

func applicationForBrowser(artifact EnvironmentArtifact, definition Definition) (map[string]any, error) {
	raw, err := json.Marshal(artifact.Application)
	if err != nil {
		return nil, ErrArtifactUnavailable
	}
	var app map[string]any
	if json.Unmarshal(raw, &app) != nil {
		return nil, ErrArtifactUnavailable
	}
	provider, ok := app["provider_config"].(map[string]any)
	if !ok || provider["image"] != artifact.Image {
		return nil, ErrArtifactUnavailable
	}
	app["id"], app["name"] = definition.ApplicationID, definition.DisplayLabel()
	provider["network_policy_id"], provider["network_policy_sha256"] = definition.NetworkPolicyID, definition.NetworkPolicySHA256
	if overrides, ok := provider["docker_overrides"].(map[string]any); ok {
		if labels, ok := overrides["labels"].(map[string]any); ok {
			labels["browser-platform.application"] = definition.ApplicationID
			labels["browser-platform.environment"] = artifact.ID
		}
	}
	return app, nil
}

func validNetworkReference(id, digest string) bool {
	return id != "" && validDigest(digest) && sealskin.ValidNetworkPolicyReference(id, digest)
}

type StaticEnvironmentCatalog map[string]EnvironmentArtifact

func (c StaticEnvironmentCatalog) Accepted(_ context.Context, id string) (EnvironmentArtifact, error) {
	artifact, ok := c[id]
	if !ok {
		return EnvironmentArtifact{}, ErrArtifactUnavailable
	}
	return artifact, nil
}

func (c StaticEnvironmentCatalog) List(_ context.Context) ([]EnvironmentArtifact, error) {
	result := make([]EnvironmentArtifact, 0, len(c))
	for _, artifact := range c {
		result = append(result, artifact)
	}
	return result, nil
}

type fileEnvironmentCatalog struct {
	Version   int                   `json:"version"`
	Artifacts []EnvironmentArtifact `json:"artifacts"`
}

type FileEnvironmentCatalog struct{ path string }

func NewFileEnvironmentCatalog(path string) (*FileEnvironmentCatalog, error) {
	if strings.TrimSpace(path) == "" {
		return nil, errors.New("environment catalog path is required")
	}
	return &FileEnvironmentCatalog{path: filepath.Clean(path)}, nil
}

func (c *FileEnvironmentCatalog) Accepted(_ context.Context, id string) (EnvironmentArtifact, error) {
	catalog, err := c.read()
	if err != nil {
		return EnvironmentArtifact{}, err
	}
	for _, artifact := range catalog.Artifacts {
		if artifact.ID == id && validAcceptedArtifact(artifact) {
			return artifact, nil
		}
	}
	return EnvironmentArtifact{}, ErrArtifactUnavailable
}

func (c *FileEnvironmentCatalog) List(_ context.Context) ([]EnvironmentArtifact, error) {
	catalog, err := c.read()
	if err != nil {
		return nil, err
	}
	return append([]EnvironmentArtifact(nil), catalog.Artifacts...), nil
}

func (c *FileEnvironmentCatalog) read() (fileEnvironmentCatalog, error) {
	file, err := os.Open(c.path)
	if err != nil {
		return fileEnvironmentCatalog{}, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return fileEnvironmentCatalog{}, ErrArtifactUnavailable
	}
	var catalog fileEnvironmentCatalog
	decoder := json.NewDecoder(io.LimitReader(file, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&catalog); err != nil || catalog.Version != 1 {
		return fileEnvironmentCatalog{}, ErrArtifactUnavailable
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return fileEnvironmentCatalog{}, ErrArtifactUnavailable
	}
	return catalog, nil
}
