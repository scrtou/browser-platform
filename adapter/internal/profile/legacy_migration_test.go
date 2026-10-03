package profile

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"browser-platform/adapter/internal/sealskin"
)

type migrationAdmin struct {
	*managementAdmin
	app             map[string]any
	lostReply       bool
	driftAfterWrite bool
}

func (a *migrationAdmin) InstalledAppDefinition(context.Context, string) (map[string]any, error) {
	encoded, _ := json.Marshal(a.app)
	var copy map[string]any
	_ = json.Unmarshal(encoded, &copy)
	return copy, nil
}

func (a *migrationAdmin) ReplaceInstalledApp(ctx context.Context, id string, app map[string]any, key string) error {
	if err := a.managementAdmin.ReplaceInstalledApp(ctx, id, app, key); err != nil {
		return err
	}
	a.app = app
	if a.driftAfterWrite {
		a.app["name"] = "unexpected"
	}
	if a.lostReply {
		return errors.New("response lost after durable PUT")
	}
	return nil
}

func migrationFixture(t *testing.T) (*Service, *lifecycleFake, *migrationAdmin, LegacyNetworkMigration) {
	t.Helper()
	a := &migrationAdmin{managementAdmin: &managementAdmin{}}
	s, fake := managementService(t, a.managementAdmin)
	s.admin = a
	s.directTemplate = &DirectTemplate{Owner: "profile-adapter", RelayImage: "sha256:" + strings.Repeat("d", 64),
		ProbeImage: "sha256:" + strings.Repeat("e", 64), ApprovedResolverID: "qa-dns", ApprovedResolverIP: "1.1.1.1", ProbeURL: "https://probe.example/"}
	s.directory.mu.Lock()
	r := s.directory.records["existing"]
	r.Disabled, r.WaylandMode = true, true
	r.RequiredRuntimeCapabilities = map[string]int{"browser_shutdown_version": 1, "session_auth_version": 1}
	s.directory.records[r.ID] = r
	if err := s.directory.writeLocked(); err != nil {
		t.Fatal(err)
	}
	s.directory.mu.Unlock()
	fake.snapshot.HomeName = r.HomeName
	fake.snapshot.NetworkDirectVersion = 1
	fake.snapshot.BrowserShutdownVersion, fake.snapshot.SessionAuthVersion = 1, 1
	a.app = map[string]any{"id": r.ApplicationID, "name": "Legacy Work", "home_directories": true,
		"provider_config": map[string]any{"image": "sha256:" + strings.Repeat("a", 64), "env": []any{map[string]any{"name": "KEEP", "value": "same"}}, "docker_overrides": map[string]any{"labels": map[string]any{"qa": "retained"}}}}
	plan := LegacyNetworkMigration{ID: "work-direct-r1", Status: "accepted", SourceRevision: r.Revision, SourceDefinition: r.Definition,
		SourceApplication: a.app, TargetImage: "sha256:" + strings.Repeat("b", 64), AcceptanceSHA256: strings.Repeat("c", 64), BackupSHA256: strings.Repeat("d", 64), RestoreSHA256: strings.Repeat("e", 64)}
	s.legacyMigrationCatalog = filepath.Join(t.TempDir(), "migrations.json")
	writeMigrationCatalog(t, s, plan)
	return s, fake, a, plan
}

func writeMigrationCatalog(t *testing.T, s *Service, plan LegacyNetworkMigration) {
	t.Helper()
	data, err := json.Marshal(map[string]any{"version": 1, "migrations": []LegacyNetworkMigration{plan}})
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(s.legacyMigrationCatalog, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func migrate(s *Service, p LegacyNetworkMigration) (Record, error) {
	return s.MigrateLegacyNetwork(context.Background(), p.SourceDefinition.ID, p.SourceRevision, p.ID, "owner", "migration-1")
}

func TestLegacyMigrationPreservesBrowserHomeAndReplaysWithoutMutation(t *testing.T) {
	s, f, a, p := migrationFixture(t)
	result, err := migrate(s, p)
	if err != nil {
		t.Fatal(err)
	}
	if result.NetworkMode != "direct" || !result.Disabled || !result.WaylandMode || result.HomeName != p.SourceDefinition.HomeName ||
		result.ApplicationID != p.SourceDefinition.ApplicationID || result.EnvironmentArtifactID != "" || result.BrowserTemplateID != "" || result.PendingMigration != nil || result.LastMigration == nil {
		t.Fatalf("bad migration: %+v", result)
	}
	if migrationDigest(a.app) != migrationDigest(migrationApplication(p, *result.LastMigration)) {
		t.Fatal("application changed outside the approved image/policy")
	}
	if a.lastAppend.Policy["home_name"] != result.HomeName || a.lastAppend.Policy["profile_id"] != result.ID || a.lastAppend.Policy["application_id"] != result.ApplicationID {
		t.Fatal("policy is not scoped to original browser")
	}
	if f.stopCalls != 0 || f.launches != 0 || len(f.homes) != 0 || a.installCalls != 0 || a.deleteCalls != 0 || a.archiveCalls != 0 {
		t.Fatal("migration changed lifecycle or Home")
	}
	replayed, err := migrate(s, p)
	if err != nil || replayed.Revision != result.Revision || a.appendCalls != 1 || a.replaceCalls != 1 {
		t.Fatalf("non-idempotent replay: %v", err)
	}
	if summary, ok := s.LegacyMigration(result.ID); !ok || !summary.Rollback || summary.Revision != result.Revision {
		t.Fatal("completed migration has no explicit rollback")
	}
}

func TestLegacyMigrationRollbackAndInterruptedRetryPreserveHome(t *testing.T) {
	for _, interrupted := range []bool{false, true} {
		t.Run(fmt.Sprint(interrupted), func(t *testing.T) {
			s, f, a, p := migrationFixture(t)
			r, err := migrate(s, p)
			if err != nil {
				t.Fatal(err)
			}
			baseRevision := r.Revision
			a.lostReply = interrupted
			rollback := func() (Record, error) {
				return s.RollbackLegacyNetwork(context.Background(), r.ID, baseRevision, p.ID, "owner", "rollback-1")
			}
			if interrupted {
				if _, err := rollback(); err == nil {
					t.Fatal("lost rollback response ignored")
				}
				pending, _ := s.record(r.ID)
				if pending.Status != RecordMigrating {
					t.Fatal("rollback lost launch gate")
				}
				if err := s.directory.open(s.directoryPath); err != nil {
					t.Fatal(err)
				}
				a.lostReply = false
			}
			restored, err := rollback()
			if err != nil || migrationDigest(restored.Definition) != migrationDigest(p.SourceDefinition) || migrationDigest(a.app) != migrationDigest(p.SourceApplication) {
				t.Fatalf("rollback mismatch: %v", err)
			}
			calls := a.replaceCalls
			if _, err := rollback(); err != nil || a.replaceCalls != calls {
				t.Fatal("rollback replay mutated application")
			}
			if f.stopCalls != 0 || f.launches != 0 || a.archiveCalls != 0 || a.deleteCalls != 0 {
				t.Fatal("rollback changed Home/lifecycle")
			}
		})
	}
}

func TestLegacyMigrationRejectsUnapprovedOrBusyInputsWithoutMutation(t *testing.T) {
	for _, scenario := range []string{"running", "resource", "unknown", "capability", "profile-drift", "application-drift", "unaccepted", "missing-backup", "public-catalog", "symlink", "arbitrary-image", "wrong-actor-key", "revision"} {
		t.Run(scenario, func(t *testing.T) {
			s, f, a, p := migrationFixture(t)
			switch scenario {
			case "running":
				f.snapshot.Workers = []sealskin.RuntimeWorker{{InstanceID: strings.Repeat("1", 64), Status: "running"}}
			case "resource":
				f.snapshot.Resources = []sealskin.RuntimeResource{{Kind: "launch", ID: "pending"}}
			case "unknown":
				f.inspectErr = errors.New("controller unavailable")
			case "capability":
				f.snapshot.NetworkDirectVersion = 0
			case "profile-drift":
				r := s.directory.records["existing"]
				r.StartURL = "https://changed.example/"
				s.directory.records[r.ID] = r
			case "application-drift":
				a.app["name"] = "changed"
			case "unaccepted":
				p.Status = "draft"
				writeMigrationCatalog(t, s, p)
			case "missing-backup":
				p.BackupSHA256 = ""
				writeMigrationCatalog(t, s, p)
			case "public-catalog":
				if err := os.Chmod(s.legacyMigrationCatalog, 0o644); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				old := s.legacyMigrationCatalog
				s.legacyMigrationCatalog += ".link"
				if err := os.Symlink(old, s.legacyMigrationCatalog); err != nil {
					t.Fatal(err)
				}
			case "arbitrary-image":
				p.TargetImage = "firefox:latest"
				writeMigrationCatalog(t, s, p)
			case "wrong-actor-key":
				_, err := s.MigrateLegacyNetwork(context.Background(), "existing", 1, p.ID, "", "")
				if err == nil {
					t.Fatal("empty identity accepted")
				}
				return
			case "revision":
				p.SourceRevision++
			}
			before, _ := os.ReadFile(s.directoryPath)
			if _, err := migrate(s, p); err == nil {
				t.Fatal("invalid migration accepted")
			}
			after, _ := os.ReadFile(s.directoryPath)
			if string(before) != string(after) || a.appendCalls != 0 || a.replaceCalls != 0 || f.stopCalls != 0 || f.launches != 0 {
				t.Fatal("rejected request mutated state")
			}
		})
	}
}

func TestLegacyMigrationResumesDurablePendingAfterRestart(t *testing.T) {
	for _, stage := range []string{"append", "replace", "lost-reply"} {
		t.Run(stage, func(t *testing.T) {
			s, f, a, p := migrationFixture(t)
			switch stage {
			case "append":
				a.appendErr = errors.New("offline")
			case "replace":
				a.patchErr = errors.New("offline")
			case "lost-reply":
				a.lostReply = true
			}
			if _, err := migrate(s, p); err == nil {
				t.Fatal("failure ignored")
			}
			r, _ := s.record("existing")
			if r.Status != RecordMigrating || r.PendingMigration == nil {
				t.Fatal("no durable launch gate")
			}
			if err := s.DeleteBrowser(context.Background(), r.ID, "owner", "delete-pending"); err == nil || f.stopCalls != 0 || a.archiveCalls != 0 {
				t.Fatal("deletion discarded a pending migration")
			}
			if _, err := s.directory.status(r.ID, RecordReady, "owner"); err == nil {
				t.Fatal("generic status update cleared migration gate")
			}
			// Reload the actual file, as a new process would, without dropping pending.
			d, err := newDirectory([]Definition{p.SourceDefinition}, time.Now)
			if err != nil {
				t.Fatal(err)
			}
			if err = d.open(s.directoryPath); err != nil {
				t.Fatal(err)
			}
			s.directory = d
			if _, err = s.Ensure(context.Background(), r.ID); err == nil || f.launches != 0 || len(f.homes) != 0 {
				t.Fatal("pending migration allowed launch")
			}
			if _, err = s.MigrateLegacyNetwork(context.Background(), r.ID, p.SourceRevision, p.ID, "other", "migration-1"); err == nil {
				t.Fatal("different actor resumed")
			}
			if _, err = s.MigrateLegacyNetwork(context.Background(), r.ID, p.SourceRevision, p.ID, "owner", "different"); err == nil {
				t.Fatal("different key resumed")
			}
			changed := p
			changed.TargetImage = "sha256:" + strings.Repeat("f", 64)
			writeMigrationCatalog(t, s, changed)
			if _, err = migrate(s, p); err == nil {
				t.Fatal("changed approved plan resumed")
			}
			writeMigrationCatalog(t, s, p)
			a.appendErr, a.patchErr, a.lostReply = nil, nil, false
			calls := a.replaceCalls
			if _, err = migrate(s, p); err != nil {
				t.Fatal(err)
			}
			if stage == "lost-reply" && a.replaceCalls != calls {
				t.Fatal("lost PUT response caused redundant replacement")
			}
		})
	}
}

func TestLegacyMigrationRequiresReadbackBeforeDirectoryCommit(t *testing.T) {
	s, _, a, p := migrationFixture(t)
	a.driftAfterWrite = true
	if _, err := migrate(s, p); err == nil {
		t.Fatal("readback drift accepted")
	}
	r, _ := s.record("existing")
	if r.Status != RecordMigrating || r.NetworkMode != "" {
		t.Fatal("mismatched application committed")
	}
	if _, err := migrate(s, p); err == nil {
		t.Fatal("unexpected installed app overwritten during retry")
	}
}

// Wait for Ensure to reach profileLock while locksMu is held. This observes
// the actual blocking point instead of relying on sleeps or a production hook.
func waitForProfileLock(t *testing.T) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		stack := make([]byte, 1<<20)
		n := runtime.Stack(stack, true)
		if strings.Contains(string(stack[:n]), "(*Service).profileLock") {
			return
		}
		runtime.Gosched()
	}
	t.Fatal("Ensure did not reach profileLock")
}

func TestEnsureReadsDirectoryAfterWaitingForLifecycleLock(t *testing.T) {
	for _, status := range []string{"disabled", "pending", "changed-definition"} {
		t.Run(status, func(t *testing.T) {
			f := &fakeOrchestrator{}
			s, _ := newTestService(t, f)
			s.locksMu.Lock()
			done := make(chan error, 1)
			go func() { _, err := s.Ensure(context.Background(), "personal"); done <- err }()
			waitForProfileLock(t)
			s.directory.mu.Lock()
			r := s.directory.records["personal"]
			switch status {
			case "disabled":
				r.Disabled = true
			case "pending":
				r.Status = RecordUpdating
			case "changed-definition":
				r.ApplicationID = "new-app"
			}
			s.directory.records[r.ID] = r
			s.directory.mu.Unlock()
			s.locksMu.Unlock()
			err := <-done
			if status == "changed-definition" {
				if err != nil || len(f.sessions) != 1 || f.sessions[0].AppID != "new-app" {
					t.Fatalf("old definition used: %v", err)
				}
			} else if err == nil || f.launches != 0 || len(f.homes) != 0 {
				t.Fatal("stale launch passed directory gate")
			}
		})
	}
}
