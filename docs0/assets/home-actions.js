/* Home buttons generator.
 * Uses the same NAV_ITEMS list as the navbar.
 */
(function () {
  function ensureTrailingSlashForDirs() {
    try {
      var u = new URL(window.location.href);
      var path = u.pathname || "";
      var last = path.split("/").pop();
      if (!path.endsWith("/") && last && last.indexOf(".") === -1) {
        window.location.replace(path + "/" + u.search + u.hash);
        return true;
      }
    } catch (e) {}
    return false;
  }

  function buildHomeActions() {
    if (ensureTrailingSlashForDirs()) return;

    var wrap = document.querySelector(".home-actions");
    if (!wrap) return;

    var items = (window.NAV_ITEMS && window.NAV_ITEMS.slice && window.NAV_ITEMS.slice()) || [];

    // On Home we want buttons for sections, not for "Home" itself.
    var out = [];
    for (var i = 0; i < items.length; i++) {
      if (items[i] && items[i].key !== "home") out.push(items[i]);
    }

    // Root for Home is the current directory (./)
    var root = new URL(".", window.location.href);

    wrap.innerHTML = "";
    for (var j = 0; j < out.length; j++) {
      var it = out[j];
      var a = document.createElement("a");
      a.className = "btn";
      a.href = new URL(it.path, root).toString();
      a.textContent = it.label;
      wrap.appendChild(a);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildHomeActions);
  } else {
    buildHomeActions();
  }
})();
