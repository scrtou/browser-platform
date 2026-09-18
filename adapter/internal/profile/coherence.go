package profile

import (
	"context"
	"errors"
	"fmt"
	"time"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

var ErrCoherenceBlocked = errors.New("current generation has not passed runtime coherence checks")

type CoherenceController interface {
	CheckCoherence(context.Context, string, sealskin.StopProfileRequest, bool) (sealskin.CoherenceAccess, error)
}

func coherenceRecovery(code string) *Recovery {
	return &Recovery{Code: code, Title: "当前会话尚未通过一致性检查", Blocking: true, Steps: []string{
		"查看环境、出口和网络分项；观测缺失或过期时等待采样，或由运维执行一致性重查",
		"修复后复核当前代次；已确认网络绕过或出口变化锁定时，由运维停止后重新打开入口，Home 数据保留",
	}}
}

func mergeCoherence(definition Definition, binding state.Binding, observed *sealskin.HomeHealth, list *checkList, report *HealthReport, now time.Time) {
	value := observed.Coherence
	required := false
	for _, record := range observed.Runtime.Records {
		required = required || record.CoherenceRequired
	}
	if value == nil && !required {
		return
	}
	invalid := func(code string) {
		list.add("coherence", CheckUnknown, true, code, "缺少当前运行绑定的完整一致性报告")
		report.Recovery = coherenceRecovery(code)
	}
	if value == nil || !value.Enabled || value.Version != 1 {
		invalid("COHERENCE_UNOBSERVED")
		return
	}
	b := value.Binding
	if b.ProfileID != definition.ID || b.HomeName != definition.HomeName || b.ApplicationID != definition.ApplicationID ||
		b.OperationID != binding.OperationID || b.SessionID != binding.SessionID || b.PolicyID != binding.NetworkPolicyID ||
		b.PolicySHA256 != binding.NetworkPolicySHA256 || len(observed.Runtime.Workers) != 1 ||
		b.WorkerID != observed.Runtime.Workers[0].InstanceID || len(observed.Workers) != 1 || b.WorkerStartedAt != observed.Workers[0].StartedAt ||
		b.EnvironmentID != observed.Workers[0].Environment.ID || b.ArtifactSHA256 != observed.Workers[0].Environment.ArtifactSHA256 {
		invalid("COHERENCE_BINDING_CHANGED")
		return
	}
	copy := *value
	report.Coherence = &copy
	expires := time.Unix(0, int64(value.ExpiresAt*float64(time.Second)))
	if expires.Before(report.ExpiresAt) {
		report.ExpiresAt = expires
	}
	for _, row := range value.Checks {
		status := CheckStatus(row.Status)
		if status != CheckPass && status != CheckFail && status != CheckWarn && status != CheckUnknown && status != CheckNotApplicable {
			status = CheckUnknown
		}
		list.add("coherence_"+row.Name, status, row.Required, row.Code, row.Message)
	}
	if !value.Fresh(now) {
		invalid("COHERENCE_EXPIRED")
		return
	}
	if !value.Permits(now) {
		status := CheckUnknown
		if value.Overall == "unhealthy" || value.LeakDetected {
			status = CheckFail
		}
		list.add("coherence", status, true, value.Code, "当前一致性门槛未放行")
		report.Recovery = coherenceRecovery(value.Code)
		return
	}
	list.add("coherence", CheckPass, true, value.Code, "当前代次的必需观测通过，报告在有效期内")
}

// ProbeCoherence is an explicit private operation. It only samples the exact
// occupied generation; stopped or unowned Homes are never launched or resumed.
func (s *Service) ProbeCoherence(ctx context.Context, id string) (sealskin.CoherenceAccess, error) {
	definition, found := s.directory.get(id)
	if !found {
		return sealskin.CoherenceAccess{}, ErrProfileNotFound
	}
	controller, ok := s.runtime.(CoherenceController)
	if !ok {
		return sealskin.CoherenceAccess{}, ErrLifecycleDisabled
	}
	lock := s.profileLock(id)
	lock.Lock()
	defer lock.Unlock()
	binding, found, err := s.store.Get(id)
	if err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	if !found || binding.Status != state.StatusRunning || binding.SessionID == "" {
		return sealskin.CoherenceAccess{}, ErrCoherenceBlocked
	}
	if err := checkDefinition(definition, binding); err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	request := sealskin.StopProfileRequest{ProfileID: id, OperationID: binding.OperationID, SessionID: binding.SessionID,
		ApplicationID: definition.ApplicationID, BootstrapURL: binding.BootstrapURL, NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256}
	return controller.CheckCoherence(ctx, definition.HomeName, request, true)
}

func (s *Service) verifySessionAccess(ctx context.Context, definition Definition, sessionID string) error {
	if s.runtime == nil {
		return nil
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return err
	}
	required := false
	for _, record := range snapshot.Records {
		required = required || record.CoherenceRequired
	}
	if snapshot.CoherenceRuntimeVersion == 0 && !required {
		return nil
	}
	controller, ok := s.runtime.(CoherenceController)
	if snapshot.CoherenceRuntimeVersion != 1 || !ok {
		return ErrCoherenceBlocked
	}
	binding, found, err := s.store.Get(definition.ID)
	if err != nil {
		return err
	}
	if !found || binding.SessionID != sessionID {
		return ErrCoherenceBlocked
	}
	request := sealskin.StopProfileRequest{ProfileID: definition.ID, OperationID: binding.OperationID, SessionID: sessionID,
		ApplicationID: definition.ApplicationID, BootstrapURL: binding.BootstrapURL, NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256}
	result, err := controller.CheckCoherence(ctx, definition.HomeName, request, false)
	if err != nil {
		return fmt.Errorf("%w: observation unavailable", ErrCoherenceBlocked)
	}
	if result.Version != 1 || !result.Allowed || required && !result.Enabled || result.Enabled && (!result.Report.Permits(s.now()) ||
		result.Report.Binding.OperationID != binding.OperationID || result.Report.Binding.SessionID != sessionID ||
		result.Report.Binding.ApplicationID != definition.ApplicationID || result.Report.Binding.PolicyID != binding.NetworkPolicyID ||
		result.Report.Binding.PolicySHA256 != binding.NetworkPolicySHA256 || result.Report.Binding.ProfileID != definition.ID ||
		result.Report.Binding.HomeName != definition.HomeName || len(snapshot.Workers) != 1 ||
		result.Report.Binding.WorkerID != snapshot.Workers[0].InstanceID) {
		return ErrCoherenceBlocked
	}
	return nil
}
