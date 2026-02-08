const http = require("http");
http.createServer((req, res) => {
  res.writeHead(200);
  res.end("WebSocket OK");
}).listen(8080, "0.0.0.0");
console.log("Server is steady on 8080");
