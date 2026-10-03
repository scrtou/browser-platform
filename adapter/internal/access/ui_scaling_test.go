package access

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestUIScalingUsesOnlyAuthorizedSessionAndCSRF(t *testing.T) {
	f := newFixture(t)
	percent, revision, writes := 100, 1, 0
	f.g.uiScaling = func(id string) (int, int, bool) { return percent, revision, id == "personal" }
	f.g.updateUIScaling = func(id string, expected, value int, actor string) (int, error) {
		if id != "personal" || actor != "alice" {
			t.Fatal("wrong Profile or actor")
		}
		if expected != revision {
			return 0, ErrDisplayRevisionConflict
		}
		percent = value
		revision++
		writes++
		return revision, nil
	}
	_, csrf, cookie := f.display(t, "alice", "personal")
	target := "https://session.test/" + personalSession + "/_browser-platform/display"
	post := func(target, origin, token, body string, cookie *http.Cookie) *httptest.ResponseRecorder {
		req := httptest.NewRequest("POST", target, strings.NewReader(body))
		req.Header.Set("Origin", origin)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Browser-Platform-CSRF", token)
		if cookie != nil {
			req.AddCookie(cookie)
		}
		out := httptest.NewRecorder()
		f.handler.ServeHTTP(out, req)
		return out
	}
	before := f.upstream.Load()
	cases := []struct {
		url, origin, token, body string
		cookie                   *http.Cookie
		code                     int
	}{
		{target, "https://session.test", csrf, `{"percent":150,"revision":1}`, nil, 401},
		{target, "https://other.test", csrf, `{"percent":150,"revision":1}`, cookie, 403},
		{target, "https://session.test", "wrong", `{"percent":150,"revision":1}`, cookie, 403},
		{strings.Replace(target, personalSession, workSession, 1), "https://session.test", csrf, `{"percent":150,"revision":1}`, cookie, 401},
		{target, "https://session.test", csrf, `{"percent":150,"revision":1,"profile":"work"}`, cookie, 400},
		{target, "https://session.test", csrf, `{"percent":151,"revision":1}`, cookie, 400},
		{target, "https://session.test", csrf, `{"revision":1}`, cookie, 400},
	}
	for _, tc := range cases {
		if out := post(tc.url, tc.origin, tc.token, tc.body, tc.cookie); out.Code != tc.code {
			t.Fatalf("got %d want %d", out.Code, tc.code)
		}
	}
	if writes != 0 {
		t.Fatal("rejected request persisted")
	}
	out := post(target, "https://session.test", csrf, `{"percent":150,"revision":1}`, cookie)
	if out.Code != 200 || writes != 1 || percent != 150 || out.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("valid setting not saved")
	}
	if out := post(target, "https://session.test", csrf, `{"percent":200,"revision":1}`, cookie); out.Code != 409 || writes != 1 {
		t.Fatal("stale page overwrote newer setting")
	}
	read := request(f.handler, "GET", target, nil, cookie)
	var setting displayScaling
	if json.Unmarshal(read.Body.Bytes(), &setting) != nil || setting.Percent != 150 || setting.Revision != 2 || setting.CSRF != csrf {
		t.Fatal("saved setting not returned")
	}
	f.invalidBinding.Store(true)
	if out := post(target, "https://session.test", csrf, `{"percent":200,"revision":2}`, cookie); out.Code != 409 || writes != 1 {
		t.Fatal("stale Session changed setting")
	}
	if f.upstream.Load() != before {
		t.Fatal("preference endpoint forwarded to Worker")
	}
}

func TestUIScalingTransformsOnlyPinnedAssets(t *testing.T) {
	directory := os.Getenv("BP_DISPLAY_ASSETS")
	if directory == "" {
		t.Skip("requires retained exact Selkies assets")
	}
	cases := map[string]string{}
	for name := range displayAssets {
		cases[name] = name
	}
	if runtime := os.Getenv("BP_DISPLAY_RUNTIME_ASSETS"); runtime != "" {
		cases["runtime-auto"] = filepath.Join(runtime, "chromix.js")
	}
	for key, file := range cases {
		name := key
		if key == "runtime-auto" {
			name = "index-BTp9L9Xk.js"
		} else {
			file = filepath.Join(directory, file)
		}
		raw, err := os.ReadFile(file)
		if err != nil {
			t.Fatal(err)
		}
		g := &Gateway{uiScaling: func(id string) (int, int, bool) { return 150, 3, id == "work" }}
		req := httptest.NewRequest("GET", "https://session.test/"+workSession+"/assets/"+name, nil)
		req = req.WithContext(context.WithValue(req.Context(), contextKey{}, requestLogin{Data: login{Profile: "work", Session: workSession, CSRF: "qa-csrf"}}))
		response := &http.Response{Request: req, StatusCode: 200, Header: http.Header{"ETag": []string{"original"}}, Body: io.NopCloser(bytes.NewReader(raw)), ContentLength: int64(len(raw))}
		if err := g.transformDisplayResponse(response); err != nil {
			t.Fatal(err)
		}
		transformed, _ := io.ReadAll(response.Body)
		if bytes.Equal(raw, transformed) || !bytes.Contains(transformed, []byte(`"percent":150`)) || !bytes.Contains(transformed, []byte(persistedScalingHandler)) || response.ContentLength != int64(len(transformed)) || response.Header.Get("ETag") != "" {
			t.Fatal("pinned UI asset not transformed")
		}
		if output := os.Getenv("BP_DISPLAY_OUTPUT"); output != "" {
			if err := os.WriteFile(filepath.Join(output, name), transformed, 0600); err != nil {
				t.Fatal(err)
			}
		}
		req = req.WithContext(context.WithValue(req.Context(), contextKey{}, requestLogin{Data: login{Profile: "fixed", Session: personalSession}}))
		response.Request = req
		response.Body = io.NopCloser(bytes.NewReader(raw))
		response.ContentLength = int64(len(raw))
		if err := g.transformDisplayResponse(response); err != nil {
			t.Fatal(err)
		}
		unchanged, _ := io.ReadAll(response.Body)
		if !bytes.Equal(raw, unchanged) {
			t.Fatal("fixed Profile acquired mutable DPI")
		}
	}
}
