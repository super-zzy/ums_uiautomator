// 在线设备模块

(function () {
  const { Elements, Common, AppState } = window;
  const { deviceList, onlineDeviceCount, refreshDeviceBtn } = Elements || {};
  const { apiGet } = Common || {};

  async function loadDeviceList() {
    if (!deviceList || !onlineDeviceCount) return;
    try {
      deviceList.innerHTML = `
        <div class="text-center text-light py-8">
          <i class="fa fa-spinner fa-spin text-2xl mb-2"></i>
          <p>加载设备中...</p>
        </div>
      `;
      const data = await apiGet("/api/device/list");
      if (data.code === 200 && Array.isArray(data.data)) {
        const devices = data.data;
        onlineDeviceCount.textContent = devices.length;
        if (devices.length === 0) {
          deviceList.innerHTML = `
            <div class="text-center text-light py-8">
              <i class="fa fa-mobile text-2xl mb-2 opacity-50"></i>
              <p>未发现在线设备，请检查ADB连接</p>
            </div>
          `;
          Elements.startTestBtn && (Elements.startTestBtn.disabled = true);
          return;
        }

        deviceList.innerHTML = devices
          .map(
            (device) => `
          <div class="border border-gray-200 rounded-lg p-3 hover:border-primary transition-colors cursor-pointer device-item"
               data-device-id="${device.device_id}">
            <div class="flex justify-between items-start">
              <div>
                <h4 class="font-medium">${device.device_name || device.device_id}</h4>
                <p class="text-sm text-light mt-1">
                  <span>型号：${device.model || "未知"}</span> |
                  <span>Android ${device.android_version || "未知"}</span>
                </p>
              </div>
              <span class="bg-success/10 text-success text-xs px-2 py-1 rounded-full">
                在线
              </span>
            </div>
          </div>
        `
          )
          .join("");

        // 设备点击选择
        document.querySelectorAll(".device-item").forEach((item) => {
          item.addEventListener("click", () => {
            document.querySelectorAll(".device-item").forEach((i) =>
              i.classList.remove("border-primary", "bg-primary/5")
            );
            item.classList.add("border-primary", "bg-primary/5");
            // 更新启动按钮状态（单用例 + 执行集）
            window.Suites?.updateStartBtnStatus?.();
            window.ExecSets?.updateStartExecSetBtnStatus?.();
          });
        });

        // 默认选中第一个
        const first = document.querySelector(".device-item");
        if (first) {
          first.classList.add("border-primary", "bg-primary/5");
        }
      } else {
        throw new Error(data.msg || "加载设备列表失败");
      }
    } catch (e) {
      console.error("加载设备列表失败:", e);
      deviceList.innerHTML = `
        <div class="text-center text-danger py-8">
          <i class="fa fa-exclamation-circle text-2xl mb-2"></i>
          <p>${e.message}</p>
        </div>
      `;
    }
  }

  function getSelectedDeviceId() {
    const selected = document.querySelector(".device-item.border-primary");
    return selected ? selected.dataset.deviceId : null;
  }

  function initDevices() {
    if (refreshDeviceBtn) {
      refreshDeviceBtn.addEventListener("click", loadDeviceList);
    }
  }

  window.Devices = {
    initDevices,
    loadDeviceList,
    getSelectedDeviceId,
  };
})();

