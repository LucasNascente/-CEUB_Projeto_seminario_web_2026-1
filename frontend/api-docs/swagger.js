"use strict";

SwaggerUIBundle({
  url: "./openapi.json",
  dom_id: "#swagger-ui",
  validatorUrl: null,
  persistAuthorization: false,
  withCredentials: true,
  requestInterceptor(request) {
    if (["POST", "PATCH"].includes(request.method?.toUpperCase())) {
      request.headers["X-HelpDesk-Request"] = "1";
    }
    return request;
  },
});
