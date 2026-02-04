/* Shared navbar generator.
 * Keeps labels consistent across pages.
 * Works with GitHub Pages (relative URLs) by using URL resolution.
 */
(function () {
  function buildNav() {
    var nav = document.getElementById("nav");
    if (!nav) return;

    // Root is the parent directory of the current page directory
    // e.g. /stats/ -> / ; /repo/stats/ -> /repo/
    var root = new URL("..", window.location.href);

    var items = [
      { key: "home", path: "", label: "Home" },
      { key: "archive", path: "archive/", label: "Archivio" },
      { key: "stats", path: "stats/", label: "Stats" },
                  { key: "meta-profile", path: "meta-profile/", label: "Meta Profile" },
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
