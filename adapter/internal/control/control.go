// Package control exposes lifecycle commands only through a private Unix
// socket. Commands use the running adapter's Profile locks and journal.
package control

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"browser-platform/adapter/internal/profile"
)

type Service interface {
	Inspect(context.Context, string) (profile.LifecycleResult, error)
	Stop(context.Context, string) (profile.LifecycleResult, error)
	Reconcile(context.Context, string) (profile.LifecycleResult, error)
}

type reply struct {
	Result profile.LifecycleResult `json:"result"`
	Error  string                  `json:"error,omitempty"`
}

func Handler(service Service) http.Handler {
	mux := http.NewServeMux()
	for _, command := range []struct {
		pattern string
		call    func(context.Context, string) (profile.LifecycleResult, error)
	}{
		{"GET /profiles/{profile}", service.Inspect},
		{"POST /profiles/{profile}/stop", service.Stop},
		{"POST /profiles/{profile}/reconcile", service.Reconcile},
	} {
		mux.HandleFunc(command.pattern, func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Cache-Control", "no-store")
			ctx, cancel := context.WithTimeout(r.Context(), 75*time.Second)
			defer cancel()
			result, err := command.call(ctx, r.PathValue("profile"))
			response := reply{Result: result}
			status := http.StatusOK
			if err != nil {
				switch {
				case errors.Is(err, profile.ErrProfileNotFound):
					status, response.Error = http.StatusNotFound, "profile not found"
				case errors.Is(err, profile.ErrOwnershipUnknown):
					status, response.Error = http.StatusConflict, "runtime ownership requires recovery"
				case errors.Is(err, profile.ErrOperationRunning):
					status, response.Error = http.StatusConflict, "profile operation is still running"
				case errors.Is(err, profile.ErrStopUnconfirmed):
					status, response.Error = http.StatusServiceUnavailable, "stop is pending; retry or reconcile required"
				case errors.Is(err, profile.ErrLifecycleDisabled):
					status, response.Error = http.StatusNotImplemented, "verified lifecycle is disabled"
				default:
					status, response.Error = http.StatusServiceUnavailable, "lifecycle operation could not be verified"
				}
			}
			w.WriteHeader(status)
			_ = json.NewEncoder(w).Encode(response)
		})
	}
	return mux
}

// Listen refuses non-sockets and only removes this user's refused stale socket.
// The caller must hold the state file's service lock for the listener lifetime.
func Listen(path string) (net.Listener, error) {
	if path == "" {
		return nil, errors.New("control socket path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, err
	}
	if info, err := os.Lstat(path); err == nil {
		owner, ok := info.Sys().(*syscall.Stat_t)
		if info.Mode()&os.ModeSocket == 0 || !ok || owner.Uid != uint32(os.Geteuid()) {
			return nil, errors.New("refusing to replace an unowned control socket path")
		}
		connection, dialErr := net.DialTimeout("unix", path, 250*time.Millisecond)
		if dialErr == nil {
			connection.Close()
			return nil, errors.New("another adapter is listening on the control socket")
		}
		if !errors.Is(dialErr, syscall.ECONNREFUSED) && !errors.Is(dialErr, os.ErrNotExist) {
			return nil, fmt.Errorf("inspect existing control socket: %w", dialErr)
		}
		if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return nil, err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	listener, err := net.Listen("unix", path)
	if err != nil {
		return nil, err
	}
	if err := os.Chmod(path, 0o600); err != nil {
		listener.Close()
		return nil, err
	}
	return listener, nil
}

func Command(ctx context.Context, socket, action, id string) (profile.LifecycleResult, error) {
	method := http.MethodPost
	path := "/profiles/" + url.PathEscape(id)
	switch action {
	case "inspect":
		method = http.MethodGet
	case "stop", "reconcile":
		path += "/" + action
	default:
		return profile.LifecycleResult{}, errors.New("unsupported control command")
	}
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socket)
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 90 * time.Second}
	request, err := http.NewRequestWithContext(ctx, method, "http://adapter"+path, nil)
	if err != nil {
		return profile.LifecycleResult{}, err
	}
	response, err := client.Do(request)
	if err != nil {
		return profile.LifecycleResult{}, fmt.Errorf("contact the running adapter control socket: %w", err)
	}
	defer response.Body.Close()
	var result reply
	if err := json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(&result); err != nil {
		return profile.LifecycleResult{}, err
	}
	if response.StatusCode != http.StatusOK || result.Error != "" {
		return result.Result, fmt.Errorf("control command returned HTTP %d: %s", response.StatusCode, result.Error)
	}
	return result.Result, nil
}
