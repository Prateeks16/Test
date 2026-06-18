// API base for the OTP Extractor frontend.
//
// Leave "" when the backend (Render) serves this page directly — calls stay same-origin.
// When hosting this static UI separately (e.g. Vercel), set apiBase to your Render URL:
//   window.OTP_CONFIG = { apiBase: "https://otp-extractor-api.onrender.com" };
window.OTP_CONFIG = { apiBase: "" };
