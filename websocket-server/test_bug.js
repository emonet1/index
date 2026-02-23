// Fixed JavaScript code
// No syntax errors remain
const WebSocket = require('ws');

function connectWebSocket(url) {
  try {
    const socket = new WebSocket(url);
    socket.on('open', () => {
      console.log('WebSocket connection established');
    });
    socket.on('error', (error) => {
      console.error('WebSocket connection failed:', error.message);
    });
    return socket;
  } catch (error) {
    console.error('WebSocket connection failed:', error.message);
    throw error;
  }
}

// Example usage (uncomment to test):
// const ws = connectWebSocket('ws://localhost:8080');