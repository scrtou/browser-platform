/* Native, user-initiated clipboard transfer for the pinned Selkies WebSocket client.
 * No Async Clipboard API, file picker, or local/remote screenshot file is used.
 * This prefix must execute before Selkies installs its keyboard capture handlers.
 */
(() => {
  "use strict";
  const limit = 25 * 1024 * 1024;
  const chunkSize = 750 * 1024;
  const imageTypes = new Set(["image/png", "image/jpeg", "image/webp", "image/bmp"]);
  const isMac = /Mac|iPod|iPhone|iPad/.test(navigator.platform);
  const deferredMeta = new Map();
  let transport, serverSettings, pending, suppressVKeyup = false, noticeTimer;
  let copyPending, copyReady, remoteClipboard, copySocket, armedCopy, suppressCKeyup = false;

  function cancelCopy(showCancellation = false) {
    const wasActive = !!(copyPending || copyReady);
    if (copyPending) {
      clearTimeout(copyPending.unchangedTimer);
      clearTimeout(copyPending.timeout);
    }
    copyPending = null;
    copyReady = null;
    if (showCancellation && wasActive) notice("复制已取消，请重新选择文字后操作。", "error");
  }

  function copyConnection() {
    const socket = transport?.socket();
    if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("disconnected");
    if (!transport.copyAllowed()) throw new Error("disabled");
    if (document.activeElement?.id !== "overlayInput" || !document.hasFocus() || pending) throw new Error("cancelled");
    return socket;
  }

  function copySocketChanged(socket) {
    cancelCopy();
    remoteClipboard = null;
    copySocket = socket;
    socket.addEventListener("close", () => {
      if (copySocket !== socket) return;
      const waiting = !!copyPending;
      cancelCopy();
      remoteClipboard = null;
      if (waiting) notice("连接已断开，未复制到本机。", "error");
    }, {once: true});
  }

  function writeNativeCopy(text, socket, event) {
    if (copyConnection() !== socket) throw new Error("disconnected");
    if (event) {
      // A platform Copy command (including Electron's Edit menu) already owns
      // the native clipboard event. Fill it synchronously, without an API grant.
      event.clipboardData.setData("text/plain", text);
      event.preventDefault();
      return true;
    }
    if (!navigator.userActivation?.isActive) return false;
    const operation = {text, socket, written: false};
    armedCopy = operation;
    try {
      return document.execCommand("copy") && operation.written;
    } finally { armedCopy = null; }
  }

  function finishNativeCopy(candidate, event) {
    try {
      if (copyConnection() !== candidate.socket || remoteClipboard?.text !== candidate.text) throw new Error("cancelled");
      cancelCopy();
      if (writeNativeCopy(candidate.text, candidate.socket, event)) {
        notice("文字已复制到本机，可切回本机应用按 ⌘V。", "copied");
      } else {
        copyReady = candidate;
        notice("文字已收到，请再按一次 ⌘C 复制到本机。", "copy-ready");
      }
    } catch {
      cancelCopy();
      notice("复制已取消，请回到远程画面重新操作。", "error");
    }
  }

  function receiveRemoteClipboard(socket, text) {
    if (socket !== copySocket || socket !== transport?.socket()) return;
    if (typeof text !== "string" || !text || text.length > limit || new TextEncoder().encode(text).length > limit) {
      remoteClipboard = null;
      copyReady = null;
      if (copyPending) {
        cancelCopy();
        notice("反向原生复制目前支持 25 MiB 以内的文字。", "error");
      }
      return;
    }
    remoteClipboard = {text, socket};
    if (copyReady?.text !== text) copyReady = null;
    // The protocol has no copy-operation id. A repeated read of its old value
    // cannot prove that the remote application has processed Ctrl+C yet.
    // Never automatically export that old value after a fixed network delay.
    if (copyPending?.socket === socket && text !== copyPending.baseline) {
      // Bind automatic completion to this Copy gesture's own short deadline.
      // Other activity must not extend it by refreshing browser activation.
      if (performance.now() > copyPending.automaticUntil) {
        const candidate = remoteClipboard;
        cancelCopy();
        copyReady = candidate;
        notice("文字已收到，请再按一次 ⌘C 复制到本机。", "copy-ready");
      } else finishNativeCopy(remoteClipboard);
    }
  }

  function requestNativeCopy(event) {
    try {
      const socket = copyConnection();
      if (copyReady) { finishNativeCopy(copyReady, event); return; }
      if (copyPending) { notice("正在等待远程文字，请稍候。", "sending"); return; }
      const request = {socket, baseline: remoteClipboard?.text, automaticUntil: performance.now() + 4000};
      copyPending = request;
      notice("正在复制远程文字…", "sending");
      transport.resetKeyboard();
      for (const held of deferredMeta.values()) held.forwarded = false;
      for (const message of ["kd,65507", "kd,99", "ku,99", "ku,65507"]) socket.send(message);
      request.unchangedTimer = setTimeout(() => {
        if (copyPending !== request) return;
        try { if (copyConnection() !== socket) throw new Error("disconnected"); }
        catch { cancelCopy(); return; }
        if (remoteClipboard) {
          copyReady = remoteClipboard;
          notice("未收到新文字。若要复制当前远程剪贴板，请再按一次 ⌘C。", "copy-ready");
        }
      }, 4000);
      request.timeout = setTimeout(() => {
        if (copyPending !== request) return;
        const current = copyReady;
        cancelCopy();
        if (current) {
          copyReady = current;
          notice("按 ⌘C 可复制当前远程剪贴板；也可重新选中文字。", "copy-ready");
        } else notice("未收到远程文字，请确认选中文字后重新复制。", "error");
      }, 20000);
    } catch (error) {
      cancelCopy();
      const messages = {
        disabled: "请启用 Clipboard 的远程传出，并确认当前会话可操作。",
        disconnected: "会话尚未连接，请连接后重新复制。",
        cancelled: "请等待当前粘贴完成，再在远程画面复制文字。"
      };
      notice(messages[error.message] || "复制未完成，请重新选择文字后重试。", "error");
    }
  }

  window.addEventListener("copy", event => {
    if (!event.isTrusted || event.target?.id !== "overlayInput" || !event.clipboardData) return;
    if (armedCopy) {
      event.stopImmediatePropagation();
      try {
        if (copyConnection() === armedCopy.socket) {
          event.clipboardData.setData("text/plain", armedCopy.text);
          event.preventDefault();
          armedCopy.written = true;
        }
      } catch {}
      return;
    }
    // macOS may deliver the native menu/accelerator Copy without DOM keydown.
    if (!isMac || window.webrtcInput?.isComposing) return;
    // Cancelling Copy with an empty DataTransfer clears the system clipboard.
    // Until text is ready, leave the empty input's native no-op uncancelled.
    // writeNativeCopy cancels it only when it supplies the actual text.
    event.stopImmediatePropagation();
    requestNativeCopy(event);
  }, true);

  function forwardDeferredMeta(event) {
    for (const held of deferredMeta.values()) {
      const input = window.webrtcInput;
      if (event?.type === "keydown" && event.metaKey && !event.ctrlKey && !event.altKey) {
        // Upstream intends Command shortcuts to become Control shortcuts. Use
        // that modifier from the start, avoiding a transient Alt menu action.
        // Its normal handler consumes the Meta slot when it remaps each key.
        if (input._keyDownList[held.event.code] !== 65507) {
          if (held.event.code in input._keyDownList) input._sendKeyEvent(input._keyDownList[held.event.code], held.event.code, false);
          input._sendKeyEvent(65507, held.event.code, true);
        }
        held.forwarded = true;
        continue;
      }
      if (held.forwarded) continue;
      // Replay the original event only to Selkies, never to the DOM. After a
      // local paste resets remote modifiers, clear its duplicate-event marker
      // so a still-held Command key can participate in the next shortcut.
      if (held.replayed) delete held.event[input._EVENT_MARKER];
      input._handleKeyDown(held.event);
      held.replayed = true;
      held.forwarded = true;
    }
  }

  function notice(message, status) {
    let element = document.getElementById("browser-platform-paste-status");
    if (!element) {
      element = document.createElement("div");
      element.id = "browser-platform-paste-status";
      element.setAttribute("role", "status");
      element.setAttribute("aria-live", "polite");
      element.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:1000000;max-width:380px;padding:12px 16px;border-radius:8px;background:#162536;color:#fff;font:14px/1.5 sans-serif;box-shadow:0 2px 14px #0006;pointer-events:none";
      document.body.appendChild(element);
    }
    clearTimeout(noticeTimer);
    element.textContent = message;
    element.dataset.status = status;
    element.hidden = false;
    if (status !== "sending") noticeTimer = setTimeout(() => { element.hidden = true; }, 6500);
  }

  function connection() {
    const socket = transport?.socket();
    if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("disconnected");
    if (!transport.allowed()) throw new Error("disabled");
    return socket;
  }

  function ensureCurrent(transaction) {
    if (transaction.signal.aborted) throw new Error("cancelled");
    if (performance.now() > transaction.deadline) throw new Error("timeout");
    if (connection() !== transaction.socket) throw new Error("disconnected");
  }

  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

  async function sendClipboard(transaction, bytes, mime) {
    const socket = transaction.socket;
    const text = mime === "text/plain";
    const multipart = bytes.length >= chunkSize;
    if (multipart) socket.send(text ? `cws,${bytes.length}` : `cbs,${mime},${bytes.length}`);
    let completed = false;
    try {
      for (let offset = 0; offset < bytes.length; offset += chunkSize) {
        ensureCurrent(transaction);
        while (socket.bufferedAmount > 2 * chunkSize) {
          await pause(25);
          ensureCurrent(transaction);
        }
        const part = bytes.subarray(offset, offset + chunkSize);
        let binary = "";
        for (let i = 0; i < part.length; i += 8192) binary += String.fromCharCode(...part.subarray(i, i + 8192));
        const prefix = multipart ? (text ? "cwd," : "cbd,") : (text ? "cw," : `cb,${mime},`);
        socket.send(prefix + btoa(binary));
        if (multipart) await pause(0);
      }
      completed = true;
    } finally {
      // On cancellation, the server rejects the incomplete length and discards it.
      if (multipart && socket.readyState === WebSocket.OPEN) socket.send(text ? "cwe" : "cbe");
    }
    if (!completed) throw new Error("cancelled");
  }

  function waitForClipboard(transaction, expected, mime) {
    let parts = null, offset = 0, poll, timeout, settled = false;
    let resolvePromise, rejectPromise;
    const socket = transaction.socket;
    const promise = new Promise((resolve, reject) => { resolvePromise = resolve; rejectPromise = reject; });
    // Sending is asynchronous too; attach rejection handling before awaiting it.
    promise.catch(() => {});
    function finish(error) {
      if (settled) return;
      settled = true;
      clearInterval(poll);
      clearTimeout(timeout);
      socket.removeEventListener("message", receive);
      socket.removeEventListener("close", closed);
      transaction.signal.removeEventListener("abort", aborted);
      parts = null;
      if (error) rejectPromise(new Error(error)); else resolvePromise();
    }
    function matches(bytes) {
      if (bytes.length !== expected.length) return false;
      for (let i = 0; i < bytes.length; i++) if (bytes[i] !== expected[i]) return false;
      return true;
    }
    function decode(encoded) {
      if (encoded.length > Math.ceil(expected.length / 3) * 4 + 4) throw new Error("oversize");
      const binary = atob(encoded);
      return Uint8Array.from(binary, c => c.charCodeAt(0));
    }
    function receive(event) {
      if (typeof event.data !== "string") return;
      try {
        const message = event.data;
        if (message.startsWith("clipboard_binary,")) {
          const separator = message.indexOf(",", 17);
          if (mime === message.slice(17, separator) && matches(decode(message.slice(separator + 1)))) finish();
        } else if (message.startsWith("clipboard,") && mime === "text/plain") {
          if (matches(decode(message.slice(10)))) finish();
        } else if (message.startsWith("clipboard_start,")) {
          const fields = message.split(",");
          parts = fields[1] === mime && Number(fields[2]) === expected.length ? new Uint8Array(expected.length) : null;
          offset = 0;
        } else if (message.startsWith("clipboard_data,") && parts) {
          const chunk = decode(message.slice(15));
          if (offset + chunk.length > parts.length) { parts = null; return; }
          parts.set(chunk, offset);
          offset += chunk.length;
        } else if (message === "clipboard_finish" && parts) {
          if (offset === parts.length && matches(parts)) finish();
          parts = null;
        }
      } catch { parts = null; }
    }
    function aborted() { finish("cancelled"); }
    function closed() { finish("disconnected"); }
    socket.addEventListener("message", receive);
    socket.addEventListener("close", closed);
    transaction.signal.addEventListener("abort", aborted, {once: true});
    timeout = setTimeout(() => finish("timeout"), 20000);
    return {
      promise,
      startPolling() {
        if (settled) return;
        const request = () => {
          try { ensureCurrent(transaction); socket.send("cr"); }
          catch { finish("cancelled"); }
        };
        request();
        poll = setInterval(request, 1000);
      },
      dispose() { finish("cancelled"); }
    };
  }

  async function paste(event) {
    if (!event.isTrusted || event.target?.id !== "overlayInput" || !event.clipboardData) return;
    cancelCopy();
    const file = [...event.clipboardData.items].find(item => imageTypes.has(item.type))?.getAsFile();
    const text = file ? "" : event.clipboardData.getData("text/plain");
    event.preventDefault();
    event.stopImmediatePropagation();
    if (pending) { notice("正在粘贴，请稍候。", "sending"); return; }
    if (!file && !text) { notice("剪贴板中没有可粘贴的截图或文字。", "error"); return; }
    const controller = new AbortController();
    const transaction = {signal: controller.signal, cancel: () => controller.abort(), deadline: performance.now() + 20000};
    let acknowledgement, temporaryBinary = false;
    try {
      transaction.socket = connection();
      const binarySetting = serverSettings?.enable_binary_clipboard;
      if (file && (!binarySetting || (binarySetting.locked && !binarySetting.value))) throw new Error("disabled");
      if (file && file.size > limit) throw new Error("oversize");
      pending = transaction;
      notice(file ? "正在粘贴图片…" : "正在粘贴文字…", "sending");
      const bytes = file ? new Uint8Array(await file.arrayBuffer()) : new TextEncoder().encode(text);
      if (!bytes.length || bytes.length > limit) throw new Error("oversize");
      ensureCurrent(transaction);
      const mime = file ? file.type : "text/plain";
      acknowledgement = waitForClipboard(transaction, bytes, mime);
      const settings = transport.settings();
      if (file && !settings.enable_binary_clipboard) {
        temporaryBinary = true;
        transaction.socket.send("SETTINGS," + JSON.stringify({...settings, enable_binary_clipboard: true}));
      }
      transport.resetKeyboard();
      await sendClipboard(transaction, bytes, mime);
      acknowledgement.startPolling();
      await acknowledgement.promise;
      ensureCurrent(transaction);
      if (document.activeElement?.id !== "overlayInput" || !document.hasFocus()) throw new Error("cancelled");
      // The exact bytes have been read back from the remote clipboard. Never
      // substitute a fixed delay, which could paste its previous contents.
      transport.resetKeyboard();
      for (const message of ["kd,65507", "kd,118", "ku,118", "ku,65507"]) transaction.socket.send(message);
      notice(file ? "已粘贴，请确认网页中的图片预览。" : "文字已粘贴。", "success");
    } catch (error) {
      const messages = {
        disabled: "请在 Clipboard 面板启用双向剪贴板传递，并确认当前会话可操作。",
        disconnected: "会话尚未连接，请连接后重新粘贴。",
        oversize: "截图过大，请缩小截取区域后重试（上限 25 MiB）。",
        cancelled: "操作位置已改变，已取消自动粘贴；请点击目标输入框后重试。",
        timeout: "图片传递未能确认，请保持页面连接后重试。"
      };
      notice(messages[error.message] || "粘贴未完成，请重新复制截图后重试。", "error");
    } finally {
      acknowledgement?.dispose();
      if (temporaryBinary && transaction.socket === transport?.socket() && transaction.socket.readyState === WebSocket.OPEN && transport.controls()) {
        // Restore the current UI preference, including any user change made
        // during transfer. The temporary setting is never saved locally.
        try { transaction.socket.send("SETTINGS," + JSON.stringify(transport.settings())); } catch {}
      }
      if (pending === transaction) pending = null;
    }
  }

  window.addEventListener("keydown", event => {
    const overlay = event.target?.id === "overlayInput";
    if (isMac && overlay && (event.code === "MetaLeft" || event.code === "MetaRight") && typeof window.webrtcInput?._handleKeyDown === "function") {
      // Upstream sends macOS Command as remote Alt before knowing the next
      // key. An Alt press/release opens Firefox's X11 menu and steals paste.
      // Defer it until the gesture is known; all other shortcuts use upstream.
      event.stopImmediatePropagation();
      if (!deferredMeta.has(event.code)) deferredMeta.set(event.code, {event, replayed: false, forwarded: false});
      return;
    }
    const localPaste = overlay && event.code === "KeyV" && event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey && !event.isComposing;
    if (localPaste) {
      // macOS Command+V is local native paste. Control+V keeps its existing
      // meaning: paste the remote Linux clipboard, including panel text.
      event.stopImmediatePropagation();
      suppressVKeyup = true;
      if (event.repeat || pending) event.preventDefault();
      try {
        connection(); transport.resetKeyboard();
        for (const held of deferredMeta.values()) held.forwarded = false;
      } catch {}
      return;
    }
    const localCopy = overlay && event.code === "KeyC" && event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey && !event.isComposing;
    if (localCopy) {
      event.preventDefault();
      event.stopImmediatePropagation();
      suppressCKeyup = true;
      if (event.isTrusted && !event.repeat) requestNativeCopy();
      return;
    }
    if (!["Meta", "Control", "Alt", "Shift"].includes(event.key)) cancelCopy(true);
    if (overlay && event.metaKey) forwardDeferredMeta(event);
    if (pending && !["Meta", "Control", "Alt", "Shift"].includes(event.key)) pending.cancel();
  }, true);
  window.addEventListener("keyup", event => {
    const held = deferredMeta.get(event.code);
    if (held) {
      deferredMeta.delete(event.code);
      if (!held.forwarded) event.stopImmediatePropagation();
      return;
    }
    if (suppressVKeyup && event.code === "KeyV") {
      event.stopImmediatePropagation();
      suppressVKeyup = false;
    }
    if (suppressCKeyup && event.code === "KeyC") {
      event.stopImmediatePropagation();
      suppressCKeyup = false;
    }
  }, true);
  window.addEventListener("paste", paste, true);
  window.addEventListener("pointerdown", event => {
    cancelCopy(true);
    if (event.target?.id === "overlayInput" && event.metaKey) forwardDeferredMeta(event);
    pending?.cancel();
  }, true);
  window.addEventListener("blur", () => { pending?.cancel(); cancelCopy(true); suppressVKeyup = false; suppressCKeyup = false; deferredMeta.clear(); });
  window.addEventListener("focusout", event => { if (event.target?.id === "overlayInput") { pending?.cancel(); cancelCopy(true); } }, true);
  window.addEventListener("message", event => {
    if (event.source === window && event.origin === location.origin && event.data?.type === "serverSettings") serverSettings = event.data.payload;
  });
  Object.defineProperty(window, "browserPlatformPaste", {value: Object.freeze({
    connect(value) { pending?.cancel(); cancelCopy(); transport = value; },
    socketChanged: copySocketChanged,
    remoteClipboard: receiveRemoteClipboard
  })});
})();
