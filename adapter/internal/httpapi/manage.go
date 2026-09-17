package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"html/template"
	"net/http"
	"strings"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
)

// environmentEntry is one row of the management list. Available is false when
// the summary could not be produced; the row then carries only the grant and
// a fixed message, never the underlying error.
type environmentEntry struct {
	ProfileID    string                      `json:"profile_id"`
	Capabilities []string                    `json:"capabilities"`
	Available    bool                        `json:"available"`
	Summary      *profile.EnvironmentSummary `json:"summary,omitempty"`
}

type environmentList struct {
	Version      int                `json:"version"`
	Subject      string             `json:"subject"`
	GeneratedAt  time.Time          `json:"generated_at"`
	Environments []environmentEntry `json:"environments"`
}

// environments reads one summary per grant. The gateway already restricted
// the grants to the login's own Profiles; a Profile the service no longer
// knows is skipped so the list never names anything beyond the grants.
func (s *Server) environments(ctx context.Context, grants []access.Grant) []environmentEntry {
	entries := make([]environmentEntry, 0, len(grants))
	for _, grant := range grants {
		entry := environmentEntry{ProfileID: grant.Profile, Capabilities: grant.Capabilities}
		summary, err := s.profiles.Environment(ctx, grant.Profile)
		switch {
		case errors.Is(err, profile.ErrProfileNotFound):
			continue
		case err != nil:
			s.logger.Warn("environment summary unavailable", "profile", grant.Profile, "error", err)
		default:
			entry.Available, entry.Summary = true, &summary
		}
		entries = append(entries, entry)
	}
	return entries
}

func (s *Server) manageEnvironments(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	grants, ok := access.Grants(request)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), 10*time.Second)
	defer cancel()
	list := environmentList{Version: 1, Subject: access.Subject(request), GeneratedAt: time.Now().UTC(), Environments: s.environments(ctx, grants)}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(list)
}

func (s *Server) managePage(writer http.ResponseWriter, request *http.Request) {
	noStore(writer)
	grants, ok := access.Grants(request)
	if !ok {
		http.NotFound(writer, request)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), 10*time.Second)
	defer cancel()
	entries := s.environments(ctx, grants)
	rows := make([]manageRow, 0, len(entries))
	for _, entry := range entries {
		rows = append(rows, manageRowFor(entry))
	}
	// The logout form needs a real Origin on its POST; see pageHeaders in access.
	writer.Header().Set("Referrer-Policy", "same-origin")
	writer.Header().Set("Content-Type", "text/html; charset=utf-8")
	writer.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
	data := struct {
		Subject     string
		GeneratedAt string
		Rows        []manageRow
		CSRF        string
	}{Subject: access.Subject(request), GeneratedAt: time.Now().UTC().Format(time.RFC3339), Rows: rows, CSRF: access.CSRF(request)}
	if err := manageTemplate.Execute(writer, data); err != nil {
		s.logger.Error("render environment list", "error", err)
	}
}

type manageRow struct {
	ProfileID, Label, EntryPath, Capabilities string
	Available                                 bool
	Status, Network, Display, Locale, Home    string
	Observed                                  bool
	Health, HealthCode, HealthTitle, Checked  string
	Stale, Blocking                           bool
	Environment                               string
}

func manageRowFor(entry environmentEntry) manageRow {
	row := manageRow{ProfileID: entry.ProfileID, Label: entry.ProfileID, EntryPath: "/browser/" + entry.ProfileID + "/",
		Capabilities: strings.Join(entry.Capabilities, ", "), Available: entry.Available}
	if !entry.Available || entry.Summary == nil {
		return row
	}
	summary := entry.Summary
	row.Label, row.EntryPath, row.Status = summary.Label, summary.EntryPath, string(summary.Status)
	row.Network, row.Display = summary.NetworkMode, summary.DisplayMode
	if summary.NetworkPolicyID != "" {
		row.Network += " · " + summary.NetworkPolicyID
	}
	row.Locale = strings.TrimSpace(strings.Join([]string{summary.Language, summary.Timezone}, " "))
	row.Home = summary.ApplicationID + " / " + summary.HomeName
	row.Observed = summary.Observed
	if summary.Health != nil {
		row.Health, row.HealthCode, row.HealthTitle = string(summary.Health.Overall), summary.Health.Code, summary.Health.Title
		row.Checked, row.Stale, row.Blocking = summary.Health.CheckedAt.UTC().Format(time.RFC3339), summary.Health.Stale, summary.Health.Blocking
		if summary.Health.Environment != nil {
			row.Environment = summary.Health.Environment.ID
			if digest := summary.Health.Environment.ArtifactSHA256; len(digest) >= 12 {
				row.Environment += " · " + digest[:12] + "…"
			}
		}
	}
	return row
}

var manageTemplate = template.Must(template.New("manage").Parse(strings.TrimSpace(`
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>环境列表</title>
  <style>
    body { font: 16px system-ui, sans-serif; margin: 2rem; color: #202124; max-width: 64rem; }
    h1 { font-size: 1.25rem; }
    table { border-collapse: collapse; width: 100%; font-size: .9rem; }
    td, th { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #ddd; vertical-align: top; }
    .meta { color: #5f6368; font-size: .85rem; }
    .stale, .blocking { color: #b3261e; }
    button { font: inherit; padding: .5rem 1rem; }
    form { margin-top: 1.5rem; }
  </style>
</head>
<body>
  <h1>环境列表</h1>
  <p class="meta">账号 {{.Subject}} · 生成时间 {{.GeneratedAt}} · 本页只读，不会启动、恢复或停止浏览器；健康结果来自最近一次采样，过期即标为 stale。</p>
  {{if .Rows}}<table>
    <tr><th>环境</th><th>记录状态</th><th>健康（采样时间）</th><th>网络</th><th>显示 / 语言 / 时区</th><th>应用 / Home</th><th>环境产物</th><th>能力</th></tr>
    {{range .Rows}}<tr>
      <td><a href="{{.EntryPath}}">{{.Label}}</a>{{if ne .Label .ProfileID}}<div class="meta">{{.ProfileID}}</div>{{end}}</td>
      {{if .Available}}<td>{{.Status}}</td>
      <td>{{if .Observed}}{{.Health}}{{if .Stale}} <span class="stale">已过期</span>{{end}}{{if .HealthCode}}<div class="meta{{if .Blocking}} blocking{{end}}">{{.HealthCode}}{{if .HealthTitle}} · {{.HealthTitle}}{{end}}</div>{{end}}<div class="meta">{{.Checked}}</div>{{else}}<span class="meta">未观测</span>{{end}}</td>
      <td>{{.Network}}</td><td>{{.Display}}{{if .Locale}}<div class="meta">{{.Locale}}</div>{{end}}</td><td class="meta">{{.Home}}</td><td class="meta">{{if .Environment}}{{.Environment}}{{else}}—{{end}}</td>
      {{else}}<td colspan="6" class="meta">摘要暂不可用</td>{{end}}
      <td class="meta">{{.Capabilities}}</td>
    </tr>{{end}}
  </table>{{else}}<p>当前账号没有获授权的环境。</p>{{end}}
  <p class="meta"><a href="/manage/environments">JSON</a> · <a href="/">返回首页</a></p>
  <form method="post" action="/auth/logout"><input type="hidden" name="csrf" value="{{.CSRF}}"><button>退出登录</button></form>
</body>
</html>
`)))
