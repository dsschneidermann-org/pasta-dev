function main() {
  var reloading = false

  function connect() {
    const socket = new WebSocket("/ws/reloader");

    socket.onmessage = function(event) {
      const data = JSON.parse(event.data);
      switch(data.refresh) {
        case 1:
          // 1000 = "Normal closure" and the second parameter is a human-readable reason.
          socket.close(1000, "Reloading page after receiving refresh");
          reloading = true;
          location.reload(true);
          break;
        case 0:
          break;
        default:
          console.error(`Reloader not handling data: '${data}'`);
          break;
      }
    }

    socket.onclose = function(e) {
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
