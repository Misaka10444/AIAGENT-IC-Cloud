/* 云梯演示前端：零依赖，手写 markdown 渲染 + 轨迹面板。 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const chatEl = $("chat");
  const inputEl = $("input");
  const sendBtn = $("send");
  const statusEl = $("status");

  let sessionId = "web-" + Math.random().toString(36).slice(2, 8);
  let busy = false;

  // ---------------- markdown ----------------
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function inline(s) {
    let t = esc(s);
    t = t.replace(/`([^`]+)`/g, (_, c) => "<code>" + c + "</code>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return t;
  }

  function md(src) {
    const lines = String(src || "").split(/\r?\n/);
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const ln = lines[i];

      if (/^\s*\|/.test(ln) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
        const head = ln.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
        i += 2;
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim())));
          i++;
        }
        out.push("<table><thead><tr>" + head.map((h) => "<th>" + h + "</th>").join("") +
          "</tr></thead><tbody>" +
          rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("") +
          "</tbody></table>");
        continue;
      }

      if (/^#{1,4}\s+/.test(ln)) {
        const level = ln.match(/^#+/)[0].length;
        out.push("<h" + Math.min(level + 2, 6) + ">" + inline(ln.replace(/^#+\s+/, "")) +
          "</h" + Math.min(level + 2, 6) + ">");
        i++;
        continue;
      }

      if (/^\s*>\s?/.test(ln)) {
        const buf = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          buf.push(inline(lines[i].replace(/^\s*>\s?/, "")));
          i++;
        }
        out.push("<blockquote>" + buf.join("<br>") + "</blockquote>");
        continue;
      }

      if (/^\s*([-*]|\d+\.)\s+/.test(ln)) {
        const ordered = /^\s*\d+\.\s+/.test(ln);
        const items = [];
        while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          items.push("<li>" + inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, "")) + "</li>");
          i++;
        }
        out.push((ordered ? "<ol>" : "<ul>") + items.join("") + (ordered ? "</ol>" : "</ul>"));
        continue;
      }

      if (!ln.trim()) { i++; continue; }

      const buf = [];
      while (i < lines.length && lines[i].trim() &&
             !/^\s*\|/.test(lines[i]) && !/^#{1,4}\s+/.test(lines[i]) &&
             !/^\s*>\s?/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        buf.push(inline(lines[i]));
        i++;
      }
      out.push("<p>" + buf.join("<br>") + "</p>");
    }
    return out.join("");
  }

  // ---------------- 渲染 ----------------
  function addMsg(role, html) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const bub = document.createElement("div");
    bub.className = "bubble";
    bub.innerHTML = html;
    wrap.appendChild(bub);
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
    return wrap;
  }

  function addUser(text) { addMsg("user", "<p>" + inline(text) + "</p>"); }

  function addTyping() {
    const el = addMsg("agent",
      '<div class="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span>' +
      '<span style="margin-left:6px">规划与检索中…</span></div>');
    return el;
  }

  function renderPanels(res) {
    // 角色时间线
    const roles = (res.roles || []).filter((r) => r.role !== "receive");
    $("roles").innerHTML = roles.length
      ? roles.map((r) =>
          '<div class="role' + (r.status === "fail" ? " fail" : "") + '">' +
          '<span class="who">' + esc(r.role) + '</span>' +
          '<span class="what">' + esc(r.action) + "</span></div>").join("")
      : '<div class="empty">—</div>';

    // 工具
    const tools = res.tool_calls || [];
    $("tools").innerHTML = tools.length
      ? tools.map((t) =>
          '<div class="tool' + (t.ok ? "" : " bad") + '">' +
          '<span class="tname">' + esc(t.tool) + "</span>" +
          '<span class="tms">' + (t.ok ? "OK" : "FAIL") + " · " + t.ms + "ms" +
          (t.attempts > 1 ? " · 重试" + (t.attempts - 1) : "") + "</span></div>").join("")
      : '<div class="empty">本轮未调用工具</div>';

    // 自检
    const fs = (res.audit && res.audit.findings) || [];
    $("audit").innerHTML = fs.length
      ? fs.map((f) =>
          '<div class="item"><span class="tag ' + f.level + '">' +
          (f.level === "pass" ? "通过" : f.level === "warn" ? "注意" : "失败") +
          "</span>" + esc(f.message) + "</div>").join("")
      : '<div class="empty">—</div>';

    // 引用
    const cs = res.citations || [];
    $("cites").innerHTML = cs.length
      ? cs.map((c) =>
          '<div class="cite"><span class="doc">' + esc(c.doc_id) + "</span> " +
          '<span class="sec">§' + esc(c.section) + " · 第" + c.line_start + "行</span>" +
          '<span class="snip">' + esc(c.snippet) + "</span></div>").join("")
      : '<div class="empty">本轮无原文引用</div>';
  }

  // ---------------- 交互 ----------------
  async function ask(text) {
    if (busy || !text.trim()) return;
    busy = true;
    sendBtn.disabled = true;
    statusEl.textContent = "推理中…";
    statusEl.classList.add("busy");
    addUser(text);
    const typing = addTyping();

    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const res = await r.json();
      typing.remove();
      if (res.error) {
        addMsg("agent", "<p>请求失败：" + esc(res.error) + "</p>");
      } else {
        addMsg("agent", md(res.answer));
        renderPanels(res);
        statusEl.textContent = res.intent + " · " + res.elapsed_ms + "ms";
      }
    } catch (e) {
      typing.remove();
      addMsg("agent", "<p>网络错误：" + esc(String(e)) + "</p>");
      statusEl.textContent = "错误";
    } finally {
      busy = false;
      sendBtn.disabled = false;
      statusEl.classList.remove("busy");
    }
  }

  function pickStudent(sid, alias) {
    document.querySelectorAll(".student").forEach((el) => el.classList.remove("active"));
    const el = document.querySelector('.student[data-sid="' + sid + '"]');
    if (el) el.classList.add("active");
    inputEl.value = sid + " ";
    inputEl.focus();
  }

  function buildStudents(list) {
    $("students").innerHTML = list.map((s) =>
      '<div class="student" data-sid="' + s.student_id + '">' +
      '<div class="n">' + esc(s.alias) + " · " + s.student_id + "</div>" +
      '<div class="m">' + s.grade + "级 " + esc(s.major) + " · 第" + s.current_term + "学期</div>" +
      '<div class="m">' + esc(s.goal) + " · " + esc(s.target_direction) + "</div></div>").join("");
    document.querySelectorAll(".student").forEach((el) => {
      el.addEventListener("click", () => pickStudent(el.dataset.sid));
    });
  }

  const PROMPTS = [
    "S001 下学期怎么选课",
    "S001 我差多少学分",
    "S003 能毕业吗",
    "S001 我会被预警吗",
    "大模型应用开发 我的先修够吗",
    "数据库原理与应用 和 操作系统 冲突吗",
    "毕业的学分要求是多少",
  ];

  function buildPrompts() {
    $("prompts").innerHTML = PROMPTS.map((p) =>
      '<button class="prompt" type="button">' + esc(p) + "</button>").join("");
    document.querySelectorAll(".prompt").forEach((el) => {
      el.addEventListener("click", () => {
        inputEl.value = el.textContent;
        ask(el.textContent);
      });
    });
  }

  async function bootstrap() {
    buildPrompts();
    try {
      const r = await fetch("/api/bootstrap");
      const d = await r.json();
      buildStudents(d.students || []);
      $("kbmeta").textContent = "知识库：" + d.kb.docs + " 篇 / " + d.kb.chunks + " 片段";
      $("enginemeta").textContent = "工具：" + (d.tools || []).length + " 个 · 引擎：" +
        (d.engine === "gateway" ? "模型网关" : "本地确定性引擎") + " v" + d.app.version;
    } catch (e) {
      $("kbmeta").textContent = "初始化失败：" + e;
    }
  }

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = inputEl.value.trim();
    inputEl.value = "";
    ask(t);
  });

  $("reset").addEventListener("click", async () => {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    sessionId = "web-" + Math.random().toString(36).slice(2, 8);
    chatEl.querySelectorAll(".msg.agent:not(:first-child)").forEach((el) => el.remove());
    ["roles", "tools", "audit", "cites"].forEach((k) => {
      $(k).innerHTML = '<div class="empty">—</div>';
    });
    statusEl.textContent = "就绪";
  });

  bootstrap();
})();
