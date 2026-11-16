USE zomato_bi;

DROP TABLE IF EXISTS customer_feedback;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS menu;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS delivery_partners;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS traffic;
DROP TABLE IF EXISTS weather;
DROP TABLE IF EXISTS cities;

CREATE TABLE cities (
    CityID          INT PRIMARY KEY,
    City            VARCHAR(100) NOT NULL UNIQUE,
    Population      BIGINT CHECK (Population > 0),
    Region          VARCHAR(50),
    AverageIncome   DECIMAL(12,2)
);

CREATE TABLE customers (
    CustomerID          INT PRIMARY KEY,
    Name                VARCHAR(150) NOT NULL,
    Age                 SMALLINT CHECK (Age BETWEEN 0 AND 100),
    Gender              VARCHAR(20),
    Phone               VARCHAR(15),
    Email               VARCHAR(150),
    City                VARCHAR(100) NOT NULL,
    State               VARCHAR(100),
    Pincode             VARCHAR(10),
    RegistrationDate    DATE NOT NULL,
    Membership          VARCHAR(30),
    TotalOrders         INT DEFAULT 0 CHECK (TotalOrders >= 0),
    PreferredCuisine    VARCHAR(50),
    CONSTRAINT fk_customers_city FOREIGN KEY (City) REFERENCES cities(City)
);

CREATE TABLE restaurants (
    RestaurantID    INT PRIMARY KEY,
    RestaurantName  VARCHAR(150) NOT NULL,
    Cuisine         VARCHAR(50),
    City            VARCHAR(100) NOT NULL,
    Area            VARCHAR(100),
    OpeningTime     TIME,
    ClosingTime     TIME,
    Rating          DECIMAL(2,1) CHECK (Rating BETWEEN 1.0 AND 5.0),
    AverageCost     DECIMAL(10,2) CHECK (AverageCost >= 0),
    OwnerName       VARCHAR(150),
    RestaurantType  VARCHAR(50),
    Latitude        DECIMAL(9,6),
    Longitude       DECIMAL(9,6),
    CONSTRAINT fk_restaurants_city FOREIGN KEY (City) REFERENCES cities(City)
);

CREATE TABLE menu (
    FoodItemID      INT PRIMARY KEY,
    RestaurantID    INT NOT NULL,
    FoodName        VARCHAR(150) NOT NULL,
    Category        VARCHAR(50),
    Price           DECIMAL(10,2) CHECK (Price >= 0),
    PreparationTime SMALLINT CHECK (PreparationTime >= 0),
    Calories        SMALLINT,
    Availability    VARCHAR(5),
    CONSTRAINT fk_menu_restaurant FOREIGN KEY (RestaurantID) REFERENCES restaurants(RestaurantID)
);

CREATE TABLE delivery_partners (
    DeliveryPartnerID   INT PRIMARY KEY,
    Name                VARCHAR(150) NOT NULL,
    Age                 SMALLINT CHECK (Age BETWEEN 16 AND 70),
    Gender              VARCHAR(20),
    VehicleType         VARCHAR(30),
    JoiningDate         DATE,
    City                VARCHAR(100) NOT NULL,
    Rating              DECIMAL(2,1) CHECK (Rating BETWEEN 1.0 AND 5.0),
    CompletedDeliveries INT DEFAULT 0 CHECK (CompletedDeliveries >= 0),
    AverageDeliveryTime DECIMAL(6,2) CHECK (AverageDeliveryTime >= 0),
    CONSTRAINT fk_dp_city FOREIGN KEY (City) REFERENCES cities(City)
);

CREATE TABLE promotions (
    PromotionID         INT PRIMARY KEY,
    CouponCode          VARCHAR(20) NOT NULL UNIQUE,
    DiscountPercentage  SMALLINT CHECK (DiscountPercentage BETWEEN 0 AND 100),
    CampaignName        VARCHAR(150),
    StartDate           DATE NOT NULL,
    EndDate             DATE NOT NULL,
    CONSTRAINT chk_promo_dates CHECK (EndDate >= StartDate)
);

CREATE TABLE orders (
    OrderID             INT PRIMARY KEY,
    CustomerID          INT NOT NULL,
    RestaurantID        INT NOT NULL,
    DeliveryPartnerID   INT NOT NULL,
    OrderDate           DATE NOT NULL,
    OrderTime           TIME NOT NULL,
    DeliveryTimeMinutes SMALLINT CHECK (DeliveryTimeMinutes >= 0),
    FoodCost            DECIMAL(10,2) CHECK (FoodCost >= 0),
    DeliveryFee         DECIMAL(8,2)  CHECK (DeliveryFee >= 0),
    Discount            DECIMAL(8,2)  DEFAULT 0 CHECK (Discount >= 0),
    CouponCode          VARCHAR(20),
    GST                 DECIMAL(8,2)  DEFAULT 0 CHECK (GST >= 0),
    FinalAmount         DECIMAL(10,2) CHECK (FinalAmount >= 0),
    OrderStatus         VARCHAR(30) NOT NULL,
    PaymentMethod       VARCHAR(30),
    CONSTRAINT fk_orders_customer   FOREIGN KEY (CustomerID)        REFERENCES customers(CustomerID),
    CONSTRAINT fk_orders_restaurant FOREIGN KEY (RestaurantID)      REFERENCES restaurants(RestaurantID),
    CONSTRAINT fk_orders_dp         FOREIGN KEY (DeliveryPartnerID) REFERENCES delivery_partners(DeliveryPartnerID),
    CONSTRAINT fk_orders_coupon     FOREIGN KEY (CouponCode)        REFERENCES promotions(CouponCode)
);

CREATE TABLE order_items (
    OrderItemID     INT PRIMARY KEY,
    OrderID         INT NOT NULL,
    FoodItemID      INT NOT NULL,
    Quantity        SMALLINT CHECK (Quantity > 0),
    UnitPrice       DECIMAL(10,2) CHECK (UnitPrice >= 0),
    TotalPrice      DECIMAL(10,2) CHECK (TotalPrice >= 0),
    CONSTRAINT fk_oi_order FOREIGN KEY (OrderID)    REFERENCES orders(OrderID),
    CONSTRAINT fk_oi_food  FOREIGN KEY (FoodItemID) REFERENCES menu(FoodItemID)
);

CREATE TABLE payments (
    PaymentID       INT PRIMARY KEY,
    OrderID         INT NOT NULL,
    PaymentMethod   VARCHAR(30),
    PaymentStatus   VARCHAR(20),
    TransactionID   VARCHAR(30),
    PaymentDate     DATE,
    CONSTRAINT fk_payments_order FOREIGN KEY (OrderID) REFERENCES orders(OrderID)
);

CREATE TABLE customer_feedback (
    FeedbackID      INT PRIMARY KEY,
    OrderID         INT NOT NULL,
    CustomerRating  SMALLINT CHECK (CustomerRating BETWEEN 1 AND 5),
    DeliveryRating  SMALLINT CHECK (DeliveryRating BETWEEN 1 AND 5),
    FoodRating      SMALLINT CHECK (FoodRating BETWEEN 1 AND 5),
    Review          TEXT,
    Sentiment       VARCHAR(20),
    CONSTRAINT fk_feedback_order FOREIGN KEY (OrderID) REFERENCES orders(OrderID)
);

CREATE TABLE weather (
    WeatherID           INT PRIMARY KEY,
    City                VARCHAR(100) NOT NULL,
    `Date`              DATE NOT NULL,
    Temperature         DECIMAL(5,2),
    Rainfall            DECIMAL(6,2),
    Humidity            SMALLINT,
    WeatherCondition    VARCHAR(30),
    CONSTRAINT fk_weather_city FOREIGN KEY (City) REFERENCES cities(City)
);

CREATE TABLE traffic (
    TrafficID       INT PRIMARY KEY,
    City            VARCHAR(100) NOT NULL,
    `Date`          DATE NOT NULL,
    `Time`          TIME NOT NULL,
    TrafficLevel    VARCHAR(20),
    AverageSpeed    DECIMAL(5,2),
    CONSTRAINT fk_traffic_city FOREIGN KEY (City) REFERENCES cities(City)
);

CREATE INDEX idx_orders_customer_date ON orders(CustomerID, OrderDate);
CREATE INDEX idx_orders_restaurant ON orders(RestaurantID);
CREATE INDEX idx_orders_deliverypartner ON orders(DeliveryPartnerID);
CREATE INDEX idx_weather_city_date ON weather(City, `Date`);
CREATE INDEX idx_traffic_city_date ON traffic(City, `Date`);

SHOW TABLES;