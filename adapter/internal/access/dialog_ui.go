package access

// PasswordDialogMarkup, CSS and Script are shared static UI for authenticated pages.
const PasswordDialogMarkup = `<dialog id="password-dialog" aria-labelledby="password-dialog-title">
<header class="password-dialog-header"><h2 id="password-dialog-title">修改密码</h2><button type="button" data-password-close aria-label="关闭修改密码">×</button></header>
<form method="post" action="/auth/password" id="password-dialog-form">
<input type="hidden" name="csrf" value="{{.CSRF}}">
<div class="password-dialog-body"><p class="meta">新密码为 4–256 字节。修改后，其他登录会退出。</p>
<p class="password-result" role="status" aria-live="polite"></p>
<fieldset><label for="modal-current-password">当前密码</label><input id="modal-current-password" name="current" type="password" autocomplete="current-password" required maxlength="256">
<label for="modal-new-password">新密码</label><input id="modal-new-password" name="password" type="password" autocomplete="new-password" required minlength="1" maxlength="256" data-password-bytes="4">
<label for="modal-confirm-password">再次输入新密码</label><input id="modal-confirm-password" name="confirm" type="password" autocomplete="new-password" required minlength="1" maxlength="256" data-password-bytes="4"></fieldset></div>
<footer class="password-dialog-footer"><button type="button" data-password-close>取消</button><button type="submit">保存密码</button></footer></form></dialog>`

const PasswordDialogCSS = `#password-dialog{width:min(480px,calc(100% - 32px));max-height:90vh;margin:auto;padding:0;border:1px solid #e2e8f0;border-radius:14px;color:#0f172a;background:#fff;box-shadow:0 20px 60px #0f172a33;overflow:auto}
#password-dialog [hidden]{display:none!important}
#password-dialog::backdrop{background:#0f172a70}
#password-dialog .password-dialog-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #e2e8f0}
#password-dialog h2{margin:0;font-size:18px}#password-dialog button{font:inherit;cursor:pointer;padding:8px 14px;border:1px solid #e2e8f0;border-radius:8px;background:white;color:#334155}
#password-dialog .password-dialog-body{padding:20px}#password-dialog fieldset{border:0;margin:0;padding:0;display:grid;gap:8px}#password-dialog label{font-size:14px;font-weight:600;margin-top:8px}
#password-dialog input:not([type=hidden]){font:inherit;width:100%;box-sizing:border-box;min-height:40px;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;background:#fff}
#password-dialog .password-dialog-footer{display:flex;justify-content:flex-end;gap:8px;padding:14px 20px;border-top:1px solid #e2e8f0}#password-dialog button[type=submit]{background:#2563eb;color:white;border-color:#2563eb}
#password-dialog :focus-visible{outline:2px solid #2563eb;outline-offset:2px}#password-dialog button:disabled{opacity:.55;cursor:default}
#password-dialog .password-result{font-size:14px;color:#b91c1c;overflow-wrap:anywhere}#password-dialog .password-result.success{color:#047857}
`

const PasswordDialogScript = `(() => {
  const byteInputs = [...document.querySelectorAll('[data-password-bytes]')];
  const validateBytes = input => {
    const length = new TextEncoder().encode(input.value).length;
    input.setCustomValidity(input.value && (length < 4 || length > 256) ? '密码须为 4–256 字节' : '');
  };
  byteInputs.forEach(input => input.addEventListener('input', () => validateBytes(input)));
  if (typeof HTMLDialogElement !== 'function' || !HTMLDialogElement.prototype.showModal) return;
  const dialog = document.getElementById('password-dialog');
  if (!dialog) return;
  const form = dialog.querySelector('form'), result = dialog.querySelector('.password-result');
  const fields = form.querySelector('fieldset'), submit = form.querySelector('[type=submit]');
  let lastFocus, busy = false;
  document.querySelectorAll('a[href="/auth/password"]').forEach(link => {
    link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls',dialog.id);
    link.addEventListener('click', event => {
      event.preventDefault(); lastFocus = link;
      if (!busy) { form.reset(); fields.disabled = false; fields.hidden = false; submit.disabled = false; result.textContent = ''; result.classList.remove('success'); form.querySelectorAll('[data-password-bytes]').forEach(validateBytes); }
      dialog.showModal(); form.querySelector('[name=current]').focus();
    });
  });
  dialog.querySelectorAll('[data-password-close]').forEach(button => button.addEventListener('click', () => { if (!busy) dialog.close(); }));
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { form.reset(); if (lastFocus && (document.activeElement === document.body || dialog.contains(document.activeElement))) lastFocus.focus(); });
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button:not([disabled]), input:not([type=hidden]):not(:disabled)')].filter(el => el.getClientRects().length);
    if (!controls.length) { event.preventDefault(); return; }
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    form.querySelectorAll('[data-password-bytes]').forEach(validateBytes);
    if (!form.reportValidity()) return;
    if (form.elements.password.value !== form.elements.confirm.value) { result.textContent = '两次输入的新密码不一致'; return; }
    const body = new URLSearchParams(new FormData(form));
    busy = true; dialog.querySelectorAll('button').forEach(button => button.disabled = true); result.textContent = '正在保存…';
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(form.action, {method:'POST',body,headers:{Accept:'application/json'},credentials:'same-origin',signal:controller.signal});
      const type = response.headers.get('Content-Type') || '';
      if (!type.includes('application/json')) { result.textContent = response.status === 429 ? '操作过于频繁，请稍后重试。' : '登录或验证已失效，请刷新页面重新登录。'; return; }
      const data = await response.json();
      result.textContent = data.message || (data.done ? '密码已更新。' : '密码未能更新。');
      result.classList.toggle('success', response.ok && data.done);
      if (data.done) { form.reset(); fields.disabled = true; fields.hidden = true; }
    } catch (_) { result.textContent = '未能确认保存结果，请用新密码重新登录核对。'; }
    finally { clearTimeout(timer); busy = false; dialog.querySelectorAll('button').forEach(button => button.disabled = false); submit.disabled = fields.disabled; }
  });
})();`
