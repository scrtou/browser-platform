package sealskin

import (
	"context"
	"encoding/hex"
	"errors"
	"net/http"
	"net/url"
	"strings"
)

func ValidNetworkPolicyReference(id, sha string) bool {
	if id == "" || sha == "" {
		return id == "" && sha == ""
	}
	if !validHomeName(id) || len(sha) != 64 || strings.ToLower(sha) != sha {
		return false
	}
	_, err := hex.DecodeString(sha)
	return err == nil
}

func (snapshot HomeRuntime) HasNetworkInventory() bool {
	return snapshot.NetworkRuntimeVersion == 1 && snapshot.Resources != nil
}

// HasLaunchJournal reports whether SealSkin records every named-Home launch
// before Docker create, so an empty inventory proves no create was started.
func (snapshot HomeRuntime) HasLaunchJournal() bool {
	return snapshot.LaunchJournalVersion == 1
}

func (snapshot HomeRuntime) HasNetworkEnforcement() bool {
	return snapshot.HasNetworkInventory() && snapshot.NetworkEnforcementVersion == 1
}

func (snapshot HomeRuntime) ValidNetworkInventory() bool {
	return (snapshot.NetworkEnforcementVersion == 0 || snapshot.NetworkEnforcementVersion == 1) &&
		(snapshot.HasNetworkInventory() || snapshot.NetworkRuntimeVersion == 0 && snapshot.NetworkEnforcementVersion == 0 && snapshot.Resources == nil)
}

func validHomeName(value string) bool {
	if value == "" || len(value) > 128 || strings.EqualFold(value, "cleanroom") {
		return false
	}
	for _, r := range value {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '_' || r == '-') {
			return false
		}
	}
	return true
}

func (c *Client) InspectHome(ctx context.Context, homeName string) (HomeRuntime, error) {
	var result HomeRuntime
	if !validHomeName(homeName) {
		return result, errors.New("invalid persistent Home name")
	}
	if err := c.secure(ctx, http.MethodGet, "/api/profile-runtime/"+url.PathEscape(homeName), nil, "", &result); err != nil {
		return result, err
	}
	if result.Version != 1 || result.HomeName != homeName || result.Records == nil || result.Workers == nil || !result.ValidNetworkInventory() {
		return HomeRuntime{}, errors.New("SealSkin returned an unsupported or incomplete runtime inventory")
	}
	return result, nil
}

func (c *Client) StopHome(ctx context.Context, homeName string, request StopProfileRequest, idempotencyKey string) error {
	if !validHomeName(homeName) {
		return errors.New("invalid persistent Home name")
	}
	if strings.TrimSpace(idempotencyKey) == "" || request.ProfileID == "" || request.OperationID == "" || request.ApplicationID == "" || request.BootstrapURL == "" {
		return errors.New("verified stop requires launch ownership and a durable idempotency key")
	}
	if !ValidNetworkPolicyReference(request.NetworkPolicyID, request.NetworkPolicySHA256) {
		return errors.New("stop requires a complete network policy reference")
	}
	return c.secure(ctx, http.MethodPost, "/api/profile-runtime/"+url.PathEscape(homeName)+"/stop", request, idempotencyKey, nil)
}

// ObserveHome returns a read-only health observation. It never starts, stops
// or rebuilds anything; upstream additionally probes the policy's probe URL
// through the generation's Relay.
func (c *Client) ObserveHome(ctx context.Context, homeName string, upstream bool) (HomeHealth, error) {
	var result HomeHealth
	if !validHomeName(homeName) {
		return result, errors.New("invalid persistent Home name")
	}
	path := "/api/profile-runtime/" + url.PathEscape(homeName) + "/health"
	if upstream {
		path += "?upstream=true"
	}
	if err := c.secure(ctx, http.MethodGet, path, nil, "", &result); err != nil {
		return result, err
	}
	if result.Version != 1 || result.HomeName != homeName || result.Workers == nil ||
		result.Runtime.Version != 1 || result.Runtime.HomeName != homeName ||
		result.Runtime.Records == nil || result.Runtime.Workers == nil || !result.Runtime.ValidNetworkInventory() {
		return HomeHealth{}, errors.New("SealSkin returned an unsupported or incomplete health observation")
	}
	return result, nil
}

// ResumeHome restarts an existing dormant generation in order (Relay, Guard,
// controller attachment, probe, Worker, display). It never creates or removes
// containers; a failed step returns a stable code and keeps the reservation.
func (c *Client) ResumeHome(ctx context.Context, homeName string, request StopProfileRequest, idempotencyKey string) (ResumeResult, error) {
	var result ResumeResult
	if !validHomeName(homeName) {
		return result, errors.New("invalid persistent Home name")
	}
	if strings.TrimSpace(idempotencyKey) == "" || request.ProfileID == "" || request.OperationID == "" || request.ApplicationID == "" || request.BootstrapURL == "" {
		return result, errors.New("resume requires launch ownership and a durable idempotency key")
	}
	if !ValidNetworkPolicyReference(request.NetworkPolicyID, request.NetworkPolicySHA256) {
		return result, errors.New("resume requires a complete network policy reference")
	}
	if err := c.secureWith(ctx, c.longClient, http.MethodPost, "/api/profile-runtime/"+url.PathEscape(homeName)+"/resume", request, idempotencyKey, &result); err != nil {
		return result, err
	}
	if result.State != "live" || result.SessionID == "" || result.InstanceID == "" {
		return ResumeResult{}, errors.New("SealSkin returned an incomplete resume result")
	}
	return result, nil
}
