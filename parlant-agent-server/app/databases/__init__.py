"""databases 包：**连接管理**层——只负责"连上哪个库"，不包含任何业务数据操作。

职责边界：
- `MongoConnection`：MongoDB 连接（motor）；产出 `.database` 句柄。
- `MySqlConnection`：MySQL 连接（SQLAlchemy async + aiomysql）；产出 engine / session 工厂。
- 业务表/集合的读写一律在 `app/repository/`（仓储层）通过注入的连接句柄完成。

未来加 MySQL（用户/登录/权限）或其它数据源，只需在此新增一个连接提供者。
"""

from app.databases.mongo import MongoConnection
from app.databases.mysql import MySqlConnection

__all__ = ["MongoConnection", "MySqlConnection"]