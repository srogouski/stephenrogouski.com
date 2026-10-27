// Visitor counter: calls the backend API, which increments and returns the count.
// The API URL is injected via window.API_URL in index.html after the backend is deployed.
(function () {
  "use strict";

  var el = document.getElementById("visitor-count");
  if (!el) {
    return;
  }

  var apiUrl = window.API_URL;
  if (!apiUrl) {
    // Backend not wired up yet — fail gracefully.
    el.textContent = "—";
    console.warn("window.API_URL is not set; visitor counter disabled.");
    return;
  }

  fetch(apiUrl, { method: "GET" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Request failed with status " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      var count = data && (data.count !== undefined ? data.count : data.views);
      el.textContent =
        typeof count === "number" ? count.toLocaleString() : "—";
    })
    .catch(function (err) {
      console.error("Failed to load visitor count:", err);
      el.textContent = "—";
    });
})();
