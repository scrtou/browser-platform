package control

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"browser-platform/adapter/internal/sealskin"
)

type fakeCoherenceService struct {
	fakeService
	calls int
}

func (f *fakeCoherenceService) ProbeCoherence(_ context.Context, id string) (sealskin.CoherenceAccess, error) {
	f.calls++
	return sealskin.CoherenceAccess{Version: 1, Enabled: true, Allowed: false, Report: &sealskin.CoherenceReport{Code: "COHERENCE_UNKNOWN", Binding: sealskin.CoherenceBinding{ProfileID: id}}}, f.err
}

func TestCoherenceProbeIsExplicitAndPreservesBlockedReport(t *testing.T) {
	service := &fakeCoherenceService{}
	handler := Handler(service)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/profiles/personal/coherence", nil))
	if response.Code != http.StatusMethodNotAllowed || service.calls != 0 {
		t.Fatal("GET triggered coherence sampling")
	}
	path := filepath.Join(t.TempDir(), "control.sock")
	listener, err := Listen(path)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	server := &http.Server{Handler: handler}
	defer server.Close()
	go server.Serve(listener) //nolint:errcheck
	result, err := CoherenceCommand(context.Background(), path, "personal")
	if err != nil || result.Allowed || result.Report.Code != "COHERENCE_UNKNOWN" || result.Report.Binding.ProfileID != "personal" || service.calls != 1 {
		t.Fatalf("blocked result lost: %+v %v", result, err)
	}
	service.err = errors.New("secret-backend-detail")
	_, err = CoherenceCommand(context.Background(), path, "personal")
	if err == nil || strings.Contains(err.Error(), "secret-backend-detail") {
		t.Fatal("backend failure was exposed")
	}
}
