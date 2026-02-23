const WebSocket = require('ws');
const http = require('http');
const express = require('express');

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
    ws.close(1011, '服务器错误');
  }
});

// 启动 WebSocket 服务器
wsServer.listen(6000, '0.0.0.0', () => {
  console.log('WebSocket服务启动，端口 6000');
  console.log('WebSocket URL: ws://localhost:6000');
});

// ===========================================
// 推送接口服务器
// ===========================================
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// 推送消息到指定教师
app.post('/push', (req, res) => {
  console.log('收到推送请求:', req.body);
  
  const { teacherId, message } = req.body;
  
  if (!teacherId || !message) {
    return res.status(400).json({ 
      success: false, 
      error: '缺少必要参数 teacherId 或 message' 
    });
  }

  const socket = clients.get(teacherId);

  if (socket && socket.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify(message));
      console.log(`✅ 消息已推送给教师 ${teacherId}`);
      return res.json({ success: true, message: '推送成功' });
    } catch (e) {
      console.error(`推送失败:`, e);
      return res.status(500).json({ success: false, error: '推送失败' });
    }
  }
  
  console.log(`❌ 教师 ${teacherId} 未在线`);
  res.json({ success: false, error: '教师未在线' });
});

// 健康检查接口
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    onlineTeachers: clients.size,
    timestamp: new Date().toISOString()
  });
});

// 获取在线教师列表
app.get('/online-teachers', (req, res) => {
  const teacherIds = Array.from(clients.keys());
  res.json({ 
    count: teacherIds.length,
    teachers: teacherIds 
  });
});

// 启动推送接口服务器
app.listen(6001, '0.0.0.0', () => {
  console.log('推送接口启动，端口 6001');
  console.log('推送接口URL: http://localhost:6001/push');
});

// 优雅关闭
process.on('SIGTERM', () => {
  console.log('收到SIGTERM信号，正在关闭服务器...');
  wsServer.close(() => {
    console.log('WebSocket服务器已关闭');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('收到SIGINT信号，正在关闭服务器...');
  wsServer.close(() => {
    console.log('WebSocket服务器已关闭');
    process.exit(0);
  });
});