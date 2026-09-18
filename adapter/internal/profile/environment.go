package profile

import (
	"context"
	"errors"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

// EnvironmentHealth is the evidence-bearing part of a summary. It is copied
// from the cached health report and carries the report's own sampling time and
// validity; an expired report is stale and its overall result is unknown.
type EnvironmentHealth struct {
	Overall     Overall                       `json:"overall"`
	Stale       bool                          `json:"stale"`
	CheckedAt   time.Time                     `json:"checked_at"`
	ExpiresAt   time.Time                     `json:"expires_at"`
	Code        string                        `json:"code,omitempty"`
	Title       string                        `json:"title,omitempty"`
	Blocking    bool                          `json:"blocking"`
	Environment *sealskin.EnvironmentIdentity `json:"environment,omitempty"`
}

// EnvironmentSummary is the read-only management view of one Profile. It is
// derived from the configured definition, the atomic journal and the cached
// health report only. It never carries operation IDs, Session IDs, bootstrap
// or handoff URLs, idempotency keys, policy digests, error text or any
// resolved environment configuration, and producing it never observes,
// launches, resumes or stops a generation.
type EnvironmentSummary struct {
	ProfileID       string             `json:"profile_id"`
	Enabled         bool               `json:"enabled"`
	Revision        int                `json:"revision"`
	Label           string             `json:"label"`
	StartURL        string             `json:"start_url"`
	EntryPath       string             `json:"entry_path"`
	ApplicationID   string             `json:"application_id"`
	HomeName        string             `json:"home_name"`
	Language        string             `json:"language,omitempty"`
	Timezone        string             `json:"timezone,omitempty"`
	DisplayMode     string             `json:"display_mode"`
	NetworkMode     string             `json:"network_mode"`
	NetworkPolicyID string             `json:"network_policy_id,omitempty"`
	Status          state.Status       `json:"status"`
	UpdatedAt       *time.Time         `json:"updated_at,omitempty"`
	Observed        bool               `json:"observed"`
	Health          *EnvironmentHealth `json:"health,omitempty"`
}

// Environment builds the summary for one configured Profile. The journal is
// read atomically without the Profile lock, like the display authorization
// check, so a long lifecycle call never blocks a management page. Health is
// read cache-only: a missing report is reported as unobserved rather than
// collected here.
func (s *Service) Environment(ctx context.Context, id string) (EnvironmentSummary, error) {
	if err := ctx.Err(); err != nil {
		return EnvironmentSummary{}, err
	}
	record, ok := s.record(id)
	if !ok {
		return EnvironmentSummary{}, ErrProfileNotFound
	}
	definition := record.Definition
	summary := EnvironmentSummary{
		ProfileID: definition.ID, Label: definition.DisplayLabel(), StartURL: definition.StartURL, EntryPath: "/browser/" + definition.ID + "/",
		ApplicationID: definition.ApplicationID, HomeName: definition.HomeName,
		DisplayMode: "x11", NetworkMode: "unmanaged", Status: state.StatusStopped,
		Enabled: !definition.Disabled, Revision: record.Revision,
	}
	if definition.Language != nil {
		summary.Language = *definition.Language
	}
	if definition.Timezone != nil {
		summary.Timezone = *definition.Timezone
	}
	if definition.WaylandMode {
		summary.DisplayMode = "wayland"
	}
	if definition.NetworkPolicyID != "" {
		summary.NetworkMode, summary.NetworkPolicyID = "managed", definition.NetworkPolicyID
	}
	binding, found, err := s.store.Get(id)
	if err != nil {
		return EnvironmentSummary{}, err
	}
	if found {
		updated := binding.UpdatedAt
		summary.Status, summary.UpdatedAt = binding.Status, &updated
	}
	report, err := s.Health(ctx, id, HealthOptions{CachedOnly: true})
	switch {
	case errors.Is(err, ErrHealthUnavailable), errors.Is(err, ErrLifecycleDisabled):
		return summary, nil
	case err != nil:
		return EnvironmentSummary{}, err
	}
	health := &EnvironmentHealth{Overall: report.Overall, Stale: report.Stale, CheckedAt: report.CheckedAt, ExpiresAt: report.ExpiresAt}
	if report.Recovery != nil {
		health.Code, health.Title, health.Blocking = report.Recovery.Code, report.Recovery.Title, report.Recovery.Blocking
	}
	if report.Environment.ID != "" || report.Environment.ArtifactSHA256 != "" {
		identity := report.Environment
		health.Environment = &identity
	}
	if report.NetworkMode == "direct" && summary.NetworkMode == "managed" {
		summary.NetworkMode = "direct"
	}
	summary.Observed, summary.Health = true, health
	return summary, nil
}
