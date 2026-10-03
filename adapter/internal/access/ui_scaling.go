package access

import (
	"bytes"
	"crypto/subtle"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
)

var ErrDisplayRevisionConflict = errors.New("display setting revision changed")

// The callbacks operate only on the Profile from the authenticated live Session.
func WithUIScaling(read func(string) (int, int, bool), update func(string, int, int, string) (int, error)) GatewayOption {
	return func(g *Gateway) { g.uiScaling, g.updateUIScaling = read, update }
}

type displayScaling struct {
	Percent   int    `json:"percent"`
	Revision  int    `json:"revision"`
	Supported bool   `json:"supported"`
	Endpoint  string `json:"endpoint,omitempty"`
	CSRF      string `json:"csrf,omitempty"`
}

func (g *Gateway) scalingFor(r *http.Request) displayScaling {
	identity, ok := r.Context().Value(contextKey{}).(requestLogin)
	if !ok || g.uiScaling == nil {
		return displayScaling{}
	}
	percent, revision, supported := g.uiScaling(identity.Data.Profile)
	return displayScaling{Percent: percent, Revision: revision, Supported: supported,
		Endpoint: "/" + identity.Data.Session + "/_browser-platform/display", CSRF: identity.Data.CSRF}
}

func (g *Gateway) displayTransformRequested(r *http.Request) bool {
	return g.displayMode(r) != "" || g.scalingFor(r).Supported
}

func (g *Gateway) serveDisplayScaling(w http.ResponseWriter, r *http.Request) {
	setting := g.scalingFor(r)
	w.Header().Set("Cache-Control", "no-store")
	if !setting.Supported {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodGet && r.Method != http.MethodPost {
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if r.Method == http.MethodPost {
		media, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if err != nil || media != "application/json" || g.updateUIScaling == nil ||
			(!SameOrigin(r, g.session) && !SameOrigin(r, g.entry)) ||
			len(r.Header.Values("X-Browser-Platform-CSRF")) != 1 || setting.CSRF == "" ||
			subtle.ConstantTimeCompare([]byte(setting.CSRF), []byte(r.Header.Get("X-Browser-Platform-CSRF"))) != 1 {
			http.Error(w, "Forbidden", http.StatusForbidden)
			return
		}
		var input struct {
			Percent  *int `json:"percent"`
			Revision int  `json:"revision"`
		}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 512))
		decoder.DisallowUnknownFields()
		var extra any
		if decoder.Decode(&input) != nil || decoder.Decode(&extra) != io.EOF || input.Percent == nil || input.Revision < 1 ||
			(*input.Percent != 0 && (*input.Percent < 100 || *input.Percent > 300 || *input.Percent%25 != 0)) {
			http.Error(w, "Invalid display setting", http.StatusBadRequest)
			return
		}
		identity := r.Context().Value(contextKey{}).(requestLogin)
		if _, err := g.updateUIScaling(identity.Data.Profile, input.Revision, *input.Percent, identity.Data.Actor); err != nil {
			if errors.Is(err, ErrDisplayRevisionConflict) {
				http.Error(w, "Display setting changed; refresh before retrying", http.StatusConflict)
			} else {
				http.Error(w, "Display setting unavailable", http.StatusUnprocessableEntity)
			}
			return
		}
		setting = g.scalingFor(r)
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(setting)
}

//go:embed ui_scaling.js
var scalingClient string

const scalingHandler = `et=g=>{const O=parseInt(g.target.value,10);Ue(O),_e({scaling_dpi:O})}`
const persistedScalingHandler = `et=async g=>{const O=parseInt(g.target.value,10);if(await window.__bpDisplayScaling.save(O)){Ue(O),_e({scaling_dpi:O})}else{g.target.value=String(De)}}`

func applyUIScaling(source []byte, setting displayScaling) ([]byte, error) {
	if !setting.Supported || bytes.Count(source, []byte(scalingHandler)) != 1 {
		return nil, fmt.Errorf("unrecognized UI scaling handler")
	}
	config, err := json.Marshal(setting)
	if err != nil {
		return nil, err
	}
	prefix := bytes.Replace([]byte(scalingClient), []byte("/*PROFILE_SETTINGS*/null"), config, 1)
	result := bytes.Replace(source, []byte(scalingHandler), []byte(persistedScalingHandler), 1)
	return append(append(prefix, '\n'), result...), nil
}
