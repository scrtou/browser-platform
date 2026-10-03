package main

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type startupProfiles interface {
	ProfileIDs() []string
	Reconcile(context.Context, string) (profile.LifecycleResult, error)
}

func reconcileAtStartup(ctx context.Context, profiles startupProfiles, logger *slog.Logger) {
	// The persisted directory is authoritative; configuration Profiles are only
	// import seeds and may be empty or stale after management mutations.
	for _, id := range profiles.ProfileIDs() {
		if ctx.Err() != nil {
			return
		}
		recoverCtx, cancel := context.WithTimeout(ctx, sealskin.LongOperationTimeout+15*time.Second)
		result, err := reconcileStartupProfile(recoverCtx, profiles, id, 2*time.Second)
		cancel()
		if err != nil {
			logger.Warn("profile still requires recovery", "profile", id, "error", err)
		} else {
			logger.Info("profile runtime reconciled", "profile", id, "status", result.Status)
		}
	}
}

func reconcileStartupProfile(ctx context.Context, profiles startupProfiles, id string, retryDelay time.Duration) (profile.LifecycleResult, error) {
	var result profile.LifecycleResult
	var err error
	for attempt := 0; attempt < 3; attempt++ {
		if ctx.Err() != nil {
			return result, ctx.Err()
		}
		result, err = profiles.Reconcile(ctx, id)
		if !errors.Is(err, profile.ErrResumeFailed) || attempt == 2 {
			return result, err
		}
		// Reconcile rechecks ownership and any intervening stop intent. Resume
		// keeps the persisted idempotency key and never creates a Worker.
		// Keep the same context: retries must not renew the recovery budget.
		timer := time.NewTimer(retryDelay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return result, ctx.Err()
		case <-timer.C:
		}
	}
	return result, err
}
