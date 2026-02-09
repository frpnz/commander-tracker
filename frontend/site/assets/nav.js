/* Shared navbar generator.
 * Keeps labels consistent across pages.
 * Works with GitHub Pages (relative URLs) by using URL resolution.
 */
(function () {
  // Normalize URLs on hosts that serve directory indexes without a trailing slash.
  // Without this, relative URL resolution can break (notably on some mobile webviews),
  // producing links like /archive/ instead of /<repo>/archive/.
  function ensureTrailingSlashForDirs() {
    try {
      var u = new URL(window.location.href);
      var path = u.pathname || "";
      var last = path.split("/").pop();

      // If it doesn't end with '/' and doesn't look like a file, treat it as a directory.
      if (!path.endsWith("/") && last && last.indexOf(".") === -1) {
        window.location.replace(path + "/" + u.search + u.hash);
        return true; // redirected
      }
    } catch (e) {
      // ignore
    }
    return false;
  }

  function buildNav() {
    if (ensureTrailingSlashForDirs()) return;

    var nav = document.getElementById("nav");
    if (!nav) return;

    // Root is the parent directory of the current page directory
    // e.g. /stats/ -> / ; /repo/stats/ -> /repo/
    var root = new URL("..", window.location.href);

    // Make the logo behave like a Home link (works across GitHub Pages subpaths).
    // Markup uses a <div class="logo">, so we attach link-like behavior here.
    var logo = document.querySelector(".topbar .logo");
    if (logo) {
      var homeHref = new URL("", root).toString();
      logo.style.cursor = "pointer";
      logo.setAttribute("role", "link");
      logo.setAttribute("tabindex", "0");
      logo.setAttribute("aria-label", "Home");
      logo.addEventListener("click", function () {
        window.location.href = homeHref;
      });
      logo.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          window.location.href = homeHref;
        }
      });
    }

    var items = [
      { key: "home", path: "", label: "Home" },
      { key: "archive", path: "archive/", label: "Archivio" },
      { key: "stats", path: "stats/", label: "Stats" },
                  { key: "meta-profile", path: "meta-profile/", label: "Meta Profile" },
      { key: "bracket-calibration", path: "bracket-calibration/", label: "Calibrazione" },
      { key: "new-game", path: "new-game/", label: "Nuova partita" },
      { key: "metrics", path: "metrics/", label: "Metrics" }
    ];

    // Infer active section from the current path (folder name)
    var pathname = window.location.pathname;
    var activeKey = null;
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === "home") continue;
      if (pathname.indexOf("/" + items[i].path) !== -1) {
        activeKey = items[i].key;
        break;
      }
    }
    if (!activeKey) activeKey = "home";

    // Clear and rebuild
    nav.innerHTML = "";
    for (var j = 0; j < items.length; j++) {
      var it = items[j];
      var a = document.createElement("a");
      a.className = "navlink" + (it.key === activeKey ? " active" : "");
      a.href = new URL(it.path, root).toString();
      a.textContent = it.label;
      nav.appendChild(a);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildNav);
  } else {
    buildNav();
  }
})();
