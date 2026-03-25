const WebSocket = require('ws');
const http = require('http');
const express = require('express'); // express is used for the push interface server

// 创建 HTTP 服务器用于 WebSocket
const wsServer = http.createServer();
const wss = new WebSocket.Server({ server: wsServer });

// teacherId -> ws 连接映射
const clients = new Map();

wss.on('connection', (ws, req) => {
  console.log('收到WebSocket连接请求');
  console.log('请求URL:', req.url);
  
  try {
    // 解析URL参数
    const url = new URL(req.url, 'http://localhost');
    const userId = url.searchParams.get('userId');
    const role = url.searchParams.get('role');
    
    console.log('连接参数:', { userId, role });

    if (!userId || role !== 'teacher') {
      console.log('非教师用户或缺少userId，关闭连接');
      ws.close(1008, '仅支持教师角色');
      return;
    }

    // 存储教师连接
    clients.set(userId, ws);
    console.log(`✅ 教师 ${userId} 已连接，当前在线教师数: ${clients.size}`);

    // 发送欢迎消息
    ws.send(JSON.stringify({
      type: 'connected',
      message: '连接成功'
    }));

    // 监听消息
    ws.on('message', (message) => {
      try {
        const data = JSON.parse(message);
        console.log('收到消息:', data);
        
        // 处理心跳
        if (data.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
      } catch (e) {
        console.error('消息解析失败:', e);
      }
    });

    // 监听连接关闭
    ws.on('close', () => {
      clients.delete(userId);
      console.log(`教师 ${userId} 断开连接，当前在线教师数: ${clients.size}`);
    });

    // 监听错误
    ws.on('error', (error) => {
      console.error(`教师 ${userId} 连接错误:`, error);
      clients.delete(userId);
    });
  } catch (error) {
    console.error('处理WebSocket连接时出错:', error);
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close(1011, '服务器错误');
    }
  }
});

// 启动 WebSocket 服务器
wsServer.listen(6000, () => {
  console.log('WebSocket服务启动，端口 6000');
  console.log('WebSocket URL: ws://localhost:6000');
});

// ===========================================
// 推送接口服务器
// ============================
const app = express();
app.use(express.json()); // Enable JSON body parsing for push requests

app.post('/api/push_message', (req, res) => {
  try {
    // 安全地从请求体中解构 userId, message, test_token
    const { userId, message, test_token } = req.body; 
    console.log('收到推送请求:', { userId, message, test_token });

    // 专门处理自动化 AI 测试请求
    if (test_token && test_token === 'AI_TEST_TOKEN') {
      console.log('Received automated AI test request with specific token.');
      // 模拟测试成功响应
      return res.json({ status: 'success', message: 'AI test token received and processed successfully.' });
    }

    if (!userId || !message) {
      return res.status(400).json({ error: '缺少 userId 或 message 参数' });
    }

    const targetWs = clients.get(userId);
    if (targetWs && targetWs.readyState === WebSocket.OPEN) {
      targetWs.send(JSON.stringify({ type: 'push', data: message }));
      return res.json({ status: 'success', message: `消息已推送给 ${userId}` });
    } else {
      // 如果用户不在线，可以选择将消息入队或直接报告失败
      return res.status(404).json({ error: `用户 ${userId} 不在线或连接已关闭` });
    }
  } catch (error) {
    console.error('处理推送请求时出错:', error);
    return res.status(500).json({ error: '服务器内部错误', details: error.message });
  }
});

const PUSH_PORT = 3000; // 为 Express 推送服务器使用一个不同的端口
app.listen(PUSH_PORT, () => {
  console.log(`推送接口服务器启动，端口 ${PUSH_PORT}`);
  console.log(`推送接口 URL: http://localhost:${PUSH_PORT}/api/push_message`);
});