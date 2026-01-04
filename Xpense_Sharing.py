import streamlit as st
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
from pydantic import BaseModel, EmailStr, constr, validator
from werkzeug.security import generate_password_hash, check_password_hash
import unittest
from unittest.mock import patch
import os

# Database setup
DB_NAME = 'expenses.db'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()

# Create tables in the database for users, expenses, and expense splits
c.executescript('''
    CREATE TABLE IF NOT EXISTS users
    (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, mobile TEXT, password TEXT);
    
    CREATE TABLE IF NOT EXISTS expenses
    (id INTEGER PRIMARY KEY, amount REAL, description TEXT, 
    payer_id INTEGER, split_method TEXT);
    
    CREATE TABLE IF NOT EXISTS expense_splits
    (id INTEGER PRIMARY KEY, expense_id INTEGER, user_id INTEGER, 
    amount REAL);
    
    CREATE INDEX IF NOT EXISTS idx_expense_splits_user_id ON expense_splits(user_id);
    CREATE INDEX IF NOT EXISTS idx_expense_splits_expense_id ON expense_splits(expense_id);
''')
conn.commit()

# Dataclass to represent a User
@dataclass
class User:
    id: int  # Unique identifier for the user
    name: str  # Name of the user
    email: str  # Email address of the user
    mobile: str  # Mobile number of the user

# Dataclass to represent an Expense
@dataclass
class Expense:
    id: int  # Unique identifier for the expense
    amount: float  # Amount of the expense
    description: str  # Description of the expense
    payer_id: int  # ID of the user who paid for the expense
    split_method: str  # Method used to split the expense

# Dataclass to represent an Expense Split
@dataclass
class ExpenseSplit:
    id: int  # Unique identifier for the expense split
    expense_id: int  # ID of the associated expense
    user_id: int  # ID of the user associated with this split
    amount: float  # Amount owed by this user for this expense

# Pydantic model for user registration with validation
class UserRegistration(BaseModel):
    name: str  # Name of the user
    email: EmailStr  # Email address of the user
    mobile: constr(min_length=10, max_length=15)  # Mobile number of the user
    password: constr(min_length=8)  # Password for the user

    # Validator to ensure mobile number contains only digits
    @validator('mobile')
    def mobile_must_be_numeric(cls, v):
        if not v.isdigit():
            raise ValueError('Mobile number must contain only digits')
        return v

    # Validator to ensure password strength
    @validator('password')
    def password_strength(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v

# Function to create a new user in the database
def create_user(name: str, email: str, mobile: str, password: str) -> Optional[User]:
    try:
        # Hash the password before storing it
        hashed_password = generate_password_hash(password)
        c.execute("INSERT INTO users (name, email, mobile, password) VALUES (?, ?, ?, ?)",
                  (name, email, mobile, hashed_password))
        conn.commit()
        # Return a User object with the new user's details
        return User(c.lastrowid, name, email, mobile)
    except sqlite3.IntegrityError:
        # Handle the case where the email already exists
        st.error("User with this email already exists.")
        return None

# Function to get a user by their email and password
def get_user(email: str, password: str) -> Optional[User]:
    c.execute("SELECT id, name, email, mobile, password FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    if user:
        # Check if the provided password matches the stored hashed password
        user_id, name, email, mobile, stored_password = user
        if check_password_hash(stored_password, password):
            # Return a User object with the user's details
            return User(user_id, name, email, mobile)
    return None

# Function to get a user by their ID
def get_user_by_id(user_id: int) -> Optional[User]:
    c.execute("SELECT id, name, email, mobile FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if user:
        # Return a User object with the user's details
        return User(*user)
    return None

# Function to get all users from the database
def get_all_users() -> List[User]:
    c.execute("SELECT id, name, email, mobile FROM users")
    # Return a list of User objects for all users
    return [User(*user) for user in c.fetchall()]

# Function to create a new expense in the database
def create_expense(amount: float, description: str, payer_id: int,
                   split_method: str, splits: Dict[int, float]) -> Expense:
    c.execute("""INSERT INTO expenses (amount, description, payer_id, split_method)
                 VALUES (?, ?, ?, ?)""", (amount, description, payer_id, split_method))
    expense_id = c.lastrowid  # Get the ID of the newly created expense

    # Insert the expense splits into the expense_splits table
    split_data = [(expense_id, user_id, split_amount) for user_id, split_amount in splits.items()]
    c.executemany("""INSERT INTO expense_splits (expense_id, user_id, amount)
                     VALUES (?, ?, ?)""", split_data)

    conn.commit()
    # Return an Expense object with the new expense's details
    return Expense(expense_id, amount, description, payer_id, split_method)

# Function to get all expenses for a specific user
def get_user_expenses(user_id: int) -> List[Expense]:
    c.execute("""SELECT DISTINCT e.* FROM expenses e
                 JOIN expense_splits es ON e.id = es.expense_id
                 WHERE es.user_id = ?""", (user_id,))
    # Return a list of Expense objects for the user's expenses
    return [Expense(*expense) for expense in c.fetchall()]

# Function to get all expenses from the database
def get_all_expenses() -> List[Expense]:
    c.execute("SELECT * FROM expenses")
    # Return a list of Expense objects for all expenses
    return [Expense(*expense) for expense in c.fetchall()]

# Function to generate a balance sheet for all users
def get_balance_sheet() -> pd.DataFrame:
    c.execute("""SELECT u.name, 
                 SUM(CASE WHEN e.payer_id = u.id THEN e.amount ELSE 0 END) as paid,
                 SUM(es.amount) as owed
                 FROM users u
                 LEFT JOIN expense_splits es ON u.id = es.user_id
                 LEFT JOIN expenses e ON es.expense_id = e.id
                 GROUP BY u.id""")
    # Create a DataFrame with the balance sheet data
    df = pd.DataFrame(c.fetchall(), columns=['Name', 'Paid', 'Owed'])
    # Calculate the balance for each user
    df['Balance'] = df['Paid'] - df['Owed']
    return df

# Set the page title and layout
st.set_page_config(page_title="Expense Sharing App", layout="wide")
st.title("Expense Sharing App")

# Authentication section
# Check if the user is logged in
if 'user_id' not in st.session_state:
    st.session_state.user_id = None

# Login/Signup tabs
if st.session_state.user_id is None:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    # Login tab
    with tab1:
        st.header("Login")
        # Input fields for email and password
        email = st.text_input("Email")
        password = st.text_input("Password", type='password')

        # Login button
        if st.button("Login"):
            # Try to authenticate the user
            user = get_user(email, password)
            if user:
                # If authentication is successful, set the user's ID in the session state
                st.session_state.user_id = user.id
                st.success(f"Welcome, {user.name}!")
            else:
                # If authentication fails, show an error message
                st.error("Invalid credentials.")

    # Sign Up tab
    with tab2:
        st.header("Sign Up")
        # Form for user registration
        with st.form("signup_form"):
            # Input fields for name, email, mobile, and password
            name = st.text_input("Name")
            email = st.text_input("Email")
            mobile = st.text_input("Mobile")
            password = st.text_input("Password", type='password')
            # Submit button for the form
            submit_button = st.form_submit_button("Sign Up")

            # If the form is submitted
            if submit_button:
                try:
                    # Create a UserRegistration object to validate the input
                    user_data = UserRegistration(name=name, email=email, mobile=mobile, password=password)
                    # Create a new user in the database
                    new_user = create_user(user_data.name, user_data.email, user_data.mobile, user_data.password)
                    if new_user:
                        # If user creation is successful, show a success message
                        st.success(f"User created: {new_user.name}. Please log in.")
                except ValueError as e:
                    # If validation fails, show an error message
                    st.error(str(e))

else:
    # If the user is logged in, show the navigation sidebar
    page = st.sidebar.selectbox("Choose a page", ["Expenses", "Balance Sheet", "Logout"])

    if page == "Expenses":
        st.header("Expense Management")

        # Form for creating a new expense
        with st.form("create_expense"):
            st.subheader("Create New Expense")
            # Input fields for amount, description, payer, and split method
            amount = st.number_input("Amount", min_value=0.01, step=0.01)
            description = st.text_input("Description")
            payer = st.selectbox("Payer", options=get_all_users(), format_func=lambda x: x.name)
            split_method = st.selectbox("Split Method", options=["Equal", "Exact", "Percentage"])

            # Get all users for expense splitting
            users = get_all_users()
            splits = {}  # Dictionary to store the expense splits

            # Calculate expense splits based on the selected split method
            if split_method == "Equal":
                split_amount = amount / len(users)
                for user in users:
                    splits[user.id] = split_amount
            elif split_method == "Exact":
                remaining = amount
                for i, user in enumerate(users):
                    if i == len(users) - 1:
                        splits[user.id] = remaining
                    else:
                        # Input field for the amount for each user
                        split = st.number_input(f"Amount for {user.name}",
                                                min_value=0.0, max_value=remaining, step=0.01)
                        splits[user.id] = split
                        remaining -= split
            elif split_method == "Percentage":
                remaining = 100.0
                for i, user in enumerate(users):
                    if i == len(users) - 1:
                        percent = remaining
                    else:
                        # Input field for the percentage for each user
                        percent = st.number_input(f"Percentage for {user.name}",
                                                  min_value=0.0, max_value=remaining, step=0.1)
                    splits[user.id] = amount * (percent / 100)
                    remaining -= percent

            # Submit button for the form
            submit_button = st.form_submit_button("Create Expense")

            # If the form is submitted
            if submit_button:
                # Create a new expense in the database
                new_expense = create_expense(amount, description, payer.id, split_method, splits)
                st.success(f"Expense created: {new_expense.description}")

        # Display the user's expenses
        st.subheader("Your Expenses")
        expenses = get_user_expenses(st.session_state.user_id)
        # Create a DataFrame to display the expenses
        expense_df = pd.DataFrame([(e.id, e.amount, e.description, get_user_by_id(e.payer_id).name, e.split_method)
                                   for e in expenses],
                                  columns=['ID', 'Amount', 'Description', 'Payer', 'Split Method'])

        # Display the expenses DataFrame
        st.dataframe(expense_df)

    elif page == "Balance Sheet":
        st.header("Balance Sheet")

        # Generate the balance sheet DataFrame
        balance_df = get_balance_sheet()
        st.dataframe(balance_df)

        # Download button for the balance sheet
        csv = balance_df.to_csv(index=False)
        st.download_button(
            label="Download Balance Sheet",
            data=csv,
            file_name="balance_sheet.csv",
            mime="text/csv",
        )

    elif page == "Logout":
        # Logout functionality
        st.session_state.user_id = None
        st.success("Logged out successfully!")

# Close the database connection when the app exits
conn.close()

# Unit tests for the application
class TestExpenseSharingApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a separate test database
        cls.test_db = 'test_expenses.db'
        cls.conn = sqlite3.connect(cls.test_db)
        cls.c = cls.conn.cursor()

        # Create tables in the test database
        cls.c.executescript('''
            CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, mobile TEXT, password TEXT);
            
            CREATE TABLE IF NOT EXISTS expenses
            (id INTEGER PRIMARY KEY, amount REAL, description TEXT, 
            payer_id INTEGER, split_method TEXT);
            
            CREATE TABLE IF NOT EXISTS expense_splits
            (id INTEGER PRIMARY KEY, expense_id INTEGER, user_id INTEGER, 
            amount REAL);
        ''')
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        # Close the test database connection and delete the test database file
        cls.conn.close()
        os.remove(cls.test_db)

    def setUp(self):
        # Clear the test database before each test
        self.c.execute("DELETE FROM users")
        self.c.execute("DELETE FROM expenses")
        self.c.execute("DELETE FROM expense_splits")
        self.conn.commit()

    def create_user(self, name, email, mobile, password):
        # Helper function to create a user in the test database
        hashed_password = generate_password_hash(password)
        self.c.execute("INSERT INTO users (name, email, mobile, password) VALUES (?, ?, ?, ?)",
                       (name, email, mobile, hashed_password))
        self.conn.commit()
        return User(self.c.lastrowid, name, email, mobile)

    def get_user(self, email, password):
        # Helper function to get a user by email and password from the test database
        self.c.execute("SELECT id, name, email, mobile, password FROM users WHERE email = ?", (email,))
        user = self.c.fetchone()
        if user and check_password_hash(user[4], password):
            return User(user[0], user[1], user[2], user[3])
        return None

    def create_expense(self, amount, description, payer_id, split_method, splits):
        # Helper function to create an expense in the test database
        self.c.execute("""INSERT INTO expenses (amount, description, payer_id, split_method)
                     VALUES (?, ?, ?, ?)""", (amount, description, payer_id, split_method))
        expense_id = self.c.lastrowid

        split_data = [(expense_id, user_id, split_amount) for user_id, split_amount in splits.items()]
        self.c.executemany("""INSERT INTO expense_splits (expense_id, user_id, amount)
                         VALUES (?, ?, ?)""", split_data)

        self.conn.commit()
        return Expense(expense_id, amount, description, payer_id, split_method)

    def get_user_expenses(self, user_id):
        # Helper function to get expenses for a user from the test database
        self.c.execute("""SELECT DISTINCT e.* FROM expenses e
                     JOIN expense_splits es ON e.id = es.expense_id
                     WHERE es.user_id = ?""", (user_id,))
        return [Expense(*expense) for expense in self.c.fetchall()]

    def test_create_user(self):
        # Test case to create a user and verify its details
        user = self.create_user("Test User", "test@example.com", "1234567890", "Password123")
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "Test User")
        self.assertEqual(user.email, "test@example.com")

    def test_get_user(self):
        # Test case to get a user by email and password and verify its details
        self.create_user("Test User", "test@example.com", "1234567890", "Password123")
        user = self.get_user("test@example.com", "Password123")
        self.assertIsNotNone(user)
        self.assertEqual(user.name, "Test User")

    def test_create_expense(self):
        # Test case to create an expense and verify its details
        user = self.create_user("Test User", "test@example.com", "1234567890", "Password123")
        expense = self.create_expense(100.0, "Test Expense", user.id, "Equal", {user.id: 100.0})
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount, 100.0)
        self.assertEqual(expense.description, "Test Expense")

    def test_get_user_expenses(self):
        # Test case to get expenses for a user and verify the result
        user = self.create_user("Test User", "test@example.com", "1234567890", "Password123")
        self.create_expense(100.0, "Test Expense", user.id, "Equal", {user.id: 100.0})
        expenses = self.get_user_expenses(user.id)
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].description, "Test Expense")

if __name__ == "__main__":
    unittest.main()
