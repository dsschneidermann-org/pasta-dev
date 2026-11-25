function main() {
  var reloading = false
  var updating = false;   // a fetch-and-morph is running
  var stale = false;      // an update arrived while it ran

  // A page script owns the attributes an element lists in data-morph-keep, so the morph leaves them.
  function keepsAttribute(element, name) {
    return (element.getAttribute("data-morph-keep") || "").split(" ").includes(name);
  }

  function reloadPage() {
    reloading = true;
    location.reload(true);
  }

  // One fetch in flight: updates arriving meanwhile collapse into one more fetch after it.
  async function update() {
    if (updating) {
      stale = true;
      return;
    }
    updating = true;
    try {
      do {
        stale = false;
        const response = await fetch(location.href, {cache: "no-store"});
        if (reloading) return;
        if (!response.ok || response.redirected) {
          reloadPage();
          return;
        }
        const fetched = new DOMParser().parseFromString(await response.text(), "text/html");
        if (reloading) return;
        // innerHTML leaves the body element's own attributes and the head to the page's scripts.
        Idiomorph.morph(document.body, fetched.body.childNodes, {
          morphStyle: "innerHTML",
          callbacks: {
            beforeAttributeUpdated: (name, element) => !keepsAttribute(element, name),
            // A page script owns everything inside an element marked data-morph-skip.
            beforeNodeMorphed: (oldNode) => !(oldNode instanceof Element && oldNode.hasAttribute("data-morph-skip")),
          },
        });
      } while (stale);
    } catch (error) {
      console.error("In-place update failed, reloading the page instead.", error);
      reloadPage();
    } finally {
      updating = false;
    }
  }

  function connect() {
    const socket = new WebSocket("/ws/reloader");

    socket.onmessage = function(event) {
      const data = JSON.parse(event.data);
      if (data.reload === 1) {
        // 1000 = "Normal closure" and the second parameter is a human-readable reason.
        socket.close(1000, "Reloading page after receiving refresh");
        reloadPage();
      } else if (data.update === 1) {
        update();
      } else if (data.heartbeat !== 1) {
        console.error(`Reloader not handling data: '${event.data}'`);
      }
    }

    socket.onopen = function() {
      window.__ws_reloader_open = true;
    };

    socket.onclose = function(e) {
      window.__ws_reloader_open = false;
      console.log("Socket is closed. Reconnect will be attempted in 1 second.", e.reason);
      setTimeout(function() {
        connect();
      }, 1000);
    };

    socket.onerror = function(err) {
      socket.close();
    };
  };

  document.addEventListener("DOMContentLoaded", function (event) {
    const scrollpos = sessionStorage.getItem("scrollpos");
    if (scrollpos) {
      window.scrollTo(0, scrollpos);
      sessionStorage.removeItem("scrollpos");
    }
  });

  document.addEventListener("visibilitychange", function() {
     if (document.hidden) {
         console.log("Browser tab is hidden");
     } else {
         console.log("Browser tab is visible");
         // This works but forces a reload when the server is offline, causing
         // the opposite effect to happen, the page is reloaded into nothing.
         // reloading = true;
         // location.reload();

         // The right way to solve browser tab deactivation and activation:
         // keep a timestamp counter as of the last server start / mutation action
         // on the server and return it for every websocket: {refresh: timestamp}
         // If timestamp is newer than the current javascript state, reload.
         // Upon first load, read the newest timestamp from the html source, a
         // data attribute or a head tag.
     }
  });

  window.addEventListener("beforeunload", function (e) {
    if(reloading) {
      sessionStorage.setItem("scrollpos", window.scrollY);
    }
  });

  connect();
}

if (!window.__ws_reloader_loaded) {
  window.__ws_reloader_loaded = true;
  main();
}
