
// Browser Platform: preferences come only from the verified artifact.
// This block follows the upstream defaults in camoufox.cfg.
var browserPlatformPrefs = JSON.parse(getenv("BROWSER_PLATFORM_FIREFOX_PREFS"));
Object.keys(browserPlatformPrefs).forEach(function (name) {
  lockPref(name, browserPlatformPrefs[name]);
});
