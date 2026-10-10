# 销售数据分析后端 接口文档（api.md）

> 依据已确认的 [spec.md](./spec.md) 编写。技术栈：Python + FastAPI + MySQL。本文档只定义接口，不含实现代码。

## 1. 概述

接口分两组：

- **销售数据管理**：CSV 上传、分类选项、商品分页列表、商品详情、销售明细。
- **数据统计分析**：销售概况、分类统计、热销排行、日 / 月销售趋势。

约定：

- 业务接口路径统一以 `/api` 开头；健康检查为 `/health`。
- 上传使用 `POST`，其余业务接口使用 `GET`。
- 金额字段一律返回**两位小数字符串**（如 `"12999.00"`）。

## 2. 通用约定

### 2.1 基础路径与请求方式

| 项 | 约定 |
|----|------|
| 业务路径前缀 | `/api` |
| 健康检查 | `/health`（不属业务路径） |
| 上传 | `POST`，`Content-Type: multipart/form-data` |
| 其他接口 | `GET`，查询参数置于 URL query |
| 字符编码 | UTF-8 |

### 2.2 分页规范（列表接口统一）

适用于「商品分页列表」「销售明细」。

| 参数 | 类型 | 必填 | 默认 | 校验 |
|------|------|------|------|------|
| page | int | 否 | 1 | ≥ 1，从 1 开始 |
| page_size | int | 否 | 10 | 1 ~ 100 |

统一返回结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 10
}
```

- `total`：筛选条件下的总记录数（不受分页影响）。
- 空结果：`items` 为空数组、`total` 为 0，**不算错误**（HTTP 200）。

### 2.3 日期规范

| 项 | 约定 |
|----|------|
| 格式 | `YYYY-MM-DD` |
| 参数名 | `start_date`、`end_date` |
| 区间 | **闭区间** `[start_date, end_date]`，含首尾日 |
| 必填 | 否（缺省规则见下） |
| 校验 | 格式非法 → 422；`start_date > end_date` → 422 |

**缺省（不传日期）规则**：

- 概况、分类统计、热销排行、销售明细：**不限日期**，统计 `sales` 全表。
- 商品详情：取**该商品自身销售跨度** `min(sale_date) ~ max(sale_date)`。
- 销售趋势：按**全量数据跨度**生成时间轴（日 → 全量最小日 ~ 最大日；月 → 全量最小月 ~ 最大月）。

### 2.4 金额与数值格式

| 字段类型 | 返回格式 | 示例 |
|----------|----------|------|
| 金额（price、sales_amount、amount） | 两位小数字符串 | `"5999.00"` |
| 销量、条数、商品数（volume / count） | 整数 | `123` |
| 日均销量 avg_daily_volume | 数值（保留两位小数） | `0.34` |

### 2.5 缺省值汇总

| 参数 | 默认值 |
|------|--------|
| page | 1 |
| page_size | 10 |
| start_date / end_date | 不传 = 按 §2.3 缺省规则 |
| sort_by（热销排行） | `volume` |
| limit（热销排行） | 10 |
| granularity（趋势） | `day` |
| group_by（趋势） | 不分组 |

### 2.6 错误响应与状态码

统一错误体（FastAPI 风格）：

```json
{ "detail": "错误说明" }
```

| 状态码 | 含义 | 触发场景 |
|--------|------|----------|
| 200 | 成功 | 正常返回 |
| 404 | 资源不存在 | 商品不存在（商品详情） |
| 422 | 输入非法 | 参数校验失败、日期格式/范围非法、上传文件非 CSV / 缺列 / 行值非法 / 超过 10MB |
| 503 | 服务不可用 | 数据库连接失败 |

## 3. 接口总览

| 方法 | 路径 | 功能 | 主要参数 |
|------|------|------|----------|
| GET | `/health` | 检查数据库连接 | 无 |
| POST | `/api/upload` | 上传 CSV 并事务追加 | csv_file（文件） |
| GET | `/api/categories` | 分类选项列表 | 无 |
| GET | `/api/products` | 商品分页列表 | page, page_size, category, name |
| GET | `/api/products/{product_id}` | 商品详情 | product_id, start_date, end_date |
| GET | `/api/sales` | 销售明细 | page, page_size, product_id, start_date, end_date |
| GET | `/api/stats/overview` | 销售概况 | start_date, end_date |
| GET | `/api/stats/categories` | 分类统计 | start_date, end_date |
| GET | `/api/stats/top-products` | 热销排行 | start_date, end_date, category, sort_by, limit |
| GET | `/api/stats/trend` | 日 / 月销售趋势 | start_date, end_date, granularity, group_by |

---

## 4. 接口详情

### 4.1 健康检查

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/health` |
| 功能 | 检查服务与数据库连接是否正常 |
| 参数 | 无 |

**成功响应 200**：

```json
{ "status": "ok", "database": "connected" }
```

**失败响应 503**：

```json
{ "detail": "数据库连接失败" }
```

---

### 4.2 CSV 上传

| 项 | 内容 |
|----|------|
| 方法 | POST |
| 路径 | `/api/upload` |
| 功能 | 上传 CSV，事务追加商品与销售数据；跳过重复销售、拒绝商品信息冲突、保留现有表和数据 |
| 表单字段 | `csv_file`（文件，必填） |

**参数**：

| 名称 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| csv_file | form-data | file | 是 | CSV 文件，UTF-8（允许 BOM），最大 10MB |

**校验与规则**：

- 文件层：仅接受 `.csv`；必需列 `product_id, product_name, category, price, quantity, sale_date` 齐全，缺列 → 422；自动处理 UTF-8 BOM。
- 行层：`product_id/product_name/category` 非空、`price` 为数值且 > 0、`quantity` 为正整数、`sale_date` 为合法日期，任一行不合法 → 422。
- 大小：超过 10MB → 422。
- 商品：不存在则新增；一致则复用；`name/category/price` 任一不一致 → 判定**冲突**并**拒绝**（不覆盖，保留库中现有信息）。
- 销售：以 `(product_id, quantity, sale_date)` 判重，库中已存在或文件内重复的**跳过**。
- 写入：整体以**事务**方式追加；不 DROP / TRUNCATE / ALTER，不删除现有数据。

**成功响应 200**：

```json
{
  "total_rows": 990,
  "inserted_products": 0,
  "inserted_sales": 1,
  "skipped_duplicates": 989,
  "rejected_conflicts": 0,
  "conflict_details": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| total_rows | int | 文件数据行总数 |
| inserted_products | int | 新增商品数 |
| inserted_sales | int | 新增销售记录数 |
| skipped_duplicates | int | 重复跳过的销售数 |
| rejected_conflicts | int | 因冲突被拒绝的商品数 |
| conflict_details | array | 冲突明细（product_id 及原因），无冲突时为空数组 |

**错误响应**：

- 422：非 CSV、缺列、行值非法、文件超 10MB。
- 503：数据库连接失败。

---

### 4.3 分类选项

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/categories` |
| 功能 | 返回 `products.category` 的去重分类列表及每类商品数，供筛选下拉与展示 |
| 参数 | 无 |

**成功响应 200**：

```json
{
  "categories": [
    { "category": "家具", "product_count": 5 },
    { "category": "家电", "product_count": 6 },
    { "category": "日用品", "product_count": 5 },
    { "category": "电子产品", "product_count": 9 },
    { "category": "运动用品", "product_count": 5 }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| category | string | 分类名 |
| product_count | int | 该分类的商品数（`products` 表内该分类商品总数） |

- 去重，按分类名升序。
- 无商品时返回空数组 `{"categories": []}`。

---

### 4.4 商品分页列表

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/products` |
| 功能 | 分页返回商品基础信息，支持分类、名称筛选 |

**参数**：

| 名称 | 类型 | 必填 | 默认 | 校验 / 说明 |
|------|------|------|------|-------------|
| page | int | 否 | 1 | ≥ 1 |
| page_size | int | 否 | 10 | 1 ~ 100 |
| category | string | 否 | 无 | 精确匹配分类 |
| name | string | 否 | 无 | 商品名称模糊包含 |

**成功响应 200**：

```json
{
  "items": [
    { "product_id": "P001", "product_name": "iPhone 14", "category": "电子产品", "price": "5999.00" }
  ],
  "total": 30,
  "page": 1,
  "page_size": 10
}
```

**错误响应**：422（分页参数非法）；503。

---

### 4.5 商品详情

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/products/{product_id}` |
| 功能 | 返回商品基础信息与统计指标（销量、销售额、交易次数、日均销量） |

**参数**：

| 名称 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| product_id | path | string | 是 | 无 | 商品编号 |
| start_date | query | string | 否 | 见 §2.3 | `YYYY-MM-DD` |
| end_date | query | string | 否 | 见 §2.3 | `YYYY-MM-DD` |

**成功响应 200**：

```json
{
  "product_id": "P001",
  "product_name": "iPhone 14",
  "category": "电子产品",
  "price": "5999.00",
  "start_date": "2024-10-09",
  "end_date": "2025-10-09",
  "sales_volume": 123,
  "sales_amount": "737877.00",
  "transaction_count": 45,
  "avg_daily_volume": 0.34
}
```

- **缺省日期**：`start_date`/`end_date` 回显为该商品自身销售跨度（`min ~ max`）。
- **日均销量** `avg_daily_volume` = 销量 ÷ 区间日历天数（含首尾日），保留两位小数。
- 范围内无销售：各指标返回 0（`sales_amount` 为 `"0.00"`），HTTP 200。

**错误响应**：

- 404：`{"detail": "商品不存在"}`。
- 422：日期格式 / 范围非法。
- 503：数据库连接失败。

---

### 4.6 销售明细

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/sales` |
| 功能 | 分页返回销售记录明细，支持商品 ID 与日期筛选 |

**参数**：

| 名称 | 类型 | 必填 | 默认 | 校验 / 说明 |
|------|------|------|------|-------------|
| page | int | 否 | 1 | ≥ 1 |
| page_size | int | 否 | 10 | 1 ~ 100 |
| product_id | string | 否 | 无 | 精确匹配 |
| start_date | string | 否 | 无 | `YYYY-MM-DD`，闭区间 |
| end_date | string | 否 | 无 | `YYYY-MM-DD`，闭区间 |

**成功响应 200**：

```json
{
  "items": [
    {
      "sale_id": 1,
      "product_id": "P001",
      "product_name": "iPhone 14",
      "quantity": 2,
      "sale_date": "2024-12-20",
      "amount": "11998.00"
    }
  ],
  "total": 990,
  "page": 1,
  "page_size": 10
}
```

- `amount` = `price × quantity`，两位小数字符串。

**错误响应**：422（分页 / 日期非法）；503。

---

### 4.7 销售概况

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/stats/overview` |
| 功能 | 返回范围内总体指标 |

**参数**：`start_date`、`end_date`（均可选，缺省不限日期）。

**成功响应 200**：

```json
{
  "start_date": "2024-10-09",
  "end_date": "2025-10-09",
  "sales_volume": 5432,
  "sales_amount": "12345678.00",
  "transaction_count": 990,
  "product_count": 30
}
```

| 字段 | 口径 |
|------|------|
| sales_volume | `SUM(quantity)` |
| sales_amount | `SUM(price × quantity)`，两位小数字符串 |
| transaction_count | 销售记录数 `COUNT(*)` |
| product_count | 发生销售的**去重商品数** `COUNT(DISTINCT product_id)` |

- 空结果：各指标为 0（`sales_amount` 为 `"0.00"`）；`start_date`/`end_date` 回显全量跨度。

**错误响应**：422；503。

---

### 4.8 分类统计

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/stats/categories` |
| 功能 | 按商品分类分组统计 |

**参数**：`start_date`、`end_date`（均可选）。

**成功响应 200**：

```json
{
  "items": [
    {
      "category": "电子产品",
      "sales_volume": 2000,
      "sales_amount": "8000000.00",
      "transaction_count": 300,
      "product_count": 10
    }
  ]
}
```

- `product_count` = 该分类发生销售的去重商品数。
- 无数据时 `items` 为空数组。

**错误响应**：422；503。

---

### 4.9 热销排行

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/stats/top-products` |
| 功能 | 按销量或销售额对商品排名 |

**参数**：

| 名称 | 类型 | 必填 | 默认 | 校验 / 说明 |
|------|------|------|------|-------------|
| start_date | string | 否 | 无 | `YYYY-MM-DD` |
| end_date | string | 否 | 无 | `YYYY-MM-DD` |
| category | string | 否 | 无 | 分类筛选（精确） |
| sort_by | string | 否 | `volume` | 取值 `volume` / `amount` |
| limit | int | 否 | 10 | ≥ 1，建议 ≤ 100 |

**成功响应 200**：

```json
{
  "items": [
    {
      "rank": 1,
      "product_id": "P002",
      "product_name": "MacBook Pro",
      "category": "电子产品",
      "sales_volume": 200,
      "sales_amount": "2599800.00",
      "transaction_count": 60
    }
  ]
}
```

- 默认按销量降序；`sort_by=amount` 时按销售额降序。
- 空结果：`items` 为空数组。

**错误响应**：422（`sort_by` / `limit` / 日期非法）；503。

---

### 4.10 日 / 月销售趋势

| 项 | 内容 |
|----|------|
| 方法 | GET |
| 路径 | `/api/stats/trend` |
| 功能 | 按日或按月返回销售趋势，支持按分类分组 |

**参数**：

| 名称 | 类型 | 必填 | 默认 | 校验 / 说明 |
|------|------|------|------|-------------|
| start_date | string | 否 | 无 | `YYYY-MM-DD`，缺省取全量跨度起点 |
| end_date | string | 否 | 无 | `YYYY-MM-DD`，缺省取全量跨度终点 |
| granularity | string | 否 | `day` | 取值 `day` / `month` |
| group_by | string | 否 | 无 | 传 `category` 按分类分组；不传返回整体单条序列 |

**成功响应 200（不分组）**：

```json
{
  "granularity": "day",
  "start_date": "2024-10-09",
  "end_date": "2024-10-12",
  "series": [
    {
      "key": "all",
      "points": [
        { "period": "2024-10-09", "sales_volume": 3, "sales_amount": "17997.00" },
        { "period": "2024-10-10", "sales_volume": 0, "sales_amount": "0.00" },
        { "period": "2024-10-11", "sales_volume": 5, "sales_amount": "29995.00" },
        { "period": "2024-10-12", "sales_volume": 2, "sales_amount": "11998.00" }
      ]
    }
  ]
}
```

**成功响应 200（`group_by=category`）**：

```json
{
  "granularity": "day",
  "start_date": "2024-10-09",
  "end_date": "2024-10-12",
  "series": [
    {
      "key": "电子产品",
      "points": [
        { "period": "2024-10-09", "sales_volume": 1, "sales_amount": "5999.00" },
        { "period": "2024-10-10", "sales_volume": 0, "sales_amount": "0.00" },
        { "period": "2024-10-11", "sales_volume": 2, "sales_amount": "11998.00" },
        { "period": "2024-10-12", "sales_volume": 0, "sales_amount": "0.00" }
      ]
    },
    {
      "key": "运动用品",
      "points": [
        { "period": "2024-10-09", "sales_volume": 2, "sales_amount": "11998.00" },
        { "period": "2024-10-10", "sales_volume": 0, "sales_amount": "0.00" },
        { "period": "2024-10-11", "sales_volume": 3, "sales_amount": "17997.00" },
        { "period": "2024-10-12", "sales_volume": 2, "sales_amount": "11998.00" }
      ]
    }
  ]
}
```

**规则**：

- `period` 格式：`granularity=day` 为 `YYYY-MM-DD`；`granularity=month` 为 `YYYY-MM`。
- **补零**：按闭区间生成完整时间轴，无数据的时间点补 0。
- **分组对齐**：`group_by=category` 时，所有分类使用**完全相同的时间轴**（点位数量一致），曲线周期一致。
- 空结果：返回完整时间轴、数值全为 0 的序列。

**错误响应**：422（`granularity` / 日期非法）；503。

---

## 5. 状态码汇总

| 状态码 | 含义 | 出现接口 |
|--------|------|----------|
| 200 | 成功 | 全部 |
| 404 | 商品不存在 | `/api/products/{product_id}` |
| 422 | 输入非法（参数 / 日期 / 上传文件） | 全部（除 `/health` 成功场景） |
| 503 | 数据库连接失败 | 全部 |

## 6. 说明与待确认

- 本文档已落实 spec.md §9 的 3 项待定：分页默认 `page=1`、`page_size=10`（上限 100）；分类选项返回「分类名 + 每类商品数」；趋势每条 `point` 同时含 `sales_volume` 与 `sales_amount`。
- 上传响应在四项必需字段（`total_rows`、`inserted_products`、`inserted_sales`、`skipped_duplicates`）之外，按 spec.md §4.1.1 补充了 `rejected_conflicts`、`conflict_details`，用于反馈被拒绝的冲突商品。
- 分页上限、`limit` 上限等数值如需调整，请告知。
