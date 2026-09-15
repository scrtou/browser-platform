package sealskin

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"math"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type CoherenceBinding struct {
	ApplicationID    string `json:"application_id"`
	ProfileID        string `json:"profile_id"`
	HomeName         string `json:"home_name"`
	OperationID      string `json:"operation_id,omitempty"`
	SessionID        string `json:"session_id,omitempty"`
	PolicyID         string `json:"policy_id"`
	PolicySHA256     string `json:"policy_sha256"`
	ArtifactSHA256   string `json:"artifact_sha256"`
	AcceptanceSHA256 string `json:"acceptance_sha256"`
	EnvironmentID    string `json:"environment_id"`
	WorkerID         string `json:"worker_id"`
	WorkerStartedAt  string `json:"worker_started_at"`
	RelayID          string `json:"relay_id"`
	RelayStartedAt   string `json:"relay_started_at"`
	GuardID          string `json:"guard_id"`
	GuardStartedAt   string `json:"guard_started_at"`
}

type CoherenceCheck struct {
	Name     string `json:"name"`
	Status   string `json:"status"`
	Required bool   `json:"required"`
	Code     string `json:"code"`
	Message  string `json:"message"`
}

type CoherenceConstraints struct {
	AllowedCountries []string `json:"allowed_countries"`
	AllowedTimezones []string `json:"allowed_timezones"`
	OnExitChange     string   `json:"on_exit_change"`
}

type CoherenceReport struct {
	Version              int                   `json:"version"`
	Enabled              bool                  `json:"enabled"`
	Mode                 string                `json:"mode"`
	NetworkMode          string                `json:"network_mode"`
	Constraints          *CoherenceConstraints `json:"constraints"`
	Overall              string                `json:"overall"`
	Allowed              bool                  `json:"allowed"`
	Code                 string                `json:"code"`
	CheckedAt            float64               `json:"checked_at"`
	ExpiresAt            float64               `json:"expires_at"`
	Nonce                string                `json:"nonce"`
	Binding              CoherenceBinding      `json:"binding"`
	Expected             map[string]any        `json:"expected"`
	Observed             map[string]any        `json:"observed"`
	Exit                 map[string]any        `json:"exit"`
	NetworkEvidence      map[string]any        `json:"network_evidence"`
	LocaleEvidence       map[string]any        `json:"locale_evidence"`
	Checks               []CoherenceCheck      `json:"checks"`
	GateSequence         uint64                `json:"gate_sequence"`
	ExitChangeBlocked    bool                  `json:"exit_change_blocked,omitempty"`
	PausedForIsolation   bool                  `json:"paused_for_isolation,omitempty"`
	LeakDetected         bool                  `json:"leak_detected,omitempty"`
	IsolationPauseFailed bool                  `json:"isolation_pause_failed,omitempty"`
}

func (r *CoherenceReport) Fresh(now time.Time) bool {
	if r == nil {
		return false
	}
	seconds := float64(now.UnixNano()) / 1e9
	return !math.IsNaN(r.CheckedAt) && !math.IsInf(r.CheckedAt, 0) && !math.IsNaN(r.ExpiresAt) && !math.IsInf(r.ExpiresAt, 0) &&
		r.CheckedAt > 0 && r.CheckedAt <= seconds && seconds < r.ExpiresAt && r.ExpiresAt-r.CheckedAt <= 60
}

func lowerHex(value string, size int) bool {
	if len(value) != size || value != strings.ToLower(value) {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

// These are the mandatory observations for the supported frozen Camoufox
// capability set. Missing rows and downgraded required flags never pass.
var coherenceRequiredChecks = []string{"observation", "user_agent", "platform", "oscpu", "cpu", "timezone", "locale", "languages",
	"intl_locale", "screen", "dpr", "webgl", "fonts", "canvas", "audio", "voices", "webrtc", "network_path", "dns", "ipv6", "direct_bypass", "exit_observation"}

func (r *CoherenceReport) Permits(now time.Time) bool {
	if r == nil || !r.Enabled || r.Version != 1 || !r.Allowed || !r.Fresh(now) || r.LeakDetected || r.ExitChangeBlocked ||
		r.PausedForIsolation || r.IsolationPauseFailed || (r.Mode != "strict" && r.Mode != "advisory") ||
		(r.Overall != "healthy" && r.Overall != "degraded") || r.GateSequence == 0 || !lowerHex(r.Nonce, 32) {
		return false
	}
	b := r.Binding
	c := r.Constraints
	if c == nil || (c.OnExitChange != "block" && c.OnExitChange != "recheck") ||
		(r.NetworkMode != "direct" && r.NetworkMode != "proxy_required") ||
		(r.Mode == "strict" && len(c.AllowedCountries) == 0 && len(c.AllowedTimezones) == 0) {
		return false
	}
	if b.ApplicationID == "" || b.ProfileID == "" || b.HomeName == "" || b.OperationID == "" || b.SessionID == "" ||
		b.PolicyID == "" || b.EnvironmentID == "" || !lowerHex(b.PolicySHA256, 64) || !lowerHex(b.ArtifactSHA256, 64) ||
		!lowerHex(b.AcceptanceSHA256, 64) || !lowerHex(b.WorkerID, 64) || !lowerHex(b.RelayID, 64) || !lowerHex(b.GuardID, 64) {
		return false
	}
	for _, value := range []string{b.WorkerStartedAt, b.RelayStartedAt, b.GuardStartedAt} {
		parsed, err := time.Parse(time.RFC3339Nano, value)
		if err != nil || parsed.IsZero() || float64(parsed.UnixNano())/1e9 > r.CheckedAt {
			return false
		}
	}
	seen := make(map[string]CoherenceCheck)
	for _, check := range r.Checks {
		if _, found := seen[check.Name]; found || check.Name == "" || check.Code == "" {
			return false
		}
		if check.Required && check.Status != "pass" {
			return false
		}
		if check.Status != "pass" && check.Status != "fail" && check.Status != "warn" && check.Status != "unknown" && check.Status != "not_applicable" {
			return false
		}
		seen[check.Name] = check
	}
	for _, name := range coherenceRequiredChecks {
		if !seen[name].Required || seen[name].Status != "pass" {
			return false
		}
	}
	for name, required := range map[string]bool{
		"direct_exit":      r.NetworkMode == "direct",
		"country":          r.Mode == "strict" && len(c.AllowedCountries) != 0,
		"allowed_timezone": r.Mode == "strict" && len(c.AllowedTimezones) != 0,
	} {
		if required && (!seen[name].Required || seen[name].Status != "pass") {
			return false
		}
	}
	return true
}

type CoherenceAccess struct {
	Version int              `json:"version"`
	Enabled bool             `json:"enabled"`
	Allowed bool             `json:"allowed"`
	Report  *CoherenceReport `json:"report"`
}

func (c *Client) CheckCoherence(ctx context.Context, home string, request StopProfileRequest, probe bool) (CoherenceAccess, error) {
	var result CoherenceAccess
	if !validHomeName(home) || request.ProfileID == "" || request.OperationID == "" || request.SessionID == "" {
		return result, errors.New("coherence requires a complete runtime binding")
	}
	action := "access"
	if probe {
		action = "probe"
	}
	// Sampling may update the generation's report and gate. Use one request
	// identifier for this logical call, including any crypto-session retry.
	var nonce [16]byte
	if _, err := rand.Read(nonce[:]); err != nil {
		return result, errors.New("could not identify coherence request")
	}
	key := "coherence-" + hex.EncodeToString(nonce[:])
	if err := c.secureWith(ctx, c.longClient, http.MethodPost, "/api/profile-runtime/"+url.PathEscape(home)+"/coherence/"+action, request, key, &result); err != nil {
		return result, err
	}
	if result.Version != 1 || !result.Enabled && !result.Allowed {
		return CoherenceAccess{}, errors.New("unsupported coherence access response")
	}
	if result.Enabled && result.Allowed {
		report := result.Report
		if !report.Permits(time.Now()) || report.Binding.ProfileID != request.ProfileID || report.Binding.HomeName != home ||
			report.Binding.ApplicationID != request.ApplicationID ||
			report.Binding.OperationID != request.OperationID || report.Binding.SessionID != request.SessionID ||
			report.Binding.PolicyID != request.NetworkPolicyID || report.Binding.PolicySHA256 != request.NetworkPolicySHA256 {
			return CoherenceAccess{}, errors.New("coherence access response is stale or bound to a different generation")
		}
	}
	return result, nil
}
