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
	"time"

	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type coherenceService interface {
	ProbeCoherence(context.Context, string) (sealskin.CoherenceAccess, error)
}

type coherenceReply struct {
	Coherence sealskin.CoherenceAccess `json:"coherence"`
	Error     string                   `json:"error,omitempty"`
}

func registerCoherence(mux *http.ServeMux, service Service) {
	mux.HandleFunc("POST /profiles/{profile}/coherence", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		prober, ok := service.(coherenceService)
		if !ok {
			w.WriteHeader(http.StatusNotImplemented)
			_ = json.NewEncoder(w).Encode(coherenceReply{Error: "coherence probing is unavailable"})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 75*time.Second)
		defer cancel()
		result, err := prober.ProbeCoherence(ctx, r.PathValue("profile"))
		response := coherenceReply{Coherence: result}
		status := http.StatusOK
		if err != nil {
			status, response.Error = http.StatusServiceUnavailable, "current generation coherence could not be observed"
			if errors.Is(err, profile.ErrProfileNotFound) {
				status, response.Error = http.StatusNotFound, "profile not found"
			}
		}
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(response)
	})
}

// CoherenceCommand samples the existing generation through the private socket.
// A blocked result is returned in full so an operator can inspect its cause.
func CoherenceCommand(ctx context.Context, socket, id string) (sealskin.CoherenceAccess, error) {
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socket)
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 90 * time.Second}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://adapter/profiles/"+url.PathEscape(id)+"/coherence", nil)
	if err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	response, err := client.Do(request)
	if err != nil {
		return sealskin.CoherenceAccess{}, fmt.Errorf("contact the running adapter control socket: %w", err)
	}
	defer response.Body.Close()
	var result coherenceReply
	if err := json.NewDecoder(io.LimitReader(response.Body, 256<<10)).Decode(&result); err != nil {
		return sealskin.CoherenceAccess{}, err
	}
	if response.StatusCode != http.StatusOK || result.Error != "" {
		return result.Coherence, fmt.Errorf("control command returned HTTP %d: %s", response.StatusCode, result.Error)
	}
	return result.Coherence, nil
}
