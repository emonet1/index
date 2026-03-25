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

// 修复：将无效的 IP 地址字符串 "*.*.*.*" 更改为 "0.0.0.0"，以便监听所有网络接口。
server.listen(8080, "0.0.0.0", () => {
  console.log("Server is steady on 8080");
});