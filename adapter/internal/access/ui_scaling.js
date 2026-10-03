// Installed only after exact Selkies asset and authenticated Profile checks.
(() => {
  const setting = /*PROFILE_SETTINGS*/null;
  const key = window.location.href.split('#')[0].replace(/[^a-zA-Z0-9.-_]/g, '_') + '_scaling_dpi';
  const seed = percent => {
    for (const suffix of ['', '_display2']) {
      if (percent) localStorage.setItem(key + suffix, String(percent * 96 / 100));
      else localStorage.removeItem(key + suffix);
    }
  };
  seed(setting.percent);
  let busy = false;
  const notice = message => {
    const select = document.getElementById('uiScalingSelect');
    if (!select) return;
    let status = document.getElementById('bp-scaling-status');
    if (!status) {
      status = document.createElement('span');
      status.id = 'bp-scaling-status';
      status.setAttribute('role', 'status');
      select.insertAdjacentElement('afterend', status);
    }
    status.textContent = message;
  };
  window.__bpDisplayScaling = {
    async save(dpi) {
      if (busy) { notice('正在保存，请稍候'); return false; }
      busy = true;
      notice('正在保存…');
      try {
        const response = await fetch(setting.endpoint, {
          method: 'POST', credentials: 'same-origin', cache: 'no-store',
          headers: {'Content-Type': 'application/json', 'X-Browser-Platform-CSRF': setting.csrf},
          body: JSON.stringify({percent: Math.round(dpi * 100 / 96), revision: setting.revision})
        });
        if (!response.ok) {
          notice(response.status === 409 ? '设置已被修改，请刷新后重试' : '缩放未保存，请刷新后重试');
          return false;
        }
        const saved = await response.json();
        if (!saved.supported || saved.percent !== Math.round(dpi * 100 / 96)) {
          notice('设置已被修改，请刷新后重试');
          return false;
        }
        setting.revision = saved.revision;
        setting.percent = saved.percent;
        seed(saved.percent);
        notice('已保存，重新连接时所有客户端共用');
        return true;
      } catch (_) {
        notice('连接失败，缩放未保存');
        return false;
      } finally {
        busy = false;
      }
    }
  };
})();
