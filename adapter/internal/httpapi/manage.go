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

type environmentCatalogService interface {
	EnvironmentArtifacts(context.Context) ([]profile.EnvironmentArtifactSummary, error)
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
	if _, ok := access.Grants(request); !ok {
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
	drafts, hasDrafts := s.profiles.(proxyDraftService)
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
	data := struct {
		Subject     string
		GeneratedAt string
		Notice      string
		Rows        []manageRow
		Accounts    []accountRow
		ProfileIDs  []string
		EntryOrigin string
		CSRF        string
		ProxyDrafts bool
	}{Subject: access.Subject(request), GeneratedAt: time.Now().UTC().Format(time.RFC3339), Notice: notices[request.URL.Query().Get("notice")],
		Rows: rows, Accounts: accountRows(accounts, profileIDs), ProfileIDs: profileIDs, EntryOrigin: s.publicOrigin.String(), CSRF: access.CSRF(request), ProxyDrafts: hasDrafts}
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
	http.Redirect(writer, request, "/manage/?notice="+url.QueryEscape(notice), http.StatusSeeOther)
}

func (s *Server) manageCreateBrowser(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	_, ok := access.Grants(request)
	manager, available := s.profiles.(browserManagementService)
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
		err := manager.DeleteBrowser(ctx, id, actor, idempotencyKey)
		switch {
		case err == nil:
			s.revokeBrowserGrants(id)
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
  <title>管理面板</title>
  <style>
    body { font: 15px system-ui, sans-serif; margin: 2rem; color: #202124; max-width: 80rem; }
    h1 { font-size: 1.3rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
    table { border-collapse: collapse; width: 100%; font-size: .88rem; }
    td, th { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #ddd; vertical-align: top; }
    .meta { color: #5f6368; font-size: .82rem; }
    .stale, .blocking, .off { color: #b3261e; }
    .notice { background: #e8f0fe; padding: .6rem .8rem; border-radius: 4px; }
    form.inline { display: inline; margin: 0 .2rem 0 0; }
    input[type=text], input[type=url], input[type=password], textarea, select { font: inherit; padding: .25rem .4rem; width: 14rem; box-sizing: border-box; }
    details { margin-top: .3rem; } details form { margin: .3rem 0; }
    button { font: inherit; padding: .3rem .7rem; }
    .actions form { margin: .25rem 0; }
    label.chk { display: inline-block; margin-right: .6rem; }
  </style>
</head>
<body>
  <h1>管理面板</h1>
  <p class="meta">管理员 {{.Subject}} · 生成时间 {{.GeneratedAt}} · 列表只读取最近一次健康采样，过期即标为 stale；关闭按钮走已验证的停止流程，不删除 Home。</p>
  {{if .Notice}}<p class="notice">{{.Notice}}</p>{{end}}
  <h2>远程浏览器</h2>
  <p class="meta">新增浏览器只接受固化环境目录中的 artifact 和受管理网络策略；DIRECT 也必须经过控制器网关。</p>
  <form method="post" action="/manage/browsers"><input type="hidden" name="csrf" value="{{.CSRF}}">
    <input type="text" name="label" maxlength="64" placeholder="名称" required>
    <input type="url" name="start_url" maxlength="2048" placeholder="起始页 URL" required>
    <input type="text" name="environment_artifact_id" maxlength="128" placeholder="固化 artifact ID" required>
    <select name="network_mode"><option value="direct">受管理 DIRECT</option><option value="proxy_required">现有代理策略</option></select>
    <input type="text" name="network_policy_id" maxlength="128" placeholder="策略 ID" required>
    <input type="text" name="network_policy_sha256" maxlength="64" placeholder="策略 SHA-256" required>
    <input type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
    <div>{{range .Accounts}}<label class="chk"><input type="checkbox" name="accounts" value="{{.ID}}"> {{.ID}}</label>{{end}}</div>
    <button>新增浏览器</button>
  </form>
  {{if .Rows}}<table>
    <tr><th>浏览器</th><th>入口 URL / 账号</th><th>记录状态</th><th>健康（采样时间）</th><th>网络</th><th>显示 / 语言 / 时区</th><th>应用 / Home</th><th>环境产物</th><th>操作</th></tr>
    {{range .Rows}}<tr>
      <td>{{.Label}}{{if ne .Label .ProfileID}}<div class="meta">{{.ProfileID}}</div>{{end}}{{if .Available}}{{if not .Enabled}}<div class="off">已停用</div>{{end}}<div class="meta">修订 {{.Revision}}</div>{{end}}</td>
      <td><a href="{{.EntryPath}}">{{$.EntryOrigin}}{{.EntryPath}}</a><div class="meta">账号：{{if .Accounts}}{{.Accounts}}{{else}}（未分配）{{end}}</div></td>
      {{if .Available}}<td>{{.Status}}</td>
      <td>{{if .Observed}}{{.Health}}{{if .Stale}} <span class="stale">已过期</span>{{end}}{{if .HealthCode}}<div class="meta{{if .Blocking}} blocking{{end}}">{{.HealthCode}}{{if .HealthTitle}} · {{.HealthTitle}}{{end}}</div>{{end}}<div class="meta">{{.Checked}}</div>{{else}}<span class="meta">未观测</span>{{end}}</td>
      <td>{{.Network}}{{if .ProxyUpstream}}<div class="meta">{{.ProxyUpstream}}</div>{{else if eq .ConfiguredNetwork "direct"}}<div class="meta">受管理 DIRECT</div>{{end}}
        {{if and $.ProxyDrafts .Managed .Manage}}{{with .Draft}}<div class="meta">草稿 {{.Protocol}}://{{.Host}}:{{.Port}} · {{.Auth}} · {{if .Expired}}已过期{{else}}{{.ProbeStatus}}{{if .ProbeCode}} {{.ProbeCode}}{{end}}{{end}}</div>
          {{if not .Expired}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="proxy_probe"><input type="hidden" name="draft_id" value="{{.ID}}"><button>探针</button></form>{{end}}{{end}}
          {{if and .Draft (not .Draft.Expired) (eq .Draft.ProbeStatus "passed")}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="proxy_apply"><input type="hidden" name="draft_id" value="{{.Draft.ID}}"><input type="hidden" name="revision" value="{{.Revision}}"><input type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required><button>应用到下一代次</button></form>{{end}}
          <details><summary class="meta">配置代理 / 切回 DIRECT</summary>
          <form method="post" action="/manage/browsers/{{.ProfileID}}" autocomplete="off"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="proxy_draft">
            <select name="protocol"><option value="socks5">socks5</option><option value="http">http</option><option value="https">https</option></select>
            <select name="auth"><option value="username_password">用户名/密码 (socks5)</option><option value="basic">basic (http/https)</option><option value="none">无认证</option></select>
            <input type="text" name="host" maxlength="253" placeholder="代理主机（公网）" required> <input type="text" name="port" maxlength="5" placeholder="端口" required>
            <input type="text" name="username" maxlength="4096" placeholder="用户名" autocomplete="off"> <input type="password" name="password" maxlength="4096" placeholder="密码" autocomplete="new-password">
            <textarea name="upstream_ca_pem" rows="2" placeholder="HTTPS 代理 CA（可选，PEM）"></textarea> <button>创建草稿</button></form>
          <form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="network_direct"><input type="hidden" name="revision" value="{{.Revision}}">
            <input type="text" name="network_policy_id" maxlength="128" placeholder="DIRECT 策略 ID" required> <input type="text" name="network_policy_sha256" maxlength="64" placeholder="策略 SHA-256" required> <input type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required><button>切回 DIRECT</button></form>
          </details>{{end}}</td><td>{{.Display}}{{if .Locale}}<div class="meta">{{.Locale}}</div>{{end}}</td><td class="meta">{{.Home}}</td><td class="meta">{{if .Environment}}{{.Environment}}{{else}}—{{end}}</td>
      <td class="actions">
        {{if .Manage}}<form method="post" action="/manage/browsers/{{.ProfileID}}"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="update"><input type="hidden" name="revision" value="{{.Revision}}">
          <input type="text" name="label" value="{{.Label}}" maxlength="64" placeholder="名称"> <input type="url" name="start_url" value="{{.StartURL}}" maxlength="2048" placeholder="起始页 URL"> <button>保存</button></form>
        {{if .Enabled}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="disable"><input type="hidden" name="revision" value="{{.Revision}}"><button>停用</button></form>
        {{else}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="enable"><input type="hidden" name="revision" value="{{.Revision}}"><button>启用</button></form>{{end}}{{end}}
        {{if and .StopAllowed .Running}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="stop"><button>安全关闭</button></form>{{end}}
        {{if .Manage}}<form method="post" action="/manage/browsers/{{.ProfileID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="delete"><input type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required><button>归档并删除</button></form>{{end}}
      </td>
      {{else}}<td colspan="7" class="meta">摘要暂不可用</td>{{end}}
    </tr>{{end}}
  </table>{{else}}<p>没有配置远程浏览器。</p>{{end}}
  <h2>访问账号</h2>
  <p class="meta">浏览器入口账号只能登录被分配的浏览器；管理员账号可进入本面板。禁用/启用账号、修改角色、重置他人密码前须 <a href="/auth/reauth?next=/manage/">确认密码</a>（5 分钟内有效）。</p>
  {{if .Accounts}}<table>
    <tr><th>账号</th><th>角色</th><th>状态</th><th>可登录的浏览器</th><th>操作</th></tr>
    {{range .Accounts}}<tr>
      <td>{{.ID}}</td><td>{{.Role}}</td><td>{{if .Disabled}}<span class="off">已禁用</span>{{else}}启用{{end}}</td>
      <td><form method="post" action="/manage/accounts/{{.ID}}"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="grants">
        {{$row := .}}{{range .AllProfiles}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"{{if index $row.Grants .}} checked{{end}}> {{.}}</label>{{end}} <button>保存分配</button></form></td>
      <td class="actions">
        <form method="post" action="/manage/accounts/{{.ID}}"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="reset_password"><input type="password" name="password" minlength="12" maxlength="256" placeholder="新密码（12–256 字节）" autocomplete="new-password"> <button>重置密码</button></form>
        {{if .Disabled}}<form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="enable"><button>启用</button></form>
        {{else}}<form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="disable"><button>禁用</button></form>{{end}}
        <form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="role"><input type="hidden" name="role" value="{{if eq .Role "admin"}}user{{else}}admin{{end}}"><button>{{if eq .Role "admin"}}改为入口账号{{else}}改为管理员{{end}}</button></form>
      </td>
    </tr>{{end}}
  </table>{{else}}<p class="meta">账号表暂不可读。</p>{{end}}
  <h3>新增账号</h3>
  <form method="post" action="/manage/accounts"><input type="hidden" name="csrf" value="{{.CSRF}}">
    <input type="text" name="account" maxlength="32" pattern="[a-z0-9][a-z0-9_-]{0,31}" placeholder="账号 ID（小写字母、数字、_-）" required>
    <input type="password" name="password" minlength="12" maxlength="256" placeholder="密码（12–256 字节）" autocomplete="new-password" required>
    <label class="chk"><input type="radio" name="role" value="user" checked> 浏览器入口账号</label><label class="chk"><input type="radio" name="role" value="admin"> 管理员（需先确认密码）</label>
    <div>{{range .ProfileIDs}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"> {{.}}</label>{{end}}</div>
    <button>创建账号</button>
  </form>
  <p class="meta"><a href="/manage/environments">JSON</a> · <a href="/">返回首页</a> · <a href="/auth/password">修改我的密码</a></p>
  <form method="post" action="/auth/logout"><input type="hidden" name="csrf" value="{{.CSRF}}"><button>退出登录</button></form>
</body>
</html>
`)))
