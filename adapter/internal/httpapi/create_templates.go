package httpapi

import (
	"context"
	"net/url"
	"strings"

	"browser-platform/adapter/internal/profile"
)

type createFingerprintChoice struct {
	BrowserID, ID, Label, Display string
}

// A new browser selects an engine and an accepted artifact. The display must
// be uniquely determined by that pair; a client cannot supply a third choice.
func newBrowserTemplates(items []profile.CompatibleTemplateSummary) []profile.CompatibleTemplateSummary {
	type pair struct{ browser, artifact string }
	counts := map[pair]int{}
	for _, item := range items {
		if item.AllowNewBrowsers {
			counts[pair{item.BrowserTemplateID, item.EnvironmentArtifactID}]++
		}
	}
	var result []profile.CompatibleTemplateSummary
	for _, item := range items {
		if item.AllowNewBrowsers && item.BrowserTemplateID != "" && item.EnvironmentArtifactID != "" &&
			item.DisplayTemplateID != "" && counts[pair{item.BrowserTemplateID, item.EnvironmentArtifactID}] == 1 {
			result = append(result, item)
		}
	}
	return result
}

func createFingerprintChoices(items []profile.CompatibleTemplateSummary) []createFingerprintChoice {
	var result []createFingerprintChoice
	for _, item := range items {
		label := item.EnvironmentLabel
		if label == "" {
			label = item.EnvironmentArtifactID
		}
		result = append(result, createFingerprintChoice{
			BrowserID: item.BrowserTemplateID, ID: item.EnvironmentArtifactID,
			Label:   label + " · " + item.Locale + " / " + item.Timezone + " · " + item.DisplayLabel,
			Display: item.DisplayLabel,
		})
	}
	return result
}

func (s *Server) resolveCreateTemplate(ctx context.Context, form url.Values) (profile.CompatibleTemplateSummary, bool) {
	if len(form["browser_template_id"]) != 1 || len(form["environment_artifact_id"]) != 1 {
		return profile.CompatibleTemplateSummary{}, false
	}
	for _, removed := range []string{"display_template_id", "template_combination"} {
		if _, present := form[removed]; present {
			return profile.CompatibleTemplateSummary{}, false
		}
	}
	catalog, ok := s.profiles.(templateCatalogService)
	if !ok || !managementCapabilities(s.profiles).TemplateCatalog {
		return profile.CompatibleTemplateSummary{}, false
	}
	items, err := catalog.CompatibleTemplates(ctx)
	if err != nil {
		return profile.CompatibleTemplateSummary{}, false
	}
	browser, artifact := strings.TrimSpace(form.Get("browser_template_id")), strings.TrimSpace(form.Get("environment_artifact_id"))
	for _, item := range newBrowserTemplates(items) {
		if item.BrowserTemplateID == browser && item.EnvironmentArtifactID == artifact {
			return item, true
		}
	}
	return profile.CompatibleTemplateSummary{}, false
}
