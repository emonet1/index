const http = require("http");
const WebSocket = require("ws");

const server = http.createServer((req, res) => {
  res.writeHead(200);
  res.end("WebSocket OK");
});

const wss = new WebSocket.Server({ server });

wss.on('connection', (ws, req) => {
  console.log('WebSocket client connected');
  ws.on('error', (err) => {
    console.error('WebSocket error:', err);
  });
});

server.listen(8080, "0.0.0.0", () => {
  console.log("Server is ready on 8080");
});