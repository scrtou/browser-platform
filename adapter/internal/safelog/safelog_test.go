package safelog

import (
	"bytes"
	"errors"
	"log/slog"
	"strings"
	"testing"
)

type untrustedValue struct{ called *bool }

func (v untrustedValue) LogValue() slog.Value {
	*v.called = true
	return slog.StringValue("synthetic-sensitive-value")
}

func TestFinalHandlerSuppressesMessagesErrorsObjectsAndNestedValues(t *testing.T) {
	var output bytes.Buffer
	logger := Logger(slog.New(slog.NewJSONHandler(&output, nil)))
	marker := "synthetic-sensitive-value"
	called := false
	logger.Error(marker, "error", errors.New(marker), "cookie", marker, "metadata", map[string]string{"key": marker})
	logger.With("error", marker).WithGroup(marker).Error("profile entry failed", "error", untrustedValue{&called})
	logger.Info("profile entry failed", "profile", "personal", "code", "DISPLAY_UNAVAILABLE", "status", 503,
		"details", slog.GroupValue(slog.Any("error", errors.New(marker)), slog.String("password", marker)))
	logger.Error("profile command failed", "action", "resume", "profile", "personal",
		"error_code", "PROFILE_NOT_DORMANT", "error", errors.New(marker))
	_, _ = (ServerErrors{Logger: logger}).Write([]byte("http: panic serving " + marker))
	if strings.Contains(output.String(), marker) || called {
		t.Fatal("untrusted data or LogValuer reached output")
	}
	for _, required := range []string{"personal", "DISPLAY_UNAVAILABLE", "503", "HTTP_SERVER_ERROR", "PROFILE_NOT_DORMANT", "resume", "error_type"} {
		if !strings.Contains(output.String(), required) {
			t.Fatalf("audit metadata missing: %s", required)
		}
	}
}
