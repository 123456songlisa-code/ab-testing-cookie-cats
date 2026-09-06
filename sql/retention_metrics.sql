-- ============================================================================
-- SQL 分析模块：用 SQL 复刻核心指标计算
-- ============================================================================
-- 为什么要这个模块：
--   数据分析师的日常工作以 Hive SQL / Spark SQL 为主，本模块用于展示 SQL 能力。
--   本文件用 DuckDB 语法编写（可直接对 CSV 查询，便于复现），
--   用到的函数在 Hive 中基本一一对应，对应关系见各行注释。
--
-- 运行方式：python src/run_sql.py（自动逐条执行并保存结果）
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 查询 1：分组样本量与占比 —— 用 SQL 手工复核 SRM
-- 分流平台承诺 50/50，看实际占比偏了多少
-- ----------------------------------------------------------------------------
SELECT
    version,
    COUNT(*)              AS user_cnt,                       -- Hive: COUNT(*) 通用
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct  -- OVER() 全局窗口，Hive 同
FROM read_csv_auto('data/cookie_cats.csv')                   -- Hive: FROM ods.cookie_cats
GROUP BY version
ORDER BY version;

-- ----------------------------------------------------------------------------
-- 查询 2：分组核心指标 —— 1 日留存、7 日留存、游戏轮数
-- 布尔列在 DuckDB 可直接 SUM()（TRUE 计 1）；Hive 中写 SUM(CASE WHEN retention_7 THEN 1 ELSE 0 END)
-- ----------------------------------------------------------------------------
SELECT
    version,
    COUNT(*)                                            AS user_cnt,
    ROUND(AVG(CASE WHEN retention_1 THEN 1 ELSE 0 END) * 100, 2) AS retention_1_pct,  -- Hive 通用写法
    ROUND(AVG(CASE WHEN retention_7 THEN 1 ELSE 0 END) * 100, 2) AS retention_7_pct,
    quantile_cont(sum_gamerounds, 0.5)                  AS rounds_median,   -- Hive: percentile_approx(sum_gamerounds, 0.5)
    quantile_cont(sum_gamerounds, 0.99)                 AS rounds_p99       -- Hive: percentile_approx(sum_gamerounds, 0.99)
FROM read_csv_auto('data/cookie_cats.csv')
GROUP BY version
ORDER BY version;

-- ----------------------------------------------------------------------------
-- 查询 3：按活跃度分层的 7 日留存 —— 定位"负效应来自哪个人群"
-- 分层口径与 src/03_hypothesis_testing.py 保持一致
-- ----------------------------------------------------------------------------
SELECT
    CASE
        WHEN sum_gamerounds <= 0   THEN '0轮(未上手)'
        WHEN sum_gamerounds <= 10  THEN '1-10轮'
        WHEN sum_gamerounds <= 50  THEN '11-50轮'
        WHEN sum_gamerounds <= 150 THEN '51-150轮'
        ELSE '150轮+'
    END                                                 AS segment,
    version,
    COUNT(*)                                            AS user_cnt,
    ROUND(AVG(CASE WHEN retention_7 THEN 1 ELSE 0 END) * 100, 2) AS retention_7_pct
FROM read_csv_auto('data/cookie_cats.csv')
GROUP BY 1, 2                                            -- Hive 支持 GROUP BY 别名/序号
ORDER BY segment, version;

-- ----------------------------------------------------------------------------
-- 查询 4：组间差的绝对值与相对提升 —— 结论表（贴进报告的最后一行）
-- ----------------------------------------------------------------------------
WITH agg AS (
    SELECT
        version,
        AVG(CASE WHEN retention_7 THEN 1 ELSE 0 END) AS r7,
        COUNT(*)                                     AS n
    FROM read_csv_auto('data/cookie_cats.csv')
    GROUP BY version
)
SELECT
    ROUND((t.r7 - c.r7) * 100, 2)                       AS abs_diff_pp,
    ROUND((t.r7 / c.r7 - 1) * 100, 2)                   AS rel_lift_pct
FROM agg c
JOIN agg t ON t.version = 'gate_40'
WHERE c.version = 'gate_30';
