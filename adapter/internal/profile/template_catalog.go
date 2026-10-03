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
	"strconv"
	"strings"
)

var ErrTemplateCatalogUnavailable = errors.New("compatible template catalog is unavailable")

var screenTemplatePattern = regexp.MustCompile(`^([0-9]{3,4})x([0-9]{3,4})@([0-9]+(?:\.[0-9]+)?)$`)

type BrowserTemplate struct {
	ID               string `json:"id"`
	Revision         int    `json:"revision"`
	Status           string `json:"status"`
	Label            string `json:"label"`
	Engine           string `json:"engine"`
	Version          string `json:"version"`
	OSFamily         string `json:"os_family"`
	Platform         string `json:"platform"`
	UserAgentProduct string `json:"user_agent_product"`
	AllowNewBrowsers bool   `json:"allow_new_browsers"`
	AcceptedAt       string `json:"accepted_at,omitempty"`
}

type DisplayTemplate struct {
	ID            string `json:"id"`
	Revision      int    `json:"revision"`
	Status        string `json:"status"`
	Label         string `json:"label"`
	DisplayServer string `json:"display_server"`
	Transport     string `json:"transport"`
	Screen        string `json:"screen"`
	Scaling       string `json:"scaling"`
	AcceptedAt    string `json:"accepted_at,omitempty"`
}

type TemplateCompatibility struct {
	Builtin               bool   `json:"builtin,omitempty"`
	BrowserTemplateID     string `json:"browser_template_id"`
	EnvironmentArtifactID string `json:"environment_artifact_id"`
	DisplayTemplateID     string `json:"display_template_id"`
	Status                string `json:"status"`
	AcceptedAt            string `json:"accepted_at,omitempty"`
}

type TemplateCatalogData struct {
	Version          int                     `json:"version"`
	BrowserTemplates []BrowserTemplate       `json:"browser_templates"`
	DisplayTemplates []DisplayTemplate       `json:"display_templates"`
	Compatibility    []TemplateCompatibility `json:"compatibility"`
}

type TemplateCatalog interface {
	Read(context.Context) (TemplateCatalogData, error)
}

type FileTemplateCatalog struct{ path string }

func NewFileTemplateCatalog(path string) (*FileTemplateCatalog, error) {
	if strings.TrimSpace(path) == "" {
		return nil, errors.New("template catalog path is required")
	}
	return &FileTemplateCatalog{path: filepath.Clean(path)}, nil
}

func (c *FileTemplateCatalog) Read(ctx context.Context) (TemplateCatalogData, error) {
	if err := ctx.Err(); err != nil {
		return TemplateCatalogData{}, err
	}
	file, err := os.Open(c.path)
	if err != nil {
		return TemplateCatalogData{}, fmt.Errorf("%w: %v", ErrTemplateCatalogUnavailable, err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return TemplateCatalogData{}, fmt.Errorf("%w: catalog must be a private regular file", ErrTemplateCatalogUnavailable)
	}
	var data TemplateCatalogData
	decoder := json.NewDecoder(io.LimitReader(file, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&data); err != nil {
		return TemplateCatalogData{}, fmt.Errorf("%w: decode catalog: %v", ErrTemplateCatalogUnavailable, err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return TemplateCatalogData{}, fmt.Errorf("%w: trailing data", ErrTemplateCatalogUnavailable)
	}
	if err := validateTemplateCatalog(data); err != nil {
		return TemplateCatalogData{}, err
	}
	return data, nil
}

type StaticTemplateCatalog TemplateCatalogData

func (c StaticTemplateCatalog) Read(context.Context) (TemplateCatalogData, error) {
	data := TemplateCatalogData(c)
	if err := validateTemplateCatalog(data); err != nil {
		return TemplateCatalogData{}, err
	}
	return data, nil
}

type CompatibleTemplateSummary struct {
	Builtin                 bool     `json:"builtin,omitempty"`
	EnvironmentLabel        string   `json:"environment_label,omitempty"`
	BrowserVersion          string   `json:"browser_version"`
	BrowserTemplateID       string   `json:"browser_template_id"`
	BrowserTemplateRevision int      `json:"browser_template_revision"`
	BrowserLabel            string   `json:"browser_label"`
	Engine                  string   `json:"engine"`
	EnvironmentArtifactID   string   `json:"environment_artifact_id"`
	EnvironmentSHA256       string   `json:"environment_sha256"`
	EnvironmentRevision     int      `json:"environment_revision"`
	Source                  string   `json:"source"`
	Locale                  string   `json:"locale"`
	Languages               []string `json:"languages"`
	Timezone                string   `json:"timezone"`
	DisplayTemplateID       string   `json:"display_template_id"`
	DisplayTemplateRevision int      `json:"display_template_revision"`
	DisplayLabel            string   `json:"display_label"`
	DisplayServer           string   `json:"display_server"`
	Transport               string   `json:"transport"`
	Screen                  string   `json:"screen"`
	Scaling                 string   `json:"scaling"`
	AllowNewBrowsers        bool     `json:"allow_new_browsers"`
}

func validateTemplateCatalog(data TemplateCatalogData) error {
	fail := func(format string, args ...any) error {
		return fmt.Errorf("%w: %s", ErrTemplateCatalogUnavailable, fmt.Sprintf(format, args...))
	}
	if data.Version != 1 {
		return fail("unsupported version")
	}
	browsers := make(map[string]BrowserTemplate, len(data.BrowserTemplates))
	for _, item := range data.BrowserTemplates {
		if !validPolicyName(item.ID) || item.Revision < 1 || item.Label == "" || item.Status != "accepted" {
			return fail("invalid browser template %q", item.ID)
		}
		if item.Engine != "camoufox" && item.Engine != "firefox_legacy" && item.Engine != "chromix" && item.Engine != "firefox" {
			return fail("unsupported browser engine for %q", item.ID)
		}
		if item.Version == "" || item.OSFamily != "linux" || item.Platform == "" || item.UserAgentProduct == "" {
			return fail("incomplete browser coherence metadata for %q", item.ID)
		}
		if item.Engine == "firefox_legacy" && item.AllowNewBrowsers {
			return fail("legacy Firefox template %q cannot create new browsers", item.ID)
		}
		if _, exists := browsers[item.ID]; exists {
			return fail("duplicate browser template %q", item.ID)
		}
		browsers[item.ID] = item
	}
	displays := make(map[string]DisplayTemplate, len(data.DisplayTemplates))
	for _, item := range data.DisplayTemplates {
		if !validPolicyName(item.ID) || item.Revision < 1 || item.Label == "" || item.Status != "accepted" {
			return fail("invalid display template %q", item.ID)
		}
		if item.DisplayServer != "x11" && item.DisplayServer != "wayland" {
			return fail("unsupported display server for %q", item.ID)
		}
		if item.Transport != "selkies" || (item.Scaling != "fixed" && item.Scaling != "fit" && item.Scaling != "auto") {
			return fail("unsupported display transport/scaling for %q", item.ID)
		}
		if item.Scaling == "auto" {
			if (item.Screen != "auto@1" && item.Screen != "auto@system") || item.DisplayServer != "x11" {
				return fail("invalid automatic display for %q", item.ID)
			}
		} else if _, _, _, err := parseTemplateScreen(item.Screen); err != nil {
			return fail("invalid display screen for %q", item.ID)
		}
		if _, exists := displays[item.ID]; exists {
			return fail("duplicate display template %q", item.ID)
		}
		displays[item.ID] = item
	}
	seen := make(map[string]bool, len(data.Compatibility))
	for _, item := range data.Compatibility {
		if item.Status != "accepted" || item.EnvironmentArtifactID == "" {
			return fail("invalid compatibility entry")
		}
		if _, ok := browsers[item.BrowserTemplateID]; !ok {
			return fail("unknown browser template %q", item.BrowserTemplateID)
		}
		if _, ok := displays[item.DisplayTemplateID]; !ok {
			return fail("unknown display template %q", item.DisplayTemplateID)
		}
		key := item.BrowserTemplateID + "\x00" + item.EnvironmentArtifactID + "\x00" + item.DisplayTemplateID
		if seen[key] {
			return fail("duplicate compatibility entry")
		}
		seen[key] = true
	}
	return nil
}

func parseTemplateScreen(value string) (int, int, float64, error) {
	match := screenTemplatePattern.FindStringSubmatch(value)
	if len(match) != 4 {
		return 0, 0, 0, errors.New("invalid screen")
	}
	w, errW := strconv.Atoi(match[1])
	h, errH := strconv.Atoi(match[2])
	dpr, errD := strconv.ParseFloat(match[3], 64)
	if errW != nil || errH != nil || errD != nil || w < 640 || h < 480 || dpr <= 0 || dpr > 4 {
		return 0, 0, 0, errors.New("invalid screen")
	}
	return w, h, dpr, nil
}

func (s *Service) CompatibleTemplates(ctx context.Context) ([]CompatibleTemplateSummary, error) {
	if s.templateCatalog == nil || s.catalog == nil {
		return nil, ErrTemplateCatalogUnavailable
	}
	data, err := s.templateCatalog.Read(ctx)
	if err != nil {
		return nil, err
	}
	browsers := make(map[string]BrowserTemplate, len(data.BrowserTemplates))
	for _, item := range data.BrowserTemplates {
		browsers[item.ID] = item
	}
	displays := make(map[string]DisplayTemplate, len(data.DisplayTemplates))
	for _, item := range data.DisplayTemplates {
		displays[item.ID] = item
	}
	result := make([]CompatibleTemplateSummary, 0, len(data.Compatibility))
	for _, combo := range data.Compatibility {
		deleted, err := s.dataDeleted("combinations", combo.BrowserTemplateID, combo.EnvironmentArtifactID, combo.DisplayTemplateID)
		if err != nil {
			return nil, err
		}
		if deleted {
			if combo.Builtin {
				return nil, ErrBuiltinTemplate
			}
			continue
		}
		browser := browsers[combo.BrowserTemplateID]
		display := displays[combo.DisplayTemplateID]
		artifact, err := s.catalog.Accepted(ctx, combo.EnvironmentArtifactID)
		if err != nil || !validAcceptedArtifact(artifact) {
			return nil, fmt.Errorf("%w: referenced environment %q is not accepted", ErrTemplateCatalogUnavailable, combo.EnvironmentArtifactID)
		}
		if err := coherentTemplateArtifact(browser, display, artifact); err != nil {
			return nil, err
		}
		result = append(result, CompatibleTemplateSummary{
			Builtin:           combo.Builtin,
			BrowserTemplateID: browser.ID, BrowserTemplateRevision: browser.Revision, BrowserLabel: browser.Label, Engine: browser.Engine, BrowserVersion: browser.Version,
			EnvironmentLabel: artifact.Label, EnvironmentArtifactID: artifact.ID, EnvironmentSHA256: artifact.SHA256, EnvironmentRevision: artifact.TemplateRevision,
			Source: artifact.Source, Locale: artifact.Locale, Languages: append([]string(nil), artifact.Languages...), Timezone: artifact.Timezone,
			DisplayTemplateID: display.ID, DisplayTemplateRevision: display.Revision, DisplayLabel: display.Label, DisplayServer: display.DisplayServer,
			Transport: display.Transport, Screen: display.Screen, Scaling: display.Scaling, AllowNewBrowsers: browser.AllowNewBrowsers,
		})
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].BrowserTemplateID != result[j].BrowserTemplateID {
			return result[i].BrowserTemplateID < result[j].BrowserTemplateID
		}
		if result[i].EnvironmentArtifactID != result[j].EnvironmentArtifactID {
			return result[i].EnvironmentArtifactID < result[j].EnvironmentArtifactID
		}
		return result[i].DisplayTemplateID < result[j].DisplayTemplateID
	})
	return result, nil
}

func coherentTemplateArtifact(browser BrowserTemplate, display DisplayTemplate, artifact EnvironmentArtifact) error {
	fail := func(reason string) error {
		return fmt.Errorf("%w: environment %q %s", ErrTemplateCatalogUnavailable, artifact.ID, reason)
	}
	if artifact.TemplateRevision < 1 || artifact.BrowserTemplateID != browser.ID || artifact.BrowserEngine != browser.Engine ||
		artifact.BrowserVersion != browser.Version || artifact.OSFamily != browser.OSFamily || artifact.Platform != browser.Platform || artifact.UserAgent == "" {
		return fail("has incomplete or mismatched browser metadata")
	}
	uaMatches := strings.Contains(strings.ToLower(artifact.UserAgent), strings.ToLower(browser.UserAgentProduct+"/"+browser.Version))
	// Chromium reduces its default UA token while the artifact retains the
	// exact executable version. Do not invent a full-version UA override.
	if browser.Engine == "chromix" && browser.UserAgentProduct == "Chrome" {
		major := strings.Split(browser.Version, ".")[0]
		uaMatches = uaMatches || strings.Contains(artifact.UserAgent, "Chrome/"+major+".0.0.0 ")
	}
	if browser.Engine == "firefox" && browser.UserAgentProduct == "Firefox" {
		major := strings.Split(browser.Version, ".")[0]
		uaMatches = uaMatches || strings.HasSuffix(artifact.UserAgent, "Firefox/"+major+".0")
	}
	if !uaMatches {
		return fail("has a User-Agent inconsistent with the browser template")
	}
	if artifact.Locale == "" || len(artifact.Languages) == 0 || artifact.Locale != artifact.Languages[0] || artifact.Timezone == "" {
		return fail("has inconsistent locale/languages/timezone metadata")
	}
	if artifact.Screen != display.Screen {
		return fail("screen/DPR does not match the display template")
	}
	if display.Scaling == "auto" && browser.Engine != "chromix" && (display.Screen != "auto@system" || (browser.Engine != "camoufox" && browser.Engine != "firefox")) {
		return fail("automatic display is not supported by this engine")
	}
	return nil
}

func posixLanguage(locale string) *string {
	value := strings.ReplaceAll(locale, "-", "_") + ".UTF-8"
	return &value
}

func (s *Service) resolveTemplateBinding(ctx context.Context, browserID, artifactID, displayID string) (TemplateBinding, EnvironmentArtifact, error) {
	if s.templateCatalog == nil || s.catalog == nil {
		return TemplateBinding{}, EnvironmentArtifact{}, ErrTemplateCatalogUnavailable
	}
	data, err := s.templateCatalog.Read(ctx)
	if err != nil {
		return TemplateBinding{}, EnvironmentArtifact{}, err
	}
	var browser BrowserTemplate
	var display DisplayTemplate
	browserFound, displayFound, combinationFound := false, false, false
	for _, item := range data.BrowserTemplates {
		if item.ID == browserID {
			browser, browserFound = item, true
			break
		}
	}
	for _, item := range data.DisplayTemplates {
		if item.ID == displayID {
			display, displayFound = item, true
			break
		}
	}
	for _, item := range data.Compatibility {
		if item.Status == "accepted" && item.BrowserTemplateID == browserID && item.EnvironmentArtifactID == artifactID && item.DisplayTemplateID == displayID {
			combinationFound = true
			break
		}
	}
	if !browserFound || !displayFound || !combinationFound {
		return TemplateBinding{}, EnvironmentArtifact{}, ErrTemplateCatalogUnavailable
	}
	artifact, err := s.catalog.Accepted(ctx, artifactID)
	if err != nil || !validAcceptedArtifact(artifact) {
		return TemplateBinding{}, EnvironmentArtifact{}, ErrArtifactUnavailable
	}
	if err := coherentTemplateArtifact(browser, display, artifact); err != nil {
		return TemplateBinding{}, EnvironmentArtifact{}, err
	}
	mode := ""
	if display.Scaling == "auto" {
		mode = "auto"
	}
	return TemplateBinding{
		ResolutionMode:    mode,
		BrowserTemplateID: browser.ID, BrowserTemplateRevision: browser.Revision,
		EnvironmentArtifactID: artifact.ID, EnvironmentArtifactSHA256: artifact.SHA256,
		EnvironmentSource: artifact.Source, EnvironmentTemplateRevision: artifact.TemplateRevision,
		DisplayTemplateID: display.ID, DisplayTemplateRevision: display.Revision,
		Language: posixLanguage(artifact.Locale), Timezone: templateStringPointer(artifact.Timezone), WaylandMode: display.DisplayServer == "wayland",
		RequiredRuntimeCapabilities: cloneCapabilities(artifact.RequiredRuntimeCapabilities),
	}, artifact, nil
}

func (s *Service) templateAllowsNewBrowser(ctx context.Context, browserID, artifactID, displayID string) (bool, error) {
	if err := s.selectableCombination(browserID, artifactID, displayID); err != nil {
		return false, err
	}
	if s.templateCatalog == nil {
		return false, ErrTemplateCatalogUnavailable
	}
	data, err := s.templateCatalog.Read(ctx)
	if err != nil {
		return false, err
	}
	allowed := false
	for _, browser := range data.BrowserTemplates {
		if browser.ID == browserID {
			allowed = browser.AllowNewBrowsers
			break
		}
	}
	if !allowed {
		return false, nil
	}
	for _, combo := range data.Compatibility {
		if combo.Status == "accepted" && combo.BrowserTemplateID == browserID &&
			combo.EnvironmentArtifactID == artifactID && combo.DisplayTemplateID == displayID {
			return true, nil
		}
	}
	return false, nil
}

func templateStringPointer(value string) *string {
	if value == "" {
		return nil
	}
	copied := value
	return &copied
}

func definitionWithTemplateBinding(base Definition, binding TemplateBinding) Definition {
	next := base
	next.ResolutionMode = binding.ResolutionMode
	next.UIScalingPercent = 0
	if next.ResolutionMode == "auto" {
		next.DisplayPreference = ""
	}
	next.BrowserTemplateID, next.BrowserTemplateRevision = binding.BrowserTemplateID, binding.BrowserTemplateRevision
	next.EnvironmentArtifactID, next.EnvironmentArtifactSHA256 = binding.EnvironmentArtifactID, binding.EnvironmentArtifactSHA256
	next.EnvironmentSource, next.EnvironmentTemplateRevision = binding.EnvironmentSource, binding.EnvironmentTemplateRevision
	next.DisplayTemplateID, next.DisplayTemplateRevision = binding.DisplayTemplateID, binding.DisplayTemplateRevision
	next.Language, next.Timezone, next.WaylandMode = binding.Language, binding.Timezone, binding.WaylandMode
	next.RequiredRuntimeCapabilities = cloneCapabilities(binding.RequiredRuntimeCapabilities)
	return next
}

func (s *Service) applyTemplateBindingLocked(ctx context.Context, record Record, expectedRevision int, target TemplateBinding, artifact EnvironmentArtifact, actor, idempotencyKey string) (Record, error) {
	// Chromium and Firefox profile formats cannot share an existing Home.
	// A different engine requires creation of a separate browser/Home.
	currentEngine := ""
	if record.EnvironmentArtifactID != "" {
		current, err := s.catalog.Accepted(ctx, record.EnvironmentArtifactID)
		if err != nil {
			return Record{}, ErrArtifactUnavailable
		}
		currentEngine = current.BrowserEngine
	}
	if (artifact.BrowserEngine == "chromix" || currentEngine == "chromix" || artifact.BrowserEngine == "firefox" || currentEngine == "firefox") && currentEngine != artifact.BrowserEngine {
		return Record{}, fmt.Errorf("%w: engine change requires a new browser Home", ErrTemplateCatalogUnavailable)
	}
	// Validate everything derivable from local accepted data before persisting
	// the launch-blocking state. Pending is reserved for interruptions after a
	// controller mutation may have started, not deterministic bad catalog data.
	nextDefinition := definitionWithTemplateBinding(record.Definition, target)
	if err := validateDefinition(nextDefinition); err != nil {
		return Record{}, err
	}
	app, err := applicationForBrowser(artifact, nextDefinition)
	if err != nil {
		return Record{}, err
	}
	pending, err := s.directory.beginTemplateChange(record.ID, expectedRevision, actor, target)
	if err != nil {
		return Record{}, err
	}
	if err := s.admin.ReplaceInstalledApp(ctx, record.ApplicationID, app, idempotencyKey+"-app"); err != nil {
		return Record{}, fmt.Errorf("replace browser template application: %w", err)
	}
	updated, err := s.directory.commitTemplateChange(record.ID, pending.Revision, actor)
	if err != nil {
		return Record{}, err
	}
	return updated, nil
}

// ApplyBrowserTemplate changes browser/fingerprint/display as one accepted
// combination. It never stops a browser implicitly. The lifecycle lock spans
// the empty-runtime proof, persistent launch gate, full application PUT and
// directory commit, so Ensure cannot race a partially applied revision.
func (s *Service) ApplyBrowserTemplate(ctx context.Context, profileID string, expectedRevision int, browserID, artifactID, displayID, actor, idempotencyKey string) (Record, error) {
	selectionLock := s.profileLock("__template_selections")
	selectionLock.Lock()
	defer selectionLock.Unlock()
	if err := s.selectableCombination(strings.TrimSpace(browserID), strings.TrimSpace(artifactID), strings.TrimSpace(displayID)); err != nil {
		return Record{}, err
	}

	if s.admin == nil || s.directoryPath == "" {
		return Record{}, ErrAdminUnavailable
	}
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 {
		return Record{}, errors.New("template apply requires an actor and durable idempotency key")
	}
	target, artifact, err := s.resolveTemplateBinding(ctx, strings.TrimSpace(browserID), strings.TrimSpace(artifactID), strings.TrimSpace(displayID))
	if err != nil {
		return Record{}, err
	}
	lock := s.profileLock(profileID)
	lock.Lock()
	defer lock.Unlock()
	record, ok := s.directory.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if record.Status == RecordReady && record.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	if record.Status == RecordUpdating {
		if record.PendingTemplate == nil || record.PendingTemplate.BaseRevision != expectedRevision || !sameTemplateBinding(record.PendingTemplate.Target, target) {
			return Record{}, ErrTemplateChangePending
		}
	} else if record.Status != RecordReady {
		return Record{}, fmt.Errorf("profile record is %s", record.Status)
	}
	if err := s.requireStoppedRuntimeLocked(ctx, profileID); err != nil {
		return Record{}, err
	}
	return s.applyTemplateBindingLocked(ctx, record, expectedRevision, target, artifact, actor, idempotencyKey)
}

// RollbackBrowserTemplate reapplies one exact earlier R7D Profile revision.
// Network selection is deliberately not part of the template binding and is
// therefore preserved rather than silently following historical proxy state.
func (s *Service) RollbackBrowserTemplate(ctx context.Context, profileID string, expectedRevision, targetProfileRevision int, actor, idempotencyKey string) (Record, error) {
	if s.admin == nil || s.directoryPath == "" {
		return Record{}, ErrAdminUnavailable
	}
	actor, idempotencyKey = strings.TrimSpace(actor), strings.TrimSpace(idempotencyKey)
	if actor == "" || idempotencyKey == "" || len(idempotencyKey) > 128 || targetProfileRevision < 1 {
		return Record{}, errors.New("template rollback requires a target revision, actor and durable idempotency key")
	}
	lock := s.profileLock(profileID)
	lock.Lock()
	defer lock.Unlock()
	record, ok := s.directory.record(profileID)
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if record.Status != RecordReady {
		return Record{}, ErrTemplateChangePending
	}
	if record.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	historical, err := s.directory.historicalTemplate(profileID, targetProfileRevision)
	if err != nil {
		return Record{}, err
	}
	target, artifact, err := s.resolveTemplateBinding(ctx, historical.BrowserTemplateID, historical.EnvironmentArtifactID, historical.DisplayTemplateID)
	if err != nil {
		return Record{}, err
	}
	if !sameTemplateBinding(target, historical) {
		return Record{}, ErrTemplateCatalogUnavailable
	}
	if err := s.requireStoppedRuntimeLocked(ctx, profileID); err != nil {
		return Record{}, err
	}
	return s.applyTemplateBindingLocked(ctx, record, expectedRevision, target, artifact, actor, idempotencyKey)
}
