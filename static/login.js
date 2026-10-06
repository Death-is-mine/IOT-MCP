/* Sign-in page (classic script: no modules, no inline code, CSP-clean).
Token slot shared with every page: localStorage "cem_token".
Firebase tabs need a web config below; the apiKey is a public client
identifier (Firebase docs), not a secret — paste the project's web app
config object to enable Email/Google/Phone. Dev tab always works. */
(function () {
  var CEM_FIREBASE_CONFIG = null; /* e.g. {apiKey:"…",authDomain:"….firebaseapp.com",projectId:"…"} */

  function $(id) { return document.getElementById(id); }
  function fail(e) {
    $("err").textContent = String((e && e.message) || e);
  }

  var tabs = document.querySelectorAll(".auth-tab");
  function show(name) {
    document.querySelectorAll("[data-panel]").forEach(function (p) {
      p.hidden = p.getAttribute("data-panel") !== name;
    });
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { show(t.getAttribute("data-tab")); });
  });
  show("email");

  var auth = null;
  if (CEM_FIREBASE_CONFIG && window.firebase) {
    try {
      firebase.initializeApp(CEM_FIREBASE_CONFIG);
      auth = firebase.auth();
      auth.onAuthStateChanged(function (u) {
        $("who").textContent = u ? "Signed in as " + (u.email || u.phoneNumber) : "";
      });
    } catch (e) { fail(e); }
  }

  function needAuth() {
    if (!auth) {
      $("err").textContent = "Firebase is not configured in this build — use the Dev token tab.";
      return null;
    }
    if (!window.firebase) {
      $("err").textContent = "Firebase SDK failed to load.";
      return null;
    }
    return auth;
  }

  $("btn-email").addEventListener("click", function () {
    var a = needAuth();
    if (!a) return;
    a.signInWithEmailAndPassword($("email").value, $("pw").value).then(save).catch(fail);
  });
  $("btn-google").addEventListener("click", function () {
    var a = needAuth();
    if (!a) return;
    a.signInWithPopup(new firebase.auth.GoogleAuthProvider()).then(save).catch(fail);
  });
  var confirm = null;
  $("btn-phone-send").addEventListener("click", function () {
    var a = needAuth();
    if (!a) return;
    window.recaptchaVerifier = new firebase.auth.RecaptchaVerifier($("recaptcha"), {size: "invisible"});
    a.signInWithPhoneNumber($("phone").value, window.recaptchaVerifier).then(function (c) {
      confirm = c;
      $("err").textContent = "Code sent.";
    }).catch(fail);
  });
  $("btn-phone-verify").addEventListener("click", function () {
    if (!confirm) { $("err").textContent = "Send a code first."; return; }
    confirm.confirm($("code").value).then(save).catch(fail);
  });

  function save(res) {
    var u = (res && res.user) || res;
    return u.getIdToken().then(function (tok) {
      localStorage.setItem("cem_token", tok);
      window.location.href = "/fleet";
    }).catch(fail);
  }

  $("btn-dev-save").addEventListener("click", function () {
    localStorage.setItem("cem_token", $("dev-token").value.trim());
    window.location.href = "/fleet";
  });
})();
