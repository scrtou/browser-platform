package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/base64"
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

type browserRecordService interface {
	Records() []profile.Record
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

type templateCatalogService interface {
	CompatibleTemplates(context.Context) ([]profile.CompatibleTemplateSummary, error)
}

type templateMutationService interface {
	ApplyBrowserTemplate(context.Context, string, int, string, string, string, string, string) (profile.Record, error)
	RollbackBrowserTemplate(context.Context, string, int, int, string, string) (profile.Record, error)
}

type legacyMigrationService interface {
	LegacyMigration(string) (profile.LegacyMigrationSummary, bool)
	MigrateLegacyNetwork(context.Context, string, int, string, string, string) (profile.Record, error)
	RollbackLegacyNetwork(context.Context, string, int, string, string, string) (profile.Record, error)
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

// networkProfileService is the R7C API. It is intentionally separate from
// the R7E page/tab work: these handlers expose redacted JSON and form writes,
// while the later UI only renders this already-validated service surface.
type networkProfileService interface {
	NetworkProfiles() ([]profile.NetworkProfileRevisionSummary, error)
	CreateNetworkProfileDraft(context.Context, string, profile.NetworkProfileDraftRequest) (profile.NetworkProfileRevisionSummary, error)
	ProbeNetworkProfileDraft(context.Context, string, string, string) (profile.NetworkProfileRevisionSummary, error)
	DisableNetworkProfile(string, int, string, string) (profile.NetworkProfileRevisionSummary, error)
	RevokeNetworkProfile(context.Context, string, int, string, string) (profile.NetworkProfileRevisionSummary, error)
	BindNetworkProfile(context.Context, string, int, string, int, string, string) (profile.Record, error)
}

type managedDirectService interface {
	SetBrowserManagedDirect(context.Context, string, int, string, string) (profile.Record, error)
}

// notices are the only strings the page echoes from a query parameter; any
// other value renders nothing.
var notices = map[string]string{
	"create_template":          "所选引擎与指纹组合已不可用，请刷新页面，重新选择对应引擎下的已验收指纹。",
	"template_saved":           "模板已保存。选择指纹模板与显示模板生成组合，通过验收后可用于浏览器。",
	"updated":                  "已保存。",
	"unchanged":                "没有需要保存的更改。",
	"stopped":                  "浏览器已安全关闭并确认资源清理。",
	"stop_pending":             "停止尚未确认完成，占用已保留；稍后重试或由运维对账。",
	"stop_conflict":            "当前状态不允许停止；请稍后重试或由运维对账。",
	"disabled":                 "浏览器已停用；新的启动和复用会被拒绝，已运行的画面不受影响。",
	"enabled":                  "浏览器已启用。",
	"revision":                 "记录已被其他操作修改，请核对后重试。",
	"invalid":                  "输入无效，未保存。",
	"unavailable":              "操作暂时不可用，未保存。",
	"created":                  "浏览器已创建，固定入口地址已生效。",
	"deleted":                  "浏览器已停止、归档 Home 并撤销应用。",
	"busy":                     "浏览器仍占用运行资源，未删除。",
	"account_created":          "账号已创建。",
	"account_updated":          "账号已更新。",
	"account_exists":           "账号已存在。",
	"last_admin":               "不能禁用或降级最后一个启用的管理员。",
	"reauth":                   "该操作需要重新确认密码。",
	"draft_created":            "代理草稿已创建，凭据只保存在控制器 Secret Store；请执行探针。",
	"draft_probed":             "探针通过，可在浏览器停止后应用到下一代次。",
	"draft_failed":             "探针未通过；草稿保留可重试或重新提交。",
	"draft_missing":            "代理草稿不存在、已过期或已被替换。",
	"draft_unprobed":           "草稿尚未通过探针，不能应用。",
	"network_applied":          "网络修订已固化；下一次启动使用新的代理或 DIRECT 策略。",
	"network_busy":             "浏览器仍占用运行资源，网络修订未应用。",
	"unmanaged":                "该浏览器不是受管理网络，不能配置代理。",
	"network_profile_created":  "代理配置草稿已创建；凭据已提交到 Secret Store，请完成探针后再绑定。",
	"network_profile_probed":   "代理配置探针已完成；通过的修订现在可供浏览器选择。",
	"network_profile_disabled": "代理修订已停用；已有引用保持，新绑定不再提供该修订。",
	"network_profile_revoked":  "代理修订已撤销。",
	"data_deleted":             "已删除，列表和可选项已更新。",
	"data_referenced":          "仍被浏览器或其回退记录引用，无法删除。请先解除关联。",
	"data_busy":                "验收任务尚未结束，无法删除。",
	"data_builtin":             "系统内置模板和验收组合不能删除。",
	"data_delete_failed":       "删除未完成，请刷新后重试；原记录和证据保留。",
	"account_deleted":          "账号已删除，其登录和显示访问权限已撤销。",
	"account_self_delete":      "不能删除当前登录账号，请使用其他管理员账号操作。",

	"network_profile_rejected": "代理配置操作被拒绝；目录和浏览器状态未被降级。",
	"template_applied":         "浏览器、指纹与显示模板新修订已应用；下一次启动使用该组合。",
	"template_rolled_back":     "已回退到选定的模板历史 revision；网络绑定保持不变。",
	"template_busy":            "浏览器仍占用运行资源，模板修订未应用。",
	"template_invalid":         "模板组合不可用或已失效，未修改浏览器。",
	"job_created":              "自定义指纹作业已排队；执行器将在隔离容器中生成并完整验收，通过后出现在固化环境目录。",
	"job_busy":                 "排队或运行中的作业已达上限，请稍后再提交。",
	"job_invalid":              "自定义指纹字段无效或当前适配器不支持（仅 Linux、DPR 1、有效 BCP 47 与 IANA 名称）。",
}

func (s *Server) networkProfileService() (networkProfileService, bool) {
	service, ok := s.profiles.(networkProfileService)
	return service, ok && managementCapabilities(s.profiles).NetworkProfiles
}

func (s *Server) manageNetworkProfileList(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok {
		http.NotFound(writer, request)
		return
	}
	service, ok := s.networkProfileService()
	if !ok {
		http.NotFound(writer, request)
		return
	}
	profiles, err := service.NetworkProfiles()
	if err != nil {
		http.Error(writer, "Network profiles are not available", http.StatusServiceUnavailable)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version  int                                     `json:"version"`
		Profiles []profile.NetworkProfileRevisionSummary `json:"profiles"`
	}{Version: 1, Profiles: profiles})
}

func networkProfileErrorStatus(err error) int {
	switch {
	case errors.Is(err, profile.ErrNetworkProfileNotFound), errors.Is(err, profile.ErrProfileNotFound):
		return http.StatusNotFound
	case errors.Is(err, profile.ErrNetworkProfileReferenced), errors.Is(err, profile.ErrNetworkProfileNotAccepted),
		errors.Is(err, profile.ErrNetworkProfileUnauthorized), errors.Is(err, profile.ErrRevisionMismatch),
		errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrOwnershipUnknown), errors.Is(err, profile.ErrStopUnconfirmed):
		return http.StatusConflict
	case errors.Is(err, profile.ErrNetworkProfileInvalid), errors.Is(err, profile.ErrProxyDraftInvalid):
		return http.StatusBadRequest
	default:
		return http.StatusServiceUnavailable
	}
}

func writeNetworkProfileResult(writer http.ResponseWriter, status int, summary profile.NetworkProfileRevisionSummary) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(struct {
		Version int                                   `json:"version"`
		Profile profile.NetworkProfileRevisionSummary `json:"network_profile"`
	}{Version: 1, Profile: summary})
}

func (s *Server) manageNetworkProfileWrite(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok {
		http.NotFound(writer, request)
		return
	}
	service, ok := s.networkProfileService()
	if !ok {
		http.NotFound(writer, request)
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 32<<10)
	if request.ParseForm() != nil {
		http.Error(writer, "Invalid network profile request", http.StatusBadRequest)
		return
	}
	uiRequest := request.PostForm.Get("return_to") == "network"
	action, actor := strings.TrimSpace(request.PostForm.Get("action")), access.Subject(request)
	if s.access != nil && !s.access.Reauthenticated(request) {
		if action == "delete" {
			s.redirectManage(writer, request, "reauth")
			return
		}
		if !writeReauthJSON(writer, request) {
			http.Error(writer, "Recent password confirmation is required", http.StatusForbidden)
		}
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	var summary profile.NetworkProfileRevisionSummary
	var err error
	status := http.StatusOK
	switch action {
	case "delete":
		s.manageNetworkDelete(writer, request)
		return
	case "create":
		port, portErr := strconv.Atoi(strings.TrimSpace(request.PostForm.Get("port")))
		if portErr != nil {
			http.Error(writer, "Invalid network profile request", http.StatusBadRequest)
			return
		}
		draft := profile.NetworkProfileDraftRequest{ID: strings.TrimSpace(request.PostForm.Get("id")), Label: strings.TrimSpace(request.PostForm.Get("label")),
			IdempotencyKey: strings.TrimSpace(request.PostForm.Get("idempotency_key")), Protocol: strings.TrimSpace(request.PostForm.Get("protocol")),
			Auth: strings.TrimSpace(request.PostForm.Get("auth")), Host: strings.TrimSpace(request.PostForm.Get("host")), Port: port,
			Username: request.PostForm.Get("username"), Password: request.PostForm.Get("password"), UpstreamCAPEM: strings.TrimSpace(request.PostForm.Get("upstream_ca_pem"))}
		request.PostForm.Del("username")
		request.PostForm.Del("password")
		summary, err = service.CreateNetworkProfileDraft(ctx, actor, draft)
		draft.Username, draft.Password = "", ""
		status = http.StatusCreated
	case "probe":
		summary, err = service.ProbeNetworkProfileDraft(ctx, strings.TrimSpace(request.PostForm.Get("id")), strings.TrimSpace(request.PostForm.Get("draft_id")), actor)
	case "disable", "revoke":
		revision, valid := parseRevision(request.PostForm.Get("revision"))
		key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
		if !valid || key == "" || len(key) > 128 {
			http.Error(writer, "Invalid network profile request", http.StatusBadRequest)
			return
		}
		if action == "disable" {
			summary, err = service.DisableNetworkProfile(strings.TrimSpace(request.PostForm.Get("id")), revision, actor, key)
		} else {
			summary, err = service.RevokeNetworkProfile(ctx, strings.TrimSpace(request.PostForm.Get("id")), revision, actor, key)
		}
	default:
		http.Error(writer, "Invalid network profile request", http.StatusBadRequest)
		return
	}
	if err != nil {
		s.logger.Warn("management action", "action", "network_profile_"+action, "status", "rejected", "error", err)
		if uiRequest {
			http.Redirect(writer, request, "/manage/?tab=network&notice=network_profile_rejected", http.StatusSeeOther)
			return
		}
		http.Error(writer, "Network profile operation was rejected", networkProfileErrorStatus(err))
		return
	}
	s.logger.Info("management action", "action", "network_profile_"+action, "network_profile", summary.ID, "revision", summary.Revision, "status", summary.Status)
	if uiRequest {
		notice := map[string]string{"create": "network_profile_created", "probe": "network_profile_probed", "disable": "network_profile_disabled", "revoke": "network_profile_revoked"}[action]
		http.Redirect(writer, request, "/manage/?tab=network&notice="+notice, http.StatusSeeOther)
		return
	}
	writeNetworkProfileResult(writer, status, summary)
}

func (s *Server) manageNetworkProfileBind(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok {
		http.NotFound(writer, request)
		return
	}
	service, ok := s.networkProfileService()
	if !ok {
		http.NotFound(writer, request)
		return
	}
	browserID := request.PathValue("profile")
	grant, ok := grantFor(request, browserID)
	if !ok || !hasCapability(grant, "manage") {
		http.Error(writer, "Forbidden", http.StatusForbidden)
		return
	}
	if s.access != nil && !s.access.Reauthenticated(request) {
		if !writeReauthJSON(writer, request) {
			http.Error(writer, "Recent password confirmation is required", http.StatusForbidden)
		}
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil {
		http.Error(writer, "Invalid network binding request", http.StatusBadRequest)
		return
	}
	uiRequest := request.PostForm.Get("return_to") == "browsers"
	browserRevision, browserOK := parseRevision(request.PostForm.Get("browser_revision"))
	networkRevision, networkOK := parseRevision(request.PostForm.Get("network_revision"))
	key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
	if !browserOK || !networkOK || key == "" || len(key) > 128 {
		http.Error(writer, "Invalid network binding request", http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	record, err := service.BindNetworkProfile(ctx, browserID, browserRevision, strings.TrimSpace(request.PostForm.Get("network_profile_id")), networkRevision, access.Subject(request), key)
	if err != nil {
		s.logger.Warn("management action", "profile", browserID, "action", "network_profile_bind", "status", "rejected", "error", err)
		if uiRequest {
			notice := "unavailable"
			switch {
			case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrStopUnconfirmed), errors.Is(err, profile.ErrOwnershipUnknown):
				notice = "network_busy"
			case errors.Is(err, profile.ErrRevisionMismatch):
				notice = "revision"
			case errors.Is(err, profile.ErrNetworkProfileNotAccepted), errors.Is(err, profile.ErrNetworkProfileUnauthorized), errors.Is(err, profile.ErrNetworkProfileInvalid):
				notice = "invalid"
			}
			s.redirectManage(writer, request, notice)
			return
		}
		http.Error(writer, "Network profile binding was rejected", networkProfileErrorStatus(err))
		return
	}
	if uiRequest {
		s.redirectManage(writer, request, "network_applied")
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version                int    `json:"version"`
		ProfileID              string `json:"profile_id"`
		Revision               int    `json:"revision"`
		NetworkProfileID       string `json:"network_profile_id"`
		NetworkProfileRevision int    `json:"network_profile_revision"`
	}{Version: 1, ProfileID: record.ID, Revision: record.Revision, NetworkProfileID: record.NetworkProfileID, NetworkProfileRevision: record.NetworkProfileRevision})
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

func (s *Server) manageTemplateCatalog(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || !managementCapabilities(s.profiles).TemplateCatalog {
		http.NotFound(writer, request)
		return
	}
	catalog, ok := s.profiles.(templateCatalogService)
	if !ok {
		http.Error(writer, "Template catalog is not available", http.StatusNotImplemented)
		return
	}
	items, err := catalog.CompatibleTemplates(request.Context())
	if err != nil {
		http.Error(writer, "Template catalog is not available", http.StatusServiceUnavailable)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version      int                                 `json:"version"`
		Combinations []profile.CompatibleTemplateSummary `json:"combinations"`
	}{Version: 1, Combinations: items})
}

func templateChangeErrorStatus(err error) int {
	switch {
	case errors.Is(err, profile.ErrProfileNotFound):
		return http.StatusNotFound
	case errors.Is(err, profile.ErrRevisionMismatch), errors.Is(err, profile.ErrBrowserBusy),
		errors.Is(err, profile.ErrTemplateChangePending), errors.Is(err, profile.ErrOwnershipUnknown),
		errors.Is(err, profile.ErrStopUnconfirmed):
		return http.StatusConflict
	case errors.Is(err, profile.ErrTemplateCatalogUnavailable), errors.Is(err, profile.ErrArtifactUnavailable):
		return http.StatusUnprocessableEntity
	default:
		return http.StatusServiceUnavailable
	}
}

func (s *Server) manageTemplateChange(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	if _, ok := access.Grants(request); !ok || !managementCapabilities(s.profiles).TemplateCatalog {
		http.NotFound(writer, request)
		return
	}
	service, ok := s.profiles.(templateMutationService)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	browserID := request.PathValue("profile")
	grant, ok := grantFor(request, browserID)
	if !ok || !hasCapability(grant, "manage") {
		http.Error(writer, "Forbidden", http.StatusForbidden)
		return
	}
	if s.access != nil && !s.access.Reauthenticated(request) {
		if !writeReauthJSON(writer, request) {
			http.Error(writer, "Recent password confirmation is required", http.StatusForbidden)
		}
		return
	}
	request.Body = http.MaxBytesReader(writer, request.Body, 8192)
	if request.ParseForm() != nil || len(request.PostForm["action"]) != 1 {
		http.Error(writer, "Invalid template change request", http.StatusBadRequest)
		return
	}
	uiRequest := request.PostForm.Get("return_to") == "browsers"
	expectedRevision, revisionOK := parseRevision(request.PostForm.Get("browser_revision"))
	key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
	if !revisionOK || key == "" || len(key) > 128 {
		http.Error(writer, "Invalid template change request", http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	var record profile.Record
	var err error
	switch request.PostForm.Get("action") {
	case "apply":
		browserTemplateID := strings.TrimSpace(request.PostForm.Get("browser_template_id"))
		artifactID := strings.TrimSpace(request.PostForm.Get("environment_artifact_id"))
		displayTemplateID := strings.TrimSpace(request.PostForm.Get("display_template_id"))
		if combination := strings.TrimSpace(request.PostForm.Get("template_combination")); combination != "" {
			parts := strings.Split(combination, "|")
			if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
				if uiRequest {
					s.redirectManage(writer, request, "template_invalid")
					return
				}
				http.Error(writer, "Invalid template change request", http.StatusBadRequest)
				return
			}
			browserTemplateID, artifactID, displayTemplateID = parts[0], parts[1], parts[2]
		}
		record, err = service.ApplyBrowserTemplate(
			ctx, browserID, expectedRevision,
			browserTemplateID, artifactID, displayTemplateID,
			access.Subject(request), key,
		)
	case "rollback":
		targetRevision, targetOK := parseRevision(request.PostForm.Get("target_revision"))
		if !targetOK {
			http.Error(writer, "Invalid template rollback request", http.StatusBadRequest)
			return
		}
		record, err = service.RollbackBrowserTemplate(ctx, browserID, expectedRevision, targetRevision, access.Subject(request), key)
	default:
		http.Error(writer, "Invalid template change request", http.StatusBadRequest)
		return
	}
	if err != nil {
		s.logger.Warn("management action", "profile", browserID, "action", "template_"+request.PostForm.Get("action"), "status", "rejected", "error", err)
		if uiRequest {
			notice := "unavailable"
			switch {
			case errors.Is(err, profile.ErrRevisionMismatch):
				notice = "revision"
			case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrTemplateChangePending), errors.Is(err, profile.ErrOwnershipUnknown), errors.Is(err, profile.ErrStopUnconfirmed):
				notice = "template_busy"
			case errors.Is(err, profile.ErrTemplateCatalogUnavailable), errors.Is(err, profile.ErrArtifactUnavailable):
				notice = "template_invalid"
			}
			s.redirectManage(writer, request, notice)
			return
		}
		http.Error(writer, "Template change was rejected", templateChangeErrorStatus(err))
		return
	}
	if uiRequest {
		notice := "template_applied"
		if request.PostForm.Get("action") == "rollback" {
			notice = "template_rolled_back"
		}
		s.redirectManage(writer, request, notice)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(struct {
		Version                     int    `json:"version"`
		ProfileID                   string `json:"profile_id"`
		Revision                    int    `json:"revision"`
		BrowserTemplateID           string `json:"browser_template_id"`
		BrowserTemplateRevision     int    `json:"browser_template_revision"`
		EnvironmentArtifactID       string `json:"environment_artifact_id"`
		EnvironmentTemplateRevision int    `json:"environment_template_revision"`
		DisplayTemplateID           string `json:"display_template_id"`
		DisplayTemplateRevision     int    `json:"display_template_revision"`
	}{
		Version: 1, ProfileID: record.ID, Revision: record.Revision,
		BrowserTemplateID: record.BrowserTemplateID, BrowserTemplateRevision: record.BrowserTemplateRevision,
		EnvironmentArtifactID: record.EnvironmentArtifactID, EnvironmentTemplateRevision: record.EnvironmentTemplateRevision,
		DisplayTemplateID: record.DisplayTemplateID, DisplayTemplateRevision: record.DisplayTemplateRevision,
	})
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
	nonceBytes := make([]byte, 18)
	if _, err := rand.Read(nonceBytes); err != nil {
		http.Error(writer, "Could not prepare management page", http.StatusInternalServerError)
		return
	}
	nonce := base64.RawStdEncoding.EncodeToString(nonceBytes)
	writer.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'nonce-"+nonce+"'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
	var artifacts []profile.EnvironmentArtifactSummary
	if catalog, ok := s.profiles.(environmentCatalogService); ok && capabilities.CreateDelete {
		if listed, err := catalog.EnvironmentArtifacts(ctx); err == nil {
			artifacts = listed
		}
	}
	var sources profile.TemplateSources
	if service, ok := s.profiles.(templateSourceService); ok && capabilities.EnvironmentJobs {
		var sourceErr error
		sources, sourceErr = service.TemplateSources()
		if tab := request.URL.Query().Get("tab"); sourceErr != nil && (tab == "fingerprint-data" || tab == "jobs" || tab == "fingerprints" || tab == "displays") {
			http.Error(writer, "Template service unavailable", http.StatusServiceUnavailable)
			return
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
	var networkProfiles []profile.NetworkProfileRevisionSummary
	networkService, hasNetworkProfiles := s.networkProfileService()
	if hasNetworkProfiles {
		listed, err := networkService.NetworkProfiles()
		if err != nil {
			hasNetworkProfiles = false
		} else {
			networkProfiles = listed
		}
	}
	var templateCombinations []profile.CompatibleTemplateSummary
	var createTemplateCombinations []profile.CompatibleTemplateSummary
	if catalog, ok := s.profiles.(templateCatalogService); ok && capabilities.TemplateCatalog {
		if listed, err := catalog.CompatibleTemplates(ctx); err == nil {
			templateCombinations = listed
			createTemplateCombinations = newBrowserTemplates(templateCombinations)
		}
	}
	acceptedNetworkProfiles := make([]profile.NetworkProfileRevisionSummary, 0, len(networkProfiles))
	createNetworkProfiles := make([]profile.NetworkProfileRevisionSummary, 0, len(networkProfiles))
	for _, item := range networkProfiles {
		if item.Status == profile.NetworkRevisionAccepted && !item.Expired {
			acceptedNetworkProfiles = append(acceptedNetworkProfiles, item)
			createNetworkProfiles = append(createNetworkProfiles, item)
		}
	}
	for index := range rows {
		if service, ok := s.profiles.(legacyMigrationService); ok {
			if migration, available := service.LegacyMigration(rows[index].ProfileID); available {
				rows[index].LegacyMigration = &migration
			}
		}
		for _, item := range acceptedNetworkProfiles {
			if item.Auth == "none" || stringSliceContains(item.AllowedProfiles, rows[index].ProfileID) {
				rows[index].NetworkProfiles = append(rows[index].NetworkProfiles, networkProfileRows([]profile.NetworkProfileRevisionSummary{item})...)
			}
		}
	}
	if records, ok := s.profiles.(browserRecordService); ok {
		byID := make(map[string]profile.Record)
		for _, record := range records.Records() {
			byID[record.ID] = record
		}
		for index := range rows {
			record, found := byID[rows[index].ProfileID]
			if !found {
				continue
			}
			rows[index].DisplayPreference = record.DisplayPreference
			rows[index].UIScalingPercent = record.UIScalingPercent
			if scaling, ok := s.profiles.(interface{ UIScalingPreference(string) (int, int, bool) }); ok {
				_, _, rows[index].UIScalingSupported = scaling.UIScalingPreference(record.ID)
			}
			rows[index].NetworkSelection = browserNetworkSelection(record.NetworkMode, record.NetworkProfileID, record.NetworkProfileRevision)
			rows[index].ResolutionMode = record.ResolutionMode
			rows[index].BrowserTemplateID = record.BrowserTemplateID
			rows[index].EnvironmentArtifactID = record.EnvironmentArtifactID
			rows[index].DisplayTemplateID = record.DisplayTemplateID
			for _, snapshot := range record.TemplateHistory {
				rows[index].TemplateHistory = append(rows[index].TemplateHistory, templateHistoryRow{
					ProfileRevision: snapshot.ProfileRevision, BrowserTemplateID: snapshot.Binding.BrowserTemplateID,
					EnvironmentArtifactID: snapshot.Binding.EnvironmentArtifactID, DisplayTemplateID: snapshot.Binding.DisplayTemplateID,
				})
			}
		}
	}
	for index := range rows {
		rows[index].NetworkSelectionAvailable = availableBrowserNetwork(rows[index], capabilities.ManagedDirect)
	}
	_, dataDeletion := s.profiles.(templateDataDeleteService)
	_, networkDeletion := s.profiles.(networkDeleteService)
	createBrowsers, _, _ := templateChoices(createTemplateCombinations)
	applyBrowsers, applyFingerprints, applyDisplays := templateChoices(templateCombinations)
	activeTab := "browsers"
	dataSection := "fingerprints"
	switch request.URL.Query().Get("tab") {
	case "network":
		if hasNetworkProfiles {
			activeTab = "network"
		}
	case "fingerprint-data", "jobs", "fingerprints", "displays":
		if hasJobs {
			activeTab = "fingerprint-data"
			switch request.URL.Query().Get("tab") {
			case "jobs":
				dataSection = "combinations"
			case "displays":
				dataSection = "displays"
			case "fingerprint-data":
				switch section := request.URL.Query().Get("section"); section {
				case "displays", "combinations":
					dataSection = section
				}
			}
		}
	case "accounts":
		activeTab = "accounts"
	}
	reauthNext := "/manage/?tab=" + activeTab
	if activeTab == "fingerprint-data" {
		reauthNext += "&section=" + dataSection
	}
	reauthURL := "/auth/reauth?next=" + url.QueryEscape(reauthNext)
	var bStats struct{ Total, Running, Healthy, Issues int }
	bStats.Total = len(rows)
	for _, r := range rows {
		if r.Running {
			bStats.Running++
		}
		if r.Available && r.Observed && !r.Stale && !r.Blocking && r.Health == "healthy" {
			bStats.Healthy++
		}
		if r.Stale || r.Blocking || !r.Available || (r.Observed && r.Health != "healthy") {
			bStats.Issues++
		}
	}

	var nStats struct{ Total, Accepted, Pending, References int }
	nStats.Total = len(networkProfiles)
	for _, np := range networkProfiles {
		if np.Status == "accepted" && !np.Expired {
			nStats.Accepted++
		} else if np.Status == "pending" && !np.Expired {
			nStats.Pending++
		}
		nStats.References += np.References
	}

	var dStats struct{ Fingerprints, Displays, Combinations, Jobs int }
	dStats.Fingerprints = len(sources.Fingerprints)
	dStats.Displays = len(sources.Displays)
	dStats.Combinations = len(templateCombinations)
	dStats.Jobs = len(jobs)

	var aStats struct{ Total, Admins, Enabled, Disabled int }
	aStats.Total = len(accounts)
	for _, a := range accounts {
		if a.Role == "admin" {
			aStats.Admins++
		}
		if a.Disabled {
			aStats.Disabled++
		} else {
			aStats.Enabled++
		}
	}

	data := struct {
		Subject                       string
		ScriptNonce                   string
		GeneratedAt                   string
		Notice                        string
		ActiveTab                     string
		DataSection                   string
		ReauthURL                     string
		Rows                          []manageRow
		Accounts                      []accountRow
		ProfileIDs                    []string
		EntryOrigin                   string
		CSRF                          string
		ProxyDrafts                   bool
		Artifacts                     []profile.EnvironmentArtifactSummary
		Jobs                          []profile.EnvironmentJobSummary
		Sources                       profile.TemplateSources
		JobsEnabled                   bool
		NetworkProfiles               []networkProfileRow
		CreateNetworkProfiles         []networkProfileRow
		NetworkEnabled                bool
		TemplateCombinations          []profile.CompatibleTemplateSummary
		CreateTemplateCombinations    []profile.CompatibleTemplateSummary
		TemplateCatalogEnabled        bool
		CreateBrowserChoices          []templateChoice
		CreateFingerprintChoices      []createFingerprintChoice
		ApplyBrowserChoices           []templateChoice
		ApplyFingerprintChoices       []templateChoice
		ApplyDisplayChoices           []templateChoice
		ManagedDirect                 bool
		CreateDelete                  bool
		DataDeletion, NetworkDeletion bool
		BrowserStats                  struct{ Total, Running, Healthy, Issues int }
		NetworkStats                  struct{ Total, Accepted, Pending, References int }
		DataStats                     struct{ Fingerprints, Displays, Combinations, Jobs int }
		AccountStats                  struct{ Total, Admins, Enabled, Disabled int }
	}{Subject: access.Subject(request), ScriptNonce: nonce, GeneratedAt: time.Now().UTC().Format(time.RFC3339), Notice: notices[request.URL.Query().Get("notice")],
		ActiveTab: activeTab, DataSection: dataSection, ReauthURL: reauthURL, Rows: rows, Accounts: accountRows(accounts, profileIDs), ProfileIDs: profileIDs,
		EntryOrigin: s.publicOrigin.String(), CSRF: access.CSRF(request), ProxyDrafts: hasDrafts,
		Sources: sources, Artifacts: artifacts, Jobs: jobs, JobsEnabled: hasJobs && capabilities.EnvironmentJobs,
		NetworkProfiles: networkProfileRows(networkProfiles), CreateNetworkProfiles: networkProfileRows(createNetworkProfiles), NetworkEnabled: hasNetworkProfiles,
		TemplateCombinations: templateCombinations, CreateTemplateCombinations: createTemplateCombinations,
		TemplateCatalogEnabled: capabilities.TemplateCatalog,
		CreateBrowserChoices:   createBrowsers, CreateFingerprintChoices: createFingerprintChoices(createTemplateCombinations),
		ApplyBrowserChoices: applyBrowsers, ApplyFingerprintChoices: applyFingerprints, ApplyDisplayChoices: applyDisplays,
		ManagedDirect: capabilities.ManagedDirect, CreateDelete: capabilities.CreateDelete, DataDeletion: dataDeletion, NetworkDeletion: networkDeletion,
		BrowserStats: bStats, NetworkStats: nStats, DataStats: dStats, AccountStats: aStats}
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
	NetworkProfiles                           []networkProfileRow
	NetworkSelection                          string
	NetworkSelectionAvailable                 bool
	LegacyMigration                           *profile.LegacyMigrationSummary
	DisplayPreference                         string
	UIScalingPercent                          int
	UIScalingSupported                        bool
	ResolutionMode                            string
	BrowserTemplateID                         string
	EnvironmentArtifactID                     string
	DisplayTemplateID                         string
	TemplateHistory                           []templateHistoryRow
}

type templateHistoryRow struct {
	ProfileRevision       int
	BrowserTemplateID     string
	EnvironmentArtifactID string
	DisplayTemplateID     string
}

type templateChoice struct {
	ID, Label string
}

func hasTemplateChoice(choices []templateChoice, current string) bool {
	for _, choice := range choices {
		if choice.ID == current && current != "" {
			return true
		}
	}
	return false
}

func templateChoices(items []profile.CompatibleTemplateSummary) (browsers, fingerprints, displays []templateChoice) {
	seenBrowsers, seenFingerprints, seenDisplays := map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, item := range items {
		if !seenBrowsers[item.BrowserTemplateID] {
			browsers = append(browsers, templateChoice{item.BrowserTemplateID, item.BrowserLabel + " · " + item.Engine + " " + item.BrowserVersion})
			seenBrowsers[item.BrowserTemplateID] = true
		}
		if !seenFingerprints[item.EnvironmentArtifactID] {
			label := item.EnvironmentLabel
			if label == "" {
				label = item.EnvironmentArtifactID
			}
			fingerprints = append(fingerprints, templateChoice{item.EnvironmentArtifactID, label + " · " + item.Engine + " " + item.BrowserVersion + " · " + item.Locale + " / " + item.Timezone})
			seenFingerprints[item.EnvironmentArtifactID] = true
		}
		if !seenDisplays[item.DisplayTemplateID] {
			displays = append(displays, templateChoice{item.DisplayTemplateID, item.DisplayLabel + " · " + item.Screen})
			seenDisplays[item.DisplayTemplateID] = true
		}
	}
	return browsers, fingerprints, displays
}

func stringSliceContains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

type accountRow struct {
	ID, Role    string
	Disabled    bool
	Profiles    string
	Grants      map[string]bool
	AllProfiles []string
}

type networkProfileRow struct {
	profile.NetworkProfileRevisionSummary
	Endpoint   string
	AcceptedAt string
	ProbeAt    string
	CreatedAt  string
}

func networkProfileRows(items []profile.NetworkProfileRevisionSummary) []networkProfileRow {
	rows := make([]networkProfileRow, 0, len(items))
	for _, item := range items {
		row := networkProfileRow{NetworkProfileRevisionSummary: item, Endpoint: redactNetworkEndpoint(item.Host, item.Port)}
		if !item.CreatedAt.IsZero() {
			row.CreatedAt = item.CreatedAt.UTC().Format(time.RFC3339)
		}
		if item.AcceptedAt != nil {
			row.AcceptedAt = item.AcceptedAt.UTC().Format(time.RFC3339)
		}
		if item.ProbeAt != nil {
			row.ProbeAt = item.ProbeAt.UTC().Format(time.RFC3339)
		}
		rows = append(rows, row)
	}
	return rows
}

func redactNetworkEndpoint(host string, port int) string {
	host = strings.TrimSpace(host)
	masked := "—"
	if host != "" {
		parts := strings.Split(host, ".")
		numeric := len(parts) == 4
		for _, part := range parts {
			if part == "" {
				numeric = false
				break
			}
			for _, r := range part {
				if r < '0' || r > '9' {
					numeric = false
					break
				}
			}
		}
		switch {
		case numeric:
			masked = parts[0] + "." + parts[1] + ".x.x"
		case strings.Contains(host, ":"):
			prefix := host
			if len(prefix) > 6 {
				prefix = prefix[:6]
			}
			masked = prefix + "…"
		case len(parts) >= 3:
			prefix := parts[0]
			if len(prefix) > 1 {
				prefix = prefix[:1]
			}
			masked = prefix + "…." + strings.Join(parts[len(parts)-2:], ".")
		case len(host) > 2:
			masked = host[:1] + "…" + host[len(host)-1:]
		default:
			masked = "••"
		}
	}
	if port > 0 {
		return masked + ":" + strconv.Itoa(port)
	}
	return masked
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
	row.NetworkSelection = browserNetworkSelection(summary.ConfiguredNetworkMode, "", 0)
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

// writeReauthJSON gives enhanced forms an explicit retryable authentication
// outcome. Other 403 responses must never trigger an operation retry.
func writeReauthJSON(writer http.ResponseWriter, request *http.Request) bool {
	if request.Header.Get("Accept") != "application/json" {
		return false
	}
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(http.StatusForbidden)
	_ = json.NewEncoder(writer).Encode(map[string]any{"done": false, "reauth": true, "message": notices["reauth"]})
	return true
}

func (s *Server) redirectManage(writer http.ResponseWriter, request *http.Request, notice string) {
	if notice == "reauth" && writeReauthJSON(writer, request) {
		return
	}

	tab := ""
	switch {
	case strings.HasPrefix(request.URL.Path, "/manage/environment-jobs"), strings.HasPrefix(request.URL.Path, "/manage/template-combinations"):
		tab = "fingerprint-data&section=combinations"
	case strings.HasPrefix(request.URL.Path, "/manage/fingerprint-templates"):
		tab = "fingerprint-data&section=fingerprints"
	case strings.HasPrefix(request.URL.Path, "/manage/display-templates"):
		tab = "fingerprint-data&section=displays"
	case strings.HasPrefix(request.URL.Path, "/manage/network-profiles"):
		tab = "network"
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
	}
	capabilities := managementCapabilities(s.profiles)
	selection, selected := s.resolveCreateTemplate(request.Context(), request.PostForm)
	if !selected {
		s.redirectManage(writer, request, "create_template")
		return
	}
	requestData.BrowserTemplateID = selection.BrowserTemplateID
	requestData.EnvironmentArtifactID = selection.EnvironmentArtifactID
	requestData.DisplayTemplateID = selection.DisplayTemplateID

	if capabilities.ManagedDirect || capabilities.NetworkProfiles {
		if request.PostForm.Get("network_policy_id") != "" || request.PostForm.Get("network_policy_sha256") != "" {
			s.redirectManage(writer, request, "invalid")
			return
		}
		network := strings.Split(request.PostForm.Get("network_selection"), "|")
		switch {
		case len(network) == 1 && network[0] == "direct" && capabilities.ManagedDirect:
			requestData.NetworkMode = "direct"
		case len(network) == 3 && network[0] == "proxy" && capabilities.NetworkProfiles:
			revision, err := strconv.Atoi(network[2])
			if err != nil || revision < 1 || network[1] == "" {
				s.redirectManage(writer, request, "invalid")
				return
			}
			requestData.NetworkMode, requestData.NetworkProfileID, requestData.NetworkProfileRevision = "proxy_required", network[1], revision
		default:
			s.redirectManage(writer, request, "invalid")
			return
		}
	} else {
		requestData.NetworkMode = strings.TrimSpace(request.PostForm.Get("network_mode"))
		requestData.NetworkPolicyID = strings.TrimSpace(request.PostForm.Get("network_policy_id"))
		requestData.NetworkPolicySHA256 = strings.TrimSpace(request.PostForm.Get("network_policy_sha256"))
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	record, err := manager.CreateBrowser(ctx, requestData, access.Subject(request), requestID)
	if err != nil {
		s.logger.Warn("management action", "action", "browser_create", "status", "rejected", "error", err)
		notice := "unavailable"
		if errors.Is(err, profile.ErrTemplateCatalogUnavailable) {
			notice = "create_template"
		}
		s.redirectManage(writer, request, notice)
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
	case "legacy_network_migrate", "legacy_network_rollback":
		if !hasCapability(grant, "manage") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		s.manageLegacyMigration(writer, request, id, actor)
		return
	case "network_select":
		if !hasCapability(grant, "manage") {
			http.Error(writer, "Forbidden", http.StatusForbidden)
			return
		}
		s.manageNetworkSelection(writer, request, id, actor)
		return
	case "network_direct_managed":
		if !managementCapabilities(s.profiles).ManagedDirect {
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
			if values := request.PostForm["ui_scaling_percent"]; len(values) > 0 {
				if len(values) != 1 {
					s.redirectManage(writer, request, "invalid")
					return
				}
				percent, err := strconv.Atoi(values[0])
				if err != nil || (percent != 0 && (percent < 100 || percent > 300 || percent%25 != 0)) {
					s.redirectManage(writer, request, "invalid")
					return
				}
				patch.UIScalingPercent = &percent
			}
			if len(request.PostForm["display_preference"]) > 1 {
				s.redirectManage(writer, request, "invalid")
				return
			}
			if len(request.PostForm["display_preference"]) == 1 {
				preference := request.PostForm.Get("display_preference")
				if preference != "" && preference != "contain" && preference != "fill" {
					s.redirectManage(writer, request, "invalid")
					return
				}
				patch.DisplayPreference = &preference
			}
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
	// The deployed generator is pinned to the accepted Camoufox 152 family.
	// Do not silently reinterpret a request for another engine or version.
	if (request.PostForm.Has("browser_engine") && (len(request.PostForm["browser_engine"]) != 1 || request.PostForm.Get("browser_engine") != "camoufox")) || (request.PostForm.Has("browser_version") && (len(request.PostForm["browser_version"]) != 1 || request.PostForm.Get("browser_version") != "152.0")) {
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
	action := request.PostForm.Get("action")
	if action == "network_direct_managed" {
		if s.access != nil && !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		service, ok := s.profiles.(managedDirectService)
		if !ok {
			s.redirectManage(writer, request, "unavailable")
			return
		}
		revision, revisionOK := parseRevision(request.PostForm.Get("revision"))
		key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
		if !revisionOK || key == "" || len(key) > 128 {
			s.redirectManage(writer, request, "invalid")
			return
		}
		ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
		defer cancel()
		_, err := service.SetBrowserManagedDirect(ctx, id, revision, actor, key)
		switch {
		case err == nil:
			s.logger.Info("management action", "profile", id, "action", action, "status", "network_applied")
			s.redirectManage(writer, request, "network_applied")
		case errors.Is(err, profile.ErrProfileNotFound):
			http.NotFound(writer, request)
		case errors.Is(err, profile.ErrManagedPolicyRequired):
			s.redirectManage(writer, request, "invalid")
		case errors.Is(err, profile.ErrRevisionMismatch):
			s.redirectManage(writer, request, "revision")
		case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrStopUnconfirmed), errors.Is(err, profile.ErrOwnershipUnknown):
			s.redirectManage(writer, request, "network_busy")
		default:
			s.logger.Warn("management action", "profile", id, "action", action, "status", "rejected", "error", err)
			s.redirectManage(writer, request, "unavailable")
		}
		return
	}
	drafts, ok := s.profiles.(proxyDraftService)
	if !ok {
		s.redirectManage(writer, request, "unavailable")
		return
	}
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

func (s *Server) manageLegacyMigration(writer http.ResponseWriter, request *http.Request, id, actor string) {
	if s.access != nil && !s.access.Reauthenticated(request) {
		s.redirectManage(writer, request, "reauth")
		return
	}
	service, ok := s.profiles.(legacyMigrationService)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	revision, valid := parseRevision(request.PostForm.Get("revision"))
	key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
	if !valid || key == "" || len(key) > 128 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	action := request.PostForm.Get("action")
	var err error
	if action == "legacy_network_rollback" {
		_, err = service.RollbackLegacyNetwork(ctx, id, revision, request.PostForm.Get("migration_id"), actor, key)
	} else {
		_, err = service.MigrateLegacyNetwork(ctx, id, revision, request.PostForm.Get("migration_id"), actor, key)
	}
	switch {
	case err == nil:
		s.logger.Info("management action", "profile", id, "action", action, "status", "network_applied")
		s.redirectManage(writer, request, "network_applied")
	case errors.Is(err, profile.ErrBrowserBusy), errors.Is(err, profile.ErrOwnershipUnknown), errors.Is(err, profile.ErrStopUnconfirmed):
		s.redirectManage(writer, request, "network_busy")
	case errors.Is(err, profile.ErrRevisionMismatch), errors.Is(err, profile.ErrLegacyMigration):
		s.redirectManage(writer, request, "revision")
	default:
		s.logger.Warn("management action", "profile", id, "action", "legacy_network_migrate", "status", "rejected")
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
	notice := "account_updated"
	sensitive := id != actor
	var err error
	switch request.PostForm.Get("action") {
	case "delete":
		if !s.access.Reauthenticated(request) {
			s.redirectManage(writer, request, "reauth")
			return
		}
		if !confirmedDelete(request) {
			s.redirectManage(writer, request, "invalid")
			return
		}
		if id == actor {
			s.redirectManage(writer, request, "account_self_delete")
			return
		}
		err = store.Delete(id)
		notice = "account_deleted"
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
		if reloadErr := s.access.Reload(); reloadErr != nil {
			s.redirectManage(writer, request, "unavailable")
			return
		}
		s.logger.Info("management action", "action", "account_update", "status", "updated")
		s.redirectManage(writer, request, notice)
	case errors.Is(err, access.ErrLastAdmin):
		s.redirectManage(writer, request, "last_admin")
	case errors.Is(err, access.ErrAccountNotFound):
		http.NotFound(writer, request)
	default:
		s.redirectManage(writer, request, "invalid")
	}
}

var manageTemplate = template.Must(template.New("manage").Funcs(template.FuncMap{"hasTemplateChoice": hasTemplateChoice}).Parse(strings.TrimSpace(`
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>远程浏览器管理</title>
  <style>
    :root {
      --bg-page: #f4f6f8;
      --bg-card: #ffffff;
      --bg-subtle: #f8fafc;
      --bg-input: #f1f5f9;
      --border-color: #e2e8f0;
      --border-subtle: #f1f5f9;
      --border-focus: #2563eb;
      --text-primary: #0f172a;
      --text-secondary: #64748b;
      --color-primary: #2563eb;
      --color-primary-hover: #1d4ed8;
      --color-success: #10b981;
      --color-success-bg: #ecfdf5;
      --color-warning: #f59e0b;
      --color-warning-bg: #fffbeb;
      --color-warning-border: #fde68a;
      --color-danger: #ef4444;
      --color-danger-bg: #fef2f2;
      --color-danger-border: #fecaca;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
      --radius-xl: 18px;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-card: 0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      --shadow-modal: 0 25px 50px -12px rgba(15, 23, 42, 0.25);
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 0;
      background: var(--bg-page);
      color: var(--text-primary);
      min-height: 100vh;
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

    /* Layout */
    .app-layout { display: flex; min-height: 100vh; }
    .app-sidebar {
      width: 230px;
      background: #ffffff;
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
      min-height: 100vh;
      padding: 1.25rem 1rem;
    }
    .sidebar-header {
      padding: 0.25rem 0.5rem 1.25rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .sidebar-brand { display: flex; align-items: center; gap: 0.75rem; }
    .brand-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 38px;
      height: 38px;
      border-radius: 10px;
      background: #0f172a;
      color: #fff;
    }
    .brand-title { font-size: 1.05rem; font-weight: 700; line-height: 1.2; }
    .brand-badge {
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 500;
      color: var(--text-secondary);
      background: var(--bg-subtle);
      padding: 0.1rem 0.4rem;
      border-radius: 4px;
      margin-top: 0.2rem;
    }
    .sidebar-collapse-btn {
      display: none;
      cursor: pointer;
      padding: .35rem;
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
      border: none;
      background: transparent;
    }
    .sidebar-collapse-btn:hover { background: var(--bg-subtle); color: var(--text-primary); }

    .nav-tabs {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
      margin: 1.25rem 0;
      flex: 1;
    }
    .nav-link, .tab-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.65rem 0.85rem;
      font-size: 0.92rem;
      font-weight: 500;
      color: var(--text-secondary);
      border-radius: var(--radius-md);
      transition: all 0.15s ease;
      white-space: nowrap;
      text-decoration: none;
    }
    .nav-link:hover, .tab-item:hover {
      color: var(--text-primary);
      text-decoration: none;
      background: var(--bg-subtle);
    }
    .nav-link.active, .tab-item.active {
      color: var(--color-primary);
      font-weight: 600;
      background: #eff6ff;
    }
    .nav-link svg, .tab-item svg { flex-shrink: 0; }

    /* Expandable Menu */
    .nav-group { margin: 0; }
    .nav-group-summary {
      cursor: pointer;
      list-style: none;
      user-select: none;
      display: flex;
      align-items: center;
      gap: .75rem;
      padding: .65rem .85rem;
      border-radius: var(--radius-md);
      font-size: .92rem;
      font-weight: 500;
      color: var(--text-secondary);
      transition: all .15s ease;
    }
    .nav-group-summary::-webkit-details-marker { display: none; }
    .nav-group-summary:hover { background: var(--bg-subtle); color: var(--text-primary); }
    .nav-group-summary .chevron { margin-left: auto; transition: transform .2s ease; }
    .nav-group[open] .nav-group-summary .chevron { transform: rotate(180deg); }
    .nav-sub {
      display: flex;
      flex-direction: column;
      gap: .25rem;
      padding-left: .85rem;
      margin: .25rem 0 .5rem;
      border-left: 2px solid var(--border-color);
      margin-left: 1.5rem;
    }
    .nav-sub .tab-item {
      padding: .5rem .75rem;
      font-size: .85rem;
    }

    /* Sidebar Toggle Mechanics */
    .sidebar-toggle-check {
      position: absolute;
      width: 1px;
      height: 1px;
      margin: -1px;
      padding: 0;
      overflow: hidden;
      clip: rect(0,0,0,0);
      border: 0;
    }
    .sidebar-backdrop { display: none; }
    .topbar-left { display: flex; align-items: center; gap: .85rem; }
    .sidebar-toggle-btn { cursor: pointer; user-select: none; }
    .sidebar-toggle-check:focus-visible ~ .app-layout .sidebar-toggle-btn,
    .sidebar-toggle-btn:focus-visible, .sidebar-collapse-btn:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }

    .sidebar-footer {
      margin-top: auto;
      padding-top: 1rem;
      border-top: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .online-indicator {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 0.82rem;
      font-weight: 500;
      color: var(--color-success);
    }
    .online-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-success); }
    .sidebar-shortcuts {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      flex-wrap: wrap;
    }
    .sidebar-icon-btn, .sidebar-shortcuts a.header-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-color);
      background: #fff;
      color: var(--text-secondary);
      cursor: pointer;
      padding: 0;
      font-size: 0.8rem;
    }
    .sidebar-icon-btn:hover, .sidebar-shortcuts a.header-link:hover {
      background: var(--bg-subtle);
      color: var(--text-primary);
      text-decoration: none;
    }

    .app-main-wrapper {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      padding: 1.5rem 2rem;
    }

    .app-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.5rem;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-color);
    }
    .header-main { flex: 1; min-width: 0; }
    .app-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.35rem; letter-spacing: -0.01em; }
    .header-meta { margin: 0; }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }
    .header-link {
      font-size: 0.85rem;
      font-weight: 500;
      padding: 0.4rem 0.75rem;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      background: #fff;
      color: var(--text-primary);
    }
    .header-link:hover { background: var(--bg-subtle); text-decoration: none; }
    .logout-form { display: inline; margin: 0; }

    .notice {
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      padding: 0.75rem 1rem;
      border-radius: var(--radius-md);
      margin-bottom: 1.5rem;
      font-weight: 500;
    }

    /* Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .stat-card {
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 1.1rem 1.25rem;
      box-shadow: var(--shadow-card);
    }
    .stat-card-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }
    .stat-badge-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 8px;
      flex-shrink: 0;
    }
    .stat-card-val {
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--text-primary);
      margin: 0.35rem 0 0.2rem;
      line-height: 1.2;
    }
    .stat-card-desc {
      font-size: 0.78rem;
      color: var(--text-secondary);
    }

    /* Toolbar */
    .action-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
    }
    .search-box {
      position: relative;
      display: flex;
      align-items: center;
      flex: 1;
      max-width: 24rem;
      min-width: 16rem;
    }
    .search-box svg {
      position: absolute;
      left: 0.85rem;
      color: var(--text-secondary);
      pointer-events: none;
    }
    [hidden] { display: none !important; }
    .filter-status { margin-bottom: 1rem; }
    .row-action { margin: .25rem 0; }
    .row-action > summary { cursor: pointer; color: var(--color-primary); padding: .35rem 0; }
    .row-action form { margin-top: .5rem; max-width: 24rem; }
    .search-input {
      font: inherit;
      font-size: 0.88rem;
      width: 100%;
      padding: 0.6rem 0.85rem 0.6rem 2.4rem;
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      color: var(--text-primary);
    }
    .search-input:focus {
      outline: none;
      border-color: var(--border-focus);
      box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    }
    .toolbar-actions { display: flex; gap: 0.6rem; align-items: center; }

    /* Progressive Dialog / Modal */
    dialog.progressive-modal {
      display: block;
      position: static;
      width: 100%;
      max-width: 100%;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      background: #fff;
      padding: 1.5rem;
      box-sizing: border-box;
      margin-bottom: 1.5rem;
    }
    dialog.progressive-modal.dialog-ready {
      display: none;
      position: fixed;
      inset: 0;
      margin: auto;
      max-width: 620px;
      max-height: 90vh;
      overflow-y: auto;
      border-radius: var(--radius-xl);
      border: 1px solid rgba(226, 232, 240, 0.9);
      box-shadow: var(--shadow-modal);
      z-index: 1000;
      padding: 1.75rem;
    }
    dialog.progressive-modal.dialog-ready[open] {
      display: block;
    }
    dialog.progressive-modal.dialog-ready::backdrop {
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(3px);
    }
    .dialog-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.25rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border-color);
    }
    .dialog-title { font-size: 1.15rem; font-weight: 700; margin: 0 0 0.2rem; }
    .dialog-close-btn {
      background: transparent;
      border: none;
      font-size: 1.4rem;
      line-height: 1;
      color: var(--text-secondary);
      cursor: pointer;
      padding: 0.2rem;
      border-radius: 4px;
    }
    .dialog-close-btn:hover { color: var(--text-primary); }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.75rem;
      margin-top: 1.25rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border-color);
    }

    .trigger-modal-btn { display: none; }
    dialog.progressive-modal:not(.dialog-ready) .dialog-close-btn,
    dialog.progressive-modal:not(.dialog-ready) .dialog-cancel-btn {
      display: none;
    }

    /* Panels */
    .panel {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-card);
      padding: 1.25rem;
      margin-bottom: 1.25rem;
    }
    .panel-header { margin-bottom: 1rem; }
    .panel-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.25rem; }
    .callout-panel { background: #fffbeb; border-color: #fde68a; }

    /* Browser Cards */
    .browser-card-list { display: flex; flex-direction: column; gap: 1.25rem; }
    .browser-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-card);
      padding: 1.35rem;
      transition: box-shadow 0.15s ease;
    }
    .browser-card:hover { box-shadow: var(--shadow-md); }
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
    .card-title { font-size: 1.2rem; font-weight: 700; }
    .card-profile-id { font-size: 0.85rem; }
    .card-badges { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.78rem;
      font-weight: 500;
      padding: 0.2rem 0.55rem;
      border-radius: 9999px;
      line-height: 1.3;
    }
    .badge-count { background: #f1f5f9; color: var(--text-secondary); font-size: 0.8rem; }
    .badge-success { background: var(--color-success-bg); color: var(--color-success); border: 1px solid #a7f3d0; }
    .badge-disabled { background: #f1f5f9; color: var(--text-secondary); }
    .badge-status { background: #eff6ff; color: var(--color-primary); border: 1px solid #bfdbfe; }
    .badge-stale { background: var(--color-danger-bg); color: var(--color-danger); border: 1px solid #fecaca; }
    .badge-role { background: #f1f5f9; color: var(--text-primary); }
    .badge-warning { background: var(--color-warning-bg); color: var(--color-warning); border: 1px solid var(--color-warning-border); }

    .card-entry {
      background: var(--bg-subtle);
      border-radius: var(--radius-md);
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      font-size: 0.88rem;
    }
    .entry-line { display: flex; align-items: baseline; gap: 0.4rem; word-break: break-all; }
    .entry-label { font-weight: 600; flex-shrink: 0; }
    .entry-url { color: var(--color-primary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break: break-all; font-weight: 500; }
    .entry-accounts { margin-top: 0.35rem; }

    .overview-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.85rem;
      background: var(--bg-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 1rem;
      margin-bottom: 1rem;
    }
    .overview-item { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; word-break: break-word; }
    .overview-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-secondary); }
    .overview-value { font-size: 0.88rem; }

    /* Forms */
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 0.85rem;
      margin-bottom: 0.85rem;
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
      gap: 0.3rem;
      flex: 1;
      min-width: 180px;
    }
    .form-field label, .field-label {
      font-size: 0.84rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    .delete-control { margin-top: 0.65rem; }
    .delete-control summary { color: var(--color-danger); cursor: pointer; font-size: 0.84rem; font-weight: 500; }
    .delete-form { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin-top: 0.5rem; }
    .form-field-action { flex-shrink: 0; }
    .field-help { font-size: 0.8rem; color: var(--text-secondary); margin: 0.25rem 0 0.5rem 0; }
    input[type=text], input[type=url], input[type=password], .fingerprint-function input[type=number], select, textarea {
      font: inherit;
      font-size: 0.9rem;
      padding: 0.5rem 0.75rem;
      min-height: 40px;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      background: #fff;
      color: var(--text-primary);
      width: 100%;
      box-sizing: border-box;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    input[type=text]:focus, input[type=url]:focus, input[type=password]:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--border-focus);
      box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    }
    textarea { min-height: 58px; resize: vertical; }
    fieldset {
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 0.75rem 1rem;
      margin: 0.65rem 0 0.85rem 0;
    }
    legend { font-size: 0.84rem; font-weight: 600; padding: 0 0.4rem; }
    .chk {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      margin-right: 0.9rem;
      margin-bottom: 0.4rem;
      font-size: 0.88rem;
      cursor: pointer;
    }
    .chk input { margin: 0; }
    .checkbox-group, .radio-group { display: flex; flex-wrap: wrap; align-items: center; }
    .form-actions { margin-top: 0.75rem; }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      font: inherit;
      font-size: 0.88rem;
      font-weight: 600;
      min-height: 38px;
      padding: 0.45rem 1rem;
      border-radius: var(--radius-md);
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
      box-sizing: border-box;
      white-space: nowrap;
      transition: all 0.15s ease;
    }
    .btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
    .btn-primary:hover { background: var(--color-primary-hover); }
    .btn-secondary { background: #fff; color: var(--text-primary); border-color: var(--border-color); }
    .btn-secondary:hover { background: var(--bg-subtle); }
    .btn-warning { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning-border); }
    .btn-warning:hover { background: #fef3c7; }
    .btn-danger { background: var(--color-danger-bg); color: var(--color-danger); border-color: var(--color-danger-border); }
    .btn-danger:hover { background: #fee2e2; }
    .btn-sm { min-height: 32px; padding: 0.25rem 0.65rem; font-size: 0.82rem; border-radius: var(--radius-sm); }

    .card-settings, .card-lifecycle {
      padding-top: 0.85rem;
      border-top: 1px solid var(--border-subtle);
      margin-bottom: 0.85rem;
    }
    .settings-title { font-size: 0.92rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-secondary); }
    .lifecycle-actions { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .network-details, .template-details {
      margin-top: 0.85rem;
      border-top: 1px solid var(--border-subtle);
      padding-top: 0.85rem;
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
      border-radius: var(--radius-md);
      border: 1px solid var(--border-color);
    }
    .sub-form-title { font-size: 0.88rem; font-weight: 600; margin: 0 0 0.5rem 0; }
    .draft-status-panel {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      padding: 0.6rem 0.85rem;
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      margin-bottom: 0.75rem;
    }
    .draft-form-wrapper, .direct-form-wrapper, .apply-draft-wrapper {
      margin-top: 0.75rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-color);
    }
    .danger-zone {
      margin-top: 1rem;
      padding: 0.9rem 1.1rem;
      border: 1px solid var(--color-danger-border);
      border-radius: var(--radius-md);
      background: #fffafa;
    }
    .danger-title { font-size: 0.92rem; font-weight: 600; color: var(--color-danger); margin-bottom: 0.25rem; }

    /* Table styles */
    .table-container {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      background: #fff;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow-card);
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }
    th, td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); vertical-align: top; }
    th { background: var(--bg-subtle); font-weight: 600; font-size: 0.82rem; color: var(--text-secondary); white-space: nowrap; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #fafafa; }
    .table-info-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.65rem 1rem;
      background: #fff;
      border-top: 1px solid var(--border-color);
      font-size: 0.82rem;
      color: var(--text-secondary);
    }

    .inline-input-group { display: flex; gap: 0.35rem; align-items: center; }
    .inline-input-group input { width: 13rem; }
    .account-btn-group { display: flex; gap: 0.35rem; margin-top: 0.35rem; flex-wrap: wrap; }
    .grants-checkboxes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.35rem; }

    /* Fingerprint Data Subnav */
    .data-nav { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 1rem 0 1.5rem; }
    .data-nav a {
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      padding: 0.65rem 1rem;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      background: #fff;
      color: var(--text-secondary);
      font-weight: 500;
    }
    .data-nav a:hover { background: var(--bg-subtle); color: var(--text-primary); text-decoration: none; }
    .data-nav a[aria-current="page"] {
      background: #eff6ff;
      border-color: var(--color-primary);
      color: var(--color-primary);
      font-weight: 600;
    }
    .data-nav-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.4rem;
      height: 1.4rem;
      border-radius: 50%;
      background: var(--bg-subtle);
      font-size: 0.78rem;
      color: var(--text-secondary);
    }
    .data-group-heading { margin: 1.5rem 0 0.85rem; font-size: 1.1rem; font-weight: 600; }
    .data-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: 1rem; }
    .data-card { min-width: 0; margin-bottom: 0; overflow-wrap: anywhere; }
    .data-card p { margin: 0.45rem 0; }
    .data-empty { color: var(--text-secondary); }
    .fingerprint-function { min-width: 0; }

    .app-footer {
      margin-top: auto;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-color);
      text-align: center;
    }

    /* Breakpoints */
    @media (max-width: 1099px) {
      .overview-grid { grid-template-columns: repeat(2, 1fr); }
      .stats-grid { grid-template-columns: repeat(2, 1fr); }
    }
    .template-combinations form { display: grid; gap: 0.5rem; }
    .template-combinations select { min-width: 0; width: 100%; }

    @media (min-width: 769px) {
      .app-sidebar { transition: margin-left .2s ease, width .2s ease, opacity .2s ease; }
      .sidebar-toggle-check:checked ~ .app-layout .app-sidebar {
        visibility: hidden;
        width: 0;
        padding-left: 0;
        padding-right: 0;
        overflow: hidden;
        opacity: 0;
        border-right: none;
        pointer-events: none;
      }
    }
    @media (max-width: 768px) {
      .app-layout { flex-direction: column; }
      .app-sidebar {
        position: fixed;
        top: 0;
        bottom: 0;
        left: 0;
        width: 260px;
        height: 100vh;
        z-index: 1000;
        background: #fff;
        box-shadow: var(--shadow-modal);
        visibility: hidden; transform: translateX(-100%);
        transition: transform .25s ease;
        overflow-y: auto;
      }
      .sidebar-collapse-btn { display: inline-flex; align-items: center; justify-content: center; }
      .sidebar-toggle-check:checked ~ .sidebar-backdrop {
        display: block;
        position: fixed;
        inset: 0;
        background: rgba(15, 23, 42, 0.45);
        backdrop-filter: blur(2px);
        z-index: 999;
      }
      .sidebar-toggle-check:checked ~ .app-layout .app-sidebar { visibility: visible; transform: translateX(0); }
      .nav-tabs { flex-direction: column; overflow-x: visible; }
      .tab-item { border-radius: var(--radius-sm); }
      .app-main-wrapper { padding: 1rem; }
      .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .65rem; }
      .stat-card { padding: .8rem; }
      .stat-card-val { font-size: 1.5rem; }
      .stat-card-desc { font-size: .72rem; }
      .stat-badge-icon { display: none; }
      .sidebar-footer { display: flex; align-items: center; justify-content: space-between; margin-top: .5rem; padding-top: .5rem; }
      .sidebar-shortcuts { margin: 0; gap: .25rem; }
      .sidebar-brand { margin-bottom: .5rem; padding-bottom: .75rem; }
      .template-combinations table, .template-combinations tbody,
      .template-combinations tr, .template-combinations td { display: block; width: 100%; min-width: 0; box-sizing: border-box; }
      .template-combinations thead { display: none; }
      .template-combinations td { overflow-wrap: anywhere; }
      .template-combinations tr { border-bottom: 1px solid var(--border-color); }

      .app-header { flex-direction: column; align-items: stretch; gap: 1rem; }
      .header-actions { justify-content: flex-start; }
      .overview-grid { grid-template-columns: 1fr; }
      .form-row { flex-direction: column; align-items: stretch; }
      .form-field { width: 100%; min-width: unset; }
      .form-field-action { width: 100%; }
      .form-field-action button { width: 100%; }
    }
.table-container {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.management-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  font-size: 13px;
  line-height: 1.4;
}
.management-table th,
.management-table td {
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  word-break: break-word;
  overflow-wrap: anywhere;
}
.management-table th {
  background: var(--bg-subtle, #f9fafb);
  color: var(--text-secondary, #6b7280);
  font-weight: 600;
  white-space: nowrap;
}
details.record-details summary {
  cursor: pointer;
  color: var(--color-primary, #2563eb);
  user-select: none;
  font-weight: 500;
}
details.record-details summary:hover {
  text-decoration: underline;
}
dialog.record-dialog {
  width: min(960px, 92vw);
  max-height: 90vh;
  margin: auto;
  padding: 0;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
  background: #ffffff;
  overflow: hidden;
}
dialog.record-dialog[open] {
  display: flex;
  flex-direction: column;
}
dialog.record-dialog::backdrop {
  background: rgba(0, 0, 0, 0.45);
}
.record-dialog .dialog-header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--bg-subtle, #f9fafb);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  z-index: 10;
}
.record-dialog .dialog-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.record-dialog .dialog-close {
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  padding: 4px 8px;
  border-radius: 4px;
  color: var(--text-secondary, #6b7280);
}
.record-dialog .dialog-close:hover,
.record-dialog .dialog-close:focus-visible {
  color: #111827;
  background: var(--border-color, #e5e7eb);
  outline: 2px solid var(--color-primary);
}
.record-dialog .dialog-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.list-row-actions{display:flex;gap:.5rem;align-items:flex-start;white-space:nowrap}
.list-row-actions .btn{white-space:nowrap}
.record-dialog .browser-card{padding:0;border:0;box-shadow:none}
.record-dialog .record-content{min-width:0}
.list-create{margin:1rem 0}.list-create-content{padding-top:1rem}
.management-table td .badge{margin-bottom:.2rem}

.record-dialog.danger-dialog{max-width:560px}
.record-dialog .dialog-title{min-width:0;overflow-wrap:anywhere}
.record-dialog .dialog-close{flex-shrink:0}
.record-dialog .dialog-footer{display:flex;justify-content:flex-end;padding:12px 16px;border-top:1px solid var(--border-color);flex-shrink:0}
.record-dialog.danger-dialog .dialog-title{color:var(--color-danger)}
  ` + access.PasswordDialogCSS + access.ReauthDialogCSS + `.record-dialog .dialog-title,
.record-dialog .dialog-header :is(h1, h2, h3, h4) {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}
.record-dialog [role="tablist"],
.record-dialog .record-dialog-tablist {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid #e5e7eb;
  padding: 0 16px;
}
.record-dialog [role="tab"],
.record-dialog .record-dialog-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 12px;
  font-size: 14px;
  color: #4b5563;
  cursor: pointer;
}
.record-dialog [role="tab"][aria-selected="true"],
.record-dialog .record-dialog-tab[aria-selected="true"] {
  color: #2563eb;
  border-bottom-color: #2563eb;
  font-weight: 500;
}
.record-dialog [role="tab"]:focus-visible,
.record-dialog .record-dialog-tab:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: -2px;
}
.record-dialog [role="tabpanel"],
.record-dialog .record-dialog-panel {
  box-shadow: none;
  border: none;
  background: transparent;
  padding: 16px 0;
}
.record-dialog .dialog-body {
  padding: 0 16px 16px;
  overflow-y: auto;
}
.record-dialog .form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}
.record-dialog .form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.record-dialog :is(input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]), select, textarea) {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  color: #1f2937;
  background-color: #fff;
}
.record-dialog :is(input, select, textarea):focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}
.record-dialog .danger-alert,
.record-dialog .danger-notice,
.record-dialog [role="alert"].danger {
  color: #dc2626;
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  margin: 8px 0;
}
.record-dialog .dialog-cancel,
.record-dialog .btn-cancel,
.record-dialog [data-action="cancel"],
.record-dialog button.cancel {
  position: sticky;
  bottom: 0;
  background-color: #fff;
}
@media (max-width: 640px) {
  .record-dialog .form-grid {
    grid-template-columns: 1fr;
  }
}

.record-dialog .record-dialog-tablist{flex-shrink:0;overflow-x:auto;gap:2px}
.record-dialog .record-dialog-tab{white-space:nowrap;border-radius:0;min-height:44px}
.record-dialog [hidden]{display:none!important}
.record-dialog .record-dialog-panel>details{margin:0 0 16px;border:0;border-radius:0;background:transparent}
.record-dialog .record-dialog-panel>details>summary{display:none}
.record-dialog .record-dialog-panel>details>.details-content{padding:0}
.record-dialog .card-settings,.record-dialog .card-lifecycle,.record-dialog .danger-zone{margin:0;padding:16px 0;border:0;background:transparent}
.record-dialog .row-action form{max-width:none}
.record-dialog .overview-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.record-dialog input[type=hidden]{display:none}
.record-dialog .record-content{width:100%}
.record-dialog .record-dialog-panel{padding:16px 0}
.fingerprint-function .delete-dialog-trigger{white-space:nowrap}
@media(max-width:640px){.record-dialog .overview-grid{grid-template-columns:1fr}.record-dialog .dialog-body{padding:0 12px 12px}}


.record-dialog .form-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px}
.record-dialog .form-field{width:100%;min-width:0;align-items:stretch}
.record-dialog .form-field-action{grid-column:1/-1;justify-self:end}
.record-dialog .details-content{margin:0;border:0;background:transparent;border-radius:0}
.record-dialog .field-help{margin:0 0 16px}
.record-dialog .inline-input-group{display:flex;flex-wrap:wrap}
.record-dialog .inline-input-group input{flex:1;min-width:160px}
.record-dialog .row-action form>.btn{margin-top:12px}
.record-dialog .panel{box-shadow:none;border:0;margin:0;padding:0}
@media(max-width:640px){.record-dialog .form-row{grid-template-columns:1fr}}
</style>
</head>
<body>
<input type="checkbox" id="sidebar-toggle" class="sidebar-toggle-check sr-only" aria-label="收起或展开侧栏">
<label for="sidebar-toggle" class="sidebar-backdrop" aria-hidden="true"></label>
<div class="app-layout">
  <aside class="app-sidebar sidebar" id="sidebar" aria-label="工作区侧栏">
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <div class="brand-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
        </div>
        <div>
          <div class="brand-title">浏览器工作区</div>
          <div class="brand-badge">控制台中心</div>
        </div>
      </div>
      <label for="sidebar-toggle" class="sidebar-collapse-btn" role="button" tabindex="0" title="收起侧栏" aria-label="收起侧栏">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </label>
    </div>

    <nav class="nav-tabs sidebar-nav" aria-label="工作区导航">
      <a href="/" class="nav-link tab-item">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        <span>工作区概览</span>
      </a>
      <details class="nav-group" id="manage-menu" open>
        <summary class="nav-group-summary" >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
          <span>管理面板</span>
          <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </summary>
        <div class="nav-sub">
          <a href="/manage/?tab=browsers" class="tab-item{{if eq .ActiveTab "browsers"}} active{{end}}"{{if eq .ActiveTab "browsers"}} aria-current="page"{{end}}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            <span>浏览器</span>
          </a>
          {{if or .NetworkEnabled (eq .ActiveTab "network")}}
          <a href="/manage/?tab=network" class="tab-item{{if eq .ActiveTab "network"}} active{{end}}"{{if eq .ActiveTab "network"}} aria-current="page"{{end}}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            <span>网络代理</span>
          </a>
          {{end}}
          {{if or .JobsEnabled (eq .ActiveTab "fingerprint-data")}}
          <a href="/manage/?tab=fingerprint-data" class="tab-item{{if eq .ActiveTab "fingerprint-data"}} active{{end}}"{{if eq .ActiveTab "fingerprint-data"}} aria-current="page"{{end}}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 0-10 10c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.1-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/></svg>
            <span>指纹数据</span>
          </a>
          {{end}}
          <a href="/manage/?tab=accounts" class="tab-item{{if eq .ActiveTab "accounts"}} active{{end}}"{{if eq .ActiveTab "accounts"}} aria-current="page"{{end}}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>访问账号</span>
          </a>
        </div>
      </details>
      <a href="/auth/password" class="nav-link tab-item">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span>修改密码</span>
      </a>
    </nav>

    <div class="sidebar-footer">
      <div class="online-indicator"><span class="online-dot"></span>已登录</div>
      <div class="sidebar-shortcuts">
        <a href="/" class="header-link" title="返回首页"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></a>
        <a href="{{.ReauthURL}}" class="header-link" title="确认密码"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></a>
        <a href="/auth/password" class="header-link" title="修改我的密码"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></a>
        <a href="/manage/environments" class="header-link" title="JSON 概览"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg></a>
        <form method="post" action="/auth/logout" class="logout-form"><input type="hidden" name="csrf" value="{{.CSRF}}"><button type="submit" class="sidebar-icon-btn" title="退出登录"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></button></form>
      </div>
    </div>
  </aside>

  <div class="app-main-wrapper main-wrapper">
    <header class="app-header topbar">
      <div class="topbar-left">
        <label for="sidebar-toggle" class="sidebar-toggle-btn btn btn-secondary" role="button" tabindex="0" title="收起/展开侧栏" aria-label="收起/展开侧栏">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          <span class="sidebar-toggle-text">侧栏</span>
        </label>
        <div class="header-main">
          <h1 class="app-title">{{if eq .ActiveTab "browsers"}}远程浏览器{{else if eq .ActiveTab "network"}}网络代理{{else if eq .ActiveTab "fingerprint-data"}}指纹数据{{else if eq .ActiveTab "accounts"}}访问账号{{else}}远程浏览器管理{{end}}</h1>
          <p class="header-meta meta">管理员 {{.Subject}} · {{if eq .ActiveTab "network"}}管理代理配置和连接状态。{{else if eq .ActiveTab "fingerprint-data"}}保存模板，验收浏览器组合。{{else if eq .ActiveTab "accounts"}}管理账号和浏览器访问权限。{{else}}创建与维护独立浏览器。{{end}}</p>
        </div>
      </div>
    </header>

    <main class="app-main">
      {{if .Notice}}<div class="notice" role="status">{{.Notice}}{{if eq .Notice "该操作需要重新确认密码。"}} <a href="{{.ReauthURL}}">确认密码</a>，完成后请重新提交原操作。{{end}}</div>{{end}}

      {{if eq .ActiveTab "browsers"}}
      <section class="section-browsers" aria-labelledby="browsers-heading">
        <h2 id="browsers-heading" style="display:none">远程浏览器</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">总环境数</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg></span></div>
            <div class="stat-card-val">{{.BrowserStats.Total}}</div>
            <div class="stat-card-desc">已配置独立浏览器环境</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">运行中</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg></span></div>
            <div class="stat-card-val">{{.BrowserStats.Running}}</div>
            <div class="stat-card-desc">当前活跃运行进程</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">健康正常</span><span class="stat-badge-icon" style="background:var(--color-success-bg);color:var(--color-success)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span></div>
            <div class="stat-card-val">{{.BrowserStats.Healthy}}</div>
            <div class="stat-card-desc">健康采样正常</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">待处理 / 需关注</span><span class="stat-badge-icon" style="background:var(--color-warning-bg);color:var(--color-warning)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></span></div>
            <div class="stat-card-val">{{.BrowserStats.Issues}}</div>
            <div class="stat-card-desc">过期、阻塞或不可用</div>
          </div>
        </div>

        <div class="action-toolbar">
          <div class="search-box" hidden>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" placeholder="搜索当前浏览器列表..." aria-label="搜索浏览器">
          </div>
          <div class="toolbar-actions">
            {{if .CreateDelete}}
            <button type="button" class="btn btn-primary trigger-modal-btn" id="open-cb-dialog" aria-haspopup="dialog">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>新增浏览器</span>
            </button>
            {{end}}
          </div>
        </div>

        {{if .CreateDelete}}
        <dialog class="modal-dialog progressive-modal create-browser-panel" id="create-browser-dialog">
          <div class="dialog-header">
            <div>
              <h3 class="dialog-title">新增浏览器</h3>
              <p class="meta">选择引擎和已验收指纹，创建独立浏览器。</p>
            </div>
            <button type="button" class="dialog-close-btn" aria-label="关闭">&times;</button>
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
                <label for="cb-browser-template">引擎</label>
                <select name="browser_template_id" id="cb-browser-template" required{{if not .CreateTemplateCombinations}} disabled{{end}}>
                  {{range .CreateBrowserChoices}}<option value="{{.ID}}">{{.Label}}</option>{{else}}<option value="">暂无可用引擎</option>{{end}}
                </select>
              </div>
              <div class="form-field">
                <label for="cb-fingerprint-template">指纹</label>
                <select name="environment_artifact_id" id="cb-fingerprint-template" required disabled aria-describedby="cb-template-info">
                  <option value="">{{if .CreateTemplateCombinations}}请选择引擎下的已验收指纹{{else}}暂无已验收的指纹组合{{end}}</option>
                </select>
                <template id="cb-fingerprint-options">{{range .CreateFingerprintChoices}}<option value="{{.ID}}" data-browser="{{.BrowserID}}" data-display="{{.Display}}">{{.Label}}</option>{{end}}</template>
                <span id="cb-template-info" class="meta" role="status">{{if .CreateTemplateCombinations}}指纹已包含显示配置，选择后自动应用。{{else}}请先到“指纹数据 → 组合验收”生成并验收组合。{{end}}</span>
                <noscript><span class="meta">请启用浏览器脚本后选择引擎和指纹。</span></noscript>
              </div>
              {{if or .ManagedDirect .NetworkEnabled}}
              <div class="form-field">
                <label for="cb-network-selection">网络</label>
                {{if or .ManagedDirect .CreateNetworkProfiles}}<select id="cb-network-selection" name="network_selection" required>
                  {{if .ManagedDirect}}<option value="direct">无代理（受管理 DIRECT）</option>{{end}}
                  {{range .CreateNetworkProfiles}}<option value="proxy|{{.ID}}|{{.Revision}}">{{.Label}} · r{{.Revision}} · {{.Protocol}} · {{.Endpoint}}</option>{{end}}
                </select>{{else}}<span class="meta">当前没有可供新浏览器使用的受管理网络配置。</span>{{end}}
                <span class="meta">可直接使用已保存的代理，无需再次填写账号密码。</span>
              </div>
              {{else}}
              <div class="form-field">
                <label for="cb-network-mode">网络模式</label>
                <select id="cb-network-mode" name="network_mode"><option value="direct">受管理 DIRECT</option><option value="proxy_required">现有代理策略</option></select>
              </div>
              <div class="form-field"><label for="cb-network-policy-id">策略 ID</label><input id="cb-network-policy-id" type="text" name="network_policy_id" maxlength="128" required></div>
              <div class="form-field"><label for="cb-network-policy-sha">策略 SHA-256</label><input id="cb-network-policy-sha" type="text" name="network_policy_sha256" maxlength="64" required></div>
              {{end}}
              <div class="form-field">
                <label for="cb-idempotency-key">幂等键</label>
                <input id="cb-idempotency-key" type="text" name="idempotency_key" maxlength="128" placeholder="幂等键" required>
              </div>
            </div>
            <fieldset class="form-field accounts-fieldset">
              <legend class="field-label">分配可登录账号</legend>
              <div class="checkbox-group">{{range .Accounts}}<label class="chk"><input type="checkbox" name="accounts" value="{{.ID}}"> {{.ID}}</label>{{end}}</div>
            </fieldset>
            <div class="dialog-actions">
              <button type="button" class="btn btn-secondary dialog-cancel-btn">取消</button>
              <button id="cb-submit" type="submit" class="btn btn-primary" data-network-ready="{{if and (or .ManagedDirect .NetworkEnabled) (not .ManagedDirect) (not .CreateNetworkProfiles)}}false{{else}}true{{end}}" disabled>新增浏览器</button>
            </div>
          </form>
        </dialog>
        {{else}}
        <div class="panel callout-panel">
          <p class="meta">新增与归档删除尚未启用；现有浏览器仍可修改、停用或安全关闭。</p>
        </div>
        {{end}}

        {{if .Rows}}
        <div class="table-container"><table class="management-table browser-management-table">
          <thead><tr><th>名称</th><th>状态</th><th>网络</th><th>操作</th></tr></thead><tbody>
          {{range .Rows}}<tr>
            <td><strong>{{.Label}}</strong>{{if ne .Label .ProfileID}}<div class="meta">{{.ProfileID}}</div>{{end}}</td>
            <td>{{if .Available}}{{if .Enabled}}<span class="badge badge-success">已启用</span>{{else}}<span class="badge badge-disabled">已停用</span>{{end}} <span class="badge badge-status">{{.Status}}</span>{{if .Stale}} <span class="badge badge-stale">健康已过期</span>{{end}}{{else}}<span class="badge badge-warning">摘要暂不可用</span>{{end}}</td>
            <td>{{if .Available}}{{.Network}}{{else}}—{{end}}</td>
            <td><div class="list-row-actions"><a class="btn btn-primary btn-sm" href="{{.EntryPath}}">打开浏览器</a>
              <details class="record-details" data-title="{{.Label}} · 浏览器管理"><summary class="btn btn-secondary btn-sm">详情 / 管理</summary><div class="record-content">
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
                  <div class="form-field">
                    <label for="display-preference-{{.ProfileID}}">显示偏好</label>
                    {{if eq .ResolutionMode "auto"}}<span class="meta">自动分辨率：远程桌面与网页可见屏幕尺寸随客户端窗口变化，DPR 按所选指纹模板生效（固定 1 或跟随 UI Scaling）。模式跟随此远程浏览器保存；切换固定分辨率需停止后应用相应环境模板。</span>
                    {{else if .BrowserTemplateID}}<select id="display-preference-{{.ProfileID}}" name="display_preference"><option value=""{{if eq .DisplayPreference ""}} selected{{end}}>沿用当前显示方式</option><option value="contain"{{if eq .DisplayPreference "contain"}} selected{{end}}>保持比例（完整画面，可能留边）</option><option value="fill"{{if eq .DisplayPreference "fill"}} selected{{end}}>铺满窗口（可能拉伸）</option></select>
                    <span class="meta">跟随此远程浏览器保存，所有客户端共用。保存后刷新远程显示页生效；不改变指纹屏幕尺寸或 DPR。</span>
                    {{else if .UIScalingSupported}}<span class="meta">旧版 Work 自动分辨率随窗口变化，可保存下方界面缩放比例。</span>{{else}}<span class="meta">当前显示未登记可调整的缩放设置。</span>{{end}}
                    {{if .UIScalingSupported}}<label for="ui-scaling-{{.ProfileID}}">界面缩放</label><select id="ui-scaling-{{.ProfileID}}" name="ui_scaling_percent"><option value="0"{{if eq .UIScalingPercent 0}} selected{{end}}>跟随客户端默认</option><option value="100"{{if eq .UIScalingPercent 100}} selected{{end}}>100%</option><option value="125"{{if eq .UIScalingPercent 125}} selected{{end}}>125%</option><option value="150"{{if eq .UIScalingPercent 150}} selected{{end}}>150%</option><option value="175"{{if eq .UIScalingPercent 175}} selected{{end}}>175%</option><option value="200"{{if eq .UIScalingPercent 200}} selected{{end}}>200%</option><option value="225"{{if eq .UIScalingPercent 225}} selected{{end}}>225%</option><option value="250"{{if eq .UIScalingPercent 250}} selected{{end}}>250%</option><option value="275"{{if eq .UIScalingPercent 275}} selected{{end}}>275%</option><option value="300"{{if eq .UIScalingPercent 300}} selected{{end}}>300%</option></select><span class="meta">保存到此浏览器，刷新远程画面后生效。远程画面的 UI Scaling 也会自动保存。</span>{{end}}
                  </div>
                  <div class="form-field-action">
                    <button type="submit" class="btn btn-secondary">保存设置</button>
                  </div>
                </div>
              </form>
            </div>
            {{end}}

            {{if and .Manage $.TemplateCombinations}}
            <details class="template-details">
              {{$row := .}}
              <summary class="details-summary">浏览器 / 指纹 / 显示模板（停止后应用）</summary>
              <div class="details-content">
                <p class="field-help meta">当前：{{if .BrowserTemplateID}}{{.BrowserTemplateID}}{{else}}legacy / 未登记{{end}} · {{if .EnvironmentArtifactID}}{{.EnvironmentArtifactID}}{{else}}未登记指纹{{end}} · {{if .DisplayTemplateID}}{{.DisplayTemplateID}}{{else}}未登记显示{{end}}。关键模板切换不会隐式停止浏览器。</p>
                <form method="post" action="/manage/browsers/{{.ProfileID}}/template" class="template-apply-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="return_to" value="browsers">
                  <input type="hidden" name="action" value="apply">
                  <input type="hidden" name="browser_revision" value="{{.Revision}}">
                  <div class="form-grid">
                    <div class="form-field">
                      <label for="browser-template-{{.ProfileID}}">引擎 / 版本（指纹绑定）</label><select id="browser-template-{{.ProfileID}}" name="browser_template_id" required>{{if not (hasTemplateChoice $.ApplyBrowserChoices $row.BrowserTemplateID)}}<option value="" selected disabled>当前绑定未登记或已不可选，请明确选择</option>{{end}}{{range $.ApplyBrowserChoices}}<option value="{{.ID}}"{{if eq .ID $row.BrowserTemplateID}} selected{{end}}>{{.Label}}</option>{{end}}</select>
                      <label for="fingerprint-template-{{.ProfileID}}">指纹模板</label><select id="fingerprint-template-{{.ProfileID}}" name="environment_artifact_id" required>{{if not (hasTemplateChoice $.ApplyFingerprintChoices $row.EnvironmentArtifactID)}}<option value="" selected disabled>当前绑定未登记或已不可选，请明确选择</option>{{end}}{{range $.ApplyFingerprintChoices}}<option value="{{.ID}}"{{if eq .ID $row.EnvironmentArtifactID}} selected{{end}}>{{.Label}}</option>{{end}}</select>
                      <label for="display-template-{{.ProfileID}}">显示模板</label><select id="display-template-{{.ProfileID}}" name="display_template_id" required>{{if not (hasTemplateChoice $.ApplyDisplayChoices $row.DisplayTemplateID)}}<option value="" selected disabled>当前绑定未登记或已不可选，请明确选择</option>{{end}}{{range $.ApplyDisplayChoices}}<option value="{{.ID}}"{{if eq .ID $row.DisplayTemplateID}} selected{{end}}>{{.Label}}</option>{{end}}</select>
                      <span class="meta">引擎与版本来自已验收目录，指纹须匹配该版本；不是只改 UA。服务端会核对最终三元组合。</span>
                      <span class="meta">高级详情：组合内部固定 {{range $.TemplateCombinations}}{{.DisplayServer}} + {{.Transport}}；{{end}}不开放 UA/WebGL/Canvas/字体逐项拼装。</span>
                    </div>
                    <div class="form-field"><label for="template-key-{{.ProfileID}}">幂等键</label><input id="template-key-{{.ProfileID}}" type="text" name="idempotency_key" maxlength="128" required></div>
                  </div>
                  <div class="form-actions"><button type="submit" class="btn btn-secondary">应用到下一 revision</button></div>
                </form>
                {{if .TemplateHistory}}
                <div class="template-history">
                  <h5 class="sub-form-title">可回退历史</h5>
                  {{range .TemplateHistory}}
                  <form method="post" action="/manage/browsers/{{$row.ProfileID}}/template" class="template-rollback-form">
                    <input type="hidden" name="csrf" value="{{$.CSRF}}">
                    <input type="hidden" name="return_to" value="browsers">
                    <input type="hidden" name="action" value="rollback">
                    <input type="hidden" name="browser_revision" value="{{$row.Revision}}">
                    <input type="hidden" name="target_revision" value="{{.ProfileRevision}}">
                    <div class="form-row">
                      <div class="form-field"><span class="field-label">r{{.ProfileRevision}}</span><span class="meta">{{.BrowserTemplateID}} · {{.EnvironmentArtifactID}} · {{.DisplayTemplateID}}</span></div>
                      <div class="form-field"><label for="rollback-key-{{.ProfileRevision}}">幂等键</label><input id="rollback-key-{{.ProfileRevision}}" type="text" name="idempotency_key" maxlength="128" required></div>
                      <div class="form-field-action"><button type="submit" class="btn btn-warning">回退到 r{{.ProfileRevision}}</button></div>
                    </div>
                  </form>
                  {{end}}
                </div>
                {{end}}
              </div>
            </details>
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

            {{if and .Manage .LegacyMigration}}
            <details class="network-details">
              <summary class="details-summary">{{if .LegacyMigration.Rollback}}回退网络迁移{{else}}迁入受管理网络{{end}}</summary>
              <div class="details-content">
                <p class="field-help">{{if .LegacyMigration.Rollback}}恢复迁移前的应用与网络配置，保留浏览器数据和停用状态。{{else}}使用已验收的网络配置，保留现有 Firefox、浏览器数据和停用状态。{{end}}操作中断后请使用相同操作标识重试。</p>
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="network-revision-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="action" value="{{if .LegacyMigration.Rollback}}legacy_network_rollback{{else}}legacy_network_migrate{{end}}">
                  <input type="hidden" name="revision" value="{{.LegacyMigration.Revision}}">
                  <input type="hidden" name="migration_id" value="{{.LegacyMigration.ID}}">
                  <label class="field-label" for="migration-key-{{.ProfileID}}">操作标识</label>
                  <input id="migration-key-{{.ProfileID}}" name="idempotency_key" maxlength="128" required>
                  <button type="submit" class="btn btn-primary"{{if .Running}} disabled{{end}}>{{if .LegacyMigration.Rollback}}恢复迁移前配置{{else}}迁入受管理直连{{end}}</button>
                </form>
              </div>
            </details>
            {{end}}
            {{if and .Manage (or $.ManagedDirect .NetworkProfiles)}}
            <details class="network-details">
              {{$browser := .}}
              <summary class="details-summary">网络配置（停止后应用）</summary>
              <div class="details-content">
                <p class="field-help meta">选择要使用的网络。请先安全关闭浏览器，确认停止后再应用；需要近期确认密码。</p>
                <form method="post" action="/manage/browsers/{{.ProfileID}}" class="network-revision-form">
                  <input type="hidden" name="csrf" value="{{$.CSRF}}">
                  <input type="hidden" name="action" value="network_select">
                  <input type="hidden" name="revision" value="{{.Revision}}">
                  <div class="form-row">
                    <div class="form-field">
                      <label for="network-selection-{{.ProfileID}}">网络</label>
                      <select id="network-selection-{{.ProfileID}}" name="network_selection" required>
                        {{if not .NetworkSelectionAvailable}}<option value="" selected disabled>当前网络不在可选列表，请选择</option>{{end}}
                        {{if $.ManagedDirect}}<option value="direct"{{if eq .NetworkSelection "direct"}} selected{{end}}>无代理（受管理 DIRECT）</option>{{end}}
                        {{range .NetworkProfiles}}<option value="proxy|{{.ID}}|{{.Revision}}"{{if eq $browser.NetworkSelection (printf "proxy|%s|%d" .ID .Revision)}} selected{{end}}>{{.Label}} · r{{.Revision}} · {{.Protocol}} · {{.Endpoint}}</option>{{end}}
                      </select>
                    </div>
                    <div class="form-field"><label for="network-key-{{.ProfileID}}">操作标识</label><input id="network-key-{{.ProfileID}}" type="text" name="idempotency_key" maxlength="128" required placeholder="为本次修改填写唯一标识"><span class="meta">重试同一次修改时，请使用相同标识。</span></div>
                    <div class="form-field-action"><button class="btn btn-primary" type="submit"{{if .Running}} disabled{{end}}>应用网络</button></div>
                  </div>
                </form>
              </div>
            </details>
            {{end}}

            {{if and $.ProxyDrafts (not $.NetworkEnabled) .Managed .Manage}}
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
              </div></details></div>
            </td></tr>{{end}}
          </tbody></table></div>
        {{else}}
        <p class="meta">没有配置远程浏览器。</p>
        {{end}}
      </section>

      {{else if and (eq .ActiveTab "network") .NetworkEnabled}}
      <section class="section-network" aria-labelledby="network-heading">
        <h2 id="network-heading" style="display:none">网络代理</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">总配置</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></span></div>
            <div class="stat-card-val">{{.NetworkStats.Total}}</div>
            <div class="stat-card-desc">已登记代理修订记录</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">正常可用</span><span class="stat-badge-icon" style="background:var(--color-success-bg);color:var(--color-success)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span></div>
            <div class="stat-card-val">{{.NetworkStats.Accepted}}</div>
            <div class="stat-card-desc">探针验收通过</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">待处理探针</span><span class="stat-badge-icon" style="background:var(--color-warning-bg);color:var(--color-warning)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></span></div>
            <div class="stat-card-val">{{.NetworkStats.Pending}}</div>
            <div class="stat-card-desc">等待探针验证</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">关联浏览器</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg></span></div>
            <div class="stat-card-val">{{.NetworkStats.References}}</div>
            <div class="stat-card-desc">引用此配置的环境</div>
          </div>
        </div>

        <div class="action-toolbar">
          <div class="search-box" hidden>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" placeholder="搜索当前代理列表..." aria-label="搜索代理">
          </div>
          <div class="toolbar-actions">
            <button type="button" class="btn btn-primary trigger-modal-btn" id="open-np-dialog" aria-haspopup="dialog">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>新增代理</span>
            </button>
          </div>
        </div>

        <dialog class="modal-dialog progressive-modal network-create-panel" id="create-network-dialog">
          <div class="dialog-header">
            <div>
              <h3 class="dialog-title">新增代理配置</h3>
              <p class="meta">创建、探针、停用和撤销需要最近确认密码。创建只写目录和 Secret Store，不会自动切换任何浏览器。</p>
            </div>
            <button type="button" class="dialog-close-btn" aria-label="关闭">&times;</button>
          </div>
          <form method="post" action="/manage/network-profiles" autocomplete="off" class="network-profile-create-form">
            <input type="hidden" name="csrf" value="{{.CSRF}}">
            <input type="hidden" name="return_to" value="network">
            <input type="hidden" name="action" value="create">
            <div class="form-grid">
              <div class="form-field"><label for="np-id">配置 ID</label><input id="np-id" type="text" name="id" maxlength="64" placeholder="例如：corp-egress" required></div>
              <div class="form-field"><label for="np-label">名称</label><input id="np-label" type="text" name="label" maxlength="64" placeholder="例如：公司代理" required></div>
              <div class="form-field"><label for="np-protocol">协议</label><select id="np-protocol" name="protocol"><option value="socks5">SOCKS5</option><option value="http">HTTP</option><option value="https">HTTPS</option></select></div>
              <div class="form-field"><label for="np-auth">认证方式</label><select id="np-auth" name="auth"><option value="username_password">用户名/密码</option><option value="basic">Basic</option><option value="none">无认证</option></select></div>
              <div class="form-field"><label for="np-host">代理主机</label><input id="np-host" type="text" name="host" maxlength="253" required></div>
              <div class="form-field"><label for="np-port">端口</label><input id="np-port" type="text" name="port" maxlength="5" required></div>
              <div class="form-field"><label for="np-user">用户名</label><input id="np-user" type="text" name="username" maxlength="4096" autocomplete="off"></div>
              <div class="form-field"><label for="np-password">密码</label><input id="np-password" type="password" name="password" maxlength="4096" autocomplete="new-password"></div>
              <div class="form-field"><label for="np-key">幂等键</label><input id="np-key" type="text" name="idempotency_key" maxlength="128" required></div>
            </div>
            <div class="form-field"><label for="np-ca">HTTPS 上游 CA（可选 PEM）</label><textarea id="np-ca" name="upstream_ca_pem" rows="2"></textarea></div>
            <div class="dialog-actions">
              <button type="button" class="btn btn-secondary dialog-cancel-btn">取消</button>
              <button type="submit" class="btn btn-primary">创建代理草稿</button>
            </div>
          </form>
        </dialog>

        {{if .NetworkProfiles}}
        <div class="table-container">
          <table class="network-profile-table management-table">
            <thead><tr><th>配置</th><th>连接</th><th>状态 / 探针</th><th>引用</th><th>操作</th></tr></thead>
            <tbody>
            {{range .NetworkProfiles}}
              <tr>
                <td><strong>{{.Label}}</strong><div class="meta">{{.ID}} · r{{.Revision}}</div>{{if .CreatedAt}}<div class="meta">创建 {{.CreatedAt}}</div>{{end}}</td>
                <td><div>{{.Protocol}} · {{.Auth}}</div><div class="meta">{{.Endpoint}}</div>{{if .HasCA}}<div class="meta">带上游 CA</div>{{end}}</td>
                <td><span class="badge badge-status">{{.Status}}</span>{{if .ProbeCode}}<div class="meta">探针 {{.ProbeCode}}{{if .ProbeAt}} · {{.ProbeAt}}{{end}}</div>{{end}}{{if .Expired}}<div class="meta blocking">已过期</div>{{end}}</td>
                <td><div>{{.References}} 个浏览器</div>{{if .AllowedProfiles}}<div class="meta">授权范围 {{len .AllowedProfiles}}</div>{{end}}</td>
                <td class="actions"><details class="record-details" data-title="{{.Label}} · 代理管理"><summary class="btn btn-secondary btn-sm">详情 / 管理</summary><div class="record-content">
                  {{if and (eq .Status "pending") .DraftID}}
                  <details class="row-action"><summary>执行探针</summary><form method="post" action="/manage/network-profiles" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="return_to" value="network"><input type="hidden" name="action" value="probe"><input type="hidden" name="id" value="{{.ID}}"><input type="hidden" name="draft_id" value="{{.DraftID}}"><button class="btn btn-primary btn-sm" type="submit">执行探针</button></form></details>
                  {{end}}
                  {{if eq .Status "accepted"}}
                  <details class="row-action"><summary>停用</summary><form method="post" action="/manage/network-profiles" class="network-revision-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="return_to" value="network"><input type="hidden" name="action" value="disable"><input type="hidden" name="id" value="{{.ID}}"><input type="hidden" name="revision" value="{{.Revision}}"><label for="np-disable-{{.ID}}-{{.Revision}}" class="field-label">停用幂等键</label><input id="np-disable-{{.ID}}-{{.Revision}}" type="text" name="idempotency_key" maxlength="128" required><button class="btn btn-warning btn-sm" type="submit">停用</button></form></details>
                  {{end}}
                  {{if eq .References 0}}
                  {{if or (eq .Status "disabled") (eq .Status "failed")}}
                  <details class="row-action"><summary>撤销</summary><form method="post" action="/manage/network-profiles" class="network-revision-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="return_to" value="network"><input type="hidden" name="action" value="revoke"><input type="hidden" name="id" value="{{.ID}}"><input type="hidden" name="revision" value="{{.Revision}}"><label for="np-revoke-{{.ID}}-{{.Revision}}" class="field-label">撤销幂等键</label><input id="np-revoke-{{.ID}}-{{.Revision}}" type="text" name="idempotency_key" maxlength="128" required><button class="btn btn-danger btn-sm" type="submit">撤销</button></form></details>
                  {{end}}
                  {{end}}
                  {{if $.NetworkDeletion}}{{if eq .References 0}}<details class="delete-control"><summary>删除代理</summary><p class="meta">删除此代理修订并撤销对应凭据；被浏览器引用时无法删除。</p><form method="post" action="/manage/network-profiles" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="delete"><input type="hidden" name="return_to" value="network"><input type="hidden" name="id" value="{{.ID}}"><input type="hidden" name="revision" value="{{.Revision}}"><input type="hidden" name="idempotency_key" value="delete-{{.ID}}-r{{.Revision}}"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除代理</button></form></details>{{else}}<p class="meta">被浏览器引用，无法删除</p>{{end}}{{end}}
                </div></details></td>
              </tr>
            {{end}}
            </tbody>
          </table>
          <div class="table-info-footer">
            <span>共 {{len .NetworkProfiles}} 条</span>
          </div>
        </div>
        {{else}}
        <div class="panel callout-panel"><p class="meta">还没有代理配置。浏览器仍只能使用已配置的受管理 DIRECT 或既有策略。</p></div>
        {{end}}
      </section>

      {{else if and (eq .ActiveTab "fingerprint-data") .JobsEnabled}}
      <section class="section-jobs" aria-labelledby="fingerprint-data-heading">
        <h2 id="fingerprint-data-heading" style="display:none">指纹数据</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">指纹模板</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0 0-10 10c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.1-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/></svg></span></div>
            <div class="stat-card-val">{{.DataStats.Fingerprints}}</div>
            <div class="stat-card-desc">已保存语言与时区</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">显示模板</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg></span></div>
            <div class="stat-card-val">{{.DataStats.Displays}}</div>
            <div class="stat-card-desc">系统与自定义显示模板</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">已验收组合</span><span class="stat-badge-icon" style="background:var(--color-success-bg);color:var(--color-success)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span></div>
            <div class="stat-card-val">{{.DataStats.Combinations}}</div>
            <div class="stat-card-desc">具备新建与复用资格</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">验收任务</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></span></div>
            <div class="stat-card-val">{{.DataStats.Jobs}}</div>
            <div class="stat-card-desc">历史生成验收作业</div>
          </div>
        </div>

        <nav class="data-nav" aria-label="指纹数据功能">
          <a href="/manage/?tab=fingerprint-data&amp;section=fingerprints"{{if eq .DataSection "fingerprints"}} aria-current="page"{{end}}><span class="data-nav-number" aria-hidden="true">1</span>指纹模板</a>
          <a href="/manage/?tab=fingerprint-data&amp;section=displays"{{if eq .DataSection "displays"}} aria-current="page"{{end}}><span class="data-nav-number" aria-hidden="true">2</span>显示模板</a>
          <a href="/manage/?tab=fingerprint-data&amp;section=combinations"{{if eq .DataSection "combinations"}} aria-current="page"{{end}}><span class="data-nav-number" aria-hidden="true">3</span>组合验收</a>
        </nav>
        <div class="fingerprint-function" data-section="{{.DataSection}}">
        {{if eq .DataSection "fingerprints"}}
        <details class="list-create"><summary class="btn btn-primary">创建指纹模板</summary><div class="list-create-content">
        <p class="meta">保存语言和时区，供不同显示配置重复使用。保存后到“组合验收”选择引擎和显示模板。</p>
        <div class="panel"><form method="post" action="/manage/fingerprint-templates"><input type="hidden" name="csrf" value="{{.CSRF}}"><div class="form-grid">
        <div class="form-field"><label for="fp-label">模板名称</label><input id="fp-label" type="text" name="label" maxlength="64" required></div>
        <div class="form-field"><label for="fp-locale">主要语言</label><input id="fp-locale" type="text" name="locale" maxlength="35" placeholder="en-US" required></div>
        <div class="form-field"><label for="fp-languages">语言列表（逗号分隔）</label><input id="fp-languages" type="text" name="languages" maxlength="200" placeholder="en-US,en" required></div>
        <div class="form-field"><label for="fp-timezone">时区</label><input id="fp-timezone" type="text" name="timezone" maxlength="64" placeholder="UTC" required></div>
        </div><div class="form-actions"><button type="submit" class="btn btn-primary">保存指纹模板</button></div></form></div></div></details>
        {{if .DataDeletion}}<p class="meta">删除前需确认密码；被浏览器或回退记录引用的模板不能删除。</p>{{end}}<h3 class="data-group-heading">已保存的指纹模板 <span class="badge badge-count">{{len .Sources.Fingerprints}}</span></h3>
        <div class="table-container"><table class="management-table fingerprint-table"><thead><tr><th>模板名称</th><th>语言 / 时区</th><th>适用引擎</th><th>操作</th></tr></thead><tbody>{{range .Sources.Fingerprints}}<tr><td><strong>{{.Label}}</strong></td><td>{{.Locale}} · {{.Timezone}}<div class="meta">语言：{{range $index, $language := .Languages}}{{if $index}}、{{end}}{{$language}}{{end}}</div></td><td>{{if .Engine}}{{.Engine}} {{.BrowserVersion}}{{else}}通用{{end}}</td><td>{{if .Builtin}}<span class="meta">内置模板不能删除</span>{{else if $.DataDeletion}}<details class="delete-control"><summary>删除指纹模板</summary><p class="meta">删除后从列表和可选项移除；浏览器引用中的数据不能删除。</p><form method="post" action="/manage/fingerprint-templates/{{.ID}}/delete" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除指纹模板</button></form></details>{{end}}</td></tr>{{else}}<tr><td colspan="4">还没有指纹模板。<p class="meta">先保存语言和时区，再到组合验收中使用。</p></td></tr>{{end}}</tbody></table></div>
        {{else if eq .DataSection "displays"}}
        <details class="list-create"><summary class="btn btn-primary">创建固定显示模板</summary><div class="list-create-content">
        <p class="meta">自定义模板使用固定尺寸和 DPR 1；系统自动显示随窗口大小和 UI Scaling 变化，内置模板不能删除。两类模板均可用于 Camoufox、Chromix 和 Firefox。</p>
        <div class="panel"><form method="post" action="/manage/display-templates"><input type="hidden" name="csrf" value="{{.CSRF}}"><div class="form-grid">
        <div class="form-field"><label for="display-label">模板名称</label><input id="display-label" type="text" name="label" maxlength="64" required></div>
        <div class="form-field"><label for="display-mode">分辨率模式</label><select id="display-mode" name="mode"><option value="fixed">固定分辨率</option></select></div>
        <div class="form-field"><label for="display-width">屏幕宽</label><input id="display-width" type="number" name="width" min="640" max="3840" value="1920" required></div>
        <div class="form-field"><label for="display-height">屏幕高</label><input id="display-height" type="number" name="height" min="480" max="2160" value="1080" required></div>
        <div class="form-field"><label for="display-dpr">DPR</label><select id="display-dpr" name="dpr"><option value="1">1（100%）</option></select></div>
        <div class="form-field"><label for="display-ww">窗口宽（默认同屏幕）</label><input id="display-ww" name="window_width" type="number" min="640" max="3840"></div>
        <div class="form-field"><label for="display-wh">窗口高（默认同屏幕）</label><input id="display-wh" name="window_height" type="number" min="480" max="2160"></div>
        </div><div class="form-actions"><button class="btn btn-primary" type="submit">保存显示模板</button></div></form></div></div></details>
        <h3 class="data-group-heading">已保存的显示模板</h3>
        <div class="table-container"><table class="management-table display-table"><thead><tr><th>模板名称</th><th>类型</th><th>屏幕 / DPR</th><th>窗口</th><th>操作</th></tr></thead><tbody>{{range .Sources.Displays}}<tr><td><strong>{{.Label}}</strong></td><td>{{if .Builtin}}系统内置{{else}}自定义{{end}}</td><td>{{if eq .Mode "auto"}}自动分辨率 · DPR 随缩放变化{{else}}{{.Width}} × {{.Height}} · DPR {{.DPR}}{{end}}</td><td>{{if eq .Mode "auto"}}随窗口调整{{else}}{{.WindowWidth}} × {{.WindowHeight}}{{end}}</td><td>{{if .Builtin}}<span class="meta">内置模板不能删除</span>{{else}}{{if $.DataDeletion}}<details class="delete-control"><summary>删除显示模板</summary><p class="meta">删除后从列表和可选项移除；浏览器引用中的数据不能删除。</p><form method="post" action="/manage/display-templates/{{.ID}}/delete" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除显示模板</button></form></details>{{end}}{{end}}</td></tr>{{else}}<tr><td colspan="5">还没有可用显示模板。</td></tr>{{end}}</tbody></table></div>
        {{else if eq .DataSection "combinations"}}
        <details class="list-create"><summary class="btn btn-primary">生成并验收</summary><div class="panel template-combinations"><p class="meta">选择已保存的模板和引擎。通过验收后，完整组合才会出现在新增浏览器的指纹选项中。</p><p class="meta">同一引擎首次生成后固定设备指纹，之后可搭配其他显示模板复用。Firefox 使用原生设备特征。</p>
        <form method="post" action="/manage/template-combinations"><input type="hidden" name="csrf" value="{{.CSRF}}"><div class="form-grid">
        <div class="form-field"><label for="combo-fingerprint">指纹模板</label><select id="combo-fingerprint" name="fingerprint_id" required><option value="" disabled selected>请选择已保存的指纹模板</option>{{range .Sources.Fingerprints}}<option value="{{.ID}}">{{.Label}} · {{.Locale}} / {{.Timezone}}</option>{{end}}</select></div>
        <div class="form-field"><label for="combo-engine">浏览器引擎</label><select id="combo-engine" name="browser_template_id" required><option value="" disabled selected>请选择引擎</option>{{range .Sources.GenerationTargets}}<option value="{{.BrowserTemplateID}}">{{.Engine}} {{.BrowserVersion}}</option>{{end}}</select></div>
        <div class="form-field"><label for="combo-display">显示模板</label><select id="combo-display" name="display_id" required><option value="" disabled selected>请选择显示模板</option>{{range .Sources.Displays}}<option value="{{.ID}}">{{if .Builtin}}系统内置 · {{else}}自定义 · {{end}}{{.Label}}</option>{{end}}</select></div>
        </div>{{if not .Sources.Fingerprints}}<p class="meta">请先<a href="/manage/?tab=fingerprint-data&amp;section=fingerprints">创建指纹模板</a>，再选择引擎和显示模板生成组合。</p>{{end}}<button class="btn btn-primary" type="submit"{{if or (not .Sources.Fingerprints) (not .Sources.Displays) (not .Sources.GenerationTargets)}} disabled{{end}}>生成并验收组合</button></form></div></details>
        {{if not .Sources.GenerationTargets}}<p class="meta">当前没有可用的生成引擎。</p>{{end}}
        {{if not .Sources.Displays}}<p class="meta">没有可用显示模板，请到<a href="/manage/?tab=fingerprint-data&amp;section=displays">显示模板</a>中查看或创建。</p>{{end}}
        <h3 class="data-group-heading">验收任务 <span class="badge badge-count">{{len .Jobs}}</span></h3>
        {{if .Jobs}}
        <div class="table-container">
          <table class="jobs-table management-table">
            <thead><tr><th>作业</th><th>模板组合 / 旧作业请求</th><th>状态</th><th>结果</th></tr></thead>
            <tbody>
              {{range .Jobs}}<tr>
                <td><div class="job-id">{{.ID}}</div><div class="meta">{{.EnvironmentID}}</div><div class="meta">{{.Actor}} · {{.RequestedAt}}</div></td>
                <td><div>{{.Locale}} · {{.Timezone}}</div>{{if .FingerprintTemplateID}}<div class="meta">{{.FingerprintTemplateID}} + {{.DisplayPresetID}}</div>{{if .Generation}}<div class="meta">{{.Generation.Engine}} {{.Generation.BrowserVersion}}</div>{{end}}{{else}}<div class="meta">旧作业：{{.Screen}} · 窗口 {{.Window}}</div>{{end}}</td>
                <td><div>{{.Status}}{{if .Phase}} · {{.Phase}}{{end}}</div>{{if .Code}}<div class="meta{{if eq .Status "failed"}} blocking{{end}}">{{.Code}}{{if .Message}} · {{.Message}}{{end}}</div>{{end}}{{if .UpdatedAt}}<div class="meta">{{.UpdatedAt}}</div>{{end}}</td>
                <td class="meta">{{if .ArtifactSHA256}}<div>产物 {{slice .ArtifactSHA256 0 12}}…</div>{{end}}{{if .AcceptanceSHA256}}<div>报告 {{slice .AcceptanceSHA256 0 12}}…</div>{{end}}{{if .Attempts}}<div>生成尝试 {{.Attempts}}</div>{{end}}{{if $.DataDeletion}}{{if or (eq .Status "accepted") (eq .Status "failed")}}<details class="delete-control"><summary>删除任务记录</summary><p class="meta">只移除这条已结束任务记录；已发布组合需单独删除，原验收证据保留。浏览器引用其结果时不能删除。</p><form method="post" action="/manage/environment-jobs/{{.ID}}/delete" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除任务记录</button></form></details>{{else}}<div class="meta">任务结束后可删除</div>{{end}}{{end}}</td>
              </tr>{{end}}
            </tbody>
          </table>
          <div class="table-info-footer">
            <span>共 {{len .Jobs}} 条</span>
          </div>
        </div>
        {{else}}<div class="panel data-empty"><p>还没有验收任务。</p><p class="meta">提交组合后，在这里查看进度和结果。</p></div>{{end}}
        <h3 class="data-group-heading">已验收组合 <span class="badge badge-count">{{len .TemplateCombinations}}</span></h3>
        <div class="table-container accepted-combinations"><table class="management-table combinations-table"><thead><tr><th>组合名称</th><th>浏览器</th><th>语言 / 时区</th><th>显示</th><th>状态</th><th>操作</th></tr></thead><tbody>{{range .TemplateCombinations}}<tr><td><strong>{{.EnvironmentLabel}}</strong></td><td>{{.BrowserLabel}}<div class="meta">{{.Engine}} {{.BrowserVersion}}</div></td><td>{{.Locale}} / {{.Timezone}}</td><td>{{.DisplayLabel}}</td><td><span class="badge">{{if .AllowNewBrowsers}}可用于新增浏览器{{else}}仅供已有浏览器使用{{end}}</span></td><td>{{if .Builtin}}<span class="meta">内置组合不能删除</span>{{else if $.DataDeletion}}<details class="delete-control"><summary>删除组合</summary><p class="meta">删除后从列表和可选项移除；浏览器引用中的数据不能删除。</p><form method="post" action="/manage/template-combinations/{{.EnvironmentArtifactID}}/delete" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="browser_template_id" value="{{.BrowserTemplateID}}"><input type="hidden" name="display_template_id" value="{{.DisplayTemplateID}}"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除组合</button></form></details>{{end}}</td></tr>{{else}}<tr><td colspan="6">还没有已验收组合。<p class="meta">保存模板不会直接生成环境，请先提交组合验收。</p></td></tr>{{end}}</tbody></table></div>
        {{end}}
        </div>
      </section>

      {{else if eq .ActiveTab "accounts"}}
      <section class="section-accounts" aria-labelledby="accounts-heading">
        <h2 id="accounts-heading" style="display:none">访问账号</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">总账号数</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span></div>
            <div class="stat-card-val">{{.AccountStats.Total}}</div>
            <div class="stat-card-desc">账号池规模</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">正常启用</span><span class="stat-badge-icon" style="background:var(--color-success-bg);color:var(--color-success)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span></div>
            <div class="stat-card-val">{{.AccountStats.Enabled}}</div>
            <div class="stat-card-desc">可登录平台</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">管理员</span><span class="stat-badge-icon" style="background:#eff6ff;color:var(--color-primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span></div>
            <div class="stat-card-val">{{.AccountStats.Admins}}</div>
            <div class="stat-card-desc">管理权限角色</div>
          </div>
          <div class="stat-card">
            <div class="stat-card-head"><span class="meta">已禁用</span><span class="stat-badge-icon" style="background:var(--color-warning-bg);color:var(--color-warning)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg></span></div>
            <div class="stat-card-val">{{.AccountStats.Disabled}}</div>
            <div class="stat-card-desc">已停用/禁止登录</div>
          </div>
        </div>

        <div class="action-toolbar">
          <div class="search-box" hidden>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" placeholder="搜索当前账号列表..." aria-label="搜索账号">
          </div>
          <div class="toolbar-actions">
            <button type="button" class="btn btn-primary trigger-modal-btn" id="open-na-dialog" aria-haspopup="dialog">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>新增账号</span>
            </button>
          </div>
        </div>

        <p class="meta" style="margin-bottom:1rem">浏览器入口账号只能登录被分配的浏览器；管理员账号可进入本面板。删除账号、禁用/启用账号、修改角色、重置他人密码前须 <a href="{{.ReauthURL}}">确认密码</a>（5 分钟内有效）。</p>

        {{if .Accounts}}
        <div class="table-container">
          <table class="accounts-table management-table">
            <thead><tr><th>账号</th><th>角色</th><th>状态</th><th>可登录的浏览器</th><th>操作</th></tr></thead>
            <tbody>
              {{range .Accounts}}<tr>
                <td><strong>{{.ID}}</strong></td>
                <td><span class="badge badge-role">{{.Role}}</span></td>
                <td>{{if .Disabled}}<span class="badge badge-disabled off">已禁用</span>{{else}}<span class="badge badge-success">启用</span>{{end}}</td>
                <td>{{len .Grants}} 个浏览器</td>
                <td class="account-actions-cell actions"><details class="record-details" data-title="{{.ID}} · 账号管理"><summary class="btn btn-secondary btn-sm">详情 / 管理</summary><div class="record-content"><details class="row-action"><summary>分配浏览器</summary><form method="post" action="/manage/accounts/{{.ID}}" class="grants-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="grants"><div class="grants-checkboxes">{{$row := .}}{{range .AllProfiles}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"{{if index $row.Grants .}} checked{{end}}> {{.}}</label>{{end}}</div><button type="submit" class="btn btn-secondary btn-sm">保存分配</button></form></details>
                  <details class="row-action"><summary>重置密码</summary><form method="post" action="/manage/accounts/{{.ID}}" class="pwd-reset-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="reset_password"><label for="pwd-{{.ID}}" class="field-label">新密码</label><div class="inline-input-group"><input id="pwd-{{.ID}}" type="password" name="password" minlength="1" data-password-bytes="4" maxlength="256" placeholder="4–256 字节" autocomplete="new-password"><button type="submit" class="btn btn-secondary btn-sm">重置密码</button></div></form></details>
                  <div class="account-btn-group">
                    {{if .Disabled}}<details class="row-action"><summary>启用</summary><form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="enable"><button type="submit" class="btn btn-secondary btn-sm">启用</button></form></details>
                    {{else}}<details class="row-action"><summary>停用</summary><form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="disable"><button type="submit" class="btn btn-warning btn-sm">禁用</button></form></details>{{end}}
                    <details class="row-action"><summary>修改角色</summary><form method="post" action="/manage/accounts/{{.ID}}" class="inline"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="role"><input type="hidden" name="role" value="{{if eq .Role "admin"}}user{{else}}admin{{end}}"><button type="submit" class="btn btn-secondary btn-sm">{{if eq .Role "admin"}}改为入口账号{{else}}改为管理员{{end}}</button></form></details>
                  </div>
                  {{if ne .ID $.Subject}}<details class="delete-control"><summary>删除账号</summary><p class="meta">删除账号并撤销其登录和显示访问权限，浏览器数据保留。最后一个启用的管理员不能删除。</p><form method="post" action="/manage/accounts/{{.ID}}" class="delete-form"><input type="hidden" name="csrf" value="{{$.CSRF}}"><input type="hidden" name="action" value="delete"><label class="chk"><input type="checkbox" name="confirm" value="delete" required> 确认删除</label><button type="submit" class="btn btn-danger btn-sm">删除账号</button></form></details>{{else}}<p class="meta">当前登录账号不能删除</p>{{end}}
                </div></details></td>
              </tr>{{end}}
            </tbody>
          </table>
          <div class="table-info-footer">
            <span>共 {{len .Accounts}} 条</span>
          </div>
        </div>
        {{else}}<p class="meta">账号表暂不可读。</p>{{end}}

        <dialog class="modal-dialog progressive-modal create-account-panel" id="create-account-dialog">
          <div class="dialog-header">
            <div>
              <h3 class="dialog-title">新增账号</h3>
              <p class="meta">创建浏览器入口或管理权限账号。</p>
            </div>
            <button type="button" class="dialog-close-btn" aria-label="关闭">&times;</button>
          </div>
          <form method="post" action="/manage/accounts" class="account-create-form"><input type="hidden" name="csrf" value="{{.CSRF}}">
            <div class="form-grid">
              <div class="form-field"><label for="na-acc">账号 ID</label><input id="na-acc" type="text" name="account" maxlength="32" pattern="[a-z0-9][a-z0-9_-]{0,31}" placeholder="账号 ID（小写字母、数字、_-）" required></div>
              <div class="form-field"><label for="na-pwd">密码</label><input id="na-pwd" type="password" name="password" minlength="1" data-password-bytes="4" maxlength="256" placeholder="密码（4–256 字节）" autocomplete="new-password" required></div>
            </div>
            <fieldset class="form-field"><legend>角色</legend><div class="radio-group"><label class="chk"><input type="radio" name="role" value="user" checked> 浏览器入口账号</label><label class="chk"><input type="radio" name="role" value="admin"> 管理员（需先确认密码）</label></div></fieldset>
            <fieldset class="form-field"><legend>可登录的浏览器</legend><div class="checkbox-group">{{range .ProfileIDs}}<label class="chk"><input type="checkbox" name="profiles" value="{{.}}"> {{.}}</label>{{end}}</div></fieldset>
            <div class="dialog-actions">
              <button type="button" class="btn btn-secondary dialog-cancel-btn">取消</button>
              <button type="submit" class="btn btn-primary">创建账号</button>
            </div>
          </form>
        </dialog>
      </section>
      {{end}}
    </main>

    <footer class="app-footer">
      <p class="meta">远程浏览器管理 · 生成时间 {{.GeneratedAt}} · 列表只读取最近一次健康采样，过期即标为 stale；关闭按钮走已验证的停止流程，不删除 Home。</p>
    </footer>
  </div>
</div>
  ` + access.PasswordDialogMarkup + access.ReauthDialogMarkup + `
<script nonce="{{.ScriptNonce}}">
  (() => {
    // Enhance existing forms only when native dialog support is available.
    for (const [dialogId, triggerId] of [
      ['create-browser-dialog', 'open-cb-dialog'],
      ['create-network-dialog', 'open-np-dialog'],
      ['create-account-dialog', 'open-na-dialog']
    ]) {
      const dialog = document.getElementById(dialogId);
      const trigger = document.getElementById(triggerId);
      if (!dialog || !trigger || typeof dialog.showModal !== 'function') continue;
      dialog.setAttribute('aria-labelledby', dialog.querySelector('h2, h3').id || (dialogId + '-title'));
      dialog.querySelector('h2, h3').id = dialog.getAttribute('aria-labelledby');
      dialog.classList.add('dialog-ready');
      trigger.style.display = 'inline-flex';
      let lastFocus;
      trigger.addEventListener('click', () => {
        lastFocus = document.activeElement;
        dialog.showModal();
        const first = dialog.querySelector('input:not([type=hidden]), select, textarea');
        if (first) first.focus();
      });
      dialog.querySelectorAll('.dialog-close-btn, .dialog-cancel-btn').forEach(button => {
        button.addEventListener('click', () => dialog.close());
      });
      dialog.addEventListener('close', () => {
        if (lastFocus && (document.activeElement === document.body || dialog.contains(document.activeElement))) lastFocus.focus();
      });
      dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], summary, [tabindex]:not([tabindex="-1"])')].filter(element => element.getClientRects().length);
        if (!controls.length) { event.preventDefault(); return; }
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      });
    }
    const search = document.querySelector('.search-input');
    if (search) {
      const rows = [...document.querySelectorAll('.browser-management-table > tbody > tr, .network-profile-table > tbody > tr, .accounts-table > tbody > tr')];
      const rowText = new Map(rows.map(row => [row, row.textContent.toLocaleLowerCase()]));
      const status = document.createElement('p');
      status.className = 'meta filter-status';
      status.setAttribute('role', 'status');
      search.closest('.action-toolbar').after(status);
      search.closest('.search-box').hidden = false;
      search.addEventListener('input', () => {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        rows.forEach(row => {
          row.hidden = !rowText.get(row).includes(query);
          if (!row.hidden) visible++;
        });
        status.textContent = query ? ('找到 ' + visible + ' 条，共 ' + rows.length + ' 条') : '';
      });
    }

    const engine = document.getElementById('cb-browser-template');
    const fingerprint = document.getElementById('cb-fingerprint-template');
    const pool = document.getElementById('cb-fingerprint-options');
    const submit = document.getElementById('cb-submit');
    const info = document.getElementById('cb-template-info');
    if (engine && fingerprint && pool && submit && info) {
      const choices = Array.from(pool.content.querySelectorAll('option'));
      function describe() {
        const selected = fingerprint.selectedOptions[0];
        info.textContent = selected && selected.value
          ? '显示配置：' + selected.dataset.display + '（随指纹自动应用）'
          : '该引擎暂无已验收的指纹组合，请先生成并验收。';
        submit.disabled = !fingerprint.value || submit.dataset.networkReady !== 'true';
      }
      function refresh() {
        const previous = fingerprint.value;
        const options = choices.filter(option => option.dataset.browser === engine.value);
        fingerprint.replaceChildren(...options.map(option => option.cloneNode(true)));
        fingerprint.disabled = options.length === 0;
        if (!options.length) fingerprint.add(new Option('暂无已验收的指纹组合', ''));
        else if (options.some(option => option.value === previous)) fingerprint.value = previous;
        describe();
      }
      engine.addEventListener('change', refresh);
      fingerprint.addEventListener('change', describe);
      engine.form.addEventListener('reset', () => setTimeout(refresh, 0));
      window.addEventListener('pageshow', refresh);
      refresh();
    }

    const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.app-sidebar');
  const main = document.querySelector('.app-main-wrapper');
  const trigger = document.querySelector('.sidebar-toggle-btn');
  const mobile = window.matchMedia('(max-width: 768px)');
  if (toggle && sidebar && trigger) {
    toggle.tabIndex = -1;
    const sync = (focus) => {
      const open = mobile.matches ? toggle.checked : !toggle.checked;
      trigger.setAttribute('aria-expanded', String(open));
      trigger.setAttribute('aria-controls', 'sidebar');
      sidebar.inert = !open;
      main.inert = mobile.matches && open;
      if (focus) {
        if (mobile.matches && open) sidebar.querySelector('.sidebar-collapse-btn').focus();
        else trigger.focus();
      }
    };
    toggle.addEventListener('change', () => sync(true));
    document.querySelectorAll('.sidebar-toggle-btn, .sidebar-collapse-btn').forEach(btn => {
      btn.addEventListener('keydown', event => {
        if (event.key === ' ' || event.key === 'Enter') {
          event.preventDefault(); toggle.checked = !toggle.checked; sync(true);
        }
      });
    });
    document.addEventListener('keydown', event => {
      if (!mobile.matches || !toggle.checked || document.querySelector('dialog[open]')) return;
      if (event.key === 'Escape') { event.preventDefault(); toggle.checked = false; sync(true); }
      if (event.key === 'Tab') {
        const controls = [...sidebar.querySelectorAll('a[href], button, summary, [tabindex="0"]')].filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    mobile.addEventListener('change', () => { toggle.checked = false; sync(false); });
    sync(false);
  }
  })();
(() => {
function setupDialogTabs(dialog, groups) {
  const body = dialog.querySelector('.record-content') || dialog.querySelector('.dialog-body') || dialog;
  const valid = (groups || []).filter(g => g?.nodes?.length);
  if (!valid.length) return;

  const baseId = dialog.id || 'dlg';
  const tablist = document.createElement('div');
  tablist.className = 'record-dialog-tablist';
  tablist.setAttribute('role', 'tablist');
  tablist.setAttribute('aria-label', '管理功能');
  const tabs = [], panels = [];

  valid.forEach((g, i) => {
    const tabId = baseId + '-tab-' + i, panelId = baseId + '-panel-' + i;
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.id = tabId;
    tab.className = 'record-dialog-tab';
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', panelId);
    tab.textContent = g.label;
    tabs.push(tab);

    const panel = document.createElement('div');
    panel.id = panelId;
    panel.className = 'record-dialog-panel';
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', tabId);
    g.nodes.forEach(n => panel.appendChild(n));
    panels.push(panel);

    tablist.appendChild(tab);
    body.appendChild(panel);
  });

  function activate(idx, focus = false) {
    tabs.forEach((t, i) => {
      const sel = i === idx;
      t.setAttribute('aria-selected', String(sel));
      t.tabIndex = sel ? 0 : -1;
      panels[i].hidden = !sel;
    });
    if (focus) tabs[idx]?.focus();
  }

  tablist.addEventListener('keydown', e => {
    let cur = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
    if (e.key === 'ArrowRight') cur = (cur + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') cur = (cur - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') cur = 0;
    else if (e.key === 'End') cur = tabs.length - 1;
    else return;
    e.preventDefault();
    activate(cur, true);
  });

  tablist.addEventListener('click', e => {
    const idx = tabs.indexOf(e.target.closest('[role="tab"]'));
    if (idx !== -1) activate(idx);
  });

  if (valid.length > 1) {
    const header = dialog.querySelector('.dialog-header');
    if (header) header.after(tablist);
    else dialog.prepend(tablist);
  }

  dialog.addEventListener('invalid', e => {
    const idx = panels.findIndex(p => p.contains(e.target));
    if (idx !== -1) activate(idx);
  }, true);

  activate(0);
}

  const organizeDialog = (dialog, content) => {
    const browser = content.querySelector('.browser-card');
    let groups;
    if (browser) {
      const nodes = [...browser.children];
      const selectors = ['.card-header,.card-entry,.overview-grid,.card-unavailable', '.card-settings', '.network-details', '.template-details', '.card-lifecycle,.danger-zone'];
      const labels = ['概览','常用设置','网络','环境模板','危险操作'];
      groups = selectors.map((selector, i) => ({label:labels[i], nodes:nodes.filter(n => n.matches(selector))}));
      groups[0].nodes.push(...nodes.filter(n => !selectors.some(s => n.matches(s))));
    } else {
      const nodes = [...content.children];
      groups = nodes.map(n => ({label:n.querySelector(':scope > summary')?.textContent.trim() || '说明',nodes:[n]}));
    }
    if (groups.filter(g => g.nodes.length).length < 2) return;
    groups.forEach(g => g.nodes.forEach(n => {if (n.tagName === 'DETAILS') n.open = true;}));
    setupDialogTabs(dialog, groups);
    if (browser) browser.remove();
  };
  const setupDialogs = () => {
    if (typeof HTMLDialogElement !== 'function' || typeof HTMLDialogElement.prototype.showModal !== 'function') return;
    document.querySelectorAll('details.record-details, .fingerprint-function details.list-create, .fingerprint-function details.delete-control').forEach((details, index) => {
      const summary = details.querySelector(':scope > summary');
      if (!summary) return;
      let content = details.querySelector(':scope > .record-content');
      if (!content) {
        content = document.createElement('div');
        content.className = 'record-content';
        [...details.childNodes].filter(node => node !== summary).forEach(node => content.appendChild(node));
      }
      const deleting = details.matches('.fingerprint-function .delete-control');
      let trigger = summary;
      if (deleting) {
        trigger = document.createElement('button'); trigger.type = 'button';
        trigger.className = 'btn btn-danger btn-sm delete-dialog-trigger';
        trigger.textContent = summary.textContent.trim();
        details.before(trigger); details.hidden = true;
      }
      const row = details.closest('tr');
      const identity = row && (row.querySelector('td strong, td .job-id') || row.querySelector('td'));

      const dialog = document.createElement('dialog');
      dialog.className = 'record-dialog' + (deleting ? ' danger-dialog' : '');
      dialog.id = 'record-dialog-' + index;
      trigger.setAttribute('aria-haspopup', 'dialog');
      trigger.setAttribute('aria-controls', dialog.id);

      const header = document.createElement('div');
      header.className = 'dialog-header';

      const title = document.createElement('h3');
      title.className = 'dialog-title';
      title.id = dialog.id + '-title';
      dialog.setAttribute('aria-labelledby', title.id);
      title.textContent = details.dataset.title || summary.dataset.title || summary.textContent.trim() || '详情';
      if (deleting && identity) title.textContent += ' · ' + identity.textContent.trim();

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'dialog-close';
      closeBtn.textContent = '✕';
      closeBtn.setAttribute('aria-label', '关闭');

      header.append(title, closeBtn);

      const body = document.createElement('div');
      body.className = 'dialog-body';
      body.appendChild(content);

      const footer = document.createElement('div');
      footer.className = 'dialog-footer';
      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'btn btn-secondary';
      cancelBtn.textContent = '取消';
      footer.appendChild(cancelBtn);
      dialog.append(header, body, footer);
      document.body.appendChild(dialog);
      if (details.matches('.record-details')) organizeDialog(dialog, content);

      const closeDialog = () => {
        if (dialog.open) dialog.close();
      };

      closeBtn.addEventListener('click', closeDialog);
      cancelBtn.addEventListener('click', closeDialog);
      dialog.addEventListener('close', () => {
        if (document.activeElement === document.body || dialog.contains(document.activeElement)) trigger.focus();
      });

      dialog.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        const focusables = [...dialog.querySelectorAll(
          'button:not([disabled]), a[href], input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
        )].filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          last.focus();
          e.preventDefault();
        } else if (!e.shiftKey && document.activeElement === last) {
          first.focus();
          e.preventDefault();
        }
      });

      trigger.addEventListener('click', (e) => {
        e.preventDefault();
        dialog.showModal();
        closeBtn.focus();
      });
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupDialogs);
  } else {
    setupDialogs();
  }
})();
  ` + access.PasswordDialogScript + access.ReauthDialogScript + `
</script>
</body>
</html>
`)))
