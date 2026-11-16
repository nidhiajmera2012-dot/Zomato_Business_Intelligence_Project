-- =====================================================================
-- ZOMATO BI PROJECT - DAY 4: 13 BUSINESS QUERIES (MySQL 8)
-- Run against the cleaned tables in the zomato_bi database.
-- HOW TO RUN: click inside ONE query, then press Ctrl + Shift + Enter
-- (this runs only the query where your cursor is).
-- Revenue counts orders with status 'Delivered' or 'Delivered Late'.
-- The data covers 2023-01-01 to 2024-12-31, so "last 6 months" means the
-- last 6 months of the DATA, not of today's date.
-- =====================================================================

USE zomato_bi;

-- ---------------------------------------------------------------------
-- Q1. JOIN + aggregation: top 10 restaurants by revenue, last 6 months
-- ---------------------------------------------------------------------
SELECT r.RestaurantID, r.RestaurantName, r.City,
       ROUND(SUM(o.FinalAmount), 2) AS total_revenue,
       COUNT(o.OrderID)             AS total_orders
FROM orders o
JOIN restaurants r ON r.RestaurantID = o.RestaurantID
WHERE o.OrderDate > DATE_SUB((SELECT MAX(OrderDate) FROM orders), INTERVAL 6 MONTH)
  AND o.OrderStatus IN ('Delivered', 'Delivered Late')
GROUP BY r.RestaurantID, r.RestaurantName, r.City
ORDER BY total_revenue DESC
LIMIT 10;

-- ---------------------------------------------------------------------
-- Q2. JOIN + aggregation: average delivery time by city, slowest first
-- ---------------------------------------------------------------------
SELECT r.City,
       ROUND(AVG(o.DeliveryTimeMinutes), 2) AS avg_delivery_minutes,
       COUNT(*)                             AS order_count
FROM orders o
JOIN restaurants r ON r.RestaurantID = o.RestaurantID
WHERE o.OrderStatus IN ('Delivered', 'Delivered Late')
GROUP BY r.City
ORDER BY avg_delivery_minutes DESC;

-- ---------------------------------------------------------------------
-- Q3. GROUP BY + HAVING: cuisines with 500+ delivered orders and an
--     average restaurant rating above 3.9
-- (The PRD version used 4.0, which returns nothing on this data because no
--  cuisine averages above 3.99. Testing a query means checking this.)
-- ---------------------------------------------------------------------
SELECT r.Cuisine,
       COUNT(o.OrderID)         AS delivered_orders,
       ROUND(AVG(r.Rating), 2)  AS avg_cuisine_rating
FROM orders o
JOIN restaurants r ON r.RestaurantID = o.RestaurantID
WHERE o.OrderStatus = 'Delivered'
GROUP BY r.Cuisine
HAVING COUNT(o.OrderID) > 500 AND AVG(r.Rating) > 3.9
ORDER BY delivered_orders DESC;

-- ---------------------------------------------------------------------
-- Q4. Aggregation with CASE: cancellation rate by cuisine
-- ---------------------------------------------------------------------
SELECT r.Cuisine,
       SUM(CASE WHEN o.OrderStatus = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
       COUNT(*) AS total_orders,
       ROUND(100.0 * SUM(CASE WHEN o.OrderStatus = 'Cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS cancellation_rate_pct
FROM orders o
JOIN restaurants r ON r.RestaurantID = o.RestaurantID
GROUP BY r.Cuisine
ORDER BY cancellation_rate_pct DESC;

-- ---------------------------------------------------------------------
-- Q5. INNER JOIN (3 tables): orders with customer, restaurant and partner
-- ---------------------------------------------------------------------
SELECT o.OrderID, c.Name AS customer_name, r.RestaurantName,
       dp.Name AS delivery_partner, o.FinalAmount, o.OrderStatus
FROM orders o
INNER JOIN customers c          ON c.CustomerID = o.CustomerID
INNER JOIN restaurants r        ON r.RestaurantID = o.RestaurantID
INNER JOIN delivery_partners dp ON dp.DeliveryPartnerID = o.DeliveryPartnerID
ORDER BY o.OrderID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q6. LEFT JOIN: every restaurant with its feedback count (fewest first)
-- ---------------------------------------------------------------------
SELECT r.RestaurantID, r.RestaurantName,
       COUNT(f.FeedbackID)              AS feedback_count,
       ROUND(AVG(f.CustomerRating), 2)  AS avg_customer_rating
FROM restaurants r
LEFT JOIN orders o            ON o.RestaurantID = r.RestaurantID
LEFT JOIN customer_feedback f ON f.OrderID = o.OrderID
GROUP BY r.RestaurantID, r.RestaurantName
ORDER BY feedback_count ASC, r.RestaurantID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q7. UNION: one "attention list" of low-rated restaurants and partners
-- ---------------------------------------------------------------------
SELECT RestaurantID AS entity_id, RestaurantName AS entity_name,
       'Restaurant' AS entity_type, Rating
FROM restaurants
WHERE Rating < 3.0
UNION
SELECT DeliveryPartnerID, Name, 'DeliveryPartner', Rating
FROM delivery_partners
WHERE Rating < 3.0
ORDER BY Rating ASC
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q8. CASE inside a subquery: how many orders fall in each speed tier
-- ---------------------------------------------------------------------
SELECT delivery_tier, COUNT(*) AS orders_in_tier
FROM (
    SELECT CASE
               WHEN DeliveryTimeMinutes IS NULL THEN 'Unknown'
               WHEN DeliveryTimeMinutes <= 20   THEN 'Fast'
               WHEN DeliveryTimeMinutes <= 40   THEN 'On Time'
               WHEN DeliveryTimeMinutes <= 60   THEN 'Delayed'
               ELSE 'Severely Delayed'
           END AS delivery_tier
    FROM orders
) t
GROUP BY delivery_tier
ORDER BY orders_in_tier DESC;

-- ---------------------------------------------------------------------
-- Q9. CTE + CASE: customer value segments by lifetime spend
-- (The PRD thresholds of 3,000 / 10,000 / 20,000 would put almost everyone
--  in Bronze, because the top customer spent only about 4,000. We use
--  thresholds that fit this data.)
-- ---------------------------------------------------------------------
WITH customer_spend AS (
    SELECT CustomerID, SUM(FinalAmount) AS lifetime_spend
    FROM orders
    WHERE OrderStatus IN ('Delivered', 'Delivered Late')
    GROUP BY CustomerID
)
SELECT value_segment, COUNT(*) AS customers, ROUND(AVG(lifetime_spend), 2) AS avg_spend
FROM (
    SELECT lifetime_spend,
           CASE WHEN lifetime_spend >= 1500 THEN 'Platinum'
                WHEN lifetime_spend >= 1000 THEN 'Gold'
                WHEN lifetime_spend >= 500  THEN 'Silver'
                ELSE 'Bronze' END AS value_segment
    FROM customer_spend
) s
GROUP BY value_segment
ORDER BY avg_spend DESC;

-- ---------------------------------------------------------------------
-- Q10. Scalar subquery: restaurants costing more than the average
-- ---------------------------------------------------------------------
SELECT RestaurantID, RestaurantName, City, AverageCost
FROM restaurants
WHERE AverageCost > (SELECT AVG(AverageCost) FROM restaurants)
ORDER BY AverageCost DESC, RestaurantID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q11. Correlated subquery: customers whose most recent order was cancelled
-- ---------------------------------------------------------------------
SELECT c.CustomerID, c.Name
FROM customers c
WHERE (
    SELECT o.OrderStatus
    FROM orders o
    WHERE o.CustomerID = c.CustomerID
    ORDER BY o.OrderDate DESC, o.OrderTime DESC
    LIMIT 1
) = 'Cancelled'
ORDER BY c.CustomerID
LIMIT 20;

-- ---------------------------------------------------------------------
-- Q12. CTE: the 10 best city-months by revenue
-- ---------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT r.City,
           DATE_FORMAT(o.OrderDate, '%Y-%m') AS order_month,
           ROUND(SUM(o.FinalAmount), 2)      AS revenue
    FROM orders o
    JOIN restaurants r ON r.RestaurantID = o.RestaurantID
    WHERE o.OrderStatus IN ('Delivered', 'Delivered Late')
    GROUP BY r.City, DATE_FORMAT(o.OrderDate, '%Y-%m')
)
SELECT City, order_month, revenue
FROM monthly_revenue
ORDER BY revenue DESC
LIMIT 10;

-- ---------------------------------------------------------------------
-- Q13. Multi-CTE: one-time vs repeat customers
-- ---------------------------------------------------------------------
WITH order_counts AS (
    SELECT CustomerID, COUNT(*) AS order_count
    FROM orders
    GROUP BY CustomerID
),
customer_segments AS (
    SELECT CustomerID,
           CASE WHEN order_count = 1 THEN 'One-Time' ELSE 'Repeat' END AS segment
    FROM order_counts
)
SELECT segment, COUNT(*) AS num_customers
FROM customer_segments
GROUP BY segment;
