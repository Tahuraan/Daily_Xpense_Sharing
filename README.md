# Expense Sharing App

## Overview
This is an expense sharing application built using Streamlit and SQLite. It allows users to register, log in, create and manage expenses, and view their balance sheet. The app ensures secure user authentication, provides various expense splitting methods, and offers a comprehensive overview of each user's financial contributions.

## Features
- User Registration and Login: Users can create an account with their name, email, mobile number, and password. The app ensures password strength with validation.
- Expense Management: Users can create new expenses, specify a payer, and choose from different splitting methods (Equal, Exact, Percentage).
- Balance Sheet: Users can view a balance sheet showing their paid, owed, and overall balance amounts.
- Download Balance Sheet: Users can download their balance sheet as a CSV file.
- Secure Authentication: Passwords are stored in the database using hashing for security.
- Responsive Design: The app is designed with a wide layout for better usability.

## Database Structure
The application uses an SQLite database with the following tables:
- `users`: Stores user information (id, name, email, mobile, password).
- `expenses`: Stores expense information (id, amount, description, payer_id, split_method).
- `expense_splits`: Stores individual expense splits (id, expense_id, user_id, amount).

## Usage
1. Run the Streamlit app: `streamlit run app.py`
2. Register a new user or log in with existing credentials.
3. Navigate through the sidebar to manage expenses, view the balance sheet, or log out.
4. In the "Expenses" section, create new expenses and choose the splitting method.
5. In the "Balance Sheet" section, view and download the balance sheet.

## Testing
The application includes a set of unit tests using the `unittest` framework. These tests cover user creation, authentication, expense creation, and expense retrieval.

To run the tests:
`python -m unittest`

## Dependencies
- Streamlit
- SQLite
- pandas
- pydantic
- werkzeug
- unittest
