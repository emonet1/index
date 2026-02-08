routerAdd("GET", "/fail", (c) => {
    throw new Error("Manual Test Error\nSecond Error Test");
});