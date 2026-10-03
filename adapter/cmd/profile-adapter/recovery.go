package main

import (
	"context"
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
		result, err := profiles.Reconcile(recoverCtx, id)
		cancel()
		if err != nil {
			logger.Warn("profile still requires recovery", "profile", id, "error", err)
		} else {
			logger.Info("profile runtime reconciled", "profile", id, "status", result.Status)
		}
	}
}
