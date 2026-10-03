package access

import (
	"bytes"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path"
	"strconv"
	"strings"
)

// Reviewed legacy Selkies clients. Automatic runtimes additionally carry the
// bounded-layout/input patch pinned below; fixed display behavior is unchanged.
var displayAssets = map[string]string{
	"index-BTp9L9Xk.js":                      "12d75adb19371bece1fb077efb9bf198a79f03e3e09255b7a310c08fde3bb088",
	"index-native-paste-628d1314a06310e5.js": "628d1314a06310e5d06299381e4e1bc1141d3e5f3046f52d763ffdb403cd801a",
}

//go:embed display_patterns.json
var displayPatternsJSON []byte
var displayPatterns = func() map[string]string {
	var p map[string]string
	if err := json.Unmarshal(displayPatternsJSON, &p); err != nil {
		panic(err)
	}
	return p
}()

func displayAsset(urlPath string) (string, bool) {
	name := path.Base(urlPath)
	digest, ok := displayAssets[name]
	return digest, ok && strings.HasSuffix(urlPath, "/assets/"+name)
}

func applyDisplayMode(source []byte, mode string) ([]byte, error) {
	if mode != "contain" && mode != "fill" {
		return nil, fmt.Errorf("invalid display mode")
	}
	result := append([]byte(nil), source...)
	for _, prefix := range []string{"WEBRTC_MANUAL_", "WEBSOCKET_MANUAL_"} {
		contain, fill := []byte(displayPatterns[prefix+"CONTAIN"]), []byte(displayPatterns[prefix+"FILL"])
		c, f := bytes.Count(result, contain), bytes.Count(result, fill)
		if c+f != 1 {
			return nil, fmt.Errorf("unrecognized fixed display geometry")
		}
		before, after := fill, contain
		if mode == "fill" {
			before, after = contain, fill
		}
		if bytes.Count(result, before) == 1 {
			result = bytes.Replace(result, before, after, 1)
		}
	}
	return result, nil
}

func (g *Gateway) displayMode(r *http.Request) string {
	if g.displayPreference == nil {
		return ""
	}
	identity, ok := r.Context().Value(contextKey{}).(requestLogin)
	if !ok {
		return ""
	}
	mode := g.displayPreference(identity.Data.Profile)
	if mode != "contain" && mode != "fill" {
		return ""
	}
	return mode
}

func (g *Gateway) transformDisplayResponse(response *http.Response) error {
	mode := g.displayMode(response.Request)
	scaling := g.scalingFor(response.Request)
	expected, ok := displayAsset(response.Request.URL.Path)
	if (mode == "" && !scaling.Supported) || !ok || response.StatusCode != http.StatusOK || response.Request.Method != http.MethodGet {
		return nil
	}
	// Unrecognized encodings/assets keep their original behavior, never apply an
	// unreviewed patch. All configured deployments serve these exact plain assets.
	if enc := response.Header.Get("Content-Encoding"); enc != "" && enc != "identity" {
		return nil
	}
	const limit = 8 << 20
	raw, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil {
		return err
	}
	if len(raw) > limit {
		response.Body = &prefixReadCloser{Reader: io.MultiReader(bytes.NewReader(raw), response.Body), closer: response.Body}
		return nil
	}
	response.Body.Close()
	response.Body = io.NopCloser(bytes.NewReader(raw))
	digest := sha256.Sum256(raw)
	actual := hex.EncodeToString(digest[:])
	// install-resolution-limit.py adds only the reviewed dynamic layout/input
	// fixes. Permit that exact asset for scaling, without widening fixed modes.
	runtimeScaling := scaling.Supported && path.Base(response.Request.URL.Path) == "index-BTp9L9Xk.js" && actual == "c7a3af93c8d368c0be1605a45f892b016ace21e891de365829b50d0159e0ce1e"
	if actual != expected && !runtimeScaling {
		return nil
	}
	transformed := raw
	if mode != "" {
		transformed, err = applyDisplayMode(transformed, mode)
		if err != nil {
			return err
		}
	}
	if scaling.Supported {
		transformed, err = applyUIScaling(transformed, scaling)
		if err != nil {
			return err
		}
	}
	response.Body = io.NopCloser(bytes.NewReader(transformed))
	response.ContentLength = int64(len(transformed))
	response.Header.Set("Content-Length", strconv.Itoa(len(transformed)))
	response.Header.Del("ETag")
	response.Header.Del("Last-Modified")
	response.Header.Del("Content-MD5")
	response.Header.Del("Digest")
	return nil
}

type prefixReadCloser struct {
	io.Reader
	closer io.Closer
}

func (p *prefixReadCloser) Close() error { return p.closer.Close() }
