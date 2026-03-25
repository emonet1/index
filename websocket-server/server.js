const http = require('http');
const WebSocket = require('ws');

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('HTTP server for WebSocket is running\n');
});

const wss = new WebSocket.Server({ server });

wss.on('connection', ws => {
  console.log('Client connected to server.js');
  ws.on('message', message => {
    console.log('Received: %s', message);
    ws.send(`Echo: ${message}`);
  });
  ws.on('close', () => {
    console.log('Client disconnected');
  });
  ws.on('error', error => {
    console.error('WebSocket error:', error);
  });
});

// FIX: Changed invalid hostname "*.*.*.*" to "0.0.0.0" to listen on all network interfaces.
server.listen(8080, "0.0.0.0", () => {
  console.log("Server is steady on 8080");
});