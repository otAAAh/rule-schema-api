// Copyright (C) 2026 Benjamin Knapp
// SPDX-License-Identifier: GPL-2.0-only
//
// Rule schema explorer: a ruleset list (left) and the selected ruleset's value
// schema (right), both read from this package's REST endpoints with the GUI
// session cookie. Plain DOM, no build step. Every text from the server goes
// through textContent - titles and help texts come from third-party packages.
(function () {
  "use strict";

  const API = "api/1.0";
  const root = document.getElementById("rse-app");
  if (!root) return;

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  async function getJson(path) {
    const response = await fetch(`${API}${path}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.title || `HTTP ${response.status}`);
    return body;
  }

  // --- layout -----------------------------------------------------------------
  const search = el("input", { type: "search", class: "rse-search", placeholder: "Search rulesets" });
  const deprecated = el("input", { type: "checkbox" });
  const count = el("span", { class: "rse-count" });
  const list = el("ul", { class: "rse-list" });
  const detail = el("div", { class: "rse-detail" }, el("p", { class: "rse-hint" }, "Select a ruleset."));
  root.append(
    el("div", { class: "rse-layout" },
      el("div", { class: "rse-side" },
        search,
        el("label", { class: "rse-toggle" }, deprecated, " include deprecated"),
        count,
        list),
      detail),
  );

  let rulesets = [];
  let selected = root.dataset.preselect || null;

  const displayName = (r) => r.display_name || r.display_name_en;

  function renderList() {
    const needle = search.value.trim().toLowerCase();
    const hits = rulesets.filter((r) =>
      !needle ||
      [r.ruleset_name, r.display_name_en, r.display_name || ""].some((s) => s.toLowerCase().includes(needle)));
    count.textContent = `${hits.length} of ${rulesets.length}`;
    list.replaceChildren();
    let group = null;
    for (const r of hits) {
      const groupTitle = r.group_display_name || r.group_display_name_en;
      if (groupTitle !== group) {
        group = groupTitle;
        list.append(el("li", { class: "rse-group" }, group));
      }
      list.append(
        el("li", {
          class: "rse-item" + (r.ruleset_name === selected ? " rse-selected" : "") + (r.is_deprecated ? " rse-deprecated" : ""),
          title: r.ruleset_name,
          onclick: () => select(r.ruleset_name),
        },
        displayName(r),
        el("span", { class: "rse-name" }, r.ruleset_name)),
      );
    }
  }

  async function loadList() {
    list.replaceChildren(el("li", { class: "rse-hint" }, "Loading…"));
    try {
      const data = await getJson(
        `/domain-types/rule_schema/collections/all${deprecated.checked ? "?include_deprecated=true" : ""}`);
      rulesets = data.value;
      renderList();
    } catch (error) {
      list.replaceChildren(el("li", { class: "rse-error" }, `Could not load rulesets: ${error.message}`));
    }
  }

  // --- schema tree --------------------------------------------------------------
  function badge(text, cls) {
    return el("span", { class: `rse-badge ${cls || ""}` }, text);
  }

  function nodeMeta(node) {
    const meta = [];
    if (node.min !== undefined) meta.push(`min ${node.min}`);
    if (node.max !== undefined) meta.push(`max ${node.max}`);
    if (node.unit) meta.push(node.unit);
    if (node.pattern) meta.push(`pattern ${node.pattern}`);
    if (node.secret) meta.push("secret");
    if (node.transformed) meta.push("transformed on save");
    if (node.type === "fixed") meta.push(`= ${JSON.stringify(node.value)}`);
    return meta.length ? el("span", { class: "rse-meta" }, meta.join(" · ")) : null;
  }

  function renderNode(node, label) {
    const head = el("div", { class: "rse-node-head" },
      label ? el("code", { class: "rse-key" }, label) : null,
      badge(node.type, `rse-t-${node.type}`),
      node.title ? el("span", { class: "rse-title" }, node.title) : null,
      nodeMeta(node));
    const body = el("div", { class: "rse-node-body" });
    if (node.help) body.append(el("div", { class: "rse-help" }, node.help));

    if (node.type === "dictionary") {
      for (const e of node.elements) {
        const child = renderNode(e.schema, `'${e.key}'`);
        child.firstChild.append(badge(e.required ? "required" : "optional", e.required ? "rse-req" : "rse-opt"));
        body.append(child);
      }
    } else if (node.type === "tuple" || node.type === "alternative") {
      node.elements.forEach((e, i) => body.append(renderNode(e, node.type === "tuple" ? `[${i}]` : `option ${i + 1}`)));
    } else if (node.element) {
      if (node.type === "timespecific") {
        body.append(el("div", { class: "rse-help" },
          `The plain value below, or {'${node.default_key}': <value>, '${node.values_key}': [(<timeperiod>, <value>), …]}`));
      }
      body.append(renderNode(node.element, node.type === "list" ? "[n]" : null));
    } else if (node.choices) {
      const table = el("div", { class: "rse-choices" });
      for (const c of node.choices) {
        const row = el("div", { class: "rse-choice" },
          el("code", {}, JSON.stringify(c.value)), " ", c.title || "");
        table.append(row);
        if (c.schema) table.append(renderNode(c.schema, `(${JSON.stringify(c.value)}, …)`));
      }
      if (node.truncated) table.append(el("div", { class: "rse-hint" }, "… more choices not shown"));
      body.append(table);
    }
    return el("div", { class: "rse-node" }, head, body);
  }

  function copyButton(text) {
    return el("button", {
      class: "rse-copy", type: "button",
      onclick: (ev) => navigator.clipboard.writeText(text).then(() => { ev.target.textContent = "Copied"; }),
    }, "Copy");
  }

  async function select(name) {
    selected = name;
    renderList();
    detail.replaceChildren(el("p", { class: "rse-hint" }, "Loading…"));
    try {
      const s = await getJson(`/objects/rule_schema/${encodeURIComponent(name)}`);
      const curl = `curl -H "Authorization: Bearer $USER $SECRET" \\\n  "${location.origin}${location.pathname.replace(/[^/]*$/, "")}${API}/objects/rule_schema/${encodeURIComponent(name)}"`;
      detail.replaceChildren(
        el("h2", {}, s.display_name || s.display_name_en),
        s.display_name ? el("div", { class: "rse-sub" }, s.display_name_en) : null,
        el("div", { class: "rse-sub" }, el("code", {}, s.ruleset_name), ` · match: ${s.match_type}`,
          s.item_type ? ` · item: ${s.item_name || s.item_type}` : ""),
        s.help ? el("p", { class: "rse-help" }, s.help) : null,
        el("h3", {}, "Example value_raw"),
        s.example_value_raw === null
          ? el("p", { class: "rse-hint" }, "No default value available.")
          : el("div", { class: "rse-code" }, el("pre", {}, s.example_value_raw), copyButton(s.example_value_raw)),
        s.item_schema ? el("h3", {}, "Item") : null,
        s.item_schema ? renderNode(s.item_schema) : null,
        el("h3", {}, "Value schema"),
        renderNode(s.schema),
        el("h3", {}, "REST API"),
        el("div", { class: "rse-code" }, el("pre", {}, curl), copyButton(curl)),
      );
    } catch (error) {
      detail.replaceChildren(el("p", { class: "rse-error" }, `Could not load the schema: ${error.message}`));
    }
  }

  search.addEventListener("input", renderList);
  deprecated.addEventListener("change", loadList);
  loadList().then(() => { if (selected) select(selected); });
})();
