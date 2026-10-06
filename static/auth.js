/* Shared auth gate (classic script: no modules, no inline code, CSP-clean).
Runs on load: without a token it sends the browser to /login, except on
pages whose body carries data-auth="optional" (landing page). */
(function () {
  function checkAuth(redirectToLogin) {
    var token = localStorage.getItem("cem_token");
    var signedOut = document.getElementById("nav-signed-out");
    var signedIn = document.getElementById("nav-signed-in");
    if (signedOut) signedOut.style.display = token ? "none" : "block";
    if (signedIn) signedIn.style.display = token ? "block" : "none";
    if (!token && redirectToLogin) window.location.href = "/login";
    return !!token;
  }

  function setupLogout() {
    var btn = document.getElementById("btn-logout");
    if (btn) {
      btn.addEventListener("click", function () {
        localStorage.removeItem("cem_token");
        window.location.href = "/";
      });
    }
  }

  var optional = document.body && document.body.dataset.auth === "optional";
  checkAuth(!optional);
  setupLogout();
})();
