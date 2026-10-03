package profile

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
	_ "time/tzdata" // IANA names are validated the same way on hosts without zoneinfo.
)

const (
	environmentJobRequestVersion = 1
	environmentJobStatusVersion  = 1
	maxPendingEnvironmentJobs    = 4
	maxListedEnvironmentJobs     = 100
)

var (
	ErrEnvironmentJobsUnavailable = errors.New("custom environment jobs require environment_job_spool")
	ErrEnvironmentJobInvalid      = errors.New("environment job request is invalid")
	ErrEnvironmentJobsBusy        = errors.New("too many environment jobs are still queued or running")
	ErrEnvironmentJobNotFound     = errors.New("environment job not found")

	languageTag = regexp.MustCompile(`^[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*$`)
	jobIDForm   = regexp.MustCompile(`^job-[a-f0-9]{16}$`)
)

// EnvironmentJobRequest carries only the high-level fields of specification
// 46.2 that the current Camoufox adapter can honour. Everything else in the
// generated specification is fixed by the server.
type EnvironmentJobRequest struct {
	DisplayMode  string
	Generation   *GenerationTarget
	Templates    *TemplateSourceRef
	Locale       string
	Languages    []string
	Timezone     string
	ScreenWidth  int
	ScreenHeight int
	DPR          float64
	WindowWidth  int
	WindowHeight int
}

// environmentSpec is the exact specification the runner validates again with
// environment.validate_spec; field names follow the Camoufox artifact schema.
type environmentSpec struct {
	ID                   string          `json:"id"`
	Revision             int             `json:"revision"`
	OSFamily             string          `json:"osFamily"`
	Locale               string          `json:"locale"`
	Languages            []string        `json:"languages"`
	Timezone             string          `json:"timezone"`
	Screen               environmentSize `json:"screen"`
	Window               environmentSize `json:"window"`
	WebRTCPolicy         string          `json:"webrtcPolicy"`
	GeolocationPolicy    string          `json:"geolocationPolicy"`
	RequiredCapabilities []string        `json:"requiredCapabilities"`
}

type environmentSize struct {
	Mode              string   `json:"mode,omitempty"`
	DPRMode           string   `json:"dprMode,omitempty"`
	Width             int      `json:"width"`
	Height            int      `json:"height"`
	DeviceScaleFactor *float64 `json:"deviceScaleFactor,omitempty"`
}

type environmentJobRequestFile struct {
	Generation  *GenerationTarget  `json:"generation,omitempty"`
	Templates   *TemplateSourceRef `json:"templates,omitempty"`
	Version     int                `json:"version"`
	JobID       string             `json:"job_id"`
	Actor       string             `json:"actor"`
	RequestedAt string             `json:"requested_at"`
	Spec        environmentSpec    `json:"spec"`
}

type environmentJobStatusFile struct {
	Version          int    `json:"version"`
	JobID            string `json:"job_id"`
	UpdatedAt        string `json:"updated_at"`
	Status           string `json:"status"`
	Phase            string `json:"phase"`
	Code             string `json:"code,omitempty"`
	Message          string `json:"message,omitempty"`
	StartedAt        string `json:"started_at,omitempty"`
	FinishedAt       string `json:"finished_at,omitempty"`
	Image            string `json:"image,omitempty"`
	Attempts         int    `json:"attempts,omitempty"`
	ArtifactID       string `json:"artifact_id,omitempty"`
	ArtifactSHA256   string `json:"artifact_sha256,omitempty"`
	AcceptanceSHA256 string `json:"acceptance_sha256,omitempty"`
	EnvironmentID    string `json:"environment_id,omitempty"`
}

// EnvironmentJobSummary is the management view of one job. It carries no
// generated device values: only the requested high-level fields, the runner's
// stable codes and the digests of a published result.
type EnvironmentJobSummary struct {
	Generation            *GenerationTarget `json:"generation,omitempty"`
	FingerprintTemplateID string            `json:"fingerprint_template_id,omitempty"`
	DisplayPresetID       string            `json:"display_preset_id,omitempty"`
	ID                    string            `json:"id"`
	EnvironmentID         string            `json:"environment_id"`
	Actor                 string            `json:"actor"`
	RequestedAt           string            `json:"requested_at"`
	Locale                string            `json:"locale"`
	Languages             []string          `json:"languages"`
	Timezone              string            `json:"timezone"`
	Screen                string            `json:"screen"`
	Window                string            `json:"window"`
	Status                string            `json:"status"`
	Phase                 string            `json:"phase,omitempty"`
	Code                  string            `json:"code,omitempty"`
	Message               string            `json:"message,omitempty"`
	UpdatedAt             string            `json:"updated_at,omitempty"`
	FinishedAt            string            `json:"finished_at,omitempty"`
	Attempts              int               `json:"attempts,omitempty"`
	ArtifactSHA256        string            `json:"artifact_sha256,omitempty"`
	AcceptanceSHA256      string            `json:"acceptance_sha256,omitempty"`
	requestedAt           time.Time         // for ordering only
}

// WithEnvironmentJobs enables custom fingerprint jobs through a private spool
// directory shared with the host-side runner. The Adapter only writes
// requests and reads status files; it never runs Docker.
func WithEnvironmentJobs(spool string) Option {
	return func(s *Service) { s.jobSpool = filepath.Clean(spool) }
}

func validateEnvironmentJob(request EnvironmentJobRequest) (environmentSpec, error) {
	fail := func(reason string) (environmentSpec, error) {
		return environmentSpec{}, fmt.Errorf("%w: %s", ErrEnvironmentJobInvalid, reason)
	}
	if len(request.Languages) == 0 || len(request.Languages) > 10 {
		return fail("between 1 and 10 languages are required")
	}
	seen := make(map[string]bool, len(request.Languages))
	for _, tag := range request.Languages {
		if !languageTag.MatchString(tag) || seen[tag] {
			return fail("languages must be unique BCP 47 tags")
		}
		seen[tag] = true
	}
	if request.Locale != request.Languages[0] {
		return fail("locale must equal the first language")
	}
	if request.Timezone == "" || request.Timezone == "Local" || len(request.Timezone) > 64 || strings.ContainsAny(request.Timezone, " \t\n") {
		return fail("timezone must be an IANA name")
	}
	if _, err := time.LoadLocation(request.Timezone); err != nil {
		return fail("timezone must be an IANA name")
	}
	if request.ScreenWidth < 640 || request.ScreenWidth > 3840 || request.ScreenHeight < 480 || request.ScreenHeight > 2160 {
		return fail("screen must be between 640x480 and 3840x2160")
	}
	auto := request.DisplayMode == "auto"
	if request.DisplayMode != "" && request.DisplayMode != "fixed" && !auto {
		return fail("unsupported display mode")
	}
	if auto && (request.Generation == nil || request.Templates == nil || request.Templates.DisplayID != builtinDisplayID || request.ScreenWidth != 1280 || request.ScreenHeight != 720 || request.DPR != 0) {
		return fail("invalid built-in automatic display")
	}
	if !auto && request.DPR != 1 {
		// The verified adapter only covers X11 at DPR 1; refusing keeps the
		// capability matrix honest instead of publishing an unverified field.
		return fail("UNSUPPORTED_CAPABILITY: deviceScaleFactor must be 1")
	}
	if request.WindowWidth == 0 && request.WindowHeight == 0 {
		request.WindowWidth, request.WindowHeight = request.ScreenWidth, request.ScreenHeight
	}
	if request.WindowWidth < 640 || request.WindowWidth > request.ScreenWidth || request.WindowHeight < 480 || request.WindowHeight > request.ScreenHeight {
		return fail("window must fit the screen and be at least 640x480")
	}
	dpr := 1.0
	webrtcPolicy, webrtcCapability := "disabled", "webrtc-disabled"
	if request.Generation != nil && request.Generation.Engine == "chromix" {
		webrtcPolicy, webrtcCapability = "proxy-only", "webrtc-proxy-only"
	}
	screen := environmentSize{Width: request.ScreenWidth, Height: request.ScreenHeight, DeviceScaleFactor: &dpr}
	capabilities := []string{"locale", "languages", "timezone", "fixed-screen", "fixed-dpr", "frozen-device-config", webrtcCapability, "proxy-only"}
	if auto {
		screen.DeviceScaleFactor = nil
		screen.Mode = "auto"
		screen.DPRMode = "system"
		capabilities[3] = "auto-screen"
		capabilities[4] = "system-dpr"
	}
	return environmentSpec{
		Revision: 1, OSFamily: "linux", Locale: request.Locale, Languages: append([]string(nil), request.Languages...), Timezone: request.Timezone,
		Screen:       screen,
		Window:       environmentSize{Width: request.WindowWidth, Height: request.WindowHeight},
		WebRTCPolicy: webrtcPolicy, GeolocationPolicy: "disabled",
		RequiredCapabilities: capabilities,
	}, nil
}

func (s *Service) spoolReady() error {
	if s.jobSpool == "" || s.catalog == nil {
		return ErrEnvironmentJobsUnavailable
	}
	info, err := os.Lstat(s.jobSpool)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0o077 != 0 {
		return fmt.Errorf("%w: spool must be a private directory", ErrEnvironmentJobsUnavailable)
	}
	return nil
}

// CreateEnvironmentJob validates the high-level fields, derives the fixed
// specification and durably enqueues it. The runner validates the same
// specification again before generating anything.
func (s *Service) CreateEnvironmentJob(ctx context.Context, actor string, request EnvironmentJobRequest) (EnvironmentJobSummary, error) {
	if err := ctx.Err(); err != nil {
		return EnvironmentJobSummary{}, err
	}
	if err := s.spoolReady(); err != nil {
		return EnvironmentJobSummary{}, err
	}
	actor = strings.TrimSpace(actor)
	if !validPolicyName(actor) {
		return EnvironmentJobSummary{}, ErrEnvironmentJobInvalid
	}
	spec, err := validateEnvironmentJob(request)
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	sourceLock := s.profileLock("__template_sources")
	sourceLock.Lock()
	defer sourceLock.Unlock()
	if request.Templates != nil {
		for kind, id := range map[string]string{"fingerprints": request.Templates.FingerprintID, "displays": request.Templates.DisplayID} {
			deleted, err := s.dataDeleted(kind, id)
			if err != nil {
				return EnvironmentJobSummary{}, err
			}
			if deleted {
				return EnvironmentJobSummary{}, ErrDataDeleted
			}
		}
	}
	lock := s.profileLock("__environment_jobs")
	lock.Lock()
	defer lock.Unlock()
	jobs, err := s.EnvironmentJobs()
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	pending := 0
	for _, job := range jobs {
		if job.Status == "queued" || job.Status == "running" {
			pending++
		}
	}
	if pending >= maxPendingEnvironmentJobs {
		return EnvironmentJobSummary{}, ErrEnvironmentJobsBusy
	}
	random, err := randomID()
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	jobID := "job-" + random[:16]
	spec.ID = "env-custom-" + random[:16]
	version := environmentJobRequestVersion
	if request.Templates != nil {
		version = 2
	}
	if request.Generation != nil {
		targets, err := s.generationTargets(ctx)
		if err != nil {
			return EnvironmentJobSummary{}, err
		}
		valid := false
		for _, target := range targets {
			if target == *request.Generation {
				valid = true
			}
		}
		if request.Templates == nil || !valid {
			return EnvironmentJobSummary{}, ErrEnvironmentJobInvalid
		}
		version = 3
	}
	file := environmentJobRequestFile{Generation: request.Generation, Templates: request.Templates, Version: version, JobID: jobID, Actor: actor, RequestedAt: s.now().UTC().Format(time.RFC3339Nano), Spec: spec}
	queue := filepath.Join(s.jobSpool, "queue")
	if err := os.MkdirAll(queue, 0700); err != nil {
		return EnvironmentJobSummary{}, err
	}
	info, err := os.Lstat(queue)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
		return EnvironmentJobSummary{}, ErrEnvironmentJobsUnavailable
	}
	if err := writeNewTemplate(filepath.Join(queue, jobID+".json"), file); err != nil {
		return EnvironmentJobSummary{}, err
	}
	return summarizeEnvironmentJob(file, nil), nil
}

func summarizeEnvironmentJob(request environmentJobRequestFile, status *environmentJobStatusFile) EnvironmentJobSummary {
	summary := EnvironmentJobSummary{Generation: request.Generation, ID: request.JobID, EnvironmentID: request.Spec.ID, Actor: request.Actor, RequestedAt: request.RequestedAt,
		Locale: request.Spec.Locale, Languages: append([]string(nil), request.Spec.Languages...), Timezone: request.Spec.Timezone,
		Screen: fmt.Sprintf("%dx%d@1", request.Spec.Screen.Width, request.Spec.Screen.Height),
		Window: fmt.Sprintf("%dx%d", request.Spec.Window.Width, request.Spec.Window.Height), Status: "queued"}
	if request.Spec.Screen.Mode == "auto" {
		summary.Screen = "auto@system"
		summary.Window = "auto"
	}
	if request.Templates != nil {
		summary.FingerprintTemplateID = request.Templates.FingerprintID
		summary.DisplayPresetID = request.Templates.DisplayID
	}
	summary.requestedAt, _ = time.Parse(time.RFC3339Nano, request.RequestedAt)
	if status != nil {
		summary.Status, summary.Phase, summary.Code, summary.Message = status.Status, status.Phase, status.Code, status.Message
		summary.UpdatedAt, summary.FinishedAt, summary.Attempts = status.UpdatedAt, status.FinishedAt, status.Attempts
		summary.ArtifactSHA256, summary.AcceptanceSHA256 = status.ArtifactSHA256, status.AcceptanceSHA256
	}
	return summary
}

func readPrivateJSON(path string, limit int64, out any) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("spool file must be a private regular file")
	}
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, limit))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(out); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("spool file contains trailing data")
	}
	return nil
}

// EnvironmentJobs lists requests with their latest runner status, newest
// first. Unreadable or foreign files are skipped rather than surfaced.
func (s *Service) EnvironmentJobs() ([]EnvironmentJobSummary, error) {
	if err := s.spoolReady(); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(filepath.Join(s.jobSpool, "queue"))
	if errors.Is(err, os.ErrNotExist) {
		return []EnvironmentJobSummary{}, nil
	}
	if err != nil {
		return nil, err
	}
	result := make([]EnvironmentJobSummary, 0, len(entries))
	for _, entry := range entries {
		name := strings.TrimSuffix(entry.Name(), ".json")
		if !jobIDForm.MatchString(name) || entry.Name() == name {
			continue
		}
		deleted, err := s.dataDeleted("jobs", name)
		if err != nil {
			return nil, err
		}
		if deleted {
			continue
		}
		var request environmentJobRequestFile
		if err := readPrivateJSON(filepath.Join(s.jobSpool, "queue", entry.Name()), 64<<10, &request); err != nil || (request.Version != environmentJobRequestVersion && request.Version != 2 && request.Version != 3) || request.JobID != name {
			continue
		}
		var status *environmentJobStatusFile
		var file environmentJobStatusFile
		if err := readPrivateJSON(filepath.Join(s.jobSpool, "status", entry.Name()), 64<<10, &file); err == nil && file.Version == environmentJobStatusVersion && file.JobID == name {
			switch file.Status {
			case "queued", "running", "accepted", "failed":
				status = &file
			}
		}
		result = append(result, summarizeEnvironmentJob(request, status))
	}
	sort.Slice(result, func(i, j int) bool {
		if !result[i].requestedAt.Equal(result[j].requestedAt) {
			return result[i].requestedAt.After(result[j].requestedAt)
		}
		return result[i].ID > result[j].ID
	})
	if len(result) > maxListedEnvironmentJobs {
		result = result[:maxListedEnvironmentJobs]
	}
	return result, nil
}

// EnvironmentJob returns one job by ID.
func (s *Service) EnvironmentJob(id string) (EnvironmentJobSummary, error) {
	if !jobIDForm.MatchString(id) {
		return EnvironmentJobSummary{}, ErrEnvironmentJobNotFound
	}
	jobs, err := s.EnvironmentJobs()
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	for _, job := range jobs {
		if job.ID == id {
			return job, nil
		}
	}
	return EnvironmentJobSummary{}, ErrEnvironmentJobNotFound
}
