package httpapi

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type fakeProfiles struct {
	ensureCalls int
	session     sealskin.Session
	err         error
	target      string
}

func (f *fakeProfiles) Ensure(context.Context, string) (sealskin.Session, error) {
	f.ensureCalls++
	return f.session, f.err
}

func (f *fakeProfiles) BootstrapTarget(profileID, operationID string) (string, error) {
	if profileID != "personal" || operationID != "operation-1" {
		return "", profile.ErrProfileNotFound
	}
	return f.target, nil
}

func TestEntryGETDoesNotLaunchAndPOSTRedirects(t *testing.T) {
	profiles := &fakeProfiles{session: sealskin.Session{
		SessionID: "session-1", SessionURL: "/session-1/?access_token=secret",
	}}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, nil }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)))

	get := httptest.NewRequest(http.MethodGet, "https://adapter.example/browser/personal/", nil)
	getResponse := httptest.NewRecorder()
	server.ServeHTTP(getResponse, get)
	if getResponse.Code != http.StatusOK || profiles.ensureCalls != 0 {
		t.Fatalf("GET status=%d ensureCalls=%d", getResponse.Code, profiles.ensureCalls)
	}
	if !strings.Contains(getResponse.Body.String(), `method="post"`) {
		t.Fatal("entry does not POST to start")
	}
	if getResponse.Header().Get("Referrer-Policy") != "same-origin" {
		t.Fatal("entry must preserve its origin on the form POST")
	}
	if getResponse.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("entry must not be cached")
	}
	if !strings.Contains(getResponse.Header().Get("Content-Security-Policy"), "form-action 'self' https://sessions.example;") {
		t.Fatal("entry must allow the form's redirect to the configured Session origin")
	}

	post := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
	post.Header.Set("Origin", "https://adapter.example")
	postResponse := httptest.NewRecorder()
	server.ServeHTTP(postResponse, post)
	if postResponse.Code != http.StatusSeeOther || profiles.ensureCalls != 1 {
		t.Fatalf("POST status=%d ensureCalls=%d body=%s", postResponse.Code, profiles.ensureCalls, postResponse.Body.String())
	}
	want := "https://sessions.example/session-1/?access_token=secret&embedded=true"
	if location := postResponse.Header().Get("Location"); location != want {
		t.Fatalf("Location=%q, want %q", location, want)
	}
	if postResponse.Header().Get("Cache-Control") != "no-store" || postResponse.Header().Get("Referrer-Policy") != "no-referrer" {
		t.Fatal("token-bearing redirect lacks no-store/no-referrer")
	}
	for _, origin := range []string{"null", "https://evil.example", "https://adapter.example.evil.example", "http://adapter.example"} {
		t.Run("reject_"+origin, func(t *testing.T) {
			crossOrigin := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
			crossOrigin.Header.Set("Origin", origin)
			crossOriginResponse := httptest.NewRecorder()
			server.ServeHTTP(crossOriginResponse, crossOrigin)
			if crossOriginResponse.Code != http.StatusForbidden || profiles.ensureCalls != 1 {
				t.Fatalf("cross-origin status=%d ensureCalls=%d", crossOriginResponse.Code, profiles.ensureCalls)
			}
			if crossOriginResponse.Header().Get("Location") != "" {
				t.Fatal("rejected start must not disclose a Session URL")
			}
		})
	}
}

func TestBootstrapRedirectAndUnknownOwnershipError(t *testing.T) {
	profiles := &fakeProfiles{target: "https://start.example/", err: profile.ErrOwnershipUnknown}
	server := New(profiles, func(context.Context) ([]sealskin.Session, error) { return nil, errors.New("offline") }, "https://adapter.example", "https://sessions.example", slog.New(slog.NewTextHandler(io.Discard, nil)))

	bootstrap := httptest.NewRequest(http.MethodGet, "https://adapter.example/bootstrap/personal/operation-1", nil)
	bootstrapResponse := httptest.NewRecorder()
	server.ServeHTTP(bootstrapResponse, bootstrap)
	if bootstrapResponse.Code != http.StatusSeeOther || bootstrapResponse.Header().Get("Location") != "https://start.example/" {
		t.Fatalf("bootstrap status=%d location=%q", bootstrapResponse.Code, bootstrapResponse.Header().Get("Location"))
	}

	start := httptest.NewRequest(http.MethodPost, "https://adapter.example/browser/personal/start", nil)
	startResponse := httptest.NewRecorder()
	server.ServeHTTP(startResponse, start)
	if startResponse.Code != http.StatusConflict || strings.Contains(startResponse.Body.String(), "EOF") {
		t.Fatalf("start status=%d body=%q", startResponse.Code, startResponse.Body.String())
	}

	ready := httptest.NewRequest(http.MethodGet, "https://adapter.example/readyz", nil)
	readyResponse := httptest.NewRecorder()
	server.ServeHTTP(readyResponse, ready)
	if readyResponse.Code != http.StatusServiceUnavailable {
		t.Fatalf("ready status=%d", readyResponse.Code)
	}
}
