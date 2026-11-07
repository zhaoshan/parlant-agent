"""B 类包：SDK 官方扩展点 / 装配（不修订 SDK 内部，随 SDK 公共 API 演进）。

与 app/patches（A 类，monkey-patch SDK 内部）相对：本包只使用 SDK 设计好的挂载
机制（configure_hooks、FastAPI instrumentor、env 配置），升级风险低一档。
"""
