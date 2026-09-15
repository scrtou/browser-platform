/* Isolated Electron guest probe. The main process only seeds/inspects the test
 * clipboard; every tested write runs in a sandbox-configured WebView with the
 * Trilium fullscreen-only permission policy and no Node/preload bridge. */
const { app, BrowserWindow, session, clipboard, nativeImage } = require('electron');
const http = require('node:http');
const fs = require('node:fs');
const assert = require('node:assert/strict');

app.setPath('userData', '/tmp/clipboard-capability-user');
app.commandLine.appendSwitch('disable-gpu');
const png = nativeImage.createFromBitmap(Buffer.from([
  0,0,255,255, 0,255,0,255, 255,0,0,255, 255,255,255,255
]), {width:2, height:2}).toPNG().toString('base64');
const fixture = `<!doctype html><meta charset="utf-8"><textarea id="target" autofocus></textarea>
<img id="image"><script>
let candidate = null; window.result = null;
window.prepare = value => { candidate = value; window.result = null; document.querySelector('#target').focus(); };
document.addEventListener('copy', event => {
  if (!candidate) return;
  const value = candidate; candidate = null;
  window.result = {trusted:event.isTrusted, activation:navigator.userActivation.isActive};
  if (value.kind === 'plain') event.clipboardData.setData('text/plain', '中文 clipboard probe');
  if (value.kind === 'html') {
    event.clipboardData.setData('text/plain', 'clipboard probe');
    event.clipboardData.setData('text/html', '<b>clipboard probe</b>');
  }
  if (value.kind === 'mime') event.clipboardData.setData(value.mime, value.png);
  if (value.kind === 'file') {
    const bytes = Uint8Array.from(atob(value.png), c => c.charCodeAt(0));
    event.clipboardData.items.add(new File([bytes], 'probe.png', {type:'image/png'}));
  }
  window.result.types = [...event.clipboardData.types];
  event.preventDefault();
});
</script>`;
const server = http.createServer((request, response) => {
  response.setHeader('Content-Type', 'text/html; charset=utf-8');
  response.end(fixture);
});
const report = {
  schemaVersion: 'browser-platform/clipboard-capabilities/v1',
  checkedAt: new Date().toISOString(), electron: process.versions.electron,
  chrome: process.versions.chrome, platform: process.platform,
  policy: 'persist:webview; only fullscreen is allowed', tests: [],
  scope: 'Linux Electron permission/API probe; not macOS, Trilium UI or OS key routing',
  chromiumSandboxDisabledForIsolatedContainer: process.argv.includes('--no-sandbox')
};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

app.whenReady().then(async () => {
  assert.equal(process.versions.electron, '43.4.0', 'use the Trilium-pinned Electron version');
  assert.ok(png.length > 0, 'PNG fixture must decode');
  const guestSession = session.fromPartition('persist:webview');
  guestSession.setPermissionRequestHandler((webContents, permission, callback) => callback(permission === 'fullscreen'));
  guestSession.setPermissionCheckHandler((webContents, permission) => permission === 'fullscreen');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const window = new BrowserWindow({width:1000, height:700, show:true,
    webPreferences:{webviewTag:true, contextIsolation:true, sandbox:true, nodeIntegration:false}});
  const guestReady = new Promise(resolve => app.on('web-contents-created', (event, contents) => {
    if (contents.getType() === 'webview') contents.once('did-finish-load', () => resolve(contents));
  }));
  fs.writeFileSync('/tmp/clipboard-capability-host.html',
    `<!doctype html><webview style="width:950px;height:650px" partition="persist:webview" src="http://127.0.0.1:${server.address().port}/"></webview>`);
  await window.loadFile('/tmp/clipboard-capability-host.html');
  const guest = await guestReady;
  const evaluate = expression => guest.executeJavaScript(expression, false);
  window.focus();
  await window.webContents.executeJavaScript("document.querySelector('webview').focus()", false);
  guest.focus();
  report.webPreferences = Object.fromEntries(['nodeIntegration','contextIsolation','sandbox'].map(key => [key,guest.getLastWebPreferences()[key]]));
  report.permissions = await evaluate(`(async () => {
    const result = {};
    for (const name of ['clipboard-read','clipboard-write']) result[name] = (await navigator.permissions.query({name})).state;
    try { await navigator.clipboard.read(); result.read = 'allowed'; } catch (error) { result.read = error.name; }
    try {
      const bytes = Uint8Array.from(atob(${JSON.stringify(png)}), c => c.charCodeAt(0));
      await navigator.clipboard.write([new ClipboardItem({'image/png':new Blob([bytes], {type:'image/png'})})]);
      result.writeImage = 'allowed';
    } catch (error) { result.writeImage = error.name; }
    return result;
  })()`);
  assert.equal(report.permissions.read, 'NotAllowedError');
  assert.equal(report.permissions.writeImage, 'NotAllowedError');
  for (const candidate of [{kind:'plain'}, {kind:'html'}, {kind:'file'},
    ...['image/png','image/jpeg','image/webp','image/bmp','application/rtf'].map(mime => ({kind:'mime',mime}))]) {
    clipboard.clear(); clipboard.writeText('previous synthetic clipboard');
    await evaluate(`window.prepare(${JSON.stringify({...candidate,png})})`);
    guest.copy(); // Native Edit/Copy; no fabricated ClipboardEvent or API grant.
    await pause(100);
    const result = await evaluate('window.result');
    assert.equal(result?.trusted, true);
    const observation = {...candidate, event:result, formats:clipboard.availableFormats(),
      text:clipboard.readText(), html:clipboard.readHTML(), image:!clipboard.readImage().isEmpty()};
    if (candidate.kind === 'plain') assert.equal(observation.text, '中文 clipboard probe');
    if (candidate.kind === 'html') assert.ok(observation.html.includes('<b>clipboard probe</b>'));
    report.tests.push(observation);
  }
  clipboard.clear();
  await evaluate(`(() => {
    const image = document.querySelector('#image'); image.src='data:image/png;base64,${png}';
    const range = document.createRange(); range.selectNode(image);
    const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
  })()`);
  await pause(150); guest.copy(); await pause(100);
  report.tests.push({kind:'native-image-selection', formats:clipboard.availableFormats(),
    image:!clipboard.readImage().isEmpty(), htmlContainsImage:clipboard.readHTML().includes('<img')});
  report.status = 'pass';
  fs.writeFileSync('/evidence/clipboard-capabilities.json', JSON.stringify(report,null,2)+'\n', {mode:0o600});
  console.log(JSON.stringify({status:report.status, electron:report.electron,
    tests:report.tests.map(test => ({kind:test.kind, mime:test.mime, image:test.image, formats:test.formats}))}));
  clipboard.clear(); server.close(); window.destroy(); app.quit();
}).catch(error => { console.error(error); app.exit(1); });
