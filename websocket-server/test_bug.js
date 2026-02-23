// Fixed JavaScript code
// No syntax errors remain
const WebSocket = require('ws');

function connectWebSocket(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    
    socket.on('open', () => {
      resolve(socket);
    });
    
    socket.on('error', (err) => {
      reject(new Error(`WebSocket connection failed: ${err.message}`));
    });
    
    socket.on('close', (code, reason) => {
      reject(new Error(`WebSocket connection closed: ${code} ${reason}`));
    });
  });
}

// Export for testing
module.exports = { connectWebSocket };