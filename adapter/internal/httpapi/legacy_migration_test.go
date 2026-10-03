package httpapi

import (
	"context"
	"strconv"
	"strings"

	"browser-platform/adapter/internal/profile"
)

type fakeLegacyMigrator struct {
	*fakeProfiles
	calls []string
}

func (f *fakeLegacyMigrator) LegacyMigration(id string) (profile.LegacyMigrationSummary, bool) {
	return profile.LegacyMigrationSummary{ID: "work-direct", Revision: 4}, id == "work"
}

func (f *fakeLegacyMigrator) MigrateLegacyNetwork(_ context.Context, id string, revision int, migration, actor, key string) (profile.Record, error) {
	f.calls = append(f.calls, strings.Join([]string{id, strconv.Itoa(revision), migration, actor, key}, "/"))
	return profile.Record{}, nil
}

func (f *fakeLegacyMigrator) RollbackLegacyNetwork(ctx context.Context, id string, revision int, migration, actor, key string) (profile.Record, error) {
	return f.MigrateLegacyNetwork(ctx, id, revision, "rollback-"+migration, actor, key)
}
