/* Mudranalaya ERP-MIS frontend. Vanilla JS, no build step. */
const root = document.getElementById("root");
const toastStack = document.getElementById("toastStack");
let CURRENT_USER = null;
let WS = null;

function toast(message, type) {
  type = type || "info";
  const it = document.createElement("div");
  it.className = "toast" + (type === "error" ? " error" : type === "success" ? " success" : "");
  it.textContent = message;
  toastStack.appendChild(it);
  setTimeout(function () { it.remove(); }, 5000);
}
function fmtMoney(v) { return "Rs. " + Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 }); }
function fmtNum(v) { return Number(v || 0).toLocaleString("en-IN"); }

function el(tag, attrs, children) {
  attrs = attrs || {};
  children = children || [];
  const node = document.createElement(tag);
  for (const k in attrs) {
    const v = attrs[k];
    if (k === "class") node.className = v;
    else if (k.indexOf("on") === 0 && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  (Array.isArray(children) ? children : [children]).forEach(function (c) {
    if (c === null || c === undefined) return;
    node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  });
  return node;
}

function dataTable(columns, rows, emptyMessage) {
  emptyMessage = emptyMessage || "No records found.";
  if (!rows || !rows.length) return el("div", { class: "empty-state" }, emptyMessage);
  const thead = el("tr", {}, columns.map(function (c) { return el("th", {}, c.label); }));
  const trs = rows.map(function (row) {
    return el("tr", {}, columns.map(function (c) {
      const cell = c.render ? c.render(row) : (row[c.key] !== undefined ? row[c.key] : "");
      return el("td", {}, cell);
    }));
  });
  return el("table", {}, [el("thead", {}, thead), el("tbody", {}, trs)]);
}

function badge(text, kind) { return el("span", { class: "badge " + (kind || "neutral") }, text); }

const STATUS_KIND_MAP = {
  OK: "ok", GREEN: "ok", APPROVED: "ok", FULFILLED: "ok", DELIVERED: "ok", ACTIVE: "ok", RECEIVED: "ok",
  LOW_STOCK: "warn", SUBMITTED: "warn", PENDING_APPROVAL: "warn", PENDING: "warn", READY: "warn",
  PARTIALLY_FULFILLED: "warn", PARTIALLY_RECEIVED: "warn", ORDERED: "warn", IN_PROGRESS: "warn", PARTIAL: "warn", PAUSED: "warn",
  RED: "danger", REJECTED: "danger", CANCELLED: "danger", REVOKED: "danger", UNDER_MAINTENANCE: "danger",
  COMPLETED: "ok", PASSED: "ok", AVAILABLE: "ok", ASSIGNED: "warn", RUNNING: "ok",
  REWORK_REQUIRED: "danger", FAILED: "danger", BILLED: "ok", DISPATCHED: "ok",
};
function statusBadge(status) { return badge(status, STATUS_KIND_MAP[status] || "neutral"); }
function priorityBadge(p) {
  return badge(p, p === "URGENT" ? "danger" : p === "HIGH" ? "warn" : "neutral");
}

function progressBar(pct) {
  pct = Math.min(100, Math.max(0, pct || 0));
  const bar = el("div", { class: "progress-bar" });
  bar.style.width = pct + "%";
  return el("div", { class: "progress-wrap" }, [bar, el("span", { class: "progress-label" }, pct + "%")]);
}

function openModal(title, formFields, onSubmit, submitLabel) {
  submitLabel = submitLabel || "Save";
  const backdrop = el("div", { class: "modal-backdrop" });
  const inputs = {};
  const fieldNodes = formFields.map(function (f) {
    let input;
    if (f.type === "select") {
      input = el("select", { name: f.name }, (f.options || []).map(function (o) { return el("option", { value: o.value }, o.label); }));
      if (f.value !== undefined) input.value = f.value;
    } else if (f.type === "textarea") {
      input = el("textarea", { name: f.name, rows: 3 }, f.value || "");
    } else if (f.type === "checkbox") {
      input = el("input", { type: "checkbox", name: f.name });
      if (f.value) input.checked = true;
    } else {
      input = el("input", { type: f.type || "text", name: f.name, value: f.value !== undefined ? String(f.value) : "" });
    }
    if (f.disabled) input.disabled = true;
    inputs[f.name] = input;
    return el("div", { class: "form-row" }, [el("label", {}, f.label), input]);
  });
  const closeBtn = el("button", { class: "btn secondary", onclick: function () { backdrop.remove(); } }, "Cancel");
  const saveBtn = el("button", { class: "btn", onclick: async function () {
    const values = {};
    for (const name in inputs) {
      if (inputs[name].type === "checkbox") values[name] = inputs[name].checked;
      else values[name] = inputs[name].value;
    }
    saveBtn.disabled = true;
    try { await onSubmit(values); backdrop.remove(); }
    catch (e) { toast(e.message, "error"); saveBtn.disabled = false; }
  } }, submitLabel);
  const modal = el("div", { class: "modal" }, [
    el("h2", {}, title),
    el("div", { class: "modal-form" }, fieldNodes),
    el("div", { class: "modal-actions" }, [closeBtn, saveBtn]),
  ]);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  return backdrop;
}

function renderLogin() {
  root.innerHTML = "";
  const errorBox = el("div", { class: "error-banner", style: "display:none" });
  const empInput = el("input", { type: "text", id: "loginEmpId", autocomplete: "username" });
  const pwInput = el("input", { type: "password", id: "loginPw", autocomplete: "current-password" });
  async function submit() {
    errorBox.style.display = "none";
    try { await API.login(empInput.value.trim(), pwInput.value); await bootApp(); }
    catch (e) { errorBox.textContent = e.message; errorBox.style.display = "block"; }
  }
  pwInput.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });
  const card = el("div", { class: "login-card" }, [
    el("h1", { class: "brand" }, "Mudranalaya ERP-MIS"),
    el("div", { class: "brand-sub" }, "Government Printing Press — Enterprise Resource Planning"),
    el("label", {}, "Employee ID"), empInput,
    el("label", {}, "Password"), pwInput,
    el("button", { class: "btn login-submit", onclick: submit }, "Sign In"),
    errorBox,
    el("div", { class: "hint-box" }, ["Dev credentials: ", el("code", {}, "MGR001 / Manager@123"), " · ", el("code", {}, "PLN001 / Planning@123"), " · ", el("code", {}, "BIL001 / Billing@123")]),
  ]);
  root.appendChild(el("div", { class: "login-shell" }, card));
}

const NAV_BY_DEPARTMENT = {
  MANAGER: ["dashboard","workorders","planning","materials","requests","purchasing","dispatch","billing","accounts","costing","users","audit","license"],
  SUB_ADMIN: ["dashboard","workorders","planning","materials","requests","purchasing","dispatch","billing","accounts","costing","users","license"],
  STORE: ["dashboard","materials","requests","purchasing"],
  PLANNING: ["dashboard","workorders","planning","materials","requests"],
  DISPATCH: ["dashboard","workorders","dispatch"],
  ACCOUNTS: ["dashboard","purchasing","accounts","costing"],
  EMPLOYEE: ["dashboard","requests"],
  DIGITAL_PRINTING: ["dashboard","workorders"],
  TRADITIONAL_PRINTING: ["dashboard","workorders"],
  PLATE_MAKING: ["dashboard","workorders"],
  BINDING: ["dashboard","workorders"],
  STANDARD: ["dashboard","workorders"],
  BILLING: ["dashboard","workorders","billing"],
  MECHANIC: ["dashboard"],
};
const NAV_LABELS = {
  dashboard:"Dashboard", workorders:"Work Orders", planning:"Planning",
  materials:"Materials & Inventory", requests:"Material Requests",
  purchasing:"Suppliers & Purchases", dispatch:"Dispatch", billing:"Billing",
  accounts:"Accounts & Budgets", costing:"Costing", users:"Users",
  audit:"Audit Log", license:"License & Devices",
};

let activeView = "dashboard";
let activeJobId = null;

function renderShell() {
  root.innerHTML = "";
  const dept = CURRENT_USER.department_code;
  const allowed = NAV_BY_DEPARTMENT[dept] || ["dashboard"];
  const nav = el("div", { class: "nav" }, allowed.map(function (view) {
    return el("button", { class: "nav-item" + (view === activeView ? " active" : ""), onclick: function () { activeJobId = null; activeView = view; renderShell(); } },
      el("span", { class: "label" }, NAV_LABELS[view]));
  }));
  const sidebar = el("div", { class: "sidebar" }, [
    el("div", { class: "sidebar-brand" }, [
      el("div", { class: "sidebar-title" }, "Mudranalaya"),
      el("div", { class: "sidebar-sub" }, "Government Printing Press"),
      el("div", { class: "dept-tag" }, (CURRENT_USER.department_name || dept).toUpperCase()),
    ]),
    nav,
    el("div", { class: "sidebar-footer" }, [
      el("span", { class: "status-dot " + (WS && WS.readyState === 1 ? "live" : "offline") }),
      WS && WS.readyState === 1 ? "Live" : "Offline",
    ]),
  ]);
  const topbar = el("div", { class: "topbar" }, [
    el("div", { class: "topbar-left" }, [el("strong", {}, CURRENT_USER.full_name), el("span", { class: "topbar-dept" }, " · " + (CURRENT_USER.department_name || dept))]),
    el("div", { class: "topbar-right" }, [
      el("span", { class: "topbar-empid" }, CURRENT_USER.employee_id),
      el("button", { class: "btn secondary sm", onclick: async function () { await API.logout(); location.reload(); } }, "Sign Out"),
    ]),
  ]);
  const content = el("div", { class: "content", id: "content" });
  root.appendChild(el("div", { class: "app-shell" }, [sidebar, el("div", { class: "main" }, [topbar, content])]));
  renderView(activeView, content);
}

function pageHeader(title, subtitle) {
  return [el("h1", { class: "page-title" }, title), el("p", { class: "page-sub" }, subtitle)];
}

async function renderView(view, content) {
  content.innerHTML = "";
  content.appendChild(el("div", { class: "empty-state" }, "Loading…"));
  try {
    const renderers = {
      dashboard: renderDashboard, workorders: renderWorkOrders, planning: renderPlanningDashboard,
      materials: renderMaterials, requests: renderRequests, purchasing: renderPurchasing,
      dispatch: renderDispatch, billing: renderBilling, accounts: renderAccounts,
      costing: renderCosting, users: renderUsers, audit: renderAudit, license: renderLicense,
    };
    content.innerHTML = "";
    if (renderers[view]) await renderers[view](content);
    else content.appendChild(el("div", { class: "empty-state" }, "View not found."));
  } catch (e) {
    content.innerHTML = "";
    content.appendChild(el("div", { class: "error-banner" }, e.message));
    console.error(e);
  }
}

/* DASHBOARD */
async function renderDashboard(content) {
  const data = await API.get("/api/dashboard");
  content.append.apply(content, pageHeader("Dashboard", "Live summary for " + (data.scope || "your department").replace(/_/g, " ")));
  const labelMap = {
    total_materials:"Total Materials", low_stock_count:"Low Stock Items", out_of_stock_count:"Out of Stock",
    inventory_value:"Inventory Value", pending_material_requests:"Pending Material Requests",
    pending_purchase_orders:"Pending Purchase Orders", total_recorded_spend:"Total Recorded Spend",
    open_production_jobs:"Open Production Jobs", pending_dispatch_orders:"Pending Dispatch Orders",
    my_open_jobs:"My Open Jobs", my_pending_requests:"My Pending Requests",
    budget_lines:"Budget Lines", my_requests:"My Requests",
  };
  const cards = [];
  for (const key in labelMap) {
    if (!(key in data)) continue;
    let value = data[key];
    if (key.indexOf("value") !== -1 || key.indexOf("spend") !== -1) value = fmtMoney(value);
    cards.push(el("div", { class: "kpi-card" }, [el("div", { class: "kpi-value" }, String(value)), el("div", { class: "kpi-label" }, labelMap[key])]));
  }
  content.appendChild(el("div", { class: "kpi-grid" }, cards));
}

/* WORK ORDERS */
async function renderWorkOrders(content) {
  if (activeJobId) return renderWorkOrderDetail(content, activeJobId);
  content.append.apply(content, pageHeader("Work Orders", "All production jobs with live workflow status."));
  const searchInput = el("input", { type: "text", placeholder: "Search job #, client, work…", style: "width:240px" });
  const statusSel = el("select", { style: "width:160px" }, [
    el("option", { value: "" }, "All Statuses"),
    ...["PLANNED","IN_PROGRESS","PARTIAL","PAUSED","COMPLETED","CANCELLED"].map(function (s) { return el("option", { value: s }, s.replace("_"," ")); })
  ]);
  const prioritySel = el("select", { style: "width:130px" }, [
    el("option", { value: "" }, "All Priorities"),
    ...["URGENT","HIGH","NORMAL","LOW"].map(function (p) { return el("option", { value: p }, p); })
  ]);
  let currentPage = 1;
  const tableContainer = el("div", {});
  const paginationContainer = el("div", { class: "pagination-bar" });

  async function loadJobs() {
    const q = [
      searchInput.value ? "search=" + encodeURIComponent(searchInput.value) : "",
      statusSel.value ? "status=" + statusSel.value : "",
      prioritySel.value ? "priority=" + prioritySel.value : "",
      "page=" + currentPage, "page_size=50",
    ].filter(Boolean).join("&");
    const data = await API.get("/api/planning/jobs?" + q);
    tableContainer.innerHTML = "";
    tableContainer.appendChild(buildWorkOrderTable(data.jobs || []));
    paginationContainer.innerHTML = "";
    if (data.pagination && data.pagination.pages > 1) {
      paginationContainer.appendChild(buildPagination(data.pagination, function (p) { currentPage = p; loadJobs(); }));
    }
  }

  let searchTimer;
  searchInput.addEventListener("input", function () { clearTimeout(searchTimer); searchTimer = setTimeout(function () { currentPage = 1; loadJobs(); }, 400); });
  statusSel.addEventListener("change", function () { currentPage = 1; loadJobs(); });
  prioritySel.addEventListener("change", function () { currentPage = 1; loadJobs(); });

  const canCreate = ["PLANNING","MANAGER","SUB_ADMIN"].indexOf(CURRENT_USER.department_code) !== -1;
  const toolbar = el("div", { class: "toolbar" }, [
    searchInput, statusSel, prioritySel, el("div", { class: "spacer" }),
    canCreate ? el("button", { class: "btn", onclick: function () { openNewJobModal(loadJobs); } }, "+ New Work Order") : null,
  ].filter(Boolean));
  content.append(el("div", { class: "panel" }, [toolbar, tableContainer, paginationContainer]));
  await loadJobs();
}

function buildWorkOrderTable(jobs) {
  if (!jobs || !jobs.length) return el("div", { class: "empty-state" }, "No work orders found.");
  const thead = el("tr", {}, ["Work Order","Description / Client","Ordered","Produced","Remaining","Progress","Current Stage","Department","Machine","Priority","Status",""].map(function (h) { return el("th", {}, h); }));
  const trs = jobs.map(function (j) {
    const stage = j.current_stage || {};
    const rowClass = j.paused ? "row-paused" : j.priority === "URGENT" ? "row-urgent" : "";
    return el("tr", { class: rowClass }, [
      el("td", {}, el("button", { class: "link-btn", onclick: function () { activeJobId = j.id; renderView(activeView, document.getElementById("content")); } }, j.job_number)),
      el("td", {}, [el("div", { class: "job-work-name" }, j.work_name), el("div", { class: "job-client" }, j.client_name)]),
      el("td", { class: "num-cell" }, fmtNum(j.copies)),
      el("td", { class: "num-cell ok-text" }, fmtNum(j.total_produced)),
      el("td", { class: "num-cell" + (j.remaining > 0 ? " warn-text" : "") }, fmtNum(j.remaining)),
      el("td", { style: "min-width:110px" }, progressBar(j.progress_pct)),
      el("td", {}, el("span", { class: "stage-badge stage-" + (stage.stage_code || "").toLowerCase() }, (stage.icon || "○") + " " + (stage.stage_label || "-"))),
      el("td", {}, el("span", { class: "dept-label" }, j.department || "-")),
      el("td", {}, el("span", { class: "machine-label" }, j.machine_name ? j.machine_name.split(" ").slice(0,2).join(" ") : "-")),
      el("td", {}, priorityBadge(j.priority)),
      el("td", {}, statusBadge(j.status)),
      el("td", {}, el("button", { class: "btn secondary sm", onclick: function () { activeJobId = j.id; renderView(activeView, document.getElementById("content")); } }, "View")),
    ]);
  });
  return el("table", { class: "wo-table" }, [el("thead", {}, thead), el("tbody", {}, trs)]);
}

function buildPagination(pagination, onPage) {
  const btns = [];
  if (pagination.page > 1) btns.push(el("button", { class: "btn secondary sm", onclick: function () { onPage(pagination.page - 1); } }, "Prev"));
  btns.push(el("span", { class: "page-info" }, "Page " + pagination.page + " of " + pagination.pages + " (" + pagination.total + " total)"));
  if (pagination.page < pagination.pages) btns.push(el("button", { class: "btn secondary sm", onclick: function () { onPage(pagination.page + 1); } }, "Next"));
  return el("div", { class: "pagination-bar" }, btns);
}

/* WORK ORDER DETAIL */
async function renderWorkOrderDetail(content, jobId) {
  const detail = await API.get("/api/planning/jobs/" + jobId + "/detail");
  const backBtn = el("button", { class: "btn secondary sm", onclick: function () { activeJobId = null; renderView(activeView, content); } }, "Back to Work Orders");
  const isPaused = detail.status === "PAUSED";
  const isUrgent = detail.priority === "URGENT";

  const headerPanel = el("div", { class: "wo-detail-header panel" + (isPaused ? " paused-banner" : "") }, [
    el("div", { class: "wo-detail-meta" }, [
      el("div", { class: "wo-number" }, detail.job_number),
      isUrgent ? el("span", { class: "urgent-tag" }, "URGENT") : null,
      isPaused ? el("span", { class: "paused-tag" }, "PAUSED") : null,
    ].filter(Boolean)),
    el("div", { class: "wo-detail-grid" }, [
      el("div", {}, [el("div", { class: "detail-label" }, "Work Description"), el("div", { class: "detail-value" }, detail.work_name)]),
      el("div", {}, [el("div", { class: "detail-label" }, "Client"), el("div", { class: "detail-value" }, detail.client_name)]),
      el("div", {}, [el("div", { class: "detail-label" }, "Pages"), el("div", { class: "detail-value" }, detail.pages || "-")]),
      el("div", {}, [el("div", { class: "detail-label" }, "Priority"), el("div", { class: "detail-value" }, [priorityBadge(detail.priority)])]),
      el("div", {}, [el("div", { class: "detail-label" }, "Status"), el("div", { class: "detail-value" }, [statusBadge(detail.status)])]),
      detail.deadline ? el("div", {}, [el("div", { class: "detail-label" }, "Deadline"), el("div", { class: "detail-value" }, detail.deadline.slice(0, 10))]) : null,
    ].filter(Boolean)),
    isPaused && detail.planning && detail.planning.pause_reason ? el("div", { class: "pause-reason-box" }, [el("strong", {}, "Pause Reason: "), detail.planning.pause_reason]) : null,
  ].filter(Boolean));

  const qtySection = el("div", { class: "qty-section panel" }, [
    el("h2", {}, "Production Quantity"),
    el("div", { class: "qty-grid" }, [
      el("div", { class: "qty-card" }, [el("div", { class: "qty-val" }, fmtNum(detail.copies)), el("div", { class: "qty-lbl" }, "Ordered")]),
      el("div", { class: "qty-card ok" }, [el("div", { class: "qty-val" }, fmtNum(detail.total_produced)), el("div", { class: "qty-lbl" }, "Produced")]),
      el("div", { class: "qty-card" + (detail.remaining_quantity > 0 ? " warn" : "") }, [el("div", { class: "qty-val" }, fmtNum(detail.remaining_quantity)), el("div", { class: "qty-lbl" }, "Remaining")]),
      el("div", { class: "qty-card" }, [el("div", { class: "qty-val" }, fmtNum(detail.dispatched_quantity || 0)), el("div", { class: "qty-lbl" }, "Dispatched")]),
      el("div", { class: "qty-card" }, [el("div", { class: "qty-val" }, fmtNum(detail.billing ? detail.billing.total_billed : 0)), el("div", { class: "qty-lbl" }, "Billed")]),
    ]),
    el("div", { class: "progress-section" }, [
      el("div", { class: "progress-label-row" }, [el("span", {}, "Production Progress"), el("strong", {}, fmtNum(detail.total_produced) + " / " + fmtNum(detail.copies) + " (" + (detail.progress_pct || 0) + "%)")]),
      el("div", { class: "progress-track" }, [(() => { const d = el("div", { class: "progress-fill" }); d.style.width = (detail.progress_pct || 0) + "%"; return d; })()]),
    ]),
  ]);

  const page1 = buildPage1BookWorkOrder(detail);
  const page2 = buildPage2ProgressReport(detail);
  const planningPanel = buildPlanningInfoSection(detail);
  const batchesPanel = buildBatchesSection(detail);
  const historyPanel = buildWorkflowHistorySection(detail);
  const actionsPanel = buildActionPanel(detail, content);
  content.append(backBtn, headerPanel, qtySection, page1, page2, planningPanel, batchesPanel, historyPanel, actionsPanel);
}

function buildPage1BookWorkOrder(detail) {
  const p = detail.planning || {};
  const t1 = el("table", { class: "maha-form-table" }, [
    el("tbody", {}, [
      el("tr", {}, [el("th", {style:"width:25%"}, "मागणी अधिकारी (Demand Officer)"), el("td", {}, detail.client_name || "-")]),
      el("tr", {}, [el("th", {}, "कामाचे वर्णन (Work Description)"), el("td", {}, detail.work_name || "-")])
    ])
  ]);

  const t2 = el("table", { class: "maha-form-table" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", {}, "एकूण मूळप्रती (Original Copies)"), el("th", {}, "एकूण पृष्ठे (Total Pages)"),
      el("th", {}, "पहिल्या वाचनासाठी पाठविल्याचा दिनांक"), el("th", {}, "मुद्रिते तपासणीसाठी पाठविल्याचा दिनांक"),
      el("th", {}, "संच प्लेटमेकिंगसाठी पाठविल्याचा दिनांक")
    ])]),
    el("tbody", {}, [el("tr", {}, [
      el("td", {}, fmtNum(detail.copies)), el("td", {}, detail.pages || "-"),
      el("td", {}, "-"), el("td", {}, "-"), el("td", {}, "-")
    ])])
  ]);

  const t3 = el("table", { class: "maha-form-table" }, [
    el("tbody", {}, [
      el("tr", {}, [el("th", {style:"width:25%"}, "मुद्रणविषयक सूचना (Printing)"), el("td", {}, [
        el("div", {}, "कागदाचा आकार आणि दर्जा: " + (p.paper_name ? p.paper_name + " " + (p.paper_gsm ? p.paper_gsm + " GSM" : "") : "-")),
        el("div", {}, "मुद्रण करावयाचे आहे: " + (p.printing_method ? p.printing_method.replace(/_/g," ") : "-"))
      ])]),
      el("tr", {}, [el("th", {}, "बांधणीविषयक सूचना (Binding)"), el("td", {}, detail.finishing ? detail.finishing.method.replace(/_/g," ") : "-")]),
      el("tr", {}, [el("th", {}, "जावकविषयक सूचना (Dispatch)"), el("td", {}, "एकूण प्रती: " + fmtNum(detail.copies))])
    ])
  ]);

  return el("div", { class: "panel maha-form-panel page-panel" }, [
    el("div", { class: "page-header-box" }, [
      el("div", { class: "page-title-main" }, "शासकीय मध्यवर्ती मुद्रणालय मुंबई ४०० ००४"),
      el("div", { class: "page-title-sub" }, "पुस्तक कार्यादेश (Book Work Order)"),
      el("div", { class: "page-meta-row" }, [
         el("span", {}, "क्रमांक (No.): " + detail.job_number),
         el("span", {}, "दिनांक (Date): " + (detail.created_at ? detail.created_at.slice(0,10) : "-"))
      ])
    ]),
    el("div", { class: "page-label" }, "PAGE 1"),
    el("div", { class: "maha-form-section" }, t1),
    el("div", { class: "maha-form-section" }, [el("div", { class: "maha-form-title" }, "डी.टी.पी. विभाग"), t2]),
    el("div", { class: "maha-form-section" }, t3)
  ]);
}

function buildPage2ProgressReport(detail) {
  const currentStageCode = (detail.current_stage || {}).stage_code || "";
  function getStageDate(code) {
    const s = (detail.workflow_stages || []).find(function(st) { return st.code === code; });
    return s && s.date ? s.date : "-";
  }
  function getCellClass(code) {
    const s = (detail.workflow_stages || []).find(function(st) { return st.code === code; });
    if (currentStageCode === code) return "active-stage-cell";
    if (s && s.status === "COMPLETED") return "completed-stage-cell";
    return "";
  }

  const dtpTable = el("table", { class: "maha-form-table" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", {}, "मूळप्रती"), el("th", {}, "प्रथम वाचनासाठी"), el("th", {}, "दुसऱ्या वाचनासाठी"),
      el("th", {}, "मान्यताप्राप्त मुद्रिते"), el("th", {}, "अंतिम मुद्रणासाठी"), el("th", {}, "यंत्र विभागात पाठविल्याचा दिनांक")
    ])]),
    el("tbody", {}, [el("tr", {}, [
      el("td", {}, fmtNum(detail.copies)),
      el("td", { class: getCellClass("PLANNING") }, getStageDate("PLANNING")),
      el("td", {}, "-"),
      el("td", {}, "-"),
      el("td", { class: getCellClass("PLATE_MAKING") }, getStageDate("PLATE_MAKING")),
      el("td", { class: getCellClass("PRINTING") }, getStageDate("PRINTING"))
    ])])
  ]);

  const p = detail.planning || {};
  const pressTable = el("table", { class: "maha-form-table", style: "height: 100%" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", {}, "यंत्र (Machine)"), el("th", {}, "कागदाचे वर्णन"), el("th", {}, "प्रमाण (Quantity)"), el("th", {}, "सही व दिनांक")
    ])]),
    el("tbody", {}, [el("tr", {}, [
      el("td", { class: getCellClass("PRINTING") }, p.machine_name ? (p.machine_name + " [" + p.machine_code + "]") : "-"),
      el("td", { class: getCellClass("PRINTING") }, p.paper_name ? (p.paper_name + (p.paper_gsm ? " " + p.paper_gsm + " GSM" : "")) : "-"),
      el("td", { class: getCellClass("PRINTING") }, p.paper_quantity_allocated ? fmtNum(p.paper_quantity_allocated) : (p.paper_quantity_required ? fmtNum(p.paper_quantity_required) : "-")),
      el("td", { class: getCellClass("PRINTING") }, p.planned_start ? p.planned_start.slice(0, 10) : "-")
    ])])
  ]);

  const costTable = el("table", { class: "maha-form-table summary-table", style: "height: 100%" }, [
    el("thead", {}, [el("tr", {}, [el("th", { colspan: 2 }, "क्रियामूल्य सारांश (Cost Summary)")])]),
    el("tbody", {}, [
      el("tr", {}, [el("td", {}, "हस्त/एक मुळाक्षर/पंक्ती प्रथम दुरुस्ती"), el("td", {}, "-")]),
      el("tr", {}, [el("td", {}, "चित्रठसे / संकल्पन / चकाकी"), el("td", {}, "-")]),
      el("tr", {}, [el("td", {}, "यंत्र/मुद्रितक आणि छपाई (Printing)"), el("td", { class: getCellClass("PRINTING") }, "-")]),
      el("tr", {}, [el("td", {}, "बांधणी क्रिया (Binding)"), el("td", { class: getCellClass("BINDING") }, detail.finishing ? detail.finishing.method.replace(/_/g," ") : "-")]),
      el("tr", {}, [el("td", {}, "कागद (Paper)"), el("td", {}, p.paper_name || "-")]),
      el("tr", {}, [el("td", {}, "आवेष्टन / जावक (Dispatch)"), el("td", { class: getCellClass("DISPATCH") }, fmtNum(detail.dispatched_quantity || 0))]),
      el("tr", {}, [el("td", {}, el("strong", {}, "एकूण रुपये (Total)")), el("td", {}, "-")])
    ])
  ]);

  const splitSection = el("div", { style: "display: flex; gap: 16px; align-items: stretch;" }, [
    el("div", { style: "flex: 1;" }, [el("div", { class: "maha-form-title" }, "यंत्र आणि मुद्रित शोधन विभागाचे प्रगतिपत्रक"), pressTable]),
    el("div", { style: "flex: 1;" }, costTable)
  ]);

  return el("div", { class: "panel maha-form-panel page-panel" }, [
    el("div", { class: "page-label" }, "PAGE 2"),
    el("div", { class: "maha-form-section", style: "margin-top: 16px;" }, [
      el("div", { class: "maha-form-title" }, "डी.टी.पी. आणि मुद्रित शोधन विभागाचे प्रगतिपत्रक"),
      dtpTable
    ]),
    el("div", { class: "maha-form-section" }, splitSection)
  ]);
}

function buildPlanningInfoSection(detail) {
  const p = detail.planning;
  if (!p) return el("div", { class: "panel" }, [el("h2", {}, "Planning"), el("div", { class: "empty-state" }, "No planning assignment yet.")]);
  const rows = [
    ["Printing Method", p.printing_method || "-"], ["Department", p.department || "-"],
    ["Machine", p.machine_name ? p.machine_name + " (" + p.machine_code + ")" : "-"],
    ["Machine Status", p.machine_status || "-"],
    ["Paper", p.paper_name ? p.paper_name + (p.paper_gsm ? " — " + p.paper_gsm + " GSM" : "") : "-"],
    ["Paper Required", p.paper_quantity_required ? fmtNum(p.paper_quantity_required) + " sheets" : "-"],
    ["Plate Required", p.plate_required ? "Yes" : "No"], ["Financial Year", p.financial_year || "-"],
    ["Planned Start", p.planned_start ? p.planned_start.slice(0,10) : "-"],
    ["Planned End", p.planned_end ? p.planned_end.slice(0,10) : "-"],
    ["Remarks", p.remarks || "-"],
  ];
  return el("div", { class: "panel" }, [el("h2", {}, "Planning Assignment"), el("div", { class: "info-grid" }, rows.map(function (r) {
    return el("div", { class: "info-row" }, [el("div", { class: "info-label" }, r[0]), el("div", { class: "info-value" }, r[1])]);
  }))]);
}

function buildBatchesSection(detail) {
  const batches = detail.batches || [];
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "Production Batches (" + batches.length + ")"));
  if (!batches.length) { panel.appendChild(el("div", { class: "empty-state" }, "No production batches recorded yet.")); return panel; }
  panel.appendChild(dataTable([
    { label: "Batch #", key: "batch_number" },
    { label: "Quantity", render: function (b) { return el("strong", {}, fmtNum(b.quantity_produced)); } },
    { label: "Department", key: "department" }, { label: "Financial Year", key: "financial_year" },
    { label: "Started", render: function (b) { return b.started_at ? b.started_at.slice(0,10) : "-"; } },
    { label: "Completed", render: function (b) { return b.completed_at ? b.completed_at.slice(0,10) : "-"; } },
    { label: "Remarks", key: "remarks" },
  ], batches));
  return panel;
}

function buildWorkflowHistorySection(detail) {
  const hist = detail.workflow_history || [];
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "Workflow History"));
  if (!hist.length) { panel.appendChild(el("div", { class: "empty-state" }, "No history recorded.")); return panel; }
  const items = hist.map(function (h) {
    const isNeg = h.to_status === "PAUSED" || h.to_status === "CANCELLED";
    const isPos = h.to_status === "COMPLETED";
    return el("div", { class: "timeline-item" + (isNeg ? " tl-warn" : isPos ? " tl-ok" : "") }, [
      el("div", { class: "tl-dot" }),
      el("div", { class: "tl-body" }, [
        el("div", { class: "tl-time" }, h.changed_at ? h.changed_at.slice(0,19).replace("T"," ") : "-"),
        el("div", { class: "tl-status" }, (h.from_status ? h.from_status + " → " : "") + (h.to_status || "")),
        h.reason ? el("div", { class: "tl-reason" }, h.reason) : null,
      ].filter(Boolean)),
    ]);
  });
  panel.appendChild(el("div", { class: "timeline" }, items));
  return panel;
}

function buildActionPanel(detail, content) {
  const dept = CURRENT_USER.department_code;
  const buttons = [];
  if (dept === "PLANNING" || dept === "MANAGER" || dept === "SUB_ADMIN") {
    buttons.push(el("button", { class: "btn " + (!detail.planning ? "" : "secondary"), onclick: function () { openPlanningModal(detail, content); } }, (detail.planning ? "Edit" : "Assign") + " Planning"));
    if (detail.status === "IN_PROGRESS" || detail.status === "PARTIAL")
      buttons.push(el("button", { class: "btn warn-btn", onclick: function () { openPauseModal(detail, content); } }, "Pause Job"));
    if (detail.status === "PAUSED")
      buttons.push(el("button", { class: "btn ok-btn", onclick: function () { openResumeModal(detail, content); } }, "Resume Job"));
  }
  if (["PLANNING","DIGITAL_PRINTING","TRADITIONAL_PRINTING","MANAGER","SUB_ADMIN"].indexOf(dept) !== -1) {
    if (detail.status !== "COMPLETED" && detail.status !== "CANCELLED" && detail.status !== "PAUSED")
      buttons.push(el("button", { class: "btn", onclick: function () { openRecordBatchModal(detail, content); } }, "Record Production"));
  }
  if ((dept === "PLATE_MAKING" || dept === "PLANNING") && detail.plate_making && detail.plate_making.status !== "COMPLETED")
    buttons.push(el("button", { class: "btn secondary", onclick: function () { openPlateModal(detail, content); } }, "Update Plate Status"));
  if (dept === "BINDING" || dept === "PLANNING") {
    if (!detail.finishing) buttons.push(el("button", { class: "btn secondary", onclick: function () { openBindingModal(detail, content); } }, "Start Binding"));
    else if (!detail.finishing.is_complete) buttons.push(el("button", { class: "btn secondary", onclick: function () { openBindingUpdateModal(detail, content); } }, "Update Binding"));
  }
  if (dept === "STANDARD" || dept === "PLANNING") {
    if (!detail.inspection) buttons.push(el("button", { class: "btn secondary", onclick: function () { openInspectionModal(detail, content); } }, "Create Inspection"));
    else if (detail.inspection.status !== "PASSED") buttons.push(el("button", { class: "btn secondary", onclick: function () { openInspectionDecideModal(detail, content); } }, "Inspection Decision"));
  }
  if (!buttons.length) return el("div", {});
  return el("div", { class: "panel action-panel" }, [el("h2", {}, "Actions"), el("div", { class: "action-btns" }, buttons)]);
}

async function openPlanningModal(detail, content) {
  const [machines, materials] = await Promise.all([API.get("/api/machines?active_only=true"), API.get("/api/materials")]);
  const pa = detail.planning || {};
  const fy = new Date().getFullYear();
  openModal("Planning Assignment — " + detail.job_number, [
    { name: "printing_method", label: "Printing Method", type: "select", options: [
      {value:"DIGITAL",label:"Digital"},{value:"OFFSET",label:"Offset / Traditional"},{value:"KOMORI",label:"Komori"},{value:"SCREEN",label:"Screen"},{value:"OTHER",label:"Other"}
    ], value: pa.printing_method || "OFFSET" },
    { name: "department_code", label: "Department", type: "select", options: [
      {value:"DIGITAL_PRINTING",label:"Digital Printing"},{value:"TRADITIONAL_PRINTING",label:"Traditional / Offset"},{value:"PLATE_MAKING",label:"Plate Making"}
    ], value: pa.department || "TRADITIONAL_PRINTING" },
    { name: "machine_id", label: "Machine", type: "select", options: [{value:"",label:"— Select Machine —"}].concat(machines.map(function (m) { return {value:m.id,label:m.name+" ["+m.status+"]"}; })), value: pa.machine_id || "" },
    { name: "paper_material_id", label: "Paper / Material", type: "select", options: [{value:"",label:"— None —"}].concat(materials.filter(function (m) { return m.unit === "SHEET" || (m.name||"").toLowerCase().includes("paper"); }).map(function (m) { return {value:m.id,label:m.name+(m.gsm?" "+m.gsm+" GSM":"")+" ("+fmtNum(m.current_stock)+")"}; })) },
    { name: "paper_quantity_required", label: "Paper Quantity (sheets)", type: "number", value: pa.paper_quantity_required || "" },
    { name: "plate_required", label: "Plate / Pre-press Required", type: "checkbox", value: pa.plate_required !== false },
    { name: "financial_year", label: "Financial Year", value: pa.financial_year || ((fy-1)+"-"+String(fy).slice(-2)) },
    { name: "planned_start_date", label: "Planned Start", type: "date" },
    { name: "planned_end_date", label: "Target End", type: "date" },
    { name: "planning_remarks", label: "Remarks", type: "textarea", value: pa.remarks || "" },
  ], async function (v) {
    await API.post("/api/planning/jobs/" + detail.id + "/assign", {
      printing_method: v.printing_method || null, department_code: v.department_code || null,
      machine_id: v.machine_id || null, paper_material_id: v.paper_material_id || null,
      paper_quantity_required: v.paper_quantity_required ? Number(v.paper_quantity_required) : null,
      plate_required: v.plate_required === true || v.plate_required === "true",
      financial_year: v.financial_year || null, planned_start_date: v.planned_start_date || null,
      planned_end_date: v.planned_end_date || null, planning_remarks: v.planning_remarks || null,
    });
    toast("Planning assignment saved", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Save Planning");
}

async function openPauseModal(detail, content) {
  const pauseReasons = [
    {value:"URGENT_ORDER",label:"Urgent Government Order"},{value:"MACHINE_BREAKDOWN",label:"Machine Breakdown"},
    {value:"MATERIAL_UNAVAILABLE",label:"Material Unavailable"},{value:"PLANNING_DECISION",label:"Planning Decision"},{value:"OTHER",label:"Other"},
  ];
  openModal("Pause Work Order — " + detail.job_number, [
    { name: "reason_code", label: "Reason", type: "select", options: pauseReasons },
    { name: "reason_detail", label: "Additional Details", type: "textarea" },
  ], async function (v) {
    const reason = pauseReasons.find(function (r) { return r.value === v.reason_code; });
    await API.post("/api/planning/jobs/" + detail.id + "/pause", { reason: (reason ? reason.label : v.reason_code) + (v.reason_detail ? ": " + v.reason_detail : "") });
    toast("Job paused", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Pause Job");
}

async function openResumeModal(detail, content) {
  const machines = await API.get("/api/machines?active_only=true");
  openModal("Resume Work Order — " + detail.job_number, [
    { name: "machine_id", label: "Machine (optional change)", type: "select", options: [{value:"",label:"Keep current"}].concat(machines.filter(function (m) { return m.status === "AVAILABLE"; }).map(function (m) { return {value:m.id,label:m.name}; })) },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ], async function (v) {
    await API.post("/api/planning/jobs/" + detail.id + "/resume", { machine_id: v.machine_id || null, remarks: v.remarks || null });
    toast("Job resumed", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Resume Job");
}

async function openRecordBatchModal(detail, content) {
  const remaining = detail.remaining_quantity || 0;
  const fy = new Date().getFullYear();
  openModal("Record Production — " + detail.job_number, [
    { name: "quantity_produced", label: "Quantity Produced (Remaining: " + fmtNum(remaining) + ")", type: "number", value: remaining > 0 ? String(remaining) : "" },
    { name: "financial_year", label: "Financial Year", value: detail.planning ? (detail.planning.financial_year || ((fy-1)+"-"+String(fy).slice(-2))) : "" },
    { name: "started_at", label: "Start Date", type: "date", value: new Date().toISOString().slice(0,10) },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ], async function (v) {
    if (!v.quantity_produced || Number(v.quantity_produced) <= 0) throw new Error("Enter a valid quantity");
    await API.post("/api/planning/jobs/" + detail.id + "/batches", {
      quantity_produced: Number(v.quantity_produced), financial_year: v.financial_year || null,
      started_at: v.started_at || null, remarks: v.remarks || null,
    });
    toast("Production batch recorded", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Record Production");
}

async function openPlateModal(detail, content) {
  const plate = detail.plate_making || {};
  openModal("Update Plate Making — " + detail.job_number, [
    { name: "status", label: "Status", type: "select", options: [
      {value:"PENDING",label:"Pending"},{value:"IN_PROGRESS",label:"In Progress"},{value:"COMPLETED",label:"Completed"},{value:"FAILED",label:"Failed"}
    ], value: plate.status || "IN_PROGRESS" },
    { name: "plate_count", label: "Plate Count", type: "number", value: plate.plate_count || "" },
    { name: "plate_size", label: "Plate Size", value: plate.plate_size || "" },
    { name: "completed_at", label: "Completed Date", type: "date", value: plate.completed_at ? plate.completed_at.slice(0,10) : "" },
    { name: "remarks", label: "Remarks", type: "textarea", value: plate.remarks || "" },
  ], async function (v) {
    await API.put("/api/plate-making/" + plate.id, {
      status: v.status, plate_count: v.plate_count ? Number(v.plate_count) : null,
      plate_size: v.plate_size || null, completed_at: v.completed_at || null, remarks: v.remarks || null,
    });
    toast("Plate status updated", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Update Plate");
}

async function openBindingModal(detail, content) {
  openModal("Start Binding — " + detail.job_number, [
    { name: "finishing_method", label: "Binding Method", type: "select", options: [
      {value:"STITCHING",label:"Stitching"},{value:"STAPLING",label:"Stapling"},{value:"WIRE_BINDING",label:"Wire Binding"},
      {value:"PERFECT_BINDING",label:"Perfect Binding"},{value:"SPIRAL_BINDING",label:"Spiral Binding"},{value:"OTHER",label:"Other"}
    ], value: "STITCHING" },
    { name: "quantity_received", label: "Quantity Received", type: "number", value: String(detail.total_produced || "") },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ], async function (v) {
    await API.post("/api/binding/job/" + detail.id, { finishing_method: v.finishing_method, quantity_received: Number(v.quantity_received), remarks: v.remarks || null });
    toast("Binding started", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Start Binding");
}

async function openBindingUpdateModal(detail, content) {
  const fin = detail.finishing;
  openModal("Update Binding — " + detail.job_number, [
    { name: "quantity_completed", label: "Quantity Completed (Received: " + fmtNum(fin.quantity_received) + ")", type: "number", value: String(fin.quantity_completed || "") },
    { name: "is_complete", label: "Mark as Complete", type: "checkbox", value: fin.is_complete },
    { name: "remarks", label: "Remarks", type: "textarea", value: fin.remarks || "" },
  ], async function (v) {
    await API.put("/api/binding/" + fin.id, { quantity_completed: Number(v.quantity_completed) || undefined, is_complete: v.is_complete === true || v.is_complete === "true", remarks: v.remarks || null });
    toast("Binding updated", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Update Binding");
}

async function openInspectionModal(detail, content) {
  openModal("Create Inspection — " + detail.job_number, [
    { name: "quantity_inspected", label: "Quantity Inspected", type: "number", value: String(detail.total_produced || "") },
    { name: "packaging_ok", label: "Packaging OK", type: "checkbox", value: true },
    { name: "quantity_ok", label: "Quantity OK", type: "checkbox", value: true },
    { name: "inspection_remarks", label: "Remarks", type: "textarea" },
  ], async function (v) {
    await API.post("/api/standard/job/" + detail.id, { quantity_inspected: Number(v.quantity_inspected) || null, packaging_ok: !!v.packaging_ok, quantity_ok: !!v.quantity_ok, inspection_remarks: v.inspection_remarks || null });
    toast("Inspection record created", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Create Inspection");
}

async function openInspectionDecideModal(detail, content) {
  const insp = detail.inspection;
  openModal("Inspection Decision — " + detail.job_number, [
    { name: "status", label: "Decision", type: "select", options: [
      {value:"PASSED",label:"APPROVED — Ready for Dispatch"},{value:"REWORK_REQUIRED",label:"REWORK REQUIRED"},{value:"FAILED",label:"FAILED"}
    ], value: insp ? insp.status : "PASSED" },
    { name: "quantity_inspected", label: "Quantity Inspected", type: "number", value: insp ? String(insp.quantity_inspected || "") : "" },
    { name: "packaging_ok", label: "Packaging OK", type: "checkbox", value: insp ? insp.packaging_ok : true },
    { name: "quantity_ok", label: "Quantity OK", type: "checkbox", value: insp ? insp.quantity_ok : true },
    { name: "inspection_remarks", label: "Remarks", type: "textarea", value: insp ? (insp.remarks || "") : "" },
    { name: "rework_instructions", label: "Rework Instructions", type: "textarea" },
  ], async function (v) {
    await API.put("/api/standard/" + insp.id + "/decide", { status: v.status, quantity_inspected: Number(v.quantity_inspected) || null, packaging_ok: !!v.packaging_ok, quantity_ok: !!v.quantity_ok, inspection_remarks: v.inspection_remarks || null, rework_instructions: v.rework_instructions || null });
    toast("Decision recorded", "success");
    activeJobId = detail.id;
    await renderView(activeView, document.getElementById("content"));
  }, "Submit Decision");
}

/* PLANNING DASHBOARD */
async function renderPlanningDashboard(content) {
  content.append.apply(content, pageHeader("Planning Dashboard", "Work order queue, machine allocation, production status."));
  const data = await API.get("/api/planning/dashboard");
  const s = data.summary || {};
  const cards = [
    {val:s.total_work_orders,lbl:"Total Work Orders",cls:""},
    {val:s.unplanned,lbl:"Awaiting Planning",cls:s.unplanned>0?"warn":""},
    {val:s.in_production,lbl:"In Production",cls:""},
    {val:s.paused,lbl:"Paused",cls:s.paused>0?"warn":""},
    {val:s.partial,lbl:"Partial / Ongoing",cls:""},
    {val:s.available_machines,lbl:"Available Machines",cls:s.available_machines===0?"warn":"ok"},
  ];
  content.appendChild(el("div", { class: "kpi-grid" }, cards.map(function (c) {
    return el("div", { class: "kpi-card" + (c.cls ? " kpi-"+c.cls : "") }, [el("div", { class: "kpi-value" }, String(c.val || 0)), el("div", { class: "kpi-label" }, c.lbl)]);
  })));
  const machines = await API.get("/api/machines?active_only=true");
  content.append(
    el("div", { class: "panel" }, [el("h2", {}, "Machines"), dataTable([
      {label:"Machine",key:"name"},{label:"Code",key:"machine_code"},{label:"Type",key:"machine_type"},
      {label:"Method",key:"printing_method"},{label:"Status",render:function(m){return statusBadge(m.status);}},{label:"Color",render:function(m){return m.is_color?"Yes":"No";}},
    ], machines, "No machines configured.")]),
    el("div", { class: "panel" }, [el("h2", {}, "Work Orders Queue"), buildWorkOrderTable(data.jobs || [])]),
  );
}

/* BILLING */
async function renderBilling(content) {
  content.append.apply(content, pageHeader("Billing", "Search work orders and generate bills."));
  const searchInput = el("input", { type: "text", placeholder: "Search by job #, client, or work…", style: "width:300px" });
  const searchBtn = el("button", { class: "btn", onclick: doSearch }, "Search");
  const resultsDiv = el("div", {});
  const detailDiv = el("div", {});
  async function doSearch() {
    const q = searchInput.value.trim();
    if (!q) { toast("Enter a search term", "error"); return; }
    searchBtn.disabled = true;
    try {
      const results = await API.get("/api/billing/search?q=" + encodeURIComponent(q));
      resultsDiv.innerHTML = "";
      if (!results.length) { resultsDiv.appendChild(el("div", { class: "empty-state" }, "No work orders found.")); return; }
      resultsDiv.appendChild(dataTable([
        {label:"Work Order",render:function(r){return el("button",{class:"link-btn",onclick:function(){loadBillingDetail(r.id,detailDiv);}},r.job_number);}},
        {label:"Client",key:"client_name"},{label:"Work",key:"work_name"},
        {label:"Ordered",render:function(r){return fmtNum(r.copies);}},{label:"Produced",render:function(r){return fmtNum(r.total_produced);}},
        {label:"Status",render:function(r){return statusBadge(r.status);}},{label:"Bills",key:"bill_count"},
        {label:"",render:function(r){return el("button",{class:"btn sm",onclick:function(){loadBillingDetail(r.id,detailDiv);}},"View");}},
      ], results));
    } catch(e) { toast(e.message,"error"); } finally { searchBtn.disabled = false; }
  }
  searchInput.addEventListener("keydown", function (ev) { if (ev.key === "Enter") doSearch(); });
  async function loadBillingDetail(jobId, container) {
    container.innerHTML = "";
    container.appendChild(el("div", { class: "empty-state" }, "Loading…"));
    try {
      const d = await API.get("/api/billing/job/" + jobId);
      container.innerHTML = "";
      container.appendChild(buildBillingDetailView(d, container));
    } catch(e) { container.innerHTML = ""; container.appendChild(el("div", { class: "error-banner" }, e.message)); }
  }
  content.append(el("div", { class: "panel" }, [el("h2", {}, "Search Work Order"), el("div", { class: "toolbar" }, [searchInput, searchBtn]), resultsDiv]), detailDiv);
}

function buildBillingDetailView(d, container) {
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "Billing Detail — " + d.job_number));
  const rows = [
    ["Work Order", d.job_number], ["Client", d.client_name], ["Work", d.work_name],
    ["Pages", d.pages || "-"], ["Ordered", fmtNum(d.copies)], ["Produced", fmtNum(d.total_produced)],
    ["Dispatched", fmtNum(d.total_dispatched)], ["Machine", d.machine_name || "-"],
    ["Printing Method", d.printing_method || "-"], ["Financial Year", d.financial_year || "-"],
    ["Billing Status", d.billing_status], ["Total Billed", fmtNum(d.total_billed_quantity)],
  ];
  panel.appendChild(el("div", { class: "info-grid" }, rows.map(function (r) {
    return el("div", { class: "info-row" }, [el("div", { class: "info-label" }, r[0]), el("div", { class: "info-value" }, r[1])]);
  })));
  if (d.billing_records && d.billing_records.length) {
    panel.appendChild(el("h3", { style: "margin-top:20px" }, "Bill History"));
    panel.appendChild(dataTable([
      {label:"Bill Reference",key:"bill_reference"},
      {label:"Quantity",render:function(b){return fmtNum(b.billing_quantity);}},
      {label:"Amount",render:function(b){return b.billing_amount ? fmtMoney(b.billing_amount) : "-";}},
      {label:"Status",render:function(b){return statusBadge(b.status);}},
      {label:"Generated",render:function(b){return b.generated_at ? b.generated_at.slice(0,10) : "-";}},
    ], d.billing_records));
  }
  panel.appendChild(el("h3", { style: "margin-top:20px" }, "Generate New Bill"));
  const qtyInput = el("input", { type: "number", value: String(d.total_produced || ""), style: "width:180px" });
  const amtInput = el("input", { type: "number", placeholder: "Billing Amount (optional)", style: "width:180px" });
  const remarkInput = el("textarea", { rows: 2, placeholder: "Remarks (optional)", style: "width:100%;margin-top:6px" });
  const genBtn = el("button", { class: "btn", onclick: async function () {
    genBtn.disabled = true;
    try {
      const blob = await API.post("/api/billing/job/" + d.job_id + "/generate", {
        billing_quantity: Number(qtyInput.value) || null, billing_amount: amtInput.value ? Number(amtInput.value) : null, remarks: remarkInput.value || null,
      });
      if (blob instanceof Blob) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "bill_" + d.job_number + ".xlsx"; a.click();
        URL.revokeObjectURL(url);
      }
      toast("Bill generated and downloaded", "success");
      const fresh = await API.get("/api/billing/job/" + d.job_id);
      container.innerHTML = "";
      container.appendChild(buildBillingDetailView(fresh, container));
    } catch(e) { toast(e.message, "error"); genBtn.disabled = false; }
  } }, "Generate Excel Bill");
  panel.appendChild(el("div", { class: "billing-form" }, [
    el("div", { class: "form-row" }, [el("label", {}, "Billing Quantity"), qtyInput]),
    el("div", { class: "form-row" }, [el("label", {}, "Billing Amount (Rs.)"), amtInput]),
    el("div", { class: "form-row" }, [el("label", {}, "Remarks"), remarkInput]),
    el("div", { style: "margin-top:12px" }, genBtn),
  ]));
  return panel;
}

/* MATERIALS */
async function renderMaterials(content) {
  content.append.apply(content, pageHeader("Materials & Inventory", "Master catalog; stock movements recorded by Store."));
  const canWrite = ["STORE","MANAGER","SUB_ADMIN"].indexOf(CURRENT_USER.department_code) !== -1;
  const materials = await API.get("/api/materials");
  const search = el("input", { type: "text", placeholder: "Search by name or SKU…" });
  let filtered = materials;
  const tableWrap = el("div", {});
  function updateTable() {
    tableWrap.innerHTML = "";
    tableWrap.appendChild(dataTable([
      {label:"SKU",key:"sku"},{label:"Name",key:"name"},{label:"Unit",key:"unit"},{label:"GSM",key:"gsm"},
      {label:"Stock",render:function(m){return fmtNum(m.current_stock);}},
      {label:"Min Stock",render:function(m){return fmtNum(m.minimum_stock);}},
      {label:"Status",render:function(m){const n=Number(m.current_stock||0),min=Number(m.minimum_stock||0); return badge(n===0?"OUT OF STOCK":n<min?"LOW STOCK":"OK",n===0?"danger":n<min?"warn":"ok");}},
      canWrite ? {label:"",render:function(m){return el("div",{style:"display:flex;gap:6px"},[
        el("button",{class:"btn secondary sm",onclick:function(){openIssueModal(m,content);}},"Issue"),
        el("button",{class:"btn secondary sm",onclick:function(){openReceiveModal(m,content);}},"Receive"),
      ]);}} : null,
    ].filter(Boolean), filtered));
  }
  search.addEventListener("input", function () {
    const q = search.value.toLowerCase();
    filtered = materials.filter(function (m) { return m.name.toLowerCase().includes(q) || (m.sku||"").toLowerCase().includes(q); });
    updateTable();
  });
  updateTable();
  content.append(el("div", { class: "panel" }, [
    el("div", { class: "toolbar" }, [search, el("div",{class:"spacer"}), canWrite ? el("button",{class:"btn",onclick:function(){openCreateMaterialModal(content);}},"+ New Material") : null].filter(Boolean)),
    tableWrap,
  ]));
}
function openCreateMaterialModal(content) {
  openModal("New Material", [
    {name:"sku",label:"SKU"},{name:"name",label:"Name"},
    {name:"unit",label:"Unit (SHEET/KG/L/PCS)"},{name:"gsm",label:"GSM (if paper)"},
    {name:"minimum_stock",label:"Minimum Stock",type:"number"},{name:"purchase_price",label:"Purchase Price",type:"number"},
    {name:"storage_location",label:"Storage Location"},
  ], async function (v) { await API.post("/api/materials",v); toast("Material created","success"); renderView(activeView,document.getElementById("content")); }, "Create Material");
}
function openIssueModal(m, content) {
  openModal("Issue Stock — " + m.name, [{name:"quantity",label:"Quantity",type:"number"},{name:"remarks",label:"Remarks",type:"textarea"}],
  async function (v) { await API.post("/api/inventory/issue",{material_id:m.id,quantity:Number(v.quantity),remarks:v.remarks}); toast("Stock issued","success"); renderView(activeView,document.getElementById("content")); }, "Issue");
}
function openReceiveModal(m, content) {
  openModal("Receive Stock — " + m.name, [{name:"quantity",label:"Quantity",type:"number"},{name:"remarks",label:"Remarks",type:"textarea"}],
  async function (v) { await API.post("/api/inventory/receive",{material_id:m.id,quantity:Number(v.quantity),remarks:v.remarks}); toast("Stock received","success"); renderView(activeView,document.getElementById("content")); }, "Receive");
}

/* REQUESTS */
async function renderRequests(content) {
  content.append.apply(content, pageHeader("Material Requests", "Submit or approve internal material requests."));
  const canApprove = ["STORE","MANAGER","SUB_ADMIN"].indexOf(CURRENT_USER.department_code) !== -1;
  const requests = await API.get("/api/requests");
  content.append(el("div", { class: "panel" }, [
    el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn",onclick:function(){openNewRequestModal(content);}},"+ New Request")]),
    dataTable([
      {label:"Request #",key:"request_number"},{label:"Status",render:function(r){return statusBadge(r.status);}},
      {label:"Items",render:function(r){return (r.items||[]).length;}},{label:"Created",render:function(r){return r.created_at?r.created_at.slice(0,10):"-";}},
      canApprove?{label:"",render:function(r){
        if(r.status!=="SUBMITTED"&&r.status!=="PENDING_APPROVAL")return "";
        return el("div",{style:"display:flex;gap:6px"},[
          el("button",{class:"btn sm ok-btn",onclick:async function(){await API.post("/api/requests/"+r.id+"/approve",{});toast("Approved","success");renderView(activeView,document.getElementById("content"));}},"Approve"),
          el("button",{class:"btn sm danger",onclick:async function(){await API.post("/api/requests/"+r.id+"/reject",{reason:"Rejected"});toast("Rejected");renderView(activeView,document.getElementById("content"));}},"Reject"),
        ]);
      }}:null,
    ].filter(Boolean), requests, "No material requests."),
  ]));
}
function openNewRequestModal(content) {
  openModal("New Material Request",[{name:"remarks",label:"Remarks / Purpose",type:"textarea"}],
  async function (v){await API.post("/api/requests",{remarks:v.remarks});toast("Request created","success");renderView(activeView,document.getElementById("content"));},"Create Request");
}

/* PURCHASING */
async function renderPurchasing(content) {
  content.append.apply(content, pageHeader("Suppliers & Purchases", "Manage suppliers and purchase orders."));
  const [suppliers, pos] = await Promise.all([API.get("/api/suppliers"), API.get("/api/purchase-orders")]);
  content.append(
    el("div",{class:"panel"},[el("h2",{},"Suppliers"),
      el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn secondary",onclick:function(){openNewSupplierModal(content);}},"+ New Supplier")]),
      dataTable([{label:"Name",key:"name"},{label:"Contact",key:"contact_person"},{label:"Phone",key:"phone"},{label:"GST",key:"gst_number"}],suppliers,"No suppliers yet.")]),
    el("div",{class:"panel"},[el("h2",{},"Purchase Orders"),
      el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn",onclick:function(){openNewPOModal(suppliers,content);}},"+ New PO")]),
      dataTable([
        {label:"PO Number",key:"po_number"},{label:"Status",render:function(p){return statusBadge(p.status);}},
        {label:"Total",render:function(p){return fmtMoney(p.total_amount);}},
        {label:"",render:function(p){return (p.status!=="RECEIVED"&&p.status!=="CANCELLED")?el("button",{class:"btn secondary sm",onclick:function(){openReceivePOModal(p,content);}},"Receive Goods"):"";}},
      ],pos,"No purchase orders yet.")]),
  );
}
function openNewSupplierModal(c){openModal("New Supplier",[{name:"name",label:"Supplier Name"},{name:"contact_person",label:"Contact"},{name:"phone",label:"Phone"},{name:"email",label:"Email"},{name:"gst_number",label:"GST Number"}],async function(v){await API.post("/api/suppliers",v);toast("Supplier added","success");renderView(activeView,document.getElementById("content"));},"Add");}
function openNewPOModal(suppliers,c){openModal("New Purchase Order",[{name:"supplier_id",label:"Supplier",type:"select",options:suppliers.map(function(s){return{value:s.id,label:s.name};})},{name:"material_id",label:"Material ID"},{name:"quantity_ordered",label:"Quantity",type:"number"},{name:"unit_price",label:"Unit Price",type:"number"}],async function(v){await API.post("/api/purchase-orders",{supplier_id:v.supplier_id,items:[{material_id:v.material_id,quantity_ordered:Number(v.quantity_ordered),unit_price:Number(v.unit_price)}]});toast("PO created","success");renderView(activeView,document.getElementById("content"));},"Create PO");}
function openReceivePOModal(po,c){openModal("Receive Goods - "+po.po_number,[{name:"material_id",label:"Material ID"},{name:"quantity_received",label:"Qty Received",type:"number"},{name:"unit_price",label:"Unit Price",type:"number"}],async function(v){await API.post("/api/purchase-orders/"+po.id+"/receive",[{material_id:v.material_id,quantity_received:Number(v.quantity_received),unit_price:Number(v.unit_price)}]);toast("Goods received","success");renderView(activeView,document.getElementById("content"));},"Confirm");}

/* DISPATCH */
async function renderDispatch(content) {
  content.append.apply(content, pageHeader("Dispatch", "Track outgoing consignments."));
  const dispatches = await API.get("/api/dispatch");
  content.append(el("div",{class:"panel"},[
    el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn",onclick:function(){openNewDispatchModal(content);}},"+ New Dispatch")]),
    dataTable([
      {label:"Dispatch #",key:"dispatch_no"},{label:"Recipient",key:"recipient"},
      {label:"Qty",render:function(d){return fmtNum(d.quantity);}},{label:"Status",render:function(d){return statusBadge(d.status);}},
      {label:"",render:function(d){return el("select",{onchange:async function(e){await API.put("/api/dispatch/"+d.id+"/status?status="+e.target.value);toast("Updated","success");renderView(activeView,document.getElementById("content"));}},["PENDING","READY","DISPATCHED","DELIVERED","CANCELLED"].map(function(s){const a={value:s};if(s===d.status)a.selected="selected";return el("option",a,s);}));}},
    ], dispatches, "No dispatch orders yet."),
  ]));
}
function openNewDispatchModal(c){openModal("New Dispatch Order",[{name:"recipient",label:"Recipient"},{name:"quantity",label:"Quantity",type:"number"},{name:"vehicle_or_courier",label:"Vehicle / Courier"},{name:"remarks",label:"Remarks",type:"textarea"}],async function(v){await API.post("/api/dispatch",{recipient:v.recipient,quantity:Number(v.quantity),vehicle_or_courier:v.vehicle_or_courier,remarks:v.remarks});toast("Dispatch created","success");renderView(activeView,document.getElementById("content"));},"Create");}

/* ACCOUNTS */
async function renderAccounts(content) {
  content.append.apply(content, pageHeader("Accounts & Budgets", "Expense tracking and budget utilization."));
  const [expenses, budgets] = await Promise.all([API.get("/api/accounts/expenses"), API.get("/api/accounts/budgets")]);
  content.append(
    el("div",{class:"panel"},[el("h2",{},"Expenses"),el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn",onclick:function(){openNewExpenseModal(content);}},"+ Record Expense")]),
      dataTable([{label:"Date",render:function(e){return e.expense_date.slice(0,10);}},{label:"Category",key:"category"},{label:"Amount",render:function(e){return fmtMoney(e.amount);}},{label:"Description",key:"description"}],expenses,"No expenses.")]),
    el("div",{class:"panel"},[el("h2",{},"Budgets"),el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn secondary",onclick:function(){openNewBudgetModal(content);}},"+ New Budget")]),
      dataTable([{label:"Fiscal Year",key:"fiscal_year"},{label:"Month",render:function(b){return b.month!==null&&b.month!==undefined?b.month:"Annual";}},{label:"Category",key:"category"},{label:"Allocated",render:function(b){return fmtMoney(b.allocated_amount);}}],budgets,"No budgets.")]),
  );
}
function openNewExpenseModal(c){const cats=["MATERIAL_PURCHASE","MAINTENANCE","UTILITY","SALARY","OTHER"];openModal("Record Expense",[{name:"category",label:"Category",type:"select",options:cats.map(function(c){return{value:c,label:c};})},{name:"amount",label:"Amount",type:"number"},{name:"description",label:"Description",type:"textarea"},{name:"expense_date",label:"Date",type:"date",value:new Date().toISOString().slice(0,10)}],async function(v){await API.post("/api/accounts/expenses",{category:v.category,amount:v.amount,description:v.description,expense_date:new Date(v.expense_date).toISOString()});toast("Expense recorded","success");renderView(activeView,document.getElementById("content"));},"Save");}
function openNewBudgetModal(c){const cats=["MATERIAL_PURCHASE","MAINTENANCE","UTILITY","SALARY","OTHER"];openModal("New Budget",[{name:"fiscal_year",label:"Fiscal Year",type:"number",value:String(new Date().getFullYear())},{name:"month",label:"Month (blank=annual)",type:"number"},{name:"category",label:"Category",type:"select",options:cats.map(function(c){return{value:c,label:c};})},{name:"allocated_amount",label:"Allocated Amount",type:"number"}],async function(v){await API.post("/api/accounts/budgets",{fiscal_year:Number(v.fiscal_year),month:v.month?Number(v.month):null,category:v.category,allocated_amount:v.allocated_amount});toast("Budget created","success");renderView(activeView,document.getElementById("content"));},"Save");}

/* COSTING */
async function renderCosting(content) {
  content.append.apply(content, pageHeader("Costing - Ready Reckoner", "DTP → proofing → CTP → printing → binding → dispatch cost estimate."));
  const canEditRates = ["MANAGER","SUB_ADMIN"].indexOf(CURRENT_USER.department_code) !== -1;
  let rates = null;
  try { rates = await API.get("/api/costing/rates"); } catch (e) { rates = null; }
  const ratePanel = el("div",{class:"panel"},[el("h2",{},"Active Rate Master")]);
  if (rates) {
    ratePanel.appendChild(dataTable([{label:"DTP/pg",key:"dtp_rate"},{label:"Proof/pg",key:"proof_rate"},{label:"CTP/plate",key:"ctp_rate"},{label:"Print/1000imp",key:"offset_printing_first_rate"},{label:"Binding/copy",key:"binding_rate"},{label:"Warehouse %",key:"warehouse_loading_pct"},{label:"Dispatch %",key:"dispatch_pct"}],[rates]));
    if (canEditRates) ratePanel.appendChild(el("button",{class:"btn secondary",style:"margin-top:10px",onclick:function(){openEditRatesModal(rates,content);}},"Edit Rates"));
  } else {
    ratePanel.appendChild(el("div",{class:"empty-state"},"No active rate master."));
    if (canEditRates) ratePanel.appendChild(el("button",{class:"btn",onclick:function(){openEditRatesModal({},content);}},"Configure Rates"));
  }
  const resultBox = el("div",{class:"empty-state"},"Fill the form and calculate.");
  const fields = {pages:el("input",{type:"number",value:"0"}),copies:el("input",{type:"number",value:"0"}),plates:el("input",{type:"number",value:"0"}),paper_cost:el("input",{type:"number",value:"0"})};
  const calcBtn = el("button",{class:"btn",style:"margin-top:14px",onclick:async function(){
    try{const r=await API.post("/api/costing/estimate",{pages:Number(fields.pages.value),copies:Number(fields.copies.value),plates:Number(fields.plates.value),paper_cost:fields.paper_cost.value});resultBox.innerHTML="";resultBox.appendChild(el("div",{},[el("div",{class:"kpi-value"},fmtMoney(r.final_landed_billing_cost)),el("div",{class:"kpi-label"},"Final — "+fmtMoney(r.per_copy_rate)+" per copy")]));}catch(e){toast(e.message,"error");}
  }},"Calculate");
  const estimatePanel = el("div",{class:"panel"},[el("h2",{},"Quick Estimate"),el("div",{class:"form-grid"},[el("div",{},[el("label",{},"Pages"),fields.pages]),el("div",{},[el("label",{},"Copies"),fields.copies]),el("div",{},[el("label",{},"Plates"),fields.plates]),el("div",{},[el("label",{},"Paper Cost (Rs.)"),fields.paper_cost])]),calcBtn,resultBox]);
  content.append(ratePanel, estimatePanel);
}
function openEditRatesModal(rates,c){openModal("Edit Costing Rates",[{name:"dtp_rate",label:"DTP Rate/page",type:"number",value:rates.dtp_rate||"1.5"},{name:"proof_rate",label:"Proof Rate/page",type:"number",value:rates.proof_rate||"0.75"},{name:"ctp_rate",label:"CTP Rate/plate",type:"number",value:rates.ctp_rate||"120"},{name:"offset_printing_first_rate",label:"Print Rate/1000imp",type:"number",value:rates.offset_printing_first_rate||"450"},{name:"binding_rate",label:"Binding Rate/copy",type:"number",value:rates.binding_rate||"3.2"},{name:"warehouse_loading_pct",label:"Warehouse %",type:"number",value:rates.warehouse_loading_pct||"15"},{name:"dispatch_pct",label:"Dispatch %",type:"number",value:rates.dispatch_pct||"3"}],async function(v){await API.put("/api/costing/rates",v);toast("Rates updated","success");renderView(activeView,document.getElementById("content"));},"Save Rates");}

/* USERS */
async function renderUsers(content) {
  content.append.apply(content, pageHeader("Users", "Manage employee accounts and department assignment."));
  const users = await API.get("/api/users");
  const ALL_DEPTS = ["SUB_ADMIN","STORE","PLANNING","DISPATCH","ACCOUNTS","EMPLOYEE","DIGITAL_PRINTING","TRADITIONAL_PRINTING","PLATE_MAKING","BINDING","STANDARD","MECHANIC","BILLING"];
  content.append(el("div",{class:"panel"},[
    el("div",{class:"toolbar"},[el("div",{class:"spacer"}),el("button",{class:"btn",onclick:function(){openNewUserModal(content,ALL_DEPTS);}},"+ New User")]),
    dataTable([
      {label:"Employee ID",key:"employee_id"},{label:"Name",key:"full_name"},{label:"Email",key:"email"},{label:"Department",key:"department_code"},
      {label:"Active",render:function(u){return statusBadge(u.is_active?"OK":"REJECTED");}},
      {label:"",render:function(u){return CURRENT_USER.department_code==="MANAGER"?el("button",{class:"btn danger sm",onclick:async function(){await API.del("/api/users/"+u.id);toast("User deactivated","success");renderView(activeView,document.getElementById("content"));}},"Deactivate"):"";}}
    ],users),
  ]));
}
function openNewUserModal(c,depts){openModal("New User",[{name:"employee_id",label:"Employee ID"},{name:"full_name",label:"Full Name"},{name:"email",label:"Email"},{name:"password",label:"Temp Password",type:"password"},{name:"department_code",label:"Department",type:"select",options:depts.map(function(d){return{value:d,label:d.replace(/_/g," ")};})}],async function(v){await API.post("/api/users",v);toast("User created","success");renderView(activeView,document.getElementById("content"));},"Create User");}

/* AUDIT */
async function renderAudit(content) {
  content.append.apply(content, pageHeader("Audit Log", "Immutable record of every significant action."));
  const logs = await API.get("/api/audit-logs?limit=300");
  content.append(el("div",{class:"panel"},dataTable([
    {label:"Time",render:function(l){return l.created_at.replace("T"," ").slice(0,19);}},{label:"Employee",key:"employee_id"},
    {label:"Department",key:"department_code"},{label:"Action",key:"action"},{label:"Entity",render:function(l){return l.entity_type||"";}},{label:"Detail",key:"detail"},
  ],logs,"No audit entries yet.")));
}

/* LICENSE */
async function renderLicense(content) {
  content.append.apply(content, pageHeader("License & Device Activation", "License status and authorized devices."));
  const status = await API.get("/api/license/status");
  const statusPanel = el("div",{class:"panel"},[
    el("h2",{},"License Status"),
    el("div",{class:"kpi-grid"},[el("div",{class:"kpi-card"},[el("div",{class:"kpi-value"},statusBadge(status.valid?"OK":"REJECTED")),el("div",{class:"kpi-label"},status.reason)])]),
    el("p",{class:"page-sub"},"Device fingerprint: "+status.this_device_fingerprint),
    el("button",{class:"btn",onclick:async function(){try{await API.post("/api/license/activate-this-device");toast("Device activated","success");renderView(activeView,document.getElementById("content"));}catch(e){toast(e.message,"error");}}},"Activate This Device"),
  ]);
  const devices = await API.get("/api/license/devices");
  const devicePanel = el("div",{class:"panel"},[el("h2",{},"Authorized Devices"),dataTable([
    {label:"Computer Name",key:"computer_name"},{label:"Fingerprint",render:function(d){return d.device_fingerprint.slice(0,16)+"…";}},
    {label:"Status",render:function(d){return statusBadge(d.status);}},
    {label:"",render:function(d){return (CURRENT_USER.department_code==="MANAGER"&&d.status==="ACTIVE")?el("button",{class:"btn danger sm",onclick:async function(){await API.post("/api/license/devices/"+d.id+"/revoke");toast("Device revoked","success");renderView(activeView,document.getElementById("content"));}},"Revoke"):"";}}
  ],devices,"No devices.")]);
  content.append(statusPanel, devicePanel);
}

/* NEW JOB MODAL */
function openNewJobModal(onDone) {
  openModal("New Work Order", [
    {name:"client_name",label:"Client / Institution"},{name:"work_name",label:"Publication / Work Description"},
    {name:"pages",label:"Pages",type:"number"},{name:"copies",label:"Copies / Quantity",type:"number"},
    {name:"priority",label:"Priority",type:"select",options:[{value:"NORMAL",label:"Normal"},{value:"HIGH",label:"High"},{value:"URGENT",label:"Urgent"},{value:"LOW",label:"Low"}],value:"NORMAL"},
  ], async function (v) {
    await API.post("/api/production/jobs", { client_name: v.client_name, work_name: v.work_name, pages: Number(v.pages)||null, copies: Number(v.copies)||null, priority: v.priority });
    toast("Work order created", "success");
    if (typeof onDone === "function") onDone();
    else renderView(activeView, document.getElementById("content"));
  }, "Create Work Order");
}

/* BOOT */
async function bootApp() {
  try { CURRENT_USER = await API.get("/api/auth/me"); }
  catch (e) { renderLogin(); return; }
  WS = API.connectWebSocket(function (msg) {
    const msgs = {
      STOCK_UPDATED:"Stock updated", LOW_STOCK:"Low stock alert",
      JOB_ASSIGNED:"Work order assigned: "+(msg.data.job_number||""),
      JOB_PAUSED:"Job paused: "+(msg.data.job_number||""),
      JOB_RESUMED:"Job resumed: "+(msg.data.job_number||""),
      PRODUCTION_UPDATED:"Production update: "+(msg.data.job_number||"")+" — "+fmtNum(msg.data.qty||0)+" copies",
      PLATES_READY:"Plates ready: "+(msg.data.job_number||""),
      BINDING_COMPLETE:"Binding complete: "+(msg.data.job_number||""),
      INSPECTION_PASSED:"Inspection passed: "+(msg.data.job_number||""),
    };
    if (msgs[msg.event]) toast(msgs[msg.event]);
    if (["JOB_ASSIGNED","JOB_PAUSED","JOB_RESUMED","PRODUCTION_UPDATED"].indexOf(msg.event) !== -1) {
      if (["workorders","planning","dashboard"].indexOf(activeView) !== -1 && !activeJobId) {
        const contentEl = document.getElementById("content");
        if (contentEl) renderView(activeView, contentEl);
      }
    }
  });
  renderShell();
}

if (API.isAuthenticated()) { bootApp(); } else { renderLogin(); }
