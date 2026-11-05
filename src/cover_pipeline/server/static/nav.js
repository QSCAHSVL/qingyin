/* 导航回调：router 注册实现，各页面只调用 go()——避免 router 与 pages 互相 import 成环 */
let navigate = (page) => { console.warn("[nav] 路由还没注册，忽略了 go(", page, ")"); };

export function setNavigator(fn) { navigate = fn; }

export function go(page) { return navigate(page); }
