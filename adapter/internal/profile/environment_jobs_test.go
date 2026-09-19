package profile

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func jobService(t *testing.T) (*Service, string) {
	t.Helper()
	admin := &managementAdmin{}
	service, _ := managementService(t, admin)
	spool := filepath.Join(t.TempDir(), "jobs")
	if err := os.Mkdir(spool, 0o700); err != nil {
		t.Fatal(err)
	}
	WithEnvironmentJobs(spool)(service)
	return service, spool
}

func jobRequest() EnvironmentJobRequest {
	return EnvironmentJobRequest{Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "America/New_York", ScreenWidth: 1920, ScreenHeight: 1080, DPR: 1}
}

func TestEnvironmentJobValidationMirrorsSpecification(t *testing.T) {
	cases := map[string]func(*EnvironmentJobRequest){
		"locale mismatch":   func(r *EnvironmentJobRequest) { r.Locale = "en-GB" },
		"duplicate":         func(r *EnvironmentJobRequest) { r.Languages = []string{"en-US", "en-US"} },
		"bad tag":           func(r *EnvironmentJobRequest) { r.Languages = []string{"en_US"}; r.Locale = "en_US" },
		"too many":          func(r *EnvironmentJobRequest) { r.Languages = strings.Split("en-US,a,b,c,d,e,f,g,h,i,j", ",") },
		"timezone":          func(r *EnvironmentJobRequest) { r.Timezone = "Mars/Olympus" },
		"timezone local":    func(r *EnvironmentJobRequest) { r.Timezone = "Local" },
		"screen small":      func(r *EnvironmentJobRequest) { r.ScreenWidth = 320 },
		"screen large":      func(r *EnvironmentJobRequest) { r.ScreenHeight = 4000 },
		"dpr":               func(r *EnvironmentJobRequest) { r.DPR = 2 },
		"window too large":  func(r *EnvironmentJobRequest) { r.WindowWidth, r.WindowHeight = 2000, 1080 },
		"window too small":  func(r *EnvironmentJobRequest) { r.WindowWidth, r.WindowHeight = 320, 200 },
		"no languages":      func(r *EnvironmentJobRequest) { r.Languages = nil; r.Locale = "" },
		"path in timezone":  func(r *EnvironmentJobRequest) { r.Timezone = "../../etc/passwd" },
		"space in timezone": func(r *EnvironmentJobRequest) { r.Timezone = "America/New York" },
	}
	for name, mutate := range cases {
		request := jobRequest()
		mutate(&request)
		if _, err := validateEnvironmentJob(request); !errors.Is(err, ErrEnvironmentJobInvalid) {
			t.Fatalf("%s: %v", name, err)
		}
	}
	spec, err := validateEnvironmentJob(jobRequest())
	if err != nil {
		t.Fatal(err)
	}
	if spec.Window != (environmentSize{Width: 1920, Height: 1080}) || spec.OSFamily != "linux" || spec.WebRTCPolicy != "disabled" ||
		spec.GeolocationPolicy != "disabled" || *spec.Screen.DeviceScaleFactor != 1 || len(spec.RequiredCapabilities) != 8 || spec.Revision != 1 {
		t.Fatalf("derived spec: %+v", spec)
	}
	custom := jobRequest()
	custom.WindowWidth, custom.WindowHeight, custom.Timezone, custom.Locale, custom.Languages = 1600, 900, "Asia/Taipei", "zh-TW", []string{"zh-TW", "zh", "en"}
	if spec, err := validateEnvironmentJob(custom); err != nil || spec.Window.Width != 1600 || spec.Timezone != "Asia/Taipei" {
		t.Fatalf("custom window: %+v %v", spec, err)
	}
}

func TestEnvironmentJobsAreDurablyQueuedAndReadBack(t *testing.T) {
	service, spool := jobService(t)
	now := time.Date(2026, 9, 18, 21, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	summary, err := service.CreateEnvironmentJob(context.Background(), "root", jobRequest())
	if err != nil {
		t.Fatal(err)
	}
	if !jobIDForm.MatchString(summary.ID) || summary.EnvironmentID != "env-custom-"+summary.ID[4:] || summary.Status != "queued" || summary.Screen != "1920x1080@1" || summary.Window != "1920x1080" {
		t.Fatalf("summary: %+v", summary)
	}
	path := filepath.Join(spool, "queue", summary.ID+".json")
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("request file: %v %v", info, err)
	}
	var file map[string]any
	if err := json.Unmarshal(mustRead(t, path), &file); err != nil {
		t.Fatal(err)
	}
	spec := file["spec"].(map[string]any)
	if file["version"] != float64(1) || file["actor"] != "root" || spec["id"] != summary.EnvironmentID || spec["osFamily"] != "linux" ||
		spec["geolocationPolicy"] != "disabled" || spec["screen"].(map[string]any)["deviceScaleFactor"] != float64(1) || spec["timezone"] != "America/New_York" {
		t.Fatalf("request content: %v", file)
	}
	jobs, err := service.EnvironmentJobs()
	if err != nil || len(jobs) != 1 || jobs[0].ID != summary.ID || jobs[0].Status != "queued" {
		t.Fatalf("list: %+v %v", jobs, err)
	}
	status := map[string]any{"version": 1, "job_id": summary.ID, "updated_at": "2026-09-18T21:05:00+00:00", "status": "running", "phase": "acceptance",
		"started_at": "2026-09-18T21:01:00+00:00", "image": "sha256:" + strings.Repeat("1", 64), "attempts": 2, "artifact_id": summary.EnvironmentID + "-artifact-1", "artifact_sha256": strings.Repeat("a", 64)}
	writeStatus(t, spool, summary.ID, status)
	job, err := service.EnvironmentJob(summary.ID)
	if err != nil || job.Status != "running" || job.Phase != "acceptance" || job.Attempts != 2 || job.ArtifactSHA256 != strings.Repeat("a", 64) {
		t.Fatalf("running status: %+v %v", job, err)
	}
	status["status"], status["phase"], status["code"], status["message"], status["finished_at"] = "failed", "failed", "ENVIRONMENT_ACCEPTANCE_FAILED", "exit 1", "2026-09-18T21:09:00+00:00"
	writeStatus(t, spool, summary.ID, status)
	job, _ = service.EnvironmentJob(summary.ID)
	if job.Status != "failed" || job.Code != "ENVIRONMENT_ACCEPTANCE_FAILED" || job.FinishedAt == "" {
		t.Fatalf("failed status: %+v", job)
	}
	// Unknown fields, foreign job IDs or wrong versions are ignored, never trusted.
	status["surprise"] = true
	writeStatus(t, spool, summary.ID, status)
	if job, _ = service.EnvironmentJob(summary.ID); job.Status != "queued" {
		t.Fatalf("unknown status fields were accepted: %+v", job)
	}
	delete(status, "surprise")
	status["job_id"] = "job-ffffffffffffffff"
	writeStatus(t, spool, summary.ID, status)
	if job, _ = service.EnvironmentJob(summary.ID); job.Status != "queued" {
		t.Fatalf("foreign status was accepted: %+v", job)
	}
	if _, err := service.EnvironmentJob("job-0000000000000000"); !errors.Is(err, ErrEnvironmentJobNotFound) {
		t.Fatalf("unknown job: %v", err)
	}
	if _, err := service.EnvironmentJob("../queue"); !errors.Is(err, ErrEnvironmentJobNotFound) {
		t.Fatalf("traversal: %v", err)
	}
}

func TestEnvironmentJobsPendingLimitAndSpoolSafety(t *testing.T) {
	service, spool := jobService(t)
	for i := 0; i < maxPendingEnvironmentJobs; i++ {
		if _, err := service.CreateEnvironmentJob(context.Background(), "root", jobRequest()); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := service.CreateEnvironmentJob(context.Background(), "root", jobRequest()); !errors.Is(err, ErrEnvironmentJobsBusy) {
		t.Fatalf("pending limit: %v", err)
	}
	jobs, _ := service.EnvironmentJobs()
	writeStatus(t, spool, jobs[0].ID, map[string]any{"version": 1, "job_id": jobs[0].ID, "updated_at": "x", "status": "accepted", "phase": "done"})
	if _, err := service.CreateEnvironmentJob(context.Background(), "root", jobRequest()); err != nil {
		t.Fatalf("after one finished: %v", err)
	}
	if _, err := service.CreateEnvironmentJob(context.Background(), "root", EnvironmentJobRequest{Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC", ScreenWidth: 1920, ScreenHeight: 1080, DPR: 2}); !errors.Is(err, ErrEnvironmentJobInvalid) {
		t.Fatalf("invalid job enqueued: %v", err)
	}
	if err := os.Chmod(spool, 0o750); err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnvironmentJobs(); !errors.Is(err, ErrEnvironmentJobsUnavailable) {
		t.Fatalf("group-readable spool accepted: %v", err)
	}
	_ = os.Chmod(spool, 0o700)
	service.jobSpool = ""
	if _, err := service.CreateEnvironmentJob(context.Background(), "root", jobRequest()); !errors.Is(err, ErrEnvironmentJobsUnavailable) {
		t.Fatalf("jobs without spool: %v", err)
	}
}

func TestCustomCatalogArtifactsCanBackNewBrowsers(t *testing.T) {
	admin := &managementAdmin{}
	service, _ := managementService(t, admin)
	catalog := service.catalog.(StaticEnvironmentCatalog)
	custom := catalog["env-r9"]
	custom.ID, custom.Source, custom.Locale, custom.Timezone, custom.Screen, custom.AcceptedAt = "env-custom-0123456789abcdef", "custom", "en-US", "America/New_York", "1920x1080@1", "2026-09-18T21:10:00+00:00"
	catalog[custom.ID] = custom
	rejected := custom
	rejected.ID, rejected.Source = "env-unverified", "generated"
	catalog[rejected.ID] = rejected
	artifacts, err := service.EnvironmentArtifacts(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	ids := make([]string, 0, len(artifacts))
	for _, artifact := range artifacts {
		ids = append(ids, artifact.ID+"/"+artifact.Source)
		if artifact.ID == custom.ID && (artifact.Locale != "en-US" || artifact.Screen != "1920x1080@1" || artifact.AcceptedAt == "") {
			t.Fatalf("custom summary lost descriptive fields: %+v", artifact)
		}
	}
	if strings.Join(ids, ",") != "env-custom-0123456789abcdef/custom,env-r9/frozen" {
		t.Fatalf("listed artifacts: %v", ids)
	}
	request := createRequest()
	request.EnvironmentArtifactID = custom.ID
	record, err := service.CreateBrowser(context.Background(), request, "root", "custom-1")
	if err != nil || record.EnvironmentSource != "custom" || record.EnvironmentArtifactID != custom.ID || admin.installCalls != 1 {
		t.Fatalf("browser on custom artifact: %+v %v installs=%d", record, err, admin.installCalls)
	}
	if admin.lastApp["provider_config"].(map[string]any)["docker_overrides"].(map[string]any)["labels"].(map[string]any)["browser-platform.environment"] != custom.ID {
		t.Fatalf("application labels: %+v", admin.lastApp)
	}
	request.EnvironmentArtifactID = rejected.ID
	if _, err := service.CreateBrowser(context.Background(), request, "root", "custom-2"); !errors.Is(err, ErrArtifactUnavailable) {
		t.Fatalf("unverified source accepted: %v", err)
	}
}

func TestFileCatalogAcceptsRunnerEntries(t *testing.T) {
	path := filepath.Join(t.TempDir(), "environment-catalog.json")
	entry := map[string]any{"id": "env-custom-0123456789abcdef", "sha256": strings.Repeat("a", 64), "acceptance_sha256": strings.Repeat("b", 64),
		"image": "sha256:" + strings.Repeat("c", 64), "source": "custom", "status": "accepted",
		"application":                   map[string]any{"id": "app-template", "provider_config": map[string]any{"image": "sha256:" + strings.Repeat("c", 64), "docker_overrides": map[string]any{"labels": map[string]any{}}}},
		"required_runtime_capabilities": map[string]int{"browser_shutdown_version": 1, "session_auth_version": 1},
		"locale":                        "en-US", "languages": []string{"en-US", "en"}, "timezone": "America/New_York", "screen": "1920x1080@1",
		"accepted_at": "2026-09-19T01:32:44.322452+00:00", "job_id": "job-0123456789abcdef"}
	encoded, _ := json.Marshal(map[string]any{"version": 1, "artifacts": []any{entry}})
	if err := os.WriteFile(path, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	catalog, err := NewFileEnvironmentCatalog(path)
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := catalog.Accepted(context.Background(), "env-custom-0123456789abcdef")
	if err != nil || artifact.Source != "custom" || artifact.Locale != "en-US" || artifact.JobID != "job-0123456789abcdef" || len(artifact.Languages) != 2 {
		t.Fatalf("runner entry: %+v %v", artifact, err)
	}
	if err := os.Chmod(path, 0o640); err != nil {
		t.Fatal(err)
	}
	if _, err := catalog.Accepted(context.Background(), "env-custom-0123456789abcdef"); !errors.Is(err, ErrArtifactUnavailable) {
		t.Fatalf("group-readable catalog accepted: %v", err)
	}
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func writeStatus(t *testing.T, spool, jobID string, status map[string]any) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(spool, "status"), 0o700); err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(status)
	if err := os.WriteFile(filepath.Join(spool, "status", jobID+".json"), encoded, 0o600); err != nil {
		t.Fatal(err)
	}
}
