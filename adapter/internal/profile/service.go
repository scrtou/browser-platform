// Package profile maps stable Profile identities to SealSkin sessions and
// enforces a conservative single-session state machine.
package profile

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode"
	"unicode/utf8"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

var (
	ErrProfileNotFound  = errors.New("profile not found")
	ErrOperationRunning = errors.New("profile operation is already running")
	ErrOwnershipUnknown = errors.New("profile session ownership is unknown; operator recovery is required")
	ErrAdminUnavailable = errors.New("verified administrator SealSkin client is not configured")
	ErrBrowserBusy      = errors.New("browser still owns runtime resources")
	ErrBrowserCreating  = errors.New("browser creation is still in progress")
	ErrBrowserDeleted   = errors.New("browser has been deleted")
)

type Definition struct {
	ID string `json:"id"`
	// Label is an optional display name for management pages; it never
	// replaces the ID used by entry paths, journals or authorization.
	Label                     string  `json:"label,omitempty"`
	ApplicationID             string  `json:"application_id"`
	HomeName                  string  `json:"home_name"`
	StartURL                  string  `json:"start_url"`
	Language                  *string `json:"language,omitempty"`
	Timezone                  *string `json:"timezone,omitempty"`
	WaylandMode               bool    `json:"wayland_mode"`
	NetworkPolicyID           string  `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256       string  `json:"network_policy_sha256,omitempty"`
	NetworkMode               string  `json:"network_mode,omitempty"`
	EnvironmentArtifactID     string  `json:"environment_artifact_id,omitempty"`
	EnvironmentArtifactSHA256 string  `json:"environment_artifact_sha256,omitempty"`
	EnvironmentSource         string  `json:"environment_source,omitempty"`
	// IdlePolicy enables automatic reclaim; nil or mode "off" disables it.
	IdlePolicy *IdlePolicy `json:"idle_policy,omitempty"`
	// RequiredRuntimeCapabilities binds a new Worker to its controller contract.
	// Stop and reconciliation remain available when the controller is older.
	RequiredRuntimeCapabilities map[string]int `json:"required_runtime_capabilities,omitempty"`
	// Disabled refuses new launches and entry reuse; running generations,
	// stop, reconciliation and health are unaffected.
	Disabled bool `json:"disabled,omitempty"`
	// ProxySecretVersion is the last Secret Store version imported for this
	// browser's proxy credentials (secret ID proxy-<id>); it only grows so a
	// version is never reused. ProxyUpstream is a display-only
	// protocol://host:port summary and the two references name the bound
	// credential version; all three are empty for DIRECT and legacy browsers.
	ProxySecretVersion     int    `json:"proxy_secret_version,omitempty"`
	ProxyUpstream          string `json:"proxy_upstream,omitempty"`
	ProxyUsernameSecretRef string `json:"proxy_username_secret_ref,omitempty"`
	ProxyPasswordSecretRef string `json:"proxy_password_secret_ref,omitempty"`
}

// IdlePolicy follows the health specification's idlePolicy: only the
// "disconnected" mode is supported (time since the last authenticated display
// connection closed). "input_idle" is rejected because no verified input
// activity source exists yet.
type IdlePolicy struct {
	Mode           string `json:"mode"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

func (p *IdlePolicy) Enabled() bool { return p != nil && p.Mode == "disconnected" }

func (p *IdlePolicy) Timeout() time.Duration {
	if p == nil || p.TimeoutSeconds <= 0 {
		return 900 * time.Second
	}
	return time.Duration(p.TimeoutSeconds) * time.Second
}

// Limits are checked before any new launch; none of them ever releases an
// existing reservation.
type Limits struct {
	MaxActiveProfiles   int    `json:"max_active_profiles,omitempty"`
	MaxConcurrentLaunch int    `json:"max_concurrent_launches,omitempty"`
	MinFreeDiskMiB      int    `json:"min_free_disk_mib,omitempty"`
	StoragePath         string `json:"storage_path,omitempty"`
	freeDiskMiB         func(string) (int64, error)
}

type Orchestrator interface {
	ListSessions(context.Context) ([]sealskin.Session, error)
	LaunchURL(context.Context, sealskin.LaunchURLRequest, string) (sealskin.LaunchResponse, error)
	ListHomeDirectories(context.Context) ([]string, error)
	CreateHomeDirectory(context.Context, string, string) error
}

// AdminOrchestrator is intentionally separate from the launch client. It is
// used only for R6 management mutations and must be configured with a
// separate administrator identity in the production process.
type AdminOrchestrator interface {
	InstallApp(context.Context, map[string]any, string) error
	PatchInstalledApp(context.Context, string, map[string]any, string) error
	DeleteInstalledApp(context.Context, string, string) error
	ImportProxySecret(context.Context, sealskin.ProxySecretImportRequest, string) (sealskin.ProxySecretRefs, error)
	ProbeProxyDraft(context.Context, sealskin.ProxyProbeRequest) (sealskin.ProxyProbeResult, error)
	AppendNetworkPolicy(context.Context, sealskin.NetworkPolicyAppendRequest, string) (sealskin.NetworkPolicyAppendResponse, error)
	RevokeProfileSecret(context.Context, string, string) (sealskin.RevokeSecretResult, error)
}

type HomeArchiver interface {
	ArchiveHomeDirectory(context.Context, string, sealskin.ArchiveHomeRequest, string) error
}

type EnvironmentArtifact struct {
	ID                          string         `json:"id"`
	SHA256                      string         `json:"sha256"`
	AcceptanceSHA256            string         `json:"acceptance_sha256"`
	Image                       string         `json:"image"`
	Source                      string         `json:"source"`
	Status                      string         `json:"status"`
	Application                 map[string]any `json:"application"`
	RequiredRuntimeCapabilities map[string]int `json:"required_runtime_capabilities,omitempty"`
	// Descriptive fields for the catalog listing; they never replace the
	// artifact's own bytes as the source of device values.
	Locale     string   `json:"locale,omitempty"`
	Languages  []string `json:"languages,omitempty"`
	Timezone   string   `json:"timezone,omitempty"`
	Screen     string   `json:"screen,omitempty"`
	AcceptedAt string   `json:"accepted_at,omitempty"`
	JobID      string   `json:"job_id,omitempty"`
}

type EnvironmentCatalog interface {
	Accepted(context.Context, string) (EnvironmentArtifact, error)
	List(context.Context) ([]EnvironmentArtifact, error)
}

type CreateBrowserRequest struct {
	Label                 string
	StartURL              string
	EnvironmentArtifactID string
	NetworkMode           string
	NetworkPolicyID       string
	NetworkPolicySHA256   string
	Language              *string
	Timezone              *string
	WaylandMode           bool
}

// ManagementCapabilities reports which optional management backends are
// fully configured. The HTTP layer uses this to avoid advertising actions
// that can only fail after submission.
type ManagementCapabilities struct {
	CreateDelete    bool
	ProxyDrafts     bool
	EnvironmentJobs bool
}

type Service struct {
	orchestrator  Orchestrator
	admin         AdminOrchestrator
	homeArchiver  HomeArchiver
	catalog       EnvironmentCatalog
	store         *state.Store
	publicBase    *url.URL
	directory     *directory
	directoryPath string
	runtime       RuntimeController
	now           func() time.Time
	health        healthCache
	limits        Limits
	launching     int32
	stopHook      func(string) // test hook, called after an idle stop attempt

	locksMu sync.Mutex
	locks   map[string]*sync.Mutex
	plansMu sync.Mutex
	plans   map[string]launchPlan

	proxyTemplate *ProxyTemplate
	draftsMu      sync.Mutex
	drafts        map[string]*proxyDraft
	jobSpool      string
}

func NewService(orchestrator Orchestrator, store *state.Store, publicBaseURL string, definitions []Definition, options ...Option) (*Service, error) {
	if orchestrator == nil || store == nil {
		return nil, errors.New("orchestrator and state store are required")
	}
	publicBase, err := url.Parse(publicBaseURL)
	if err != nil || publicBase.Scheme != "https" || publicBase.Host == "" {
		return nil, errors.New("adapter public base URL must be absolute HTTPS")
	}
	if publicBase.RawQuery != "" || publicBase.Fragment != "" {
		return nil, errors.New("adapter public base URL must not contain a query or fragment")
	}
	if publicBase.Path != "" && publicBase.Path != "/" {
		return nil, errors.New("adapter public base URL must be an HTTPS origin without a path")
	}
	now := time.Now
	catalog, err := newDirectory(definitions, now)
	if err != nil {
		return nil, err
	}
	service := &Service{
		orchestrator: orchestrator, store: store, publicBase: publicBase,
		directory: catalog, locks: make(map[string]*sync.Mutex), now: now,
		health: healthCache{reports: make(map[string]HealthReport), inflight: make(map[string]*healthFlight), started: make(map[string]time.Time)},
	}
	for _, option := range options {
		option(service)
	}
	service.directory.now = func() time.Time { return service.now() }
	if service.directoryPath != "" {
		if err := service.directory.open(service.directoryPath); err != nil {
			return nil, err
		}
	} else if len(service.directory.records) == 0 {
		return nil, errors.New("at least one profile is required")
	}
	for _, definition := range service.directory.definitions() {
		if len(definition.RequiredRuntimeCapabilities) != 0 && service.runtime == nil {
			return nil, errors.New("runtime capability requirements need verified lifecycle")
		}
		if definition.NetworkPolicyID != "" && service.runtime == nil {
			return nil, errors.New("network policies require verified lifecycle")
		}
		if definition.IdlePolicy.Enabled() && service.runtime == nil {
			return nil, errors.New("idle reclaim requires verified lifecycle")
		}
	}
	return service, nil
}

// WithLimits installs capacity thresholds checked before every new launch.
func WithLimits(limits Limits) Option {
	return func(s *Service) {
		if limits.freeDiskMiB == nil {
			limits.freeDiskMiB = freeDiskMiB
		}
		s.limits = limits
	}
}

// WithDirectory persists the browser definitions in a private file. An
// existing file is authoritative; a missing one is created from the
// configured profiles.
func WithDirectory(path string) Option {
	return func(s *Service) { s.directoryPath = path }
}

func WithAdminOrchestrator(admin AdminOrchestrator) Option {
	return func(s *Service) { s.admin = admin }
}

func WithHomeArchiver(archiver HomeArchiver) Option {
	return func(s *Service) { s.homeArchiver = archiver }
}

func WithEnvironmentCatalog(catalog EnvironmentCatalog) Option {
	return func(s *Service) { s.catalog = catalog }
}

// WithProxyTemplate enables proxy drafts. The template fixes the operator
// values every generated proxy_required revision shares: the launching
// SealSkin identity, the Relay and probe image digests and the approved
// probe target.
func WithProxyTemplate(template ProxyTemplate) Option {
	return func(s *Service) { copied := template; s.proxyTemplate = &copied }
}

// Records lists every browser definition with its directory metadata.
func (s *Service) Records() []Record { return s.directory.all() }

// ProfileIDs lists the configured Profile IDs in a stable order.
func (s *Service) ProfileIDs() []string { return s.directory.ids() }

func (s *Service) ManagementCapabilities() ManagementCapabilities {
	createDelete := s.directoryPath != "" && s.admin != nil && s.homeArchiver != nil && s.catalog != nil
	return ManagementCapabilities{
		CreateDelete:    createDelete,
		ProxyDrafts:     createDelete && s.proxyTemplate != nil,
		EnvironmentJobs: s.catalog != nil && s.jobSpool != "",
	}
}

// KnownProfile reports whether a Profile ID is configured.
func (s *Service) KnownProfile(id string) bool {
	_, ok := s.directory.get(id)
	return ok
}

// UpdateBrowser changes display fields or the enabled flag under optimistic
// locking. It never touches a running generation: the next launch reads the
// new start URL, and a disabled browser only refuses new launches and reuse.
func (s *Service) UpdateBrowser(id string, expectedRevision int, actor string, patch BrowserPatch) (Record, error) {
	return s.directory.update(id, expectedRevision, actor, patch)
}

// Ensure returns a live session for a Profile. It never launches while an
// earlier operation has an unproven outcome.
func (s *Service) Ensure(ctx context.Context, profileID string) (result sealskin.Session, resultErr error) {
	definition, ok := s.directory.get(profileID)
	if !ok {
		return sealskin.Session{}, ErrProfileNotFound
	}
	if definition.Disabled {
		return sealskin.Session{}, ErrProfileDisabled
	}
	lock := s.profileLock(profileID)
	lock.Lock()
	defer lock.Unlock()
	defer func() {
		if resultErr == nil && result.SessionID != "" {
			if err := s.verifySessionAccess(ctx, definition, result.SessionID); err != nil {
				result, resultErr = sealskin.Session{}, err
			}
		}
	}()

	// Reject an incompatible controller before even creating a new Home.
	if len(definition.RequiredRuntimeCapabilities) != 0 {
		snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
		if err != nil {
			return sealskin.Session{}, err
		}
		if err := verifyRequiredCapabilities(definition, snapshot); err != nil {
			return sealskin.Session{}, err
		}
	}
	if err := s.ensureHome(ctx, definition.HomeName); err != nil {
		return sealskin.Session{}, fmt.Errorf("ensure SealSkin Home %q: %w", definition.HomeName, err)
	}
	sessions, err := s.orchestrator.ListSessions(ctx)
	if err != nil {
		return sealskin.Session{}, fmt.Errorf("list SealSkin sessions: %w", err)
	}
	binding, found, err := s.store.Get(profileID)
	if err != nil {
		return sealskin.Session{}, err
	}
	if s.runtime != nil {
		if err := s.verifyBeforeEnsure(ctx, definition, binding, found); err != nil {
			return sealskin.Session{}, err
		}
	}
	if found {
		switch binding.Status {
		case state.StatusRunning:
			if session, ok := findByID(sessions, binding.SessionID); ok {
				return session, nil
			}
			if err := s.mark(profileID, binding.OperationID, state.StatusUnknown, "bound SealSkin session disappeared"); err != nil {
				return sealskin.Session{}, err
			}
			return sealskin.Session{}, ErrOwnershipUnknown
		case state.StatusLaunching, state.StatusUnknown:
			return s.reconcileExisting(profileID, binding, sessions)
		case state.StatusStopping:
			return sealskin.Session{}, ErrOperationRunning
		case state.StatusStopped, state.StatusFailed:
			// A confirmed non-running state may start a new operation.
		default:
			return sealskin.Session{}, fmt.Errorf("unsupported profile state %q", binding.Status)
		}
	}

	initialURL := ""
	if s.runtime != nil && definition.NetworkPolicyID != "" {
		snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
		if err != nil {
			return sealskin.Session{}, err
		}
		if snapshot.ProfileInitialURLVersion == 1 {
			initialURL = definition.StartURL
		}
	}
	if err := s.checkCapacity(profileID); err != nil {
		return sealskin.Session{}, err
	}
	atomic.AddInt32(&s.launching, 1)
	defer atomic.AddInt32(&s.launching, -1)
	binding, err = s.prepareLaunch(profileID)
	if err != nil {
		return sealskin.Session{}, err
	}
	request := sealskin.LaunchURLRequest{
		URL: binding.BootstrapURL, InitialURL: initialURL, ApplicationID: definition.ApplicationID,
		HomeName: definition.HomeName, Language: definition.Language,
		Timezone: definition.Timezone, WaylandMode: definition.WaylandMode,
		NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256,
	}
	if s.runtime != nil {
		request.ProfileID, request.OperationID = profileID, binding.OperationID
	}
	launched, launchErr := s.orchestrator.LaunchURL(ctx, request, binding.IdempotencyKey)
	if launchErr == nil {
		if launched.SessionID == "" || launched.SessionURL == "" {
			launchErr = errors.New("SealSkin returned an incomplete launch response")
		} else {
			if err := s.verifyManagedLaunch(ctx, definition, binding, launched.SessionID, initialURL != ""); err != nil {
				_ = s.mark(profileID, binding.OperationID, state.StatusUnknown, "network-managed launch requires reconciliation")
				return sealskin.Session{}, err
			}
			if err := s.bindRunning(profileID, binding.OperationID, launched.SessionID); err != nil {
				return sealskin.Session{}, fmt.Errorf("persist launched session ownership: %w", err)
			}
			return sealskin.Session{
				SessionID: launched.SessionID, SessionURL: launched.SessionURL,
				AppID:         definition.ApplicationID,
				LaunchContext: &sealskin.LaunchContext{Type: "url", Value: binding.BootstrapURL},
			}, nil
		}
	}

	// A response can be lost after launch. The unique bootstrap URL lets us
	// recover exactly one matching session without issuing another launch.
	reconciled, listErr := s.orchestrator.ListSessions(ctx)
	if listErr == nil {
		matches := findByMarker(reconciled, binding.BootstrapURL, definition.ApplicationID)
		if len(matches) == 1 {
			if err := s.verifyManagedLaunch(ctx, definition, binding, matches[0].SessionID, initialURL != ""); err != nil {
				_ = s.mark(profileID, binding.OperationID, state.StatusUnknown, "network-managed launch requires reconciliation")
				return sealskin.Session{}, err
			}
			if err := s.bindRunning(profileID, binding.OperationID, matches[0].SessionID); err != nil {
				return sealskin.Session{}, err
			}
			return matches[0], nil
		}
		if len(matches) > 1 {
			_ = s.mark(profileID, binding.OperationID, state.StatusUnknown, "multiple SealSkin sessions match one launch operation")
			return sealskin.Session{}, ErrOwnershipUnknown
		}
	}

	var apiErr *sealskin.APIError
	if errors.As(launchErr, &apiErr) && apiErr.StatusCode >= 400 && apiErr.StatusCode < 500 {
		if binding.NetworkPolicyID != "" {
			snapshot, inspectErr := s.inspectRuntime(ctx, definition.HomeName)
			if inspectErr != nil || !snapshot.HasNetworkInventory() || !runtimeEmpty(snapshot) {
				_ = s.mark(profileID, binding.OperationID, state.StatusUnknown, "network preparation remains reserved")
				return sealskin.Session{}, errors.Join(ErrOwnershipUnknown, launchErr, inspectErr)
			}
		}
		if err := s.mark(profileID, binding.OperationID, state.StatusFailed, launchErr.Error()); err != nil {
			return sealskin.Session{}, err
		}
		return sealskin.Session{}, launchErr
	}
	detail := launchErr.Error()
	if listErr != nil {
		detail += "; reconciliation failed: " + listErr.Error()
	}
	if err := s.mark(profileID, binding.OperationID, state.StatusUnknown, detail); err != nil {
		return sealskin.Session{}, err
	}
	return sealskin.Session{}, fmt.Errorf("%w: %v", ErrOwnershipUnknown, launchErr)
}

func (s *Service) BootstrapTarget(profileID, operationID string) (string, error) {
	definition, ok := s.directory.get(profileID)
	if !ok {
		return "", ErrProfileNotFound
	}
	binding, found, err := s.store.Get(profileID)
	if err != nil {
		return "", err
	}
	if !found || binding.OperationID != operationID {
		return "", ErrProfileNotFound
	}
	switch binding.Status {
	case state.StatusLaunching, state.StatusRunning, state.StatusUnknown:
	default:
		return "", ErrProfileNotFound
	}
	return definition.StartURL, nil
}

// ResetUnknown is intentionally separate from Ensure. It is for an explicit
// operator recovery after the SealSkin/Docker state has been inspected.
func (s *Service) ResetUnknown(profileID string) error {
	if s.runtime != nil {
		return errors.New("verified lifecycle is enabled; use reconcile-profile or stop-profile instead of an unchecked reset")
	}
	if _, ok := s.directory.get(profileID); !ok {
		return ErrProfileNotFound
	}
	return s.store.Update(profileID, func(current *state.Binding) (*state.Binding, error) {
		if current == nil {
			return nil, nil
		}
		if current.Status != state.StatusUnknown && current.Status != state.StatusFailed && current.Status != state.StatusLaunching {
			return nil, fmt.Errorf("profile state %q cannot be reset", current.Status)
		}
		current.Status = state.StatusStopped
		current.SessionID = ""
		current.LastError = "operator reset"
		return current, nil
	})
}

func (s *Service) ensureHome(ctx context.Context, homeName string) error {
	homes, err := s.orchestrator.ListHomeDirectories(ctx)
	if err != nil {
		return err
	}
	if contains(homes, homeName) {
		return nil
	}
	idempotency, err := randomID()
	if err != nil {
		return err
	}
	if err := s.orchestrator.CreateHomeDirectory(ctx, homeName, idempotency); err == nil {
		return nil
	} else {
		// Home creation is naturally reconcilable by name.
		homes, listErr := s.orchestrator.ListHomeDirectories(ctx)
		if listErr == nil && contains(homes, homeName) {
			return nil
		}
		return err
	}
}

func (s *Service) prepareLaunch(profileID string) (state.Binding, error) {
	operationID, err := randomID()
	if err != nil {
		return state.Binding{}, err
	}
	idempotencyKey, err := randomID()
	if err != nil {
		return state.Binding{}, err
	}
	bootstrap := *s.publicBase
	bootstrap.Path = "/bootstrap/" + url.PathEscape(profileID) + "/" + operationID
	bootstrap.RawPath = ""
	definition, _ := s.directory.get(profileID)
	binding := state.Binding{
		Status: state.StatusLaunching, OperationID: operationID,
		IdempotencyKey: idempotencyKey, BootstrapURL: bootstrap.String(),
		HomeName: definition.HomeName, ApplicationID: definition.ApplicationID,
		NetworkPolicyID: definition.NetworkPolicyID, NetworkPolicySHA256: definition.NetworkPolicySHA256,
	}
	err = s.store.Update(profileID, func(current *state.Binding) (*state.Binding, error) {
		if current != nil && current.Status != state.StatusStopped && current.Status != state.StatusFailed {
			return nil, ErrOperationRunning
		}
		return &binding, nil
	})
	return binding, err
}

func (s *Service) reconcileExisting(profileID string, binding state.Binding, sessions []sealskin.Session) (sealskin.Session, error) {
	definition, _ := s.directory.get(profileID)
	matches := findByMarker(sessions, binding.BootstrapURL, definition.ApplicationID)
	if len(matches) == 1 {
		if err := s.bindRunning(profileID, binding.OperationID, matches[0].SessionID); err != nil {
			return sealskin.Session{}, err
		}
		return matches[0], nil
	}
	if len(matches) > 1 {
		if err := s.mark(profileID, binding.OperationID, state.StatusUnknown, "multiple sessions match launch marker"); err != nil {
			return sealskin.Session{}, err
		}
		return sealskin.Session{}, ErrOwnershipUnknown
	}
	if binding.Status == state.StatusLaunching {
		return sealskin.Session{}, ErrOperationRunning
	}
	return sealskin.Session{}, ErrOwnershipUnknown
}

func (s *Service) bindRunning(profileID, operationID, sessionID string) error {
	return s.store.Update(profileID, func(current *state.Binding) (*state.Binding, error) {
		if current == nil || current.OperationID != operationID {
			return nil, errors.New("launch ownership changed before it could be persisted")
		}
		if current.Status == state.StatusStopping {
			return nil, ErrOperationRunning
		}
		current.Status = state.StatusRunning
		current.SessionID = sessionID
		current.LastError = ""
		// A running binding ends any resume episode; the next dormant episode
		// must use a fresh idempotency key or SealSkin would replay this result.
		current.ResumeIdempotencyKey = ""
		return current, nil
	})
}

func (s *Service) mark(profileID, operationID string, status state.Status, detail string) error {
	return s.store.Update(profileID, func(current *state.Binding) (*state.Binding, error) {
		if current == nil || current.OperationID != operationID {
			return nil, errors.New("profile ownership changed")
		}
		current.Status = status
		current.LastError = detail
		return current, nil
	})
}

func (s *Service) profileLock(profileID string) *sync.Mutex {
	s.locksMu.Lock()
	defer s.locksMu.Unlock()
	if s.locks[profileID] == nil {
		s.locks[profileID] = &sync.Mutex{}
	}
	return s.locks[profileID]
}

func findByID(sessions []sealskin.Session, id string) (sealskin.Session, bool) {
	for _, session := range sessions {
		if session.SessionID == id {
			return session, true
		}
	}
	return sealskin.Session{}, false
}

func findByMarker(sessions []sealskin.Session, marker, appID string) []sealskin.Session {
	var matches []sealskin.Session
	for _, session := range sessions {
		if session.AppID == appID && session.LaunchContext != nil &&
			session.LaunchContext.Type == "url" && session.LaunchContext.Value == marker {
			matches = append(matches, session)
		}
	}
	return matches
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func randomID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	return hex.EncodeToString(value), nil
}

// DisplayLabel returns the configured label or, when none is set, the ID.
func (d Definition) DisplayLabel() string {
	if d.Label == "" {
		return d.ID
	}
	return d.Label
}

func validLabel(label string) bool {
	if label == "" {
		return true
	}
	if !utf8.ValidString(label) || utf8.RuneCountInString(label) > 64 || strings.TrimSpace(label) != label {
		return false
	}
	for _, char := range label {
		if !unicode.IsPrint(char) {
			return false
		}
	}
	return true
}

func validateDefinition(definition Definition) error {
	if definition.ID == "" || definition.ApplicationID == "" || definition.HomeName == "" || definition.StartURL == "" {
		return errors.New("id, application_id, home_name and start_url are required")
	}
	if !validLabel(definition.Label) {
		return errors.New("label must be at most 64 printable characters without surrounding whitespace")
	}
	for name, version := range definition.RequiredRuntimeCapabilities {
		if version != 1 || (name != "browser_shutdown_version" && name != "session_auth_version") {
			return errors.New("required_runtime_capabilities supports browser_shutdown_version and session_auth_version at version 1")
		}
	}
	if policy := definition.IdlePolicy; policy != nil {
		switch policy.Mode {
		case "off", "disconnected":
		case "input_idle":
			return errors.New("idle_policy.mode input_idle is not supported: no verified input activity source exists")
		default:
			return errors.New("idle_policy.mode must be off or disconnected")
		}
		if policy.Mode == "disconnected" && (policy.TimeoutSeconds < 60 || policy.TimeoutSeconds > 86400) {
			return errors.New("idle_policy.timeout_seconds must be between 60 and 86400")
		}
	}
	if !sealskin.ValidNetworkPolicyReference(definition.NetworkPolicyID, definition.NetworkPolicySHA256) {
		return errors.New("network_policy_id and network_policy_sha256 must identify one complete immutable revision")
	}
	if definition.NetworkMode != "" && definition.NetworkMode != "legacy" && definition.NetworkMode != "direct" && definition.NetworkMode != "proxy_required" {
		return errors.New("network_mode must be legacy, direct or proxy_required")
	}
	if definition.ProxySecretVersion < 0 || definition.ProxySecretVersion > 999999999 {
		return errors.New("proxy_secret_version is out of range")
	}
	if (definition.ProxyUsernameSecretRef == "") != (definition.ProxyPasswordSecretRef == "") {
		return errors.New("proxy secret references must be paired")
	}
	if definition.ProxyUsernameSecretRef != "" {
		if !sealskin.ValidSecretReference(definition.ProxyUsernameSecretRef, "username") || !sealskin.ValidSecretReference(definition.ProxyPasswordSecretRef, "password") {
			return errors.New("proxy secret references are invalid")
		}
		if definition.NetworkMode != "proxy_required" {
			return errors.New("proxy secret references require network_mode proxy_required")
		}
	}
	if definition.ProxyUpstream != "" && (definition.NetworkMode != "proxy_required" || len(definition.ProxyUpstream) > 300 || strings.ContainsAny(definition.ProxyUpstream, "@ \t\n")) {
		return errors.New("proxy_upstream must be a protocol://host:port summary of a proxy_required browser")
	}
	if definition.EnvironmentArtifactID != "" {
		if len(definition.EnvironmentArtifactSHA256) != 64 || strings.ToLower(definition.EnvironmentArtifactSHA256) != definition.EnvironmentArtifactSHA256 {
			return errors.New("environment artifact must carry a lowercase SHA-256")
		}
		if _, err := hex.DecodeString(definition.EnvironmentArtifactSHA256); err != nil {
			return errors.New("environment artifact SHA-256 is invalid")
		}
		if definition.EnvironmentSource != "frozen" && definition.EnvironmentSource != "custom" {
			return errors.New("new browser environments must come from a frozen or custom accepted artifact")
		}
	}
	for _, value := range []string{definition.ID, definition.HomeName} {
		for _, char := range value {
			if !((char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') ||
				(char >= '0' && char <= '9') || char == '_' || char == '-') {
				return fmt.Errorf("%q may contain only letters, digits, underscore and hyphen", value)
			}
		}
	}
	start, err := url.Parse(definition.StartURL)
	if err != nil || (start.Scheme != "https" && start.Scheme != "http") || start.Host == "" {
		return errors.New("start_url must be an absolute HTTP(S) URL")
	}
	if start.User != nil {
		return errors.New("start_url must not contain user credentials")
	}
	return nil
}
