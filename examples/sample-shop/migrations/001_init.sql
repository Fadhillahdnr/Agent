CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer_id INT REFERENCES customers(id),
  total NUMERIC(12,2) NOT NULL,
  status TEXT DEFAULT 'new',
  created_at TIMESTAMP NOT NULL
);
