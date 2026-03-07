// 这是一个故意的语法错误测试
routerAdd("GET", "/test", (c) => {
    // 修复了右括号缺失的问题
    return c.json(200, {message: "test"});
});