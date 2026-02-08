const express = require('express');
const axios = require('axios');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());

// 这里的 Key 放在服务器端，安全！
const API_KEY = 'sk-86c77a39ce87413f8502d80e02408779'; 
const ALIYUN_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation';

app.post('/api/chat', async (req, res) => {
    try {
        const response = await axios.post(ALIYUN_URL, req.body, {
            headers: {
                'Authorization': `Bearer ${API_KEY}`,
                'Content-Type': 'application/json'
            }
        });
        res.json(response.data);
    } catch (error) {
        console.error('调用阿里API失败:', error.message);
        res.status(500).send('AI 服务暂时不可用');
    }
});

const PORT = 3001;
app.listen(PORT, () => {
    console.log(`AI 代理服务运行在 http://localhost:${PORT}`);
});
