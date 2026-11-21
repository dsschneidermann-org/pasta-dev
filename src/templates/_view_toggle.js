// Flip the page view between its rendered Markdown and the page-type's Sphinx doc.
// "Model" overlays an iframe (loaded lazily on first open) on top of the rendered body;
// "Page" hides it again. Only page.html (via _nav.html) carries these elements.
function initViewToggle() {
  const pageButton = document.getElementById("show-page");
  const modelButton = document.getElementById("show-model");
  const viewBody = document.getElementById("view-body");
  const modelView = document.getElementById("model-view");
  if (!pageButton || !modelButton || !viewBody || !modelView) {
    return;
  }

  const showModel = function () {
    // Load the page-type doc on open whenever it is not the one data-src names: the first open, or
    // after the page's status changed in place.
    if (modelView.getAttribute("src") !== modelView.dataset.src) {
      modelView.src = modelView.dataset.src;
    }
    viewBody.classList.add("model-active");
    modelView.hidden = false;
    modelButton.setAttribute("aria-pressed", "true");
    pageButton.setAttribute("aria-pressed", "false");
  };

  const showPage = function () {
    viewBody.classList.remove("model-active");
    modelView.hidden = true;
    pageButton.setAttribute("aria-pressed", "true");
    modelButton.setAttribute("aria-pressed", "false");
  };

  modelButton.addEventListener("click", showModel);
  pageButton.addEventListener("click", showPage);
}

document.addEventListener("DOMContentLoaded", function (event) {
  if (!window.__view_toggle_loaded) {
    window.__view_toggle_loaded = true;
    initViewToggle();
  }
});
