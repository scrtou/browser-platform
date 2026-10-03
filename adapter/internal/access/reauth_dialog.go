package access

const ReauthDialogMarkup = `<dialog id="reauth-dialog" aria-labelledby="reauth-dialog-title"><form method="post" action="/auth/reauth">
<input type="hidden" name="csrf" value="{{.CSRF}}"><h2 id="reauth-dialog-title">确认当前密码</h2>
<p>此操作需要验证身份。验证通过后继续刚才提交的操作。</p>
<label for="reauth-current-password">当前密码</label><input id="reauth-current-password" type="password" name="password" autocomplete="current-password" maxlength="256" required>
<p role="status" aria-live="polite"></p><footer><button type="button" data-reauth-cancel>取消</button><button type="submit">确认密码</button></footer></form></dialog>`

const ReauthDialogCSS = `#reauth-dialog{width:min(440px,calc(100% - 32px));max-height:90vh;box-sizing:border-box;border:1px solid #e2e8f0;border-radius:14px;padding:24px;margin:auto;color:#0f172a;background:white;box-shadow:0 20px 60px #0f172a33}
#reauth-dialog::backdrop{background:#0f172a70}#reauth-dialog h2{font-size:18px;margin:0 0 16px}#reauth-dialog p{font-size:14px;line-height:1.6}#reauth-dialog input:not([type=hidden]){font:inherit;box-sizing:border-box;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin-top:8px}#reauth-dialog footer{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}#reauth-dialog button{font:inherit;border:1px solid #cbd5e1;border-radius:8px;padding:8px 14px;background:white;cursor:pointer}#reauth-dialog button[type=submit]{background:#2563eb;color:white;border-color:#2563eb}#reauth-dialog [role=status],.delete-result{color:#b91c1c;font-size:14px;overflow-wrap:anywhere}#reauth-dialog :focus-visible{outline:2px solid #2563eb;outline-offset:2px}#reauth-dialog button:disabled{opacity:.6}`

const ReauthDialogScript = `(() => {
  const dialog = document.getElementById('reauth-dialog');
  if (!dialog || !dialog.showModal) return;
  const form = dialog.querySelector('form'), status = dialog.querySelector('[role=status]');
  const password = form.elements.password;
  let resolvePending, previousFocus, busy = false;
  const ask = (pendingOperation) => new Promise(resolve => {
    if (resolvePending) { resolve(false); return; }
    resolvePending = resolve; previousFocus = document.activeElement;
    form.reset(); status.textContent = '';
    dialog.querySelector('h2 + p').textContent = pendingOperation ? '此操作需要验证身份。验证通过后继续刚才提交的操作。' : '请输入当前密码，验证后 5 分钟内可执行敏感操作。';
    dialog.showModal(); password.focus();
  });
  dialog.addEventListener('close', () => {
    form.reset(); if (resolvePending) { const resolve = resolvePending; resolvePending = null; resolve(false); }
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
  });
  dialog.querySelector('[data-reauth-cancel]').addEventListener('click', () => { if (!busy) dialog.close(); });
  dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
  dialog.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('input:not([type=hidden]),button:not([disabled])')];
    const first = controls[0], last = controls[controls.length-1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  async function post(action, body, timeout = 15000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(action, {method:'POST', body, credentials:'same-origin', headers:{Accept:'application/json'}, signal:controller.signal});
      if (response.redirected) {
        const target = new URL(response.url);
        if (target.origin === location.origin && target.pathname.startsWith('/manage/')) return {redirect:target.pathname + target.search};
        return {done:false,message:'登录已失效，请刷新页面重新登录。'};
      }
      if (!(response.headers.get('Content-Type') || '').includes('application/json')) return {done:false,message:response.status===429 ? '操作过于频繁，请稍后重试。' : '操作未完成（HTTP ' + response.status + '），请刷新核对后重试。'};
      const data = await response.json(); data.done = response.ok && data.done !== false; return data;
    } finally { clearTimeout(timer); }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !form.reportValidity()) return;
    busy = true; dialog.querySelectorAll('button').forEach(b => b.disabled = true); status.textContent = '正在验证…';
    try {
      const result = await post(form.action, new URLSearchParams(new FormData(form)));
      if (result.done) { const resolve = resolvePending; resolvePending = null; dialog.close(); if (resolve) resolve(true); }
      else { status.textContent = result.message || '验证失败'; password.value = ''; password.focus(); }
    } catch (_) { status.textContent = '验证请求未完成，请重试。'; }
    finally { busy = false; dialog.querySelectorAll('button').forEach(b => b.disabled = false); }
  });
  document.querySelectorAll('a[href^="/auth/reauth"]').forEach(link => link.addEventListener('click', async event => {
    event.preventDefault(); if (await ask(false)) { const notice = document.querySelector('.notice'); if (notice) notice.textContent = '密码已确认，请继续原操作。'; }
  }));
  const sensitive = form => {
    const path = new URL(form.getAttribute('action'), location.href).pathname;
    const action = form.elements.namedItem('action')?.value || '';
    if (/^\/manage\/(fingerprint-templates|display-templates|template-combinations|environment-jobs)\/[^/]+\/delete$/.test(path)) return true;
    if (path === '/manage/network-profiles') return true;
    if (/^\/manage\/browsers\/[^/]+\/(network-profile|template)$/.test(path)) return true;
    if (/^\/manage\/browsers\/[^/]+$/.test(path)) return ['delete','proxy_apply','network_direct','network_direct_managed','network_select','legacy_network_migrate','legacy_network_rollback'].includes(action);
    if (path === '/manage/accounts') return form.elements.namedItem('role')?.value === 'admin';
    if (/^\/manage\/accounts\/[^/]+$/.test(path)) return ['delete','reset_password','disable','enable','role'].includes(action);
    return false;
  };
  document.querySelectorAll('form[method="post"][action^="/manage/"]').forEach(operation => {
    let sending = false;
    operation.addEventListener('submit', async event => {
      if (!sensitive(operation)) return;
      event.preventDefault(); if (sending || !operation.reportValidity()) return;
      sending = true;
      let feedback = operation.querySelector('.delete-result');
      if (!feedback) { feedback = document.createElement('p'); feedback.className = 'delete-result'; feedback.setAttribute('role','status'); operation.prepend(feedback); }
      // Snapshot before requesting a password: retry exactly the original intent.
      const body = new URLSearchParams(new FormData(operation));
      if (event.submitter?.name) body.append(event.submitter.name, event.submitter.value);
      const target = new URL(operation.getAttribute('action'), location.href).href;
      const submits = [...operation.querySelectorAll('button[type=submit],input[type=submit]')].filter(b => !b.disabled);
      submits.forEach(b => b.disabled = true); feedback.textContent = '正在处理…';
      try {
        let result = await post(target, body, 195000);
        if (result.reauth) {
          if (!(await ask(true))) { feedback.textContent = '已取消验证，尚未执行操作。'; return; }
          result = await post(target, body, 195000);
        }
        if (result.redirect) window.location.assign(result.redirect);
        else if (result.done) { feedback.textContent = result.message || '操作已完成'; window.location.reload(); }
        else feedback.textContent = result.message || '操作未完成，原数据保留。';
      } catch (_) { feedback.textContent = '未能确认操作结果，请刷新核对；重试时沿用原操作标识。'; }
      finally { sending = false; submits.forEach(b => b.disabled = false); }
    });
  });
})();`
