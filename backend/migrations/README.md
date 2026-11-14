# migrations

运行时不执行 SQL 迁移：`backend/src/config/app.py` 在启动时调用 `Base.metadata.create_all`，
表结构与 `src/models/*.py` 保持一致。`001_core_tables.sql` 只是给人看的参考 DDL
（字段、约束、外键、唯一键），改模型时请同步更新，便于 DBA 评审。
