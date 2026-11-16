-- =====================================================================
-- ZOMATO BI PROJECT - DAY 5: ADVANCED QUERIES (MySQL 8)
-- Window functions, date handling, views and an index.
-- Continues from 04_business_queries_mysql.sql (Q1-Q15), so numbering
-- starts at Q16. Together the two files hold 28 queries.
-- HOW TO RUN: click inside ONE query, then press Ctrl + Shift + Enter.
-- Revenue counts orders with status 'Delivered' or 'Delivered Late'.
-- "Today" in the data = the last order date (2024-12-31), not the real date.
-- =====================================================================

USE zomato_bi;

-- #####################################################################
-- PART 1: WINDOW FUNCTIONS
-- A window function looks at other rows without collapsing them into one
-- (unlike GROUP BY). PARTITION BY = "restart for each group".
-- #####################################################################

-- ---------------------------------------------------------------------
-- Q16. ROW_NUMBER vs RANK vs DENSE_RANK: Mumbai restaurants ranked by rating
-- Ratings tie often. Look at what each function does with the ties:
--   ROW_NUMBER = always 1,2,3...   RANK = ties share a number, then skips
--   DENSE_RANK = ties share a number, no skipping
-- ---------------------------------------------------------------------
SELECT RestaurantID, RestaurantName, City, Rating, row_num, rank_num, dense_rank_num
FROM (
    SELECT RestaurantID, RestaurantName, City, Rating,
           ROW_NUMBER() OVER (PARTITION BY City ORDER BY Rating DESC, RestaurantID) AS row_num,
           RANK()       OVER (PARTITION BY City ORDER BY Rating DESC)               AS rank_num,
           DENSE_RANK() OVER (PARTITION BY City ORDER BY Rating DESC)               AS dense_rank_num
    FROM restaurants
    WHERE Rating IS NOT NULL
) ranked
WHERE City = 'Mumbai'
ORDER BY row_num
LIMIT 15;

-- ---------------------------------------------------------------------
-- Q17. CTE + RANK: top 3 restaurants by revenue in every city
-- ---------------------------------------------------------------------
WITH city_ranks AS (
    SELECT r.RestaurantID, r.RestaurantName, r.City,
           ROUND(SUM(o.FinalAmount), 2) AS total_revenue,
           RANK() OVER (PARTITION BY r.City ORDER BY SUM(o.FinalAmount) DESC) AS city_rank
    FROM restaurants r
    JOIN orders o ON o.RestaurantID = r.RestaurantID
    WHERE o.OrderStatus IN ('Delivered', 'Delivered Late')
    GROUP BY r.RestaurantID, r.RestaurantName, r.City
)
SELECT City, city_rank, RestaurantID, RestaurantName, total_revenue
FROM city_ranks
WHERE city_rank <= 3
ORDER BY City, city_rank, RestaurantID;

-- ---------------------------------------------------------------------
-- Q18. LAG and LEAD: each order next to the customer's previous and next order
-- ---------------------------------------------------------------------
SELECT CustomerID, OrderID, OrderDate, FinalAmount,
       LAG(FinalAmount)  OVER (PARTITION BY CustomerID ORDER BY OrderDate, OrderID) AS previous_order_amount,
       LEAD(FinalAmount) OVER (PARTITION BY CustomerID ORDER BY OrderDate, OrderID) AS next_order_amount,
       ROUND(FinalAmount - LAG(FinalAmount) OVER (PARTITION BY CustomerID ORDER BY OrderDate, OrderID), 2) AS change_vs_previous
FROM orders
WHERE OrderStatus IN ('Delivered', 'Delivered Late')
ORDER BY CustomerID, OrderDate, OrderID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q19. CTE + LAG: Mumbai month-over-month revenue change
-- ---------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT DATE_FORMAT(o.OrderDate, '%Y-%m') AS order_month,
           ROUND(SUM(o.FinalAmount), 2)      AS revenue
    FROM orders o
    JOIN restaurants r ON r.RestaurantID = o.RestaurantID
    WHERE r.City = 'Mumbai'
      AND o.OrderStatus IN ('Delivered', 'Delivered Late')
    GROUP BY DATE_FORMAT(o.OrderDate, '%Y-%m')
)
SELECT order_month, revenue,
       LAG(revenue) OVER (ORDER BY order_month) AS prev_month_revenue,
       ROUND(100 * (revenue - LAG(revenue) OVER (ORDER BY order_month))
                 / LAG(revenue) OVER (ORDER BY order_month), 1) AS change_pct
FROM monthly_revenue
ORDER BY order_month;

-- ---------------------------------------------------------------------
-- Q20. Recency: days since each customer's last order (longest ago first)
-- This is one of the PRD's sample questions.
-- ---------------------------------------------------------------------
SELECT CustomerID,
       MAX(OrderDate) AS last_order_date,
       DATEDIFF((SELECT MAX(OrderDate) FROM orders), MAX(OrderDate)) AS days_since_last_order,
       RANK() OVER (ORDER BY MAX(OrderDate) ASC) AS recency_rank
FROM orders
GROUP BY CustomerID
ORDER BY days_since_last_order DESC, CustomerID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q21. NTILE: top 10% of delivery partners by completed deliveries and rating
-- NTILE(10) cuts the list into 10 equal groups; group 1 is the top 10%.
-- This is one of the PRD's sample questions.
-- ---------------------------------------------------------------------
SELECT DeliveryPartnerID, Name, City, Rating, CompletedDeliveries, decile
FROM (
    SELECT DeliveryPartnerID, Name, City, Rating, CompletedDeliveries,
           NTILE(10) OVER (ORDER BY CompletedDeliveries DESC, Rating DESC, DeliveryPartnerID) AS decile
    FROM delivery_partners
) ranked
WHERE decile = 1
ORDER BY CompletedDeliveries DESC, Rating DESC, DeliveryPartnerID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q22. Running total: cumulative revenue month by month
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT DATE_FORMAT(OrderDate, '%Y-%m') AS order_month,
           ROUND(SUM(FinalAmount), 2)      AS revenue
    FROM orders
    WHERE OrderStatus IN ('Delivered', 'Delivered Late')
    GROUP BY DATE_FORMAT(OrderDate, '%Y-%m')
)
SELECT order_month, revenue,
       ROUND(SUM(revenue) OVER (ORDER BY order_month), 2) AS running_total
FROM monthly
ORDER BY order_month;

-- ---------------------------------------------------------------------
-- Q23. Coupon performance: which codes gave the most discount
-- This is one of the PRD's sample questions.
-- ---------------------------------------------------------------------
SELECT p.CampaignName, p.CouponCode,
       COUNT(o.OrderID)                       AS orders_using_coupon,
       ROUND(SUM(o.Discount), 2)              AS total_discount_value,
       ROUND(SUM(o.FinalAmount), 2)           AS revenue_from_coupon_orders,
       RANK() OVER (ORDER BY SUM(o.Discount) DESC) AS discount_rank
FROM promotions p
JOIN orders o ON o.CouponCode = p.CouponCode
GROUP BY p.CampaignName, p.CouponCode
ORDER BY total_discount_value DESC, p.CouponCode
LIMIT 10;

-- #####################################################################
-- PART 2: DATE HANDLING (date parts, date arithmetic, month/quarter buckets)
-- #####################################################################

-- ---------------------------------------------------------------------
-- Q24. Quarter buckets: orders and revenue per quarter
-- ---------------------------------------------------------------------
SELECT YEAR(OrderDate)    AS order_year,
       QUARTER(OrderDate) AS order_quarter,
       COUNT(*)           AS orders,
       ROUND(SUM(FinalAmount), 2) AS revenue
FROM orders
WHERE OrderStatus IN ('Delivered', 'Delivered Late')
GROUP BY YEAR(OrderDate), QUARTER(OrderDate)
ORDER BY order_year, order_quarter;

-- ---------------------------------------------------------------------
-- Q25. Date part: orders by day of the week
-- ---------------------------------------------------------------------
SELECT DAYNAME(OrderDate) AS day_of_week,
       COUNT(*)           AS order_count,
       ROUND(SUM(FinalAmount), 2) AS total_revenue
FROM orders
GROUP BY DAYNAME(OrderDate), WEEKDAY(OrderDate)
ORDER BY WEEKDAY(OrderDate);

-- ---------------------------------------------------------------------
-- Q26. Date arithmetic: customer tenure in days (longest-registered first)
-- ---------------------------------------------------------------------
SELECT CustomerID, Name, RegistrationDate,
       DATEDIFF((SELECT MAX(OrderDate) FROM orders), RegistrationDate) AS tenure_days
FROM customers
ORDER BY tenure_days DESC, CustomerID
LIMIT 10;

-- #####################################################################
-- PART 3: VIEWS
-- A view is a saved query that you can use like a table.
-- Run the two CREATE statements once, then query the views (Q27, Q28).
-- #####################################################################

-- View 1: one row per order with the customer, restaurant and partner details
CREATE OR REPLACE VIEW vw_order_base AS
SELECT o.OrderID, o.CustomerID, o.RestaurantID, o.DeliveryPartnerID,
       o.OrderDate, o.OrderTime, o.DeliveryTimeMinutes, o.FinalAmount, o.OrderStatus,
       c.City  AS customer_city,
       r.City  AS restaurant_city,
       r.Cuisine,
       r.Rating AS restaurant_rating,
       dp.VehicleType,
       dp.Rating AS partner_rating
FROM orders o
JOIN customers c          ON c.CustomerID = o.CustomerID
JOIN restaurants r        ON r.RestaurantID = o.RestaurantID
JOIN delivery_partners dp ON dp.DeliveryPartnerID = o.DeliveryPartnerID;

-- View 2: restaurant scorecard
CREATE OR REPLACE VIEW vw_restaurant_scorecard AS
SELECT r.RestaurantID, r.RestaurantName, r.City, r.Rating,
       COUNT(o.OrderID) AS total_orders,
       SUM(CASE WHEN o.OrderStatus = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
       ROUND(100.0 * SUM(CASE WHEN o.OrderStatus = 'Cancelled' THEN 1 ELSE 0 END)
             / NULLIF(COUNT(o.OrderID), 0), 2) AS cancellation_rate_pct,
       ROUND(AVG(o.DeliveryTimeMinutes), 2) AS avg_delivery_time
FROM restaurants r
LEFT JOIN orders o ON o.RestaurantID = r.RestaurantID
GROUP BY r.RestaurantID, r.RestaurantName, r.City, r.Rating;

-- ---------------------------------------------------------------------
-- Q27. Using view 1: average delivery time by restaurant city
-- (the top rows should equal your Q2 result)
-- ---------------------------------------------------------------------
SELECT restaurant_city,
       ROUND(AVG(DeliveryTimeMinutes), 2) AS avg_delivery_minutes,
       COUNT(*) AS order_count
FROM vw_order_base
WHERE OrderStatus IN ('Delivered', 'Delivered Late')
GROUP BY restaurant_city
ORDER BY avg_delivery_minutes DESC
LIMIT 5;

-- ---------------------------------------------------------------------
-- Q28. Using view 2: restaurants with the highest cancellation rate
--      (only restaurants with at least 15 orders, so tiny samples do not mislead)
-- ---------------------------------------------------------------------
SELECT RestaurantID, RestaurantName, City, total_orders, cancelled_orders, cancellation_rate_pct
FROM vw_restaurant_scorecard
WHERE total_orders >= 15
ORDER BY cancellation_rate_pct DESC, RestaurantID
LIMIT 10;

-- #####################################################################
-- PART 4: INDEX WITH A DOCUMENTED PERFORMANCE REASON
-- Why: the dashboard and many reports filter orders by a date or date range
-- (for example "last week" or "December"). The table already has an index
-- on (CustomerID, OrderDate), but that index cannot help when the query has
-- no CustomerID, so MySQL reads every row. An index on OrderDate alone
-- lets MySQL jump straight to the matching dates.
-- Test: run the EXPLAIN below BEFORE and AFTER creating the index and write
-- down 'type', 'key' and 'rows' from each result.
-- #####################################################################

-- Step 1: BEFORE. Expect type = ALL and rows about 20,000 (full table scan)
EXPLAIN SELECT OrderID, FinalAmount
FROM orders
WHERE OrderDate BETWEEN '2024-12-01' AND '2024-12-07';

-- Step 2: create the index
CREATE INDEX idx_orders_orderdate ON orders (OrderDate);

-- Step 3: AFTER. Expect type = range, key = idx_orders_orderdate, far fewer rows
EXPLAIN SELECT OrderID, FinalAmount
FROM orders
WHERE OrderDate BETWEEN '2024-12-01' AND '2024-12-07';
