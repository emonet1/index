// 这是一个故意的语法错误测试
routerAdd("GET", "/test", (c) => {
    // ❌ 故意漏掉右括号
    return c.json(200, {message: "test"});
});