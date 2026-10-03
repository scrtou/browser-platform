package profile

import "reflect"

const builtinFixedDisplayID = "display-0000000000000002"

func builtinFingerprintTemplates() []FingerprintTemplate {
	const created = "2026-10-02T00:00:00Z"
	return []FingerprintTemplate{
		{Version: 2, Builtin: true, ID: "fp-0000000000000001", Label: "通用 US", Revision: 1, Locale: "en-US", Languages: []string{"en-US", "en"}, Timezone: "America/New_York", CreatedAt: created},
		{Version: 2, Builtin: true, ID: "fp-0000000000000002", Label: "通用 TW", Revision: 1, Locale: "zh-TW", Languages: []string{"zh-TW", "zh", "en-US", "en"}, Timezone: "Asia/Taipei", CreatedAt: created},
		{Version: 2, Builtin: true, ID: "fp-0000000000000003", Label: "通用 JP", Revision: 1, Locale: "ja-JP", Languages: []string{"ja-JP", "ja", "en-US", "en"}, Timezone: "Asia/Tokyo", CreatedAt: created},
		{Version: 2, Builtin: true, ID: "fp-0000000000000004", Label: "通用 CN", Revision: 1, Locale: "zh-CN", Languages: []string{"zh-CN", "zh", "en-US", "en"}, Timezone: "Asia/Shanghai", CreatedAt: created},
	}
}

func builtinDisplayPresets() []DisplayPreset {
	return []DisplayPreset{builtinDisplayPreset(), {
		Builtin: true, ID: builtinFixedDisplayID, Label: "固定 1920×1080 · DPR 1", Revision: 1,
		Mode: "fixed", Width: 1920, Height: 1080, DPR: 1, WindowWidth: 1920, WindowHeight: 1080, CreatedAt: "2026-10-02T00:00:00Z",
	}}
}

func builtinSource(kind, id string) bool {
	if kind == "fingerprints" {
		for _, value := range builtinFingerprintTemplates() {
			if value.ID == id {
				return true
			}
		}
	}
	return kind == "displays" && (id == builtinDisplayID || id == builtinFixedDisplayID)
}

func validBuiltinFingerprint(value FingerprintTemplate) bool {
	for _, expected := range builtinFingerprintTemplates() {
		if reflect.DeepEqual(value, expected) {
			return true
		}
	}
	return false
}

func validBuiltinDisplay(value DisplayPreset) bool {
	for _, expected := range builtinDisplayPresets() {
		if value == expected {
			return true
		}
	}
	return false
}
