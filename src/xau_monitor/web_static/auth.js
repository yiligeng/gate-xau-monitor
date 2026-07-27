const form = document.querySelector("#login-form");
const button = document.querySelector("#login-button");
const errorNode = document.querySelector("#login-error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorNode.textContent = "";
  button.disabled = true;
  button.textContent = "正在验证…";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.username.value.trim(),
        password: form.password.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "登录失败");
    }
    window.location.replace("/");
  } catch (error) {
    errorNode.textContent = error.message;
    form.password.select();
  } finally {
    button.disabled = false;
    button.textContent = "登录";
  }
});
