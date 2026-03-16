// 全局状态与通用工具（供各模块复用）

// 全局任务状态
window.AppState = {
  currentTaskId: null,
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
  currentTime: document.getElementById("current-time"),

  // 设备列表
  deviceList: document.getElementById("device-list"),
  refreshDeviceBtn: document.getElementById("refresh-device-btn"),

  // 测试配置
  testSuiteSelect: document.getElementById("test-suite-select"),
  startTestBtn: document.getElementById("start-test-btn"),
  stopTestBtn: document.getElementById("stop-test-btn"),
  viewReportBtn: document.getElementById("view-report-btn"),
  taskLog: document.getElementById("task-log"),

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

// 任务日志输出
function addTaskLog(message, type = "info") {
  const { taskLog } = Elements;
  if (!taskLog) return;

  const logTypes = {
    info: "text-dark",
    success: "text-success",
    warning: "text-warning",
    danger: "text-danger",
  };

  const logElement = document.createElement("p");
  logElement.className = `${logTypes[type] || "text-dark"} mb-1`;
  logElement.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;

  taskLog.appendChild(logElement);
  taskLog.scrollTop = taskLog.scrollHeight;
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

window.Common = {
  apiGet,
  apiPost,
  addTaskLog,
  saveHistory,
  loadHistory,
};

