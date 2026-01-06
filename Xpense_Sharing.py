import streamlit as st
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
from pydantic import BaseModel, EmailStr, constr, validator, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- DATABASE ----------------
DB_NAME = "expenses.db"
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()

c.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    name TEXT,
    email TEXT UNIQUE,
    mobile TEXT,
    password TEXT
);

CREATE TABLE IF NOT EXISTS expenses(
    id INTEGER PRIMARY KEY,
    amount REAL,
    description TEXT,
    payer_id INTEGER,
    split_method TEXT
);

CREATE TABLE IF NOT EXISTS expense_splits(
    id INTEGER PRIMARY KEY,
    expense_id INTEGER,
    user_id INTEGER,
    amount REAL
);
""")
conn.commit()

# ---------------- MODELS ----------------
@dataclass
class User:
    id: int
    name: str
    email: str
    mobile: str

@dataclass
class Expense:
    id: int
    amount: float
    description: str
    payer_id: int
    split_method: str

class UserRegistration(BaseModel):
    name: str
    email: EmailStr
    mobile: constr(min_length=10, max_length=15)
    password: constr(min_length=8)

    @validator("mobile")
    def digits_only(cls, v):
        if not v.isdigit():
            raise ValueError("Mobile must be numeric")
        return v

    @validator("password")
    def strong_password(cls, v):
        if not any(i.isdigit() for i in v) or not any(i.isupper() for i in v):
            raise ValueError("Password must contain number & uppercase")
        return v

# ---------------- HELPERS ----------------
def create_user(name, email, mobile, password):
    try:
        c.execute(
            "INSERT INTO users VALUES (NULL,?,?,?,?)",
            (name, email, mobile, generate_password_hash(password))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def authenticate(email, password):
    c.execute("SELECT id,name,email,mobile,password FROM users WHERE email=?", (email,))
    row = c.fetchone()
    if row and check_password_hash(row[4], password):
        return User(row[0], row[1], row[2], row[3])
    return None

def get_users():
    c.execute("SELECT id,name,email,mobile FROM users")
    return [User(*u) for u in c.fetchall()]

def create_expense(amount, desc, payer_id, method, splits):
    c.execute(
        "INSERT INTO expenses VALUES(NULL,?,?,?,?)",
        (amount, desc, payer_id, method)
    )
    eid = c.lastrowid
    for uid, amt in splits.items():
        c.execute(
            "INSERT INTO expense_splits VALUES(NULL,?,?,?)",
            (eid, uid, amt)
        )
    conn.commit()

def user_expenses(uid):
    c.execute("""
        SELECT DISTINCT e.*
        FROM expenses e
        JOIN expense_splits s ON e.id=s.expense_id
        WHERE s.user_id=?
    """, (uid,))
    return [Expense(*e) for e in c.fetchall()]

def balance_sheet():
    c.execute("""
        SELECT u.name,
        COALESCE(p.paid,0) paid,
        COALESCE(o.owed,0) owed
        FROM users u
        LEFT JOIN (
            SELECT payer_id, SUM(amount) paid
            FROM expenses GROUP BY payer_id
        ) p ON u.id=p.payer_id
        LEFT JOIN (
            SELECT user_id, SUM(amount) owed
            FROM expense_splits GROUP BY user_id
        ) o ON u.id=o.user_id
    """)
    df = pd.DataFrame(c.fetchall(), columns=["Name","Paid","Owed"])
    df["Balance"] = df["Paid"] - df["Owed"]
    return df

# ---------------- STREAMLIT UI ----------------
st.set_page_config("Expense Sharing App", layout="wide")
st.title("Expense Sharing App")

if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    t1, t2 = st.tabs(["Login", "Sign Up"])

    with t1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = authenticate(email, password)
            if user:
                st.session_state.user = user
                st.success("Login successful")
            else:
                st.error("Invalid credentials")

    with t2:
        with st.form("signup"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            mobile = st.text_input("Mobile")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Register"):
                try:
                    data = UserRegistration(
                        name=name, email=email, mobile=mobile, password=password
                    )
                    if create_user(**data.dict()):
                        st.success("Account created. Please login.")
                    else:
                        st.error("Email already exists")
                except ValidationError as e:
                    st.error(e.errors()[0]["msg"])

else:
    page = st.sidebar.selectbox("Menu", ["Expenses", "Balance Sheet", "Logout"])

    if page == "Expenses":
        users = get_users()
        with st.form("expense"):
            amt = st.number_input("Amount", min_value=0.01)
            desc = st.text_input("Description")
            payer = st.selectbox("Payer", users, format_func=lambda x: x.name)
            method = st.selectbox("Split Method", ["Equal", "Exact"])

            splits = {}
            if method == "Equal":
                for u in users:
                    splits[u.id] = amt / len(users)
            else:
                total = 0
                for u in users:
                    val = st.number_input(f"{u.name}", min_value=0.0)
                    splits[u.id] = val
                    total += val

            if st.form_submit_button("Create"):
                if round(sum(splits.values()), 2) != round(amt, 2):
                    st.error("Split total must equal amount")
                else:
                    create_expense(amt, desc, payer.id, method, splits)
                    st.success("Expense added")

        st.dataframe(pd.DataFrame(
            [(e.description, e.amount, e.split_method) for e in user_expenses(st.session_state.user.id)],
            columns=["Description","Amount","Split"]
        ))

    elif page == "Balance Sheet":
        df = balance_sheet()
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), "balance.csv")

    else:
        st.session_state.user = None
        st.success("Logged out")

