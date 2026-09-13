async ({operation, value}) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("browser-platform-qa", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("proof");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  try {
    if (operation === "write") {
      document.cookie = `bp_home=${value}; Max-Age=86400; Path=/; Secure; SameSite=Strict`;
      localStorage.setItem("bp_home", value);
      await new Promise((resolve, reject) => {
        const tx = db.transaction("proof", "readwrite");
        tx.objectStore("proof").put(value, "home");
        tx.oncomplete = resolve;
        tx.onabort = () => reject(tx.error);
        tx.onerror = () => reject(tx.error);
      });
    }
    const indexed = await new Promise((resolve, reject) => {
      const request = db.transaction("proof").objectStore("proof").get("home");
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
    return {
      cookie: document.cookie.split("; ").find(item => item.startsWith("bp_home="))?.slice(8) ?? null,
      localStorage: localStorage.getItem("bp_home"),
      indexedDB: indexed
    };
  } finally {
    db.close();
  }
}
