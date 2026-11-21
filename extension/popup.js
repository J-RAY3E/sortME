/* Tabs -> Obsidian: export current window and/or individual Chromium tab groups. */
const $ = (id) => document.getElementById(id);
const say = (text) => { $("msg").textContent = text; };
const stamp = () => new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

async function windowId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab ? tab.windowId : null;
}

async function renderGroups() {
  const box = $("groups");
  if (!chrome.tabGroups) {
    box.innerHTML = '<div class="hint">Tab groups are not available in this browser.</div>';
    return;
  }
  try {
    const win = await windowId();
    const groups = (await chrome.tabGroups.query({})).filter((g) => g.windowId === win);
    if (!groups.length) {
      box.innerHTML = '<div class="hint">No tab groups in this window.</div>';
      return;
    }
    const tabs = await chrome.tabs.query({ windowId: win });
    box.innerHTML = groups.map((g) => {
      const count = tabs.filter((t) => t.groupId === g.id).length;
      const color = g.color && g.color !== "grey" ? g.color : "#888";
      return `<label class="group">
        <input type="checkbox" class="group-check" value="${g.id}">
        <span class="dot" style="background:${escapeHtml(color)}"></span>
        <span class="gname">${escapeHtml(g.title || "Untitled group")}</span>
        <span class="gcount">${count}</span>
      </label>`;
    }).join("");
  } catch (e) {
    box.innerHTML = '<div class="hint">Could not read tab groups.</div>';
  }
}

function selectedGroupIds() {
  return [...document.querySelectorAll(".group-check:checked")].map((el) => Number(el.value));
}

function cleanTabs(tabs) {
  let list = tabs.filter((t) => t.url && /^https?:/i.test(t.url));
  if ($("skip-internal").checked) {
    list = list.filter((t) => !/(localhost|127\.0\.0\.1|chrome:\/\/|chrome-extension:)/i.test(t.url));
  }
  if ($("dedupe").checked) {
    const seen = new Set();
    list = list.filter((t) => {
      const key = t.url.split("#")[0].replace(/\?.*$/, "");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  return list.map((t) => ({
    title: t.title || t.url,
    url: t.url,
    favIconUrl: t.favIconUrl || null,
    groupId: t.groupId >= 0 ? t.groupId : null,
  }));
}

async function collect() {
  const win = await windowId();
  const groups = selectedGroupIds();
  const all = await chrome.tabs.query({ windowId: win });
  const scopes = [];

  if ($("window").checked || !groups.length) {
    scopes.push({ label: "window", group: null, tabs: cleanTabs(all) });
  }
  for (const id of groups) {
    const meta = chrome.tabGroups ? await chrome.tabGroups.get(id).catch(() => null) : null;
    scopes.push({
      label: "group",
      group: { id, title: meta?.title || null, color: meta?.color || null },
      tabs: cleanTabs(all.filter((t) => t.groupId === id)),
    });
  }
  return scopes.filter((s) => s.tabs.length);
}

function payload(scopes) {
  if (scopes.length === 1) {
    const s = scopes[0];
    return [{
      exported_at: new Date().toISOString(),
      source: s.group ? "chrome-group" : "chrome-window",
      group: s.group,
      tabs: s.tabs,
    }];
  }
  return scopes.map((s) => ({
    exported_at: new Date().toISOString(),
    source: s.group ? "chrome-group" : "chrome-window",
    group: s.group,
    tabs: s.tabs,
  }));
}

async function downloadJSON() {
  const scopes = await collect();
  if (!scopes.length) { say("No http(s) tabs in the selected scope."); return; }
  const docs = $("per-group").checked ? payload(scopes) : [payload(scopes)[0]];
  let saved = 0;
  for (const doc of docs) {
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const suffix = doc.group?.title ? "-" + doc.group.title.replace(/[^\w-]+/g, "-").slice(0, 30) : "";
    await chrome.downloads.download({ url, filename: `tabs${suffix}-${stamp()}.json`, saveAs: true });
    URL.revokeObjectURL(url);
    saved++;
  }
  say(`✓ ${saved} file(s) downloaded.`);
}

async function clipboardJSON() {
  const scopes = await collect();
  if (!scopes.length) { say("No http(s) tabs in the selected scope."); return; }
  const docs = $("per-group").checked ? payload(scopes) : [payload(scopes)[0]];
  await navigator.clipboard.writeText(JSON.stringify(docs.length === 1 ? docs[0] : docs, null, 2));
  say(`✓ JSON for ${scopes.reduce((n, s) => n + s.tabs.length, 0)} tabs copied.`);
}

async function clipboardMarkdown() {
  const scopes = await collect();
  if (!scopes.length) { say("No http(s) tabs in the selected scope."); return; }
  const lines = [];
  for (const s of scopes) {
    if (s.group) lines.push(`## ${s.group.title || "Tab group"}`);
    for (const t of s.tabs) lines.push(`- [${t.title}](${t.url})`);
  }
  await navigator.clipboard.writeText(lines.join("\n"));
  say(`✓ Markdown links for ${scopes.reduce((n, s) => n + s.tabs.length, 0)} tabs copied.`);
}

async function refreshCount() {
  const scopes = await collect();
  const n = scopes.reduce((sum, s) => sum + s.tabs.length, 0);
  $("count").textContent = `${n} tab(s) in the selected scope`;
}

document.addEventListener("DOMContentLoaded", async () => {
  await renderGroups();
  for (const id of ["window", "dedupe", "skip-internal"]) {
    $(id).addEventListener("change", refreshCount);
  }
  $("groups").addEventListener("change", refreshCount);
  $("download").addEventListener("click", downloadJSON);
  $("copy-json").addEventListener("click", clipboardJSON);
  $("copy-md").addEventListener("click", clipboardMarkdown);
  await refreshCount();
});
