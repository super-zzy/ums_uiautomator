// 历史记录模块（单用例 + 执行集）

(function () {
  const { Elements, AppState, Common } = window;
  const {
    taskHistoryTableSingle,
    taskHistoryTableExecSet,
    historyTabSingle,
    historyTabExecSet,
    historyPanelSingle,
    historyPanelExecSet,
    clearHistoryBtn,
    viewReportBtn,
    historySinglePagination,
    historySinglePageInfo,
    historySinglePrevPage,
    historySingleNextPage,
    historyExecSetPagination,
    historyExecSetPageInfo,
    historyExecSetPrevPage,
    historyExecSetNextPage,
  } = Elements || {};
  const { addTaskLog, saveHistory, loadHistory, apiGet, formatDuration } =
    Common || {};

  const HistoryState = {
    activeTab: "single",
    single: { page: 1, pageSize: 10, totalPages: 1, total: 0 },
    execSet: { page: 1, pageSize: 10, totalPages: 1, total: 0 },
  };

  function statusBadge(status) {
    const s = String(status || "").trim().toLowerCase();
    if (s === "success") {
      return {
        cls: "bg-success/10 text-success",
        text: "成功",
      };
    }
    if (s === "stop") {
      return {
        cls: "bg-danger/10 text-danger",
        text: "停止",
      };
    }
    if (s === "failure") {
      return {
        cls: "bg-warning/10 text-warning",
        text: "失败",
      };
    }
    return { cls: "bg-warning/10 text-warning", text: s || "-" };
  }

  function renderSingleHistory(items) {
    if (!taskHistoryTableSingle) return;
    if (!items.length) {
      taskHistoryTableSingle.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无任务历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableSingle.innerHTML = items
      .map(
        (h, index) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${h.task_id || "-"}</td>
        <td class="py-3 px-4">${h.device_id || "-"}</td>
        <td class="py-3 px-4">${h.case_name || h.case_id || "-"}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${statusBadge(h.status).cls}">
            ${statusBadge(h.status).text}
          </span>
        </td>
        <td class="py-3 px-4">${h.start_time || h.create_time || "-"}</td>
        <td class="py-3 px-4">${formatDuration ? formatDuration(h.exec_duration) : (h.exec_duration || "-")}</td>
        <td class="py-3 px-4">
          ${
            h.report_index_path
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('/api/report/files/${encodeURIComponent(
                          h.task_id
                        )}/index.html', '_blank')">
                     <i class="fa fa-file-text-o mr-1"></i>查看报告
                 </button>`
              : `<span class="text-light text-sm">无报告</span>`
          }
          ${
            h.video_path
              ? `${String(h.video_path).toLowerCase().endsWith(".mp4")
                  ? `<button class="ml-3 text-primary hover:text-primary/80 text-sm"
                        data-action="view-media" data-kind="video" data-task-id="${encodeURIComponent(
                          h.task_id
                        )}" type="button">
                      <i class="fa fa-play-circle mr-1"></i>查看视频
                    </button>`
                  : `<button class="ml-3 text-primary hover:text-primary/80 text-sm"
                        data-action="view-media" data-kind="shots" data-task-id="${encodeURIComponent(
                          h.task_id
                        )}" type="button">
                      <i class="fa fa-picture-o mr-1"></i>查看截图
                    </button>`}
                 <a class="ml-3 text-success hover:text-success/80 text-sm"
                    href="/api/test/video/${encodeURIComponent(h.task_id)}">
                    <i class="fa fa-download mr-1"></i>${
                      String(h.video_path).toLowerCase().endsWith(".mp4")
                        ? "下载视频"
                        : "下载截图"
                    }
                 </a>`
              : ``
          }
        </td>
      </tr>
    `
      )
      .join("");
  }

  function renderExecSetHistory(items) {
    if (!taskHistoryTableExecSet) return;
    if (!items.length) {
      taskHistoryTableExecSet.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-8 text-light">
            <i class="fa fa-history text-2xl mb-2"></i>
            <p>暂无执行集历史记录</p>
          </td>
        </tr>
      `;
      return;
    }
    taskHistoryTableExecSet.innerHTML = items
      .map(
        (h, index) => `
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 px-4">${h.task_id || "-"}</td>
        <td class="py-3 px-4">${h.device_id || "-"}</td>
        <td class="py-3 px-4">${h.exec_set_name || h.exec_set_id || "-"}</td>
        <td class="py-3 px-4">
          <span class="px-2 py-1 rounded-full text-xs ${statusBadge(h.status).cls}">
            ${statusBadge(h.status).text}
          </span>
        </td>
        <td class="py-3 px-4">${h.start_time || h.create_time || "-"}</td>
        <td class="py-3 px-4">${formatDuration ? formatDuration(h.exec_duration) : (h.exec_duration || "-")}</td>
        <td class="py-3 px-4">
          ${
            h.report_index_path
              ? `<button class="text-primary hover:text-primary/80 text-sm"
                        onclick="window.open('/api/report/files/${encodeURIComponent(
                          h.task_id
                        )}/index.html', '_blank')">
                     <i class="fa fa-file-text-o mr-1"></i>查看报告
                 </button>`
              : `<span class="text-light text-sm">无报告</span>`
          }
          ${
            h.video_path
              ? `${String(h.video_path).toLowerCase().endsWith(".mp4")
                  ? `<button class="ml-3 text-primary hover:text-primary/80 text-sm"
                        data-action="view-media" data-kind="video" data-task-id="${encodeURIComponent(
                          h.task_id
                        )}" type="button">
                      <i class="fa fa-play-circle mr-1"></i>查看视频
                    </button>`
                  : `<button class="ml-3 text-primary hover:text-primary/80 text-sm"
                        data-action="view-media" data-kind="shots" data-task-id="${encodeURIComponent(
                          h.task_id
                        )}" type="button">
                      <i class="fa fa-picture-o mr-1"></i>查看截图
                    </button>`}
                 <a class="ml-3 text-success hover:text-success/80 text-sm"
                    href="/api/test/video/${encodeURIComponent(h.task_id)}">
                    <i class="fa fa-download mr-1"></i>${
                      String(h.video_path).toLowerCase().endsWith(".mp4")
                        ? "下载视频"
                        : "下载截图"
                    }
                 </a>`
              : ``
          }
        </td>
      </tr>
    `
      )
      .join("");
  }

  // ---------------- 媒体弹窗：视频 / 截图 ----------------
  const MediaViewer = (function () {
    let state = { open: false, kind: null, taskId: null, items: [], idx: 0 };

    function el(id) {
      return document.getElementById(id);
    }

    function showModal() {
      const modal = el("media-viewer-modal");
      if (modal) modal.classList.remove("hidden");
      state.open = true;
    }

    function hideModal() {
      const modal = el("media-viewer-modal");
      if (modal) modal.classList.add("hidden");
      const video = el("media-viewer-video");
      if (video) {
        try {
          video.pause();
        } catch (e) {}
        video.removeAttribute("src");
        try {
          video.load();
        } catch (e) {}
      }
      state = { open: false, kind: null, taskId: null, items: [], idx: 0 };
    }

    function setMsg(text) {
      const node = el("media-viewer-msg");
      if (node) node.textContent = text || "";
    }

    function setTitle(title, taskId) {
      const t = el("media-viewer-title");
      const sub = el("media-viewer-subtitle");
      if (t) t.textContent = title || "媒体预览";
      if (sub) sub.textContent = taskId ? `task=${taskId}` : "";
    }

    function setPanels(kind) {
      const vp = el("media-viewer-video-panel");
      const sp = el("media-viewer-shot-panel");
      if (vp) vp.classList.toggle("hidden", kind !== "video");
      if (sp) sp.classList.toggle("hidden", kind !== "shots");
      const icon = (document.querySelector("#media-viewer-title") || {}).previousElementSibling;
      if (icon && icon.classList) {
        icon.className =
          kind === "video"
            ? "fa fa-play-circle text-primary"
            : "fa fa-picture-o text-primary";
      }
    }

    function updateShotUI() {
      const counter = el("media-viewer-counter");
      const prevBtn = el("media-viewer-prev");
      const nextBtn = el("media-viewer-next");
      const total = state.items.length;
      if (counter) {
        counter.textContent = total
          ? `${state.idx + 1} / ${total}（${state.items[state.idx].name}）`
          : "- / -";
      }
      if (prevBtn) prevBtn.disabled = state.idx <= 0;
      if (nextBtn) nextBtn.disabled = state.idx >= total - 1;
    }

    function renderThumbs() {
      const wrap = el("media-viewer-thumbs");
      if (!wrap) return;
      wrap.innerHTML = "";
      const total = state.items.length;
      if (!total) return;
      state.items.forEach((it, i) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className =
          "border rounded overflow-hidden bg-white hover:opacity-90 focus:outline-none " +
          (i === state.idx ? "ring-2 ring-primary" : "");
        btn.style.width = "92px";
        btn.style.height = "62px";
        btn.dataset.idx = String(i);
        const img = document.createElement("img");
        img.alt = it.name || "thumb";
        img.className = "w-full h-full object-cover";
        img.loading = "lazy";
        img.src = it.url + (it.url.includes("?") ? "&" : "?") + "thumb=1&t=" + Date.now();
        btn.appendChild(img);
        btn.addEventListener("click", () => showShotAt(i));
        wrap.appendChild(btn);
      });
    }

    function highlightThumbs() {
      const wrap = el("media-viewer-thumbs");
      if (!wrap) return;
      Array.from(wrap.querySelectorAll("button[data-idx]")).forEach((b) => {
        const i = parseInt(b.dataset.idx, 10);
        b.classList.toggle("ring-2", i === state.idx);
        b.classList.toggle("ring-primary", i === state.idx);
      });
    }

    function showShotAt(i) {
      const total = state.items.length;
      if (!total) return;
      state.idx = Math.max(0, Math.min(total - 1, i));
      updateShotUI();
      highlightThumbs();
      const img = el("media-viewer-shot");
      if (!img) return;
      setMsg("加载中...");
      const url = state.items[state.idx].url + (state.items[state.idx].url.includes("?") ? "&" : "?") + "t=" + Date.now();
      img.onload = () => setMsg("");
      img.onerror = () => setMsg("图片加载失败，请稍后重试或下载查看");
      img.src = url;
    }

    async function openVideo(taskId) {
      state.kind = "video";
      state.taskId = taskId;
      setTitle("视频预览", taskId);
      setPanels("video");
      setMsg("");
      const video = el("media-viewer-video");
      const dl = el("media-viewer-download");
      if (dl) {
        dl.href = `/api/test/video/${encodeURIComponent(taskId)}`;
        dl.textContent = "下载视频";
        dl.innerHTML = '<i class="fa fa-download mr-1"></i>下载视频';
      }
      if (video) {
        video.src = `/api/test/video/view/${encodeURIComponent(taskId)}`;
        try {
          video.load();
        } catch (e) {}
      }
      showModal();
    }

    async function openShots(taskId) {
      state.kind = "shots";
      state.taskId = taskId;
      state.items = [];
      state.idx = 0;
      setTitle("截图预览", taskId);
      setPanels("shots");
      setMsg("正在加载截图列表...");
      const dl = el("media-viewer-download");
      if (dl) {
        dl.href = `/api/test/video/${encodeURIComponent(taskId)}`;
        dl.innerHTML = '<i class="fa fa-download mr-1"></i>下载截图';
      }
      showModal();
      try {
        const data = await apiGet(`/api/test/screenshots/${encodeURIComponent(taskId)}`);
        if (!data || data.code !== 200) {
          throw new Error((data && data.msg) || "加载截图列表失败");
        }
        const items = Array.isArray(data.data && data.data.items) ? data.data.items : [];
        if (!items.length) {
          setMsg("该任务无可用截图（你仍可以点击右下角下载查看）");
          updateShotUI();
          const wrap = el("media-viewer-thumbs");
          if (wrap) wrap.innerHTML = "";
          return;
        }
        state.items = items;
        setMsg("");
        renderThumbs();
        showShotAt(0);
      } catch (e) {
        setMsg(`加载失败：${e.message}`);
      }
    }

    function bindEventsOnce() {
      const close = () => hideModal();
      const c1 = el("media-viewer-close");
      const c2 = el("media-viewer-close2");
      if (c1 && !c1._bound) {
        c1.addEventListener("click", close);
        c1._bound = true;
      }
      if (c2 && !c2._bound) {
        c2.addEventListener("click", close);
        c2._bound = true;
      }
      const modal = el("media-viewer-modal");
      if (modal && !modal._bound) {
        modal.addEventListener("click", (e) => {
          if (e.target === modal) close();
        });
        modal._bound = true;
      }
      const prevBtn = el("media-viewer-prev");
      const nextBtn = el("media-viewer-next");
      if (prevBtn && !prevBtn._bound) {
        prevBtn.addEventListener("click", () => showShotAt(state.idx - 1));
        prevBtn._bound = true;
      }
      if (nextBtn && !nextBtn._bound) {
        nextBtn.addEventListener("click", () => showShotAt(state.idx + 1));
        nextBtn._bound = true;
      }
      if (!window.__mediaViewerKeyBound) {
        window.addEventListener("keydown", (e) => {
          if (!state.open) return;
          if (e.key === "Escape") {
            hideModal();
            return;
          }
          if (state.kind === "shots") {
            if (e.key === "ArrowLeft") showShotAt(state.idx - 1);
            if (e.key === "ArrowRight") showShotAt(state.idx + 1);
          }
        });
        window.__mediaViewerKeyBound = true;
      }
    }

    bindEventsOnce();
    return { openVideo, openShots };
  })();

  function updatePaginationUI(tabKey, page, totalPages, total) {
    if (tabKey === "single") {
      historySinglePageInfo &&
        (historySinglePageInfo.textContent = `第 ${page} 页 / 共 ${totalPages} 页（${total} 条）`);
      if (historySinglePrevPage) historySinglePrevPage.disabled = page <= 1;
      if (historySingleNextPage)
        historySingleNextPage.disabled = page >= totalPages;
      historySinglePagination &&
        historySinglePagination.classList.remove("hidden");
    } else {
      historyExecSetPageInfo &&
        (historyExecSetPageInfo.textContent = `第 ${page} 页 / 共 ${totalPages} 页（${total} 条）`);
      if (historyExecSetPrevPage) historyExecSetPrevPage.disabled = page <= 1;
      if (historyExecSetNextPage)
        historyExecSetNextPage.disabled = page >= totalPages;
      historyExecSetPagination &&
        historyExecSetPagination.classList.remove("hidden");
    }
  }

  function appendTask(task) {
    AppState.taskHistory.unshift(task);
    saveHistory();
    // 新版历史列表以数据库为准，这里触发刷新第一页（让用户立刻看到最新记录）
    refreshActiveTab(true);
  }

  async function loadSinglePage(page) {
    const ps = HistoryState.single.pageSize;
    const url = `/api/test/history?page=${page}&page_size=${ps}`;
    const data = await apiGet(url);
    if (data.code !== 200 || !data.data) {
      throw new Error(data.msg || "加载执行历史失败");
    }
    const items = Array.isArray(data.data.items) ? data.data.items : [];
    HistoryState.single.page = data.data.page || page;
    HistoryState.single.totalPages = data.data.total_pages || 1;
    HistoryState.single.total = data.data.total || 0;
    renderSingleHistory(items);
    updatePaginationUI(
      "single",
      HistoryState.single.page,
      HistoryState.single.totalPages,
      HistoryState.single.total
    );
  }

  async function loadExecSetPage(page) {
    const ps = HistoryState.execSet.pageSize;
    const url = `/api/test/exec-set/history?page=${page}&page_size=${ps}`;
    const data = await apiGet(url);
    if (data.code !== 200 || !data.data) {
      throw new Error(data.msg || "加载执行集执行历史失败");
    }
    const items = Array.isArray(data.data.items) ? data.data.items : [];
    HistoryState.execSet.page = data.data.page || page;
    HistoryState.execSet.totalPages = data.data.total_pages || 1;
    HistoryState.execSet.total = data.data.total || 0;
    renderExecSetHistory(items);
    updatePaginationUI(
      "exec_set",
      HistoryState.execSet.page,
      HistoryState.execSet.totalPages,
      HistoryState.execSet.total
    );
  }

  async function refreshActiveTab(forceFirstPage = false) {
    try {
      if (HistoryState.activeTab === "exec_set") {
        const p = forceFirstPage ? 1 : HistoryState.execSet.page;
        await loadExecSetPage(p);
      } else {
        const p = forceFirstPage ? 1 : HistoryState.single.page;
        await loadSinglePage(p);
      }
    } catch (e) {
      console.error(e);
      addTaskLog &&
        addTaskLog(`[错误] ${e.message || "加载历史失败"}`, "danger");
    }
  }

  function initTabs() {
    if (!historyTabSingle || !historyTabExecSet) return;
    historyTabSingle.addEventListener("click", () => {
      HistoryState.activeTab = "single";
      historyTabSingle.classList.add("border-primary", "text-primary");
      historyTabSingle.classList.remove("text-light");
      historyTabExecSet.classList.remove("border-primary", "text-primary");
      historyTabExecSet.classList.add("text-light");
      historyPanelSingle &&
        historyPanelSingle.classList.remove("hidden");
      historyPanelExecSet &&
        historyPanelExecSet.classList.add("hidden");
      historyExecSetPagination &&
        historyExecSetPagination.classList.add("hidden");
      historySinglePagination &&
        historySinglePagination.classList.remove("hidden");
      refreshActiveTab(false);
    });
    historyTabExecSet.addEventListener("click", () => {
      HistoryState.activeTab = "exec_set";
      historyTabExecSet.classList.add("border-primary", "text-primary");
      historyTabExecSet.classList.remove("text-light");
      historyTabSingle.classList.remove("border-primary", "text-primary");
      historyTabSingle.classList.add("text-light");
      historyPanelExecSet &&
        historyPanelExecSet.classList.remove("hidden");
      historyPanelSingle &&
        historyPanelSingle.classList.add("hidden");
      historySinglePagination &&
        historySinglePagination.classList.add("hidden");
      historyExecSetPagination &&
        historyExecSetPagination.classList.remove("hidden");
      refreshActiveTab(false);
    });
  }

  function initPagination() {
    historySinglePrevPage &&
      historySinglePrevPage.addEventListener("click", () => {
        const next = Math.max(1, HistoryState.single.page - 1);
        loadSinglePage(next).catch((e) => {
          console.error(e);
        });
      });
    historySingleNextPage &&
      historySingleNextPage.addEventListener("click", () => {
        const next = Math.min(
          HistoryState.single.totalPages,
          HistoryState.single.page + 1
        );
        loadSinglePage(next).catch((e) => {
          console.error(e);
        });
      });

    historyExecSetPrevPage &&
      historyExecSetPrevPage.addEventListener("click", () => {
        const next = Math.max(1, HistoryState.execSet.page - 1);
        loadExecSetPage(next).catch((e) => {
          console.error(e);
        });
      });
    historyExecSetNextPage &&
      historyExecSetNextPage.addEventListener("click", () => {
        const next = Math.min(
          HistoryState.execSet.totalPages,
          HistoryState.execSet.page + 1
        );
        loadExecSetPage(next).catch((e) => {
          console.error(e);
        });
      });
  }

  function initClearButton() {
    if (!clearHistoryBtn) return;
    clearHistoryBtn.addEventListener("click", () => {
      if (
        !confirm("确定要清空所有任务历史记录吗？此操作不可恢复！")
      ) {
        return;
      }
      AppState.taskHistory = [];
      saveHistory();
      renderSingleHistory([]);
      renderExecSetHistory([]);
      updatePaginationUI("single", 1, 1, 0);
      updatePaginationUI("exec_set", 1, 1, 0);
      addTaskLog && addTaskLog("[提示] 任务历史已清空", "info");
    });
  }

  function initHistory() {
    loadHistory();
    // 兼容旧结构
    AppState.taskHistory = (AppState.taskHistory || []).map((t) => ({
      ...t,
      reportUrl: t.reportUrl || t.report_url || "",
      status: t.status || "未知",
    }));
    // 初次加载：默认进入“单用例执行历史”第一页
    initPagination();
    refreshActiveTab(true);
    initTabs();
    initClearButton();

    // 历史表格的“查看视频/截图”按钮事件委托
    function bindMediaClick(tbody) {
      if (!tbody || tbody._boundMediaClick) return;
      tbody.addEventListener("click", (e) => {
        const btn = e.target && e.target.closest
          ? e.target.closest("button[data-action='view-media']")
          : null;
        if (!btn) return;
        const kind = btn.dataset.kind;
        const taskId = btn.dataset.taskId ? decodeURIComponent(btn.dataset.taskId) : "";
        if (!taskId) return;
        if (kind === "video") {
          MediaViewer.openVideo(taskId);
        } else {
          MediaViewer.openShots(taskId);
        }
      });
      tbody._boundMediaClick = true;
    }
    bindMediaClick(taskHistoryTableSingle);
    bindMediaClick(taskHistoryTableExecSet);
  }

  window.History = {
    initHistory,
    renderHistory: refreshActiveTab,
    appendTask,
  };
})();

