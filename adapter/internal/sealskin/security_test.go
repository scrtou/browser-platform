package sealskin

import (
	"errors"
	"strings"
	"testing"
)

func TestErrorsKeepClassificationWithoutBackendSecrets(t *testing.T) {
	secret := "r5d-synthetic-private-value-0f9ca52a"
	cause := errors.New("Authorization: Bearer " + secret + " https://session.invalid/?access_token=" + secret)
	api := &APIError{StatusCode: 503, Detail: cause.Error()}
	ambiguous := &AmbiguousMutationError{Operation: "POST /api/launch/url", Cause: cause}
	for _, err := range []error{api, ambiguous} {
		if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), "access_token") {
			t.Errorf("error text exposes backend detail for %T", err)
		}
	}
	if api.Detail != cause.Error() || !errors.Is(ambiguous, cause) {
		t.Fatal("classification evidence must remain available internally")
	}
}

func TestSessionURLRejectsCredentialsAndFragments(t *testing.T) {
	for _, value := range []string{
		"https://user:password@session.example/sid/", "/sid/#secret", "https://session.example/sid/?", "https:opaque",
	} {
		if _, err := ResolveSessionURL("https://session.example", value, true); err == nil {
			t.Errorf("accepted malformed Session URL %q", value)
		}
	}
}
