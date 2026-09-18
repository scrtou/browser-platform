package profile

import (
	"context"
	"errors"
	"fmt"

	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

var (
	ErrLifecycleDisabled  = errors.New("verified lifecycle is not enabled")
	ErrStopUnconfirmed    = errors.New("profile stop is pending; container removal has not been confirmed")
	ErrResumeFailed       = errors.New("dormant generation could not be resumed; Worker remains stopped and the Home stays reserved")
	ErrNotDormant         = errors.New("profile runtime is not a dormant generation")
	ErrRuntimeUnsupported = errors.New("SealSkin does not provide the required Worker runtime capabilities")
)

type RuntimeController interface {
	InspectHome(context.Context, string) (sealskin.HomeRuntime, error)
	StopHome(context.Context, string, sealskin.StopProfileRequest, string) error
	// ObserveHome is read-only; upstream requests a probe through the Relay.
	ObserveHome(context.Context, string, bool) (sealskin.HomeHealth, error)
	// ResumeHome restarts a dormant generation in order; it never creates.
	ResumeHome(context.Context, string, sealskin.StopProfileRequest, string) (sealskin.ResumeResult, error)
}

type Option func(*Service)

func WithLifecycle(runtime RuntimeController) Option {
	return func(s *Service) { s.runtime = runtime }
}

// LifecycleResult intentionally omits bootstrap URLs and access credentials.
type LifecycleResult struct {
	ProfileID    string         `json:"profile_id"`
	Status       state.Status   `json:"status"`
	SessionID    string         `json:"session_id,omitempty"`
	Records      int            `json:"records"`
	Workers      int            `json:"workers"`
	Orphans      int            `json:"orphans"`
	Resources    int            `json:"resources"`
	Relays       int            `json:"relays"`
	Guards       int            `json:"guards"`
	Networks     int            `json:"networks"`
	NetworkPhase string         `json:"network_phase,omitempty"`
	LaunchPhase  string         `json:"launch_phase,omitempty"`
	Capabilities map[string]int `json:"capabilities,omitempty"`
}

func runtimeEmpty(snapshot sealskin.HomeRuntime) bool {
	return len(snapshot.Records) == 0 && len(snapshot.Workers) == 0 && len(snapshot.Resources) == 0
}

func lifecycleResult(id string, binding state.Binding, found bool, snapshot sealskin.HomeRuntime) LifecycleResult {
	result := LifecycleResult{ProfileID: id, Status: binding.Status, SessionID: binding.SessionID,
		Records: len(snapshot.Records), Workers: len(snapshot.Workers), Resources: len(snapshot.Resources),
		Capabilities: snapshot.Capabilities()}
	if !found {
		result.Status = state.StatusStopped
		if !runtimeEmpty(snapshot) {
			result.Status = state.StatusUnknown
		}
	}
	for _, worker := range snapshot.Workers {
		if !worker.Recorded {
			result.Orphans++
		}
	}
	for _, resource := range snapshot.Resources {
		switch resource.Kind {
		case "reservation":
			result.NetworkPhase = resource.Status
		case "relay":
			result.Relays++
		case "guard":
			result.Guards++
		case "internal", "egress":
			result.Networks++
		case "launch":
			result.LaunchPhase = resource.Status
		}
	}
	return result
}

func checkDefinition(definition Definition, binding state.Binding) error {
	if binding.Status == state.StatusStopped || binding.Status == state.StatusFailed {
		return nil
	}
	if binding.HomeName != "" && binding.HomeName != definition.HomeName ||
		binding.ApplicationID != "" && binding.ApplicationID != definition.ApplicationID {
		return fmt.Errorf("%w: configured Home or application changed during an active operation", ErrOwnershipUnknown)
	}
	// Existing legacy sessions keep their original policy until stopped.
	if binding.NetworkPolicyID != "" && (binding.NetworkPolicyID != definition.NetworkPolicyID || binding.NetworkPolicySHA256 != definition.NetworkPolicySHA256) {
		return fmt.Errorf("%w: network policy changed during an active operation", ErrOwnershipUnknown)
	}
	return nil
}

func recordBelongs(record sealskin.RuntimeRecord, definition Definition, binding state.Binding) bool {
	if record.IsCollaboration || record.AppID != definition.ApplicationID || record.SessionID == "" || len(record.InstanceIDs) != 1 || record.InstanceIDs[0] == "" ||
		record.NetworkPolicyID != binding.NetworkPolicyID || record.NetworkPolicySHA256 != binding.NetworkPolicySHA256 {
		return false
	}
	if record.ProfileID != "" || record.OperationID != "" {
		return record.ProfileID == definition.ID && record.OperationID == binding.OperationID
	}
	return record.LaunchContext != nil && record.LaunchContext.Type == "url" &&
		record.LaunchContext.Value == binding.BootstrapURL &&
		(binding.SessionID == "" || binding.SessionID == record.SessionID)
}

// validateOwnership checks the entire Home, not just the requested session.
// A foreign mount or newer generation prevents any destructive operation.
func validateOwnership(snapshot sealskin.HomeRuntime, definition Definition, binding state.Binding) error {
	if binding.NetworkPolicyID != "" && !snapshot.HasNetworkInventory() {
		return fmt.Errorf("%w: network inventory capability is required", ErrOwnershipUnknown)
	}
	records := make(map[string]sealskin.RuntimeRecord)
	for _, record := range snapshot.Records {
		if !recordBelongs(record, definition, binding) {
			return ErrOwnershipUnknown
		}
		if _, duplicate := records[record.SessionID]; duplicate {
			return ErrOwnershipUnknown
		}
		records[record.SessionID] = record
	}
	seen := make(map[string]bool)
	for _, worker := range snapshot.Workers {
		if !worker.Owned || worker.AppID != definition.ApplicationID || worker.InstanceID == "" || seen[worker.InstanceID] ||
			worker.NetworkPolicyID != binding.NetworkPolicyID || worker.NetworkPolicySHA256 != binding.NetworkPolicySHA256 {
			return ErrOwnershipUnknown
		}
		seen[worker.InstanceID] = true
		if worker.ProfileID != "" || worker.OperationID != "" {
			if !worker.Managed || worker.ProfileID != definition.ID || worker.OperationID != binding.OperationID {
				return ErrOwnershipUnknown
			}
		} else {
			record, exists := records[worker.SessionID]
			if !exists || !worker.Recorded || !contains(record.InstanceIDs, worker.InstanceID) {
				return ErrOwnershipUnknown
			}
		}
	}
	resources := make(map[string]bool)
	for _, resource := range snapshot.Resources {
		if !resource.Owned || resource.ID == "" || resources[resource.Kind+":"+resource.ID] ||
			resource.ProfileID != definition.ID || resource.OperationID != binding.OperationID ||
			resource.AppID != definition.ApplicationID ||
			resource.PolicyID != binding.NetworkPolicyID || resource.PolicySHA256 != binding.NetworkPolicySHA256 {
			return ErrOwnershipUnknown
		}
		switch resource.Kind {
		case "reservation", "relay", "guard", "probe", "internal", "egress":
			if resource.PolicyID == "" {
				return ErrOwnershipUnknown
			}
		case "launch":
			// A create-before journal may belong to a plain (policy-less) launch.
		default:
			return ErrOwnershipUnknown
		}
		resources[resource.Kind+":"+resource.ID] = true
	}
	return nil
}

func runtimeStopping(snapshot sealskin.HomeRuntime) bool {
	for _, record := range snapshot.Records {
		if record.Phase == "stopping" {
			return true
		}
	}
	for _, resource := range snapshot.Resources {
		if resource.Kind == "reservation" && resource.Status == "stopping" {
			return true
		}
	}
	return false
}

// dormantRuntime recognizes the state a daemon or host restart leaves behind:
// one running-phase record, one owned stopped Worker and, for a managed
// generation, its complete network allocation. Nothing else qualifies.
func dormantRuntime(snapshot sealskin.HomeRuntime) (string, bool) {
	if len(snapshot.Records) != 1 || len(snapshot.Workers) != 1 || runtimeStopping(snapshot) {
		return "", false
	}
	record, worker := snapshot.Records[0], snapshot.Workers[0]
	if record.Phase != "running" || record.IsCollaboration || !worker.Owned || !worker.Recorded ||
		worker.SessionID != record.SessionID || !contains(record.InstanceIDs, worker.InstanceID) {
		return "", false
	}
	if worker.Status != "exited" && worker.Status != "created" {
		return "", false
	}
	kinds := map[string]int{}
	for _, resource := range snapshot.Resources {
		kinds[resource.Kind]++
	}
	if record.NetworkPolicyID == "" {
		if len(snapshot.Resources) != 0 {
			return "", false
		}
		return record.SessionID, true
	}
	for _, kind := range []string{"reservation", "internal", "egress", "relay", "guard"} {
		if kinds[kind] != 1 {
			return "", false
		}
	}
	if kinds["probe"] != 0 {
		return "", false
	}
	return record.SessionID, true
}

func liveRuntime(snapshot sealskin.HomeRuntime) (string, bool) {
	if len(snapshot.Records) != 1 || len(snapshot.Workers) != 1 || runtimeStopping(snapshot) {
		return "", false
	}
	record, worker := snapshot.Records[0], snapshot.Workers[0]
	if record.Phase != "running" || worker.Status != "running" || !worker.Recorded ||
		worker.SessionID != record.SessionID || !contains(record.InstanceIDs, worker.InstanceID) {
		return "", false
	}
	if record.NetworkPolicyID != "" {
		reservations := 0
		for _, resource := range snapshot.Resources {
			if resource.Kind == "reservation" {
				reservations++
			}
		}
		if reservations != 1 {
			return "", false
		}
	}
	return record.SessionID, true
}

func (s *Service) inspectRuntime(ctx context.Context, home string) (sealskin.HomeRuntime, error) {
	if s.runtime == nil {
		return sealskin.HomeRuntime{}, ErrLifecycleDisabled
	}
	snapshot, err := s.runtime.InspectHome(ctx, home)
	if err != nil {
		return snapshot, fmt.Errorf("inspect Profile runtime: %w", err)
	}
	if snapshot.Version != 1 || snapshot.HomeName != home || snapshot.Records == nil || snapshot.Workers == nil || !snapshot.ValidNetworkInventory() {
		return sealskin.HomeRuntime{}, errors.New("runtime inventory is incomplete; Profile remains reserved")
	}
	return snapshot, nil
}

func (s *Service) verifyBeforeEnsure(ctx context.Context, definition Definition, binding state.Binding, found bool) error {
	if found {
		if err := checkDefinition(definition, binding); err != nil {
			return err
		}
		if binding.Status == state.StatusStopping {
			return ErrOperationRunning
		}
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return err
	}
	if err := verifyRequiredCapabilities(definition, snapshot); err != nil {
		return err
	}
	if !found || binding.Status == state.StatusStopped || binding.Status == state.StatusFailed {
		if definition.NetworkPolicyID != "" && !snapshot.HasNetworkEnforcement() {
			return errors.New("SealSkin must support network enforcement before a policy-managed launch")
		}
		if !runtimeEmpty(snapshot) {
			return ErrOwnershipUnknown
		}
		return nil
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return err
	}
	if _, live := liveRuntime(snapshot); live {
		return nil
	}
	if _, dormant := dormantRuntime(snapshot); dormant {
		if _, err := s.resumeLocked(ctx, definition, binding); err != nil {
			return err
		}
		return nil
	}
	if err := s.mark(definition.ID, binding.OperationID, state.StatusUnknown, "runtime requires reconciliation"); err != nil {
		return err
	}
	return ErrOwnershipUnknown
}

// resumeLocked asks SealSkin to bring a dormant generation back in order and
// re-verifies the live inventory before the binding is trusted again. The
// caller holds the Profile lock. Failure leaves the journal as unknown with the
// stable code; no launch or stop is issued.
func (s *Service) resumeLocked(ctx context.Context, definition Definition, binding state.Binding) (sealskin.ResumeResult, error) {
	if len(definition.RequiredRuntimeCapabilities) != 0 {
		snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
		if err != nil {
			return sealskin.ResumeResult{}, err
		}
		if err := verifyRequiredCapabilities(definition, snapshot); err != nil {
			return sealskin.ResumeResult{}, err
		}
	}
	if binding.ResumeIdempotencyKey == "" {
		key, err := randomID()
		if err != nil {
			return sealskin.ResumeResult{}, err
		}
		if err := s.store.Update(definition.ID, func(current *state.Binding) (*state.Binding, error) {
			if current == nil || current.OperationID != binding.OperationID {
				return nil, ErrOwnershipUnknown
			}
			if current.ResumeIdempotencyKey == "" {
				current.ResumeIdempotencyKey = key
			}
			current.LastError = "dormant generation resume in progress"
			binding = *current
			return current, nil
		}); err != nil {
			return sealskin.ResumeResult{}, err
		}
	}
	request := sealskin.StopProfileRequest{ProfileID: definition.ID, OperationID: binding.OperationID,
		ApplicationID: definition.ApplicationID, SessionID: binding.SessionID, BootstrapURL: binding.BootstrapURL,
		NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256}
	result, resumeErr := s.runtime.ResumeHome(ctx, definition.HomeName, request, binding.ResumeIdempotencyKey)
	snapshot, inspectErr := s.inspectRuntime(ctx, definition.HomeName)
	if resumeErr == nil && inspectErr == nil {
		if err := validateOwnership(snapshot, definition, binding); err == nil {
			if sessionID, live := liveRuntime(snapshot); live && sessionID == result.SessionID {
				if err := s.bindRunning(definition.ID, binding.OperationID, sessionID); err != nil {
					return result, err
				}
				if err := s.verifySessionAccess(ctx, definition, sessionID); err != nil {
					return result, err
				}
				return result, nil
			}
		}
		resumeErr = &sealskin.APIError{StatusCode: 409, Detail: "RESUME_INVENTORY_MISMATCH"}
	}
	detail := "dormant generation resume failed"
	if resumeErr != nil {
		detail += ": " + resumeCode(resumeErr)
	} else if inspectErr != nil {
		detail += ": inventory unavailable after resume"
	}
	if err := s.mark(definition.ID, binding.OperationID, state.StatusUnknown, detail); err != nil {
		return result, err
	}
	return result, fmt.Errorf("%w: %v", ErrResumeFailed, errors.Join(resumeErr, inspectErr))
}

// resumeCode extracts the stable SealSkin code without any Docker detail.
func resumeCode(err error) string {
	var apiErr *sealskin.APIError
	if errors.As(err, &apiErr) && apiErr.Detail != "" && len(apiErr.Detail) <= 64 {
		return apiErr.Detail
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "RESUME_TIMEOUT"
	}
	return "RESUME_ERROR"
}

// Resume is the explicit operator entry: it resumes a dormant generation for
// a running/unknown binding without launching anything.
func (s *Service) Resume(ctx context.Context, id string) (LifecycleResult, error) {
	definition, ok := s.directory.get(id)
	if !ok {
		return LifecycleResult{}, ErrProfileNotFound
	}
	lock := s.profileLock(id)
	lock.Lock()
	defer lock.Unlock()
	binding, found, err := s.store.Get(id)
	if err != nil {
		return LifecycleResult{}, err
	}
	if err := checkDefinition(definition, binding); err != nil {
		return LifecycleResult{}, err
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return LifecycleResult{}, err
	}
	result := lifecycleResult(id, binding, found, snapshot)
	if !found || binding.Status == state.StatusStopped || binding.Status == state.StatusFailed || binding.Status == state.StatusStopping {
		return result, ErrNotDormant
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return result, err
	}
	if sessionID, live := liveRuntime(snapshot); live {
		if err := s.bindRunning(id, binding.OperationID, sessionID); err != nil {
			return result, err
		}
		if err := s.verifySessionAccess(ctx, definition, sessionID); err != nil {
			return result, err
		}
		result.Status, result.SessionID = state.StatusRunning, sessionID
		return result, nil
	}
	if _, dormant := dormantRuntime(snapshot); !dormant {
		return result, ErrNotDormant
	}
	resumed, err := s.resumeLocked(ctx, definition, binding)
	if err != nil {
		result.Status = state.StatusUnknown
		return result, err
	}
	remaining, inspectErr := s.inspectRuntime(ctx, definition.HomeName)
	if inspectErr == nil {
		result = lifecycleResult(id, binding, true, remaining)
	}
	result.Status, result.SessionID = state.StatusRunning, resumed.SessionID
	return result, nil
}

func (s *Service) verifyManagedLaunch(ctx context.Context, definition Definition, binding state.Binding, sessionID string, initialURL bool) error {
	if binding.NetworkPolicyID == "" && len(definition.RequiredRuntimeCapabilities) == 0 {
		return nil
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return err
	}
	if err := verifyRequiredCapabilities(definition, snapshot); err != nil {
		return err
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return err
	}
	if initialURL && snapshot.ProfileInitialURLVersion != 1 {
		return errors.New("SealSkin initial URL capability changed during launch")
	}
	if actual, live := liveRuntime(snapshot); !live || actual != sessionID {
		return ErrOwnershipUnknown
	}
	return nil
}

func verifyRequiredCapabilities(definition Definition, snapshot sealskin.HomeRuntime) error {
	actual := snapshot.Capabilities()
	for name, required := range definition.RequiredRuntimeCapabilities {
		if actual[name] != required {
			return ErrRuntimeUnsupported
		}
	}
	return nil
}

// Inspect is read-only and uses the same per-Profile lock as Ensure and Stop.
func (s *Service) Inspect(ctx context.Context, id string) (LifecycleResult, error) {
	definition, ok := s.directory.get(id)
	if !ok {
		return LifecycleResult{}, ErrProfileNotFound
	}
	lock := s.profileLock(id)
	lock.Lock()
	defer lock.Unlock()
	binding, found, err := s.store.Get(id)
	if err != nil {
		return LifecycleResult{}, err
	}
	if err := checkDefinition(definition, binding); err != nil {
		return LifecycleResult{}, err
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return LifecycleResult{}, err
	}
	return lifecycleResult(id, binding, found, snapshot), nil
}

// Stop records durable intent before requesting a stop and independently
// verifies its result. No timeout, HTTP success, or missing session record by
// itself is sufficient to release the Profile.
func (s *Service) Stop(ctx context.Context, id string) (LifecycleResult, error) {
	if _, ok := s.directory.get(id); !ok {
		return LifecycleResult{}, ErrProfileNotFound
	}
	lock := s.profileLock(id)
	lock.Lock()
	defer lock.Unlock()
	return s.stopLocked(ctx, id)
}

func (s *Service) stopLocked(ctx context.Context, id string) (LifecycleResult, error) {
	definition, _ := s.directory.get(id)
	binding, found, err := s.store.Get(id)
	if err != nil {
		return LifecycleResult{}, err
	}
	if err := checkDefinition(definition, binding); err != nil {
		return LifecycleResult{}, err
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return LifecycleResult{}, err
	}
	result := lifecycleResult(id, binding, found, snapshot)
	if !found {
		if runtimeEmpty(snapshot) {
			return result, nil
		}
		return result, ErrOwnershipUnknown
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return result, err
	}
	if runtimeEmpty(snapshot) {
		if binding.SessionID == "" && (binding.Status == state.StatusLaunching || binding.Status == state.StatusUnknown) && !snapshot.HasLaunchJournal() {
			// An unacknowledged launch without any discoverable worker is not
			// proof that a previously submitted create request never ran,
			// unless SealSkin journals every launch before Docker create.
			return result, ErrOwnershipUnknown
		}
		if err := s.markStopped(id, binding.OperationID); err != nil {
			return result, err
		}
		result.Status, result.SessionID = state.StatusStopped, ""
		return result, nil
	}
	stopOperation, err := randomID()
	if err != nil {
		return result, err
	}
	stopKey, err := randomID()
	if err != nil {
		return result, err
	}
	err = s.store.Update(id, func(current *state.Binding) (*state.Binding, error) {
		if current == nil || current.OperationID != binding.OperationID {
			return nil, ErrOwnershipUnknown
		}
		current.Status = state.StatusStopping
		if current.StopOperationID == "" {
			current.StopOperationID, current.StopIdempotencyKey = stopOperation, stopKey
		}
		if current.SessionID == "" && len(snapshot.Records) == 1 {
			current.SessionID = snapshot.Records[0].SessionID
		}
		current.LastError = ""
		binding = *current
		return current, nil
	})
	if err != nil {
		return result, err
	}
	request := sealskin.StopProfileRequest{ProfileID: id, OperationID: binding.OperationID,
		ApplicationID: definition.ApplicationID, SessionID: binding.SessionID, BootstrapURL: binding.BootstrapURL,
		NetworkPolicyID: binding.NetworkPolicyID, NetworkPolicySHA256: binding.NetworkPolicySHA256}
	stopErr := s.runtime.StopHome(ctx, definition.HomeName, request, binding.StopIdempotencyKey)
	remaining, inspectErr := s.inspectRuntime(ctx, definition.HomeName)
	if inspectErr == nil && (binding.NetworkPolicyID == "" || remaining.HasNetworkInventory()) && runtimeEmpty(remaining) {
		if err := s.markStopped(id, binding.OperationID); err != nil {
			return result, err
		}
		return LifecycleResult{ProfileID: id, Status: state.StatusStopped}, nil
	}
	if err := s.mark(id, binding.OperationID, state.StatusStopping, "stop result unconfirmed; retry or reconcile required"); err != nil {
		return result, err
	}
	result.Status = state.StatusStopping
	if inspectErr == nil {
		result = lifecycleResult(id, binding, true, remaining)
	}
	return result, errors.Join(ErrStopUnconfirmed, stopErr, inspectErr)
}

func (s *Service) markStopped(id, operation string) error {
	return s.store.Update(id, func(current *state.Binding) (*state.Binding, error) {
		if current == nil || current.OperationID != operation {
			return nil, ErrOwnershipUnknown
		}
		current.Status = state.StatusStopped
		current.SessionID = ""
		current.LastError = ""
		return current, nil
	})
}

// Reconcile resumes an already persisted stop intent. Otherwise it only
// reconciles ownership; a labeled orphan is quarantined until explicit Stop.
func (s *Service) Reconcile(ctx context.Context, id string) (LifecycleResult, error) {
	definition, ok := s.directory.get(id)
	if !ok {
		return LifecycleResult{}, ErrProfileNotFound
	}
	lock := s.profileLock(id)
	lock.Lock()
	defer lock.Unlock()
	binding, found, err := s.store.Get(id)
	if err != nil {
		return LifecycleResult{}, err
	}
	if err := checkDefinition(definition, binding); err != nil {
		return LifecycleResult{}, err
	}
	if found && binding.Status == state.StatusStopping {
		return s.stopLocked(ctx, id)
	}
	snapshot, err := s.inspectRuntime(ctx, definition.HomeName)
	if err != nil {
		return LifecycleResult{}, err
	}
	result := lifecycleResult(id, binding, found, snapshot)
	if !found {
		if runtimeEmpty(snapshot) {
			return result, nil
		}
		return result, ErrOwnershipUnknown
	}
	if err := validateOwnership(snapshot, definition, binding); err != nil {
		return result, err
	}
	if runtimeStopping(snapshot) {
		// A direct SealSkin stop can remove its Session record before failing
		// to remove the Relay. The durable network reservation resumes it.
		return s.stopLocked(ctx, id)
	}
	if sessionID, live := liveRuntime(snapshot); live {
		if binding.Status == state.StatusStopped || binding.Status == state.StatusFailed {
			return result, ErrOwnershipUnknown
		}
		if err := s.bindRunning(id, binding.OperationID, sessionID); err != nil {
			return result, err
		}
		result.Status, result.SessionID = state.StatusRunning, sessionID
		return result, nil
	}
	if _, dormant := dormantRuntime(snapshot); dormant && binding.Status != state.StatusStopped && binding.Status != state.StatusFailed {
		resumed, err := s.resumeLocked(ctx, definition, binding)
		if err != nil {
			result.Status = state.StatusUnknown
			return result, err
		}
		if remaining, inspectErr := s.inspectRuntime(ctx, definition.HomeName); inspectErr == nil {
			result = lifecycleResult(id, binding, true, remaining)
		}
		result.Status, result.SessionID = state.StatusRunning, resumed.SessionID
		return result, nil
	}
	if runtimeEmpty(snapshot) && (binding.SessionID != "" || binding.Status == state.StatusStopped || binding.Status == state.StatusFailed || snapshot.HasLaunchJournal()) {
		// With a create-before journal, an empty inventory proves that no create
		// was started for this Home; the ambiguous launch is settled as stopped.
		if err := s.markStopped(id, binding.OperationID); err != nil {
			return result, err
		}
		result.Status, result.SessionID = state.StatusStopped, ""
		return result, nil
	}
	if err := s.mark(id, binding.OperationID, state.StatusUnknown, "runtime requires recovery; no replacement was launched"); err != nil {
		return result, err
	}
	result.Status = state.StatusUnknown
	return result, ErrOwnershipUnknown
}
