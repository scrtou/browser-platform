"use strict";
const observe = async ({expectedVoiceCount}) => {
  async function sha256(bytes) {
    const result = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(result), value => value.toString(16).padStart(2, "0")).join("");
  }
  // System fonts and speech voices initialize asynchronously. Measure after
  // readiness instead of treating the first non-empty voice list as complete.
  await document.fonts.ready;
  await document.fonts.load('19px "Noto Sans TC"', "繁體中文");
  for (let attempt = 0; attempt < 100 && speechSynthesis.getVoices().length !== expectedVoiceCount; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  await new Promise(resolve => setTimeout(resolve, 100));
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 100;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#1e4c83";
  ctx.fillRect(2, 3, 311, 89);
  ctx.fillStyle = "#e9d383";
  ctx.font = "19px sans-serif";
  ctx.fillText("Browser Platform 繁體中文", 7, 44);
  const canvasPNG = canvas.toDataURL();
  const canvasSHA256 = await sha256(new TextEncoder().encode(canvasPNG));
  const simple = document.createElement("canvas");
  simple.width = 32;
  simple.height = 32;
  const simpleContext = simple.getContext("2d");
  simpleContext.fillStyle = "#1e4c83";
  simpleContext.fillRect(0, 0, 32, 32);
  const canvasDiagnostics = {
    repeatStable: canvasPNG === canvas.toDataURL(),
    pixelsSHA256: await sha256(ctx.getImageData(0, 0, 320, 100).data.buffer),
    simpleSHA256: await sha256(new TextEncoder().encode(simple.toDataURL())),
    simplePixelsSHA256: await sha256(simpleContext.getImageData(0, 0, 32, 32).data.buffer),
    textWidth: ctx.measureText("Browser Platform 繁體中文").width,
  };

  const audio = new OfflineAudioContext(1, 4096, 44100);
  const oscillator = audio.createOscillator();
  oscillator.type = "triangle";
  oscillator.frequency.value = 1000;
  const compressor = audio.createDynamicsCompressor();
  oscillator.connect(compressor);
  compressor.connect(audio.destination);
  oscillator.start(0);
  const buffer = await audio.startRendering();
  const audioSHA256 = await sha256(buffer.getChannelData(0).buffer);

  const gl = document.createElement("canvas").getContext("webgl");
  const debug = gl?.getExtension("WEBGL_debug_renderer_info");
  const webgl = debug ? {
    vendor: gl.getParameter(debug.UNMASKED_VENDOR_WEBGL),
    renderer: gl.getParameter(debug.UNMASKED_RENDERER_WEBGL),
    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE)
  } : null;
  if (gl) gl.getExtension("WEBGL_lose_context")?.loseContext();

  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    oscpu: navigator.oscpu,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemoryType: typeof navigator.deviceMemory,
    locale: navigator.language,
    languages: Array.from(navigator.languages),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    intlLocale: Intl.DateTimeFormat().resolvedOptions().locale,
    normalizedLocale: new Intl.Locale(navigator.language).maximize().toString(),
    normalizedIntlLocale: new Intl.Locale(Intl.DateTimeFormat().resolvedOptions().locale).maximize().toString(),
    geolocationType: typeof navigator.geolocation,
    screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth,
      availHeight: screen.availHeight, colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth},
    window: {outerWidth, outerHeight, innerWidth, innerHeight},
    deviceScaleFactor: devicePixelRatio,
    webrtcType: typeof RTCPeerConnection,
    voicesReady: speechSynthesis.getVoices().length === expectedVoiceCount,
    canvasSHA256, canvasDiagnostics, audioSHA256, webgl,
    fonts: ["Arial", "DejaVu Sans", "Liberation Sans", "Noto Sans CJK TC"].map(
      font => ({font, present: document.fonts.check(`16px "${font}"`)})),
    voices: speechSynthesis.getVoices().map(voice => ({
      name: voice.name, lang: voice.lang, uri: voice.voiceURI, local: voice.localService
    })).sort((left, right) => left.uri.localeCompare(right.uri))
  };
};

(async () => {
  const params = new URLSearchParams(location.search);
  const nonce = params.get("nonce");
  const expectedVoiceCount = Number(params.get("voices"));
  const result = {version:1, nonce, complete:false};
  try {
    if (!/^[a-f0-9]{32}$/.test(nonce || "") || location.hostname.split(".")[0] !== nonce ||
        !Number.isInteger(expectedVoiceCount) || expectedVoiceCount < 0 || expectedVoiceCount > 256)
      throw new Error("INPUT_INVALID");
    const response = await fetch("/whoami?nonce=" + nonce + "&phase=browser", {
      cache:"no-store", credentials:"omit", redirect:"error", signal:AbortSignal.timeout(7000)
    });
    if (!response.ok) throw new Error("WHOAMI_UNAVAILABLE");
    const body = await response.text();
    if (body.length > 8192) throw new Error("WHOAMI_TOO_LARGE");
    result.whoami = JSON.parse(body);
    result.observed = await observe({expectedVoiceCount});
  } catch (_) {
    result.error = "PAGE_OBSERVATION_UNAVAILABLE";
  }
  result.complete = true;
  document.body.textContent = JSON.stringify(result);
})();
