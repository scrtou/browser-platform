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
	"strconv"
	"strings"
	"sync"
	"time"

	"browser-platform/adapter/internal/sealskin"
)

const networkProfileCatalogVersion = 1

const (
	NetworkRevisionPending  = "pending"
	NetworkRevisionAccepted = "accepted"
	NetworkRevisionDisabled = "disabled"
	NetworkRevisionFailed   = "failed"
	NetworkRevisionRevoked  = "revoked"
)

var (
	ErrNetworkProfilesUnavailable = errors.New("network profile catalog is not configured")
	ErrNetworkProfileInvalid      = errors.New("network profile is invalid")
	ErrNetworkProfileNotFound     = errors.New("network profile revision was not found")
	ErrNetworkProfileNotAccepted  = errors.New("network profile revision is not accepted")
	ErrNetworkProfileReferenced   = errors.New("network profile revision is still referenced by a browser")
	ErrNetworkProfileUnauthorized = errors.New("network profile credentials are not authorized for this browser")
)

// NetworkProfileDraftRequest creates one new immutable upstream revision.
// Credential values are forwarded once to the controller and never persisted
// in the Adapter catalog. A public CA certificate is persisted in the private
// catalog because it is needed to materialize browser-specific policies later.
type NetworkProfileDraftRequest struct {
	ID             string
	Label          string
	IdempotencyKey string
	Protocol       string
	Auth           string
	Host           string
	Port           int
	Username       string
	Password       string
	UpstreamCAPEM  string
}

// NetworkProfileRevisionSummary is the administrator-safe view. It contains
// neither credential references nor CA bytes; References is derived from the
// authoritative browser directory rather than trusted from catalog metadata.
type NetworkProfileRevisionSummary struct {
	ID              string     `json:"id"`
	Label           string     `json:"label"`
	Revision        int        `json:"revision"`
	Status          string     `json:"status"`
	Protocol        string     `json:"protocol"`
	Auth            string     `json:"auth"`
	Host            string     `json:"host"`
	Port            int        `json:"port"`
	HasCA           bool       `json:"has_ca"`
	ProbeCode       string     `json:"probe_code,omitempty"`
	ProbeAt         *time.Time `json:"probe_at,omitempty"`
	UpstreamIP      string     `json:"upstream_ip,omitempty"`
	AllowedProfiles []string   `json:"allowed_profiles,omitempty"`
	References      int        `json:"references"`
	DraftID         string     `json:"draft_id,omitempty"`
	CreatedAt       time.Time  `json:"created_at"`
	AcceptedAt      *time.Time `json:"accepted_at,omitempty"`
	ExpiresAt       *time.Time `json:"expires_at,omitempty"`
	Expired         bool       `json:"expired,omitempty"`
}

type networkProfileRevisionRecord struct {
	Revision          int        `json:"revision"`
	Status            string     `json:"status"`
	Protocol          string     `json:"protocol"`
	Auth              string     `json:"auth"`
	Host              string     `json:"host"`
	Port              int        `json:"port"`
	UpstreamCAPEM     string     `json:"upstream_ca_pem,omitempty"`
	UsernameSecretRef string     `json:"username_secret_ref,omitempty"`
	PasswordSecretRef string     `json:"password_secret_ref,omitempty"`
	AllowedProfiles   []string   `json:"allowed_profiles,omitempty"`
	DraftID           string     `json:"draft_id,omitempty"`
	IdempotencyKey    string     `json:"idempotency_key"`
	ProbeCode         string     `json:"probe_code,omitempty"`
	ProbeAt           *time.Time `json:"probe_at,omitempty"`
	UpstreamIP        string     `json:"upstream_ip,omitempty"`
	CreatedAt         time.Time  `json:"created_at"`
	CreatedBy         string     `json:"created_by"`
	AcceptedAt        *time.Time `json:"accepted_at,omitempty"`
	ExpiresAt         *time.Time `json:"expires_at,omitempty"`
}

type networkProfileRecord struct {
	ID        string                         `json:"id"`
	Label     string                         `json:"label"`
	Revisions []networkProfileRevisionRecord `json:"revisions"`
}

type networkProfileAuditEvent struct {
	At             time.Time `json:"at"`
	Actor          string    `json:"actor"`
	Action         string    `json:"action"`
	ID             string    `json:"id"`
	Revision       int       `json:"revision"`
	IdempotencyKey string    `json:"idempotency_key,omitempty"`
}

type networkProfileCatalogFile struct {
	Version  int                        `json:"version"`
	Revision int                        `json:"revision"`
	Profiles []networkProfileRecord     `json:"profiles"`
	Audit    []networkProfileAuditEvent `json:"audit,omitempty"`
}

type networkProfileCatalog struct {
	mu       sync.RWMutex
	path     string
	revision int
	profiles map[string]networkProfileRecord
	audit    []networkProfileAuditEvent
	now      func() time.Time
}

func newNetworkProfileCatalog(path string, now func() time.Time) (*networkProfileCatalog, error) {
	if strings.TrimSpace(path) == "" {
		return nil, ErrNetworkProfilesUnavailable
	}
	catalog := &networkProfileCatalog{path: filepath.Clean(path), profiles: make(map[string]networkProfileRecord), now: now}
	if err := catalog.open(); err != nil {
		return nil, err
	}
	return catalog, nil
}

func (c *networkProfileCatalog) open() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	file, err := os.Open(c.path)
	if errors.Is(err, os.ErrNotExist) {
		c.revision = 1
		return c.writeLocked()
	}
	if err != nil {
		return fmt.Errorf("open network profile catalog: %w", err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("network profile catalog must be a private regular file")
	}
	var data networkProfileCatalogFile
	decoder := json.NewDecoder(io.LimitReader(file, 4<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&data); err != nil {
		return fmt.Errorf("decode network profile catalog: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("network profile catalog contains trailing data")
	}
	if data.Version != networkProfileCatalogVersion || data.Revision < 1 {
		return errors.New("unsupported network profile catalog")
	}
	profiles := make(map[string]networkProfileRecord, len(data.Profiles))
	for _, profile := range data.Profiles {
		if !validNetworkProfileID(profile.ID) || !validLabel(profile.Label) || profile.Label == "" || len(profile.Revisions) == 0 {
			return fmt.Errorf("invalid network profile %q", profile.ID)
		}
		if _, exists := profiles[profile.ID]; exists {
			return fmt.Errorf("duplicate network profile %q", profile.ID)
		}
		last := 0
		for index := range profile.Revisions {
			revision := &profile.Revisions[index]
			if revision.Revision != last+1 || validateStoredNetworkRevision(*revision) != nil {
				return fmt.Errorf("invalid network profile %q revision %d", profile.ID, revision.Revision)
			}
			last = revision.Revision
		}
		profiles[profile.ID] = profile
	}
	seenKeys := make(map[string]struct{})
	for _, event := range data.Audit {
		if event.At.IsZero() || strings.TrimSpace(event.Actor) == "" || strings.TrimSpace(event.Action) == "" ||
			!validNetworkProfileID(event.ID) || event.Revision < 1 || strings.TrimSpace(event.IdempotencyKey) != event.IdempotencyKey || len(event.IdempotencyKey) > 128 {
			return errors.New("invalid network profile audit event")
		}
		if event.IdempotencyKey != "" {
			key := event.Actor + "\x00" + event.IdempotencyKey
			if _, exists := seenKeys[key]; exists {
				return errors.New("duplicate network profile idempotency key")
			}
			seenKeys[key] = struct{}{}
		}
	}
	c.revision, c.profiles, c.audit = data.Revision, profiles, append([]networkProfileAuditEvent(nil), data.Audit...)
	return nil
}

func (c *networkProfileCatalog) writeLocked() error {
	profiles := make([]networkProfileRecord, 0, len(c.profiles))
	for _, profile := range c.profiles {
		profiles = append(profiles, profile)
	}
	sort.Slice(profiles, func(i, j int) bool { return profiles[i].ID < profiles[j].ID })
	encoded, err := json.MarshalIndent(networkProfileCatalogFile{Version: networkProfileCatalogVersion, Revision: c.revision, Profiles: profiles, Audit: c.audit}, "", "  ")
	if err != nil {
		return fmt.Errorf("encode network profile catalog: %w", err)
	}
	encoded = append(encoded, '\n')
	temp, err := os.CreateTemp(filepath.Dir(c.path), ".network-profiles-*")
	if err != nil {
		return fmt.Errorf("create temporary network profile catalog: %w", err)
	}
	name := temp.Name()
	keep := false
	defer func() {
		temp.Close()
		if !keep {
			_ = os.Remove(name)
		}
	}()
	if err := temp.Chmod(0o600); err != nil {
		return fmt.Errorf("protect network profile catalog: %w", err)
	}
	if _, err := temp.Write(encoded); err != nil {
		return fmt.Errorf("write network profile catalog: %w", err)
	}
	if err := temp.Sync(); err != nil {
		return fmt.Errorf("sync network profile catalog: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close network profile catalog: %w", err)
	}
	if err := os.Rename(name, c.path); err != nil {
		return fmt.Errorf("replace network profile catalog: %w", err)
	}
	keep = true
	if directory, err := os.Open(filepath.Dir(c.path)); err == nil {
		_ = directory.Sync()
		_ = directory.Close()
	}
	return nil
}

func validNetworkProfileID(value string) bool {
	return len(value) <= 64 && validPolicyName(value)
}

func validateStoredNetworkRevision(revision networkProfileRevisionRecord) error {
	if revision.Revision < 1 || revision.CreatedAt.IsZero() || strings.TrimSpace(revision.CreatedBy) == "" ||
		strings.TrimSpace(revision.IdempotencyKey) == "" || len(revision.IdempotencyKey) > 128 {
		return ErrNetworkProfileInvalid
	}
	switch revision.Status {
	case NetworkRevisionPending, NetworkRevisionAccepted, NetworkRevisionDisabled, NetworkRevisionFailed, NetworkRevisionRevoked:
	default:
		return ErrNetworkProfileInvalid
	}
	request := ProxyDraftRequest{Protocol: revision.Protocol, Auth: revision.Auth, Host: revision.Host, Port: revision.Port, UpstreamCAPEM: revision.UpstreamCAPEM}
	if revision.Auth != "none" {
		request.Username, request.Password = "stored", "stored"
	}
	if err := validateProxyDraft(request); err != nil {
		return err
	}
	if (revision.UsernameSecretRef == "") != (revision.PasswordSecretRef == "") {
		return ErrNetworkProfileInvalid
	}
	if revision.UsernameSecretRef != "" && (!sealskin.ValidSecretReference(revision.UsernameSecretRef, "username") || !sealskin.ValidSecretReference(revision.PasswordSecretRef, "password")) {
		return ErrNetworkProfileInvalid
	}
	if revision.Auth != "none" && (revision.Status == NetworkRevisionAccepted || revision.Status == NetworkRevisionDisabled) && revision.UsernameSecretRef == "" {
		return ErrNetworkProfileInvalid
	}
	if revision.Status == NetworkRevisionPending && (revision.DraftID == "" || revision.ExpiresAt == nil) {
		return ErrNetworkProfileInvalid
	}
	return nil
}

func cloneNetworkProfile(profile networkProfileRecord) networkProfileRecord {
	copy := profile
	copy.Revisions = append([]networkProfileRevisionRecord(nil), profile.Revisions...)
	for index := range copy.Revisions {
		copy.Revisions[index].AllowedProfiles = append([]string(nil), profile.Revisions[index].AllowedProfiles...)
	}
	return copy
}

func (c *networkProfileCatalog) reserve(id, label, actor, draftID, idempotencyKey string, request ProxyDraftRequest, allowed []string, expires time.Time) (networkProfileRevisionRecord, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !validNetworkProfileID(id) || label == "" || !validLabel(label) || strings.TrimSpace(actor) == "" || draftID == "" ||
		strings.TrimSpace(idempotencyKey) == "" || len(idempotencyKey) > 128 {
		return networkProfileRevisionRecord{}, ErrNetworkProfileInvalid
	}
	profile, exists := c.profiles[id]
	if exists && profile.Label != label {
		return networkProfileRevisionRecord{}, fmt.Errorf("%w: label changes require a separate rename operation", ErrNetworkProfileInvalid)
	}
	if exists {
		for _, revision := range profile.Revisions {
			if revision.Status == NetworkRevisionPending && revision.ExpiresAt != nil && c.now().UTC().Before(*revision.ExpiresAt) {
				return networkProfileRevisionRecord{}, fmt.Errorf("%w: a draft is already pending", ErrNetworkProfileInvalid)
			}
		}
	}
	revisionNumber := len(profile.Revisions) + 1
	created := c.now().UTC()
	expires = expires.UTC()
	revision := networkProfileRevisionRecord{Revision: revisionNumber, Status: NetworkRevisionPending, Protocol: request.Protocol, Auth: request.Auth,
		Host: request.Host, Port: request.Port, UpstreamCAPEM: request.UpstreamCAPEM, AllowedProfiles: append([]string(nil), allowed...),
		DraftID: draftID, IdempotencyKey: idempotencyKey, CreatedAt: created, CreatedBy: actor, ExpiresAt: &expires}
	if !exists {
		profile = networkProfileRecord{ID: id, Label: label}
	}
	profile.Revisions = append(profile.Revisions, revision)
	previousRevision := c.revision
	c.profiles[id], c.revision = profile, c.revision+1
	c.audit = append(c.audit, networkProfileAuditEvent{At: created, Actor: actor, Action: "revision_reserved", ID: id, Revision: revisionNumber, IdempotencyKey: idempotencyKey})
	if err := c.writeLocked(); err != nil {
		delete(c.profiles, id)
		if exists {
			c.profiles[id] = cloneNetworkProfile(networkProfileRecord{ID: profile.ID, Label: profile.Label, Revisions: profile.Revisions[:len(profile.Revisions)-1]})
		}
		c.revision = previousRevision
		c.audit = c.audit[:len(c.audit)-1]
		return networkProfileRevisionRecord{}, err
	}
	return revision, nil
}

func (c *networkProfileCatalog) mutate(id string, revision int, actor, idempotencyKey, action string, apply func(*networkProfileRevisionRecord) error) (networkProfileRevisionRecord, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	actor = strings.TrimSpace(actor)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if actor == "" || len(idempotencyKey) > 128 {
		return networkProfileRevisionRecord{}, ErrNetworkProfileInvalid
	}
	if idempotencyKey != "" {
		for _, event := range c.audit {
			if event.Actor != actor || event.IdempotencyKey != idempotencyKey {
				continue
			}
			if event.ID != id || event.Revision != revision || event.Action != action {
				return networkProfileRevisionRecord{}, ErrRevisionMismatch
			}
			profile, ok := c.profiles[id]
			if !ok || revision < 1 || revision > len(profile.Revisions) {
				return networkProfileRevisionRecord{}, ErrNetworkProfileNotFound
			}
			return profile.Revisions[revision-1], nil
		}
	}
	profile, ok := c.profiles[id]
	if !ok || revision < 1 || revision > len(profile.Revisions) {
		return networkProfileRevisionRecord{}, ErrNetworkProfileNotFound
	}
	before := cloneNetworkProfile(profile)
	beforeRevision, beforeAudit := c.revision, len(c.audit)
	target := &profile.Revisions[revision-1]
	if err := apply(target); err != nil {
		return networkProfileRevisionRecord{}, err
	}
	c.profiles[id], c.revision = profile, c.revision+1
	c.audit = append(c.audit, networkProfileAuditEvent{At: c.now().UTC(), Actor: actor, Action: action, ID: id, Revision: revision, IdempotencyKey: idempotencyKey})
	if err := c.writeLocked(); err != nil {
		c.profiles[id], c.revision, c.audit = before, beforeRevision, c.audit[:beforeAudit]
		return networkProfileRevisionRecord{}, err
	}
	return *target, nil
}

func (c *networkProfileCatalog) attachSecretRefs(id string, revision int, refs sealskin.ProxySecretRefs, actor string) (networkProfileRevisionRecord, error) {
	return c.mutate(id, revision, actor, "", "secret_imported", func(target *networkProfileRevisionRecord) error {
		if target.Status != NetworkRevisionPending || target.UsernameSecretRef != "" || target.PasswordSecretRef != "" {
			return ErrNetworkProfileInvalid
		}
		target.UsernameSecretRef, target.PasswordSecretRef = refs.UsernameSecretRef, refs.PasswordSecretRef
		return validateStoredNetworkRevision(*target)
	})
}

func (c *networkProfileCatalog) fail(id string, revision int, actor, action, code string) (networkProfileRevisionRecord, error) {
	return c.mutate(id, revision, actor, "", action, func(target *networkProfileRevisionRecord) error {
		if target.Status != NetworkRevisionPending {
			return ErrNetworkProfileNotAccepted
		}
		target.Status, target.ProbeCode, target.UsernameSecretRef, target.PasswordSecretRef = NetworkRevisionFailed, code, "", ""
		if action == "probe_failed" {
			now := c.now().UTC()
			target.ProbeAt = &now
		}
		return nil
	})
}

func (c *networkProfileCatalog) accept(id string, revision int, actor, code, upstreamIP string) (networkProfileRevisionRecord, error) {
	return c.mutate(id, revision, actor, "", "revision_accepted", func(target *networkProfileRevisionRecord) error {
		if target.Status != NetworkRevisionPending {
			return ErrNetworkProfileNotAccepted
		}
		now := c.now().UTC()
		target.Status, target.ProbeCode, target.UpstreamIP, target.ProbeAt, target.AcceptedAt = NetworkRevisionAccepted, code, upstreamIP, &now, &now
		return nil
	})
}

func (c *networkProfileCatalog) setStatus(id string, revision int, actor, idempotencyKey, status string) (networkProfileRevisionRecord, error) {
	action := "revision_" + status
	return c.mutate(id, revision, actor, idempotencyKey, action, func(target *networkProfileRevisionRecord) error {
		switch status {
		case NetworkRevisionDisabled:
			if target.Status == NetworkRevisionDisabled {
				return nil
			}
			if target.Status != NetworkRevisionAccepted {
				return ErrNetworkProfileNotAccepted
			}
		case NetworkRevisionRevoked:
			if target.Status == NetworkRevisionRevoked {
				return nil
			}
		default:
			return ErrNetworkProfileInvalid
		}
		target.Status = status
		if status == NetworkRevisionRevoked {
			target.DraftID, target.UsernameSecretRef, target.PasswordSecretRef = "", "", ""
		}
		return nil
	})
}

func (c *networkProfileCatalog) mutationByIdempotency(id string, revision int, actor, idempotencyKey, action string) (networkProfileRecord, networkProfileRevisionRecord, bool, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return networkProfileRecord{}, networkProfileRevisionRecord{}, false, ErrNetworkProfileInvalid
	}
	for _, event := range c.audit {
		if event.Actor != actor || event.IdempotencyKey != idempotencyKey {
			continue
		}
		if event.ID != id || event.Revision != revision || event.Action != action {
			return networkProfileRecord{}, networkProfileRevisionRecord{}, false, ErrRevisionMismatch
		}
		profile, ok := c.profiles[id]
		if !ok || revision < 1 || revision > len(profile.Revisions) {
			return networkProfileRecord{}, networkProfileRevisionRecord{}, false, ErrNetworkProfileNotFound
		}
		return cloneNetworkProfile(profile), profile.Revisions[revision-1], true, nil
	}
	return networkProfileRecord{}, networkProfileRevisionRecord{}, false, nil
}

func (c *networkProfileCatalog) getRevision(id string, revision int) (networkProfileRecord, networkProfileRevisionRecord, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	profile, ok := c.profiles[id]
	if !ok || revision < 1 || revision > len(profile.Revisions) {
		return networkProfileRecord{}, networkProfileRevisionRecord{}, ErrNetworkProfileNotFound
	}
	return cloneNetworkProfile(profile), profile.Revisions[revision-1], nil
}

func (c *networkProfileCatalog) draft(id, draftID string) (networkProfileRecord, networkProfileRevisionRecord, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	profile, ok := c.profiles[id]
	if !ok {
		return networkProfileRecord{}, networkProfileRevisionRecord{}, ErrNetworkProfileNotFound
	}
	for _, revision := range profile.Revisions {
		if revision.DraftID == draftID {
			return cloneNetworkProfile(profile), revision, nil
		}
	}
	return networkProfileRecord{}, networkProfileRevisionRecord{}, ErrNetworkProfileNotFound
}

func (c *networkProfileCatalog) byIdempotency(actor, key string) (networkProfileRecord, networkProfileRevisionRecord, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	for _, profile := range c.profiles {
		for _, revision := range profile.Revisions {
			if revision.CreatedBy == actor && revision.IdempotencyKey == key {
				return cloneNetworkProfile(profile), revision, true
			}
		}
	}
	return networkProfileRecord{}, networkProfileRevisionRecord{}, false
}

func (c *networkProfileCatalog) pending(id string) (networkProfileRecord, networkProfileRevisionRecord, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	profile, ok := c.profiles[id]
	if !ok {
		return networkProfileRecord{}, networkProfileRevisionRecord{}, false
	}
	for _, revision := range profile.Revisions {
		if revision.Status == NetworkRevisionPending {
			return cloneNetworkProfile(profile), revision, true
		}
	}
	return networkProfileRecord{}, networkProfileRevisionRecord{}, false
}

func (c *networkProfileCatalog) all() []networkProfileRecord {
	c.mu.RLock()
	defer c.mu.RUnlock()
	profiles := make([]networkProfileRecord, 0, len(c.profiles))
	for _, profile := range c.profiles {
		profiles = append(profiles, cloneNetworkProfile(profile))
	}
	sort.Slice(profiles, func(i, j int) bool { return profiles[i].ID < profiles[j].ID })
	return profiles
}

func (s *Service) networkProfilesReady() error {
	if err := s.proxyReady(); err != nil {
		return err
	}
	if s.networkProfiles == nil {
		return ErrNetworkProfilesUnavailable
	}
	return nil
}

func (s *Service) verifyNetworkProfileBinding(definition Definition) error {
	if s.networkProfiles == nil {
		return ErrNetworkProfilesUnavailable
	}
	_, revision, err := s.networkProfiles.getRevision(definition.NetworkProfileID, definition.NetworkProfileRevision)
	if err != nil {
		return err
	}
	if revision.Status != NetworkRevisionAccepted && revision.Status != NetworkRevisionDisabled {
		return ErrNetworkProfileNotAccepted
	}
	wantUpstream := revision.Protocol + "://" + revision.Host + ":" + strconv.Itoa(revision.Port)
	if definition.ProxyUpstream != wantUpstream || definition.ProxyUsernameSecretRef != revision.UsernameSecretRef ||
		definition.ProxyPasswordSecretRef != revision.PasswordSecretRef {
		return errors.New("browser binding differs from the accepted network profile revision")
	}
	return nil
}

func (s *Service) networkRevisionSummary(profile networkProfileRecord, revision networkProfileRevisionRecord) NetworkProfileRevisionSummary {
	references := 0
	for _, browser := range s.Records() {
		if browser.NetworkProfileID == profile.ID && browser.NetworkProfileRevision == revision.Revision {
			references++
		}
	}
	summary := NetworkProfileRevisionSummary{ID: profile.ID, Label: profile.Label, Revision: revision.Revision, Status: revision.Status,
		Protocol: revision.Protocol, Auth: revision.Auth, Host: revision.Host, Port: revision.Port, HasCA: revision.UpstreamCAPEM != "",
		ProbeCode: revision.ProbeCode, ProbeAt: revision.ProbeAt, UpstreamIP: revision.UpstreamIP, AllowedProfiles: append([]string(nil), revision.AllowedProfiles...),
		References: references, DraftID: revision.DraftID, CreatedAt: revision.CreatedAt, AcceptedAt: revision.AcceptedAt, ExpiresAt: revision.ExpiresAt}
	if revision.Status == NetworkRevisionPending && revision.ExpiresAt != nil {
		summary.Expired = !s.now().UTC().Before(*revision.ExpiresAt)
	}
	return summary
}

// NetworkProfiles returns every revision in stable ID/revision order.
func (s *Service) NetworkProfiles() ([]NetworkProfileRevisionSummary, error) {
	if err := s.networkProfilesReady(); err != nil {
		return nil, err
	}
	var summaries []NetworkProfileRevisionSummary
	for _, profile := range s.networkProfiles.all() {
		for _, revision := range profile.Revisions {
			if s.networkProfiles.revisionDeleted(profile.ID, revision.Revision) {
				continue
			}
			summaries = append(summaries, s.networkRevisionSummary(profile, revision))
		}
	}
	return summaries, nil
}

func (s *Service) networkSecretReference(id string, revision int) string {
	return fmt.Sprintf("secret://network-%s/password/%d", id, revision)
}

func (s *Service) revokeNetworkSecret(ctx context.Context, id string, revision int) error {
	operationID, err := randomID()
	if err != nil {
		return err
	}
	result, err := s.admin.RevokeProfileSecret(ctx, s.networkSecretReference(id, revision), operationID)
	if err != nil {
		return err
	}
	if !result.Revoked || !result.CleanupComplete {
		return errors.New("network profile credential revocation is incomplete")
	}
	return nil
}

func (s *Service) networkAllowedRecords() ([]Record, []string, []sealskin.SecretGrant) {
	records := s.Records()
	allowed := make([]string, 0, len(records))
	grants := make([]sealskin.SecretGrant, 0, len(records))
	for _, record := range records {
		if record.Status != RecordReady {
			continue
		}
		allowed = append(allowed, record.ID)
		grants = append(grants, s.grantFor(record))
	}
	sort.Strings(allowed)
	sort.Slice(grants, func(i, j int) bool { return grants[i].Profile < grants[j].Profile })
	return records, allowed, grants
}

// CreateNetworkProfileDraft reserves a catalog revision before importing any
// credential bytes. The version is never reused, including after failures.
func (s *Service) CreateNetworkProfileDraft(ctx context.Context, actor string, request NetworkProfileDraftRequest) (summary NetworkProfileRevisionSummary, err error) {
	defer func() { request.Username, request.Password = "", "" }()
	if err := s.networkProfilesReady(); err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	request.ID, request.Label, request.IdempotencyKey, actor = strings.TrimSpace(request.ID), strings.TrimSpace(request.Label), strings.TrimSpace(request.IdempotencyKey), strings.TrimSpace(actor)
	proxyRequest := ProxyDraftRequest{Protocol: request.Protocol, Auth: request.Auth, Host: request.Host, Port: request.Port,
		Username: request.Username, Password: request.Password, UpstreamCAPEM: request.UpstreamCAPEM}
	if !validNetworkProfileID(request.ID) || request.Label == "" || !validLabel(request.Label) || actor == "" || request.IdempotencyKey == "" || len(request.IdempotencyKey) > 128 {
		return NetworkProfileRevisionSummary{}, ErrNetworkProfileInvalid
	}
	if err := validateProxyDraft(proxyRequest); err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	records, allowed, grants := s.networkAllowedRecords()
	if existingProfile, existingRevision, ok := s.networkProfiles.byIdempotency(actor, request.IdempotencyKey); ok {
		if existingProfile.ID != request.ID || existingProfile.Label != request.Label || existingRevision.Protocol != request.Protocol ||
			existingRevision.Auth != request.Auth || existingRevision.Host != request.Host || existingRevision.Port != request.Port ||
			existingRevision.UpstreamCAPEM != request.UpstreamCAPEM {
			return NetworkProfileRevisionSummary{}, ErrRevisionMismatch
		}
		if existingRevision.Status == NetworkRevisionFailed && existingRevision.ProbeCode == "SECRET_IMPORT_FAILED" {
			return NetworkProfileRevisionSummary{}, fmt.Errorf("%w: the original secret import failed; use a new idempotency key", ErrNetworkProfileNotAccepted)
		}
		// A crash can occur after the durable reservation but before the
		// controller import. The same request/key resumes that exact version;
		// no new revision is allocated and grants are not widened.
		if existingRevision.Status == NetworkRevisionPending && existingRevision.Auth != "none" && existingRevision.PasswordSecretRef == "" {
			var retryGrants []sealskin.SecretGrant
			for _, record := range records {
				if contains(existingRevision.AllowedProfiles, record.ID) {
					retryGrants = append(retryGrants, s.grantFor(record))
				}
			}
			if len(retryGrants) != len(existingRevision.AllowedProfiles) {
				return NetworkProfileRevisionSummary{}, ErrNetworkProfileUnauthorized
			}
			refs, importErr := s.admin.ImportProxySecret(ctx, sealskin.ProxySecretImportRequest{SecretID: "network-" + request.ID, SecretVersion: existingRevision.Revision,
				Grants: retryGrants, Username: request.Username, Password: request.Password}, fmt.Sprintf("network-import-%s-%d", request.ID, existingRevision.Revision))
			if importErr != nil {
				return NetworkProfileRevisionSummary{}, fmt.Errorf("resume network profile credential import: %w", importErr)
			}
			existingRevision, err = s.networkProfiles.attachSecretRefs(request.ID, existingRevision.Revision, refs, actor)
			if err != nil {
				return NetworkProfileRevisionSummary{}, err
			}
		}
		return s.networkRevisionSummary(existingProfile, existingRevision), nil
	}
	if pendingProfile, pendingRevision, ok := s.networkProfiles.pending(request.ID); ok {
		if pendingRevision.ExpiresAt == nil || s.now().UTC().Before(*pendingRevision.ExpiresAt) {
			return NetworkProfileRevisionSummary{}, fmt.Errorf("%w: a draft is already pending", ErrNetworkProfileInvalid)
		}
		if pendingRevision.PasswordSecretRef != "" {
			if err := s.revokeNetworkSecret(ctx, pendingProfile.ID, pendingRevision.Revision); err != nil {
				return NetworkProfileRevisionSummary{}, err
			}
		}
		if _, err := s.networkProfiles.fail(pendingProfile.ID, pendingRevision.Revision, actor, "draft_expired", "DRAFT_EXPIRED"); err != nil {
			return NetworkProfileRevisionSummary{}, err
		}
	}
	if request.Auth != "none" && len(grants) == 0 {
		return NetworkProfileRevisionSummary{}, fmt.Errorf("%w: no ready browser grants are available", ErrNetworkProfileInvalid)
	}
	draftID, err := randomID()
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	revision, err := s.networkProfiles.reserve(request.ID, request.Label, actor, draftID, request.IdempotencyKey, proxyRequest, allowed, s.now().Add(proxyDraftLifetime))
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	profile, _, _ := s.networkProfiles.getRevision(request.ID, revision.Revision)
	if request.Auth != "none" {
		refs, importErr := s.admin.ImportProxySecret(ctx, sealskin.ProxySecretImportRequest{SecretID: "network-" + request.ID, SecretVersion: revision.Revision,
			Grants: grants, Username: request.Username, Password: request.Password}, fmt.Sprintf("network-import-%s-%d", request.ID, revision.Revision))
		if importErr != nil {
			_, _ = s.networkProfiles.fail(request.ID, revision.Revision, actor, "secret_import_failed", "SECRET_IMPORT_FAILED")
			return NetworkProfileRevisionSummary{}, fmt.Errorf("import network profile credentials: %w", importErr)
		}
		revision, err = s.networkProfiles.attachSecretRefs(request.ID, revision.Revision, refs, actor)
		if err != nil {
			_ = s.revokeNetworkSecret(ctx, request.ID, revision.Revision)
			return NetworkProfileRevisionSummary{}, err
		}
	}
	return s.networkRevisionSummary(profile, revision), nil
}

// ProbeNetworkProfileDraft validates a pending revision. Failed probes revoke
// their Secret Store version before the catalog is marked failed.
func (s *Service) ProbeNetworkProfileDraft(ctx context.Context, id, draftID, actor string) (NetworkProfileRevisionSummary, error) {
	if err := s.networkProfilesReady(); err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	profile, revision, err := s.networkProfiles.draft(strings.TrimSpace(id), strings.TrimSpace(draftID))
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	if revision.Status == NetworkRevisionAccepted || revision.Status == NetworkRevisionFailed {
		return s.networkRevisionSummary(profile, revision), nil
	}
	if revision.Status != NetworkRevisionPending {
		return NetworkProfileRevisionSummary{}, ErrNetworkProfileNotAccepted
	}
	if revision.ExpiresAt == nil || !s.now().UTC().Before(*revision.ExpiresAt) {
		if revision.PasswordSecretRef != "" {
			if err := s.revokeNetworkSecret(ctx, profile.ID, revision.Revision); err != nil {
				return NetworkProfileRevisionSummary{}, err
			}
		}
		failed, failErr := s.networkProfiles.fail(profile.ID, revision.Revision, actor, "draft_expired", "DRAFT_EXPIRED")
		return s.networkRevisionSummary(profile, failed), failErr
	}
	request := sealskin.ProxyProbeRequest{UpstreamHost: revision.Host, UpstreamPort: revision.Port, UpstreamProtocol: revision.Protocol,
		UpstreamAuth: revision.Auth, UpstreamTLSCAPEM: revision.UpstreamCAPEM, ProbeURL: s.proxyTemplate.ProbeURL, ProbeTimeoutSeconds: s.proxyTemplate.timeout()}
	if revision.Auth != "none" {
		var grant *sealskin.SecretGrant
		for _, record := range s.Records() {
			if contains(revision.AllowedProfiles, record.ID) {
				value := s.grantFor(record)
				grant = &value
				break
			}
		}
		if grant == nil {
			return NetworkProfileRevisionSummary{}, ErrNetworkProfileUnauthorized
		}
		request.UsernameSecretRef, request.PasswordSecretRef, request.Grant = revision.UsernameSecretRef, revision.PasswordSecretRef, grant
	}
	result, err := s.admin.ProbeProxyDraft(ctx, request)
	if err != nil {
		return NetworkProfileRevisionSummary{}, fmt.Errorf("probe network profile draft: %w", err)
	}
	if result.Status != "passed" {
		if revision.PasswordSecretRef != "" {
			if err := s.revokeNetworkSecret(ctx, profile.ID, revision.Revision); err != nil {
				return NetworkProfileRevisionSummary{}, err
			}
		}
		failed, failErr := s.networkProfiles.fail(profile.ID, revision.Revision, actor, "probe_failed", result.Code)
		return s.networkRevisionSummary(profile, failed), failErr
	}
	accepted, err := s.networkProfiles.accept(profile.ID, revision.Revision, actor, result.Code, result.UpstreamIP)
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	return s.networkRevisionSummary(profile, accepted), nil
}

// DisableNetworkProfile prevents new bindings while keeping existing browser
// generations and policy references valid.
func (s *Service) DisableNetworkProfile(id string, revision int, actor, idempotencyKey string) (NetworkProfileRevisionSummary, error) {
	if err := s.networkProfilesReady(); err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	profile, _, err := s.networkProfiles.getRevision(id, revision)
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	updated, err := s.networkProfiles.setStatus(id, revision, actor, idempotencyKey, NetworkRevisionDisabled)
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	return s.networkRevisionSummary(profile, updated), nil
}

// RevokeNetworkProfile refuses revisions referenced by any current browser,
// then tombstones credentials before marking the revision revoked.
func (s *Service) RevokeNetworkProfile(ctx context.Context, id string, revision int, actor, idempotencyKey string) (NetworkProfileRevisionSummary, error) {
	if err := s.networkProfilesReady(); err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	if profile, current, replay, err := s.networkProfiles.mutationByIdempotency(id, revision, actor, idempotencyKey, "revision_"+NetworkRevisionRevoked); err != nil {
		return NetworkProfileRevisionSummary{}, err
	} else if replay {
		return s.networkRevisionSummary(profile, current), nil
	}
	profile, current, err := s.networkProfiles.getRevision(id, revision)
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	summary := s.networkRevisionSummary(profile, current)
	if summary.References != 0 {
		return NetworkProfileRevisionSummary{}, ErrNetworkProfileReferenced
	}
	if current.PasswordSecretRef != "" {
		if err := s.revokeNetworkSecret(ctx, id, revision); err != nil {
			return NetworkProfileRevisionSummary{}, err
		}
	}
	updated, err := s.networkProfiles.setStatus(id, revision, actor, idempotencyKey, NetworkRevisionRevoked)
	if err != nil {
		return NetworkProfileRevisionSummary{}, err
	}
	return s.networkRevisionSummary(profile, updated), nil
}

func networkPolicyRevisionID(browserID, networkID string, revision int) string {
	value := browserID + "-" + networkID + "-r" + strconv.Itoa(revision)
	if len(value) <= 128 {
		return value
	}
	digest := sha256.Sum256([]byte(value))
	prefix := browserID
	if len(prefix) > 48 {
		prefix = prefix[:48]
	}
	network := networkID
	if len(network) > 48 {
		network = network[:48]
	}
	return prefix + "-" + network + "-" + hex.EncodeToString(digest[:])[:16]
}

// BindNetworkProfile materializes one accepted catalog revision as a precise
// browser policy. It holds the Profile lifecycle lock from the empty-runtime
// check through the application and directory mutations, so Ensure cannot
// race a new generation into the change window.
func (s *Service) BindNetworkProfile(ctx context.Context, browserID string, expectedRevision int, networkID string, networkRevision int, actor, idempotencyKey string) (Record, error) {
	if err := s.networkProfilesReady(); err != nil {
		return Record{}, err
	}
	s.networkProfilesMu.Lock()
	defer s.networkProfilesMu.Unlock()
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return Record{}, ErrNetworkProfileInvalid
	}
	profile, revision, err := s.networkProfiles.getRevision(networkID, networkRevision)
	if err != nil {
		return Record{}, err
	}
	if revision.Status != NetworkRevisionAccepted {
		return Record{}, ErrNetworkProfileNotAccepted
	}
	lock := s.profileLock(browserID)
	lock.Lock()
	defer lock.Unlock()
	record, err := s.catalogBindableRecord(browserID)
	if err != nil {
		return Record{}, err
	}
	if record.NetworkBindingKey == idempotencyKey {
		if record.NetworkProfileID == profile.ID && record.NetworkProfileRevision == revision.Revision {
			return record, nil
		}
		return Record{}, ErrRevisionMismatch
	}
	if record.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	if revision.Auth != "none" && !contains(revision.AllowedProfiles, browserID) {
		return Record{}, ErrNetworkProfileUnauthorized
	}
	if err := s.requireStoppedRuntimeLocked(ctx, browserID); err != nil {
		return Record{}, err
	}
	policyID := networkPolicyRevisionID(browserID, profile.ID, revision.Revision)
	policy := map[string]any{
		"username": s.proxyTemplate.Owner, "profile_id": record.ID, "home_name": record.HomeName, "application_id": record.ApplicationID,
		"mode": "proxy_required", "relay_image": s.proxyTemplate.RelayImage, "probe_image": s.proxyTemplate.ProbeImage,
		"upstream_host": revision.Host, "upstream_port": revision.Port, "upstream_protocol": revision.Protocol, "upstream_auth": revision.Auth,
		"probe_url": s.proxyTemplate.ProbeURL, "probe_timeout_seconds": s.proxyTemplate.timeout(),
	}
	if revision.Auth != "none" {
		policy["username_secret_ref"], policy["password_secret_ref"] = revision.UsernameSecretRef, revision.PasswordSecretRef
	}
	appended, err := s.admin.AppendNetworkPolicy(ctx, sealskin.NetworkPolicyAppendRequest{PolicyID: policyID, Policy: policy, UpstreamTLSCAPEM: revision.UpstreamCAPEM}, idempotencyKey+"-policy")
	if err != nil {
		return Record{}, fmt.Errorf("append browser network policy: %w", err)
	}
	binding := NetworkBinding{Mode: "proxy_required", PolicyID: appended.PolicyID, PolicySHA256: appended.PolicySHA256,
		NetworkProfileID: profile.ID, NetworkProfileRevision: revision.Revision, NetworkBindingKey: idempotencyKey,
		ProxyUpstream:          revision.Protocol + "://" + revision.Host + ":" + strconv.Itoa(revision.Port),
		ProxyUsernameSecretRef: revision.UsernameSecretRef, ProxyPasswordSecretRef: revision.PasswordSecretRef}
	return s.switchNetwork(ctx, record, binding, actor, idempotencyKey, 0)
}

// catalogBindableRecord also admits an R6 legacy record whose immutable
// managed policy is present but whose explicit network_mode field predates
// the R7 directory schema. The binding immediately persists proxy_required;
// records without a complete policy reference remain unmanaged.
func (s *Service) catalogBindableRecord(profileID string) (Record, error) {
	record, ok := s.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if record.Status != RecordReady {
		return Record{}, ErrBrowserCreating
	}
	if record.NetworkMode == "direct" || record.NetworkMode == "proxy_required" {
		return record, nil
	}
	if record.NetworkMode == "" && record.NetworkPolicyID != "" && record.NetworkPolicySHA256 != "" && sealskin.ValidNetworkPolicyReference(record.NetworkPolicyID, record.NetworkPolicySHA256) {
		return record, nil
	}
	return Record{}, ErrNetworkUnmanaged
}
