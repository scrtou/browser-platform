package httpapi

import (
	"net/http"
	"strconv"
	"strings"
)

func browserNetworkSelection(mode, id string, revision int) string {
	if mode == "direct" {
		return "direct"
	}
	if id != "" && revision > 0 {
		return "proxy|" + id + "|" + strconv.Itoa(revision)
	}
	return ""
}

func availableBrowserNetwork(row manageRow, direct bool) bool {
	if row.NetworkSelection == "direct" && direct {
		return true
	}
	for _, item := range row.NetworkProfiles {
		if row.NetworkSelection == browserNetworkSelection("proxy_required", item.ID, item.Revision) {
			return true
		}
	}
	return false
}

// The compact form dispatches to the original protected handlers. The service
// remains responsible for authorization, revision checks and stopped resources.
func (s *Server) manageNetworkSelection(writer http.ResponseWriter, request *http.Request, id, actor string) {
	if s.access != nil && !s.access.Reauthenticated(request) {
		s.redirectManage(writer, request, "reauth")
		return
	}
	for _, field := range []string{"network_selection", "revision", "idempotency_key"} {
		if len(request.PostForm[field]) != 1 {
			s.redirectManage(writer, request, "invalid")
			return
		}
	}
	_, revisionOK := parseRevision(request.PostForm.Get("revision"))
	key := strings.TrimSpace(request.PostForm.Get("idempotency_key"))
	if !revisionOK || key == "" || len(key) > 128 {
		s.redirectManage(writer, request, "invalid")
		return
	}
	capabilities := managementCapabilities(s.profiles)
	selection := strings.Split(request.PostForm.Get("network_selection"), "|")
	switch {
	case len(selection) == 1 && selection[0] == "direct" && capabilities.ManagedDirect:
		request.PostForm.Set("action", "network_direct_managed")
		s.manageNetwork(writer, request, id, actor)
	case len(selection) == 3 && selection[0] == "proxy" && capabilities.NetworkProfiles:
		if _, ok := parseRevision(selection[2]); !ok || strings.TrimSpace(selection[1]) == "" {
			s.redirectManage(writer, request, "invalid")
			return
		}
		request.PostForm.Set("return_to", "browsers")
		request.PostForm.Set("browser_revision", request.PostForm.Get("revision"))
		request.PostForm.Set("network_profile_id", selection[1])
		request.PostForm.Set("network_revision", selection[2])
		s.manageNetworkProfileBind(writer, request)
	default:
		s.redirectManage(writer, request, "invalid")
	}
}
