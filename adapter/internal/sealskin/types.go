package sealskin

import "fmt"

// LaunchURLRequest mirrors SealSkin's /api/launch/url request.
type LaunchURLRequest struct {
	URL                 string  `json:"url"`
	InitialURL          string  `json:"initial_url,omitempty"`
	ApplicationID       string  `json:"application_id"`
	HomeName            string  `json:"home_name"`
	Language            *string `json:"language,omitempty"`
	Timezone            *string `json:"timezone,omitempty"`
	SelectedGPU         *string `json:"selected_gpu,omitempty"`
	LaunchInRoomMode    bool    `json:"launch_in_room_mode"`
	WaylandMode         bool    `json:"wayland_mode"`
	ProfileID           string  `json:"profile_id,omitempty"`
	OperationID         string  `json:"operation_id,omitempty"`
	NetworkPolicyID     string  `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string  `json:"network_policy_sha256,omitempty"`
}

type LaunchResponse struct {
	SessionURL string `json:"session_url"`
	SessionID  string `json:"session_id"`
}

type LaunchContext struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}

type Session struct {
	SessionID       string         `json:"session_id"`
	AppID           string         `json:"app_id"`
	AppName         string         `json:"app_name"`
	AppLogo         string         `json:"app_logo"`
	CreatedAt       float64        `json:"created_at"`
	SessionURL      string         `json:"session_url"`
	LaunchContext   *LaunchContext `json:"launch_context"`
	IsCollaboration bool           `json:"is_collaboration"`
	HomeName        string         `json:"home_name"`
	InstanceID      string         `json:"instance_id"`
	ProfileID       string         `json:"profile_id"`
	OperationID     string         `json:"operation_id"`
	LifecyclePhase  string         `json:"lifecycle_phase"`
}

// HomeRuntime is a fresh, token-free snapshot from the verified lifecycle API.
// Every container mounting the Home is included, even if it is not owned by
// this deployment or its session record has disappeared.
type HomeRuntime struct {
	Version                   int               `json:"version"`
	HomeName                  string            `json:"home_name"`
	Records                   []RuntimeRecord   `json:"records"`
	Workers                   []RuntimeWorker   `json:"workers"`
	NetworkRuntimeVersion     int               `json:"network_runtime_version,omitempty"`
	NetworkEnforcementVersion int               `json:"network_enforcement_version,omitempty"`
	LaunchJournalVersion      int               `json:"launch_journal_version,omitempty"`
	ProfileInitialURLVersion  int               `json:"profile_initial_url_version,omitempty"`
	CoherenceRuntimeVersion   int               `json:"coherence_runtime_version,omitempty"`
	BrowserShutdownVersion    int               `json:"browser_shutdown_version,omitempty"`
	SessionAuthVersion        int               `json:"session_auth_version,omitempty"`
	Resources                 []RuntimeResource `json:"resources"`
}

// Capabilities reports versions observed from the current controller. Missing
// fields remain zero; an image or a prepared manifest is not runtime evidence.
func (snapshot HomeRuntime) Capabilities() map[string]int {
	return map[string]int{
		"network_runtime_version":     snapshot.NetworkRuntimeVersion,
		"network_enforcement_version": snapshot.NetworkEnforcementVersion,
		"launch_journal_version":      snapshot.LaunchJournalVersion,
		"profile_initial_url_version": snapshot.ProfileInitialURLVersion,
		"coherence_runtime_version":   snapshot.CoherenceRuntimeVersion,
		"browser_shutdown_version":    snapshot.BrowserShutdownVersion,
		"session_auth_version":        snapshot.SessionAuthVersion,
	}
}

type RuntimeRecord struct {
	CoherenceRequired   bool           `json:"coherence_required,omitempty"`
	SessionID           string         `json:"session_id"`
	AppID               string         `json:"app_id"`
	ProfileID           string         `json:"profile_id"`
	OperationID         string         `json:"operation_id"`
	NetworkPolicyID     string         `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string         `json:"network_policy_sha256,omitempty"`
	InstanceIDs         []string       `json:"instance_ids"`
	Phase               string         `json:"phase"`
	LaunchContext       *LaunchContext `json:"launch_context"`
	IsCollaboration     bool           `json:"is_collaboration"`
}

type RuntimeWorker struct {
	InstanceID          string `json:"instance_id"`
	SessionID           string `json:"session_id"`
	AppID               string `json:"app_id"`
	ProfileID           string `json:"profile_id"`
	OperationID         string `json:"operation_id"`
	NetworkPolicyID     string `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string `json:"network_policy_sha256,omitempty"`
	Status              string `json:"status"`
	Owned               bool   `json:"owned"`
	Managed             bool   `json:"managed"`
	Recorded            bool   `json:"recorded"`
}

// RuntimeResource reserves a Home even when no Worker or Session exists.
type RuntimeResource struct {
	ID           string `json:"id"`
	Kind         string `json:"kind"`
	Owned        bool   `json:"owned"`
	Recorded     bool   `json:"recorded"`
	Status       string `json:"status"`
	ProfileID    string `json:"profile_id"`
	OperationID  string `json:"operation_id"`
	AppID        string `json:"app_id"`
	PolicyID     string `json:"policy_id"`
	PolicySHA256 string `json:"policy_sha256"`
}

type StopProfileRequest struct {
	ProfileID           string `json:"profile_id"`
	OperationID         string `json:"operation_id"`
	ApplicationID       string `json:"application_id"`
	SessionID           string `json:"session_id"`
	BootstrapURL        string `json:"bootstrap_url"`
	NetworkPolicyID     string `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string `json:"network_policy_sha256,omitempty"`
}

type HomeDirectories struct {
	HomeDirs []string `json:"home_dirs"`
}

type UserSettings struct {
	Active            bool   `json:"active"`
	Group             string `json:"group"`
	PersistentStorage bool   `json:"persistent_storage"`
	PublicSharing     bool   `json:"public_sharing"`
	HardenContainer   bool   `json:"harden_container"`
	HardenOpenbox     bool   `json:"harden_openbox"`
	GPU               bool   `json:"gpu"`
	StorageLimit      int    `json:"storage_limit"`
	SessionLimit      int    `json:"session_limit"`
}

type CreateUserRequest struct {
	Username  string       `json:"username"`
	PublicKey string       `json:"public_key"`
	Settings  UserSettings `json:"settings"`
}

type CreatedUser struct {
	Username  string        `json:"username"`
	PublicKey string        `json:"public_key"`
	IsAdmin   bool          `json:"is_admin"`
	Settings  *UserSettings `json:"settings"`
}

type CreateUserResponse struct {
	User       CreatedUser `json:"user"`
	PrivateKey *string     `json:"private_key"`
}

type EnvVar struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

type InstalledAppProviderConfig struct {
	Image               string         `json:"image"`
	Env                 []EnvVar       `json:"env"`
	DockerOverrides     map[string]any `json:"docker_overrides"`
	NetworkPolicyID     string         `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string         `json:"network_policy_sha256,omitempty"`
}

type InstalledApp struct {
	ID             string                     `json:"id"`
	ProviderConfig InstalledAppProviderConfig `json:"provider_config"`
}

type APIError struct {
	StatusCode int
	Detail     string
}

func (e *APIError) Error() string {
	// Detail is available for typed protocol classification, never ordinary
	// error text: validation/library responses may include supplied secrets.
	return fmt.Sprintf("SealSkin API returned HTTP %d", e.StatusCode)
}

// AmbiguousMutationError means the caller cannot prove whether a mutating
// request ran. Retrying it with a new SealSkin crypto session may duplicate
// the action because SealSkin's idempotency cache is process-local.
type AmbiguousMutationError struct {
	Operation string
	Cause     error
}

func (e *AmbiguousMutationError) Error() string {
	return "SealSkin request result is ambiguous"
}

func (e *AmbiguousMutationError) Unwrap() error { return e.Cause }

// HomeHealth is a fresh, token-free runtime observation from the health API.
// It never contains display credentials, environment values or command lines.
type HomeHealth struct {
	Coherence  *CoherenceReport `json:"coherence,omitempty"`
	Version    int              `json:"version"`
	HomeName   string           `json:"home_name"`
	ObservedAt float64          `json:"observed_at"`
	Runtime    HomeRuntime      `json:"runtime"`
	Workers    []WorkerHealth   `json:"workers"`
	Network    *NetworkHealth   `json:"network"`
}

type WorkerHealth struct {
	InstanceID  string              `json:"instance_id"`
	SessionID   string              `json:"session_id"`
	Owned       bool                `json:"owned"`
	Recorded    bool                `json:"recorded"`
	Status      string              `json:"status"`
	StartedAt   string              `json:"started_at"`
	NetworkMode string              `json:"network_mode"`
	Environment EnvironmentIdentity `json:"environment"`
	Processes   ProcessSummary      `json:"processes"`
	Display     ObservedCheck       `json:"display"`
	// DisplayConnections counts Caddy-held authenticated connections to the
	// Worker's display port; -1 means the observation was not possible.
	DisplayConnections int `json:"display_connections"`
}

type EnvironmentIdentity struct {
	ID             string `json:"id"`
	ArtifactSHA256 string `json:"artifact_sha256"`
}

// ProcessSummary counts classified processes; Error replaces the counts when
// the container's process table could not be read.
type ProcessSummary struct {
	Error         string   `json:"error,omitempty"`
	Total         int      `json:"total"`
	BrowserMain   int      `json:"browser_main"`
	BrowserChild  int      `json:"browser_child"`
	DisplayServer []string `json:"display_server"`
	Streamer      int      `json:"streamer"`
}

// ObservedCheck is one bounded probe result with a stable code.
type ObservedCheck struct {
	Status     string  `json:"status"`
	Code       string  `json:"code"`
	LatencyMS  int     `json:"latency_ms,omitempty"`
	Detail     string  `json:"detail,omitempty"`
	MeasuredAt float64 `json:"measured_at,omitempty"`
	HTTPStatus string  `json:"http_status,omitempty"`
	Reply      int     `json:"reply,omitempty"`
}

type NetworkHealth struct {
	Mode               string         `json:"mode,omitempty"`
	ApprovedResolverID string         `json:"approved_resolver_id,omitempty"`
	Phase              string         `json:"phase"`
	PolicyID           string         `json:"policy_id"`
	PolicySHA256       string         `json:"policy_sha256"`
	EnforcementVersion int            `json:"enforcement_version"`
	Code               string         `json:"code,omitempty"`
	Relay              RelayHealth    `json:"relay"`
	Guard              GuardHealth    `json:"guard"`
	WorkerNamespace    *bool          `json:"worker_namespace"`
	Upstream           *ObservedCheck `json:"upstream"`
}

type RelayHealth struct {
	Container string `json:"container"`
	Status    string `json:"status"`
	Code      string `json:"code"`
	LatencyMS int    `json:"latency_ms,omitempty"`
}

type GuardHealth struct {
	Container string `json:"container"`
}

// ResumeResult reports an ordered resume of one dormant generation.
type ResumeResult struct {
	Resumed    bool     `json:"resumed"`
	State      string   `json:"state"`
	SessionID  string   `json:"session_id"`
	InstanceID string   `json:"instance_id"`
	Steps      []string `json:"steps"`
}
