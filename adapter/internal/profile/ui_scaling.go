package profile

import "context"

// UIScalingPreference reads the Profile's shared presentation setting. Fixed
// screen/DPR contracts never acquire mutable DPI from this preference.
func (s *Service) UIScalingPreference(id string) (percent, revision int, supported bool) {
	record, ok := s.directory.record(id)
	if !ok || record.Status != RecordReady {
		return 0, 0, false
	}
	return record.UIScalingPercent, record.Revision, s.supportsUIScaling(record.Definition)
}

func (s *Service) supportsUIScaling(def Definition) bool {
	if def.BrowserTemplateID == "" {
		return def.WaylandMode // Legacy Work's native automatic display.
	}
	if def.ResolutionMode != "auto" || s.templateCatalog == nil {
		return false
	}
	data, err := s.templateCatalog.Read(context.Background())
	if err != nil {
		return false
	}
	for _, display := range data.DisplayTemplates {
		if display.ID == def.DisplayTemplateID && display.Revision == def.DisplayTemplateRevision && display.Status == "accepted" {
			return display.Screen == "auto@system" && display.Scaling == "auto"
		}
	}
	return false
}

func validUIScaling(percent int) bool {
	return percent == 0 || (percent >= 100 && percent <= 300 && percent%25 == 0)
}
