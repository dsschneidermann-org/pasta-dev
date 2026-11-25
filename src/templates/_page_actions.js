// Posts the page's actions with fetch, so the page stays as it is and the in-place update that every
// change sends shows the result. The forms' own post, which loads the page again, is the fallback.
document.getElementById("page-actions").addEventListener("submit", async function (event) {
  window.scrollTo(0, 0);
  event.preventDefault();
  const form = event.target;
  const action = form.action;
  let accepted = false;
  // Without the socket no update would arrive to show the change.
  if (window.__ws_reloader_open) {
    try {
      // Following the redirect would render the page once more, for an answer nobody reads.
      const response = await fetch(action, {
        method: "POST",
        body: new URLSearchParams(new FormData(form)),
        redirect: "manual",
      });
      accepted = response.type === "opaqueredirect";
    } catch (error) {
      console.error("Posting the page action failed, posting the form instead.", error);
    }
  }
  if (!accepted) {
    // The post lands on the page or on the server's error. An update may have changed the form's action since.
    form.action = action;
    form.submit();
  }
});
