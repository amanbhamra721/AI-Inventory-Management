(function () {
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

  // Local points to FastAPI on your machine.
  // Production must be HTTPS to avoid browser mixed-content blocking.
  window.APP_CONFIG = {
    apiBaseUrl: isLocal ? "http://127.0.0.1:8000" : "https://api.thekoshak.com",
  };
})();
