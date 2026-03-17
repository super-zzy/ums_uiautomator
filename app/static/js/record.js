// 录制页面逻辑：实时展示屏幕 + 鼠标操作生成脚本

(function () {
  const { Elements, Common } = window;
  const { apiGet, apiPost, addTaskLog } = Common || {};

  let isRecording = false;
  let screenshotTimer = null;
  let deviceInfo = null; // { device_id, width, height }
  let dragState = null; // 鼠标拖拽状态，用于识别滑动

  // 动态创建录屏区域所需的 DOM 元素引用
  function resolveElements() {
    return {
      recordStartBtn: document.getElementById("record-start-btn"),
      recordStopBtn: document.getElementById("record-stop-btn"),
      recordSaveBtn: document.getElementById("record-save-btn"),
      recordScreenImg: document.getElementById("record-screen"),
      recordCodeTextarea: document.getElementById("record-code"),
      recordNameInput: document.getElementById("record-name"),
    };
  }

  function getSelectedDeviceId() {
    return window.Devices?.getSelectedDeviceId?.() || null;
  }

  async function fetchDeviceInfo(deviceId) {
    try {
      const resp = await apiGet(
        `/api/record/device-info?device_id=${encodeURIComponent(deviceId)}`
      );
      if (resp.code === 200 && resp.data) {
        deviceInfo = resp.data;
        return deviceInfo;
      }
      throw new Error(resp.msg || "获取设备信息失败");
    } catch (e) {
      console.error("获取设备信息失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 获取设备信息失败：${e.message}`, "danger");
      return null;
    }
  }

  async function startRecording() {
    const els = resolveElements();
    const deviceId = getSelectedDeviceId();
    if (!deviceId) {
      addTaskLog && addTaskLog("[错误] 请先在左侧选择一个在线设备", "danger");
      return;
    }
    try {
      addTaskLog &&
        addTaskLog(
          `[信息] 准备开始录制（设备：${deviceId}），正在初始化...`,
          "info"
        );
      const info = await fetchDeviceInfo(deviceId);
      if (!info) return;

      const resp = await apiPost("/api/record/start", { device_id: deviceId });
      if (resp.code !== 200) {
        throw new Error(resp.msg || "开始录制失败");
      }
      isRecording = true;

      els.recordStartBtn && (els.recordStartBtn.disabled = true);
      els.recordStopBtn && (els.recordStopBtn.disabled = false);
      els.recordSaveBtn && (els.recordSaveBtn.disabled = true);
      els.recordCodeTextarea && (els.recordCodeTextarea.value = "");

      addTaskLog &&
        addTaskLog(
          `[成功] 已开始录制（设备：${deviceId}），请在下方屏幕上点击进行操作`,
          "success"
        );
      startScreenshotLoop();
    } catch (e) {
      console.error("开始录制失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 开始录制失败：${e.message}`, "danger");
    }
  }

  function startScreenshotLoop() {
    const els = resolveElements();
    if (!els.recordScreenImg) return;
    stopScreenshotLoop();

    const loadShot = async () => {
      const deviceId = getSelectedDeviceId();
      if (!deviceId || !isRecording) return;
      try {
        const resp = await fetch(
          `/api/record/screenshot?device_id=${encodeURIComponent(deviceId)}`,
          { cache: "no-store" }
        );
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        els.recordScreenImg.src = url;
      } catch (e) {
        console.error("加载截图失败:", e);
      }
    };

    loadShot();
    screenshotTimer = setInterval(loadShot, 1000);
  }

  function stopScreenshotLoop() {
    if (screenshotTimer) {
      clearInterval(screenshotTimer);
      screenshotTimer = null;
    }
  }

  function mapPointToDeviceCoords(event, img) {
    if (!deviceInfo || !img) return null;

    const rect = img.getBoundingClientRect();
    const naturalWidth = img.naturalWidth || deviceInfo.width;
    const naturalHeight = img.naturalHeight || deviceInfo.height;

    if (!naturalWidth || !naturalHeight || !rect.width || !rect.height) {
      return null;
    }

    // object-contain 情况下，图片会按等比例缩放并在容器中居中显示，需要扣掉上下 / 左右的黑边再做比例换算
    const scale = Math.min(rect.width / naturalWidth, rect.height / naturalHeight);
    const displayWidth = naturalWidth * scale;
    const displayHeight = naturalHeight * scale;

    const offsetLeft = rect.left + (rect.width - displayWidth) / 2;
    const offsetTop = rect.top + (rect.height - displayHeight) / 2;

    let xInImg = event.clientX - offsetLeft;
    let yInImg = event.clientY - offsetTop;

    // 若点击在黑边区域（不在实际图片区域内），视为无效
    if (xInImg < 0 || yInImg < 0 || xInImg > displayWidth || yInImg > displayHeight) {
      return null;
    }

    const px = xInImg / displayWidth;
    const py = yInImg / displayHeight;
    const x = Math.round(px * deviceInfo.width);
    const y = Math.round(py * deviceInfo.height);
    return { x, y };
  }

  async function handleScreenClick(event) {
    event.preventDefault();
    // 若当前有拖拽起点，mouseup 时会处理滑动，这里不再当作点击
    if (!isRecording || !deviceInfo || dragState) return;
    const els = resolveElements();
    const img = els.recordScreenImg;
    if (!img) return;

    const point = mapPointToDeviceCoords(event, img);
    if (!point) return;
    const { x, y } = point;

    const deviceId = getSelectedDeviceId();
    if (!deviceId) return;

    try {
      const resp = await apiPost("/api/record/click", {
        device_id: deviceId,
        x,
        y,
      });
      if (resp.code === 200) {
        addTaskLog &&
          addTaskLog(
            `[信息] 录制点击：(${x}, ${y})，已下发到设备`,
            "info"
          );
      } else {
        throw new Error(resp.msg || "点击失败");
      }
    } catch (e) {
      console.error("录制点击失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 录制点击失败：${e.message}`, "danger");
    }
  }

  function handleScreenMouseDown(event) {
    if (!isRecording || !deviceInfo) return;
    event.preventDefault();
    const els = resolveElements();
    const img = els.recordScreenImg;
    if (!img) return;
    const point = mapPointToDeviceCoords(event, img);
    if (!point) return;
    dragState = {
      startX: point.x,
      startY: point.y,
    };
  }

  async function handleScreenMouseUp(event) {
    if (!isRecording || !deviceInfo) {
      dragState = null;
      return;
    }
    event.preventDefault();
    const els = resolveElements();
    const img = els.recordScreenImg;
    if (!img) {
      dragState = null;
      return;
    }
    const deviceId = getSelectedDeviceId();
    if (!deviceId) {
      dragState = null;
      return;
    }
    if (!dragState) {
      return;
    }
    const startX = dragState.startX;
    const startY = dragState.startY;
    dragState = null;

    const pointEnd = mapPointToDeviceCoords(event, img);
    if (!pointEnd) return;
    const endX = pointEnd.x;
    const endY = pointEnd.y;

    const dx = endX - startX;
    const dy = endY - startY;
    const distance = Math.sqrt(dx * dx + dy * dy);
    // 距离太短当作点击，交给 click 事件（不在这里处理）
    if (distance < 50) {
      return;
    }

    try {
      const resp = await apiPost("/api/record/swipe", {
        device_id: deviceId,
        start_x: startX,
        start_y: startY,
        end_x: endX,
        end_y: endY,
      });
      if (resp.code === 200) {
        addTaskLog &&
          addTaskLog(
            `[信息] 录制滑动：(${startX}, ${startY}) -> (${endX}, ${endY})，已下发到设备`,
            "info"
          );
      } else {
        throw new Error(resp.msg || "滑动失败");
      }
    } catch (e) {
      console.error("录制滑动失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 录制滑动失败：${e.message}`, "danger");
    }
  }

  async function stopRecording() {
    const els = resolveElements();
    const deviceId = getSelectedDeviceId();
    if (!deviceId) {
      addTaskLog && addTaskLog("[错误] 未找到录制中的设备", "danger");
      return;
    }
    try {
      const resp = await apiPost("/api/record/stop", { device_id: deviceId });
      if (resp.code !== 200 || !resp.data) {
        throw new Error(resp.msg || "停止录制失败");
      }
      isRecording = false;
      stopScreenshotLoop();

      const { suggest_name, code } = resp.data;
      if (els.recordNameInput) {
        els.recordNameInput.value =
          (suggest_name && suggest_name.replace(/\.py$/, "")) || "";
      }
      if (els.recordCodeTextarea) {
        els.recordCodeTextarea.value = code || "";
      }

      els.recordStartBtn && (els.recordStartBtn.disabled = false);
      els.recordStopBtn && (els.recordStopBtn.disabled = true);
      els.recordSaveBtn && (els.recordSaveBtn.disabled = false);

      addTaskLog &&
        addTaskLog("[成功] 录制已结束，已生成脚本，请确认后保存为用例", "success");
    } catch (e) {
      console.error("停止录制失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 停止录制失败：${e.message}`, "danger");
    }
  }

  async function saveRecordedCase() {
    const els = resolveElements();
    const nameInput = els.recordNameInput;
    const codeTextarea = els.recordCodeTextarea;
    if (!nameInput || !codeTextarea) return;

    let name = nameInput.value.trim();
    const content = codeTextarea.value || "";

    if (!name) {
      addTaskLog && addTaskLog("[错误] 请先填写用例名称", "danger");
      return;
    }
    if (!content.trim()) {
      addTaskLog && addTaskLog("[错误] 当前脚本为空，无法保存", "danger");
      return;
    }
    if (!name.endsWith(".py")) {
      name = `${name}.py`;
    }

    try {
      const resp = await fetch("/api/test/suite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content }),
      });
      const data = await resp.json();
      if (data.code === 200) {
        addTaskLog &&
          addTaskLog(
            `[成功] 录制脚本已保存为用例：${name}`,
            "success"
          );
        // 刷新右侧用例列表
        window.Suites && window.Suites.loadTestSuites();
        els.recordSaveBtn && (els.recordSaveBtn.disabled = true);
      } else {
        throw new Error(data.msg || "保存用例失败");
      }
    } catch (e) {
      console.error("保存录制用例失败:", e);
      addTaskLog &&
        addTaskLog(`[错误] 保存录制用例失败：${e.message}`, "danger");
    }
  }

  function initRecordUI() {
    const els = resolveElements();
    if (!els.recordStartBtn || !els.recordScreenImg) {
      // 页面上未包含录制区域时直接返回
      return;
    }

    els.recordStartBtn.addEventListener("click", startRecording);
    els.recordStopBtn &&
      els.recordStopBtn.addEventListener("click", stopRecording);
    els.recordSaveBtn &&
      els.recordSaveBtn.addEventListener("click", saveRecordedCase);
    els.recordScreenImg.addEventListener("click", handleScreenClick);
    els.recordScreenImg.addEventListener("mousedown", handleScreenMouseDown);
    window.addEventListener("mouseup", handleScreenMouseUp);

    // 初始状态
    els.recordStartBtn.disabled = false;
    els.recordStopBtn && (els.recordStopBtn.disabled = true);
    els.recordSaveBtn && (els.recordSaveBtn.disabled = true);
  }

  window.Record = {
    initRecordUI,
  };
})();

