# -*- coding: utf-8 -*-
"""
SQL 模块运行器：逐条执行 sql/retention_metrics.sql 里的 4 个查询。
数据量只有 9 万行，DuckDB 直接对 CSV 即席查询即可，无需建表/起服务。
真实生产环境等价于：Hive 上跑同样的 SQL（语法对照见 SQL 文件内注释）。

运行方式：python src/run_sql.py
输出：控制台表格 + results/sql_q1~q4.csv
"""
import os
import re

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_PATH = os.path.join(ROOT, "sql", "retention_metrics.sql")
OUT_DIR = os.path.join(ROOT, "results")
os.makedirs(OUT_DIR, exist_ok=True)

os.chdir(ROOT)  # SQL 里的相对路径 'data/...' 以仓库根为基准

with open(SQL_PATH, encoding="utf-8") as f:
    raw = f.read()

# 按 ';' 切分，去掉纯注释块，得到可执行语句
statements = [s.strip() for s in raw.split(";")]
statements = [s for s in statements if s and re.sub(r"--[^\n]*", "", s).strip()]

for i, stmt in enumerate(statements, 1):
    res = duckdb.sql(stmt)
    tbl = res.df()
    print(f"\n===== 查询 {i} =====")
    print(tbl.to_string(index=False))
    tbl.to_csv(os.path.join(OUT_DIR, f"sql_q{i}.csv"), index=False, encoding="utf-8-sig")

print(f"\n已保存：results/sql_q1~q{len(statements)}.csv")
