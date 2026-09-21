package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"html/template"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

// environmentEntry is one row of the management list. Available is false when
// the summary could not be produced; the row then carries only the grant and
// a fixed message, never the underlying error.
type environmentEntry struct {
	ProfileID    string                      `json:"profile_id"`
	Capabilities []string                    `json:"capabilities"`
	Available    bool                        `json:"available"`
	Summary      *profile.EnvironmentSummary `json:"summary,omitempty"`
	Accounts     []string                    `json:"accounts"`
}

type environmentList struct {
	Version      int                `json:"version"`
	Subject      string             `json:"subject"`
	GeneratedAt  time.Time          `json:"generated_at"`
	Environments []environmentEntry `json:"environments"`
}

// manageService is the write side of the management surface. Stop reuses the
// verified lifecycle; UpdateBrowser only changes display fields and the
// enabled flag under optimistic locking.
type manageService interface {
	Stop(context.Context, string) (profile.LifecycleResult, error)
	UpdateBrowser(string, int, string, profile.BrowserPatch) (profile.Record, error)
}

type browserManagementService interface {
	CreateBrowser(context.Context, profile.CreateBrowserRequest, string, string) (profile.Record, error)
	DeleteBrowser(context.Context, string, string, string) error
}

type managementCapabilityService interface {
	ManagementCapabilities() profile.ManagementCapabilities
}

func managementCapabilities(service any) profile.ManagementCapabilities {
	if capabilities, ok := service.(managementCapabilityService); ok {
		return capabilities.ManagementCapabilities()
	}
	return profile.ManagementCapabilities{}
}

type environmentCatalogService interface {
	EnvironmentArtifacts(context.Context) ([]profile.EnvironmentArtifactSummary, error)
}

// environmentJobService is the R6E surface: the form only carries the
// high-level fields of specification 46.2, and the list never exposes
// generated device values.
type environmentJobService interface {
	CreateEnvironmentJob(context.Context, string, profile.EnvironmentJobRequest) (profile.EnvironmentJobSummary, error)
	EnvironmentJobs() ([]profile.EnvironmentJobSummary, error)
}

// proxyDraftService is the R6D write side: credentials travel once from the
// form into CreateProxyDraft and are never stored by the HTTP layer.
type proxyDraftService interface {
	CreateProxyDraft(context.Context, string, string, profile.ProxyDraftRequest) (profile.ProxyDraftSummary, error)
	ProbeProxyDraft(context.Context, string, string) (profile.ProxyDraftSummary, error)
	ApplyProxyDraft(context.Context, string, int, string, string, string) (profile.Record, error)
	SetBrowserDirect(context.Context, string, int, string, string, string, string) (profile.Record, error)
	ProxyDraft(string) (profile.ProxyDraftSummary, bool)
}

// notices are the only strings the page echoes from a query parameter; any
// other value renders nothing.
var notices = map[string]string{
	"updated":         "已保存。",
	"unchanged":       "没有需要保存的更改。",
	"stopped":         "浏览器已安全关闭并确认资源清理。",
	"stop_pending":    "停止尚未确认完成，占用已保留；稍后重试或由运维对账。",
	"stop_conflict":   "当前状态不允许停止；请稍后重试或由运维对账。",
	"disabled":        "浏览器已停用；新的启动和复用会被拒绝，已运行的画面不受影响。",
	"enabled":         "浏览器已启用。",
	"revision":        "记录已被其他操作修改，请核对后重试。",
	"invalid":         "输入无效，未保存。",
	"unavailable":     "操作暂时不可用，未保存。",
	"created":         "浏览器已创建，固定入口地址已生效。",
	"deleted":         "浏览器已停止、归档 Home 并撤销应用。",
	"busy":            "浏览器仍占用运行资源，未删除。",
	"account_created": "账号已创建。",
	"account_updated": "账号已更新。",
	"account_exists":  "账号已存在。",
	"last_admin":      "不能禁用或降级最后一个启用的管理员。",
	"reauth":          "该操作需要重新确认密码。",
	"draft_created":   "代理草稿已创建，凭据只保存在控制器 Secret Store；请执行探针。",
	"draft_probed":    "探针通过，可在浏览器停止后应用到下一代次。",
	"draft_failed":    "探针未通过；草稿保留可重试或重新提交。",
	"draft_missing":   "代理草稿不存在、已过期或已被替换。",
	"draft_unprobed":  "草稿尚未通过探针，不能应用。",
	"network_applied": "网络修订已固化；下一次启动使用新的代理或 DIRECT 策略。",
	"network_busy":    "浏览器仍占用运行资源，网络修订未应用。",
	"unmanaged":       "该浏览器不是受管理网络，不能配置代理。",
	"job_created":     "自定义指纹作业已排队；执行器将在隔离容器中生成并完整验收，通过后出现在固化环境目录。",
	"job_busy":        "排队或运行中的作业已达上限，请稍后再提交。",
	"job_invalid":     "自定义指纹字段无效或当前适配器不支持（仅 Linux、DPR 1、有效 BCP 47 与 IANA 名称）。",
}

// environments reads one summary per grant. The gateway already restricted
// the grants to administrators; a Profile the service no longer knows is
// skipped so the list never names anything beyond the grants.
func (s *Server) environments(ctx context.Context, grants []access.Grant, accounts []access.Account) []environmentEntry {
	entries := make([]environmentEntry, 0, len(grants))
	for _, grant := range grants {
		entry := environmentEntry{ProfileID: grant.Profile, Capabilities: grant.Capabilities, Accounts: []string{}}
		for _, account := range accounts {
			for _, id := range account.Profiles {
				if id == grant.Profile {
					entry.Accounts = append(entry.Accounts, account.ID)
				}
			}
		}
		summary, err := s.profiles.Environment(ctx, grant.Profile)
		switch {
		case errors.Is(err, profile.ErrProfileNotFound):
			continue
		case err != nil:
			s.logger.Warn("environment summary unavailable", "profile", grant.Profile, "error", err)
		default:
			entry.Available, entry.Summary = true, &summary
		}
		entries = append(entries, entry)
	}
	return entries
}

func (s *Server) accounts() []access.Account {
	if s.access == nil {
		return nil
	}
	accounts, err := s.access.Accounts().Snapshot()
	if err != nil {
		s.logger.Warn("environment summary unavailable", "error", err)
		return nil
	}
	return accounts
}

func (s *Server) manageEnvironments(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	grants, ok := access.Grants(request)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), 10*time.Second)
	defer cancel()
	list := environmentList{Version: 1, Subject: access.Subject(request), GeneratedAt: time.Now().UTC(), Environments: s.environments(ctx, grants, s.accounts())}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(list)
}

func (s *Server) manageEnvironmentCatalog(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || !managementCapabilities(s.profiles).CreateDelete {
		http.NotFound(writer, request)
		return
	}
	catalog, ok := s.profiles.(environmentCatalogService)
	if !ok {
		http.Error(writer, "Environment catalog is not available", http.StatusNotImplemented)
		return
	}
	artifacts, err := catalog.EnvironmentArtifacts(request.Context())
	if err != nil {
		http.Error(writer, "Environment catalog is not available", http.StatusServiceUnavailable)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version   int                                  `json:"version"`
		Artifacts []profile.EnvironmentArtifactSummary `json:"artifacts"`
	}{Version: 1, Artifacts: artifacts})
}

func (s *Server) managePage(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	grants, ok := access.Grants(request)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), 10*time.Second)
	defer cancel()
	accounts := s.accounts()
	entries := s.environments(ctx, grants, accounts)
	capabilities := managementCapabilities(s.profiles)
	drafts, hasDrafts := s.profiles.(proxyDraftService)
	hasDrafts = hasDrafts && capabilities.ProxyDrafts
	rows := make([]manageRow, 0, len(entries))
	for _, entry := range entries {
		row := manageRowFor(entry)
		if hasDrafts && row.Managed {
			if draft, ok := drafts.ProxyDraft(entry.ProfileID); ok {
				copied := draft
				row.Draft = &copied
				if draft.ProbedAt != nil {
					row.DraftProbedAt = draft.ProbedAt.UTC().Format(time.RFC3339)
				}
			}
		}
		rows = append(rows, row)
	}
	profileIDs := make([]string, 0, len(entries))
	for _, entry := range entries {
		profileIDs = append(profileIDs, entry.ProfileID)
	}
	// The forms need a real Origin on their POSTs; see pageHeaders in access.
	writer.Header().Set("Referrer-Policy", "same-origin")
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	writer.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
	var artifacts []profile.EnvironmentArtifactSummary
	if catalog, ok := s.profiles.(environmentCatalogService); ok && capabilities.CreateDelete {
		if listed, err := catalog.EnvironmentArtifacts(ctx); err == nil {
			artifacts = listed
		}
	}
	var jobs []profile.EnvironmentJobSummary
	jobService, hasJobs := s.profiles.(environmentJobService)
	hasJobs = hasJobs && capabilities.EnvironmentJobs
	if hasJobs {
		listed, err := jobService.EnvironmentJobs()
		if err != nil {
			hasJobs = false
		} else {
			jobs = listed
		}
	}
	activeTab := "browsers"
	switch request.URL.Query().Get("tab") {
	case "jobs":
		if hasJobs {
			activeTab = "jobs"
		}
	case "accounts":
		activeTab = "accounts"
	}
	reauthURL := "/auth/reauth?next=" + url.QueryEscape("/manage/?tab="+activeTab)
	data := struct {
		Subject      string
		GeneratedAt  string
		Notice       string
		ActiveTab    string
		ReauthURL    string
		Rows         []manageRow
		Accounts     []accountRow
		ProfileIDs   []string
		EntryOrigin  string
		CSRF         string
		ProxyDrafts  bool
		Artifacts    []profile.EnvironmentArtifactSummary
		Jobs         []profile.EnvironmentJobSummary
		JobsEnabled  bool
		CreateDelete bool
	}{Subject: access.Subject(request), GeneratedAt: time.Now().UTC().Format(time.RFC3339), Notice: notices[request.URL.Query().Get("notice")],
		ActiveTab: activeTab, ReauthURL: reauthURL, Rows: rows, Accounts: accountRows(accounts, profileIDs), ProfileIDs: profileIDs,
		EntryOrigin: s.publicOrigin.String(), CSRF: access.CSRF(request), ProxyDrafts: hasDrafts,
		Artifacts: artifacts, Jobs: jobs, JobsEnabled: hasJobs && capabilities.EnvironmentJobs, CreateDelete: capabilities.CreateDelete}
	if err := manageTemplate.Execute(writer, data); err != nil {
		s.logger.Error("render environment list", "error", err)
	}
}

type manageRow struct {
	ProfileID, Label, EntryPath, Capabilities string
	Available                                 bool
	Status, Network, Display, Locale, Home    string
	Observed                                  bool
	Health, HealthCode, HealthTitle, Checked  string
	Stale, Blocking                           bool
	Environment                               string
	Enabled, Running, Manage, StopAllowed     bool
	Revision                                  int
	StartURL                                  string
	Accounts                                  string
	Managed                                   bool
	ConfiguredNetwork, ProxyUpstream          string
	Draft                                     *profile.ProxyDraftSummary
	DraftProbedAt                             string
}

type accountRow struct {
	ID, Role    string
	Disabled    bool
	Profiles    string
	Grants      map[string]bool
	AllProfiles []string
}

func accountRows(accounts []access.Account, profileIDs []string) []accountRow {
	rows := make([]accountRow, 0, len(accounts))
	for _, account := range accounts {
		row := accountRow{ID: account.ID, Role: account.EffectiveRole(), Disabled: account.Disabled,
			Profiles: strings.Join(account.Profiles, ", "), Grants: make(map[string]bool, len(account.Profiles)), AllProfiles: profileIDs}
		for _, id := range account.Profiles {
			row.Grants[id] = true
		}
		rows = append(rows, row)
	}
	return rows
}

func manageRowFor(entry environmentEntry) manageRow {
	row := manageRow{ProfileID: entry.ProfileID, Label: entry.ProfileID, EntryPath: "/browser/" + entry.ProfileID + "/",
		Capabilities: strings.Join(entry.Capabilities, ", "), Available: entry.Available, Accounts: strings.Join(entry.Accounts, ", ")}
	for _, capability := range entry.Capabilities {
		switch capability {
		case "manage":
			row.Manage = true
		case "stop":
			row.StopAllowed = true
		}
	}
	if !entry.Available || entry.Summary == nil {
		return row
	}
	summary := entry.Summary
	row.Label, row.EntryPath, row.Status = summary.Label, summary.EntryPath, string(summary.Status)
	row.Network, row.Display = summary.NetworkMode, summary.DisplayMode
	if summary.NetworkPolicyID != "" {
		row.Network += " · " + summary.NetworkPolicyID
	}
	row.Locale = strings.TrimSpace(strings.Join([]string{summary.Language, summary.Timezone}, " "))
	row.Home = summary.ApplicationID + " / " + summary.HomeName
	row.Observed = summary.Observed
	row.Enabled, row.Revision, row.StartURL = summary.Enabled, summary.Revision, summary.StartURL
	row.ConfiguredNetwork, row.ProxyUpstream = summary.ConfiguredNetworkMode, summary.ProxyUpstream
	row.Managed = summary.ConfiguredNetworkMode == "direct" || summary.ConfiguredNetworkMode == "proxy_required"
	row.Running = summary.Status == "running" || summary.Status == "launching" || summary.Status == "stopping" || summary.Status == "unknown"
	if summary.Health != nil {
		row.Health, row.HealthCode, row.HealthTitle = string(summary.Health.Overall), summary.Health.Code, summary.Health.Title
		row.Checked, row.Stale, row.Blocking = summary.Health.CheckedAt.UTC().Format(time.RFC3339), summary.Health.Stale, summary.Health.Blocking
		if summary.Health.Environment != nil {
			row.Environment = summary.Health.Environment.ID
			if digest := summary.Health.Environment.ArtifactSHA256; len(digest) >= 12 {
				row.Environment += " · " + digest[:12] + "…"
			}
		}
	}
	return row
}

func (s *Server) redirectManage(writer http.ResponseWriter, request *http.Request, notice string) {
	tab := ""
	switch {
	case strings.HasPrefix(request.URL.Path, "/manage/environment-jobs"):
		tab = "jobs"
	case strings.HasPrefix(request.URL.Path, "/manage/accounts"):
		tab = "accounts"
	}
	target := "/manage/"
	switch {
	case tab != "" && notice != "":
		target = "/manage/?tab=" + tab + "&notice=" + url.QueryEscape(notice)
	case tab != "":
		target = "/manage/?tab=" + tab
	case notice != "":
		target = "/manage/?notice=" + url.QueryEscape(notice)
	}
	http.Redirect(writer, request, target, http.StatusSeeOther)
}

func (s *Server) manageCreateBrowser(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	_, ok := access.Grants(request)
	manager, available := s.profiles.(browserManagementService)
	available = available && managementCapabilities(s.profiles).CreateDelete
	if !ok || !available {
		http.NotFound(writer, request)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil || len(request.PostForm["idempotency_key"]) != 1 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	requestID := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
	if requestID == "" || len(requestID) > 128 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	requestData := profile.CreateBrowserRequest{
		Label: strings.TrimSpace(request.PostForm.Get("label")), StartURL: strings.TrimSpace(request.PostForm.Get("start_url")),
		EnvironmentArtifactID: strings.TrimSpace(request.PostForm.Get("environment_artifact_id")), NetworkMode: strings.TrimSpace(request.PostForm.Get("network_mode")),
		NetworkPolicyID: strings.TrimSpace(request.PostForm.Get("network_policy_id")), NetworkPolicySHA256: strings.TrimSpace(request.PostForm.Get("network_policy_sha256")),
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	record, err := manager.CreateBrowser(ctx, requestData, access.Subject(request), requestID)
	if err != nil {
		s.logger.Warn("management action", "action", "browser_create", "status", "rejected", "error", err)
		s.redirectManage(writer, request, "unavailable")
		return
	}
	if s.access != nil {
		for _, accountID := range request.PostForm["accounts"] {
			if grantErr := s.access.Accounts().SetGrants(accountID, appendExistingGrant(s.access, accountID, record.ID)); grantErr != nil {
				s.logger.Warn("browser account assignment failed", "profile", record.ID, "error", grantErr)
			}
		}
		_ = s.access.Reload()
	}
	s.logger.Info("management action", "action", "browser_create", "profile", record.ID, "status", "created")
	s.redirectManage(writer, request, "created")
}

func appendExistingGrant(gateway *access.Gateway, accountID, profileID string) []string {
	for _, account := range gatewayAccounts(gateway) {
		if account.ID != accountID {
			continue
		}
		for _, id := range account.Profiles {
			if id == profileID {
				return account.Profiles
			}
		}
		return append(append([]string(nil), account.Profiles...), profileID)
	}
	return []string{profileID}
}

func gatewayAccounts(gateway *access.Gateway) []access.Account {
	accounts, err := gateway.Accounts().Snapshot()
	if err != nil {
		return nil
	}
	return accounts
}

func (s *Server) revokeBrowserGrants(profileID string) {
	if s.access == nil {
		return
	}
	for _, account := range gatewayAccounts(s.access) {
		grants := make([]string, 0, len(account.Profiles))
		for _, id := range account.Profiles {
			if id != profileID {
				grants = append(grants, id)
			}
		}
		if len(grants) != len(account.Profiles) {
			_ = s.access.Accounts().SetGrants(account.ID, grants)
		}
	}
	_ = s.access.Reload()
}

// grantFor returns the administrator's grant for a Profile named in a form
// POST; the gateway already verified login, role and CSRF.
func grantFor(request *http.Request, id string) (access.Grant, bool) {
	grants, ok := access.Grants(request)
	if !ok {
		return access.Grant{}, false
	}
	for _, grant := range grants {
		if grant.Profile == id {
			return grant, true
		}
	}
	return access.Grant{}, false
}

func hasCapability(grant access.Grant, wanted string) bool {
	for _, capability := range grant.Capabilities {
		if capability == wanted {
			return true
		}
	}
	return false
}

func parseRevision(value string) (int, bool) {
	revision := 0
	if value == "" || len(value) > 9 {
		return 0, false
	}
	for _, char := range value {
		if char < '0' || char > '9' {
			return 0, false
		}
		revision = revision*10 + int(char-'0')
	}
	return revision, revision > 0
}

// manageBrowser handles the per-browser forms: update label/start URL,
// enable/disable, and safe stop. Every branch leaves Home, journal and
// running generations untouched except through the verified Stop path.
func (s *Server) manageBrowser(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	id := request.PathValue("profile")
	grant, ok := grantFor(request, id)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	manage, ok := s.profiles.(manageService)
	if !ok {
		http.Error(writer, "Management operations are not available", http.StatusNotImplemented)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil || len(request.PostForm["action"]) != 1 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	actor := access.Subject(request)
	switch request.PostForm.Get("action") {
	case "delete":
		if !managementCapabilities(s.profiles).CreateDelete {
			http.NotFound(writer, request)
			return
		}
		if !hasCapability(grant, "manage") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		if s.access != nil && !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		manager, ok := s.profiles.(browserManagementService)
		if !ok {
			s.redirectManage(writer, request, "unavailable")
			return
		}
		idempotencyKey := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
		if idempotencyKey == "" || len(idempotencyKey) > 128 {
			s.redirectManage(writer, request, "invalid")
			return
		}
		ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
		defer cancel()
		if s.access != nil {
			if err := s.access.Accounts().RemoveProfileGrants(id); err != nil {
				s.logger.Warn("browser account grant cleanup failed", "profile", id, "error", err)
				s.redirectManage(writer, request, "unavailable")
				return
			}
			if err := s.access.Reload(); err != nil {
				s.logger.Warn("browser account registry reload failed", "profile", id, "error", err)
				s.redirectManage(writer, request, "unavailable")
				return
			}
		}
		err := manager.DeleteBrowser(ctx, id, actor, idempotencyKey)
		switch {
		case err == nil:
			s.logger.Info("management action", "profile", id, "action", "browser_delete", "status", "deleted")
			s.redirectManage(writer, request, "deleted")
		case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrStopUnconfirmed):
			s.redirectManage(writer, request, "busy")
		case errors.Is(err, profile.ErrProfileNotFound):
			http.NotFound(writer, request)
		default:
			s.logger.Warn("management action", "profile", id, "action", "browser_delete", "status", "rejected", "error", err)
			s.redirectManage(writer, request, "unavailable")
		}
		return
	case "stop":
		if !hasCapability(grant, "stop") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
		defer cancel()
		result, err := manage.Stop(ctx, id)
		switch {
		case err == nil && result.Status == "stopped":
			s.logger.Info("management action", "profile", id, "action", "stop", "status", "stopped")
			s.redirectManage(writer, request, "stopped")
		case errors.Is(err, profile.ErrStopUnconfirmed), err == nil:
			s.logger.Warn("management action", "profile", id, "action", "stop", "status", "pending")
			s.redirectManage(writer, request, "stop_pending")
		case errors.Is(err, profile.ErrProfileNotFound):
			http.NotFound(writer, request)
		default:
			s.logger.Warn("management action", "profile", id, "action", "stop", "status", "conflict", "error", err)
			s.redirectManage(writer, request, "stop_conflict")
		}
		return
	case "proxy_draft", "proxy_probe", "proxy_apply", "network_direct":
		if !managementCapabilities(s.profiles).ProxyDrafts {
			http.NotFound(writer, request)
			return
		}
		if !hasCapability(grant, "manage") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		s.manageNetwork(writer, request, id, actor)
		return
	case "update", "enable", "disable":
		if !hasCapability(grant, "manage") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		revision, ok := parseRevision(request.PostForm.Get("revision"))
		if !ok {
			s.redirectManage(writer, request, "invalid")
			return
		}
		patch := profile.BrowserPatch{}
		notice := "updated"
		switch request.PostForm.Get("action") {
		case "update":
			if len(request.PostForm["label"]) == 1 {
				label := strings.TrimSpace(request.PostForm.Get("label"))
				patch.Label = &label
			}
			if len(request.PostForm["start_url"]) == 1 {
				start := strings.TrimSpace(request.PostForm.Get("start_url"))
				patch.StartURL = &start
			}
		case "enable":
			enabled := false
			patch.Disabled, notice = &enabled, "enabled"
		case "disable":
			disabled := true
			patch.Disabled, notice = &disabled, "disabled"
		}
		before, _ := s.profiles.Environment(request.Context(), id)
		record, err := manage.UpdateBrowser(id, revision, actor, patch)
		switch {
		case err == nil && record.Revision == before.Revision && before.Revision != 0:
			s.redirectManage(writer, request, "unchanged")
		case err == nil:
			s.logger.Info("management action", "profile", id, "action", request.PostForm.Get("action"), "status", "updated")
			s.redirectManage(writer, request, notice)
		case errors.Is(err, profile.ErrRevisionMismatch):
			s.redirectManage(writer, request, "revision")
		case errors.Is(err, profile.ErrProfileNotFound):
			http.NotFound(writer, request)
		case errors.Is(err, profile.ErrDirectoryReadOnly):
			s.redirectManage(writer, request, "unavailable")
		default:
			s.redirectManage(writer, request, "invalid")
		}
		return
	default:
		s.redirectManage(writer, request, "invalid")
	}
}

func (s *Server) manageEnvironmentJobList(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || !managementCapabilities(s.profiles).EnvironmentJobs {
		http.NotFound(writer, request)
		return
	}
	jobService, ok := s.profiles.(environmentJobService)
	if !ok {
		http.Error(writer, "Environment jobs are not available", http.StatusNotImplemented)
		return
	}
	jobs, err := jobService.EnvironmentJobs()
	if err != nil {
		http.Error(writer, "Environment jobs are not available", http.StatusServiceUnavailable)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version int                             `json:"version"`
		Jobs    []profile.EnvironmentJobSummary `json:"jobs"`
	}{Version: 1, Jobs: jobs})
}

// manageEnvironmentJobCreate enqueues one custom fingerprint job. The form
// carries only specification 46.2 fields; the service fixes everything else.
func (s *Server) manageEnvironmentJobCreate(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || !managementCapabilities(s.profiles).EnvironmentJobs {
		http.NotFound(writer, request)
		return
	}
	jobService, ok := s.profiles.(environmentJobService)
	if !ok {
		s.redirectManage(writer, request, "unavailable")
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil {
		s.redirectManage(writer, request, "job_invalid")
		return
	}
	number := func(name string) int {
		value, err := strconv.Atoi(strings.TrimSpace(request.PostForm.Get(name)))
		if err != nil {
			return -1
		}
		return value
	}
	dpr, err := strconv.ParseFloat(strings.TrimSpace(request.PostForm.Get("dpr")), 64)
	if err != nil {
		dpr = 0
	}
	var languages []string
	for _, tag := range strings.Split(request.PostForm.Get("languages"), ",") {
		if tag = strings.TrimSpace(tag); tag != "" {
			languages = append(languages, tag)
		}
	}
	jobRequest := profile.EnvironmentJobRequest{Locale: strings.TrimSpace(request.PostForm.Get("locale")), Languages: languages,
		Timezone: strings.TrimSpace(request.PostForm.Get("timezone")), ScreenWidth: number("screen_width"), ScreenHeight: number("screen_height"), DPR: dpr}
	if strings.TrimSpace(request.PostForm.Get("window_width")) != "" || strings.TrimSpace(request.PostForm.Get("window_height")) != "" {
		jobRequest.WindowWidth, jobRequest.WindowHeight = number("window_width"), number("window_height")
	}
	summary, err := jobService.CreateEnvironmentJob(request.Context(), access.Subject(request), jobRequest)
	switch {
	case err == nil:
		s.logger.Info("management action", "action", "environment_job_create", "job", summary.ID, "status", "queued")
		s.redirectManage(writer, request, "job_created")
	case errors.Is(err, profile.ErrEnvironmentJobInvalid):
		s.redirectManage(writer, request, "job_invalid")
	case errors.Is(err, profile.ErrEnvironmentJobsBusy):
		s.redirectManage(writer, request, "job_busy")
	default:
		s.logger.Warn("management action", "action", "environment_job_create", "status", "rejected", "error", err)
		s.redirectManage(writer, request, "unavailable")
	}
}

// manageNetwork handles the R6D proxy draft and DIRECT switch actions. The
// draft credentials are read from the form once, handed to the service and
// cleared; the log lines never carry them. Applying a revision or switching
// to DIRECT changes the next generation's network, so both require a recent
// password confirmation like deletion.
func (s *Server) manageNetwork(writer http.ResponseWriter, request *http.Request, id, actor string) {
	drafts, ok := s.profiles.(proxyDraftService)
	if !ok {
		s.redirectManage(writer, request, "unavailable")
		return
	}
	action := request.PostForm.Get("action")
	if s.access != nil && (action == "proxy_apply" || action == "network_direct") && !s.access.Reauthenticated(request) {
		s.redirectManage(writer, request, "reauth")
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	var err error
	notice := "invalid"
	switch action {
	case "proxy_draft":
		port, portErr := strconv.Atoi(strings.TrimSpace(request.PostForm.Get("port")))
		if portErr != nil {
			s.redirectManage(writer, request, "invalid")
			return
		}
		draft := profile.ProxyDraftRequest{Protocol: strings.TrimSpace(request.PostForm.Get("protocol")), Auth: strings.TrimSpace(request.PostForm.Get("auth")),
			Host: strings.TrimSpace(request.PostForm.Get("host")), Port: port, Username: request.PostForm.Get("username"), Password: request.PostForm.Get("password"),
			UpstreamCAPEM: strings.TrimSpace(request.PostForm.Get("upstream_ca_pem"))}
		request.PostForm.Del("password")
		request.PostForm.Del("username")
		_, err = drafts.CreateProxyDraft(ctx, id, actor, draft)
		draft.Password, draft.Username = "", ""
		notice = "draft_created"
	case "proxy_probe":
		var summary profile.ProxyDraftSummary
		summary, err = drafts.ProbeProxyDraft(ctx, id, strings.TrimSpace(request.PostForm.Get("draft_id")))
		notice = "draft_probed"
		if err == nil && summary.ProbeStatus != "passed" {
			notice = "draft_failed"
		}
	case "proxy_apply", "network_direct":
		revision, ok := parseRevision(request.PostForm.Get("revision"))
		idempotencyKey := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
		if !ok || idempotencyKey == "" || len(idempotencyKey) > 128 {
			s.redirectManage(writer, request, "invalid")
			return
		}
		if action == "proxy_apply" {
			_, err = drafts.ApplyProxyDraft(ctx, id, revision, strings.TrimSpace(request.PostForm.Get("draft_id")), actor, idempotencyKey)
		} else {
			_, err = drafts.SetBrowserDirect(ctx, id, revision, strings.TrimSpace(request.PostForm.Get("network_policy_id")), strings.TrimSpace(request.PostForm.Get("network_policy_sha256")), actor, idempotencyKey)
		}
		notice = "network_applied"
	}
	switch {
	case err == nil:
		s.logger.Info("management action", "profile", id, "action", action, "status", notice)
		s.redirectManage(writer, request, notice)
	case errors.Is(err, profile.ErrProfileNotFound):
		http.NotFound(writer, request)
	case errors.Is(err, profile.ErrProxyDraftInvalid), errors.Is(err, profile.ErrManagedPolicyRequired):
		s.redirectManage(writer, request, "invalid")
	case errors.Is(err, profile.ErrProxyDraftNotFound):
		s.redirectManage(writer, request, "draft_missing")
	case errors.Is(err, profile.ErrProxyDraftNotProbed):
		s.redirectManage(writer, request, "draft_unprobed")
	case errors.Is(err, profile.ErrNetworkUnmanaged):
		s.redirectManage(writer, request, "unmanaged")
	case errors.Is(err, profile.ErrRevisionMismatch):
		s.redirectManage(writer, request, "revision")
	case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrStopUnconfirmed), errors.Is(err, profile.ErrOwnershipUnknown):
		s.redirectManage(writer, request, "network_busy")
	default:
		s.logger.Warn("management action", "profile", id, "action", action, "status", "rejected", "error", err)
		s.redirectManage(writer, request, "unavailable")
	}
}

// manageAccounts creates entry or administrator accounts from the panel. The
// password only travels in the form body and is cleared after hashing.
func (s *Server) manageAccounts(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || s.access == nil {
		http.NotFound(writer, request)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil {
		s.redirectManage(writer, request, "invalid")
		return
	}
	defer func() {
		request.PostForm.Del("password")
		request.Form.Del("password")
	}()
	id, role, password := request.PostForm.Get("account"), request.PostForm.Get("role"), request.PostForm.Get("password")
	if len(request.PostForm["password"]) != 1 || (role != access.RoleUser && role != access.RoleAdmin) {
		s.redirectManage(writer, request, "invalid")
		return
	}
	if role == access.RoleAdmin && !s.access.Reauthenticated(request) {
		s.redirectManage(writer, request, "reauth")
		return
	}
	err := s.access.Accounts().Put(id, password, role, request.PostForm["profiles"], false)
	password = ""
	switch {
	case err == nil:
		_ = s.access.Reload()
		s.logger.Info("management action", "action", "account_create", "status", "created")
		s.redirectManage(writer, request, "account_created")
	case errors.Is(err, access.ErrAccountExists):
		s.redirectManage(writer, request, "account_exists")
	default:
		s.redirectManage(writer, request, "invalid")
	}
}

// manageAccount changes one account: reset password, enable/disable, grants
// or role. Changing another account's password or an administrator's status
// requires a recent password confirmation.
func (s *Server) manageAccount(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || s.access == nil {
		http.NotFound(writer, request)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil || len(request.PostForm["action"]) != 1 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	defer func() {
		request.PostForm.Del("password")
		request.Form.Del("password")
	}()
	id, actor := request.PathValue("account"), access.Subject(request)
	store := s.access.Accounts()
	sensitive := id != actor
	var err error
	switch request.PostForm.Get("action") {
	case "reset_password":
		if len(request.PostForm["password"]) != 1 {
			s.redirectManage(writer, request, "invalid")
			return
		}
		if sensitive && !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		err = store.SetPassword(id, request.PostForm.Get("password"))
	case "disable", "enable":
		if !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		err = store.SetDisabled(id, request.PostForm.Get("action") == "disable")
	case "grants":
		err = store.SetGrants(id, request.PostForm["profiles"])
	case "role":
		if !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		err = store.SetRole(id, request.PostForm.Get("role"))
	default:
		s.redirectManage(writer, request, "invalid")
		return
	}
	switch {
	case err == nil:
		_ = s.access.Reload()
		s.logger.Info("management action", "action", "account_update", "status", "updated")
		s.redirectManage(writer, request, "account_updated")
	case errors.Is(err, access.ErrLastAdmin):
		s.redirectManage(writer, request, "last_admin")
	case errors.Is(err, access.ErrAccountNotFound):
		http.NotFound(writer, request)
	default:
		s.redirectManage(writer, request, "invalid")
	}
}

var manageTemplate = template.Must(template.New("manage").Parse(strings.TrimSpace(`
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>远程浏览器管理</title>
  <style>
    :root {
      --bg-page: #f0f2f5;
      --bg-card: #ffffff;
      --bg-subtle: #f8f9fa;
      --border-color: #dadce0;
      --border-subtle: #e8eaed;
      --border-focus: #1a73e8;
      --text-primary: #202124;
      --text-secondary: #5f6368;
      --color-primary: #1a73e8;
      --color-primary-hover: #1557b0;
      --color-success: #0d652d;
      --color-success-bg: #e6f4ea;
      --color-warning: #b06000;
      --color-warning-bg: #fef7e0;
      --color-warning-border: #fde68a;
      --color-danger: #b3261e;
      --color-danger-bg: #fce8e6;
      --color-danger-border: #f5c2c7;
      --radius: 6px;
      --shadow-card: 0 1px 3px rgba(60,64,67,0.08), 0 1px 2px rgba(60,64,67,0.04);
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 1.5rem;
      background: var(--bg-page);
      color: var(--text-primary);
      max-width: 82rem;
      margin-left: auto;
      margin-right: auto;
    }
    a { color: var(--color-primary); text-decoration: none; }
    a:hover { text-decoration: underline; }
    a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible {
      outline: 2px solid var(--border-focus);
      outline-offset: 2px;
    }
    h1, h2, h3, h4, h5 { color: var(--text-primary); margin: 0; }
    .meta { color: var(--text-secondary); font-size: 0.82rem; }
    .stale, .blocking, .off { color: var(--color-danger); }
    .inline { display: inline; margin: 0; }
    .app-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.5rem;
      margin-bottom: 1.25rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-color);
    }
    .header-main { flex: 1; min-width: 0; }
    .app-title { font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem; }
    .header-meta { margin: 0; }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }
    .header-link {
      font-size: 0.88rem;
      padding: 0.35rem 0.6rem;
      border-radius: var(--radius);
    }
    .logout-form { display: inline; margin: 0; }
    .notice {
      background: #e8f0fe;
      color: #174ea6;
      border: 1px solid #d2e3fc;
      padding: 0.75rem 1rem;
      border-radius: var(--radius);
      margin-bottom: 1.5rem;
      font-weight: 500;
    }
    .nav-tabs {
      display: flex;
      gap: 0.5rem;
      border-bottom: 2px solid var(--border-color);
      margin-bottom: 1.5rem;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      flex-wrap: wrap;
    }
    .tab-item {
      display: inline-flex;
      align-items: center;
      padding: 0.55rem 1.1rem;
      font-size: 0.95rem;
      font-weight: 500;
      color: var(--text-secondary);
      text-decoration: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -2px;
      white-space: nowrap;
      border-radius: var(--radius) var(--radius) 0 0;
      transition: color 0.15s ease, border-color 0.15s ease;
    }
    .tab-item:hover {
      color: var(--color-primary);
      text-decoration: none;
      background: var(--bg-subtle);
    }
    .tab-item.active {
      color: var(--color-primary);
      font-weight: 600;
      border-bottom-color: var(--color-primary);
      background: var(--bg-card);
    }
    .section-browsers, .section-jobs, .section-accounts { margin-bottom: 2rem; }
    .section-header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .section-title { font-size: 1.15rem; font-weight: 600; }
    .panel {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow-card);
      padding: 1.25rem;
      margin-bottom: 1.25rem;
    }
    .panel-header { margin-bottom: 1rem; }
    .panel-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.25rem; }
    .callout-panel { background: #fef7e0; border-color: #fde68a; }
    .browser-card-list { display: flex; flex-direction: column; gap: 1.25rem; }
    .browser-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow-card);
      padding: 1.25rem;
    }
    .browser-card.is-disabled { border-left: 4px solid var(--text-secondary); }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
      margin-bottom: 0.85rem;
      flex-wrap: wrap;
    }
    .card-header-main { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
    .card-title { font-size: 1.15rem; font-weight: 600; }
    .card-profile-id { font-size: 0.85rem; }
    .card-badges { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .badge {
      display: inline-flex;
      align-items: center;
      font-size: 0.78rem;
      font-weight: 500;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      border: 1px solid transparent;
      line-height: 1.3;
    }
    .badge-count { background: #e8eaed; color: #3c4043; font-size: 0.82rem; }
    .badge-success { background: var(--color-success-bg); color: var(--color-success); border-color: #ceead6; }
    .badge-disabled { background: #f1f3f4; color: #5f6368; border-color: #dadce0; }
    .badge-status { background: #e8f0fe; color: #174ea6; border-color: #d2e3fc; }
    .badge-stale { background: var(--color-danger-bg); color: var(--color-danger); border-color: #fad2cf; }
    .badge-role { background: #f1f3f4; color: #3c4043; border-color: #dadce0; }
    .badge-warning { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning-border); }
    .card-entry {
      background: var(--bg-subtle);
      border-radius: var(--radius);
      padding: 0.65rem 0.85rem;
      margin-bottom: 1rem;
      font-size: 0.88rem;
    }
    .entry-line { display: flex; align-items: baseline; gap: 0.4rem; word-break: break-all; }
    .entry-label { font-weight: 600; flex-shrink: 0; }
    .entry-url { color: var(--color-primary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break: break-all; overflow-wrap: break-word; }
    .entry-accounts { margin-top: 0.25rem; }
    .overview-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.85rem;
      background: var(--bg-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius);
      padding: 0.85rem;
      margin-bottom: 1rem;
    }
    .overview-item { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; word-break: break-word; }
    .overview-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-secondary); }
    .overview-value { font-size: 0.88rem; }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 0.75rem;
      margin-bottom: 0.75rem;
    }
    .form-row {
      display: flex;
      gap: 0.75rem;
      align-items: flex-end;
      flex-wrap: wrap;
      margin-bottom: 0.75rem;
    }
    .form-field {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      flex: 1;
      min-width: 180px;
    }
    .form-field label, .field-label {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    .form-field-action { flex-shrink: 0; }
    .field-help { font-size: 0.8rem; color: var(--text-secondary); margin: 0.25rem 0 0.5rem 0; }
    input[type=text], input[type=url], input[type=password], select, textarea {
      font: inherit;
      font-size: 0.88rem;
      padding: 0.4rem 0.6rem;
      min-height: 38px;
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      background: #fff;
      color: var(--text-primary);
      width: 100%;
      box-sizing: border-box;
    }
    textarea { min-height: 52px; resize: vertical; }
    fieldset {
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 0.6rem 0.85rem;
      margin: 0.5rem 0 0.75rem 0;
    }
    legend { font-size: 0.82rem; font-weight: 600; padding: 0 0.35rem; }
    .chk {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      margin-right: 0.85rem;
      margin-bottom: 0.35rem;
      font-size: 0.88rem;
      cursor: pointer;
    }
    .chk input { margin: 0; }
    .checkbox-group, .radio-group { display: flex; flex-wrap: wrap; align-items: center; }
    .form-actions { margin-top: 0.5rem; }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font: inherit;
      font-size: 0.88rem;
      font-weight: 500;
      min-height: 38px;
      padding: 0.4rem 0.9rem;
      border-radius: var(--radius);
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
      box-sizing: border-box;
      white-space: nowrap;
    }
    .btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
    .btn-primary:hover { background: var(--color-primary-hover); }
    .btn-secondary { background: #fff; color: var(--text-primary); border-color: var(--border-color); }
    .btn-secondary:hover { background: #f1f3f4; }
    .btn-warning { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning-border); }
    .btn-warning:hover { background: #fef3c7; }
    .btn-danger { background: var(--color-danger-bg); color: var(--color-danger); border-color: var(--color-danger-border); }
    .btn-danger:hover { background: #f8d7da; }
    .btn-sm { min-height: 30px; padding: 0.2rem 0.6rem; font-size: 0.82rem; }
    .card-settings, .card-lifecycle {
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-subtle);
      margin-bottom: 0.75rem;
    }
    .settings-title { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-secondary); }
    .lifecycle-actions { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .network-details {
      margin-top: 0.75rem;
      border-top: 1px solid var(--border-subtle);
      padding-top: 0.75rem;
    }
    .details-summary {
      cursor: pointer;
      font-weight: 600;
      font-size: 0.88rem;
      color: var(--color-primary);
      user-select: none;
    }
    .details-content {
      margin-top: 0.75rem;
      padding: 1rem;
      background: var(--bg-subtle);
      border-radius: var(--radius);
      border: 1px solid var(--border-color);
    }
    .sub-form-title { font-size: 0.88rem; font-weight: 600; margin: 0 0 0.5rem 0; }
    .draft-status-panel {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      padding: 0.5rem 0.75rem;
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      margin-bottom: 0.75rem;
    }
    .draft-form-wrapper, .direct-form-wrapper, .apply-draft-wrapper {
      margin-top: 0.75rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-color);
    }
    .danger-zone {
      margin-top: 1rem;
      padding: 0.85rem 1rem;
      border: 1px solid var(--color-danger-border);
      border-radius: var(--radius);
      background: #fffafa;
    }
    .danger-title { font-size: 0.9rem; font-weight: 600; color: var(--color-danger); margin-bottom: 0.25rem; }
    .table-container {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      background: #fff;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow-card);
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }
    th, td { padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border-color); vertical-align: top; }
    th { background: var(--bg-subtle); font-weight: 600; font-size: 0.82rem; color: var(--text-secondary); white-space: nowrap; }
    tr:last-child td { border-bottom: none; }
    .inline-input-group { display: flex; gap: 0.35rem; align-items: center; }
    .inline-input-group input { width: 13rem; }
    .account-btn-group { display: flex; gap: 0.35rem; margin-top: 0.35rem; flex-wrap: wrap; }
    .grants-checkboxes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.35rem; }
    .app-footer {
      margin-top: 2.5rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border-color);
      text-align: center;
    }
    @media (max-width: 1099px) {
      .overview-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 699px) {
      body { padding: 1rem; }
      .app-header { flex-direction: column; align-items: stretch; gap: 1rem; }
      .header-actions { justify-content: flex-start; }
      .nav-tabs { gap: 0.25rem; margin-bottom: 1rem; }
      .tab-item { padding: 0.45rem 0.75rem; font-size: 0.88rem; }
      .overview-grid { grid-template-columns: 1fr; }
      .form-row { flex-direction: column; align-items: stretch; }
      .form-field { width: 100%; min-width: unset; }
      .form-field-action { width: 100%; }
      .form-field-action button { width: 100%; }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <div class="header-main">
      <h1 class="app-title">远程浏览器管理</h1>
      <p class="header-meta meta">管理员 {{.Subject}} · 列表只读取最近一次健康采样，过期即标为 stale；关闭按钮走已验证的停止流程，不删除 Home。</p>
    </div>
    <div class="header-actions">
      <a href="/" class="header-link">返回首页</a>
      <a href="{{.ReauthURL}}" class="header-link">确认密码</a>
      <a href="/auth/password" class="header-link">修改我的密码</a>
      <a href="/manage/environments" class="header-link">JSON</a>
      <form method="post" action="/auth/logout" class="logout-form"><input type="hidden" name="csrf" value="{{.CSRF}}"><button type="submit" class="btn btn-secondary btn-sm">退出登录</button></form>
    </div>
  </header>

  <main class="app-main">
    {{if .Notice}}<div class="notice" role="status">{{.Notice}}</div>{{end}}

    <nav class="nav-tabs" aria-label="管理功能">
      <a href="/manage/?tab=browsers" class="tab-item{{if eq .ActiveTab "browsers"}} active{{end}}"{{if eq .ActiveTab "browsers"}} aria-current="page"{{end}}>浏览器</a>
      {{if .JobsEnabled}}
      <a href="/manage/?tab=jobs" class="tab-item{{if eq .ActiveTab "jobs"}} active{{end}}"{{if eq .ActiveTab "jobs"}} aria-current="page"{{end}}>指纹作业</a>
      {{end}}
      <a href="/manage/?tab=accounts" class="tab-item{{if eq .ActiveTab "accounts"}} active{{end}}"{{if eq .ActiveTab "accounts"}} aria-current="page"{{end}}>访问账号</a>
    </nav>

    {{if eq .ActiveTab "browsers"}}
    <section class="section-browsers" aria-labelledby="browsers-heading">
      <div class="section-header">
        <h2 id="browsers-heading" class="section-title">远程浏览器</h2>
        {{if .Rows}}<span class="badge badge-count">{{len .Rows}} 个环境</span>{{end}}
      </div>

      {{if .CreateDelete}}
      <div class="panel create-browser-panel">
        <div class="panel-header">
          <h3 class="panel-title">新增浏览器</h3>
          <p class="meta">新增浏览器只接受固化环境目录中的 artifact 和受管理网络策略；DIRECT 也必须经过控制器网关。</p>
        </div>
        <form method="post" action="/manage/browsers" class="browser-create-form"><input type="hidden" name="csrf" value="{{.CSRF}}">
          <div class="form-grid">
            <div class="form-field">
              <label for="cb-label">名称</label>
              <input id="cb-label" type="text" name="label" maxlength="64" placeholder="例如：开发环境" required>
            </div>
            <div class="form-field">
              <label for="cb-start-url">起始页 URL</label>
              <input id="cb-start-url" type="url" name="start_url" maxlength="2048" placeholder="起始页 URL" required>
            </div>
            <div class="form-field">
              <label for="cb-env-artifact">环境产物</label>
              {{if .Artifacts}}<select name="environment_artifact_id" id="cb-env-artifact" required>{{range .Artifacts}}<option value="{{.ID}}">{{.ID}}{{if .Locale}} · {{.Locale}}{{end}}{{if .Timezone}} · {{.Timezone}}{{end}}{{if .Screen}} · {{.Screen}}{{end}} · {{.Source}}</option>{{end}}</select>
              {{else}}<input id="cb-env-artifact" type="text" name="environment_artifact_id" maxlength="128" placeholder="固化 artifact ID" required>{{end}}
            </div>
            <div class="form-field">
              <label for="cb-network-mode">网络模式</label>
              <select id="cb-network-mode" name="network_mode"><option value="direct">受管理 DIRECT</option><option value="proxy_required">现有代理策略</option></select>
            </div>
            <div class="form-field">
              <label for="cb-network-policy-id">策略 ID</label>
              <input id="cb-network-policy-id" type="text" name="network_policy_id" maxlength="128" placeholder="策略 ID" required>
            </div>
            <div class="form-field">
              <label for="cb-network-policy-sha">策略 SHA-256</label>
              <input id="cb-network-policy-sha" type="text" name="network_policy_sha256" maxlength="64" placeholder="策略 SHA-256" required>
            </div>
            <div class="form-field">
              <label for="cb-idempotency-key">幂等键</label>
              <input id="cb-idempotency-key" type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
            </div>
          </div>
          <fieldset class="form-field accounts-fieldset">
            <legend class="field-label">分配可登录账号</legend>
            <div class="checkbox-group">{{range .Accounts}}<label class="chk"><input type="checkbox" name="accounts" value="{{.ID}}"> {{.ID}}</label>{{end}}</div>
          </fieldset>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">新增浏览器</button>
          </div>
        </form>
      </div>
      {{else}}
      <div class="panel callout-panel">
        <p class="meta">新增与归档删除尚未启用；现有浏览器仍可修改、停用或安全关闭。</p>
      </div>
      {{end}}

      {{if .Rows}}
      <div class="browser-card-list">
        {{range .Rows}}
        <article class="browser-card{{if not .Enabled}} is-disabled{{end}}">
          <header class="card-header">
            <div class="card-header-main">
              <h3 class="card-title">{{.Label}}</h3>
              {{if ne .Label .ProfileID}}<span class="meta card-profile-id">{{.ProfileID}}</span>{{end}}
            </div>
            <div class="card-badges">
              {{if .Available}}
                {{if .Enabled}}<span class="badge badge-success">已启用</span>{{else}}<span class="badge badge-disabled off">已停用</span>{{end}}
                <span class="badge badge-status">{{.Status}}</span>
                <span class="meta card-revision">修订 {{.Revision}}</span>
              {{else}}
                <span class="badge badge-warning">摘要暂不可用</span>
              {{end}}
            </div>
          </header>

          <div class="card-entry">
            <div class="entry-line"><span class="entry-label">入口：</span><a href="{{.EntryPath}}" class="entry-url">{{$.EntryOrigin}}{{.EntryPath}}</a></div>
            <div class="entry-accounts meta">账号：{{if .Accounts}}{{.Accounts}}{{else}}（未分配）{{end}}</div>
          </div>

          {{if .Available}}
          <div class="overview-grid">
            <div class="overview-item">
              <span class="overview-label">健康状态</span>
              <div class="overview-value">
                {{if .Observed}}
                  <span class="health-overall">{{.Health}}</span>
                  {{if .Stale}} <span class="badge badge-stale stale">已过期</span>{{end}}
                  {{if .HealthCode}}<div class="meta{{if .Blocking}} blocking{{end}}">{{.HealthCode}}{{if .HealthTitle}} · {{.HealthTitle}}{{end}}</div>{{end}}
                  <div class="meta">{{.Checked}}</div>
                {{else}}
                  <span class="meta">未观测</span>
                {{end}}
              </div>
            </div>
            <div class="overview-item">
              <span class="overview-label">网络</span>
              <div class="overview-value">
                <div>{{.Network}}</div>
                {{if .ProxyUpstream}}<div class="meta">{{.ProxyUpstream}}</div>{{else if eq .ConfiguredNetwork "direct"}}<div class="meta">受管理 DIRECT</div>{{end}}
              </div>
            </div>
            <div class="overview-item">
              <span class="overview-label">显示 / 语言 / 时区</span>
              <div class="overview-value">
                <div>{{.Display}}</div>
                {{if .Locale}}<div class="meta">{{.Locale}}</div>{{end}}
              </div>
            </div>
            <div class="overview-item">
              <span class="overview-label">环境产物</span>
              <div class="overview-value meta">{{if .Environment}}{{.Environment}}{{else}}—{{end}}</div>
            </div>
            <div class="overview-item">
              <span class="overview-label">应用 / Home</span>
              <div class="overview-value meta">{{.Home}}</div>
            </div>
          </div>

          {{if .Manage}}
          <div class="card-settings">
            <h4 class="settings-title">常用设置</h4>
            <form method="post" action="/manage/browsers/{{.ProfileID}}" class="settings-form">
              <input type="hidden" name="csrf" value="{{$.CSRF}}">
              <input type="hidden" name="action" value="update">
              <input type="hidden" name="revision" value="{{.Revision}}">
              <div class="form-row">
                <div class="form-field">
                  <label for="label-{{.ProfileID}}">名称</label>
                  <input id="label-{{.ProfileID}}" type="text" name="label" value="{{.Label}}" maxlength="64" placeholder="名称">
                </div>
                <div class="form-field">
                  <label for="url-{{.ProfileID}}">起始页 URL</label>
                  <input id="url-{{.ProfileID}}" type="url" name="start_url" value="{{.StartURL}}" maxlength="2048" placeholder="起始页 URL">
                </div>
                <div class="form-field-action">
                  <button type="submit" class="btn btn-secondary">保存设置</button>
                </div>
              </div>
            </form>
          </div>
          {{end}}

          <div class="card-lifecycle">
            <h4 class="settings-title">生命周期操作</h4>
            <div class="lifecycle-actions">
              {{if .Manage}}
                {{if .Enabled}}
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="disable"><input type="hidden" name="revision" value="{{.Revision}}"><button type="submit" class="btn btn-warning">停用</button></form>
                {{else}}
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="enable"><input type="hidden" name="revision" value="{{.Revision}}"><button type="submit" class="btn btn-primary">启用</button></form>
                {{end}}
              {{end}}
              {{if and .StopAllowed .Running}}
              <form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="stop"><button type="submit" class="btn btn-warning">安全关闭</button></form>
              {{end}}
            </div>
          </div>

          {{if and $.ProxyDrafts .Managed .Manage}}
          <details class="network-details"{{if .Draft}} open{{end}}>
            <summary class="details-summary">配置代理 / 切回 DIRECT</summary>
            <div class="details-content">
              {{with .Draft}}
              <div class="draft-status-panel">
                <div class="draft-info meta">草稿 {{.Protocol}}://{{.Host}}:{{.Port}} · {{.Auth}} · {{if .Expired}}已过期{{else}}{{.ProbeStatus}}{{if .ProbeCode}} {{.ProbeCode}}{{end}}{{end}}</div>
                {{if not .Expired}}
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="proxy_probe"><input type="hidden" name="draft_id" value="{{.ID}}"><button type="submit" class="btn btn-secondary btn-sm">探针</button></form>
                {{end}}
              </div>
              {{end}}

              {{if and .Draft (not .Draft.Expired) (eq .Draft.ProbeStatus "passed")}}
              <div class="apply-draft-wrapper">
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="apply-draft-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="action" value="proxy_apply">
                  <input type="hidden" name="draft_id" value="{{.Draft.ID}}">
                  <input type="hidden" name="revision" value="{{.Revision}}">
                  <div class="form-row">
                    <div class="form-field">
                      <label for="apply-key-{{.ProfileID}}">幂等键</label>
                      <input id="apply-key-{{.ProfileID}}" type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
                    </div>
                    <div class="form-field-action">
                      <button type="submit" class="btn btn-primary">应用到下一代次</button>
                    </div>
                  </div>
                  <p class="field-help meta">探针已通过；下一次启动将应用新代理，需要最近确认过密码。</p>
                </form>
              </div>
              {{end}}

              <div class="draft-form-wrapper">
                <h5 class="sub-form-title">创建新代理草稿</h5>
                <form method="post" action="/manage/browsers/{{.ProfileID}}" autocomplete="off" class="proxy-draft-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="action" value="proxy_draft">
                  <div class="form-grid">
                    <div class="form-field">
                      <label for="proto-{{.ProfileID}}">协议</label>
                      <select id="proto-{{.ProfileID}}" name="protocol"><option value="socks5">socks5</option><option value="http">http</option><option value="https">https</option></select>
                    </div>
                    <div class="form-field">
                      <label for="auth-{{.ProfileID}}">认证方式</label>
                      <select id="auth-{{.ProfileID}}" name="auth"><option value="username_password">用户名/密码 (socks5)</option><option value="basic">basic (http/https)</option><option value="none">无认证</option></select>
                    </div>
                    <div class="form-field">
                      <label for="host-{{.ProfileID}}">代理主机（公网）</label>
                      <input id="host-{{.ProfileID}}" type="text" name="host" maxlength="253" placeholder="代理主机（公网）" required>
                    </div>
                    <div class="form-field">
                      <label for="port-{{.ProfileID}}">端口</label>
                      <input id="port-{{.ProfileID}}" type="text" name="port" maxlength="5" placeholder="端口" required>
                    </div>
                    <div class="form-field">
                      <label for="user-{{.ProfileID}}">用户名</label>
                      <input id="user-{{.ProfileID}}" type="text" name="username" maxlength="4096" placeholder="用户名" autocomplete="off">
                    </div>
                    <div class="form-field">
                      <label for="pass-{{.ProfileID}}">密码</label>
                      <input id="pass-{{.ProfileID}}" type="password" name="password" maxlength="4096" placeholder="密码" autocomplete="new-password">
                    </div>
                  </div>
                  <div class="form-field">
                    <label for="ca-{{.ProfileID}}">HTTPS 代理 CA（可选，PEM）</label>
                    <textarea id="ca-{{.ProfileID}}" name="upstream_ca_pem" rows="2" placeholder="HTTPS 代理 CA（可选，PEM）"></textarea>
                  </div>
                  <div class="form-actions">
                    <button type="submit" class="btn btn-secondary">创建草稿</button>
                  </div>
                </form>
              </div>

              <div class="direct-form-wrapper">
                <h5 class="sub-form-title">切回 DIRECT 策略</h5>
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="direct-switch-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="action" value="network_direct">
                  <input type="hidden" name="revision" value="{{.Revision}}">
                  <div class="form-grid">
                    <div class="form-field">
                      <label for="dir-pol-{{.ProfileID}}">DIRECT 策略 ID</label>
                      <input id="dir-pol-{{.ProfileID}}" type="text" name="network_policy_id" maxlength="128" placeholder="DIRECT 策略 ID" required>
                    </div>
                    <div class="form-field">
                      <label for="dir-sha-{{.ProfileID}}">策略 SHA-256</label>
                      <input id="dir-sha-{{.ProfileID}}" type="text" name="network_policy_sha256" maxlength="64" placeholder="策略 SHA-256" required>
                    </div>
                    <div class="form-field">
                      <label for="dir-key-{{.ProfileID}}">幂等键</label>
                      <input id="dir-key-{{.ProfileID}}" type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
                    </div>
                  </div>
                  <div class="form-actions">
                    <button type="submit" class="btn btn-secondary">切回 DIRECT</button>
                  </div>
                </form>
              </div>
            </div>
          </details>
          {{end}}

          {{if and $.CreateDelete .Manage}}
          <div class="danger-zone">
            <h4 class="danger-title">危险操作</h4>
            <p class="field-help meta">停止浏览器、归档对应 Home 并撤销访问授权；此操作不可逆，需要最近确认过密码。</p>
            <form method="post" action="/manage/browsers/{{.ProfileID}}" class="delete-form">
              <input type="hidden" name="csrf" value="{{$.CSRF}}">
              <input type="hidden" name="action" value="delete">
              <div class="form-row">
                <div class="form-field">
                  <label for="del-key-{{.ProfileID}}">幂等键</label>
                  <input id="del-key-{{.ProfileID}}" type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
                </div>
                <div class="form-field-action">
                  <button type="submit" class="btn btn-danger">归档并删除</button>
                </div>
              </div>
            </form>
          </div>
          {{end}}
          {{else}}
          <div class="card-unavailable"><p class="meta">摘要暂不可用</p></div>
          {{end}}
        </article>
        {{end}}
      </div>
      {{else}}
      <p class="meta">没有配置远程浏览器。</p>
      {{end}}
    </section>
    {{else if and (eq .ActiveTab "jobs") .JobsEnabled}}
    <section class="section-jobs" aria-labelledby="jobs-heading">
      <div class="section-header"><h2 id="jobs-heading" class="section-title">自定义指纹作业</h2></div>
      <p class="meta">只提交高层字段；服务端在隔离容器中一次生成完整产物并执行完整验收（两个 QA Home 各 10 次重建），通过后可在“浏览器”页新增浏览器时选择该产物。当前适配器只支持 Linux、DPR 1；一次只运行一个作业。</p>
      <div class="panel create-job-panel">
        <form method="post" action="/manage/environment-jobs" class="job-create-form"><input type="hidden" name="csrf" value="{{.CSRF}}"><input type="hidden" name="dpr" value="1">
          <div class="form-grid">
            <div class="form-field"><label for="job-locale">Locale</label><input id="job-locale" type="text" name="locale" maxlength="35" placeholder="例如：en-US" required></div>
            <div class="form-field"><label for="job-languages">Languages</label><input id="job-languages" type="text" name="languages" maxlength="200" placeholder="逗号分隔，首项须等于 locale" required></div>
            <div class="form-field"><label for="job-tz">IANA 时区</label><input id="job-tz" type="text" name="timezone" maxlength="64" placeholder="例如：America/New_York" required></div>
            <div class="form-field"><label for="job-sw">屏幕宽</label><input id="job-sw" type="text" name="screen_width" maxlength="4" value="1920" required></div>
            <div class="form-field"><label for="job-sh">屏幕高</label><input id="job-sh" type="text" name="screen_height" maxlength="4" value="1080" required></div>
            <div class="form-field"><label for="job-ww">窗口宽（默认同屏幕）</label><input id="job-ww" type="text" name="window_width" maxlength="4" placeholder="窗口宽（默认同屏幕）"></div>
            <div class="form-field"><label for="job-wh">窗口高（默认同屏幕）</label><input id="job-wh" type="text" name="window_height" maxlength="4" placeholder="窗口高（默认同屏幕）"></div>
          </div>
          <div class="form-actions"><button type="submit" class="btn btn-primary">提交作业</button></div>
        </form>
      </div>
      {{if .Jobs}}
      <div class="table-container">
        <table class="jobs-table">
          <thead><tr><th>作业</th><th>请求</th><th>状态</th><th>结果</th></tr></thead>
          <tbody>
            {{range .Jobs}}<tr>
              <td><div class="job-id">{{.ID}}</div><div class="meta">{{.EnvironmentID}}</div><div class="meta">{{.Actor}} · {{.RequestedAt}}</div></td>
              <td><div>{{.Locale}} · {{.Timezone}}</div><div class="meta">{{.Screen}} · 窗口 {{.Window}}</div></td>
              <td><div>{{.Status}}{{if .Phase}} · {{.Phase}}{{end}}</div>{{if .Code}}<div class="meta{{if eq .Status "failed"}} blocking{{end}}">{{.Code}}{{if .Message}} · {{.Message}}{{end}}</div>{{end}}{{if .UpdatedAt}}<div class="meta">{{.UpdatedAt}}</div>{{end}}</td>
              <td class="meta">{{if .ArtifactSHA256}}<div>产物 {{slice .ArtifactSHA256 0 12}}…</div>{{end}}{{if .AcceptanceSHA256}}<div>报告 {{slice .AcceptanceSHA256 0 12}}…</div>{{end}}{{if .Attempts}}<div>生成尝试 {{.Attempts}}</div>{{end}}</td>
            </tr>{{end}}
          </tbody>
        </table>
      </div>
      {{else}}<p class="meta">没有作业。</p>{{end}}
    </section>
    {{else if eq .ActiveTab "accounts"}}
    <section class="section-accounts" aria-labelledby="accounts-heading">
      <div class="section-header"><h2 id="accounts-heading" class="section-title">访问账号</h2></div>
      <p class="meta">浏览器入口账号只能登录被分配的浏览器；管理员账号可进入本面板。禁用/启用账号、修改角色、重置他人密码前须 <a href="{{.ReauthURL}}">确认密码</a>（5 分钟内有效）。</p>
      {{if .Accounts}}
      <div class="table-container">
        <table class="accounts-table">
          <thead><tr><th>账号</th><th>角色</th><th>状态</th><th>可登录的浏览器</th><th>操作</th></tr></thead>
          <tbody>
            {{range .Accounts}}<tr>
              <td><strong>{{.ID}}</strong></td>
              <td><span class="badge badge-role">{{.Role}}</span></td>
              <td>{{if .Disabled}}<span class="badge badge-disabled off">已禁用</span>{{else}}<span class="badge badge-success">启用</span>{{end}}</td>
              <td><form method="post" action="/manage/accounts/{{.ID}}" class="grants-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="grants"><div class="grants-checkboxes">{{$row := .}}{{range .AllProfiles}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"{{if index $row.Grants .}} checked{{end}}> {{.}}</label>{{end}}</div><button type="submit" class="btn btn-secondary btn-sm">保存分配</button></form></td>
              <td class="account-actions-cell actions">
                <form method="post" action="/manage/accounts/{{.ID}}" class="pwd-reset-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="reset_password"><label for="pwd-{{.ID}}" class="field-label">新密码</label><div class="inline-input-group"><input id="pwd-{{.ID}}" type="password" name="password" minlength="12" maxlength="256" placeholder="12–256 字节" autocomplete="new-password"><button type="submit" class="btn btn-secondary btn-sm">重置密码</button></div></form>
                <div class="account-btn-group">
                  {{if .Disabled}}<form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="enable"><button type="submit" class="btn btn-secondary btn-sm">启用</button></form>
                  {{else}}<form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="disable"><button type="submit" class="btn btn-warning btn-sm">禁用</button></form>{{end}}
                  <form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="role"><input type="hidden" name="role" value="{{if eq .Role "admin"}}user{{else}}admin{{end}}"><button type="submit" class="btn btn-secondary btn-sm">{{if eq .Role "admin"}}改为入口账号{{else}}改为管理员{{end}}</button></form>
                </div>
              </td>
            </tr>{{end}}
          </tbody>
        </table>
      </div>
      {{else}}<p class="meta">账号表暂不可读。</p>{{end}}

      <div class="panel create-account-panel">
        <h3 class="panel-title">新增账号</h3>
        <form method="post" action="/manage/accounts" class="account-create-form"><input type="hidden" name="csrf" value="{{.CSRF}}">
          <div class="form-grid">
            <div class="form-field"><label for="na-acc">账号 ID</label><input id="na-acc" type="text" name="account" maxlength="32" pattern="[a-z0-9][a-z0-9_-]{0,31}" placeholder="账号 ID（小写字母、数字、_-）" required></div>
            <div class="form-field"><label for="na-pwd">密码</label><input id="na-pwd" type="password" name="password" minlength="12" maxlength="256" placeholder="密码（12–256 字节）" autocomplete="new-password" required></div>
          </div>
          <fieldset class="form-field"><legend>角色</legend><div class="radio-group"><label class="chk"><input type="radio" name="role" value="user" checked> 浏览器入口账号</label><label class="chk"><input type="radio" name="role" value="admin"> 管理员（需先确认密码）</label></div></fieldset>
          <fieldset class="form-field"><legend>可登录的浏览器</legend><div class="checkbox-group">{{range .ProfileIDs}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"> {{.}}</label>{{end}}</div></fieldset>
          <div class="form-actions"><button type="submit" class="btn btn-primary">创建账号</button></div>
        </form>
      </div>
    </section>
    {{end}}
  </main>

  <footer class="app-footer">
    <p class="meta">远程浏览器管理 · 生成时间 {{.GeneratedAt}} · 列表只读取最近一次健康采样，过期即标为 stale；关闭按钮走已验证的停止流程，不删除 Home。</p>
  </footer>
</body>
</html>
`)))
