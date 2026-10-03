package access

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDisplayModeOnlyChangesReviewedGeometry(t *testing.T) {
	for _, old := range []string{"CONTAIN", "FILL"} {
		raw := []byte("KEEP_INPUT_MAPPING;" + displayPatterns["WEBRTC_MANUAL_"+old] + ";" + displayPatterns["WEBSOCKET_MANUAL_"+old] + ";KEEP_SERVER_SETTINGS;")
		for _, mode := range []string{"contain", "fill"} {
			got, err := applyDisplayMode(raw, mode)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Contains(got, []byte(displayPatterns["WEBRTC_MANUAL_"+strings.ToUpper(mode)])) || !bytes.Contains(got, []byte("KEEP_INPUT_MAPPING")) || !bytes.HasSuffix(got, []byte("KEEP_SERVER_SETTINGS;")) {
				t.Fatal("unexpected patch")
			}
		}
	}
	if _, err := applyDisplayMode([]byte("unknown"), "fill"); err == nil {
		t.Fatal("unknown geometry accepted")
	}
}
func TestDisplayResponseDoesNotPatchUnknownBytesOrOtherProfile(t *testing.T) {
	g := &Gateway{displayPreference: func(id string) string {
		if id == "personal" {
			return "fill"
		}
		return ""
	}}
	req := httptest.NewRequest("GET", "https://session.test/"+personalSession+"/assets/index-BTp9L9Xk.js", nil)
	req = req.WithContext(context.WithValue(req.Context(), contextKey{}, requestLogin{Data: login{Profile: "personal"}}))
	raw := []byte(displayPatterns["WEBRTC_MANUAL_CONTAIN"] + displayPatterns["WEBSOCKET_MANUAL_CONTAIN"])
	response := &http.Response{Request: req, StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(bytes.NewReader(raw)), ContentLength: int64(len(raw))}
	if err := g.transformDisplayResponse(response); err != nil {
		t.Fatal(err)
	}
	got, _ := io.ReadAll(response.Body)
	if !bytes.Equal(raw, got) {
		t.Fatal("unrecognized asset changed")
	}
	other := req.WithContext(context.WithValue(req.Context(), contextKey{}, requestLogin{Data: login{Profile: "work"}}))
	if g.displayMode(other) != "" {
		t.Fatal("preference leaked between profiles")
	}
	if g.displayMode(httptest.NewRequest("GET", "https://session.test/", nil)) != "" {
		t.Fatal("unauthenticated preference used")
	}
}
