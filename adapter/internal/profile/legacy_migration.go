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
	"strings"

	"browser-platform/adapter/internal/sealskin"
)

var ErrLegacyMigration = errors.New("approved legacy network migration is unavailable or no longer matches")

// LegacyNetworkMigration is operator-owned input, never accepted from a web
// form. The source is the complete resolved application from the encrypted API,
// not its partial installed_apps.yml record. Only image and policy may change.
type LegacyNetworkMigration struct {
	ID                string         `json:"id"`
	Status            string         `json:"status"`
	SourceRevision    int            `json:"source_revision"`
	SourceDefinition  Definition     `json:"source_definition"`
	SourceApplication map[string]any `json:"source_application"`
	TargetImage       string         `json:"target_image"`
	AcceptanceSHA256  string         `json:"acceptance_sha256"`
	BackupSHA256      string         `json:"backup_sha256"`
	RestoreSHA256     string         `json:"restore_sha256"`
}

// LegacyMigrationState contains only binding/audit metadata. Full applications
// and recovery evidence remain in the private operator catalog.
type LegacyMigrationState struct {
	Direction    string `json:"direction,omitempty"`
	ID           string `json:"id"`
	PlanSHA256   string `json:"plan_sha256"`
	BaseRevision int    `json:"base_revision"`
	Actor        string `json:"actor"`
	Key          string `json:"key"`
	PolicyID     string `json:"policy_id,omitempty"`
	PolicySHA256 string `json:"policy_sha256,omitempty"`
}

type LegacyMigrationSummary struct {
	ID       string
	Revision int
	Rollback bool
}

type installedAppReader interface {
	InstalledAppDefinition(context.Context, string) (map[string]any, error)
}

func WithLegacyNetworkMigrations(path string) Option {
	return func(s *Service) { s.legacyMigrationCatalog = path }
}

func migrationDigest(value any) string {
	encoded, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:])
}

func validateLegacyMigration(plan LegacyNetworkMigration) error {
	d := plan.SourceDefinition
	provider, ok := plan.SourceApplication["provider_config"].(map[string]any)
	image, _ := provider["image"].(string)
	if !validNetworkProfileID(plan.ID) || plan.Status != "accepted" || plan.SourceRevision < 1 ||
		validateDefinition(d) != nil || !d.Disabled || !d.WaylandMode ||
		(d.NetworkMode != "" && d.NetworkMode != "legacy") || d.NetworkPolicyID != "" || d.NetworkPolicySHA256 != "" ||
		d.NetworkProfileID != "" || d.NetworkProfileRevision != 0 || d.NetworkBindingKey != "" ||
		d.ProxySecretVersion != 0 || d.ProxyUsernameSecretRef != "" || d.ProxyPasswordSecretRef != "" || d.ProxyUpstream != "" ||
		d.EnvironmentArtifactID != "" || d.BrowserTemplateID != "" ||
		d.RequiredRuntimeCapabilities["browser_shutdown_version"] != 1 || d.RequiredRuntimeCapabilities["session_auth_version"] != 1 ||
		!ok || plan.SourceApplication["id"] != d.ApplicationID ||
		!strings.HasPrefix(image, "sha256:") || !validDigest(strings.TrimPrefix(image, "sha256:")) ||
		!strings.HasPrefix(plan.TargetImage, "sha256:") || !validDigest(strings.TrimPrefix(plan.TargetImage, "sha256:")) || image == plan.TargetImage ||
		!validDigest(plan.AcceptanceSHA256) || !validDigest(plan.BackupSHA256) || !validDigest(plan.RestoreSHA256) {
		return ErrLegacyMigration
	}
	for _, key := range []string{"network_policy_id", "network_policy_sha256"} {
		if value := provider[key]; value != nil && value != "" {
			return ErrLegacyMigration
		}
	}
	for _, key := range []string{"image_sha", "last_checked_at", "pull_status", "overrides"} {
		if _, exists := plan.SourceApplication[key]; exists {
			return ErrLegacyMigration
		}
	}
	return nil
}

func (s *Service) legacyMigrations() ([]LegacyNetworkMigration, error) {
	if s.legacyMigrationCatalog == "" || s.directoryPath == "" || s.directTemplate == nil || s.runtime == nil {
		return nil, ErrLegacyMigration
	}
	if _, ok := s.admin.(installedAppReader); !ok {
		return nil, ErrLegacyMigration
	}
	info, err := os.Lstat(s.legacyMigrationCatalog)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 || info.Size() > 4<<20 {
		return nil, ErrLegacyMigration
	}
	file, err := os.Open(s.legacyMigrationCatalog)
	if err != nil {
		return nil, ErrLegacyMigration
	}
	defer file.Close()
	var data struct {
		Version    int                      `json:"version"`
		Migrations []LegacyNetworkMigration `json:"migrations"`
	}
	decoder := json.NewDecoder(io.LimitReader(file, 4<<20))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&data) != nil || data.Version != 1 {
		return nil, ErrLegacyMigration
	}
	var trailing any
	if !errors.Is(decoder.Decode(&trailing), io.EOF) {
		return nil, ErrLegacyMigration
	}
	ids, profiles := map[string]bool{}, map[string]bool{}
	for _, plan := range data.Migrations {
		if validateLegacyMigration(plan) != nil || ids[plan.ID] || profiles[plan.SourceDefinition.ID] {
			return nil, ErrLegacyMigration
		}
		ids[plan.ID], profiles[plan.SourceDefinition.ID] = true, true
	}
	return data.Migrations, nil
}

func (s *Service) migrationPlanDigest(plan LegacyNetworkMigration) string {
	return migrationDigest(struct {
		Plan   LegacyNetworkMigration
		Direct *DirectTemplate
	}{plan, s.directTemplate})
}

// LegacyMigration returns only a high-level action for the matching browser.
// A pending operation continues with its original base revision.
func (s *Service) LegacyMigration(profileID string) (LegacyMigrationSummary, bool) {
	plans, err := s.legacyMigrations()
	if err != nil {
		return LegacyMigrationSummary{}, false
	}
	record, ok := s.record(profileID)
	if !ok {
		return LegacyMigrationSummary{}, false
	}
	for _, plan := range plans {
		if plan.SourceDefinition.ID != profileID {
			continue
		}
		if record.PendingMigration != nil && record.PendingMigration.Direction == "rollback" && record.PendingMigration.PlanSHA256 == s.migrationPlanDigest(plan) {
			return LegacyMigrationSummary{ID: plan.ID, Revision: record.PendingMigration.BaseRevision, Rollback: true}, true
		}
		if record.Status == RecordReady && record.Disabled && record.LastMigration != nil && record.LastMigration.Direction == "" && record.LastMigration.PlanSHA256 == s.migrationPlanDigest(plan) && migrationDigest(record.Definition) == migrationDigest(migratedDefinition(plan, *record.LastMigration)) {
			return LegacyMigrationSummary{ID: plan.ID, Revision: record.Revision, Rollback: true}, true
		}
		if migrationDigest(plan.SourceDefinition) != migrationDigest(record.Definition) {
			continue
		}
		if record.Status == RecordReady && record.Revision == plan.SourceRevision ||
			record.Status == RecordMigrating && record.PendingMigration != nil && record.PendingMigration.PlanSHA256 == s.migrationPlanDigest(plan) {
			return LegacyMigrationSummary{ID: plan.ID, Revision: plan.SourceRevision}, true
		}
	}
	return LegacyMigrationSummary{}, false
}

func validateMigrationState(record Record) error {
	if (record.Status == RecordMigrating) != (record.PendingMigration != nil) {
		return ErrLegacyMigration
	}
	for _, item := range []*LegacyMigrationState{record.PendingMigration, record.LastMigration} {
		if item == nil {
			continue
		}
		if !validNetworkProfileID(item.ID) || !validDigest(item.PlanSHA256) || item.BaseRevision < 1 ||
			(item.Direction != "" && item.Direction != "rollback") ||
			item.BaseRevision >= record.Revision || item.Actor == "" || item.Key == "" || len(item.Key) > 128 ||
			!sealskin.ValidNetworkPolicyReference(item.PolicyID, item.PolicySHA256) {
			return ErrLegacyMigration
		}
	}
	if record.LastMigration != nil && !validNetworkReference(record.LastMigration.PolicyID, record.LastMigration.PolicySHA256) {
		return ErrLegacyMigration
	}
	return nil
}

// writeMigration uses optimistic directory locking in addition to the service
// lifecycle lock, so ordinary label/enable updates cannot be silently lost.
func (d *directory) writeMigration(before, after Record, actor string) (Record, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.path == "" {
		return Record{}, ErrDirectoryReadOnly
	}
	current, ok := d.records[before.ID]
	if !ok || current.Revision != before.Revision || migrationDigest(current) != migrationDigest(before) {
		return Record{}, ErrRevisionMismatch
	}
	after.Revision = before.Revision + 1
	after.UpdatedAt, after.UpdatedBy = d.now().UTC(), actor
	if err := validateDefinition(after.Definition); err != nil {
		return Record{}, err
	}
	if err := validateMigrationState(after); err != nil {
		return Record{}, err
	}
	previousRevision := d.revision
	d.records[before.ID], d.revision = after, d.revision+1
	if err := d.writeLocked(); err != nil {
		d.records[before.ID], d.revision = before, previousRevision
		return Record{}, err
	}
	return after, nil
}

func migrationApplication(plan LegacyNetworkMigration, state LegacyMigrationState) map[string]any {
	encoded, _ := json.Marshal(plan.SourceApplication)
	var app map[string]any
	_ = json.Unmarshal(encoded, &app)
	provider := app["provider_config"].(map[string]any)
	provider["image"] = plan.TargetImage
	provider["network_policy_id"], provider["network_policy_sha256"] = state.PolicyID, state.PolicySHA256
	return app
}

// MigrateLegacyNetwork retains the legacy browser/Home and disabled flag. It
// never stops, starts or creates a Home. A durable gate precedes every external
// mutation, and the original request can resume after a process interruption.
func (s *Service) MigrateLegacyNetwork(ctx context.Context, profileID string, revision int, migrationID, actor, key string) (Record, error) {
	actor, key = strings.TrimSpace(actor), strings.TrimSpace(key)
	if actor == "" || key == "" || len(key) > 128 || ctx.Err() != nil {
		return Record{}, ErrLegacyMigration
	}
	plans, err := s.legacyMigrations()
	if err != nil {
		return Record{}, err
	}
	var plan LegacyNetworkMigration
	for _, candidate := range plans {
		if candidate.ID == migrationID && candidate.SourceDefinition.ID == profileID && candidate.SourceRevision == revision {
			plan = candidate
		}
	}
	if plan.ID == "" {
		return Record{}, ErrLegacyMigration
	}
	lock := s.profileLock(profileID)
	lock.Lock()
	defer lock.Unlock()
	record, ok := s.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	wanted := LegacyMigrationState{ID: plan.ID, PlanSHA256: s.migrationPlanDigest(plan), BaseRevision: revision, Actor: actor, Key: key}
	matches := func(actual *LegacyMigrationState) bool {
		return actual != nil && actual.Direction == "" && actual.ID == wanted.ID && actual.PlanSHA256 == wanted.PlanSHA256 &&
			actual.BaseRevision == wanted.BaseRevision && actual.Actor == actor && actual.Key == key
	}
	if record.Status == RecordReady && matches(record.LastMigration) {
		if record.NetworkMode == "direct" && record.NetworkPolicyID == record.LastMigration.PolicyID && record.NetworkPolicySHA256 == record.LastMigration.PolicySHA256 {
			return record, nil
		}
		return Record{}, ErrRevisionMismatch
	}
	if migrationDigest(record.Definition) != migrationDigest(plan.SourceDefinition) ||
		(record.Status != RecordReady && record.Status != RecordMigrating) ||
		(record.Status == RecordReady && record.Revision != revision) ||
		(record.Status == RecordMigrating && !matches(record.PendingMigration)) {
		return Record{}, ErrLegacyMigration
	}
	if err := s.requireStoppedRuntimeLocked(ctx, profileID); err != nil {
		return Record{}, err
	}
	snapshot, err := s.inspectRuntime(ctx, record.HomeName)
	if err != nil {
		return Record{}, err
	}
	if snapshot.NetworkDirectVersion != 1 || snapshot.NetworkRuntimeVersion != 1 || snapshot.NetworkEnforcementVersion != 1 {
		return Record{}, ErrLegacyMigration
	}
	if err := verifyRequiredCapabilities(record.Definition, snapshot); err != nil {
		return Record{}, err
	}
	reader := s.admin.(installedAppReader)
	currentApp, err := reader.InstalledAppDefinition(ctx, record.ApplicationID)
	if err != nil {
		return Record{}, fmt.Errorf("read migration application: %w", err)
	}
	if migrationDigest(currentApp) != migrationDigest(plan.SourceApplication) {
		if record.PendingMigration == nil || !validNetworkReference(record.PendingMigration.PolicyID, record.PendingMigration.PolicySHA256) ||
			migrationDigest(currentApp) != migrationDigest(migrationApplication(plan, *record.PendingMigration)) {
			return Record{}, ErrLegacyMigration
		}
	}
	if record.Status == RecordReady {
		after := record
		after.Status, after.PendingMigration = RecordMigrating, &wanted
		record, err = s.directory.writeMigration(record, after, actor)
		if err != nil {
			return Record{}, err
		}
	}
	if record.PendingMigration.PolicyID == "" {
		policyID := networkPolicyRevisionID(profileID, "migration-"+plan.ID, revision)
		policy := map[string]any{
			"username": s.directTemplate.Owner, "profile_id": profileID, "home_name": record.HomeName, "application_id": record.ApplicationID,
			"mode": "direct", "approved_resolver_id": s.directTemplate.ApprovedResolverID, "approved_resolver_ip": s.directTemplate.ApprovedResolverIP,
			"relay_image": s.directTemplate.RelayImage, "probe_image": s.directTemplate.ProbeImage,
			"upstream_host": "", "upstream_port": 0, "probe_url": s.directTemplate.ProbeURL, "probe_timeout_seconds": s.directTemplate.timeout(),
		}
		appended, appendErr := s.admin.AppendNetworkPolicy(ctx, sealskin.NetworkPolicyAppendRequest{PolicyID: policyID, Policy: policy}, key+"-policy")
		if appendErr != nil {
			return Record{}, fmt.Errorf("append migration policy: %w", appendErr)
		}
		if appended.PolicyID != policyID || !validNetworkReference(appended.PolicyID, appended.PolicySHA256) {
			return Record{}, ErrLegacyMigration
		}
		pending := *record.PendingMigration
		pending.PolicyID, pending.PolicySHA256 = appended.PolicyID, appended.PolicySHA256
		after := record
		after.PendingMigration = &pending
		record, err = s.directory.writeMigration(record, after, actor)
		if err != nil {
			return Record{}, err
		}
	}
	target := migrationApplication(plan, *record.PendingMigration)
	targetDigest := migrationDigest(target)
	if migrationDigest(currentApp) != targetDigest {
		if err := s.admin.ReplaceInstalledApp(ctx, record.ApplicationID, target, key+"-app"); err != nil {
			return Record{}, fmt.Errorf("replace migration application: %w", err)
		}
	}
	observed, err := reader.InstalledAppDefinition(ctx, record.ApplicationID)
	if err != nil || migrationDigest(observed) != targetDigest {
		return Record{}, ErrLegacyMigration
	}
	after := record
	after.NetworkMode, after.NetworkPolicyID, after.NetworkPolicySHA256 = "direct", record.PendingMigration.PolicyID, record.PendingMigration.PolicySHA256
	after.Status, after.LastMigration, after.PendingMigration = RecordReady, record.PendingMigration, nil
	return s.directory.writeMigration(record, after, actor)
}

func migratedDefinition(plan LegacyNetworkMigration, state LegacyMigrationState) Definition {
	d := plan.SourceDefinition
	d.NetworkMode, d.NetworkPolicyID, d.NetworkPolicySHA256 = "direct", state.PolicyID, state.PolicySHA256
	return d
}

// RollbackLegacyNetwork restores the exact approved source app and definition,
// keeping the Home and immutable policy registry. It has its own durable gate
// and request identity; no old journal, account file or Home is restored.
func (s *Service) RollbackLegacyNetwork(ctx context.Context, profileID string, revision int, migrationID, actor, key string) (Record, error) {
	actor, key = strings.TrimSpace(actor), strings.TrimSpace(key)
	if actor == "" || key == "" || len(key) > 128 || ctx.Err() != nil {
		return Record{}, ErrLegacyMigration
	}
	plans, err := s.legacyMigrations()
	if err != nil {
		return Record{}, err
	}
	var plan LegacyNetworkMigration
	for _, p := range plans {
		if p.ID == migrationID && p.SourceDefinition.ID == profileID {
			plan = p
		}
	}
	if plan.ID == "" {
		return Record{}, ErrLegacyMigration
	}
	lock := s.profileLock(profileID)
	lock.Lock()
	defer lock.Unlock()
	r, ok := s.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	planSHA := s.migrationPlanDigest(plan)
	match := func(p *LegacyMigrationState) bool {
		return p != nil && p.Direction == "rollback" && p.ID == migrationID && p.PlanSHA256 == planSHA && p.BaseRevision == revision && p.Actor == actor && p.Key == key
	}
	if r.Status == RecordReady && match(r.LastMigration) {
		if migrationDigest(r.Definition) == migrationDigest(plan.SourceDefinition) {
			return r, nil
		}
		return Record{}, ErrRevisionMismatch
	}
	var pending LegacyMigrationState
	if r.Status == RecordMigrating && match(r.PendingMigration) {
		pending = *r.PendingMigration
	} else if r.Status == RecordReady && r.Revision == revision && r.LastMigration != nil &&
		r.LastMigration.Direction == "" && r.LastMigration.ID == migrationID && r.LastMigration.PlanSHA256 == planSHA {
		pending = *r.LastMigration
		pending.Direction, pending.BaseRevision, pending.Actor, pending.Key = "rollback", revision, actor, key
	} else {
		return Record{}, ErrLegacyMigration
	}
	if migrationDigest(r.Definition) != migrationDigest(migratedDefinition(plan, pending)) {
		return Record{}, ErrLegacyMigration
	}
	if err := s.requireStoppedRuntimeLocked(ctx, profileID); err != nil {
		return Record{}, err
	}
	reader := s.admin.(installedAppReader)
	app, err := reader.InstalledAppDefinition(ctx, r.ApplicationID)
	if err != nil {
		return Record{}, err
	}
	sourceSHA := migrationDigest(plan.SourceApplication)
	if migrationDigest(app) != migrationDigest(migrationApplication(plan, pending)) &&
		!(r.Status == RecordMigrating && migrationDigest(app) == sourceSHA) {
		return Record{}, ErrLegacyMigration
	}
	if r.Status == RecordReady {
		after := r
		after.Status, after.PendingMigration = RecordMigrating, &pending
		r, err = s.directory.writeMigration(r, after, actor)
		if err != nil {
			return Record{}, err
		}
	}
	if migrationDigest(app) != sourceSHA {
		if err := s.admin.ReplaceInstalledApp(ctx, r.ApplicationID, plan.SourceApplication, key+"-rollback-app"); err != nil {
			return Record{}, err
		}
	}
	observed, err := reader.InstalledAppDefinition(ctx, r.ApplicationID)
	if err != nil || migrationDigest(observed) != sourceSHA {
		return Record{}, ErrLegacyMigration
	}
	after := r
	after.Definition, after.Status, after.LastMigration, after.PendingMigration = plan.SourceDefinition, RecordReady, &pending, nil
	return s.directory.writeMigration(r, after, actor)
}
