package profile

import (
	"context"

	"browser-platform/adapter/internal/state"
)

// CheckDisplaySession is a read-only authorization check. The SealSkin
// display proxy still validates its own cookie and actual Session record.
func (s *Service) CheckDisplaySession(ctx context.Context, id, sessionID string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	definition, ok := s.directory.get(id)
	if !ok {
		return ErrProfileNotFound
	}
	// Read the atomic journal without waiting for a long lifecycle call's
	// Profile lock. A persisted stopping/resume intent revokes display now.
	binding, found, err := s.store.Get(id)
	if err != nil || !found || binding.Status != state.StatusRunning || binding.SessionID != sessionID || sessionID == "" ||
		binding.HomeName != definition.HomeName || binding.ApplicationID != definition.ApplicationID || binding.StopOperationID != "" || binding.ResumeIdempotencyKey != "" {
		return ErrOwnershipUnknown
	}
	return checkDefinition(definition, binding)
}
