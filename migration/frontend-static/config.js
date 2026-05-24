(function () {
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

  // Local default points to FastAPI on your machine.
  // For production GitHub Pages, replace apiBaseUrl with your deployed API domain.
  window.APP_CONFIG = {
    apiBaseUrl: isLocal ? "http://127.0.0.1:8000" : "https://your-api-domain.com",
  };
})();
