package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
)

type templateDataDeleteService interface {
	DeleteTemplateData(context.Context, string, string, string, string, string) error
}
type networkDeleteService interface {
	DeleteNetworkProfile(context.Context, string, int, string, string) error
}

func confirmedDelete(r *http.Request) bool {
	return len(r.PostForm["confirm"]) == 1 && r.PostForm.Get("confirm") == "delete"
}
func (s *Server) deleteNotice(w http.ResponseWriter, r *http.Request, err error) {
	notice := "data_deleted"
	switch {
	case err == nil:
	case errors.Is(err, profile.ErrNetworkProfileReferenced), errors.Is(err, profile.ErrDataReferenced):
		notice = "data_referenced"
	case errors.Is(err, profile.ErrDataInUse):
		notice = "data_busy"
	case errors.Is(err, profile.ErrBuiltinTemplate):
		notice = "data_builtin"
	default:
		notice = "data_delete_failed"
	}
	if r.Header.Get("Accept") == "application/json" {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		if err != nil {
			w.WriteHeader(http.StatusConflict)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"done": err == nil, "message": notices[notice]})
		return
	}
	s.redirectManage(w, r, notice)
}
func (s *Server) manageTemplateDataDelete(w http.ResponseWriter, r *http.Request) {
	noStore(w)
	if _, ok := access.Grants(r); !ok || !managementCapabilities(s.profiles).EnvironmentJobs {
		http.NotFound(w, r)
		return
	}
	svc, ok := s.profiles.(templateDataDeleteService)
	if !ok {
		http.NotFound(w, r)
		return
	}
	if s.access != nil && !s.access.Reauthenticated(r) {
		if r.Header.Get("Accept") == "application/json" {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(http.StatusForbidden)
			_ = json.NewEncoder(w).Encode(map[string]any{"done": false, "reauth": true, "message": notices["reauth"]})
			return
		}
		s.redirectManage(w, r, "reauth")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8192)
	if r.ParseForm() != nil || !confirmedDelete(r) {
		s.redirectManage(w, r, "invalid")
		return
	}
	allowed := map[string]bool{"csrf": true, "confirm": true, "browser_template_id": true, "display_template_id": true}
	for k, v := range r.PostForm {
		if !allowed[k] || len(v) != 1 {
			s.redirectManage(w, r, "invalid")
			return
		}
	}
	kind := ""
	switch {
	case strings.HasPrefix(r.URL.Path, "/manage/fingerprint-templates/"):
		kind = "fingerprints"
	case strings.HasPrefix(r.URL.Path, "/manage/display-templates/"):
		kind = "displays"
	case strings.HasPrefix(r.URL.Path, "/manage/template-combinations/"):
		kind = "combinations"
	case strings.HasPrefix(r.URL.Path, "/manage/environment-jobs/"):
		kind = "jobs"
	default:
		http.NotFound(w, r)
		return
	}
	err := svc.DeleteTemplateData(r.Context(), kind, r.PathValue("id"), r.PostForm.Get("browser_template_id"), r.PostForm.Get("display_template_id"), access.Subject(r))
	s.logger.Info("management action", "action", "data_delete", "kind", kind, "succeeded", err == nil)
	s.deleteNotice(w, r, err)
}
func (s *Server) manageNetworkDelete(w http.ResponseWriter, r *http.Request) {
	svc, ok := s.profiles.(networkDeleteService)
	if !ok {
		http.NotFound(w, r)
		return
	}
	if !confirmedDelete(r) {
		s.redirectManage(w, r, "invalid")
		return
	}
	for _, k := range []string{"action", "id", "revision", "idempotency_key"} {
		if len(r.PostForm[k]) != 1 {
			s.redirectManage(w, r, "invalid")
			return
		}
	}
	revision, valid := parseRevision(r.PostForm.Get("revision"))
	if !valid {
		s.redirectManage(w, r, "invalid")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), sealskin.LongOperationTimeout)
	defer cancel()
	err := svc.DeleteNetworkProfile(ctx, r.PostForm.Get("id"), revision, access.Subject(r), r.PostForm.Get("idempotency_key"))
	s.logger.Info("management action", "action", "network_delete", "succeeded", err == nil)
	s.deleteNotice(w, r, err)
}
