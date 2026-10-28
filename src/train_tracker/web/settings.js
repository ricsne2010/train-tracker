// API keys page: one card per agency that needs a key, with Test and Save.
"use strict";

let state = null;

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

function statusLine(f) {
  const s = f.status;
  if (!s || s.disabled) return { cls: "off", text: "Off: no key saved yet" };
  if (s.last_error && !s.last_ok) return { cls: "bad", text: `Not working: ${s.last_error}` };
  if (s.last_error) return { cls: "warn", text: `Last check failed: ${s.last_error}` };
  if (s.last_ok) return { cls: "ok", text: `Live: ${s.count} train${s.count === 1 ? "" : "s"} on the map` };
  return { cls: "warn", text: "Starting…" };
}

function render() {
  const locked = document.getElementById("locked");
  locked.hidden = state.editable;
  locked.textContent = state.reason || "";
  document.getElementById("where").textContent = `Keys are saved on this computer in ${state.envfile}.`;

  const cards = document.getElementById("cards");
  cards.innerHTML = "";
  for (const f of state.feeds) {
    const st = statusLine(f);
    const card = document.createElement("section");
    card.className = "card";
    card.id = f.id;
    card.innerHTML = `
      <div class="card-head"><h2>${esc(f.agency)}</h2><span class="pill ${st.cls}">${esc(st.text)}</span></div>
      <p>${esc(f.help || "")} ${f.signup ? `<a href="${esc(f.signup)}" target="_blank" rel="noopener">Get a key ↗</a>` : ""}</p>
      ${f.keys.map((k) => `
        <label class="field"><span>${esc(k.label)}</span>
          <input name="${esc(k.var)}" type="${k.secret ? "password" : "text"}" autocomplete="off" spellcheck="false"
            placeholder="${k.saved ? `Saved (${esc(k.saved)}). Type to replace` : "Paste here"}" ${state.editable ? "" : "disabled"}>
        </label>`).join("")}
      <div class="actions">
        <button class="test" ${state.editable ? "" : "disabled"}>Test</button>
        <button class="save primary" ${state.editable ? "" : "disabled"}>Save</button>
        ${f.keys.some((k) => k.saved) ? `<button class="clear" ${state.editable ? "" : "disabled"}>Remove key</button>` : ""}
      </div>
      <p class="result" role="status"></p>`;
    const result = card.querySelector(".result");
    const show = (ok, text) => { result.className = `result ${ok ? "good" : "bad"}`; result.textContent = text; };
    const values = () => {
      const v = {};
      for (const input of card.querySelectorAll("input")) if (input.value.trim()) v[input.name] = input.value.trim();
      return v;
    };
    const busy = (btn, on) => { btn.disabled = on; btn.classList.toggle("busy", on); };

    card.querySelector(".test").addEventListener("click", async (e) => {
      busy(e.target, true); show(true, "Checking with the agency…");
      try {
        const r = await api("api/settings/test", { feed: f.id, values: values() });
        show(r.ok, r.message);
      } catch (err) { show(false, err.message); }
      busy(e.target, false);
    });
    card.querySelector(".save").addEventListener("click", async (e) => {
      const v = values();
      if (!Object.keys(v).length) return show(false, "Paste a key first.");
      busy(e.target, true);
      try {
        state = await api("api/settings", { values: v });
        render();
        flash(f.id, true, "Saved. The feed is starting; its trains appear on the map within a minute.");
      } catch (err) { show(false, err.message); busy(e.target, false); }
    });
    const clear = card.querySelector(".clear");
    if (clear) clear.addEventListener("click", async () => {
      if (!confirm(`Remove the saved ${f.agency} key from this computer?`)) return;
      try {
        state = await api("api/settings", { values: Object.fromEntries(f.keys.map((k) => [k.var, ""])) });
        render();
        flash(f.id, true, "Key removed. This feed is now off.");
      } catch (err) { show(false, err.message); }
    });
    cards.appendChild(card);
  }
  if (location.hash) document.querySelector(location.hash)?.classList.add("focus");
}

function flash(id, ok, text) {
  const r = document.querySelector(`#${id} .result`);
  if (r) { r.className = `result ${ok ? "good" : "bad"}`; r.textContent = text; }
}

async function refresh() {
  try {
    const next = await api("api/settings");
    // keep what the user is typing: only redraw the status pills
    if (state && document.activeElement && document.activeElement.tagName === "INPUT") {
      for (const f of next.feeds) {
        const pill = document.querySelector(`#${f.id} .pill`), st = statusLine(f);
        if (pill) { pill.className = `pill ${st.cls}`; pill.textContent = st.text; }
      }
      state = next;
      return;
    }
    const results = {};
    for (const r of document.querySelectorAll(".result")) results[r.closest(".card").id] = [r.className, r.textContent];
    state = next;
    render();
    for (const [id, [cls, text]] of Object.entries(results)) {
      const r = document.querySelector(`#${id} .result`);
      if (r) { r.className = cls; r.textContent = text; }
    }
  } catch (err) {
    document.getElementById("cards").innerHTML = `<p class="result bad">Couldn't load settings: ${esc(err.message)}</p>`;
  }
}

refresh();
setInterval(refresh, 10000);
