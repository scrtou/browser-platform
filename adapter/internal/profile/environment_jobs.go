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
	Width             int      `json:"width"`
	Height            int      `json:"height"`
	DeviceScaleFactor *float64 `json:"deviceScaleFactor,omitempty"`
}

type environmentJobRequestFile struct {
	Version     int             `json:"version"`
	JobID       string          `json:"job_id"`
	Actor       string          `json:"actor"`
	RequestedAt string          `json:"requested_at"`
	Spec        environmentSpec `json:"spec"`
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
	ID               string    `json:"id"`
	EnvironmentID    string    `json:"environment_id"`
	Actor            string    `json:"actor"`
	RequestedAt      string    `json:"requested_at"`
	Locale           string    `json:"locale"`
	Languages        []string  `json:"languages"`
	Timezone         string    `json:"timezone"`
	Screen           string    `json:"screen"`
	Window           string    `json:"window"`
	Status           string    `json:"status"`
	Phase            string    `json:"phase,omitempty"`
	Code             string    `json:"code,omitempty"`
	Message          string    `json:"message,omitempty"`
	UpdatedAt        string    `json:"updated_at,omitempty"`
	FinishedAt       string    `json:"finished_at,omitempty"`
	Attempts         int       `json:"attempts,omitempty"`
	ArtifactSHA256   string    `json:"artifact_sha256,omitempty"`
	AcceptanceSHA256 string    `json:"acceptance_sha256,omitempty"`
	requestedAt      time.Time // for ordering only
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
	if request.DPR != 1 {
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
	return environmentSpec{
		Revision: 1, OSFamily: "linux", Locale: request.Locale, Languages: append([]string(nil), request.Languages...), Timezone: request.Timezone,
		Screen:       environmentSize{Width: request.ScreenWidth, Height: request.ScreenHeight, DeviceScaleFactor: &dpr},
		Window:       environmentSize{Width: request.WindowWidth, Height: request.WindowHeight},
		WebRTCPolicy: "disabled", GeolocationPolicy: "disabled",
		RequiredCapabilities: []string{"locale", "languages", "timezone", "fixed-screen", "fixed-dpr", "frozen-device-config", "webrtc-disabled", "proxy-only"},
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
	file := environmentJobRequestFile{Version: environmentJobRequestVersion, JobID: jobID, Actor: actor, RequestedAt: s.now().UTC().Format(time.RFC3339Nano), Spec: spec}
	encoded, err := json.Marshal(file)
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	queue := filepath.Join(s.jobSpool, "queue")
	if err := os.MkdirAll(queue, 0o700); err != nil {
		return EnvironmentJobSummary{}, err
	}
	path := filepath.Join(queue, jobID+".json")
	handle, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return EnvironmentJobSummary{}, fmt.Errorf("enqueue environment job: %w", err)
	}
	if _, err := handle.Write(append(encoded, '\n')); err != nil {
		handle.Close()
		os.Remove(path)
		return EnvironmentJobSummary{}, err
	}
	if err := handle.Sync(); err != nil {
		handle.Close()
		os.Remove(path)
		return EnvironmentJobSummary{}, err
	}
	if err := handle.Close(); err != nil {
		os.Remove(path)
		return EnvironmentJobSummary{}, err
	}
	if dir, err := os.Open(queue); err == nil {
		_ = dir.Sync()
		dir.Close()
	}
	return summarizeEnvironmentJob(file, nil), nil
}

func summarizeEnvironmentJob(request environmentJobRequestFile, status *environmentJobStatusFile) EnvironmentJobSummary {
	summary := EnvironmentJobSummary{ID: request.JobID, EnvironmentID: request.Spec.ID, Actor: request.Actor, RequestedAt: request.RequestedAt,
		Locale: request.Spec.Locale, Languages: append([]string(nil), request.Spec.Languages...), Timezone: request.Spec.Timezone,
		Screen: fmt.Sprintf("%dx%d@1", request.Spec.Screen.Width, request.Spec.Screen.Height),
		Window: fmt.Sprintf("%dx%d", request.Spec.Window.Width, request.Spec.Window.Height), Status: "queued"}
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
		var request environmentJobRequestFile
		if err := readPrivateJSON(filepath.Join(s.jobSpool, "queue", entry.Name()), 64<<10, &request); err != nil || request.Version != environmentJobRequestVersion || request.JobID != name {
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
