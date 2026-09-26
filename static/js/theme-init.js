/* Applies the saved theme before first paint (loaded synchronously in <head>). */
(function () {
  var root = document.documentElement;
  var theme = null;
  try { theme = localStorage.getItem("ourlove-theme"); } catch (e) { /* storage unavailable */ }
  if (theme !== "light" && theme !== "dark") theme = root.getAttribute("data-default-theme") || "dark";
  root.setAttribute("data-theme", theme);
  root.classList.remove("no-js");
})();
