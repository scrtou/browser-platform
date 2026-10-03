package profile

import (
	"browser-platform/adapter/internal/sealskin"
	"context"
	"errors"
	"testing"
)

type recordingArchiver struct {
	requests []sealskin.ArchiveHomeRequest
	keys     []string
	fail     bool
}

func (a *recordingArchiver) ArchiveHomeDirectory(_ context.Context, _ string, request sealskin.ArchiveHomeRequest, key string) error {
	a.requests = append(a.requests, request)
	a.keys = append(a.keys, key)
	if request.EnvironmentArtifactID == "" {
		return errors.New("archive requires a recorded ID or explicit unrecorded marker")
	}
	if a.fail {
		return errors.New("archive temporarily unavailable")
	}
	return nil
}

func TestLegacyArchivePreservesUnknownMetadataAndRetryIdentity(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := managementService(t, admin)
	fake.snapshot.HomeName = "existing-home"
	archive := &recordingArchiver{fail: true}
	service.homeArchiver = archive
	if err := service.DeleteBrowser(context.Background(), "existing", "root", "legacy-delete"); err == nil {
		t.Fatal("archive failure ignored")
	}
	record, _ := service.record("existing")
	if record.Status != RecordDeleting || record.EnvironmentArtifactID != "" || admin.deleteCalls != 0 {
		t.Fatal("failed archive changed legacy definition or deleted app")
	}
	archive.fail = false
	if err := service.DeleteBrowser(context.Background(), "existing", "root", "legacy-delete"); err != nil {
		t.Fatal(err)
	}
	if service.KnownProfile("existing") || len(archive.requests) != 2 || archive.requests[0] != archive.requests[1] || archive.keys[0] != archive.keys[1] {
		t.Fatal("legacy retry identity changed")
	}
	request := archive.requests[1]
	if request.EnvironmentArtifactID != "legacy-unrecorded" || request.ApplicationID != "existing-app" || request.ProfileID != "existing" || request.Actor != "root" {
		t.Fatalf("legacy provenance lost: %+v", request)
	}
}

func TestRecordedArchiveKeepsAcceptedArtifactID(t *testing.T) {
	admin := &managementAdmin{}
	service, fake := managementService(t, admin)
	record, err := service.CreateBrowser(context.Background(), createRequest(), "root", "recorded-create")
	if err != nil {
		t.Fatal(err)
	}
	fake.snapshot.HomeName = record.HomeName
	archive := &recordingArchiver{}
	service.homeArchiver = archive
	if err := service.DeleteBrowser(context.Background(), record.ID, "root", "recorded-delete"); err != nil {
		t.Fatal(err)
	}
	if len(archive.requests) != 1 || archive.requests[0].EnvironmentArtifactID != record.EnvironmentArtifactID {
		t.Fatal("recorded artifact replaced")
	}
}
