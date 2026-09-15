package profile

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"syscall"
	"time"

	"browser-platform/adapter/internal/state"
)

// ErrCapacity means a new launch was refused before any reservation was made.
var ErrCapacity = errors.New("capacity threshold reached; no launch was started")

// CapacityError carries the stable code for the entry and the control socket.
type CapacityError struct {
	Code   string
	Detail string
}

func (e *CapacityError) Error() string { return e.Code + ": " + e.Detail }
func (e *CapacityError) Unwrap() error { return ErrCapacity }

func freeDiskMiB(path string) (int64, error) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return 0, err
	}
	return int64(stat.Bavail) * int64(stat.Bsize) / (1 << 20), nil
}

// checkCapacity runs under the Profile lock before prepareLaunch. It never
// touches SealSkin and never changes the journal; it only refuses.
func (s *Service) checkCapacity(profileID string) error {
	limits := s.limits
	if limits.MaxActiveProfiles > 0 {
		all, err := s.store.All()
		if err != nil {
			return err
		}
		active := 0
		for id, binding := range all {
			if id == profileID {
				continue
			}
			switch binding.Status {
			case state.StatusStopped, state.StatusFailed:
			default:
				active++
			}
		}
		if active >= limits.MaxActiveProfiles {
			return &CapacityError{Code: "CAPACITY_ACTIVE_PROFILES", Detail: fmt.Sprintf("%d active Profiles reach the limit of %d", active, limits.MaxActiveProfiles)}
		}
	}
	if limits.MaxConcurrentLaunch > 0 && int(s.launching) >= limits.MaxConcurrentLaunch {
		return &CapacityError{Code: "CAPACITY_CONCURRENT_LAUNCHES", Detail: fmt.Sprintf("%d launches in flight reach the limit of %d", s.launching, limits.MaxConcurrentLaunch)}
	}
	if limits.MinFreeDiskMiB > 0 {
		path := limits.StoragePath
		if path == "" {
			path = "/"
		}
		free, err := limits.freeDiskMiB(path)
		if err != nil {
			return &CapacityError{Code: "CAPACITY_DISK_UNKNOWN", Detail: "free disk space could not be measured"}
		}
		if free < int64(limits.MinFreeDiskMiB) {
			return &CapacityError{Code: "CAPACITY_DISK", Detail: fmt.Sprintf("%d MiB free is below the minimum of %d MiB", free, limits.MinFreeDiskMiB)}
		}
	}
	return nil
}

// IdleDecision reports what one idle evaluation did.
type IdleDecision struct {
	ProfileID string        `json:"profile_id"`
	Action    string        `json:"action"` // off, unobserved, connected, counting, reclaimed, reclaim_pending, skipped
	Remaining time.Duration `json:"remaining"`
	Detail    string        `json:"detail,omitempty"`
}

// ApplyIdle evaluates the disconnected idle policy against one fresh health
// report. Only a fresh report bound to the current running operation advances
// or clears the countdown; unknown observations do neither (H05). Reclaim
// uses the verified Stop path and never releases anything by time alone.
func (s *Service) ApplyIdle(ctx context.Context, report HealthReport, logger *slog.Logger) IdleDecision {
	definition, ok := s.profiles[report.ProfileID]
	decision := IdleDecision{ProfileID: report.ProfileID, Action: "off"}
	if !ok || !definition.IdlePolicy.Enabled() {
		return decision
	}
	binding, found, err := s.store.Get(report.ProfileID)
	if err != nil || !found || binding.Status != state.StatusRunning || binding.OperationID != report.Binding.OperationID {
		decision.Action = "skipped"
		return decision
	}
	if report.Stale || report.Overall == OverallUnknown || report.Runtime.DisplayConnections < 0 {
		decision.Action = "unobserved"
		return decision
	}
	if worker := findCheck(report, "worker"); worker == nil || worker.Status != CheckPass {
		decision.Action = "unobserved"
		return decision
	}
	now := s.now()
	if report.Runtime.DisplayConnections > 0 {
		if binding.IdleSince != nil {
			_ = s.store.Update(report.ProfileID, func(current *state.Binding) (*state.Binding, error) {
				if current == nil || current.OperationID != binding.OperationID {
					return nil, errors.New("binding changed")
				}
				current.IdleSince = nil
				return current, nil
			})
		}
		decision.Action = "connected"
		return decision
	}
	if binding.IdleSince == nil {
		if err := s.store.Update(report.ProfileID, func(current *state.Binding) (*state.Binding, error) {
			if current == nil || current.OperationID != binding.OperationID || current.Status != state.StatusRunning {
				return nil, errors.New("binding changed")
			}
			if current.IdleSince == nil {
				stamp := now
				current.IdleSince = &stamp
			}
			return current, nil
		}); err != nil {
			decision.Action = "skipped"
			return decision
		}
		decision.Action, decision.Remaining = "counting", definition.IdlePolicy.Timeout()
		return decision
	}
	remaining := definition.IdlePolicy.Timeout() - now.Sub(*binding.IdleSince)
	if remaining > 0 {
		decision.Action, decision.Remaining = "counting", remaining
		return decision
	}
	// The countdown has expired on a possibly cached report. Reclaim only on a
	// forced fresh observation (at most HealthMinInterval old); a throttled or
	// failed refresh defers the decision to the next sample.
	// A throttled refresh still returns the last report, which is then at most
	// HealthMinInterval old; that is fresh enough for this decision.
	fresh, err := s.Health(ctx, report.ProfileID, HealthOptions{Force: true, Wait: 60 * time.Second})
	if (err != nil && !errors.Is(err, ErrHealthThrottled)) || fresh.Stale || fresh.Overall == OverallUnknown ||
		fresh.Runtime.DisplayConnections < 0 || fresh.Binding.OperationID != binding.OperationID {
		decision.Action, decision.Remaining = "counting", 0
		return decision
	}
	if fresh.Runtime.DisplayConnections > 0 {
		_ = s.store.Update(report.ProfileID, func(current *state.Binding) (*state.Binding, error) {
			if current == nil || current.OperationID != binding.OperationID {
				return nil, errors.New("binding changed")
			}
			current.IdleSince = nil
			return current, nil
		})
		decision.Action = "connected"
		return decision
	}
	result, stopErr := s.Stop(ctx, report.ProfileID)
	if s.stopHook != nil {
		s.stopHook(report.ProfileID)
	}
	if stopErr != nil {
		decision.Action, decision.Detail = "reclaim_pending", result.Status.String()
		if logger != nil {
			logger.Warn("idle reclaim stop unconfirmed; will retry", "profile", report.ProfileID, "status", result.Status)
		}
		return decision
	}
	decision.Action = "reclaimed"
	if logger != nil {
		logger.Info("idle reclaim completed after verified stop", "profile", report.ProfileID, "idle_since", binding.IdleSince.UTC().Format(time.RFC3339))
	}
	return decision
}

func findCheck(report HealthReport, name string) *HealthCheck {
	for i := range report.Checks {
		if report.Checks[i].Name == name {
			return &report.Checks[i]
		}
	}
	return nil
}
