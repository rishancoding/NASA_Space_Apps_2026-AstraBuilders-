// Capture only ThermaGuard's rendered workspace when the user sends a message.
// Never read other tabs, browser storage, chat history, or hidden page content.
const bytes = (value) => new TextEncoder().encode(JSON.stringify(value)).length;
const visible = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
const clean = (text = "") => text.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
const label = (el) => el.getAttribute("aria-label") ||
  el.getAttribute("aria-labelledby")?.split(" ").map((id) => document.getElementById(id)?.innerText || "").join(" ") ||
  el.labels?.[0]?.innerText || el.getAttribute("placeholder") || el.name || "Setting";

export function captureScreenContext(page, pageLabel) {
  const workspace = document.getElementById("workspace");
  const drawer = document.querySelector('[aria-label="Experiment details"]');
  const context = { page, page_label: pageLabel, captured_at: new Date().toISOString(), truncated: false };
  if (drawer && visible(drawer)) context.selected_test = clean(drawer.innerText).slice(0, 3000);
  context.controls = [...(workspace?.querySelectorAll('input:not([type="password"]):not([type="hidden"]):not([type="range"]), input[type="range"][aria-valuetext], select, [role="combobox"], [aria-pressed="true"]') || [])]
    .filter(visible).slice(0, 30).map((el) => ({
      label: clean(label(el)).slice(0, 96),
      value: clean(el.getAttribute("aria-valuetext") || (el.type === "checkbox" ? String(el.checked) : el.getAttribute("role") === "combobox" || el.hasAttribute("aria-pressed") ? el.innerText : el.value)).slice(0, 160),
    }));
  const text = clean(workspace?.innerText);
  context.page_text = text.slice(0, 6500);
  context.truncated = text.length > context.page_text.length;
  // Keep selected settings and open test details ahead of long result tables.
  while (bytes(context) > 10000) {
    context.truncated = true;
    if (context.page_text.length) context.page_text = context.page_text.slice(0, -300);
    else if (context.selected_test?.length) context.selected_test = context.selected_test.slice(0, -300);
    else context.controls.pop();
  }
  return context;
}

export function buildChatPayload(messages, context) {
  const history = messages.slice(-7).map((m) => ({ ...m, content: m.content.slice(0, 4000) }));
  const payload = { messages: history, context };
  // Fit UTF-8 text and context below the API's 24 KB limit, including long chats.
  while (bytes(payload) > 23000 && history.length > 1) history.splice(0, Math.min(2, history.length - 1));
  while (bytes(payload) > 23000 && payload.context) {
    if (payload.context.page_text) payload.context = { ...payload.context, page_text: payload.context.page_text.slice(0, -300), truncated: true };
    else if (payload.context.selected_test) payload.context = { ...payload.context, selected_test: payload.context.selected_test.slice(0, -300), truncated: true };
    else if (payload.context.controls?.length) payload.context = { ...payload.context, controls: payload.context.controls.slice(0, -1), truncated: true };
    else payload.context = null;
  }
  return payload;
}
