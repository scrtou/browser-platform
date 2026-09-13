(async () => {
  const output = document.createElement("pre");
  output.id = "qa-result";
  output.hidden = true;
  document.body.appendChild(output);
  try {
    const before = await storageProof({operation: "read"});
    const initialize = new URLSearchParams(location.search).get("initialize");
    if (initialize) await storageProof({operation: "write", value: initialize});
    const after = await storageProof({operation: "read"});
    const observed = await observeEnvironment({expectedVoiceCount: __EXPECTED_VOICE_COUNT__});
    output.textContent = JSON.stringify({before, after, observed});
  } catch (error) {
    output.textContent = JSON.stringify({error: String(error)});
  }
  output.dataset.complete = "true";
})();
