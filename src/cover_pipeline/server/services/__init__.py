"""服务层：app.py 只做 HTTP 适配，业务逻辑都在这几个模块里。

约定：每个模块对外导出一组 `func(state, ...) -> dict`，返回值就是接口的响应体
（状态码、鉴权、查询参数解析留在 app.py）。这样接口形状只在一个地方定义。
"""

from __future__ import annotations
