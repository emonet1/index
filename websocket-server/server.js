const http = require("http");
const WebSocket = require("ws");

const server = http.createServer((req, res) => {
  res.writeHead(200);
  res.end("WebSocket OK");
});

const wss = new WebSocket.Server({ server });

wss.on('connection', (ws, req) => {
  console.log('Client connected');
  ws.on('error', console.error);
});

server.listen(8080, "0.0.0.0", () => {
  console.log("Server is steady on 8080");
});