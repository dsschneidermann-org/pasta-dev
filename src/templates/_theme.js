function main() {
  const themeForm = document.getElementById("theme-form");
  const stylesheet = document.getElementById("js-stylesheet");
  const startupStylesheet = document.getElementById("js-startup-stylesheet");

  const updateTheme = function() {
    const theme = themeForm.querySelector(`input[name="theme"]:checked`).value || "light";

    const localUrl = `/static/water.css/${theme}.min.css`;

    stylesheet.href = localUrl;

    localStorage.setItem("theme", theme);

    // Update specific elements.
    body.classList.remove("light");
    body.classList.remove("dark");
    body.classList.add(theme);
  }

  themeForm.addEventListener("change", updateTheme);

  const body = document.getElementsByTagName("body")[0];
  const stored = localStorage.getItem("theme");
  if (stored === "dark") {
    document.getElementById("theme-light").checked = false;
    document.getElementById("theme-dark").checked = true;
  } else {
    document.getElementById("theme-light").checked = true;
    document.getElementById("theme-dark").checked = false;
  }
  updateTheme();

  startupStylesheet.parentElement.removeChild(startupStylesheet);
  body.style = null;
}

if (!window.__theme_loaded) {
  window.__theme_loaded = true;
  main();
}
