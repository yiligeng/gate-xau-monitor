const form = document.querySelector("#account-form");
const currentUser = document.querySelector("#current-user");
const message = document.querySelector("#account-message");
const saveButton = document.querySelector("#save-button");
const logoutButton = document.querySelector("#logout-button");

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = { ok: false, error: "服务器响应异常" };
  }
  if (response.status === 401 && url !== "/api/auth/change-credentials") {
    window.location.replace("/login");
    throw new Error("登录已过期");
  }
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "操作失败");
  }
  return payload;
}

async function loadAccount() {
  try {
    const payload = await request("/api/auth/me");
    currentUser.textContent = payload.user.username;
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  const newPassword = form.new_password.value;
  if (newPassword !== form.confirm_password.value) {
    message.textContent = "两次新密码不一致";
    message.className = "form-message error";
    return;
  }
  if (!form.new_username.value.trim() && !newPassword) {
    message.textContent = "请填写新用户名或新密码";
    message.className = "form-message error";
    return;
  }
  saveButton.disabled = true;
  saveButton.textContent = "正在保存…";
  try {
    const payload = await request("/api/auth/change-credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: form.current_password.value,
        new_username: form.new_username.value.trim() || null,
        new_password: newPassword || null,
      }),
    });
    currentUser.textContent = payload.user.username;
    form.reset();
    message.textContent = "账号信息已经更新，其他登录会话已撤销。";
    message.className = "form-message success";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "保存修改";
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await request("/api/auth/logout", { method: "POST" });
  } catch {
    // The cookie is cleared server-side when possible. Either way, leave the UI.
  }
  window.location.replace("/login");
});

loadAccount();
