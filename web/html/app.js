// AWS 비용 일일 리포트 — 프론트엔드
// API는 같은 origin의 /api/* 로 호출하고, nginx가 WAS로 프록시한다.
"use strict";

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const charts = {};

const fmt = (value, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
const signed = (value, currency) =>
  (value > 0 ? "+" : value < 0 ? "−" : "") + fmt(Math.abs(value), currency);
const tone = (value) => (value > 0 ? "up" : value < 0 ? "down" : "");

async function getJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

function showNotice(message) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

function drawChart(id, config) {
  charts[id]?.destroy();
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--grid");
  charts[id] = new Chart($(id), config);
}

function renderCards(r) {
  $("total").textContent = fmt(r.total, r.currency);
  $("prev").textContent = fmt(r.prev_total, r.currency);
  const pct = r.change_pct === null ? "" : ` (${r.change_pct > 0 ? "+" : ""}${r.change_pct}%)`;
  $("change").textContent = signed(r.change, r.currency) + pct;
  $("change").className = `value ${tone(r.change)}`;
  $("mtd").textContent = fmt(r.month_to_date, r.currency);
}

function renderTrend(t, selected) {
  const accent = css("--accent");
  drawChart("trendChart", {
    type: "line",
    data: {
      labels: t.points.map((p) => p.date.slice(5)),
      datasets: [{
        data: t.points.map((p) => p.total),
        borderColor: accent,
        backgroundColor: css("--accent-fill"),
        fill: true,
        tension: 0.25,
        pointRadius: t.points.map((p) => (p.date === selected ? 5 : 2)),
        pointBackgroundColor: accent,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => fmt(c.parsed.y, t.currency) } },
      },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => `$${v}` } } },
    },
  });
}

function renderServices(r) {
  const top = r.services.slice(0, 10);
  drawChart("serviceChart", {
    type: "bar",
    data: {
      labels: top.map((s) => s.service.replace(/^(Amazon|AWS) ?/, "")),
      datasets: [{ data: top.map((s) => s.amount), backgroundColor: css("--accent"), borderRadius: 4 }],
    },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => fmt(c.parsed.x, r.currency) } },
      },
    },
  });

  const tbody = $("serviceRows");
  tbody.replaceChildren();
  for (const s of r.services) {
    const tr = document.createElement("tr");
    const cells = [
      [s.service, ""],
      [fmt(s.amount, r.currency), ""],
      [fmt(s.prev_amount, r.currency), ""],
      [signed(s.change, r.currency), tone(s.change)],
    ];
    for (const [text, cls] of cells) {
      const td = document.createElement("td");
      td.textContent = text; // XSS 방지: innerHTML 사용 안 함
      if (cls) td.className = cls;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

async function load(date) {
  try {
    const [report, trend] = await Promise.all([
      getJson(`/api/costs/daily?date=${date}`),
      getJson(`/api/costs/trend?days=30&end=${date}`),
    ]);
    showNotice(report.has_data ? "" : `${date} 데이터가 아직 수집되지 않았습니다.`);
    renderCards(report);
    renderTrend(trend, date);
    renderServices(report);
    loadBudgets(date.slice(0, 7), report.services.map((s) => s.service));
  } catch (err) {
    showNotice(`데이터를 불러오지 못했습니다: ${err.message}`);
  }
}

// ---------------------------------------------------------------- 월 예산 (등록 · 조회 · 수정)
let budgetMonth = null;

async function sendJson(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? "입력값을 확인하세요" : data.detail;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
}

function budgetMessage(text, isError = false) {
  $("budgetMsg").textContent = text;
  $("budgetMsg").className = isError ? "form-msg error" : "form-msg";
}

function renderBudgets(budgets) {
  const tbody = $("budgetRows");
  tbody.replaceChildren();
  if (!budgets.length) {
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "등록된 예산이 없습니다.";
    tbody.appendChild(document.createElement("tr")).appendChild(td);
    return;
  }
  for (const b of budgets) {
    const tr = document.createElement("tr");
    const add = (...nodes) => tr.appendChild(document.createElement("td")).append(...nodes);

    const amount = document.createElement("input");
    amount.type = "number";
    amount.min = "0.01";
    amount.step = "0.01";
    amount.value = b.amount;
    amount.setAttribute("aria-label", `${b.service} 예산`);

    const meter = document.createElement("span");
    meter.className = b.usage_pct > 100 ? "meter over" : "meter";
    meter.appendChild(document.createElement("span")).style.width = `${Math.min(b.usage_pct, 100)}%`;
    const pct = document.createElement("span");
    pct.textContent = `${b.usage_pct}%`;
    if (b.usage_pct > 100) pct.className = "up";

    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "저장";
    save.addEventListener("click", async () => {
      try {
        const updated = await sendJson("PUT", `/api/budgets/${b.id}`, { amount: Number(amount.value) });
        budgetMessage(`${updated.service} 예산을 ${fmt(updated.amount)}(으)로 수정했습니다.`);
        loadBudgets(budgetMonth);
      } catch (err) {
        budgetMessage(`수정 실패: ${err.message}`, true);
      }
    });

    add(b.service); // textContent 로 들어가므로 XSS 안전
    add(amount);
    add(fmt(b.spent));
    add(meter, pct);
    add(save);
    tbody.appendChild(tr);
  }
}

async function loadBudgets(month, services = null) {
  budgetMonth = month;
  $("budgetMonth").textContent = month;
  if (services) {
    $("budgetService").replaceChildren(...services.map((name) => new Option(name, name)));
  }
  try {
    renderBudgets(await getJson(`/api/budgets?month=${month}`));
  } catch (err) {
    budgetMessage(`예산을 불러오지 못했습니다: ${err.message}`, true);
  }
}

$("budgetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const created = await sendJson("POST", "/api/budgets", {
      month: budgetMonth,
      service: $("budgetService").value,
      amount: Number($("budgetAmount").value),
    });
    budgetMessage(`${created.service} ${created.month} 예산을 등록했습니다.`);
    $("budgetAmount").value = "";
    loadBudgets(budgetMonth);
  } catch (err) {
    budgetMessage(`등록 실패: ${err.message}`, true);
  }
});

async function init() {
  let latest = null;
  try {
    const meta = await getJson("/api/meta");
    latest = meta.latest_date;
    $("meta").textContent = `source: ${meta.cost_source} · v${meta.version}` +
      (latest ? ` · 최신 ${latest}` : "");
  } catch (err) {
    $("meta").textContent = "API 연결 실패";
  }
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const initial = latest || yesterday;
  $("date").value = initial;
  $("date").max = yesterday;
  $("date").addEventListener("change", (e) => e.target.value && load(e.target.value));
  load(initial);
}

init();
