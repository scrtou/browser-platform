package profile

import (
	"context"
	"errors"
	"fmt"
	"net"
	"strconv"
	"strings"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

const proxyDraftLifetime = 30 * time.Minute

var (
	ErrProxyUnavailable    = errors.New("proxy drafts require the administrator client and a proxy policy template")
	ErrProxyDraftInvalid   = errors.New("proxy draft is invalid")
	ErrProxyDraftNotFound  = errors.New("proxy draft not found, expired or replaced")
	ErrProxyDraftNotProbed = errors.New("proxy draft has not passed its probe")
	ErrNetworkUnmanaged    = errors.New("browser network is not managed by an immutable policy revision")
)

// ProxyTemplate fixes the operator-owned parts of every generated
// proxy_required revision. Owner is the SealSkin identity that launches
// browsers; the images are complete sha256 digests already present on the
// host; ProbeURL is the approved HTTPS probe target.
type ProxyTemplate struct {
	Owner               string `json:"owner"`
	RelayImage          string `json:"relay_image"`
	ProbeImage          string `json:"probe_image"`
	ProbeURL            string `json:"probe_url"`
	ProbeTimeoutSeconds int    `json:"probe_timeout_seconds,omitempty"`
}

func (t ProxyTemplate) timeout() int {
	if t.ProbeTimeoutSeconds <= 0 {
		return 10
	}
	return t.ProbeTimeoutSeconds
}

// Validate mirrors the controller's NetworkPolicy constraints for the fields
// the template supplies.
func (t ProxyTemplate) Validate() error {
	if !validPolicyName(t.Owner) {
		return errors.New("proxy_template.owner must be the SealSkin launch username")
	}
	for name, image := range map[string]string{"relay_image": t.RelayImage, "probe_image": t.ProbeImage} {
		if !strings.HasPrefix(image, "sha256:") || !validDigest(strings.TrimPrefix(image, "sha256:")) {
			return fmt.Errorf("proxy_template.%s must be a complete sha256: image digest", name)
		}
	}
	if !strings.HasPrefix(t.ProbeURL, "https://") || len(t.ProbeURL) > 2048 || strings.ContainsAny(t.ProbeURL, " @\t\n") {
		return errors.New("proxy_template.probe_url must be an HTTPS URL without credentials")
	}
	if t.ProbeTimeoutSeconds < 0 || t.ProbeTimeoutSeconds > 20 {
		return errors.New("proxy_template.probe_timeout_seconds must be between 1 and 20")
	}
	return nil
}

// ProxyDraftRequest is the administrator's submission. The credential values
// are forwarded once to the controller Secret Store and then discarded.
type ProxyDraftRequest struct {
	Protocol      string
	Auth          string
	Host          string
	Port          int
	Username      string
	Password      string
	UpstreamCAPEM string
}

// ProxyDraftSummary is the redacted management view of one draft.
type ProxyDraftSummary struct {
	ID            string     `json:"id"`
	ProfileID     string     `json:"profile_id"`
	Protocol      string     `json:"protocol"`
	Auth          string     `json:"auth"`
	Host          string     `json:"host"`
	Port          int        `json:"port"`
	HasCA         bool       `json:"has_ca"`
	SecretVersion int        `json:"secret_version,omitempty"`
	ProbeStatus   string     `json:"probe_status"`
	ProbeCode     string     `json:"probe_code,omitempty"`
	UpstreamIP    string     `json:"upstream_ip,omitempty"`
	CreatedAt     time.Time  `json:"created_at"`
	ExpiresAt     time.Time  `json:"expires_at"`
	ProbedAt      *time.Time `json:"probed_at,omitempty"`
	Expired       bool       `json:"expired"`
}

// proxyDraft is memory-only like a launch plan: a process restart drops every
// draft, and its reserved credential version is revoked on the next draft,
// switch or deletion of the same browser.
type proxyDraft struct {
	summary ProxyDraftSummary
	actor   string
	refs    sealskin.ProxySecretRefs
	caPEM   string
}

func validPolicyName(value string) bool {
	if value == "" || len(value) > 128 {
		return false
	}
	for _, char := range value {
		if !((char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') || (char >= '0' && char <= '9') || char == '_' || char == '-') {
			return false
		}
	}
	return true
}

func validUpstreamHost(host string) bool {
	if host == "" || len(host) > 253 || host != strings.TrimSpace(host) || strings.ContainsAny(host, " /@:\\") {
		return false
	}
	if ip := net.ParseIP(host); ip != nil {
		four := ip.To4()
		return four != nil && four.String() == host && four.IsGlobalUnicast() && !four.IsPrivate() && !four.IsLoopback() &&
			!four.IsLinkLocalUnicast() && !four.IsUnspecified() && !four.IsMulticast() && !(four[0] == 100 && four[1] >= 64 && four[1] <= 127)
	}
	lowered := strings.ToLower(strings.TrimSuffix(host, "."))
	if lowered == "localhost" || strings.HasSuffix(lowered, ".localhost") || strings.HasSuffix(lowered, ".local") ||
		strings.HasSuffix(lowered, ".internal") || strings.HasSuffix(lowered, ".home.arpa") || !strings.Contains(lowered, ".") {
		return false
	}
	for _, label := range strings.Split(lowered, ".") {
		if label == "" || len(label) > 63 || strings.HasPrefix(label, "-") || strings.HasSuffix(label, "-") {
			return false
		}
		for _, char := range label {
			if !((char >= 'a' && char <= 'z') || (char >= '0' && char <= '9') || char == '-') {
				return false
			}
		}
	}
	return true
}

func validCredential(value string) bool {
	if value == "" || len(value) > 4096 {
		return false
	}
	for _, char := range value {
		if char < 32 || char == 127 {
			return false
		}
	}
	return true
}

func validateProxyDraft(request ProxyDraftRequest) error {
	allowed := map[string][]string{"socks5": {"none", "username_password"}, "http": {"none", "basic"}, "https": {"none", "basic"}}
	auths, ok := allowed[request.Protocol]
	if !ok || !contains(auths, request.Auth) {
		return fmt.Errorf("%w: unsupported protocol/authentication pair", ErrProxyDraftInvalid)
	}
	if !validUpstreamHost(request.Host) || request.Port < 1 || request.Port > 65535 {
		return fmt.Errorf("%w: upstream must be a public host name or IPv4 address with a port", ErrProxyDraftInvalid)
	}
	if request.Auth == "none" {
		if request.Username != "" || request.Password != "" {
			return fmt.Errorf("%w: unauthenticated proxies must not carry credentials", ErrProxyDraftInvalid)
		}
	} else if !validCredential(request.Username) || !validCredential(request.Password) {
		return fmt.Errorf("%w: username and password are required", ErrProxyDraftInvalid)
	}
	if request.UpstreamCAPEM != "" {
		if request.Protocol != "https" || len(request.UpstreamCAPEM) > 16384 || !strings.Contains(request.UpstreamCAPEM, "-----BEGIN CERTIFICATE-----") ||
			strings.Contains(request.UpstreamCAPEM, "PRIVATE KEY") {
			return fmt.Errorf("%w: an upstream CA is only accepted as a certificate for HTTPS proxies", ErrProxyDraftInvalid)
		}
	}
	return nil
}

func (s *Service) proxyReady() error {
	if s.directoryPath == "" {
		return ErrDirectoryReadOnly
	}
	if s.admin == nil || s.proxyTemplate == nil {
		return ErrProxyUnavailable
	}
	return nil
}

func (s *Service) managedRecord(profileID string) (Record, error) {
	record, ok := s.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if record.Status != RecordReady {
		return Record{}, ErrBrowserCreating
	}
	if record.NetworkMode != "direct" && record.NetworkMode != "proxy_required" {
		return Record{}, ErrNetworkUnmanaged
	}
	return record, nil
}

func (s *Service) grantFor(record Record) sealskin.SecretGrant {
	return sealskin.SecretGrant{Owner: s.proxyTemplate.Owner, Profile: record.ID, Home: record.HomeName, App: record.ApplicationID}
}

// CreateProxyDraft reserves the next credential version, imports the
// credentials into the controller Secret Store and keeps only references.
// Any earlier draft of the same browser is replaced and its version revoked.
func (s *Service) CreateProxyDraft(ctx context.Context, profileID, actor string, request ProxyDraftRequest) (summary ProxyDraftSummary, err error) {
	defer func() { request.Password, request.Username = "", "" }()
	if err := s.proxyReady(); err != nil {
		return ProxyDraftSummary{}, err
	}
	actor = strings.TrimSpace(actor)
	if actor == "" {
		return ProxyDraftSummary{}, ErrProxyDraftInvalid
	}
	if err := validateProxyDraft(request); err != nil {
		return ProxyDraftSummary{}, err
	}
	record, err := s.managedRecord(profileID)
	if err != nil {
		return ProxyDraftSummary{}, err
	}
	if previous := s.takeProxyDraft(profileID); previous != nil {
		if err := s.revokeProxyVersion(ctx, profileID, previous.summary.SecretVersion); err != nil {
			return ProxyDraftSummary{}, fmt.Errorf("revoke replaced proxy draft: %w", err)
		}
	}
	version, err := s.directory.bumpProxySecretVersion(profileID, actor)
	if err != nil {
		return ProxyDraftSummary{}, err
	}
	draft := &proxyDraft{actor: actor, caPEM: request.UpstreamCAPEM}
	id, err := randomID()
	if err != nil {
		return ProxyDraftSummary{}, err
	}
	now := s.now().UTC()
	draft.summary = ProxyDraftSummary{ID: id, ProfileID: profileID, Protocol: request.Protocol, Auth: request.Auth, Host: request.Host, Port: request.Port,
		HasCA: request.UpstreamCAPEM != "", SecretVersion: version, ProbeStatus: "pending", CreatedAt: now, ExpiresAt: now.Add(proxyDraftLifetime)}
	if request.Auth != "none" {
		refs, err := s.admin.ImportProxySecret(ctx, sealskin.ProxySecretImportRequest{SecretID: "proxy-" + profileID, SecretVersion: version,
			Grants: []sealskin.SecretGrant{s.grantFor(record)}, Username: request.Username, Password: request.Password},
			fmt.Sprintf("proxy-import-%s-%d", profileID, version))
		if err != nil {
			return ProxyDraftSummary{}, fmt.Errorf("import proxy credentials: %w", err)
		}
		draft.refs = refs
	}
	s.draftsMu.Lock()
	if s.drafts == nil {
		s.drafts = make(map[string]*proxyDraft)
	}
	s.drafts[profileID] = draft
	s.draftsMu.Unlock()
	return s.summaryOf(draft), nil
}

func (s *Service) summaryOf(draft *proxyDraft) ProxyDraftSummary {
	summary := draft.summary
	summary.Expired = !s.now().UTC().Before(summary.ExpiresAt)
	return summary
}

// ProxyDraft is the read-only view for management pages; it has no side effects.
func (s *Service) ProxyDraft(profileID string) (ProxyDraftSummary, bool) {
	s.draftsMu.Lock()
	defer s.draftsMu.Unlock()
	draft, ok := s.drafts[profileID]
	if !ok {
		return ProxyDraftSummary{}, false
	}
	return s.summaryOf(draft), true
}

func (s *Service) takeProxyDraft(profileID string) *proxyDraft {
	s.draftsMu.Lock()
	defer s.draftsMu.Unlock()
	draft, ok := s.drafts[profileID]
	if ok {
		delete(s.drafts, profileID)
	}
	return draft
}

func (s *Service) dropProxyDraft(profileID string) { s.takeProxyDraft(profileID) }

func (s *Service) liveDraft(profileID, draftID string) (*proxyDraft, error) {
	s.draftsMu.Lock()
	defer s.draftsMu.Unlock()
	draft, ok := s.drafts[profileID]
	if !ok || draft.summary.ID != draftID || !s.now().UTC().Before(draft.summary.ExpiresAt) {
		return nil, ErrProxyDraftNotFound
	}
	return draft, nil
}

// ProbeProxyDraft asks the controller to verify the draft; the result is kept
// on the draft so a later apply can require it.
func (s *Service) ProbeProxyDraft(ctx context.Context, profileID, draftID string) (ProxyDraftSummary, error) {
	if err := s.proxyReady(); err != nil {
		return ProxyDraftSummary{}, err
	}
	record, err := s.managedRecord(profileID)
	if err != nil {
		return ProxyDraftSummary{}, err
	}
	draft, err := s.liveDraft(profileID, draftID)
	if err != nil {
		return ProxyDraftSummary{}, err
	}
	request := sealskin.ProxyProbeRequest{UpstreamHost: draft.summary.Host, UpstreamPort: draft.summary.Port, UpstreamProtocol: draft.summary.Protocol,
		UpstreamAuth: draft.summary.Auth, UpstreamTLSCAPEM: draft.caPEM, ProbeURL: s.proxyTemplate.ProbeURL, ProbeTimeoutSeconds: s.proxyTemplate.timeout()}
	if draft.summary.Auth != "none" {
		grant := s.grantFor(record)
		request.UsernameSecretRef, request.PasswordSecretRef, request.Grant = draft.refs.UsernameSecretRef, draft.refs.PasswordSecretRef, &grant
	}
	result, err := s.admin.ProbeProxyDraft(ctx, request)
	if err != nil {
		return ProxyDraftSummary{}, fmt.Errorf("probe proxy draft: %w", err)
	}
	s.draftsMu.Lock()
	defer s.draftsMu.Unlock()
	if current, ok := s.drafts[profileID]; !ok || current != draft {
		return ProxyDraftSummary{}, ErrProxyDraftNotFound
	}
	probed := s.now().UTC()
	draft.summary.ProbeStatus, draft.summary.ProbeCode, draft.summary.UpstreamIP, draft.summary.ProbedAt = result.Status, result.Code, result.UpstreamIP, &probed
	return s.summaryOf(draft), nil
}

func (s *Service) emptyRuntime(ctx context.Context, profileID string) error {
	result, err := s.Stop(ctx, profileID)
	if err != nil {
		return err
	}
	if result.Status != state.StatusStopped || result.Workers != 0 || result.Resources != 0 {
		return ErrBrowserBusy
	}
	return nil
}

// ApplyProxyDraft fixes a probed draft into an immutable proxy_required
// revision bound to the browser's next generation. Every step is idempotent
// so the same draft can be retried after a partial failure.
func (s *Service) ApplyProxyDraft(ctx context.Context, profileID string, expectedRevision int, draftID, actor, idempotencyKey string) (Record, error) {
	if err := s.proxyReady(); err != nil {
		return Record{}, err
	}
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return Record{}, errors.New("applying a proxy draft requires an actor and durable idempotency key")
	}
	record, err := s.managedRecord(profileID)
	if err != nil {
		return Record{}, err
	}
	if record.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	draft, err := s.liveDraft(profileID, draftID)
	if err != nil {
		return Record{}, err
	}
	if draft.summary.ProbeStatus != "passed" {
		return Record{}, ErrProxyDraftNotProbed
	}
	if err := s.emptyRuntime(ctx, profileID); err != nil {
		return Record{}, err
	}
	policyID := fmt.Sprintf("%s-proxy-r%d", profileID, draft.summary.SecretVersion)
	policy := map[string]any{
		"username": s.proxyTemplate.Owner, "profile_id": record.ID, "home_name": record.HomeName, "application_id": record.ApplicationID,
		"mode": "proxy_required", "relay_image": s.proxyTemplate.RelayImage, "probe_image": s.proxyTemplate.ProbeImage,
		"upstream_host": draft.summary.Host, "upstream_port": draft.summary.Port, "upstream_protocol": draft.summary.Protocol, "upstream_auth": draft.summary.Auth,
		"probe_url": s.proxyTemplate.ProbeURL, "probe_timeout_seconds": s.proxyTemplate.timeout(),
	}
	if draft.summary.Auth != "none" {
		policy["username_secret_ref"], policy["password_secret_ref"] = draft.refs.UsernameSecretRef, draft.refs.PasswordSecretRef
	}
	appended, err := s.admin.AppendNetworkPolicy(ctx, sealskin.NetworkPolicyAppendRequest{PolicyID: policyID, Policy: policy, UpstreamTLSCAPEM: draft.caPEM}, idempotencyKey+"-policy")
	if err != nil {
		return Record{}, fmt.Errorf("append proxy policy revision: %w", err)
	}
	binding := NetworkBinding{Mode: "proxy_required", PolicyID: appended.PolicyID, PolicySHA256: appended.PolicySHA256,
		ProxyUpstream:          draft.summary.Protocol + "://" + draft.summary.Host + ":" + strconv.Itoa(draft.summary.Port),
		ProxyUsernameSecretRef: draft.refs.UsernameSecretRef, ProxyPasswordSecretRef: draft.refs.PasswordSecretRef}
	updated, err := s.switchNetwork(ctx, record, binding, actor, idempotencyKey, draft.summary.SecretVersion)
	if err != nil {
		return Record{}, err
	}
	s.dropProxyDraft(profileID)
	return updated, nil
}

// SetBrowserDirect binds a stopped browser to an already registered DIRECT
// revision and revokes every proxy credential version it ever held.
func (s *Service) SetBrowserDirect(ctx context.Context, profileID string, expectedRevision int, policyID, policySHA256, actor, idempotencyKey string) (Record, error) {
	if err := s.proxyReady(); err != nil {
		return Record{}, err
	}
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return Record{}, errors.New("switching to DIRECT requires an actor and durable idempotency key")
	}
	if !validNetworkReference(policyID, policySHA256) {
		return Record{}, ErrManagedPolicyRequired
	}
	record, err := s.managedRecord(profileID)
	if err != nil {
		return Record{}, err
	}
	if record.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	if err := s.emptyRuntime(ctx, profileID); err != nil {
		return Record{}, err
	}
	updated, err := s.switchNetwork(ctx, record, NetworkBinding{Mode: "direct", PolicyID: policyID, PolicySHA256: policySHA256}, actor, idempotencyKey, 0)
	if err != nil {
		return Record{}, err
	}
	s.dropProxyDraft(profileID)
	return updated, nil
}

// switchNetwork patches the application definition, revokes every credential
// version except keep, then writes the directory revision. The application
// and directory always reference the same immutable policy after success;
// a failure between the steps leaves the launch gate closed (policy mismatch)
// and the same call can be retried.
func (s *Service) switchNetwork(ctx context.Context, record Record, binding NetworkBinding, actor, idempotencyKey string, keep int) (Record, error) {
	patch := map[string]any{"provider_config": map[string]any{"network_policy_id": binding.PolicyID, "network_policy_sha256": binding.PolicySHA256}}
	if err := s.admin.PatchInstalledApp(ctx, record.ApplicationID, patch, idempotencyKey+"-app"); err != nil {
		return Record{}, fmt.Errorf("bind application to policy revision: %w", err)
	}
	if err := s.revokeProxySecrets(ctx, record.ID, record.ProxySecretVersion, keep); err != nil {
		return Record{}, fmt.Errorf("revoke superseded proxy credentials: %w", err)
	}
	updated, err := s.directory.setNetwork(record.ID, record.Revision, actor, binding)
	if err != nil {
		return Record{}, err
	}
	return updated, nil
}

// revokeProxySecrets tombstones every credential version 1..latest of a
// browser except keep. Revocation is idempotent and versions that were never
// imported only gain a tombstone, so retries and abandoned drafts are safe.
func (s *Service) revokeProxySecrets(ctx context.Context, profileID string, latest, keep int) error {
	for version := 1; version <= latest; version++ {
		if version == keep {
			continue
		}
		if err := s.revokeProxyVersion(ctx, profileID, version); err != nil {
			return err
		}
	}
	return nil
}

func (s *Service) revokeProxyVersion(ctx context.Context, profileID string, version int) error {
	if s.admin == nil {
		return ErrAdminUnavailable
	}
	if version < 1 {
		return nil
	}
	operationID, err := randomID()
	if err != nil {
		return err
	}
	reference := fmt.Sprintf("secret://proxy-%s/password/%d", profileID, version)
	result, err := s.admin.RevokeProfileSecret(ctx, reference, operationID)
	if err != nil {
		return err
	}
	if !result.Revoked || !result.CleanupComplete {
		return fmt.Errorf("revocation of %s is incomplete", reference)
	}
	return nil
}
