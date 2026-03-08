try {
    const data = getData(); // 假设这是获取数据的函数
    if (data && Array.isArray(data)) {
        const result = data.map(item => item.test);
        console.log(result);
    } else {
        console.error('Data is not an array or undefined');
    }
} catch (error) {
    console.error('An error occurred:', error.message);
}