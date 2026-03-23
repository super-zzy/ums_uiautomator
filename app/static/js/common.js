// 全局状态与通用工具（供各模块复用）

// 全局任务状态
window.AppState = {
  currentTaskId: null,
  currentTaskMeta: null,
  // 兼容老的 key（taskHistory）与新的 automation_test_task_history
  taskHistory:
    JSON.parse(localStorage.getItem("automation_test_task_history")) ||
    JSON.parse(localStorage.getItem("taskHistory") || "[]"),
  refreshInterval: null,
};

// DOM 元素集中管理
window.Elements = {
  // 概览数据
  onlineDeviceCount: document.getElementById("online-device-count"),
  testSuiteCount: document.getElementById("test-suite-count"),
  runningTaskCount: document.getElementById("running-task-count"),
  execSetCount: document.getElementById("exec-set-count"),
  historySingleCount: document.getElementById("history-single-count"),
  historyExecSetCount: document.getElementById("history-exec-set-count"),
  currentTime: document.getElementById("current-time"),

  // 设备列表
  deviceList: document.getElementById("device-list"),
  refreshDeviceBtn: document.getElementById("refresh-device-btn"),
  atxGuideBtn: document.getElementById("atx-guide-btn"),

  // 任务管理（在线设备卡片下）
  runningTaskTable: document.getElementById("running-task-table"),
  refreshRunningTasksBtn: document.getElementById("refresh-running-tasks-btn"),

  // 测试配置
  testSuiteSelect: document.getElementById("test-suite-select"),
  startTestBtn: document.getElementById("start-test-btn"),
  stopTestBtn: document.getElementById("stop-test-btn"),
  viewReportBtn: document.getElementById("view-report-btn"),
  taskLog: document.getElementById("task-log"),
  recordVideoCheckbox: document.getElementById("record-video-checkbox"),

  // 用例编辑
  editSuiteBtn: document.getElementById("edit-suite-btn"),
  newSuiteBtn: document.getElementById("new-suite-btn"),
  deleteSuiteBtn: document.getElementById("delete-suite-btn"),
  suiteEditorModal: document.getElementById("suite-editor-modal"),
  closeEditorBtn: document.getElementById("close-editor-btn"),
  cancelEditBtn: document.getElementById("cancel-edit-btn"),
  saveSuiteBtn: document.getElementById("save-suite-btn"),
  suiteContent: document.getElementById("suite-content"),
  editorModalTitle: document.getElementById("editor-modal-title"),
  newSuiteNameContainer: document.getElementById("new-suite-name-container"),
  newSuiteName: document.getElementById("new-suite-name"),

  // 历史记录
  taskHistoryTableSingle: document.getElementById("task-history-table-single"),
  taskHistoryTableExecSet: document.getElementById(
    "task-history-table-exec-set"
  ),
  historyTabSingle: document.getElementById("history-tab-single"),
  historyTabExecSet: document.getElementById("history-tab-exec-set"),
  historyPanelSingle: document.getElementById("history-panel-single"),
  historyPanelExecSet: document.getElementById("history-panel-exec-set"),
  clearHistoryBtn: document.getElementById("clear-history-btn"),
  historySinglePagination: document.getElementById("history-single-pagination"),
  historySinglePageInfo: document.getElementById("history-single-page-info"),
  historySinglePrevPage: document.getElementById("history-single-prev-page"),
  historySingleNextPage: document.getElementById("history-single-next-page"),
  historyExecSetPagination: document.getElementById(
    "history-exec-set-pagination"
  ),
  historyExecSetPageInfo: document.getElementById("history-exec-set-page-info"),
  historyExecSetPrevPage: document.getElementById(
    "history-exec-set-prev-page"
  ),
  historyExecSetNextPage: document.getElementById(
    "history-exec-set-next-page"
  ),

  // 顶部刷新
  refreshBtn: document.getElementById("refresh-btn"),

  // 执行集区域
  execSetList: document.getElementById("exec-set-list"),
  createExecSetBtn: document.getElementById("create-exec-set-btn"),
  execSetEditorModal: document.getElementById("exec-set-editor-modal"),
  closeExecSetEditorBtn: document.getElementById("close-exec-set-editor-btn"),
  cancelExecSetBtn: document.getElementById("cancel-exec-set-btn"),
  saveExecSetBtn: document.getElementById("save-exec-set-btn"),
  execSetEditorTitle: document.getElementById("exec-set-editor-title"),
  execSetName: document.getElementById("exec-set-name"),
  execSetDesc: document.getElementById("exec-set-desc"),
  caseFilterInput: document.getElementById("case-filter-input"),
  allCasesTbody: (function () {
    const table = document.getElementById("all-cases-list");
    return table ? table.querySelector("tbody") : null;
  })(),
  selectedCasesTbody: (function () {
    const table = document.getElementById("selected-cases-list");
    return table ? table.querySelector("tbody") : null;
  })(),
  addSelectedCasesBtn: document.getElementById("add-selected-cases-btn"),
  removeSelectedCasesBtn: document.getElementById("remove-selected-cases-btn"),
  selectedCaseCount: document.getElementById("selected-case-count"),
  execSetSelect: document.getElementById("exec-set-select"),
  startExecSetBtn: document.getElementById("start-exec-set-btn"),

  // 用例/执行集管理 Tabs 与列表分页
  caseManageTab: document.getElementById("case-manage-tab"),
  execSetManageTab: document.getElementById("exec-set-manage-tab"),
  publicMethodManageTab: document.getElementById("public-method-manage-tab"),
  caseManagePanel: document.getElementById("case-manage-panel"),
  execSetManagePanel: document.getElementById("exec-set-manage-panel"),
  publicMethodManagePanel: document.getElementById("public-method-manage-panel"),
  caseListTbody: document.getElementById("case-list-tbody"),
  casePageInfo: document.getElementById("case-page-info"),
  casePrevPage: document.getElementById("case-prev-page"),
  caseNextPage: document.getElementById("case-next-page"),
  execSetPageInfo: document.getElementById("exec-set-page-info"),
  execSetPrevPage: document.getElementById("exec-set-prev-page"),
  execSetNextPage: document.getElementById("exec-set-next-page"),
};

// 通用 API 封装
async function apiGet(url) {
  const resp = await fetch(url);
  return resp.json();
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return resp.json();
}

async function apiPut(url, body) {
  const resp = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return resp.json();
}

// 任务日志输出（委托给独立的 TaskLog 模块）
function addTaskLog(message, type = "info") {
  if (window.TaskLog && typeof window.TaskLog.addLog === "function") {
    window.TaskLog.addLog(message, type);
  }
}

// 任务历史存取（统一使用 automation_test_task_history）
function saveHistory() {
  try {
    localStorage.setItem(
      "automation_test_task_history",
      JSON.stringify(AppState.taskHistory || [])
    );
    // 兼容旧 key
    localStorage.setItem(
      "taskHistory",
      JSON.stringify(AppState.taskHistory || [])
    );
  } catch (e) {
    console.error("保存任务历史失败", e);
    addTaskLog(`[错误] 任务历史保存失败：${e.message}`, "danger");
  }
}

function loadHistory() {
  try {
    const str =
      localStorage.getItem("automation_test_task_history") ||
      localStorage.getItem("taskHistory");
    if (!str) {
      AppState.taskHistory = [];
      return;
    }
    const arr = JSON.parse(str);
    if (!Array.isArray(arr)) {
      AppState.taskHistory = [];
      saveHistory();
    } else {
      AppState.taskHistory = arr;
    }
  } catch (e) {
    console.error("加载任务历史失败", e);
    AppState.taskHistory = [];
    addTaskLog(`[错误] 任务历史加载失败：${e.message}`, "danger");
  }
}

// 简单的日期时间解析（后端格式：YYYY-MM-DD HH:MM:SS）
function parseDateTime(value) {
  if (!value) return null;
  try {
    const str = String(value).trim().replace(" ", "T");
    const ts = Date.parse(str);
    if (Number.isNaN(ts)) return null;
    return new Date(ts);
  } catch (e) {
    return null;
  }
}

// 将秒数格式化为「X小时Y分Z秒」
function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}h${m}m${s}s`;
  }
  if (m > 0) {
    return `${m}m${s}s`;
  }
  return `${s}s`;
}

window.Common = {
  apiGet,
  apiPost,
  apiPut,
  addTaskLog,
  saveHistory,
  loadHistory,
  parseDateTime,
  formatDuration,
};

