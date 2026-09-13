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
