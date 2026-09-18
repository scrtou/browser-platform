package profile

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

// Health reports are read-only: they never take the Profile lock, never call
// LaunchURL or StopHome and never rewrite the journal. Every report is bound to
// the journal binding it observed and expires after HealthTTL.
const (
	HealthTTL            = 60 * time.Second
	HealthMinInterval    = 10 * time.Second
	healthCollectTimeout = 30 * time.Second
)

var (
	ErrHealthThrottled   = errors.New("health probe requested too soon after the previous one")
	ErrHealthUnavailable = errors.New("no health report has been collected yet")
	ErrHealthPending     = errors.New("health collection is still running")
)

type CheckStatus string

const (
	CheckPass          CheckStatus = "pass"
	CheckFail          CheckStatus = "fail"
	CheckWarn          CheckStatus = "warn"
	CheckUnknown       CheckStatus = "unknown"
	CheckNotApplicable CheckStatus = "not_applicable"
)

type Overall string

const (
	OverallHealthy   Overall = "healthy"
	OverallDegraded  Overall = "degraded"
	OverallUnknown   Overall = "unknown"
	OverallUnhealthy Overall = "unhealthy"
	OverallOffline   Overall = "offline"
)

type HealthCheck struct {
	Name     string      `json:"name"`
	Status   CheckStatus `json:"status"`
	Required bool        `json:"required"`
	Code     string      `json:"code"`
	Message  string      `json:"message"`
}

// Recovery is the user-facing hint. Blocking means the fixed entry should show
// it before reconnecting to the Session.
type Recovery struct {
	Code     string   `json:"code"`
	Title    string   `json:"title"`
	Steps    []string `json:"steps"`
	Blocking bool     `json:"blocking"`
}

type HealthBinding struct {
	Status              state.Status `json:"status"`
	OperationID         string       `json:"operation_id,omitempty"`
	SessionID           string       `json:"session_id,omitempty"`
	ApplicationID       string       `json:"application_id"`
	HomeName            string       `json:"home_name"`
	NetworkPolicyID     string       `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256 string       `json:"network_policy_sha256,omitempty"`
	UpdatedAt           *time.Time   `json:"updated_at,omitempty"`
}

type HealthRuntime struct {
	Records         int    `json:"records"`
	Workers         int    `json:"workers"`
	Orphans         int    `json:"orphans"`
	Resources       int    `json:"resources"`
	NetworkPhase    string `json:"network_phase,omitempty"`
	LaunchPhase     string `json:"launch_phase,omitempty"`
	WorkerStatus    string `json:"worker_status,omitempty"`
	WorkerStartedAt string `json:"worker_started_at,omitempty"`
	ObservedAt      string `json:"observed_at,omitempty"`
	// DisplayConnections is the number of authenticated display connections
	// SealSkin's proxy holds to the Worker; -1 when it could not be observed.
	DisplayConnections int `json:"display_connections"`
}

type HealthReport struct {
	journalBinding state.Binding
	hasBinding     bool
	Version        int                          `json:"version"`
	NetworkMode    string                       `json:"network_mode,omitempty"`
	ProfileID      string                       `json:"profile_id"`
	Overall        Overall                      `json:"overall"`
	CheckedAt      time.Time                    `json:"checked_at"`
	ExpiresAt      time.Time                    `json:"expires_at"`
	Stale          bool                         `json:"stale"`
	Cached         bool                         `json:"cached"`
	Binding        HealthBinding                `json:"binding"`
	Environment    sealskin.EnvironmentIdentity `json:"environment"`
	Coherence      *sealskin.CoherenceReport    `json:"coherence,omitempty"`
	Runtime        HealthRuntime                `json:"runtime"`
	Checks         []HealthCheck                `json:"checks"`
	Recovery       *Recovery                    `json:"recovery"`
}

// Public strips the launch-operation capability and the Session identifier for
// the authenticated entry site; codes, messages and recovery steps remain.
func (r HealthReport) Public() HealthReport {
	r.Binding.OperationID = ""
	r.Binding.SessionID = ""
	if r.Coherence != nil {
		copy := *r.Coherence
		copy.Binding.OperationID, copy.Binding.SessionID = "", ""
		r.Coherence = &copy
	}
	return r
}

// AsOf marks an expired report; expiry is a required check so an expired
// report can never present itself as healthy or offline.
func (r HealthReport) AsOf(now time.Time) HealthReport {
	checks := make([]HealthCheck, 0, len(r.Checks)+1)
	for _, check := range r.Checks {
		if check.Name != "freshness" {
			checks = append(checks, check)
		}
	}
	if !now.Before(r.ExpiresAt) {
		r.Stale = true
		checks = append(checks, HealthCheck{Name: "freshness", Status: CheckUnknown, Required: true, Code: "REPORT_EXPIRED",
			Message: "报告已超过 " + HealthTTL.String() + " 有效期，需要重新采集"})
	} else {
		r.Stale = false
		checks = append(checks, HealthCheck{Name: "freshness", Status: CheckPass, Required: true, Code: "REPORT_FRESH",
			Message: "报告在有效期内"})
	}
	r.Checks = checks
	if r.Coherence != nil && !r.Coherence.Fresh(now) {
		copy := *r.Coherence
		copy.Allowed = false
		if copy.Overall != "unhealthy" {
			copy.Overall, copy.Code = "unknown", "COHERENCE_EXPIRED"
		}
		r.Coherence = &copy
		r.Recovery = coherenceRecovery("COHERENCE_EXPIRED")
	}
	r.Overall = overallStatus(checks, r.Overall == OverallOffline && !r.Stale)
	return r
}

// HealthOptions selects cache behaviour; none of them enables a mutation.
type HealthOptions struct {
	Force      bool          // start a fresh collection even if a fresh report is cached; HealthMinInterval applies
	CachedOnly bool          // never collect; return the last report, marked stale when expired
	Wait       time.Duration // maximum time to wait for an in-flight collection; 0 waits until ctx ends
}

type healthFlight struct {
	done   chan struct{}
	report HealthReport
	err    error
}

type healthCache struct {
	mu       sync.Mutex
	reports  map[string]HealthReport
	inflight map[string]*healthFlight
	started  map[string]time.Time
}

// Health returns the Profile's report. It only reads the journal and calls the
// read-only SealSkin observation endpoint; it never launches or stops anything.
func (s *Service) Health(ctx context.Context, id string, opts HealthOptions) (HealthReport, error) {
	if _, ok := s.directory.get(id); !ok {
		return HealthReport{}, ErrProfileNotFound
	}
	if s.runtime == nil {
		return HealthReport{}, ErrLifecycleDisabled
	}
	now := s.now()
	s.health.mu.Lock()
	cached, hasCached := s.health.reports[id]
	if opts.CachedOnly {
		s.health.mu.Unlock()
		if !hasCached {
			return HealthReport{}, ErrHealthUnavailable
		}
		cached.Cached = true
		return s.boundHealth(cached, now)
	}
	if hasCached && !opts.Force && now.Before(cached.ExpiresAt) {
		s.health.mu.Unlock()
		cached.Cached = true
		return s.boundHealth(cached, now)
	}
	flight := s.health.inflight[id]
	if flight == nil {
		if opts.Force && hasCached && now.Sub(s.health.started[id]) < HealthMinInterval {
			s.health.mu.Unlock()
			cached.Cached = true
			report, err := s.boundHealth(cached, now)
			if err != nil {
				return HealthReport{}, err
			}
			return report, ErrHealthThrottled
		}
		flight = &healthFlight{done: make(chan struct{})}
		s.health.inflight[id] = flight
		s.health.started[id] = now
		go s.runHealthFlight(id, flight)
	}
	s.health.mu.Unlock()
	var deadline <-chan time.Time
	if opts.Wait > 0 {
		timer := time.NewTimer(opts.Wait)
		defer timer.Stop()
		deadline = timer.C
	}
	select {
	case <-flight.done:
		if flight.err != nil {
			return HealthReport{}, flight.err
		}
		return s.boundHealth(flight.report, s.now())
	case <-deadline:
		return HealthReport{}, ErrHealthPending
	case <-ctx.Done():
		return HealthReport{}, ctx.Err()
	}
}

// Every return, including a completed shared flight, rechecks the current
// journal. Keep the stored historical report; a GET never starts a replacement
// observation merely because its binding changed.
func (s *Service) boundHealth(report HealthReport, now time.Time) (HealthReport, error) {
	current, found, err := s.store.Get(report.ProfileID)
	if err != nil {
		return HealthReport{}, err
	}
	if found != report.hasBinding || !sameHealthJournal(current, report.journalBinding) {
		definition, _ := s.directory.get(report.ProfileID)
		result := buildHealthReport(definition, current, found, nil, errBindingChanged, now)
		result.Cached = report.Cached
		return result.AsOf(now), nil
	}
	return report.AsOf(now), nil
}

func sameHealthJournal(a, b state.Binding) bool {
	return a.ProfileID == b.ProfileID && a.Status == b.Status && a.OperationID == b.OperationID &&
		a.SessionID == b.SessionID && a.HomeName == b.HomeName && a.ApplicationID == b.ApplicationID &&
		a.NetworkPolicyID == b.NetworkPolicyID && a.NetworkPolicySHA256 == b.NetworkPolicySHA256 &&
		a.BootstrapURL == b.BootstrapURL && a.ResumeIdempotencyKey == b.ResumeIdempotencyKey &&
		a.StopOperationID == b.StopOperationID && a.LastError == b.LastError
}

func (s *Service) runHealthFlight(id string, flight *healthFlight) {
	ctx, cancel := context.WithTimeout(context.Background(), healthCollectTimeout)
	defer cancel()
	report, err := s.collectHealth(ctx, id)
	s.health.mu.Lock()
	if err == nil {
		s.health.reports[id] = report
	}
	delete(s.health.inflight, id)
	s.health.mu.Unlock()
	flight.report, flight.err = report, err
	close(flight.done)
}

// SampleHealth refreshes every Profile roughly once per interval with jitter,
// so entry-page and dashboard reads usually hit a fresh cache.
func (s *Service) SampleHealth(ctx context.Context, interval time.Duration, observe func(HealthReport)) {
	if interval <= 0 {
		return
	}
	for {
		jitter := time.Duration(float64(interval) * 0.1 * (float64(s.now().UnixNano()%1000)/500 - 1))
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval + jitter):
		}
		for _, id := range s.directory.ids() {
			report, err := s.Health(ctx, id, HealthOptions{})
			if err == nil && observe != nil {
				observe(report)
			}
			if ctx.Err() != nil {
				return
			}
		}
	}
}

func (s *Service) collectHealth(ctx context.Context, id string) (HealthReport, error) {
	definition, _ := s.directory.get(id)
	binding, found, err := s.store.Get(id)
	if err != nil {
		return HealthReport{}, err
	}
	upstream := found && binding.NetworkPolicyID != "" && binding.Status == state.StatusRunning
	observation, observeErr := s.runtime.ObserveHome(ctx, definition.HomeName, upstream)
	now := s.now()
	after, foundAfter, err := s.store.Get(id)
	if err != nil {
		return HealthReport{}, err
	}
	if foundAfter != found || !sameHealthJournal(after, binding) {
		return buildHealthReport(definition, after, foundAfter, nil, errBindingChanged, now), nil
	}
	var observed *sealskin.HomeHealth
	if observeErr == nil {
		observed = &observation
	}
	return buildHealthReport(definition, binding, found, observed, observeErr, now), nil
}

var errBindingChanged = errors.New("profile binding changed during the health observation")

type checkList struct {
	checks []HealthCheck
}

func (c *checkList) add(name string, status CheckStatus, required bool, code, message string) {
	c.checks = append(c.checks, HealthCheck{Name: name, Status: status, Required: required, Code: code, Message: message})
}

func (c *checkList) find(name string) *HealthCheck {
	for i := range c.checks {
		if c.checks[i].Name == name {
			return &c.checks[i]
		}
	}
	return nil
}

func overallStatus(checks []HealthCheck, offline bool) Overall {
	if offline {
		return OverallOffline
	}
	for _, check := range checks {
		if check.Required && check.Status == CheckFail {
			return OverallUnhealthy
		}
	}
	for _, check := range checks {
		if check.Required && check.Status == CheckUnknown {
			return OverallUnknown
		}
	}
	for _, check := range checks {
		if !check.Required && (check.Status == CheckFail || check.Status == CheckWarn || check.Status == CheckUnknown) {
			return OverallDegraded
		}
	}
	return OverallHealthy
}

func buildHealthReport(definition Definition, binding state.Binding, found bool, observed *sealskin.HomeHealth, observeErr error, now time.Time) HealthReport {
	report := HealthReport{Version: 1, ProfileID: definition.ID, CheckedAt: now, ExpiresAt: now.Add(HealthTTL),
		journalBinding: binding, hasBinding: found,
		Binding: HealthBinding{Status: state.StatusStopped, ApplicationID: definition.ApplicationID, HomeName: definition.HomeName}}
	if found {
		updated := binding.UpdatedAt
		report.Binding = HealthBinding{Status: binding.Status, OperationID: binding.OperationID, SessionID: binding.SessionID,
			ApplicationID: definition.ApplicationID, HomeName: definition.HomeName,
			NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256, UpdatedAt: &updated}
	}
	proxyRequired := found && binding.NetworkPolicyID != ""
	list := &checkList{}
	list.add("entry", CheckPass, true, "ADAPTER_OK", "固定入口服务正在响应")
	offline := false
	if observeErr != nil {
		code, message := "CONTROL_UNAVAILABLE", "SealSkin 控制面没有返回运行观测，无法判断实例状态"
		switch {
		case errors.Is(observeErr, errBindingChanged):
			code, message = "BINDING_CHANGED", "观测期间 Profile 绑定发生变化，本次结果作废"
		case errors.Is(observeErr, context.DeadlineExceeded):
			code, message = "CONTROL_TIMEOUT", "运行观测超时，尚不能判断实例状态"
		}
		list.add("control", CheckUnknown, true, code, message)
		for _, name := range []string{"session", "worker", "browser", "display"} {
			list.add(name, CheckUnknown, true, code, "缺少控制面观测")
		}
		list.add("proxy", CheckUnknown, proxyRequired, code, "缺少控制面观测")
		report.Checks = list.checks
		report.Overall = overallStatus(list.checks, false)
		report.Recovery = &Recovery{Code: code, Title: "健康观测暂不可用", Blocking: false, Steps: []string{
			"探测超时、报告过期或控制面不可用时不会自动重建浏览器",
			"稍后重试；持续出现时由运维执行 inspect-profile 核对 SealSkin 与 Docker 状态",
		}}
		return report
	}
	list.add("control", CheckPass, true, "CONTROL_OK", "SealSkin 控制面已返回运行观测")
	snapshot := observed.Runtime
	report.Runtime = summarizeRuntime(snapshot, observed)
	unknownAll := func(code, message string) {
		for _, name := range []string{"session", "worker", "browser", "display"} {
			list.add(name, CheckUnknown, true, code, message)
		}
		list.add("proxy", CheckUnknown, proxyRequired, code, message)
	}
	switch {
	case !found || binding.Status == state.StatusStopped || binding.Status == state.StatusFailed:
		if runtimeEmpty(snapshot) {
			offline = true
			for _, name := range []string{"session", "worker", "browser", "display", "proxy"} {
				list.add(name, CheckNotApplicable, false, "PROFILE_STOPPED", "Profile 已确认停止，没有运行实例")
			}
			report.Recovery = &Recovery{Code: "PROFILE_STOPPED", Title: "Profile 已停止", Blocking: false, Steps: []string{
				"打开固定入口会新建会话并继续使用同一 Home 中的数据",
			}}
		} else {
			unknownAll("RUNTIME_UNEXPECTED", "journal 显示已停止，但 Home 仍有记录、容器或网络资源")
			report.Recovery = &Recovery{Code: "RUNTIME_UNEXPECTED", Title: "运行资源与状态不一致", Blocking: false, Steps: []string{
				"入口不会自动重建；由运维执行 reconcile-profile 对账，必要时 stop-profile 清理后再打开入口",
			}}
		}
	case binding.Status == state.StatusStopping:
		unknownAll("PROFILE_STOPPING", "停止操作进行中，资源尚未确认全部消失")
		report.Recovery = &Recovery{Code: "PROFILE_STOPPING", Title: "正在停止", Blocking: false, Steps: []string{
			"等待停止完成；停止未确认时重复 stop-profile 或 reconcile-profile",
		}}
	case binding.Status == state.StatusLaunching:
		unknownAll("PROFILE_LAUNCHING", "启动操作尚未确认结果")
		report.Recovery = &Recovery{Code: "PROFILE_LAUNCHING", Title: "正在启动", Blocking: false, Steps: []string{
			"稍后刷新入口；启动结果未知时由运维执行 reconcile-profile",
		}}
	case binding.Status == state.StatusUnknown && strings.HasPrefix(binding.LastError, "dormant generation resume failed"):
		code := "RESUME_FAILED"
		if _, detail, ok := strings.Cut(binding.LastError, ": "); ok && detail != "" {
			code = detail
		}
		unknownAll(code, "重启后的按序恢复失败，浏览器容器保持停止，占用与会话记录保留")
		report.Recovery = &Recovery{Code: code, Title: "重启后恢复失败，浏览器未启动", Blocking: false, Steps: []string{
			"探测或规则失败时浏览器不会联网启动；修复上游代理或网络后重新打开入口，或由运维执行 resume-profile 重试",
			"持续失败时由运维 stop-profile 清理本代次后重新打开入口；Home 数据保留",
		}}
	case binding.Status == state.StatusUnknown:
		unknownAll("PROFILE_OWNERSHIP_UNKNOWN", "Profile 运行归属未知，需要运维恢复")
		report.Recovery = &Recovery{Code: "PROFILE_OWNERSHIP_UNKNOWN", Title: "需要运维恢复", Blocking: false, Steps: []string{
			"由运维执行 inspect-profile 与 reconcile-profile；确认后 stop-profile 再重新打开入口",
		}}
	default:
		if err := checkDefinition(definition, binding); err != nil {
			unknownAll("PROFILE_DEFINITION_DRIFT", "配置的 Home、应用或策略与活动绑定不一致")
		} else if err := validateOwnership(snapshot, definition, binding); err != nil {
			unknownAll("OWNERSHIP_UNPROVEN", "Home 上存在异属或不同代次的资源")
			report.Recovery = &Recovery{Code: "OWNERSHIP_UNPROVEN", Title: "需要运维对账", Blocking: false, Steps: []string{
				"由运维执行 inspect-profile 与 reconcile-profile，不要手动删除占用",
			}}
		} else {
			evaluateRunning(definition, binding, observed, list, &report)
		}
	}
	if definition.IdlePolicy.Enabled() && found && binding.Status == state.StatusRunning {
		switch {
		case report.Runtime.DisplayConnections < 0:
			list.add("idle", CheckUnknown, false, "IDLE_UNOBSERVED", "无法观测显示连接数，空闲计时不推进也不清除")
		case report.Runtime.DisplayConnections > 0:
			list.add("idle", CheckPass, false, "IDLE_CONNECTED", fmt.Sprintf("%d 个已认证显示连接", report.Runtime.DisplayConnections))
		case binding.IdleSince != nil:
			remaining := definition.IdlePolicy.Timeout() - now.Sub(*binding.IdleSince)
			if remaining < 0 {
				remaining = 0
			}
			list.add("idle", CheckWarn, false, "IDLE_COUNTING", fmt.Sprintf("没有显示连接，%s 后按可靠停止回收（重新连接即取消）", remaining.Round(time.Second)))
		default:
			list.add("idle", CheckWarn, false, "IDLE_DISCONNECTED", "没有显示连接，下次采样开始计时")
		}
	}
	if !offline && observed != nil {
		mergeCoherence(definition, binding, observed, list, &report, now)
	}
	report.Checks = list.checks
	report.Overall = overallStatus(list.checks, offline)
	if report.Recovery == nil {
		report.Recovery = selectRecovery(list, definition)
	}
	return report
}

func summarizeRuntime(snapshot sealskin.HomeRuntime, observed *sealskin.HomeHealth) HealthRuntime {
	result := HealthRuntime{Records: len(snapshot.Records), Workers: len(snapshot.Workers), Resources: len(snapshot.Resources), DisplayConnections: -1}
	for _, worker := range snapshot.Workers {
		if !worker.Recorded {
			result.Orphans++
		}
	}
	for _, resource := range snapshot.Resources {
		switch resource.Kind {
		case "reservation":
			result.NetworkPhase = resource.Status
		case "launch":
			result.LaunchPhase = resource.Status
		}
	}
	if observed != nil {
		if observed.ObservedAt > 0 {
			result.ObservedAt = time.Unix(0, int64(observed.ObservedAt*float64(time.Second))).UTC().Format(time.RFC3339)
		}
		if len(observed.Workers) == 1 {
			result.WorkerStatus, result.WorkerStartedAt = observed.Workers[0].Status, observed.Workers[0].StartedAt
			result.DisplayConnections = observed.Workers[0].DisplayConnections
		}
	}
	return result
}

func evaluateRunning(definition Definition, binding state.Binding, observed *sealskin.HomeHealth, list *checkList, report *HealthReport) {
	snapshot := observed.Runtime
	var record *sealskin.RuntimeRecord
	switch {
	case len(snapshot.Records) == 0:
		list.add("session", CheckFail, true, "SESSION_MISSING", "SealSkin 没有该代次的会话记录")
	case len(snapshot.Records) > 1:
		list.add("session", CheckUnknown, true, "SESSION_AMBIGUOUS", "Home 上有多条会话记录")
	default:
		record = &snapshot.Records[0]
		switch {
		case record.Phase == "stopping":
			list.add("session", CheckUnknown, true, "SESSION_STOPPING", "会话记录处于停止阶段")
		case record.Phase != "running":
			list.add("session", CheckUnknown, true, "SESSION_NOT_RUNNING", "会话记录阶段为 "+record.Phase)
		case binding.SessionID != "" && record.SessionID != binding.SessionID:
			list.add("session", CheckUnknown, true, "SESSION_MISMATCH", "会话记录与 journal 绑定的 Session 不一致")
		default:
			list.add("session", CheckPass, true, "SESSION_RUNNING", "会话记录存在且处于运行阶段")
		}
	}
	var worker *sealskin.RuntimeWorker
	var health *sealskin.WorkerHealth
	switch {
	case len(snapshot.Workers) == 0:
		list.add("worker", CheckFail, true, "WORKER_MISSING", "没有挂载该 Home 的浏览器容器")
	case len(snapshot.Workers) > 1:
		list.add("worker", CheckUnknown, true, "WORKER_MULTIPLE", "多个容器挂载同一 Home")
	default:
		worker = &snapshot.Workers[0]
		for i := range observed.Workers {
			if observed.Workers[i].InstanceID == worker.InstanceID {
				health = &observed.Workers[i]
			}
		}
		status := worker.Status
		if health != nil && health.Status != "" {
			status = health.Status
		}
		if status != "running" {
			if _, dormant := dormantRuntime(snapshot); dormant {
				list.add("worker", CheckFail, true, "WORKER_DORMANT", "浏览器容器已停止（例如 Docker 或主机重启后），会话记录与网络分配仍在，可按序恢复")
			} else {
				list.add("worker", CheckFail, true, "WORKER_NOT_RUNNING", "浏览器容器状态为 "+status)
			}
			worker = nil
		} else {
			list.add("worker", CheckPass, true, "WORKER_RUNNING", "浏览器容器正在运行")
		}
	}
	switch {
	case worker == nil || health == nil:
		list.add("browser", CheckUnknown, true, "BROWSER_UNOBSERVED", "Worker 未运行或未被观测，无法判断浏览器进程")
		list.add("display", CheckUnknown, true, "DISPLAY_UNOBSERVED", "Worker 未运行或未被观测，无法判断显示服务")
	case health.Processes.Error != "":
		list.add("browser", CheckUnknown, true, "BROWSER_UNOBSERVED", "无法读取容器进程表："+health.Processes.Error)
		list.add("display", CheckUnknown, true, "DISPLAY_UNOBSERVED", "无法读取容器进程表："+health.Processes.Error)
	default:
		processes := health.Processes
		switch {
		case processes.BrowserMain == 0:
			list.add("browser", CheckFail, true, "BROWSER_EXITED", "浏览器主进程已退出，桌面与会话仍在运行")
		case processes.BrowserMain > 1:
			list.add("browser", CheckWarn, true, "BROWSER_MULTIPLE", fmt.Sprintf("检测到 %d 个浏览器主进程", processes.BrowserMain))
		default:
			list.add("browser", CheckPass, true, "BROWSER_RUNNING", "浏览器主进程正在运行")
		}
		switch {
		case len(processes.DisplayServer) == 0:
			list.add("display", CheckFail, true, "DISPLAY_SERVER_MISSING", "没有显示服务进程（Xvfb/Xwayland/labwc）")
		case processes.Streamer == 0:
			list.add("display", CheckFail, true, "DISPLAY_STREAMER_MISSING", "没有 Selkies 串流进程")
		case health.Display.Status == "pass":
			list.add("display", CheckPass, true, "DISPLAY_READY", "显示服务进程存在，控制器可访问显示端口")
		case health.Display.Status == "fail":
			list.add("display", CheckFail, true, health.Display.Code, "控制器无法正常访问显示端口")
		default:
			list.add("display", CheckUnknown, true, health.Display.Code, "显示端口未被观测")
		}
		report.Environment = health.Environment
	}
	switch {
	case binding.NetworkPolicyID == "" && definition.NetworkPolicyID != "":
		list.add("proxy", CheckWarn, false, "PROXY_LEGACY_GENERATION",
			"当前代次在策略 "+definition.NetworkPolicyID+" 生效前启动，未受管理网络保护；停止后新建会话才采用该策略")
	case binding.NetworkPolicyID == "":
		list.add("proxy", CheckNotApplicable, false, "PROXY_NOT_CONFIGURED", "该 Profile 未配置受管理网络策略")
	default:
		network := observed.Network
		if network != nil && network.Mode == "direct" {
			report.NetworkMode = "direct"
			list.add("proxy", CheckNotApplicable, false, "DIRECT_NO_UPSTREAM", "此代次使用受管理 DIRECT，没有外部上游代理")
			evaluateDirectNetwork(network, binding, list)
			return
		}
		switch {
		case network == nil:
			list.add("proxy", CheckUnknown, true, "PROXY_UNOBSERVED", "没有该代次的网络占用观测")
		case network.Code != "":
			list.add("proxy", CheckUnknown, true, network.Code, "网络占用记录无法读取")
		case network.Guard.Container != "running":
			list.add("proxy", CheckFail, true, "PROXY_GUARD_NOT_RUNNING", "Guard 容器状态为 "+network.Guard.Container)
		case network.WorkerNamespace != nil && !*network.WorkerNamespace:
			list.add("proxy", CheckFail, true, "PROXY_NAMESPACE_CHANGED", "Worker 不再共享 Guard 的网络命名空间")
		case network.Relay.Status == "fail":
			list.add("proxy", CheckFail, true, network.Relay.Code, "Relay 容器状态为 "+network.Relay.Container+"，控制器无法完成 SOCKS5 握手")
		case network.Relay.Status != "pass":
			list.add("proxy", CheckUnknown, true, network.Relay.Code, "Relay 未被观测")
		case network.Upstream == nil:
			list.add("proxy", CheckPass, true, "PROXY_RELAY_OK", "Relay 接受连接；本次未探测上游")
		case network.Upstream.Status == "pass":
			list.add("proxy", CheckPass, true, "PROXY_OK", fmt.Sprintf("经 Relay 到探测地址的 HTTPS 请求成功（%d ms）", network.Upstream.LatencyMS))
		case network.Upstream.Status == "fail":
			list.add("proxy", CheckFail, true, network.Upstream.Code, "经 Relay 的上游探测失败")
		default:
			list.add("proxy", CheckUnknown, true, network.Upstream.Code, "上游探测超时或探测端点异常，不能据此判定代理失效")
		}
	}
}

func evaluateDirectNetwork(network *sealskin.NetworkHealth, binding state.Binding, list *checkList) {
	switch {
	case network.PolicyID != binding.NetworkPolicyID || network.PolicySHA256 != binding.NetworkPolicySHA256:
		list.add("egress", CheckUnknown, true, "DIRECT_BINDING_CHANGED", "出站观测不属于当前策略修订")
	case network.Code != "":
		list.add("egress", CheckUnknown, true, network.Code, "DIRECT 配置或主机地址证据不可用，不能确认出站状态")
	case network.EnforcementVersion != 1:
		list.add("egress", CheckUnknown, true, "DIRECT_ENFORCEMENT_UNPROVEN", "无法确认 DIRECT 隔离能力")
	case network.Guard.Container != "running":
		list.add("egress", CheckFail, true, "DIRECT_GUARD_NOT_RUNNING", "DIRECT 网络隔离容器未运行")
	case network.WorkerNamespace == nil:
		list.add("egress", CheckUnknown, true, "DIRECT_NAMESPACE_UNOBSERVED", "未观测到浏览器的受限网络")
	case !*network.WorkerNamespace:
		list.add("egress", CheckFail, true, "DIRECT_NAMESPACE_CHANGED", "浏览器不再使用本代次的受限网络")
	case network.Relay.Status == "fail":
		list.add("egress", CheckFail, true, "DIRECT_GATEWAY_UNAVAILABLE", "DIRECT 网关不可用，网站出站受阻")
	case network.Relay.Status != "pass":
		list.add("egress", CheckUnknown, true, "DIRECT_GATEWAY_UNOBSERVED", "尚不能确认 DIRECT 网关状态")
	case network.Upstream == nil:
		list.add("egress", CheckUnknown, true, "DIRECT_PROBE_NOT_RUN", "网关接受连接，但本次尚未验证公网探测")
	case network.Upstream.Status == "pass":
		list.add("egress", CheckPass, true, "DIRECT_OK", "经专属 DIRECT 网关的 HTTPS 探测通过")
	case network.Upstream.Status == "fail":
		list.add("egress", CheckFail, true, "DIRECT_PROBE_FAILED", "经 DIRECT 网关的 HTTPS 探测失败")
	default:
		list.add("egress", CheckUnknown, true, "DIRECT_PROBE_UNKNOWN", "探测超时或端点异常，尚不能判断公网连通性")
	}
}

func selectRecovery(list *checkList, definition Definition) *Recovery {
	browser, display, proxy := list.find("browser"), list.find("display"), list.find("proxy")
	egress := list.find("egress")
	session, worker := list.find("session"), list.find("worker")
	switch {
	case egress != nil && egress.Status == CheckFail && (egress.Code == "DIRECT_GUARD_NOT_RUNNING" || egress.Code == "DIRECT_NAMESPACE_CHANGED"):
		return &Recovery{Code: egress.Code, Title: "DIRECT 网络隔离不可用", Blocking: true, Steps: []string{
			"由运维 stop-profile 清理本代次，确认资源全部消失后重新打开入口；Home 数据保留",
			"不要单独重启 Guard 去接管仍存活的旧浏览器",
		}}
	case worker != nil && worker.Code == "WORKER_DORMANT":
		return &Recovery{Code: "WORKER_DORMANT", Title: "浏览器容器已停止，可恢复", Blocking: false, Steps: []string{
			"打开固定入口会先按序恢复本代次（Relay → Guard → 探测 → 浏览器），探测失败时不会联网启动",
			"也可由运维执行 resume-profile；恢复失败时保留占用，按提示 stop-profile 后重新打开入口",
		}}
	case proxy != nil && proxy.Status == CheckFail && (proxy.Code == "PROXY_GUARD_NOT_RUNNING" || proxy.Code == "PROXY_NAMESPACE_CHANGED"):
		// A lost Guard also takes the display path down; name the cause, not the symptom.
		return &Recovery{Code: proxy.Code, Title: "本代次的网络 Guard 已丢失，显示与代理都会中断", Blocking: true, Steps: []string{
			"不要单独重启 Guard 去接管仍存活的旧 Worker",
			"由运维执行 stop-profile 清理本代次，确认资源全部消失后重新打开入口；Home 数据保留",
		}}
	case browser != nil && browser.Status == CheckFail:
		return &Recovery{Code: "BROWSER_EXITED", Title: "浏览器已退出，远程桌面与会话仍在运行", Blocking: true, Steps: []string{
			"点击「继续进入会话」回到远程桌面；只刷新入口会回到空桌面",
			"在远程桌面空白处点右键，选择 FireFox 重新打开浏览器（Mac 触控板可双指点按）",
			"需要找回标签页时，在 Firefox 中使用 History → Restore Previous Session",
		}}
	case display != nil && display.Status == CheckFail:
		return &Recovery{Code: display.Code, Title: "显示通道不可用", Blocking: true, Steps: []string{
			"重新加载 Trilium 中的页面；若仍无法显示，由运维执行 inspect-profile 核对 Worker",
			"不要删除 Home 或手动重置状态；必要时由运维 stop-profile 后重新打开入口",
		}}
	case proxy != nil && proxy.Status == CheckFail:
		return &Recovery{Code: proxy.Code, Title: "代理链路故障，网站访问会失败且不会直连", Blocking: true, Steps: []string{
			"浏览器与会话保留，不需要重开浏览器",
			"由运维检查上游代理与本代次的 Relay/Guard；Guard 丢失时先 stop-profile 清理本代次再重新打开入口",
		}}
	case egress != nil && egress.Status == CheckFail:
		return &Recovery{Code: egress.Code, Title: "DIRECT 网站出站不可用", Blocking: true, Steps: []string{
			"浏览器和会话保留，由运维核对专属网关、批准解析器与主机地址证据",
			"需要新建网络时先执行 stop-profile，确认清理完成后重新打开入口",
		}}
	case (worker != nil && worker.Status == CheckFail) || (session != nil && session.Status == CheckFail):
		return &Recovery{Code: firstFailure(list), Title: "运行实例已消失或异常", Blocking: false, Steps: []string{
			"入口不会自动重建；由运维执行 reconcile-profile 对账，确认后 stop-profile 再重新打开入口",
		}}
	}
	for _, check := range list.checks {
		if check.Required && check.Status == CheckUnknown {
			return &Recovery{Code: check.Code, Title: "状态尚不能判断", Blocking: false, Steps: []string{
				"探测超时、报告过期或观测不完整时不会自动重建；稍后重试或由运维 inspect-profile 核对",
			}}
		}
	}
	if proxy != nil && proxy.Status == CheckWarn {
		return &Recovery{Code: proxy.Code, Title: "旧代次未受管理网络保护", Blocking: false, Steps: []string{
			"当前会话继续可用；要采用策略 " + definition.NetworkPolicyID + "，需由运维 stop-profile 后重新打开入口",
		}}
	}
	return nil
}

func firstFailure(list *checkList) string {
	for _, check := range list.checks {
		if check.Status == CheckFail {
			return check.Code
		}
	}
	return "RUNTIME_UNHEALTHY"
}
