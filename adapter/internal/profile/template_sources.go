package profile

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// FingerprintTemplate contains no screen, window or DPR settings.
// Frozen device values are generated once by the runner and retained separately.
type FingerprintTemplate struct {
	Builtin        bool     `json:"builtin,omitempty"`
	Version        int      `json:"version,omitempty"`
	ID             string   `json:"id"`
	Label          string   `json:"label"`
	Revision       int      `json:"revision"`
	Engine         string   `json:"engine,omitempty"`
	BrowserVersion string   `json:"browser_version,omitempty"`
	Locale         string   `json:"locale"`
	Languages      []string `json:"languages"`
	Timezone       string   `json:"timezone"`
	CreatedAt      string   `json:"created_at"`
}
type DisplayPreset struct {
	Builtin      bool    `json:"builtin,omitempty"`
	DPRMode      string  `json:"dpr_mode,omitempty"`
	ID           string  `json:"id"`
	Label        string  `json:"label"`
	Revision     int     `json:"revision"`
	Mode         string  `json:"mode"`
	Width        int     `json:"width"`
	Height       int     `json:"height"`
	DPR          float64 `json:"dpr"`
	WindowWidth  int     `json:"window_width"`
	WindowHeight int     `json:"window_height"`
	CreatedAt    string  `json:"created_at"`
}
type TemplateSourceRef struct {
	FingerprintID     string `json:"fingerprint_id"`
	FingerprintSHA256 string `json:"fingerprint_sha256"`
	DisplayID         string `json:"display_id"`
	DisplaySHA256     string `json:"display_sha256"`
}

// GenerationTarget snapshots the accepted browser revision, independently of a source.
type GenerationTarget struct {
	BrowserTemplateID       string `json:"browser_template_id"`
	BrowserTemplateRevision int    `json:"browser_template_revision"`
	Engine                  string `json:"engine"`
	BrowserVersion          string `json:"browser_version"`
}
type TemplateSources struct {
	GenerationTargets []GenerationTarget    `json:"generation_targets"`
	Fingerprints      []FingerprintTemplate `json:"fingerprints"`
	Displays          []DisplayPreset       `json:"displays"`
}

func validTemplateLabel(label string) bool {
	return strings.TrimSpace(label) == label && label != "" && len([]rune(label)) <= 64 && !strings.ContainsAny(label, "\r\n\x00")
}
func validateFingerprintTemplate(v FingerprintTemplate) error {
	if v.Builtin || builtinSource("fingerprints", v.ID) {
		if validBuiltinFingerprint(v) {
			return nil
		}
		return ErrEnvironmentJobInvalid
	}
	if !validTemplateLabel(v.Label) || !((v.Version == 2 && v.Engine == "" && v.BrowserVersion == "") || (v.Version == 0 && v.Engine == "camoufox" && v.BrowserVersion == "152.0")) {
		return ErrEnvironmentJobInvalid
	}
	_, err := validateEnvironmentJob(EnvironmentJobRequest{Locale: v.Locale, Languages: v.Languages, Timezone: v.Timezone, ScreenWidth: 1920, ScreenHeight: 1080, DPR: 1})
	return err
}

const builtinDisplayID = "display-0000000000000001"

func builtinDisplayPreset() DisplayPreset {
	return DisplayPreset{ID: builtinDisplayID, Label: "自动分辨率 · DPR 随缩放变化", Revision: 1, Mode: "auto", Width: 1280, Height: 720, WindowWidth: 1280, WindowHeight: 720, Builtin: true, DPRMode: "system", CreatedAt: "2026-10-01T00:00:00Z"}
}

func validateDisplayPreset(v DisplayPreset) error {
	if v.Builtin || builtinSource("displays", v.ID) || v.Mode == "auto" || v.DPRMode != "" {
		if validBuiltinDisplay(v) {
			return nil
		}
		return ErrEnvironmentJobInvalid
	}
	if !validTemplateLabel(v.Label) || v.Mode != "fixed" {
		return ErrEnvironmentJobInvalid
	}
	_, err := validateEnvironmentJob(EnvironmentJobRequest{Locale: "en-US", Languages: []string{"en-US"}, Timezone: "UTC", ScreenWidth: v.Width, ScreenHeight: v.Height, DPR: v.DPR, WindowWidth: v.WindowWidth, WindowHeight: v.WindowHeight})
	return err
}
func (s *Service) templateSourceDirectory(kind string) (string, error) {
	if err := s.spoolReady(); err != nil {
		return "", err
	}
	root := filepath.Join(s.jobSpool, "templates")
	for _, p := range []string{root, filepath.Join(root, kind)} {
		if err := os.Mkdir(p, 0700); err != nil && !os.IsExist(err) {
			return "", err
		}
		info, err := os.Lstat(p)
		if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
			return "", ErrEnvironmentJobsUnavailable
		}
	}
	return filepath.Join(root, kind), nil
}
func writeNewTemplate(path string, value any) error {
	raw, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".template-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(append(raw, '\n')); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	// Link publishes an already complete private file and cannot replace a record.
	if err = os.Link(f.Name(), path); err != nil {
		return err
	}
	d, err := os.Open(filepath.Dir(path))
	if err == nil {
		err = d.Sync()
		d.Close()
	}
	return err
}
func (s *Service) CreateFingerprintTemplate(ctx context.Context, v FingerprintTemplate) (FingerprintTemplate, error) {
	if err := ctx.Err(); err != nil {
		return v, err
	}
	if v.Builtin || builtinSource("fingerprints", v.ID) || v.Engine != "" || v.BrowserVersion != "" || (v.Version != 0 && v.Version != 2) {
		return v, ErrEnvironmentJobInvalid
	}
	v.Version = 2
	if err := validateFingerprintTemplate(v); err != nil {
		return v, err
	}
	root, err := s.templateSourceDirectory("fingerprints")
	if err != nil {
		return v, err
	}
	random, err := randomID()
	if err != nil {
		return v, err
	}
	v.ID = "fp-" + random[:16]
	v.Revision = 1
	v.CreatedAt = s.now().UTC().Format(time.RFC3339Nano)
	return v, writeNewTemplate(filepath.Join(root, v.ID+".json"), v)
}
func (s *Service) CreateDisplayPreset(ctx context.Context, v DisplayPreset) (DisplayPreset, error) {
	if err := ctx.Err(); err != nil {
		return v, err
	}
	if v.Builtin || builtinSource("displays", v.ID) || v.Mode != "fixed" || v.DPRMode != "" {
		return v, ErrEnvironmentJobInvalid
	}
	if err := validateDisplayPreset(v); err != nil {
		return v, err
	}
	root, err := s.templateSourceDirectory("displays")
	if err != nil {
		return v, err
	}
	random, err := randomID()
	if err != nil {
		return v, err
	}
	v.ID = "display-" + random[:16]
	v.Revision = 1
	v.CreatedAt = s.now().UTC().Format(time.RFC3339Nano)
	if v.WindowWidth == 0 && v.WindowHeight == 0 {
		v.WindowWidth = v.Width
		v.WindowHeight = v.Height
	}
	return v, writeNewTemplate(filepath.Join(root, v.ID+".json"), v)
}
func (s *Service) TemplateSources() (TemplateSources, error) {
	out := TemplateSources{Fingerprints: []FingerprintTemplate{}, Displays: []DisplayPreset{}}
	targets, err := s.generationTargets(context.Background())
	if err != nil {
		return out, err
	}
	out.GenerationTargets = targets
	for _, kind := range []string{"fingerprints", "displays"} {
		root, err := s.templateSourceDirectory(kind)
		if err != nil {
			return out, err
		}
		defaults := map[string]any{}
		if kind == "fingerprints" {
			for _, value := range builtinFingerprintTemplates() {
				defaults[value.ID] = value
			}
		} else {
			for _, value := range builtinDisplayPresets() {
				defaults[value.ID] = value
			}
		}
		for id, value := range defaults {
			path := filepath.Join(root, id+".json")
			if _, e := os.Lstat(path); os.IsNotExist(e) {
				if e = writeNewTemplate(path, value); e != nil && !os.IsExist(e) {
					return out, e
				}
			}
		}
		entries, err := os.ReadDir(root)
		if err != nil {
			return out, err
		}
		for _, e := range entries {
			if !strings.HasSuffix(e.Name(), ".json") {
				continue
			}
			deleted, err := s.dataDeleted(kind, strings.TrimSuffix(e.Name(), ".json"))
			if err != nil {
				return out, err
			}
			if deleted {
				if builtinSource(kind, strings.TrimSuffix(e.Name(), ".json")) {
					return out, ErrBuiltinTemplate
				}
				continue
			}
			if kind == "fingerprints" {
				var v FingerprintTemplate
				if err = readPrivateJSON(filepath.Join(root, e.Name()), 64<<10, &v); err != nil {
					return out, err
				}
				if v.ID+".json" != e.Name() || v.Revision != 1 || validateFingerprintTemplate(v) != nil {
					return out, ErrEnvironmentJobInvalid
				}
				out.Fingerprints = append(out.Fingerprints, v)
			} else {
				var v DisplayPreset
				if err = readPrivateJSON(filepath.Join(root, e.Name()), 64<<10, &v); err != nil {
					return out, err
				}
				if v.ID+".json" != e.Name() || v.Revision != 1 || validateDisplayPreset(v) != nil {
					return out, ErrEnvironmentJobInvalid
				}
				out.Displays = append(out.Displays, v)
			}
		}
	}
	return out, nil
}
func templateSourceDigest(path string) (string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), nil
}
func (s *Service) CreateTemplateCombination(ctx context.Context, actor, fingerprintID, displayID, browserTemplateID string) (EnvironmentJobSummary, error) {
	sources, err := s.TemplateSources()
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	var fp FingerprintTemplate
	var dp DisplayPreset
	for _, v := range sources.Fingerprints {
		if v.ID == fingerprintID {
			fp = v
		}
	}
	for _, v := range sources.Displays {
		if v.ID == displayID {
			dp = v
		}
	}
	var target *GenerationTarget
	for _, v := range sources.GenerationTargets {
		if v.BrowserTemplateID == browserTemplateID {
			candidate := v
			target = &candidate
		}
	}
	if fp.ID == "" || dp.ID == "" || target == nil || (fp.Version == 0 && (fp.Engine != target.Engine || fp.BrowserVersion != target.BrowserVersion)) {
		return EnvironmentJobSummary{}, ErrEnvironmentJobInvalid
	}
	fhash, err := templateSourceDigest(filepath.Join(s.jobSpool, "templates/fingerprints", fp.ID+".json"))
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	dhash, err := templateSourceDigest(filepath.Join(s.jobSpool, "templates/displays", dp.ID+".json"))
	if err != nil {
		return EnvironmentJobSummary{}, err
	}
	req := EnvironmentJobRequest{DisplayMode: dp.Mode, Generation: target, Locale: fp.Locale, Languages: fp.Languages, Timezone: fp.Timezone, ScreenWidth: dp.Width, ScreenHeight: dp.Height, DPR: dp.DPR, WindowWidth: dp.WindowWidth, WindowHeight: dp.WindowHeight, Templates: &TemplateSourceRef{fp.ID, fhash, dp.ID, dhash}}
	// Only the trusted service composes dimensions, never the fingerprint form.
	job, err := s.CreateEnvironmentJob(ctx, actor, req)
	if err != nil {
		return job, fmt.Errorf("template combination: %w", err)
	}
	return job, nil
}

// An accepted runtime is not necessarily a supported custom generator.
// Keep this filter aligned with the host runner's supported target versions.
func (s *Service) generationTargets(ctx context.Context) ([]GenerationTarget, error) {
	out := []GenerationTarget{}
	if s.templateCatalog == nil {
		return out, nil
	}
	data, err := s.templateCatalog.Read(ctx)
	if err != nil {
		return nil, err
	}
	for _, b := range data.BrowserTemplates {
		if supportedGenerationBrowser(b) && b.Status == "accepted" && b.AllowNewBrowsers && b.OSFamily == "linux" && b.Platform == "Linux x86_64" {
			out = append(out, GenerationTarget{b.ID, b.Revision, b.Engine, b.Version})
		}
	}
	return out, nil
}

func supportedGenerationBrowser(b BrowserTemplate) bool {
	return (b.ID == "camoufox-linux-v152" && b.Engine == "camoufox" && b.Version == "152.0" && b.UserAgentProduct == "Firefox") ||
		(b.ID == "chromix-linux-154" && b.Engine == "chromix" && b.Version == "154.0.8037.57" && b.UserAgentProduct == "Chrome") ||
		(b.ID == "firefox-linux-155" && b.Engine == "firefox" && b.Version == "155.0.1" && b.UserAgentProduct == "Firefox")
}
