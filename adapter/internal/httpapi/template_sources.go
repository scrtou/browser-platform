package httpapi

import (
	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
)

type templateSourceService interface {
	TemplateSources() (profile.TemplateSources, error)
	CreateFingerprintTemplate(context.Context, profile.FingerprintTemplate) (profile.FingerprintTemplate, error)
	CreateDisplayPreset(context.Context, profile.DisplayPreset) (profile.DisplayPreset, error)
	CreateTemplateCombination(context.Context, string, string, string, string) (profile.EnvironmentJobSummary, error)
}

func (s *Server) manageTemplateSources(w http.ResponseWriter, r *http.Request) {
	noStore(w)
	if _, ok := access.Grants(r); !ok || !managementCapabilities(s.profiles).EnvironmentJobs {
		http.NotFound(w, r)
		return
	}
	svc, ok := s.profiles.(templateSourceService)
	if !ok {
		http.Error(w, "Template service unavailable", http.StatusServiceUnavailable)
		return
	}
	sources, err := svc.TemplateSources()
	if err != nil {
		http.Error(w, "Template service unavailable", http.StatusServiceUnavailable)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(struct {
		Version int `json:"version"`
		profile.TemplateSources
	}{1, sources})
}

func (s *Server) manageTemplateSourceCreate(w http.ResponseWriter, r *http.Request) {
	noStore(w)
	if _, ok := access.Grants(r); !ok || !managementCapabilities(s.profiles).EnvironmentJobs {
		http.NotFound(w, r)
		return
	}
	svc, ok := s.profiles.(templateSourceService)
	if !ok {
		http.Error(w, "Template service unavailable", http.StatusServiceUnavailable)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8192)
	if r.ParseForm() != nil {
		s.redirectManage(w, r, "invalid")
		return
	}
	// Reject duplicate and foreign fields instead of quietly accepting screen
	// values on a fingerprint form. CSRF is verified by the gateway.
	allowed := map[string]bool{"csrf": true, "label": true}
	switch r.URL.Path {
	case "/manage/fingerprint-templates":
		for _, k := range []string{"locale", "languages", "timezone"} {
			allowed[k] = true
		}
	case "/manage/display-templates":
		for _, k := range []string{"mode", "width", "height", "dpr", "window_width", "window_height"} {
			allowed[k] = true
		}
	case "/manage/template-combinations":
		allowed["fingerprint_id"] = true
		allowed["display_id"] = true
		allowed["browser_template_id"] = true
	default:
		http.NotFound(w, r)
		return
	}
	for k, v := range r.PostForm {
		if !allowed[k] || len(v) != 1 {
			s.redirectManage(w, r, "invalid")
			return
		}
	}
	text := func(k string) string { return strings.TrimSpace(r.PostForm.Get(k)) }
	number := func(k string) int {
		if text(k) == "" {
			return 0
		}
		v, e := strconv.Atoi(text(k))
		if e != nil {
			return -1
		}
		return v
	}
	var err error
	switch r.URL.Path {
	case "/manage/fingerprint-templates":
		languages := []string{}
		for _, v := range strings.Split(text("languages"), ",") {
			languages = append(languages, strings.TrimSpace(v))
		}
		_, err = svc.CreateFingerprintTemplate(r.Context(), profile.FingerprintTemplate{Label: text("label"), Locale: text("locale"), Languages: languages, Timezone: text("timezone")})
	case "/manage/display-templates":
		dpr, e := strconv.ParseFloat(text("dpr"), 64)
		if e != nil {
			dpr = 0
		}
		_, err = svc.CreateDisplayPreset(r.Context(), profile.DisplayPreset{Label: text("label"), Mode: text("mode"), Width: number("width"), Height: number("height"), DPR: dpr, WindowWidth: number("window_width"), WindowHeight: number("window_height")})
	case "/manage/template-combinations":
		if text("browser_template_id") == "" {
			s.redirectManage(w, r, "invalid")
			return
		}
		_, err = svc.CreateTemplateCombination(r.Context(), access.Subject(r), text("fingerprint_id"), text("display_id"), text("browser_template_id"))
	}
	notice := "template_saved"
	if r.URL.Path == "/manage/template-combinations" {
		notice = "job_created"
	}
	if err != nil {
		notice = "unavailable"
		if errors.Is(err, profile.ErrEnvironmentJobInvalid) {
			notice = "invalid"
		}
		if errors.Is(err, profile.ErrEnvironmentJobsBusy) {
			notice = "job_busy"
		}
	}
	s.redirectManage(w, r, notice)
}
