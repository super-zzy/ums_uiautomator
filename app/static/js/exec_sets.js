// 执行集管理与执行模块

(function () {
  const { Elements, AppState, Common } = window;
  const {
    execSetList,
    createExecSetBtn,
    execSetEditorModal,
    closeExecSetEditorBtn,
    cancelExecSetBtn,
    saveExecSetBtn,
    execSetEditorTitle,
    execSetName,
    execSetDesc,
    allCasesTbody,
    selectedCasesTbody,
    addSelectedCasesBtn,
    removeSelectedCasesBtn,
    selectedCaseCount,
    execSetSelect,
    startExecSetBtn,
    execSetPageInfo,
    execSetPrevPage,
    execSetNextPage,
    recordVideoCheckbox,
  } = Elements || {};
  const { apiGet, apiPost, addTaskLog, parseDateTime, formatDuration } =
    Common || {};

  let currentEditingExecSetId = null;
  let selectedCaseIds = [];
  let allCasesCache = [];
  let allExecSetsCache = [];
  let execSetPage = 1;
  const EXEC_SET_PAGE_SIZE = 10;

  function renderExecSetTable() {
    if (!execSetList) return;
    const list = allExecSetsCache || [];
    if (!list.length) {
      execSetList.innerHTML = `
            <tr>
              <td colspan="6" class="text-center py-4 text-light">
                暂无执行集，请点击"新建执行集"创建
              </td>
            </tr>
          `;
      execSetPageInfo && (execSetPageInfo.textContent = "第 1 页");
      execSetPrevPage && (execSetPrevPage.disabled = true);
      execSetNextPage && (execSetNextPage.disabled = true);
      return;
    }
    const total = list.length;
    const totalPages = Math.max(1, Math.ceil(total / EXEC_SET_PAGE_SIZE));
    if (execSetPage > totalPages) execSetPage = totalPages;
    if (execSetPage < 1) execSetPage = 1;
    const start = (execSetPage - 1) * EXEC_SET_PAGE_SIZE;
    const end = start + EXEC_SET_PAGE_SIZE;
    const pageItems = list.slice(start, end);
    execSetList.innerHTML = pageItems
      .map(
        (es) => `
            <tr class="border-b border-gray-100 hover:bg-gray-50">
              <td class="py-3 px-4 text-sm">${es.id}</td>
              <td class="py-3 px-4 text-sm">${es.name}</td>
              <td class="py-3 px-4 text-sm">${es.case_count}</td>
              <td class="py-3 px-4 text-sm text-light">${es.created_at || ""}</td>
              <td class="py-3 px-4 text-sm text-light">${es.updated_at || ""}</td>
              <td class="py-3 px-4 text-sm">
                <button class="text-success hover:text-success/80 mr-2" data-action="start" data-id="${es.id}" data-name="${es.name}">
                  <i class="fa fa-play"></i> 启动
                </button>
                <button class="text-primary hover:text-primary/80 mr-2" data-action="view-report" data-id="${es.id}" data-name="${es.name}">
                  <i class="fa fa-file-text-o"></i> 查看报告
                </button>
                <button class="text-primary hover:text-primary/80 mr-2" data-action="edit" data-id="${es.id}">
                  <i class="fa fa-edit"></i> 编辑
                </button>
                <button class="text-danger hover:text-danger/80 mr-2" data-action="delete" data-id="${es.id}" data-name="${es.name}">
                  <i class="fa fa-trash"></i> 删除
                </button>
                <button class="text-success hover:text-success/80" data-action="select" data-id="${es.id}" data-name="${es.name}">
                  <i class="fa fa-check"></i> 选择
                </button>
              </td>
            </tr>
          `
      )
      .join("");
    execSetPageInfo &&
      (execSetPageInfo.textContent = `第 ${execSetPage} / ${totalPages} 页，共 ${total} 条`);
    if (execSetPrevPage) {
      execSetPrevPage.disabled = execSetPage <= 1;
    }
    if (execSetNextPage) {
      execSetNextPage.disabled = execSetPage >= totalPages;
    }
  }

  async function loadExecSets() {
    if (!execSetList || !execSetSelect) return;
    try {
      const data = await apiGet("/api/test/exec-sets");
      if (data.code === 200 && Array.isArray(data.data)) {
        allExecSetsCache = data.data;
        execSetPage = 1;
        renderExecSetTable();
        // 行内按钮事件委托（仅绑定一次）
        if (!execSetList._boundClick) {
          execSetList.addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-action]");
            if (!btn) return;
            const action = btn.dataset.action;
            const id = btn.dataset.id;
            const name = btn.dataset.name;
            if (!id) return;
            if (action === "start") {
              selectExecSet(id, name);
              startExecSetTest();
            } else if (action === "view-report") {
              openLatestExecSetReport(id, name);
            } else if (action === "edit") {
              editExecSet(id);
            } else if (action === "delete") {
              deleteExecSet(id, name);
            } else if (action === "select") {
              selectExecSet(id, name);
            }
          });
          execSetList._boundClick = true;
        }
        execSetSelect.innerHTML =
          '<option value="" disabled selected>请选择执行集</option>' +
          allExecSetsCache
            .map(
              (es) =>
                `<option value="${es.id}">${es.name}（${es.case_count}个用例）</option>`
            )
            .join("");
      } else {
        throw new Error(data.msg || "加载执行集失败");
      }
    } catch (e) {
      console.error("加载执行集失败:", e);
      execSetList.innerHTML = `
        <tr>
          <td colspan="6" class="text-center py-4 text-danger">加载失败：${e.message}</td>
        </tr>
      `;
    }
  }

  async function loadAllCasesForExecSet() {
    if (!allCasesTbody) return;
    try {
      const data = await apiGet("/api/test/suites");
      if (data.code === 200 && Array.isArray(data.data)) {
        allCasesCache = data.data;
        allCasesTbody.innerHTML = allCasesCache
          .map(
            (c) => `
          <tr class="border-b border-gray-100 hover:bg-gray-50">
            <td class="py-2 px-2 text-center">
              <input type="checkbox" class="case-checkbox" value="${c.id}">
            </td>
            <td class="py-2 px-2 text-xs">${c.name} (${c.rel_path})</td>
          </tr>
        `
          )
          .join("");
        // 用例列表加载完成后，根据最新的 allCasesCache 重新渲染已选用例，
        // 避免在编辑执行集时仅显示 ID 占位信息。
        renderSelectedCases();
      } else {
        throw new Error(data.msg || "加载用例失败");
      }
    } catch (e) {
      console.error("加载用例失败:", e);
      allCasesTbody.innerHTML = `
        <tr>
          <td colspan="2" class="text-center py-4 text-danger text-xs">
            加载失败：${e.message}
          </td>
        </tr>
      `;
    }
  }

  function renderSelectedCases() {
    if (!selectedCasesTbody || !selectedCaseCount) return;
    selectedCaseCount.textContent = selectedCaseIds.length;
    if (!selectedCaseIds.length) {
      selectedCasesTbody.innerHTML = `
        <tr>
          <td colspan="2" class="text-center py-4 text-light text-xs">暂无选中用例</td>
        </tr>
      `;
      return;
    }
    const map = {};
    allCasesCache.forEach((c) => {
      map[c.id] = c;
    });
    selectedCasesTbody.innerHTML = selectedCaseIds
      .map((id) => {
        const c = map[id] || { name: `ID=${id}`, rel_path: "" };
        return `
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-2 px-2 text-center">
            <input type="checkbox" class="selected-case-checkbox" value="${id}">
          </td>
          <td class="py-2 px-2 text-xs">${c.name} (${c.rel_path})</td>
        </tr>
      `;
      })
      .join("");
  }

  function openCreateExecSetModal() {
    currentEditingExecSetId = null;
    selectedCaseIds = [];
    execSetEditorTitle && (execSetEditorTitle.textContent = "新建执行集");
    execSetName && (execSetName.value = "");
    execSetDesc && (execSetDesc.value = "");
    renderSelectedCases();
    loadAllCasesForExecSet();
    execSetEditorModal &&
      execSetEditorModal.classList.remove("hidden");
  }

  async function editExecSet(id) {
    try {
      const data = await apiGet(`/api/test/exec-set/${id}`);
      if (data.code === 200 && data.data) {
        const es = data.data;
        currentEditingExecSetId = id;
        selectedCaseIds = (es.cases || [])
          .map((c) => c.case_id)
          .filter((v) => v !== undefined && v !== null)
          .map((v) => parseInt(v, 10));
        execSetEditorTitle &&
          (execSetEditorTitle.textContent = "编辑执行集");
        execSetName && (execSetName.value = es.name || "");
        execSetDesc && (execSetDesc.value = es.description || "");
        renderSelectedCases();
        loadAllCasesForExecSet();
        execSetEditorModal &&
          execSetEditorModal.classList.remove("hidden");
      } else {
        throw new Error(data.msg || "获取执行集详情失败");
      }
    } catch (e) {
      console.error("编辑执行集失败:", e);
      addTaskLog &&
        addTaskLog(
          `[错误] 打开执行集编辑框失败：${e.message}`,
          "danger"
        );
    }
  }

  async function deleteExecSet(id, name) {
    if (!confirm(`确定要删除执行集"${name}"吗？`)) return;
    try {
      const resp = await fetch(`/api/test/exec-set/${id}`, {
        method: "DELETE",
      });
      const data = await resp.json();
      if (data.code === 200) {
        addTaskLog &&
          addTaskLog("[成功] 执行集删除成功", "success");
        loadExecSets();
      } else {
        throw new Error(data.msg || "删除执行集失败");
      }
    } catch (e) {
      console.error("删除执行集失败:", e);
      addTaskLog &&
        addTaskLog(
          `[错误] 删除执行集失败：${e.message}`,
          "danger"
        );
    }
  }

  function selectExecSet(id, name) {
    if (!execSetSelect) return;
    execSetSelect.value = id;
    updateStartExecSetBtnStatus();
    addTaskLog &&
      addTaskLog(`[信息] 已选择执行集：${name}`, "info");
  }

  function updateStartExecSetBtnStatus() {
    if (!startExecSetBtn || !execSetSelect) return;
    const deviceId = window.Devices?.getSelectedDeviceId?.();
    const execId = execSetSelect.value;
    startExecSetBtn.disabled = !deviceId || !execId;
  }

  function addSelectedCases() {
    const nodes = document.querySelectorAll(".case-checkbox:checked");
    const newIds = Array.from(nodes).map((n) =>
      parseInt(n.value, 10)
    );
    const set = new Set(selectedCaseIds);
    newIds.forEach((id) => {
      if (!set.has(id)) selectedCaseIds.push(id);
    });
    nodes.forEach((n) => (n.checked = false));
    renderSelectedCases();
  }

  function removeSelectedCases() {
    const nodes = document.querySelectorAll(
      ".selected-case-checkbox:checked"
    );
    const remove = new Set(
      Array.from(nodes).map((n) => parseInt(n.value, 10))
    );
    selectedCaseIds = selectedCaseIds.filter((id) => !remove.has(id));
    renderSelectedCases();
  }

  async function saveExecSet() {
    const name = execSetName ? execSetName.value.trim() : "";
    const desc = execSetDesc ? execSetDesc.value.trim() : "";
    if (!name) {
      alert("执行集名称不能为空");
      return;
    }
    if (!Array.isArray(selectedCaseIds) || !selectedCaseIds.length) {
      if (
        !confirm(
          "当前执行集未选择任何用例，确定要继续保存吗？"
        )
      ) {
        return;
      }
    }
    try {
      let id = currentEditingExecSetId;
      if (!id) {
        const createData = await apiPost("/api/test/exec-set", {
          name,
          description: desc,
        });
        if (createData.code !== 200 || !createData.data?.id) {
          throw new Error(
            createData.msg || "创建执行集失败"
          );
        }
        id = createData.data.id;
      } else {
        const resp = await fetch(`/api/test/exec-set/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, description: desc }),
        });
        const data = await resp.json();
        if (data.code !== 200) {
          throw new Error(
            data.msg || "更新执行集信息失败"
          );
        }
      }
      const casesResp = await fetch(
        `/api/test/exec-set/${id}/cases`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ suite_ids: selectedCaseIds }),
        }
      );
      const casesData = await casesResp.json();
      if (casesData.code !== 200) {
        throw new Error(
          casesData.msg || "保存执行集用例失败"
        );
      }
      addTaskLog &&
        addTaskLog(
          `[成功] 执行集保存成功（ID：${id}，用例数：${casesData.data.case_count}）`,
          "success"
        );
      closeExecSetEditorModal();
      loadExecSets();
    } catch (e) {
      console.error("保存执行集出错：", e);
      alert(`保存执行集时发生错误：${e.message}`);
    }
  }

  function closeExecSetEditorModal() {
    execSetEditorModal &&
      execSetEditorModal.classList.add("hidden");
    currentEditingExecSetId = null;
    selectedCaseIds = [];
  }

  async function openLatestExecSetReport(execSetId, execSetName) {
    try {
      const data = await apiGet(
        `/api/test/exec-set/history?exec_set_id=${encodeURIComponent(
          execSetId
        )}&limit=1`
      );
      if (data.code !== 200 || !Array.isArray(data.data) || !data.data.length) {
        addTaskLog &&
          addTaskLog(
            `[提示] 执行集「${execSetName}」暂无可用执行历史`,
            "info"
          );
        return;
      }
      const latest = data.data[0];
      if (!latest.task_id || !latest.report_index_path) {
        addTaskLog &&
          addTaskLog(
            `[提示] 执行集「${execSetName}」最近一次执行尚未生成报告`,
            "info"
          );
        return;
      }
      const url = `/api/report/files/${encodeURIComponent(
        latest.task_id
      )}/index.html`;
      window.open(url, "_blank");
    } catch (e) {
      console.error("打开执行集最新报告失败:", e);
      addTaskLog &&
        addTaskLog(
          `[错误] 获取执行集「${execSetName}」最新执行结果失败：${e.message}`,
          "danger"
        );
    }
  }

  async function startExecSetTest() {
    const deviceId = window.Devices?.getSelectedDeviceId?.();
    const execId = execSetSelect ? execSetSelect.value : "";
    if (!deviceId || !execId) {
      addTaskLog &&
        addTaskLog("[错误] 请先选择设备和执行集", "danger");
      return;
    }
    const execName =
      execSetSelect.options[execSetSelect.selectedIndex].text;
    try {
      addTaskLog &&
        addTaskLog(
          `[信息] 正在启动执行集测试（设备：${deviceId}，执行集：${execName}）`,
          "info"
        );
      const data = await apiPost("/api/test/start-exec-set", {
        device_id: deviceId,
        exec_set_id: execId,
        record_video: !!(recordVideoCheckbox && recordVideoCheckbox.checked),
      });
      if (data.code === 200) {
        const mainTaskId = data.data.main_task_id;
        addTaskLog &&
          addTaskLog(
            `[成功] 执行集测试任务已启动（主任务ID：${mainTaskId}，子任务数：${data.data.sub_task_count}）`,
            "success"
          );
        const newTask = {
          id: mainTaskId,
          device: deviceId,
          execSetName: data.data.exec_set_name || execName,
          suite: execName,
          type: "exec_set",
          status: "运行中",
          time: new Date().toLocaleString("zh-CN"),
          reportUrl: "",
        };
        window.History?.appendTask?.(newTask);
        pollExecSetStatus(mainTaskId);
      } else {
        throw new Error(data.msg || "启动执行集测试失败");
      }
    } catch (e) {
      console.error("启动执行集测试失败:", e);
      addTaskLog &&
        addTaskLog(
          `[错误] 启动执行集测试失败：${e.message}`,
          "danger"
        );
    }
  }

  async function pollExecSetStatus(
    mainTaskId,
    errorRetry = 0
  ) {
    const maxErrorRetry = 10;
    const url = `/api/test/status/${encodeURIComponent(
      mainTaskId
    )}`;
    try {
      const resp = await fetch(url);
      if (!resp.ok) {
        if (errorRetry < maxErrorRetry) {
          setTimeout(
            () =>
              pollExecSetStatus(mainTaskId, errorRetry + 1),
            3000
          );
        } else {
          addTaskLog &&
            addTaskLog(
              "[错误] 多次重试后仍无法获取执行集任务状态（HTTP错误），请稍后手动刷新页面。",
              "danger"
            );
        }
        return;
      }
      const data = await resp.json();
      if (data.code !== 200 || !data.data) {
        if (errorRetry < maxErrorRetry) {
          setTimeout(
            () =>
              pollExecSetStatus(mainTaskId, errorRetry + 1),
            3000
          );
        } else {
          addTaskLog &&
            addTaskLog(
              "[错误] 多次重试后仍无法获取执行集任务状态（后端错误），请稍后手动刷新页面。",
              "danger"
            );
        }
        return;
      }
      const task = data.data;
      if (task.status === "running" || task.status === "pending") {
        setTimeout(
          () => pollExecSetStatus(mainTaskId, 0),
          3000
        );
        return;
      }
      const statusText =
        task.status && task.status.toString().includes("success")
          ? "成功"
          : "失败";
      const reportUrl = task.report_url || "";
      const idx = (AppState.taskHistory || []).findIndex(
        (t) => t.id === mainTaskId
      );
      if (idx !== -1) {
        AppState.taskHistory[idx].status = statusText;
        if (reportUrl) {
          AppState.taskHistory[idx].reportUrl = reportUrl;
        }
        // 计算耗时
        try {
          const start = parseDateTime && parseDateTime(task.start_time);
          const end = parseDateTime && parseDateTime(task.end_time);
          if (start && end) {
            const sec = Math.max(
              0,
              Math.floor((end.getTime() - start.getTime()) / 1000)
            );
            AppState.taskHistory[idx].duration = formatDuration
              ? formatDuration(sec)
              : `${sec}s`;
          }
        } catch (e) {
          // ignore parse error
        }
        Common.saveHistory();
        window.History?.renderHistory?.();
      }
      addTaskLog &&
        addTaskLog(
          `[信息] 执行集任务 ${mainTaskId} 已结束，状态：${statusText}${
            reportUrl ? "，汇总报告已生成" : ""
          }`,
          statusText === "成功" ? "success" : "danger"
        );
    } catch (e) {
      console.error("轮询执行集任务状态失败:", e, "url:", url);
      if (errorRetry < maxErrorRetry) {
        setTimeout(
          () => pollExecSetStatus(mainTaskId, errorRetry + 1),
          3000
        );
      } else {
        addTaskLog &&
          addTaskLog(
            "[错误] 多次重试后仍无法获取执行集任务状态（网络异常），请稍后手动刷新页面。",
            "danger"
          );
      }
    }
  }

  function initExecSetEvents() {
    createExecSetBtn &&
      createExecSetBtn.addEventListener(
        "click",
        openCreateExecSetModal
      );
    closeExecSetEditorBtn &&
      closeExecSetEditorBtn.addEventListener(
        "click",
        closeExecSetEditorModal
      );
    cancelExecSetBtn &&
      cancelExecSetBtn.addEventListener(
        "click",
        closeExecSetEditorModal
      );
    saveExecSetBtn &&
      saveExecSetBtn.addEventListener("click", saveExecSet);
    addSelectedCasesBtn &&
      addSelectedCasesBtn.addEventListener(
        "click",
        addSelectedCases
      );
    removeSelectedCasesBtn &&
      removeSelectedCasesBtn.addEventListener(
        "click",
        removeSelectedCases
      );
    execSetSelect &&
      execSetSelect.addEventListener(
        "change",
        updateStartExecSetBtnStatus
      );
    startExecSetBtn &&
      startExecSetBtn.addEventListener(
        "click",
        startExecSetTest
      );

    // 执行集分页
    if (execSetPrevPage) {
      execSetPrevPage.addEventListener("click", () => {
        execSetPage -= 1;
        renderExecSetTable();
      });
    }
    if (execSetNextPage) {
      execSetNextPage.addEventListener("click", () => {
        execSetPage += 1;
        renderExecSetTable();
      });
    }
  }

  function initExecSets() {
    initExecSetEvents();
    loadExecSets();
  }

  window.ExecSets = {
    initExecSets,
    loadExecSets,
    updateStartExecSetBtnStatus,
  };
})();

