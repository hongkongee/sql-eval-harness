-- company_db 픽스처: NL-to-SQL 테스트셋(data/testset.jsonl)의 정답/예측 쿼리를
-- 동일 조건에서 실행해 비교하기 위한 샘플 스키마 + 데이터 (SQLite 문법)

CREATE TABLE departments (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    location TEXT NOT NULL
);

CREATE TABLE employees (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    salary        INTEGER NOT NULL,
    hire_date     TEXT NOT NULL,
    manager_id    INTEGER REFERENCES employees(id)
);

CREATE TABLE projects (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    budget        INTEGER NOT NULL,
    start_date    TEXT NOT NULL
);

CREATE TABLE customers (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    email   TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    INTEGER NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    order_date  TEXT NOT NULL
);

INSERT INTO departments (id, name, location) VALUES
    (1, 'Engineering', 'Seoul'),
    (2, 'Sales', 'Busan'),
    (3, 'HR', 'Seoul'),
    (4, 'Marketing', 'Incheon'),
    (5, 'Finance', 'Seoul');

INSERT INTO employees (id, name, department_id, salary, hire_date, manager_id) VALUES
    (1, '김민준', 1, 65000000, '2019-03-01', NULL),
    (2, '이서연', 1, 58000000, '2021-07-15', 1),
    (3, '박지훈', 1, 52000000, '2022-05-10', 1),
    (4, '최유진', 2, 60000000, '2018-11-01', NULL),
    (5, '김도윤', 2, 47000000, '2022-09-01', 4),
    (6, '정하은', 2, 45000000, '2023-02-20', 4),
    (7, '강민서', 3, 55000000, '2020-01-10', NULL),
    (8, '김서준', 3, 42000000, '2023-06-01', 7),
    (9, '윤지우', 4, 50000000, '2019-08-15', NULL),
    (10, '임채원', 4, 44000000, '2022-03-01', 9),
    (11, '한지호', 4, 41000000, '2023-01-05', 9),
    (12, '오세훈', 5, 70000000, '2017-04-01', NULL),
    (13, '김하윤', 5, 53000000, '2021-10-10', 12),
    (14, '신유나', 5, 48000000, '2022-11-20', 12),
    (15, '배준호', 1, 39000000, '2023-04-01', 1);

INSERT INTO projects (id, name, department_id, budget, start_date) VALUES
    (1, 'AI 플랫폼 구축', 1, 150000000, '2023-01-15'),
    (2, '백엔드 리뉴얼', 1, 80000000, '2022-06-01'),
    (3, '해외영업 확장', 2, 120000000, '2023-03-01'),
    (4, '신규 채용 시스템', 3, 40000000, '2022-09-01'),
    (5, '브랜드 캠페인', 4, 90000000, '2023-02-10'),
    (6, '회계 시스템 고도화', 5, 110000000, '2022-11-01');

INSERT INTO customers (id, name, email, country) VALUES
    (1, 'John Smith', 'john.smith@example.com', 'USA'),
    (2, 'Emily Davis', 'emily.davis@example.com', 'USA'),
    (3, 'Liam Brown', 'liam.brown@example.com', 'UK'),
    (4, 'Sophia Wilson', 'sophia.wilson@example.com', 'Canada'),
    (5, 'Noah Garcia', 'noah.garcia@example.com', 'USA'),
    (6, 'Ava Martinez', 'ava.martinez@example.com', 'Mexico'),
    (7, 'Yuki Tanaka', 'yuki.tanaka@example.com', 'Japan'),
    (8, 'Mia Anderson', 'mia.anderson@example.com', 'USA');

INSERT INTO products (id, name, category, price) VALUES
    (1, 'Wireless Mouse', 'Electronics', 25000),
    (2, 'Mechanical Keyboard', 'Electronics', 89000),
    (3, 'USB-C Hub', 'Electronics', 35000),
    (4, 'Office Chair', 'Furniture', 150000),
    (5, 'Standing Desk', 'Furniture', 320000),
    (6, 'Notebook Set', 'Stationery', 8000),
    (7, 'Fountain Pen', 'Stationery', 45000),
    (8, 'Monitor 27in', 'Electronics', 280000),
    (9, 'Desk Lamp', 'Furniture', 22000),
    (10, 'Backpack', 'Accessories', 60000);

-- product_id=10(Backpack)은 의도적으로 주문 없음 (nlsql_026 검증용)
-- customer_id=4,8은 의도적으로 주문 없음 (nlsql_024 검증용)
INSERT INTO orders (id, customer_id, product_id, quantity, order_date) VALUES
    (1, 1, 1, 2, '2023-01-10'),
    (2, 1, 4, 1, '2023-01-15'),
    (3, 1, 6, 5, '2023-02-01'),
    (4, 2, 2, 1, '2023-01-20'),
    (5, 2, 8, 1, '2023-03-05'),
    (6, 3, 3, 3, '2023-02-14'),
    (7, 3, 5, 1, '2023-02-20'),
    (8, 5, 7, 2, '2023-01-05'),
    (9, 5, 9, 1, '2023-03-15'),
    (10, 6, 1, 12, '2023-02-25'),
    (11, 7, 2, 1, '2023-01-30');
