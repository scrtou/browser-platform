// Package spec defines reference wire contracts for design.md sections 45-50.
// These declarations do not implement validation, orchestration, or a service.
package spec

import (
	"encoding/json"
	"time"
)

type RevisionRef struct {
	ID       string `json:"id"`
	Revision int    `json:"revision"`
}

// SecretRef is an opaque locator with a pinned credential version, not a path
// accepted from the browser and never the secret value itself.
type SecretRef string

type LocationExpectation struct {
	Country string `json:"country,omitempty"`
	Region  string `json:"region,omitempty"`
	City    string `json:"city,omitempty"`
}

type ProxyConfig struct {
	ID                string              `json:"id"`
	Revision          int                 `json:"revision"`
	Name              string              `json:"name"`
	Type              string              `json:"type"` // http | https | socks5
	Host              string              `json:"host"`
	Port              int                 `json:"port"`
	UsernameSecretRef *SecretRef          `json:"usernameSecretRef,omitempty"`
	PasswordSecretRef *SecretRef          `json:"passwordSecretRef,omitempty"`
	ExpectedLocation  LocationExpectation `json:"expectedLocation"`
	Enabled           bool                `json:"enabled"`
}

type CoherencePolicy struct {
	Mode             string   `json:"mode"` // advisory | strict
	AllowedCountries []string `json:"allowedCountries"`
	AllowedTimezones []string `json:"allowedTimezones"`
	OnExitChange     string   `json:"onExitChange"` // recheck | block
}

type NetworkPolicy struct {
	ID                  string          `json:"id"`
	Revision            int             `json:"revision"`
	Mode                string          `json:"mode"` // direct | proxy_required
	DNSMode             string          `json:"dnsMode"` // upstream | approved_resolver
	WebRTCPolicy        string          `json:"webrtcPolicy"` // disabled | relay_only
	IPv6Policy          string          `json:"ipv6Policy"` // blocked | enforced
	AllowedLANCIDRs     []string        `json:"allowedLanCidrs"`
	ApprovedResolverIDs []string        `json:"approvedResolverIds"`
	ProbeEndpointID     string          `json:"probeEndpointId"`
	ProbeTimeoutSeconds int             `json:"probeTimeoutSeconds"`
	ProbeTTLSeconds     int             `json:"probeTtlSeconds"`
	Coherence           CoherencePolicy `json:"coherence"`
}

type ScreenSpec struct {
	Width             int     `json:"width"`
	Height            int     `json:"height"`
	DeviceScaleFactor float64 `json:"deviceScaleFactor"`
}

// Optional constraints: support must be declared by a tested engine adapter.
// memoryGb is not a Docker memory limit or a promise to expose deviceMemory.
type HardwareSpec struct {
	CPUCores *int     `json:"cpuCores,omitempty"`
	MemoryGB *float64 `json:"memoryGb,omitempty"`
}

type GeolocationSpec struct {
	Mode           string   `json:"mode"` // disabled | fixed | from_proxy_on_create
	Latitude       *float64 `json:"latitude,omitempty"`
	Longitude      *float64 `json:"longitude,omitempty"`
	AccuracyMeters *float64 `json:"accuracyMeters,omitempty"`
}

type BrowserEnvironment struct {
	ID                   string          `json:"id"`
	Revision             int             `json:"revision"`
	Name                 string          `json:"name"`
	Engine               string          `json:"engine"`
	OSFamily             string          `json:"osFamily"`
	Locale               string          `json:"locale"`
	Languages            []string        `json:"languages"`
	Timezone             string          `json:"timezone"`
	Screen               ScreenSpec      `json:"screen"`
	Hardware             HardwareSpec    `json:"hardware"`
	Geolocation          GeolocationSpec `json:"geolocation"`
	RequiredCapabilities []string        `json:"requiredCapabilities"`
}

type EnvironmentArtifact struct {
	ID                string          `json:"id"`
	Environment       RevisionRef     `json:"environment"`
	Engine            string          `json:"engine"`
	EngineVersion     string          `json:"engineVersion"`
	GeneratorVersion  string          `json:"generatorVersion"`
	AdapterVersion    string          `json:"adapterVersion"`
	WorkerImageDigest string          `json:"workerImageDigest"`
	ArtifactSHA256    string          `json:"artifactSha256"`
	ResolvedConfig    json.RawMessage `json:"resolvedConfig"`
	CreatedAt         time.Time       `json:"createdAt"`
}

type IdlePolicy struct {
	Mode           string `json:"mode"` // disconnected | input_idle
	TimeoutSeconds int    `json:"timeoutSeconds"`
}

type ResourceLimits struct {
	CPUMillis   int   `json:"cpuMillis"`
	MemoryBytes int64 `json:"memoryBytes"`
	ShmBytes    int64 `json:"shmBytes"`
	PidsLimit   int   `json:"pidsLimit"`
}

type Profile struct {
	ID                    string         `json:"id"`
	Name                  string         `json:"name"`
	Engine                string         `json:"engine"`
	PersistentHome        string         `json:"persistentHome"`
	Proxy                 *RevisionRef   `json:"proxy,omitempty"`
	NetworkPolicy         RevisionRef    `json:"networkPolicy"`
	Environment           RevisionRef    `json:"environment"`
	EnvironmentArtifactID *string        `json:"environmentArtifactId,omitempty"`
	StartURL              string         `json:"startUrl"`
	IdlePolicy            IdlePolicy     `json:"idlePolicy"`
	ResourceLimits        ResourceLimits `json:"resourceLimits"`
	Enabled               bool           `json:"enabled"`
	ConfigRevision        int            `json:"configRevision"`
}

type ConfigurationExample struct {
	SchemaVersion string               `json:"schemaVersion"`
	Proxies       []ProxyConfig        `json:"proxies"`
	Policies      []NetworkPolicy      `json:"networkPolicies"`
	Environments  []BrowserEnvironment `json:"environments"`
	Profiles      []Profile            `json:"profiles"`
}

type ProxyObservation struct {
	ID              string       `json:"id"`
	ProfileID       string       `json:"profileId"`
	OperationID     string       `json:"operationId"`
	Proxy           *RevisionRef `json:"proxy,omitempty"`
	NetworkPolicy   RevisionRef  `json:"networkPolicy"`
	ProbeEndpointID string       `json:"probeEndpointId"`
	MeasuredAt      time.Time    `json:"measuredAt"`
	ExpiresAt       time.Time    `json:"expiresAt"`
	Status          string       `json:"status"` // pass | fail | unknown
	PublicIPv4      string       `json:"publicIpv4,omitempty"`
	PublicIPv6      string       `json:"publicIpv6,omitempty"`
	LatencyMS       *int64       `json:"latencyMs,omitempty"`
	Country         string       `json:"country,omitempty"`
	Region          string       `json:"region,omitempty"`
	City            string       `json:"city,omitempty"`
	GeoSource       string       `json:"geoSource,omitempty"`
	GeoConfidence   string       `json:"geoConfidence"`
	ErrorCode       string       `json:"errorCode,omitempty"`
}

type HealthCheck struct {
	Name     string `json:"name"`
	Status   string `json:"status"` // pass | fail | warn | unknown | not_applicable
	Required bool   `json:"required"`
	Code     string `json:"code"`
	Message  string `json:"message"` // generated from safe templates, no raw exceptions
}

type HealthReport struct {
	ID                string            `json:"id"`
	ProfileID         string            `json:"profileId"`
	OperationID       string            `json:"operationId,omitempty"`
	ExternalSessionID string            `json:"externalSessionId,omitempty"`
	CheckedAt         time.Time         `json:"checkedAt"`
	ExpiresAt         time.Time         `json:"expiresAt"`
	Overall           string            `json:"overall"`
	Engine            string            `json:"engine"`
	Environment       RevisionRef       `json:"environment"`
	NetworkPolicy     RevisionRef       `json:"networkPolicy"`
	Observation       *ProxyObservation `json:"observation,omitempty"`
	Checks            []HealthCheck     `json:"checks"`
}
