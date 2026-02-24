/* Single source of truth for navigation + home actions.
 *
 * Edit the order/labels/paths here and both the navbar (all pages)
 * and the Home buttons will automatically stay consistent.
 */
(function () {
  window.NAV_ITEMS = [
    { key: "home", path: "", label: "Home" },
    { key: "archive", path: "archive/", label: "Archivio" },
    { key: "stats", path: "stats/", label: "Stats" },
    { key: "meta-profile", path: "meta-profile/", label: "Meta Profile" },
    { key: "bracket-calibration", path: "bracket-calibration/", label: "Calibrazione" },
    { key: "draft", path: "draft/", label: "Draft" },
    { key: "new-game", path: "new-game/", label: "Nuova partita" }
  ];
})();
