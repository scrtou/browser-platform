// Package safelog removes untrusted error values at the final log boundary.
package safelog

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
)

type handler struct{ next slog.Handler }

var messages = map[string]bool{
	"only one Profile command may be supplied": true, "profile adapter stopped": true,
	"profile state reset after operator inspection": true, "SealSkin control plane not ready before startup reconciliation": true,
	"profile still requires recovery": true, "profile runtime reconciled": true, "adapter control listener failed": true,
	"profile health changed": true, "idle policy": true, "graceful shutdown": true, "control shutdown": true,
	"profile adapter listening": true, "SealSkin control plane became ready": true,
	"idle reclaim stop unconfirmed; will retry": true, "idle reclaim completed after verified stop": true,
	"Session proxy unavailable": true, "access session revoked": true, "login denied": true, "login succeeded": true,
	"HTTP server failure": true, "profile health unavailable": true, "render browser entry": true,
	"reject SealSkin session URL": true, "display authorization unavailable": true, "entry pre-check skipped": true,
	"render recovery hint": true, "profile entry failed": true,
	"environment summary unavailable": true, "render environment list": true,
}

var identifier = regexp.MustCompile(`^[A-Za-z0-9_-]{1,128}$`)
var eventCode = regexp.MustCompile(`^[A-Z][A-Z0-9_]{0,95}$`)
var metadata = regexp.MustCompile(`^[A-Za-z0-9_.:+-]{1,128}$`)

func Logger(logger *slog.Logger) *slog.Logger {
	if logger == nil {
		logger = slog.Default()
	}
	if _, ok := logger.Handler().(*handler); ok {
		return logger
	}
	return slog.New(&handler{logger.Handler()})
}

func attribute(attr slog.Attr) slog.Attr {
	key := strings.ToLower(attr.Key)
	if err, ok := attr.Value.Any().(error); ok {
		return slog.String("error_type", fmt.Sprintf("%T", err))
	}
	if attr.Value.Kind() == slog.KindGroup && (key == "context" || key == "details") {
		values := attr.Value.Group()
		copy := make([]slog.Attr, len(values))
		for i, value := range values {
			copy[i] = attribute(value)
		}
		attr.Value = slog.GroupValue(copy...)
		return attr
	}
	// Unknown objects, LogValuers, errors already converted to strings, and
	// arbitrary attributes are never rendered. Only explicit audit metadata
	// is allowed; no raw request, URL, inspect object or exception details.
	if attr.Value.Kind() == slog.KindString {
		value := attr.Value.String()
		switch key {
		case "profile", "profile_id", "operation_id":
			if identifier.MatchString(value) {
				return attr
			}
		case "event", "code", "error_code":
			if eventCode.MatchString(value) {
				return attr
			}
		case "status", "overall", "action", "remaining", "idle_since", "address":
			if metadata.MatchString(value) {
				return attr
			}
		}
	}
	if (key == "attempts" || key == "status") && (attr.Value.Kind() == slog.KindInt64 || attr.Value.Kind() == slog.KindUint64) {
		return attr
	}
	return slog.String("redacted", "[redacted]")
}

func (h *handler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.next.Enabled(ctx, level)
}

func (h *handler) Handle(ctx context.Context, record slog.Record) error {
	message := record.Message
	if !messages[message] {
		message = "LOG_MESSAGE_SUPPRESSED"
	}
	clean := slog.NewRecord(record.Time, record.Level, message, record.PC)
	record.Attrs(func(attr slog.Attr) bool { clean.AddAttrs(attribute(attr)); return true })
	return h.next.Handle(ctx, clean)
}

func (h *handler) WithAttrs(attrs []slog.Attr) slog.Handler {
	clean := make([]slog.Attr, len(attrs))
	for i, attr := range attrs {
		clean[i] = attribute(attr)
	}
	return &handler{h.next.WithAttrs(clean)}
}

func (h *handler) WithGroup(name string) slog.Handler {
	if name != "context" && name != "details" {
		name = "redacted"
	}
	return &handler{h.next.WithGroup(name)}
}

// ServerErrors intentionally discards arbitrary net/http panic/parse text.
// A stable event records that a server error occurred without copying input.
type ServerErrors struct{ Logger *slog.Logger }

func (w ServerErrors) Write(raw []byte) (int, error) {
	Logger(w.Logger).Error("HTTP server failure", "event", "HTTP_SERVER_ERROR")
	return len(raw), nil
}
